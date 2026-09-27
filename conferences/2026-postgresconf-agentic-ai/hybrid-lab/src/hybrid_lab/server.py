"""FastAPI app for the hybrid search lab UI. Run: uv run hybrid-lab (127.0.0.1:8018)."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from hybrid_lab import search
from hybrid_lab.arms import ARMS, BY_STAGE, MARKER, source_file
from hybrid_lab.bedrock import BedrockError
from hybrid_lab.db import open_pool, sql_text
from hybrid_lab.evaluate import bm25_available

STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open one connection pool for the life of the server."""
    app.state.pool = open_pool()
    yield
    app.state.pool.close()


app = FastAPI(title="Hybrid search lab", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class SearchRequest(BaseModel):
    """A question (FiQA id or typed text) and the arms to run for it."""

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


@app.get("/api/arms")
def arms(request: Request) -> list[dict]:
    """List every arm, whether it is on by default, and whether it can run here."""
    with request.app.state.pool.connection() as conn:
        has_bm25 = bm25_available(conn)
    return [
        {
            "stage": arm.stage,
            "label": arm.label,
            "sql_file": source_file(arm),
            "rerank_of": list(arm.rerank_of),
            "default_on": arm.default_on,
            "pitfall": arm.pitfall,
            "available": has_bm25 or not arm.needs_bm25,
            "unavailable_reason": None if has_bm25 or not arm.needs_bm25
            else "pg_textsearch is not loaded or docs_body_bm25 is missing",
        }
        for arm in ARMS
    ]


@app.get("/api/questions")
def question_list(request: Request, q: str = "") -> dict:
    """Curated stage questions plus a text search over the 648 test questions."""
    with request.app.state.pool.connection() as conn:
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
    with request.app.state.pool.connection() as conn:
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
def scoreboard(request: Request) -> dict:
    """The graded scoreboard, plus the questions where hybrid gained or lost most."""
    with request.app.state.pool.connection() as conn:
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
         max(ndcg10) FILTER (WHERE stage = 'rrf_bm25') AS hybrid,
         max(ndcg10) FILTER (WHERE stage = 'vector') AS vector
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
def document(request: Request, doc_id: str) -> dict:
    """Full text of one FiQA post."""
    with request.app.state.pool.connection() as conn:
        row = conn.execute("SELECT id, body FROM docs WHERE id = %s", (doc_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"No document {doc_id}")
    return {"id": row[0], "body": row[1]}


@app.get("/api/status")
def status(request: Request) -> dict:
    """Versions and counts, for the header and for a pre-talk check."""
    with request.app.state.pool.connection() as conn:
        version = conn.execute("SELECT current_setting('server_version')").fetchone()[0]
        extensions = dict(conn.execute(
            "SELECT extname, extversion FROM pg_extension"
            " WHERE extname IN ('vector', 'pg_textsearch')"
        ).fetchall())
        docs, embedded = conn.execute(
            "SELECT count(*), count(embedding) FROM docs"
        ).fetchone()
    return {"postgres": version, "extensions": extensions, "docs": docs, "embedded": embedded}


def main() -> None:
    """Start the server on loopback only."""
    uvicorn.run(
        "hybrid_lab.server:app",
        host=os.getenv("LAB_HOST", "127.0.0.1"),
        port=int(os.getenv("LAB_PORT", "8018")),
    )
