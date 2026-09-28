"""FastAPI app for the hybrid search lab UI. Run: uv run hybrid-lab (127.0.0.1:8018)."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from psycopg_pool import ConnectionPool, PoolTimeout
from pydantic import BaseModel, Field

from hybrid_lab import search
from hybrid_lab.arms import ARMS, BY_STAGE, MARKER, source_file
from hybrid_lab.bedrock import BedrockError
from hybrid_lab.db import dataset, open_pool, sql_text
from hybrid_lab.evaluate import bm25_available, local_available

STATIC = Path(__file__).parent / "static"
LOG = logging.getLogger("hybrid_lab")
DATASET_LABELS = {
    "fiqa": "FiQA · finance questions",
    "scifact": "SciFact · science claims",
    "nfcorpus": "NFCorpus · nutrition and medicine",
    "scidocs": "SCIDOCS · paper citations",
}


def configured_datasets() -> list[str]:
    """Datasets to serve: LAB_DATASETS, or just LAB_DATASET when DATABASE_URL is set."""
    if os.getenv("DATABASE_URL"):
        return [dataset()]
    return [n.strip() for n in os.getenv("LAB_DATASETS", ",".join(DATASET_LABELS)).split(",")]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open one connection pool per dataset database that exists; skip the rest."""
    app.state.pools = {}
    for name in configured_datasets():
        pool = open_pool(None if os.getenv("DATABASE_URL") else name)
        try:
            pool.wait(timeout=5.0)
            app.state.pools[name] = pool
        except PoolTimeout:
            LOG.warning("Skipping %s: its database is not reachable.", name)
            pool.close()
    if not app.state.pools:
        raise RuntimeError("No lab database is reachable. Run ./scripts/setup.sh first.")
    yield
    for pool in app.state.pools.values():
        pool.close()


def pool_for(request: Request, name: str | None) -> ConnectionPool:
    """The pool for a dataset, defaulting to the first one served.

    Raises:
        HTTPException: 404 for a dataset this server does not serve.
    """
    pools = request.app.state.pools
    chosen = name or next(iter(pools))
    if chosen not in pools:
        raise HTTPException(404, f"Dataset {chosen} is not loaded on this server.")
    return pools[chosen]


app = FastAPI(title="Hybrid search lab", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class SearchRequest(BaseModel):
    """A question (FiQA id or typed text) and the arms to run for it."""

    dataset: str | None = None
    question_id: str | None = None
    text: str | None = Field(default=None, max_length=500)
    arms: list[str] = Field(min_length=1, max_length=len(ARMS))


@app.exception_handler(BedrockError)
def bedrock_failed(_: Request, exc: BedrockError) -> JSONResponse:
    """Bedrock problems are the only live network dependency; say so plainly."""
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/")
def index() -> FileResponse:
    """Serve the single-page UI."""
    return FileResponse(STATIC / "index.html")


# Columns shown first for each dataset: FiQA teaches the pitfalls with the frontier model;
# the others show what BM25 adds to the small local model.
DEFAULT_ARMS = {
    "fiqa": ("bm25", "vector", "rrf_bm25", "vector_rerank"),
    "*": ("bm25", "vector_local", "blend_local", "vector"),
}

SUMMARY_STAGES = (
    "bm25", "vector", "rrf_bm25", "blend_bm25", "vector_rerank",
    "vector_local", "rrf_local", "blend_local",
)


def _unavailable_reason(arm, has_bm25: bool, has_local: bool) -> str | None:
    if arm.needs_bm25 and not has_bm25:
        return "pg_textsearch is not loaded or docs_body_bm25 is missing"
    if arm.local and not has_local:
        return "Run py/2b_embed_local.py to fill the small model's vectors"
    return None


@app.get("/api/datasets")
def datasets(request: Request) -> list[dict]:
    """The datasets this server has loaded, with their sizes."""
    result = []
    for name, pool in request.app.state.pools.items():
        with pool.connection() as conn:
            docs, questions = conn.execute(
                "SELECT (SELECT count(*) FROM docs),"
                " (SELECT count(*) FROM queries WHERE split = 'test')"
            ).fetchone()
        result.append({"name": name, "label": DATASET_LABELS.get(name, name),
                       "docs": docs, "questions": questions})
    return result


@app.get("/api/summary")
def summary(request: Request) -> dict:
    """NDCG@10 of the main arms on every loaded dataset that has been evaluated."""
    columns, cells = [], {}
    for name, pool in request.app.state.pools.items():
        with pool.connection() as conn:
            if conn.execute("SELECT to_regclass('scoreboard') IS NULL").fetchone()[0]:
                continue
            rows = conn.execute(
                "SELECT stage, ndcg_at_10 FROM scoreboard WHERE stage = ANY(%s)",
                (list(SUMMARY_STAGES),),
            ).fetchall()
            weight = conn.execute(
                "SELECT value FROM fusion_settings WHERE name = 'blend_vector_weight'"
            ).fetchone()
        columns.append({"name": name, "label": DATASET_LABELS.get(name, name),
                        "blend_weight": weight[0] if weight else None})
        for stage, ndcg in rows:
            cells.setdefault(stage, {})[name] = float(ndcg)
    return {
        "datasets": columns,
        "arms": [{"stage": s, "label": BY_STAGE[s].label, "cells": cells.get(s, {})}
                 for s in SUMMARY_STAGES if s in cells],
    }


@app.get("/api/arms")
def arms(request: Request, dataset: str | None = None) -> list[dict]:
    """List every arm, whether it is on by default for this dataset, and whether it can run."""
    with pool_for(request, dataset).connection() as conn:
        has_bm25 = bm25_available(conn)
        has_local = local_available(conn)
    name = dataset or next(iter(request.app.state.pools))
    defaults = DEFAULT_ARMS.get(name, DEFAULT_ARMS["*"])
    return [
        {
            "stage": arm.stage,
            "label": arm.label,
            "sql_file": source_file(arm),
            "rerank_of": list(arm.rerank_of),
            "default_on": arm.stage in defaults,
            "pitfall": arm.pitfall,
            "available": (has_bm25 or not arm.needs_bm25) and (has_local or not arm.local),
            "unavailable_reason": _unavailable_reason(arm, has_bm25, has_local),
        }
        for arm in ARMS
    ]


@app.get("/api/questions")
def question_list(request: Request, q: str = "", dataset: str | None = None) -> dict:
    """Curated stage questions plus a text search over the test questions."""
    with pool_for(request, dataset).connection() as conn:
        demo = conn.execute(
            "SELECT d.query_id, d.label, d.reason, q.body FROM demo_questions d"
            " JOIN queries q ON q.id = d.query_id ORDER BY d.position"
        ).fetchall()
        matches = conn.execute(
            "SELECT id, body FROM queries WHERE split = 'test' AND body ILIKE %s"
            " ORDER BY length(body), id LIMIT 25",
            (f"%{q.strip()}%",),
        ).fetchall()
    return {
        "demo": [{"id": i, "label": lb, "reason": r, "body": b} for i, lb, r, b in demo],
        "matches": [{"id": i, "body": b} for i, b in matches],
    }


@app.post("/api/search")
def run_search(request: Request, body: SearchRequest) -> dict:
    """Run the requested arms for one question. Typed questions are embedded on Bedrock."""
    unknown = [stage for stage in body.arms if stage not in BY_STAGE]
    if unknown:
        raise HTTPException(400, f"Unknown arms: {', '.join(unknown)}")
    with pool_for(request, body.dataset).connection() as conn:
        try:
            question = search.resolve(conn, body.question_id, body.text)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        cards = search.run_arms(conn, question, body.arms)
    return {
        "question": {"id": question.id, "body": question.body, "judged": question.judged,
                     "answers": sorted(question.relevance, key=lambda d: (len(d), d))},
        "arms": cards,
    }


@app.get("/api/sql/{stage}")
def sql_source(stage: str) -> dict:
    """Return an arm's SQL file exactly as it is on disk."""
    arm = BY_STAGE.get(stage)
    if arm is None:
        raise HTTPException(404, f"Unknown arm {stage}")
    file_name = source_file(arm)
    text = sql_text(file_name)
    note = None
    if arm.rerank_of:
        files = ", ".join(f"sql/{source_file(BY_STAGE[s])}" for s in arm.rerank_of)
        note = (f"Candidates are the top 50 from {files} (combined, duplicates removed). "
                "Their text is then sent to Cohere Rerank on Bedrock, which reorders them. "
                "The reranker runs outside PostgreSQL.")
    return {"file": f"sql/{file_name}", "text": text, "marker": MARKER, "note": note}


@app.get("/api/scoreboard")
def scoreboard(request: Request, dataset: str | None = None) -> dict:
    """The graded scoreboard, plus the questions where hybrid gained or lost most."""
    with pool_for(request, dataset).connection() as conn:
        if conn.execute("SELECT to_regclass('scoreboard') IS NULL").fetchone()[0]:
            raise HTTPException(409, "No scoreboard yet. Run py/4_evaluate.py first.")
        cur = conn.execute("SELECT * FROM scoreboard ORDER BY ndcg_at_10 DESC, stage")
        names = [column.name for column in cur.description]
        rows = [dict(zip(names, row, strict=True)) for row in cur.fetchall()]
        swings = conn.execute(SWINGS_SQL).fetchall()
    labels = {arm.stage: arm.label for arm in ARMS}
    for row in rows:
        row["label"] = labels.get(row["stage"], row["stage"])
    return {
        "rows": rows,
        "swings": [{"direction": d, "id": i, "body": b, "hybrid": float(h), "vector": float(v)}
                   for d, i, b, h, v in swings],
    }


SWINGS_SQL = """
WITH p AS (
  SELECT query_id,
         max(ndcg10) FILTER (WHERE stage = 'blend_local') AS hybrid,
         max(ndcg10) FILTER (WHERE stage = 'vector_local') AS vector
    FROM question_scores GROUP BY query_id
), ranked AS (
  SELECT CASE WHEN hybrid > vector THEN 'gain' ELSE 'loss' END AS direction, query_id,
         hybrid, vector,
         row_number() OVER (PARTITION BY hybrid > vector ORDER BY abs(hybrid - vector) DESC,
                            query_id) AS n
    FROM p WHERE hybrid <> vector
)
SELECT r.direction, r.query_id, q.body, round(r.hybrid, 3), round(r.vector, 3)
  FROM ranked r JOIN queries q ON q.id = r.query_id
 WHERE r.n <= 5
 ORDER BY r.direction, r.n
"""


@app.get("/api/doc/{doc_id}")
def document(request: Request, doc_id: str, dataset: str | None = None) -> dict:
    """Full text of one document."""
    with pool_for(request, dataset).connection() as conn:
        row = conn.execute("SELECT id, body FROM docs WHERE id = %s", (doc_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"No document {doc_id}")
    return {"id": row[0], "body": row[1]}


@app.get("/api/status")
def status(request: Request, dataset: str | None = None) -> dict:
    """Versions and counts, for the header and for a pre-talk check."""
    with pool_for(request, dataset).connection() as conn:
        version = conn.execute("SELECT current_setting('server_version')").fetchone()[0]
        extensions = dict(conn.execute(
            "SELECT extname, extversion FROM pg_extension"
            " WHERE extname IN ('vector', 'pg_textsearch')"
        ).fetchall())
        docs, embedded, empty = conn.execute(
            "SELECT count(*), count(embedding), count(*) FILTER (WHERE body ~ '^\\s*$')"
            " FROM docs"
        ).fetchone()
    return {"postgres": version, "extensions": extensions, "docs": docs, "embedded": embedded,
            "empty": empty}


def main() -> None:
    """Start the server on loopback only."""
    uvicorn.run(
        "hybrid_lab.server:app",
        host=os.getenv("LAB_HOST", "127.0.0.1"),
        port=int(os.getenv("LAB_PORT", "8018")),
    )
