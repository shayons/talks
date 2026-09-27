# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]>=3.2", "pgvector>=0.4", "boto3>=1.35"]
# ///
r"""Run a few real questions through <table>_hybrid_search() and show where each row came from.

    uv run templates/try_search.py --function public.articles_hybrid_search --dims 1536 \
        --display-sql "left(title, 80)" --table public.articles --id-column id \
        "how do I reset my password" "refund for a damaged item"

Each question is embedded with the provider's QUERY input type, as the application must do.
"""

from __future__ import annotations

import argparse
import os

import psycopg
from embedding_providers import make_provider
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg import sql


def parse_args() -> argparse.Namespace:
    """Read the function, display settings, and the questions to try."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("questions", nargs="+")
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--function", required=True, help="schema.<table>_hybrid_search")
    parser.add_argument("--table", required=True, help="schema.table, to show each row")
    parser.add_argument("--id-column", required=True)
    parser.add_argument("--display-sql", required=True, help="SQL expression shown per row")
    parser.add_argument("--provider", default="bedrock", choices=["bedrock", "openai", "fastembed"])
    parser.add_argument("--model")
    parser.add_argument("--dims", type=int, required=True)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    if not args.dsn:
        parser.error("Set DATABASE_URL or pass --dsn.")
    return args


def main() -> None:
    """Embed each question, call the function, and print its rows with both ranks."""
    args = parse_args()
    provider = make_provider(args.provider, args.dims, args.model)
    vectors = provider.embed(args.questions, "query")
    schema, table = args.table.split(".", 1)
    query = sql.SQL(
        "SELECT h.score, h.keyword_rank, h.vector_rank, {display}"
        "  FROM {fn}(%s, %s, %s) h JOIN {schema}.{table} t ON t.{id} = h.{id}"
        " ORDER BY h.score DESC"
    ).format(
        display=sql.SQL(args.display_sql),
        fn=sql.SQL(".").join(sql.Identifier(p) for p in args.function.split(".", 1)),
        schema=sql.Identifier(schema), table=sql.Identifier(table),
        id=sql.Identifier(args.id_column),
    )
    with psycopg.connect(args.dsn) as conn:
        register_vector(conn)
        for question, vector in zip(args.questions, vectors, strict=True):
            print(f"\n{question}")
            print("  rrf      keyword  vector  row")
            for score, keyword, semantic, shown in conn.execute(
                query, (question, Vector(vector), args.limit)
            ):
                print(f"  {score:.4f}  {keyword or '-':>7}  {semantic or '-':>6}  {shown}")


if __name__ == "__main__":
    main()
