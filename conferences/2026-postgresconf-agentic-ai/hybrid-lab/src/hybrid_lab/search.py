"""Run selected arms for one question and shape the results for the UI."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import psycopg

from hybrid_lab import bedrock, questions
from hybrid_lab.arms import BY_STAGE, CANDIDATES, SHOWN, Arm, ArmResult, run_sql_arm
from hybrid_lab.metrics import ndcg_at_k, recall_at_k

PREVIEW_CHARS = 280


@dataclass
class Question:
    """The question being searched and, for FiQA test questions, its judgments."""

    id: str
    body: str
    relevance: dict[str, int] = field(default_factory=dict)

    @property
    def judged(self) -> bool:
        """True for FiQA test questions, which have known right answers."""
        return bool(self.relevance)


def resolve(conn: psycopg.Connection, question_id: str | None, text: str | None) -> Question:
    """Load a stored question, or embed and store typed text. Either becomes active.

    Raises:
        ValueError: If neither an id nor text is given.
        LookupError: If the id does not exist.
    """
    if text and text.strip():
        question_id = questions.ask(conn, text)
    elif question_id:
        questions.use(conn, question_id)
    else:
        raise ValueError("Choose a question or type one.")
    body = conn.execute("SELECT body FROM queries WHERE id = %s", (question_id,)).fetchone()[0]
    relevance = dict(
        conn.execute(
            "SELECT doc_id, relevance FROM qrels WHERE query_id = %s", (question_id,)
        ).fetchall()
    )
    conn.rollback()
    return Question(id=question_id, body=body, relevance=relevance)


def run_arms(conn: psycopg.Connection, question: Question, stages: list[str]) -> list[dict]:
    """Run each requested arm and return one result card per arm, in request order.

    Raises:
        KeyError: If a stage name is unknown.
    """
    arms = [BY_STAGE[stage] for stage in stages]
    live: dict[str, ArmResult] = {}
    cards = []
    for arm in arms:
        if arm.rerank_of:
            result, source = _rerank(conn, arm, question, live)
        else:
            result, source = _sql(conn, arm, question, live), "live SQL"
        cards.append(_card(arm, question, result, source, live))
    _attach_previews(conn, cards)
    return cards


def _sql(conn: psycopg.Connection, arm: Arm, question: Question, live: dict) -> ArmResult:
    if arm.stage not in live:
        live[arm.stage] = run_sql_arm(conn, arm, question.id)
    return live[arm.stage]


def _rerank(
    conn: psycopg.Connection, arm: Arm, question: Question, live: dict
) -> tuple[ArmResult, str]:
    bases = [_sql(conn, BY_STAGE[stage], question, live) for stage in arm.rerank_of]
    if question.judged:
        stored = _stored(conn, arm.stage, question.id)
        if stored is not None:
            return stored, "stored run"
    ids = list(dict.fromkeys(row["doc_id"] for base in bases for row in base.rows[:CANDIDATES]))
    bodies = dict(conn.execute("SELECT id, body FROM docs WHERE id = ANY(%s)", (ids,)).fetchall())
    conn.rollback()
    started = time.perf_counter()
    order = bedrock.rerank(question.body, [bodies[doc_id] or " " for doc_id in ids])
    base_ms = sum(base.elapsed_ms for base in bases)
    elapsed_ms = base_ms + (time.perf_counter() - started) * 1000
    rows = [
        {"rank": position, "doc_id": ids[index], "score": score}
        for position, (index, score) in enumerate(order, start=1)
    ]
    return ArmResult(rows=rows, elapsed_ms=elapsed_ms), "live rerank"


def _stored(conn: psycopg.Connection, stage: str, query_id: str) -> ArmResult | None:
    rows = conn.execute(
        "SELECT rank, doc_id, score FROM runs WHERE stage = %s AND query_id = %s ORDER BY rank",
        (stage, query_id),
    ).fetchall()
    timing = conn.execute(
        "SELECT elapsed_ms FROM run_timings WHERE stage = %s AND query_id = %s", (stage, query_id)
    ).fetchone()
    conn.rollback()
    if not rows:
        return None
    return ArmResult(
        rows=[{"rank": r, "doc_id": d, "score": s} for r, d, s in rows],
        elapsed_ms=timing[0] if timing else 0.0,
    )


def _card(arm: Arm, question: Question, result: ArmResult, source: str, live: dict) -> dict:
    ranked = [row["doc_id"] for row in result.rows]
    base_ranks = {}
    if arm.rerank_of and arm.rerank_of[0] in live:
        base_ranks = {row["doc_id"]: row["rank"] for row in live[arm.rerank_of[0]].rows}
    rows = [
        {
            "rank": row["rank"],
            "doc_id": row["doc_id"],
            "score": None if row.get("score") is None else float(row["score"]),
            "relevant": (question.relevance.get(row["doc_id"], 0) > 0) if question.judged else None,
            "keyword_rank": row.get("keyword_rank"),
            "vector_rank": row.get("vector_rank"),
            "from_rank": base_ranks.get(row["doc_id"]),
        }
        for row in result.rows[:SHOWN]
    ]
    return {
        "stage": arm.stage,
        "label": arm.label,
        "source": source,
        "elapsed_ms": round(result.elapsed_ms, 1),
        "returned": len(result.rows),
        "ndcg10": ndcg_at_k(ranked, question.relevance) if question.judged else None,
        "recall50": recall_at_k(ranked, question.relevance) if question.judged else None,
        "relevant_total": len(question.relevance),
        "base_label": BY_STAGE[arm.rerank_of[0]].label if arm.rerank_of else None,
        "rows": rows,
    }


def _attach_previews(conn: psycopg.Connection, cards: list[dict]) -> None:
    ids = sorted({row["doc_id"] for card in cards for row in card["rows"]})
    previews = dict(
        conn.execute(
            "SELECT id, left(body, %s) FROM docs WHERE id = ANY(%s)", (PREVIEW_CHARS, ids)
        ).fetchall()
    )
    conn.rollback()
    for card in cards:
        for row in card["rows"]:
            row["preview"] = previews.get(row["doc_id"], "")
