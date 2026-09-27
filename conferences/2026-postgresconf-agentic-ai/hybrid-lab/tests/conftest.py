"""A 20-post fixture database with known answers and hand-built embeddings.

Question "101" embeds as the unit vector e0. Post n's embedding is
[s_n, sqrt(1 - s_n^2), ...] with the second component on its own axis, so its cosine
similarity to 101 is exactly s_n. That fixes the vector ranking without a model.
"""

from __future__ import annotations

import math
import os

import psycopg
import pytest
from pgvector import Vector
from pgvector.psycopg import register_vector

from hybrid_lab.db import run_script, sql_text

ADMIN_DSN = os.getenv("TEST_ADMIN_URL", "postgresql://coffee:coffee@127.0.0.1:5433/postgres")
TEST_DB = "fiqa_test"
DIMS = 1536

POSTS = {
    "1": ("Roth IRA contribution limit for 2024 is 7000 dollars.", 0.40),
    "2": ("The contribution limit for a Roth IRA depends on income.", 0.30),
    "3": ("Keep an emergency fund in a high-yield savings account.", 0.95),
    "4": ("A rainy-day fund belongs in cash, not stocks.", 0.90),
    "5": ("Money market funds are a safe place to park savings.", 0.85),
    "6": ("Index funds have low expense ratios.", 0.20),
    "7": ("Report freelance income on form 1099-NEC.", 0.10),
    "8": ("Form 1099-MISC reports rents and prizes.", 0.12),
    "9": ("Credit card interest compounds daily.", 0.05),
    "10": ("Park the car in the garage overnight.", 0.50),
    "11": ("Traditional IRA contributions may be deductible.", 0.25),
    "12": ("Your emergency fund should cover six months of expenses.", 0.92),
    "13": ("Certificates of deposit lock savings for a fixed term.", 0.70),
    "14": ("Treasury bills are short-term government debt.", 0.60),
    "15": ("A 401(k) match is free money from your employer.", 0.15),
    "16": ("Dividends from stocks are taxed differently.", 0.08),
    "17": ("Mortgage rates rose again this year.", 0.03),
    "18": ("Budget apps help track spending.", 0.35),
    "19": ("Rainy weather does not affect the stock market.", 0.45),
    "20": ("", 0.0),
}
QUESTIONS = {
    "101": "Where should I park my rainy-day fund?",
    "102": "roth ira contribution limit",
}
QRELS = [("101", "3", 1), ("101", "4", 1), ("101", "12", 1), ("102", "1", 1), ("102", "2", 1)]


def unit_axis(axis: int) -> list[float]:
    vector = [0.0] * DIMS
    vector[axis] = 1.0
    return vector


def post_vector(position: int, similarity: float) -> list[float]:
    vector = [0.0] * DIMS
    vector[0] = similarity
    vector[position + 1] = math.sqrt(1 - similarity**2)
    return vector


@pytest.fixture(scope="session")
def test_dsn() -> str:
    with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {TEST_DB} TEMPLATE template0 ENCODING 'UTF8'")
    dsn = ADMIN_DSN.rsplit("/", 1)[0] + f"/{TEST_DB}"
    os.environ["DATABASE_URL"] = dsn
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION vector; CREATE EXTENSION pg_textsearch")
        register_vector(conn)
        conn.execute(sql_text("01_schema.sql"))
        _insert_fixture(conn)
        run_script(conn, "02_indexes.sql")
    return dsn


def _insert_fixture(conn: psycopg.Connection) -> None:
    for position, (doc_id, (body, similarity)) in enumerate(POSTS.items(), start=1):
        vector = Vector(post_vector(position, similarity)) if body else None
        conn.execute(
            "INSERT INTO docs (id, body, embedding) VALUES (%s, %s, %s)", (doc_id, body, vector)
        )
    q2_vector = post_vector(len(POSTS) + 5, 0.0)
    for query_id, body in QUESTIONS.items():
        vector = unit_axis(0) if query_id == "101" else q2_vector
        conn.execute(
            "INSERT INTO queries (id, body, split, embedding) VALUES (%s, %s, 'test', %s)",
            (query_id, body, Vector(vector)),
        )
    conn.cursor().executemany("INSERT INTO qrels VALUES (%s, %s, %s)", QRELS)
    conn.execute("ANALYZE")


@pytest.fixture()
def conn(test_dsn: str):
    connection = psycopg.connect(test_dsn)
    register_vector(connection)
    yield connection
    connection.close()
