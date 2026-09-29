"""PostgreSQL access: one place for the DSN, connections, and the lab's SQL files."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

LAB_ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = LAB_ROOT / "sql"
CLUSTER_DSN = "postgresql://postgres:postgres@127.0.0.1:5433"

load_dotenv(LAB_ROOT / ".env")


def dataset() -> str:
    """The BEIR dataset this process works on (LAB_DATASET, default fiqa)."""
    return os.getenv("LAB_DATASET", "fiqa")


def database_url(name: str | None = None) -> str:
    """Return DATABASE_URL if set, otherwise the lab cluster's database for the dataset."""
    if name is None and os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    return f"{CLUSTER_DSN}/{name or dataset()}"


def connect(name: str | None = None, **kwargs) -> psycopg.Connection:
    """Open a connection with pgvector types registered.

    Args:
        name: A dataset's database; defaults to DATABASE_URL or LAB_DATASET.
        **kwargs: Passed to psycopg.connect, for example autocommit=True.

    Raises:
        RuntimeError: If PostgreSQL is unreachable, with the command that starts it.
    """
    url = database_url(name)
    try:
        conn = psycopg.connect(url, **kwargs)
    except psycopg.OperationalError as exc:
        raise RuntimeError(
            f"Cannot connect to {_redacted(url)}: {exc}".strip()
            + "\nCreate and start it with: LAB_DB=<dataset> ./scripts/setup.sh"
        ) from exc
    register_vector(conn)
    return conn


def open_pool(name: str | None = None, max_size: int = 8) -> ConnectionPool:
    """Open a connection pool for the web server."""
    return ConnectionPool(
        database_url(name), min_size=1, max_size=max_size, configure=register_vector, open=True
    )


def sql_text(name: str) -> str:
    """Return the text of a file in sql/.

    Raises:
        FileNotFoundError: If the file does not exist, naming the directory searched.
    """
    path = SQL_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"{name} not found in {SQL_DIR}")
    return path.read_text()


def run_script(conn: psycopg.Connection, name: str) -> list[tuple[str, float]]:
    """Run a sql/ file statement by statement (autocommit) and time each one.

    Statements must end with a semicolon at the end of a line. Use this for setup files
    such as 02_indexes.sql, not for files with function bodies.

    Returns:
        (first line of the statement, elapsed milliseconds) for each statement.
    """
    timings = []
    for statement in _statements(sql_text(name)):
        started = time.perf_counter()
        conn.execute(statement)
        first_line = next(
            line for line in statement.splitlines() if line and not line.startswith("--")
        )
        timings.append((first_line.strip(), (time.perf_counter() - started) * 1000))
    return timings


def _statements(text: str) -> list[str]:
    parts = re.split(r";[ \t]*\n", text)
    code = [part.strip() for part in parts]
    return [part for part in code if any(
        line.strip() and not line.strip().startswith("--") for line in part.splitlines()
    )]


def _redacted(dsn: str) -> str:
    if "@" not in dsn or "://" not in dsn:
        return dsn
    scheme, rest = dsn.split("://", 1)
    credentials, host = rest.split("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"
