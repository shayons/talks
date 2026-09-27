# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]>=3.2", "pgvector>=0.4", "boto3>=1.35"]
# ///
r"""Grade keyword, vector, hybrid (and optionally reranked) search on your own table.

    # With labels: CSV columns question,relevant_id[,relevance]
    uv run templates/evaluate.py --table public.articles --id-column id \\
        --text-sql "coalesce(title,'') || ' ' || coalesce(body,'')" --dims 1536 \\
        --function public.articles_hybrid_search --labels labels.csv

    # Without labels: an LLM writes one question per sampled row (see references/evaluation.md)
    uv run templates/evaluate.py ... --synthetic 200

Everything is written to the hybrid_eval schema; templates/scoreboard.sql prints the result.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
from pathlib import Path

import psycopg
from embedding_providers import make_provider
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg import sql

HERE = Path(__file__).parent
DEPTH = 50
QUESTION_PROMPT = (
    "Here is a document from a search index.\n\n<document>\n{text}\n</document>\n\n"
    "Write one question that a real person might type into a search box and that this "
    "document answers. Paraphrase: do not copy distinctive phrases or rare words from the "
    "document unless the person would already know them (for example a product name). "
    "Reply with the question only."
)


def parse_args() -> argparse.Namespace:
    """Read command-line options; DATABASE_URL is the default DSN."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--table", required=True, help="schema.table")
    parser.add_argument("--id-column", required=True)
    parser.add_argument("--text-sql", required=True)
    parser.add_argument("--function", required=True, help="schema.<table>_hybrid_search")
    parser.add_argument("--provider", default="bedrock", choices=["bedrock", "openai", "fastembed"])
    parser.add_argument("--model")
    parser.add_argument("--dims", type=int, required=True)
    parser.add_argument("--text-config", default="english")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--labels", type=Path)
    source.add_argument("--synthetic", type=int, metavar="N")
    parser.add_argument("--question-model", default="us.anthropic.claude-sonnet-5")
    parser.add_argument("--rerank", action="store_true", help="add Cohere Rerank 3.5 on Bedrock")
    args = parser.parse_args()
    if not args.dsn:
        parser.error("Set DATABASE_URL or pass --dsn.")
    return args


def create_schema(conn: psycopg.Connection, dims: int) -> None:
    """Recreate the hybrid_eval tables for a fresh run."""
    conn.execute(sql.SQL("""
        CREATE SCHEMA IF NOT EXISTS hybrid_eval;
        DROP TABLE IF EXISTS hybrid_eval.runs, hybrid_eval.timings, hybrid_eval.qrels,
                             hybrid_eval.questions;
        CREATE TABLE hybrid_eval.questions (question_id text PRIMARY KEY, body text NOT NULL,
                                            embedding vector({dims}));
        CREATE TABLE hybrid_eval.qrels (question_id text REFERENCES hybrid_eval.questions,
                                        doc_id text, relevance int NOT NULL DEFAULT 1,
                                        PRIMARY KEY (question_id, doc_id));
        CREATE TABLE hybrid_eval.runs (arm text, question_id text, rank int, doc_id text,
                                       score float8, PRIMARY KEY (arm, question_id, rank));
        CREATE TABLE hybrid_eval.timings (arm text, question_id text, elapsed_ms float8,
                                          PRIMARY KEY (arm, question_id));
    """).format(dims=sql.Literal(dims)))


def load_labels(conn: psycopg.Connection, path: Path) -> None:
    """Load question,relevant_id[,relevance] rows from a CSV file."""
    count = 0
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            question_id = "L" + hashlib.sha1(row["question"].encode()).hexdigest()[:12]
            conn.execute("INSERT INTO hybrid_eval.questions VALUES (%s, %s) ON CONFLICT DO NOTHING",
                         (question_id, row["question"]))
            conn.execute("INSERT INTO hybrid_eval.qrels VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                         (question_id, row["relevant_id"], int(row.get("relevance") or 1)))
            count += 1
    if not count:
        raise SystemExit(f"{path} has no rows; expected columns question,relevant_id")
    print(f"Loaded {count} labeled rows from {path}")


def synthesize(conn: psycopg.Connection, args: argparse.Namespace) -> None:
    """Ask an LLM for one question per sampled row; that row is its known answer."""
    import boto3

    schema, table = args.table.split(".", 1)
    rows = conn.execute(sql.SQL(
        "SELECT {id}::text, left({text}, 6000) FROM {schema}.{table}"
        " WHERE btrim({text}) <> '' ORDER BY random() LIMIT {n}"
    ).format(id=sql.Identifier(args.id_column), text=sql.SQL(args.text_sql),
             schema=sql.Identifier(schema), table=sql.Identifier(table),
             n=sql.Literal(args.synthetic))).fetchall()
    client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
    for doc_id, text in rows:
        response = client.converse(
            modelId=args.question_model,
            messages=[{"role": "user", "content": [{"text": QUESTION_PROMPT.format(text=text)}]}],
            inferenceConfig={"maxTokens": 120},
        )
        question = response["output"]["message"]["content"][0]["text"].strip()
        conn.execute("INSERT INTO hybrid_eval.questions VALUES (%s, %s)", (f"S{doc_id}", question))
        conn.execute("INSERT INTO hybrid_eval.qrels VALUES (%s, %s)", (f"S{doc_id}", doc_id))
    print(f"Wrote {len(rows)} synthetic questions with {args.question_model}")


def embed_questions(conn: psycopg.Connection, args: argparse.Namespace) -> None:
    """Embed every question with the provider's query input type."""
    provider = make_provider(args.provider, args.dims, args.model)
    rows = conn.execute("SELECT question_id, body FROM hybrid_eval.questions").fetchall()
    for start in range(0, len(rows), provider.batch_size):
        batch = rows[start:start + provider.batch_size]
        vectors = provider.embed([body for _, body in batch], "query")
        for (question_id, _), vector in zip(batch, vectors, strict=True):
            conn.execute("UPDATE hybrid_eval.questions SET embedding = %s WHERE question_id = %s",
                         (Vector(vector), question_id))


def arm_queries(args: argparse.Namespace) -> dict[str, sql.Composable]:
    """SQL for each arm; %(body)s is the question text and %(emb)s its embedding."""
    schema, table = args.table.split(".", 1)
    names = {"id": sql.Identifier(args.id_column), "schema": sql.Identifier(schema),
             "table": sql.Identifier(table), "cfg": sql.Literal(args.text_config),
             "fn": sql.SQL(".").join(sql.Identifier(p) for p in args.function.split(".", 1))}
    return {
        "keyword": sql.SQL(
            "SELECT {id}::text, ts_rank_cd(search_tsv, q) FROM {schema}.{table},"
            " CAST(replace(plainto_tsquery({cfg}, %(body)s)::text, ' & ', ' | ') AS tsquery) q"
            " WHERE search_tsv @@ q ORDER BY 2 DESC, 1 LIMIT 50").format(**names),
        "vector": sql.SQL(
            "SELECT {id}::text, 1 - (embedding <=> %(emb)s) FROM {schema}.{table}"
            " WHERE embedding IS NOT NULL ORDER BY embedding <=> %(emb)s LIMIT 50").format(**names),
        "hybrid": sql.SQL(
            "SELECT {id}::text, score FROM {fn}(%(body)s, %(emb)s, 50)").format(**names),
    }


def run_arms(conn: psycopg.Connection, args: argparse.Namespace) -> None:
    """Run each arm for every question twice; the second, warm pass is recorded."""
    questions = conn.execute("SELECT question_id, body, embedding FROM hybrid_eval.questions"
                             " WHERE embedding IS NOT NULL").fetchall()
    conn.execute("SET hnsw.ef_search = 100")
    for arm, query in arm_queries(args).items():
        for question_id, body, embedding in questions * 2:  # first pass warms the cache
            started = time.perf_counter()
            rows = conn.execute(query, {"body": body, "emb": embedding}).fetchall()
            record(conn, arm, question_id, rows, (time.perf_counter() - started) * 1000)
        print(f"  {arm}: {len(questions)} questions")


def record(conn, arm: str, question_id: str, rows: list, elapsed_ms: float) -> None:
    """Replace one arm's stored top 50 and timing for one question."""
    conn.execute("DELETE FROM hybrid_eval.runs WHERE arm = %s AND question_id = %s",
                 (arm, question_id))
    conn.cursor().executemany(
        "INSERT INTO hybrid_eval.runs VALUES (%s, %s, %s, %s, %s)",
        [(arm, question_id, rank, doc_id, score)
         for rank, (doc_id, score) in enumerate(rows[:DEPTH], start=1)],
    )
    conn.execute("INSERT INTO hybrid_eval.timings VALUES (%s, %s, %s) ON CONFLICT (arm,"
                 " question_id) DO UPDATE SET elapsed_ms = EXCLUDED.elapsed_ms",
                 (arm, question_id, elapsed_ms))


def rerank(conn: psycopg.Connection, args: argparse.Namespace) -> None:
    """Reorder each question's hybrid top 50 with Cohere Rerank 3.5 on Bedrock."""
    import boto3

    client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
    schema, table = args.table.split(".", 1)
    text_query = sql.SQL("SELECT {text} FROM {schema}.{table} WHERE {id}::text = %s").format(
        text=sql.SQL(args.text_sql), schema=sql.Identifier(schema),
        table=sql.Identifier(table), id=sql.Identifier(args.id_column))
    for question_id, body in conn.execute(
            "SELECT question_id, body FROM hybrid_eval.questions").fetchall():
        ids = [r[0] for r in conn.execute("SELECT doc_id FROM hybrid_eval.runs WHERE arm ="
                                          " 'hybrid' AND question_id = %s ORDER BY rank",
                                          (question_id,)).fetchall()]
        if not ids:
            continue
        docs = [conn.execute(text_query, (doc_id,)).fetchone()[0] or " " for doc_id in ids]
        started = time.perf_counter()
        response = client.invoke_model(modelId="cohere.rerank-v3-5:0", body=json.dumps(
            {"query": body, "documents": docs, "top_n": len(docs), "api_version": 2}))
        results = json.loads(response["body"].read())["results"]
        rows = [(ids[r["index"]], r["relevance_score"]) for r in results]
        record(conn, "hybrid_rerank", question_id, rows, (time.perf_counter() - started) * 1000)
    print("  hybrid_rerank: done")


def main() -> None:
    """Build the question set, run every arm, and print the scoreboard."""
    args = parse_args()
    with psycopg.connect(args.dsn, autocommit=True) as conn:
        register_vector(conn)
        create_schema(conn, args.dims)
        if args.labels:
            load_labels(conn, args.labels)
        else:
            synthesize(conn, args)
        embed_questions(conn, args)
        run_arms(conn, args)
        if args.rerank:
            rerank(conn, args)
        cur = conn.execute((HERE / "scoreboard.sql").read_text())
        print("\n| arm | NDCG@10 | Recall@50 | p50 ms | p95 ms | questions |")
        print("| --- | ---: | ---: | ---: | ---: | ---: |")
        for row in cur.fetchall():
            print("| " + " | ".join(str(value) for value in row) + " |")


if __name__ == "__main__":
    main()
