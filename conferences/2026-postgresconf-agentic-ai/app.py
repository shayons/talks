"""FastAPI entry point for the AI Coffee Roastery demo.

Endpoints
---------
GET  /                         → serves static/index.html
GET  /api/customers            → list available demo users
POST /api/query                → run a query through the agent pipeline
GET  /api/health               → quick DB ping
"""
from __future__ import annotations

import logging
import asyncio
import json
import os
import queue
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agents import (
    SessionCustomerMismatchError,
    SessionNotFoundError,
    UnknownCustomerError,
    run_query,
)
from db import close_pool, conn
from search import compare_search, search_status
from llm import RunCancelled, chat_configuration, resolve_route
from experiments import (ExperimentConflict, price_status, change_price,
                         fixture_status, prepare_fixture, compare_indexes)


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        yield
    finally:
        close_pool()


app = FastAPI(title="Coffee & queries", version="2.0", lifespan=lifespan)

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
    except Exception as exc:
        logger.exception("database health check failed")
        raise HTTPException(
            status_code=503,
            detail="database unavailable",
        ) from exc


@app.get("/api/customers")
def list_customers() -> list[dict]:
    # Stable IDs preserve the pour-over, espresso and Tokyo demo scenarios.
    # Names come from the database, including customized seeds. Unknown users fall
    # through alphabetically so new seed data still lands somewhere sane.
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, preferences_summary
              FROM customers
             ORDER BY CASE id
                        WHEN 'u_marco' THEN 1
                        WHEN 'u_ana'   THEN 2
                        WHEN 'u_yuki'  THEN 3
                        ELSE 99
                      END,
                      name
            """
        )
        return [
            {"id": r[0], "name": r[1], "summary": r[2]}
            for r in cur.fetchall()
        ]


class QueryIn(BaseModel):
    customer_id: str = Field(min_length=1, max_length=64)
    query: str = Field(min_length=1, max_length=2_000)
    session_id: UUID | None = None
    model_route: Literal["bedrock-openai", "bedrock-claude", "openai"] | None = None


@app.post("/api/query")
def api_query(q: QueryIn) -> dict:
    if not q.query.strip():
        raise HTTPException(status_code=400, detail="query is empty")
    try:
        resolve_route(q.model_route)
        return run_query(
            customer_id=q.customer_id,
            query=q.query.strip(),
            session_id=str(q.session_id) if q.session_id else None,
            model_route=q.model_route,
        )
    except UnknownCustomerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SessionCustomerMismatchError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Check the selected model configuration.") from exc
    except Exception as exc:
        logger.exception("agent query failed")
        raise HTTPException(status_code=500, detail="agent query failed") from exc


@app.get("/api/chat/config")
def api_chat_config() -> dict:
    return chat_configuration()


async def query_events(q: QueryIn):
    """Bounded worker bridge: blocking SQL stays off the server event loop.

Closing the SSE connection signals cancellation. The worker checks at model
chunks and database step boundaries; already committed approvals remain pending.
"""
    events: queue.Queue = queue.Queue(maxsize=128)
    cancelled = threading.Event()
    deadline = time.monotonic() + 180

    def publish(event):
        while not cancelled.is_set():
            try:
                events.put(event, timeout=0.1)
                return
            except queue.Full:
                continue
        raise RunCancelled()

    def worker():
        try:
            result = run_query(customer_id=q.customer_id, query=q.query.strip(),
                               session_id=str(q.session_id) if q.session_id else None,
                               model_route=q.model_route, on_event=publish, cancelled=cancelled)
            publish({"type": "done", "session_id": result["session_id"]})
        except RunCancelled:
            pass
        except Exception as exc:
            if isinstance(exc, (UnknownCustomerError, SessionNotFoundError, SessionCustomerMismatchError)):
                detail = str(exc)
            else:
                logger.exception("streaming agent query failed")
                detail = "The reply could not finish. Check model access and the session trace before resending."
            try:
                publish({"type": "error", "detail": detail})
            except RunCancelled:
                pass

    thread = threading.Thread(target=worker, name="chat-stream", daemon=True)
    thread.start()
    try:
        yield ": connected\n\n"
        while True:
            if time.monotonic() >= deadline:
                yield 'data: {"type":"error","detail":"The reply timed out. Check the session before resending."}\n\n'
                break
            try:
                event = await asyncio.to_thread(events.get, True, 1)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
            if event["type"] in {"done", "error"}:
                break
    finally:
        cancelled.set()


@app.post("/api/query/stream")
async def api_query_stream(q: QueryIn) -> StreamingResponse:
    if not q.query.strip():
        raise HTTPException(status_code=400, detail="query is empty")
    try:
        resolve_route(q.model_route)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StreamingResponse(query_events(q), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    budget: int | None = Field(default=None, ge=0, le=100_000)
    roasts: list[Literal["light", "medium-light", "medium", "medium-dark", "dark"]] = Field(default_factory=list, max_length=5)
    origins: list[str] = Field(default_factory=list, max_length=10)
    stock_only: bool = True
    fuzzy: bool = False
    candidates: int = Field(default=12, ge=1, le=100)
    rrf_k: int = Field(default=60, ge=1, le=200)
    explain: bool = False


@app.get("/api/search/status")
def api_search_status() -> dict:
    try:
        return search_status()
    except Exception as exc:
        logger.exception("search readiness check failed")
        raise HTTPException(status_code=503, detail="Search is unavailable. Check PostgreSQL and apply the hybrid search migration.") from exc


@app.post("/api/search")
def api_search(q: SearchIn) -> dict:
    if not q.query.strip():
        raise HTTPException(status_code=400, detail="Enter a search term.")
    if any(not origin.strip() or len(origin) > 100 for origin in q.origins):
        raise HTTPException(status_code=422, detail="Origins must contain 1–100 characters.")
    try:
        options = q.model_dump()
        options["query"] = q.query.strip()
        return compare_search(**options)
    except Exception as exc:
        logger.exception("search failed")
        raise HTTPException(status_code=503, detail="Search could not complete. Check PostgreSQL, the hybrid search migration, and the local embedding model, then retry.") from exc


def stage_enabled():
    return os.getenv('ENABLE_STAGE_CONTROLS', '0') == '1'


def check_stage_request(request: Request):
    if not stage_enabled():
        raise HTTPException(status_code=403, detail='Stage controls are disabled on this server.')
    if request.headers.get('content-type', '').split(';')[0].strip() != 'application/json':
        raise HTTPException(status_code=415, detail='Stage controls require JSON.')
    origin = request.headers.get('origin')
    if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
        raise HTTPException(status_code=403, detail='Use stage controls from this app’s own page.')


def experiment_call(function, **options):
    try:
        return function(**options)
    except ExperimentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('conference experiment failed')
        raise HTTPException(status_code=503, detail='The experiment could not complete. Check PostgreSQL and retry.') from exc


@app.get('/api/experiments/status')
def api_experiment_status():
    return {'enabled': stage_enabled(), 'price': experiment_call(price_status),
            'fixture': experiment_call(fixture_status)}


class PriceIn(BaseModel):
    action: Literal['raise', 'restore']


@app.post('/api/experiments/price')
def api_experiment_price(body: PriceIn, request: Request):
    check_stage_request(request)
    return experiment_call(change_price, action=body.action)


@app.post('/api/experiments/index/prepare')
def api_experiment_prepare(request: Request):
    check_stage_request(request)
    return experiment_call(prepare_fixture)


class IndexIn(BaseModel):
    filtered: bool = True
    ef_search: int = Field(default=40, ge=20, le=400)
    iterative: bool = False


@app.post('/api/experiments/index/compare')
def api_experiment_compare(body: IndexIn, request: Request):
    check_stage_request(request)
    return experiment_call(compare_indexes, **body.model_dump())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=False,
    )
