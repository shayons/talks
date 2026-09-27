# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]>=3.2"]
# ///
"""Report what hybrid search needs from this database, and describe one table. Read-only.

DATABASE_URL=postgresql://... uv run scripts/check_env.py --table public.articles
"""

from __future__ import annotations

import argparse
import os

import psycopg
from psycopg import sql


def parse_args() -> argparse.Namespace:
    """Read --dsn (default DATABASE_URL) and the optional --table."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--table", help="schema.table to describe")
    args = parser.parse_args()
    if not args.dsn:
        parser.error("Set DATABASE_URL or pass --dsn.")
    return args


def report_server(conn: psycopg.Connection) -> None:
    """Print the server version and the state of the extensions hybrid search uses."""
    version = conn.execute("SHOW server_version").fetchone()[0]
    print(f"PostgreSQL {version}")
    rows = conn.execute(
        "SELECT a.name, a.default_version, e.extversion"
        "  FROM pg_available_extensions a LEFT JOIN pg_extension e ON e.extname = a.name"
        " WHERE a.name IN ('vector', 'pg_textsearch', 'pg_trgm') ORDER BY a.name"
    ).fetchall()
    found = {name for name, _, _ in rows}
    for name, available, installed in rows:
        state = f"installed {installed}" if installed else "available, not installed"
        print(f"  {name}: {state} (default {available})")
    for name in sorted({"vector", "pg_textsearch"} - found):
        print(f"  {name}: NOT AVAILABLE on this server")
    preload = conn.execute("SHOW shared_preload_libraries").fetchone()[0]
    print(f"  shared_preload_libraries = '{preload}' (pg_textsearch must be listed here)")
    if int(version.split(".")[0]) < 13:
        print("  WARNING: PostgreSQL 13+ is required.")


def report_table(conn: psycopg.Connection, qualified: str) -> None:
    """Print columns, estimated rows, indexes, and three sample rows of one table."""
    schema, table = qualified.split(".", 1)
    if conn.execute("SELECT to_regclass(%s)", (qualified,)).fetchone()[0] is None:
        raise SystemExit(f"Table {qualified} not found.")
    columns = conn.execute(
        "SELECT attname, format_type(atttypid, atttypmod), attnotnull FROM pg_attribute"
        " WHERE attrelid = %s::regclass AND attnum > 0 AND NOT attisdropped ORDER BY attnum",
        (qualified,),
    ).fetchall()
    estimate = conn.execute(
        "SELECT reltuples::bigint FROM pg_class WHERE oid = %s::regclass", (qualified,)
    ).fetchone()[0]
    if estimate > 0:
        print(f"\n{qualified}: about {estimate:,} rows (planner estimate)")
    else:
        count_query = sql.SQL("SELECT count(*) FROM {}.{}").format(
            sql.Identifier(schema), sql.Identifier(table)
        )
        exact = conn.execute(count_query).fetchone()[0]
        print(f"\n{qualified}: {exact:,} rows (never analyzed; run ANALYZE before tuning)")
    for name, data_type, not_null in columns:
        print(f"  {name}: {data_type}{' NOT NULL' if not_null else ''}")
    print("Indexes:")
    for name, definition in conn.execute(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = %s AND tablename = %s",
        (schema, table),
    ):
        print(f"  {name}: {definition}")
    print("Sample rows (text truncated to 120 characters):")
    query = sql.SQL("SELECT * FROM {}.{} LIMIT 3").format(
        sql.Identifier(schema), sql.Identifier(table)
    )
    for row in conn.execute(query):
        print("  " + " | ".join(str(value)[:120] for value in row))


def main() -> None:
    """Connect read-only and print the report."""
    args = parse_args()
    with psycopg.connect(args.dsn) as conn:
        conn.read_only = True
        report_server(conn)
        if args.table:
            report_table(conn, args.table)


if __name__ == "__main__":
    main()
