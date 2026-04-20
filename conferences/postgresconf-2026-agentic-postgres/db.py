"""Database helpers — one place for DSN + pool + embedding model."""
from __future__ import annotations

import os
from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

import psycopg
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector
from dotenv import load_dotenv

load_dotenv()

DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://coffee:coffee@localhost:5432/coffee",
)

# fastembed uses BAAI/bge-small-en-v1.5 by default — 384-dim, ONNX, ~130MB.
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")


def _configure(conn: psycopg.Connection) -> None:
    register_vector(conn)


_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            DSN,
            min_size=1,
            max_size=8,
            configure=_configure,
            open=True,
        )
    return _pool


@contextmanager
def conn() -> Iterator[psycopg.Connection]:
    with get_pool().connection() as c:
        yield c


@lru_cache(maxsize=1)
def embedder():
    """Lazy-load the embedding model. First call downloads ~130MB once."""
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=EMBED_MODEL)


def embed(text: str) -> list[float]:
    """Return a 384-dim embedding for a string."""
    return list(next(embedder().embed([text])))


def embed_batch(texts: list[str]) -> list[list[float]]:
    return [list(v) for v in embedder().embed(texts)]
