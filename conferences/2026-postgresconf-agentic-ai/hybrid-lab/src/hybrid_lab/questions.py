"""Choose the question every arm file reads (the active_query view)."""

from __future__ import annotations

import hashlib

import psycopg
from pgvector import Vector

from hybrid_lab import bedrock


def ask(conn: psycopg.Connection, text: str) -> str:
    """Embed a typed question, store it as a demo question, and make it active.

    Returns:
        The question id. Re-asking the same text reuses the stored embedding.

    Raises:
        ValueError: If the text is blank.
        bedrock.BedrockError: If the question needs embedding and Bedrock fails.
    """
    text = " ".join(text.split())
    if not text:
        raise ValueError("Type a question first.")
    query_id = "demo-" + hashlib.sha1(text.encode()).hexdigest()[:12]
    exists = conn.execute(
        "SELECT 1 FROM queries WHERE id = %s AND embedding IS NOT NULL", (query_id,)
    ).fetchone()
    if not exists:
        vector = Vector(bedrock.embed_query(text))
        conn.execute(
            "INSERT INTO queries (id, body, split, embedding) VALUES (%s, %s, 'demo', %s)"
            " ON CONFLICT (id) DO UPDATE SET embedding = EXCLUDED.embedding",
            (query_id, text, vector),
        )
    use(conn, query_id)
    return query_id


def use(conn: psycopg.Connection, query_id: str) -> None:
    """Make an existing question the active one for SQLTools and psql sessions.

    Raises:
        LookupError: If no question has this id.
    """
    row = conn.execute("SELECT body FROM queries WHERE id = %s", (query_id,)).fetchone()
    if row is None:
        conn.rollback()
        raise LookupError(f"No question with id {query_id!r}.")
    conn.execute("UPDATE lab_state SET query_id = %s", (query_id,))
    conn.commit()


def active(conn: psycopg.Connection) -> tuple[str, str] | None:
    """Return (id, text) of the active question, or None."""
    row = conn.execute(
        "SELECT q.id, q.body FROM lab_state s JOIN queries q ON q.id = s.query_id"
    ).fetchone()
    conn.rollback()
    return (row[0], row[1]) if row else None
