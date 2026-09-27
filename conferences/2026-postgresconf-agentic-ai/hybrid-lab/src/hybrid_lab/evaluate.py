"""Run every arm on every FiQA test question and record the results in PostgreSQL."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor

import psycopg

from hybrid_lab import bedrock
from hybrid_lab.arms import ARMS, CANDIDATES, Arm, ArmResult, run_sql_arm
from hybrid_lab.db import LAB_ROOT, sql_text

Progress = Callable[[str], None]


def bm25_available(conn: psycopg.Connection) -> bool:
    """Return True when pg_textsearch is installed and the BM25 index exists."""
    row = conn.execute(
        "SELECT to_regclass('docs_body_bm25') IS NOT NULL"
        " AND EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_textsearch')"
    ).fetchone()
    conn.rollback()
    return bool(row and row[0])


def test_question_ids(conn: psycopg.Connection) -> list[str]:
    """Return the 648 FiQA test question ids in a stable order."""
    ids = conn.execute(
        "SELECT id FROM queries WHERE split = 'test' ORDER BY id::int"
    ).fetchall()
    conn.rollback()
    return [row[0] for row in ids]


def evaluate_sql_arm(
    conn: psycopg.Connection, arm: Arm, query_ids: list[str], progress: Progress = print
) -> None:
    """Run an arm once to warm caches, then again for timing, and store the second pass."""
    for query_id in query_ids:
        run_sql_arm(conn, arm, query_id)
    results = [(query_id, run_sql_arm(conn, arm, query_id)) for query_id in query_ids]
    _store(conn, arm.stage, results)
    progress(f"{arm.stage}: {len(results)} questions")


def evaluate_rerank_arm(
    conn: psycopg.Connection, arm: Arm, workers: int = 8, progress: Progress = print
) -> None:
    """Rerank the stored top 50 of the base arm(s) with Cohere Rerank for every question.

    With several base arms, the candidates are the union of their top 50s, deduplicated.
    """
    base = _stored_candidates(conn, arm.rerank_of)
    if not base:
        raise RuntimeError(f"Run {', '.join(arm.rerank_of)} before {arm.stage}.")
    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(_rerank_one, base))
    _store(conn, arm.stage, results)
    progress(f"{arm.stage}: {len(results)} questions")


def run_all(
    conn: psycopg.Connection, stages: Iterable[str] | None = None, progress: Progress = print
) -> None:
    """Evaluate the requested stages (default: all available) and refresh the scoreboard."""
    wanted = set(stages) if stages is not None else {arm.stage for arm in ARMS}
    has_bm25 = bm25_available(conn)
    query_ids = test_question_ids(conn)
    for arm in ARMS:
        if arm.stage not in wanted:
            continue
        if arm.needs_bm25 and not has_bm25:
            progress(f"{arm.stage}: skipped, pg_textsearch or docs_body_bm25 is missing")
            continue
        if arm.rerank_of:
            evaluate_rerank_arm(conn, arm, progress=progress)
        else:
            evaluate_sql_arm(conn, arm, query_ids, progress=progress)
    refresh_scoreboard(conn)


def refresh_scoreboard(conn: psycopg.Connection) -> list[dict]:
    """Run sql/10_scoreboard.sql (recreates its views) and return the summary rows."""
    with conn.cursor() as cur:
        cur.execute(sql_text("10_scoreboard.sql"))
        while cur.nextset():
            pass
    conn.commit()
    return scoreboard(conn)


def scoreboard(conn: psycopg.Connection) -> list[dict]:
    """Return the scoreboard view, best NDCG@10 first."""
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM scoreboard ORDER BY ndcg_at_10 DESC, stage")
        names = [column.name for column in cur.description]
        rows = [dict(zip(names, row, strict=True)) for row in cur.fetchall()]
    conn.rollback()
    return rows


def write_scoreboard_markdown(rows: list[dict], labels: dict[str, str]) -> str:
    """Write results/scoreboard.md and return its text."""
    lines = [
        "# FiQA scoreboard",
        "",
        "648 FiQA-2018 test questions · PostgreSQL 18.6 · pgvector 0.8.6 · pg_textsearch 1.4.0",
        "· Cohere Embed v4 (1536 dims) and Cohere Rerank 3.5 on Amazon Bedrock.",
        "Latency is local laptop wall time per question; rerank rows include the Bedrock call.",
        "",
        "| Arm | NDCG@10 | Recall@50 | p50 ms | p95 ms | Better / worse than Vector |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        versus = f"{row['better_than_vector']} / {row['worse_than_vector']}"
        lines.append(
            f"| {labels.get(row['stage'], row['stage'])} | {row['ndcg_at_10']} | "
            f"{row['recall_at_50']} | {row['p50_ms']} | {row['p95_ms']} | {versus} |"
        )
    text = "\n".join(lines) + "\n"
    path = LAB_ROOT / "results" / "scoreboard.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text)
    return text


def _stored_candidates(
    conn: psycopg.Connection, stages: tuple[str, ...]
) -> list[tuple[str, str, list[tuple[str, str]], float]]:
    rows = conn.execute(
        """
        SELECT q.id, q.body,
               array_agg(ARRAY[r.doc_id, d.body]
                         ORDER BY array_position(%(stages)s::text[], r.stage), r.rank),
               (SELECT sum(t.elapsed_ms) FROM run_timings t
                 WHERE t.query_id = q.id AND t.stage = ANY(%(stages)s))
          FROM runs r
          JOIN queries q ON q.id = r.query_id
          JOIN docs d ON d.id = r.doc_id
         WHERE r.stage = ANY(%(stages)s) AND r.rank <= %(depth)s
         GROUP BY q.id, q.body
         ORDER BY q.id::int
        """,
        {"stages": list(stages), "depth": CANDIDATES},
    ).fetchall()
    conn.rollback()
    result = []
    for query_id, question, cands, base_ms in rows:
        unique = list(dict.fromkeys((c[0], c[1]) for c in cands))
        result.append((query_id, question, unique, base_ms or 0.0))
    return result


def _rerank_one(item: tuple[str, str, list[tuple[str, str]], float]) -> tuple[str, ArmResult]:
    query_id, question, candidates, base_ms = item
    started = time.perf_counter()
    order = bedrock.rerank(question, [body or " " for _, body in candidates])
    rerank_ms = (time.perf_counter() - started) * 1000
    rows = [
        {"rank": position, "doc_id": candidates[index][0], "score": score}
        for position, (index, score) in enumerate(order, start=1)
    ]
    return query_id, ArmResult(rows=rows, elapsed_ms=base_ms + rerank_ms)


def _store(conn: psycopg.Connection, stage: str, results: list[tuple[str, ArmResult]]) -> None:
    with conn.transaction():
        conn.execute("DELETE FROM runs WHERE stage = %s", (stage,))
        conn.execute("DELETE FROM run_timings WHERE stage = %s", (stage,))
        with conn.cursor().copy(
            "COPY runs (stage, query_id, rank, doc_id, score) FROM STDIN"
        ) as copy:
            for query_id, result in results:
                for row in result.rows[:CANDIDATES]:
                    copy.write_row((stage, query_id, row["rank"], row["doc_id"], row["score"]))
        with conn.cursor().copy(
            "COPY run_timings (stage, query_id, elapsed_ms) FROM STDIN"
        ) as copy:
            for query_id, result in results:
                copy.write_row((stage, query_id, result.elapsed_ms))
    conn.commit()
