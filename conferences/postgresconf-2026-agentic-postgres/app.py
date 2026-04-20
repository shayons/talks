"""FastAPI entry point for the AI Coffee Roastery demo.

Endpoints
---------
GET  /                         → serves static/index.html
GET  /api/customers            → list available demo users
POST /api/query                → run a query through the agent pipeline
GET  /api/health               → quick DB ping
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db import conn
from agents import run_query


app = FastAPI(title="AI Coffee Roastery", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    try:
        with conn() as c, c.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"db error: {e}")


@app.get("/api/customers")
def list_customers() -> list[dict]:
    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT id, name, preferences_summary FROM customers ORDER BY name")
        return [
            {"id": r[0], "name": r[1], "summary": r[2]}
            for r in cur.fetchall()
        ]


class QueryIn(BaseModel):
    customer_id: str
    query: str
    session_id: str | None = None


@app.post("/api/query")
def api_query(q: QueryIn) -> dict:
    if not q.query.strip():
        raise HTTPException(status_code=400, detail="query is empty")
    try:
        return run_query(
            customer_id=q.customer_id,
            query=q.query.strip(),
            session_id=q.session_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
