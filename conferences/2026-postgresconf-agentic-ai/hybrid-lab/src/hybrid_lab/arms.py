"""The search arms: which SQL file produces each stage, and how to run one.

Every arm file has a `-- == ARM QUERY ==` line. Everything above it is for exploring on
stage; everything below it is executed here byte-for-byte, so the measured SQL is the SQL
the audience sees.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import psycopg

from hybrid_lab.db import sql_text

MARKER = "-- == ARM QUERY =="
CANDIDATES = 50
SHOWN = 10


@dataclass(frozen=True)
class Arm:
    """One retrieval method the lab can run and score."""

    stage: str
    label: str
    sql_file: str | None = None
    rerank_of: tuple[str, ...] = ()
    needs_bm25: bool = False
    local: bool = False
    default_on: bool = False
    pitfall: bool = False


ARMS: tuple[Arm, ...] = (
    Arm("keyword_and", "Keyword · all words", "03_keyword_and.sql", pitfall=True),
    Arm("keyword_or", "Keyword · ts_rank_cd", "04_keyword_or.sql", pitfall=True),
    Arm("bm25", "BM25", "05_bm25.sql", needs_bm25=True),
    Arm("vector_local", "Vector · bge-small (local)", "06b_vector_local.sql", local=True),
    Arm("rrf_local", "RRF · BM25 + bge-small", "08d_hybrid_rrf_local.sql", needs_bm25=True,
        local=True),
    Arm("blend_local", "Tuned blend · bge-small", "08e_hybrid_blend_local.sql",
        needs_bm25=True, local=True),
    Arm("vector", "Vector · Embed v4", "06_vector.sql"),
    Arm("naive_sum", "Score sum", "07a_naive_sum.sql", pitfall=True),
    Arm("concat_dedupe", "Concatenate", "07b_concat_dedupe.sql", pitfall=True),
    Arm("rrf", "RRF · ts_rank_cd + Embed v4", "08a_hybrid_rrf.sql"),
    Arm("rrf_bm25", "RRF · BM25 + Embed v4", "08b_hybrid_rrf_bm25.sql", needs_bm25=True),
    Arm("blend_bm25", "Tuned blend · Embed v4", "08c_hybrid_blend.sql", needs_bm25=True),
    Arm("vector_rerank", "Embed v4 + Rerank", rerank_of=("vector",)),
    Arm("rrf_rerank", "RRF · ts_rank_cd + Rerank", rerank_of=("rrf",)),
    Arm("rrf_bm25_rerank", "RRF · BM25 + Rerank", rerank_of=("rrf_bm25",), needs_bm25=True),
    Arm("union_rerank", "Embed v4 ∪ BM25 + Rerank", rerank_of=("vector", "bm25"),
        needs_bm25=True),
    Arm("vector_halfvec", "Embed v4 · halfvec", "12a_halfvec.sql"),
    Arm("vector_binary", "Embed v4 · binary + rescore", "12b_binary.sql"),
)
BY_STAGE = {arm.stage: arm for arm in ARMS}


def source_file(arm: Arm) -> str:
    """The SQL file an arm runs, or for a rerank arm, the file of its first candidate list."""
    return arm.sql_file or BY_STAGE[arm.rerank_of[0]].sql_file or ""


@dataclass(frozen=True)
class ArmResult:
    """Rows returned by one arm for one question, and how long the SQL took."""

    rows: list[dict]
    elapsed_ms: float


def arm_sql(arm: Arm) -> str:
    """Return the executable section of an arm's SQL file.

    Raises:
        ValueError: If the arm has no SQL file or the file lacks the marker line.
    """
    if arm.sql_file is None:
        raise ValueError(f"{arm.stage} reranks {', '.join(arm.rerank_of)}; it has no SQL file")
    _, marker, section = sql_text(arm.sql_file).partition(MARKER)
    if not marker:
        raise ValueError(f"sql/{arm.sql_file} is missing the line '{MARKER}'")
    return section.strip()


def run_sql_arm(conn: psycopg.Connection, arm: Arm, query_id: str) -> ArmResult:
    """Run one arm for one question in a transaction that is always rolled back.

    The rollback discards the arm's SET statements, so arms cannot leak settings
    into each other through a shared connection.
    """
    sql = arm_sql(arm)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('lab.query_id', %s, true)", (query_id,))
            started = time.perf_counter()
            cur.execute(sql)
            rows = _last_result(cur)
            elapsed_ms = (time.perf_counter() - started) * 1000
    finally:
        conn.rollback()
    return ArmResult(rows=rows, elapsed_ms=elapsed_ms)


def _last_result(cur: psycopg.Cursor) -> list[dict]:
    rows: list[dict] = []
    while True:
        if cur.description is not None:
            names = [column.name for column in cur.description]
            rows = [dict(zip(names, row, strict=True)) for row in cur.fetchall()]
        if not cur.nextset():
            return rows
