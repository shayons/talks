"""Database helpers — one place for DSN, pool, and embedding model.

DEMO_MODE=local  -> uses DATABASE_URL as-is (default).
DEMO_MODE=aurora -> builds a TLS DSN from the Aurora endpoint and managed
                    Secrets Manager secret when the first DB connection opens.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator
from urllib.parse import quote

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

load_dotenv()


def demo_mode() -> str:
    mode = os.getenv("DEMO_MODE", "local").strip().lower()
    if mode not in {"local", "aurora"}:
        raise ValueError("DEMO_MODE must be either 'local' or 'aurora'")
    return mode


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required when DEMO_MODE=aurora")
    return value


def _aurora_dsn() -> str:
    import boto3

    secret_arn = _required_env("AURORA_SECRET_ARN")
    endpoint = _required_env("AURORA_CLUSTER_ENDPOINT")
    region = os.getenv("AWS_REGION", "us-east-1")
    dbname = os.getenv("AURORA_DATABASE", "coffee")
    port = os.getenv("AURORA_PORT", "5432")

    sm = boto3.client("secretsmanager", region_name=region)
    secret = sm.get_secret_value(SecretId=secret_arn)
    if "SecretString" not in secret:
        raise RuntimeError("Aurora secret must contain a JSON SecretString")
    creds = json.loads(secret["SecretString"])
    try:
        user = quote(str(creds["username"]), safe="")
        password = quote(str(creds["password"]), safe="")
    except KeyError as exc:
        raise RuntimeError(
            "Aurora secret must contain username and password"
        ) from exc
    return (
        f"postgresql://{user}:{password}@{endpoint}:{port}/{dbname}"
        "?sslmode=require"
    )


@lru_cache(maxsize=1)
def database_url() -> str:
    if demo_mode() == "aurora":
        return _aurora_dsn()
    return os.getenv(
        "DATABASE_URL",
        "postgresql://coffee:coffee@127.0.0.1:5433/coffee",
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
            database_url(),
            min_size=1,
            max_size=8,
            configure=_configure,
            open=True,
        )
    return _pool


def close_pool() -> None:
    """Close and clear the process-wide pool, if it was opened."""
    global _pool
    pool, _pool = _pool, None
    if pool is not None:
        pool.close()


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
