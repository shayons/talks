# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]>=3.2", "pgvector>=0.4", "boto3>=1.35"]
# ///
r"""Fill a table's embedding column in resumable batches.

Only rows whose embedding IS NULL and whose text is not blank are sent, so re-running after
an interruption continues where it stopped. Throttling is waited out, not fatal.

    uv run templates/backfill_embeddings.py --table public.articles --id-column id \\
        --text-sql "coalesce(title, '') || ' ' || coalesce(body, '')" --dims 1536

--text-sql is a SQL expression over the table's columns. It is trusted input from the
operator running this script (it is interpolated into the query), never user input.
"""

from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor

import psycopg
from embedding_providers import Provider, make_provider
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg import sql

PAGE = 5_000


def parse_args() -> argparse.Namespace:
    """Read command-line options; DATABASE_URL is the default DSN."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL"), required=False)
    parser.add_argument("--table", required=True, help="schema.table")
    parser.add_argument("--id-column", required=True)
    parser.add_argument("--text-sql", required=True, help="SQL expression producing the text")
    parser.add_argument("--embedding-column", default="embedding")
    parser.add_argument("--provider", default="bedrock", choices=["bedrock", "openai", "fastembed"])
    parser.add_argument("--model")
    parser.add_argument("--dims", type=int, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not args.dsn:
        parser.error("Set DATABASE_URL or pass --dsn.")
    return args


def pending_page(conn: psycopg.Connection, args: argparse.Namespace, after) -> list[tuple]:
    """The next page of rows that still need an embedding, in id order."""
    schema, table = args.table.split(".", 1)
    query = sql.SQL(
        "SELECT {id}, {text} FROM {schema}.{table}"
        " WHERE {emb} IS NULL AND btrim({text}) <> '' AND ({after}::text IS NULL OR {id} > {after})"
        " ORDER BY {id} LIMIT {page}"
    ).format(
        id=sql.Identifier(args.id_column), text=sql.SQL(args.text_sql),
        schema=sql.Identifier(schema), table=sql.Identifier(table),
        emb=sql.Identifier(args.embedding_column), after=sql.Literal(after),
        page=sql.Literal(PAGE),
    )
    return conn.execute(query).fetchall()


def store(args: argparse.Namespace, provider: Provider, rows: list[tuple]) -> int:
    """Embed one batch as documents and write it back in one transaction."""
    vectors = provider.embed([text for _, text in rows], "document")
    schema, table = args.table.split(".", 1)
    update = sql.SQL("UPDATE {schema}.{table} SET {emb} = %s WHERE {id} = %s").format(
        schema=sql.Identifier(schema), table=sql.Identifier(table),
        emb=sql.Identifier(args.embedding_column), id=sql.Identifier(args.id_column),
    )
    with psycopg.connect(args.dsn) as conn:
        register_vector(conn)
        conn.cursor().executemany(
            update, [(Vector(v), row_id) for (row_id, _), v in zip(rows, vectors, strict=True)]
        )
    return len(rows)


def main() -> None:
    """Embed every pending row, page by page, with a pool of workers."""
    args = parse_args()
    provider = make_provider(args.provider, args.dims, args.model)
    print(f"Embedding with {provider.name} {provider.model} ({provider.dims} dims)")
    done, started, after = 0, time.perf_counter(), None
    with psycopg.connect(args.dsn) as conn, ThreadPoolExecutor(args.workers) as pool:
        while rows := pending_page(conn, args, after):
            after = rows[-1][0]
            size = provider.batch_size
            batches = [rows[i:i + size] for i in range(0, len(rows), size)]
            done += sum(pool.map(lambda batch: store(args, provider, batch), batches))
            rate = done / (time.perf_counter() - started)
            print(f"  {done:,} rows embedded ({rate:,.0f} rows/s)")
    print("Done. Now build the HNSW index (migration.sql, Part B).")


if __name__ == "__main__":
    main()
