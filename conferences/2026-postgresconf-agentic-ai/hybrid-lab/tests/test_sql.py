"""The SQL files behave as the talk claims, on a fixture with known answers."""

from __future__ import annotations

import re

import pytest

from conftest import POSTS, QRELS
from hybrid_lab.arms import ARMS, BY_STAGE, arm_sql, run_sql_arm
from hybrid_lab.evaluate import evaluate_sql_arm, refresh_scoreboard
from hybrid_lab.metrics import ndcg_at_k

RAINY_DAY, ROTH = "101", "102"


def ranked(conn, stage: str, query_id: str) -> list[dict]:
    return run_sql_arm(conn, BY_STAGE[stage], query_id).rows


def ids(rows: list[dict]) -> list[str]:
    return [row["doc_id"] for row in rows]


def test_every_sql_arm_has_a_marker_and_exactly_one_query():
    for arm in ARMS:
        if arm.sql_file is None:
            continue
        statements = [s for s in re.split(r";[ \t]*\n", arm_sql(arm) + "\n") if s.strip()]
        queries = [s for s in statements if not s.lstrip().upper().startswith("SET ")]
        assert len(queries) == 1, arm.sql_file
        assert queries[0].lstrip().upper().startswith(("WITH", "SELECT")), arm.sql_file


def test_all_words_matches_nothing_for_a_natural_question(conn):
    assert ranked(conn, "keyword_and", RAINY_DAY) == []


def test_any_word_matching_finds_the_partial_matches(conn):
    found = set(ids(ranked(conn, "keyword_or", RAINY_DAY)))
    assert {"4", "5", "10"} <= found  # rainy-day fund, park savings, park the car


def test_all_words_works_when_every_word_is_present(conn):
    assert set(ids(ranked(conn, "keyword_and", ROTH))) == {"1", "2"}


def test_vector_ranks_by_known_cosine_similarity(conn):
    rows = ranked(conn, "vector", RAINY_DAY)
    expected = sorted((d for d, (body, _) in POSTS.items() if body),
                      key=lambda d: (-POSTS[d][1], d))
    assert ids(rows) == expected
    assert rows[0]["score"] == pytest.approx(0.95, abs=1e-6)


def test_rrf_score_is_the_sum_of_reciprocal_ranks(conn):
    keyword = {row["doc_id"]: row["rank"] for row in ranked(conn, "keyword_or", RAINY_DAY)}
    vector = {row["doc_id"]: row["rank"] for row in ranked(conn, "vector", RAINY_DAY)}
    fused = ranked(conn, "rrf", RAINY_DAY)
    assert set(ids(fused)) == set(keyword) | set(vector)
    for row in fused:
        doc = row["doc_id"]
        expected = sum(1 / (60 + ranks[doc]) for ranks in (keyword, vector) if doc in ranks)
        assert row["score"] == pytest.approx(expected)
        assert (row["keyword_rank"], row["vector_rank"]) == (keyword.get(doc), vector.get(doc))
    scores = [row["score"] for row in fused]
    assert scores == sorted(scores, reverse=True)


def test_concatenation_puts_every_keyword_hit_first(conn):
    keyword = ids(ranked(conn, "keyword_or", RAINY_DAY))
    stacked = ids(ranked(conn, "concat_dedupe", RAINY_DAY))
    assert stacked[: len(keyword)] == keyword
    assert len(stacked) == len(set(stacked))


def test_bm25_ranks_rarer_terms_higher(conn):
    rows = ranked(conn, "bm25", ROTH)
    assert ids(rows)[:2] in (["1", "2"], ["2", "1"])
    assert all(row["score"] > 0 for row in rows)


def test_scoreboard_sql_matches_python_ndcg(conn):
    for stage in ("vector", "rrf", "keyword_and"):
        evaluate_sql_arm(conn, BY_STAGE[stage], [RAINY_DAY, ROTH], progress=lambda _: None)
    refresh_scoreboard(conn)
    relevance: dict[str, dict[str, int]] = {}
    for query_id, doc_id, grade in QRELS:
        relevance.setdefault(query_id, {})[doc_id] = grade
    rows = conn.execute("SELECT stage, query_id, ndcg10 FROM question_scores").fetchall()
    assert len(rows) == 6
    for stage, query_id, ndcg in rows:
        run = conn.execute(
            "SELECT doc_id FROM runs WHERE stage = %s AND query_id = %s ORDER BY rank",
            (stage, query_id),
        ).fetchall()
        expected = ndcg_at_k([r[0] for r in run], relevance[query_id])
        assert float(ndcg) == pytest.approx(expected), (stage, query_id)
    conn.rollback()


def test_hnsw_returns_at_most_ef_search_rows(conn):
    conn.execute("CREATE TEMP TABLE points AS SELECT i AS id,"
                 " (SELECT array_agg(random())::vector(8) FROM generate_series(1, 8) g"
                 "  WHERE i > 0) AS v FROM generate_series(1, 400) i")
    conn.execute("CREATE INDEX ON points USING hnsw (v vector_l2_ops)")
    conn.execute("SET LOCAL enable_seqscan = off")
    nearest = "SELECT count(*) FROM (SELECT id FROM points ORDER BY v <-> '[0,0,0,0,0,0,0,0]'" \
              " LIMIT 50) n"
    assert conn.execute(nearest).fetchone()[0] == 40
    conn.execute("SET LOCAL hnsw.ef_search = 100")
    assert conn.execute(nearest).fetchone()[0] == 50
    conn.rollback()


def test_iterative_scan_fills_a_filtered_limit(conn):
    conn.execute("CREATE TEMP TABLE items AS SELECT i AS id, i % 20 = 0 AS rare,"
                 " (SELECT array_agg(random())::vector(8) FROM generate_series(1, 8) g"
                 "  WHERE i > 0) AS v FROM generate_series(1, 2000) i")
    conn.execute("CREATE INDEX ON items USING hnsw (v vector_l2_ops)")
    conn.execute("SET LOCAL enable_seqscan = off")
    conn.execute("SET LOCAL enable_bitmapscan = off")
    filtered = "SELECT count(*) FROM (SELECT id FROM items WHERE rare" \
               " ORDER BY v <-> '[0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5]' LIMIT 20) n"
    assert conn.execute(filtered).fetchone()[0] < 20
    conn.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
    assert conn.execute(filtered).fetchone()[0] == 20
    conn.rollback()


def test_hybrid_function_honors_required_terms(conn):
    conn.execute("SET search_path = public")
    from hybrid_lab.db import sql_text

    conn.execute(sql_text("11_hybrid_function.sql").split("-- Try it")[0])
    rows = conn.execute(
        "SELECT h.doc_id FROM queries q, hybrid_search(q.body, q.embedding, 10, 'savings') h"
        " WHERE q.id = %s", (RAINY_DAY,)
    ).fetchall()
    docs = {row[0] for row in rows}
    assert docs and docs <= {"3", "5", "13"}  # only posts that contain "savings"
    conn.rollback()
