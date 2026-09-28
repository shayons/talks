# %% [markdown]
# # 2. Embed the corpus and the test questions with Cohere Embed v4 on Bedrock
#
# Posts use `input_type='search_document'`; questions use `'search_query'`.
# Only rows whose `embedding IS NULL` are sent, so this cell is safe to re-run after
# an interruption. The first full run makes ~600 calls of 96 posts each.

# %%
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from pgvector import Vector

from hybrid_lab.bedrock import MAX_TEXTS_PER_CALL, BedrockThrottled, embed
from hybrid_lab.db import connect

WORKERS = 4  # Embed v4 has a tokens-per-minute quota; more workers just wait longer.
THROTTLE_WAITS = (15, 30, 60, 60, 120, 120)  # seconds, after botocore's own retries


def pending(table: str) -> list[tuple[str, str]]:
    """Rows that still need an embedding (blank text can never be embedded)."""
    with connect() as conn:
        return conn.execute(
            f"SELECT id, body FROM {table} WHERE embedding IS NULL AND btrim(body) <> '' "
            "ORDER BY id"
        ).fetchall()


def embed_with_patience(texts: list[str], input_type: str) -> list[list[float]]:
    """Embed a batch, waiting out quota throttling instead of failing the whole run."""
    for wait in THROTTLE_WAITS:
        try:
            return embed(texts, input_type)
        except BedrockThrottled:
            time.sleep(wait)
    return embed(texts, input_type)


def embed_and_store(table: str, rows: list[tuple[str, str]], input_type: str) -> int:
    """Embed one batch and write it back in a single transaction."""
    vectors = embed_with_patience([body for _, body in rows], input_type)
    with connect() as conn:
        conn.cursor().executemany(
            f"UPDATE {table} SET embedding = %s WHERE id = %s",
            [(Vector(vector), row_id) for (row_id, _), vector in zip(rows, vectors, strict=True)],
        )
    return len(rows)


def embed_table(table: str, input_type: str) -> None:
    rows = pending(table)
    batches = [rows[i:i + MAX_TEXTS_PER_CALL] for i in range(0, len(rows), MAX_TEXTS_PER_CALL)]
    print(f"{table}: {len(rows):,} rows to embed in {len(batches)} calls")
    done, started = 0, time.perf_counter()
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(embed_and_store, table, batch, input_type) for batch in batches]
        for future in as_completed(futures):
            done += future.result()
            if done % (MAX_TEXTS_PER_CALL * 50) < MAX_TEXTS_PER_CALL or done == len(rows):
                rate = done / (time.perf_counter() - started)
                print(f"  {done:,}/{len(rows):,}  ({rate:,.0f} rows/s)")


# %%
embed_table("queries", "search_query")
embed_table("docs", "search_document")

# %% [markdown]
# Check: every non-blank row has a 1536-dimension vector, and Embed v4 returns
# unit-length vectors, so cosine distance and inner product rank identically.

# %%
with connect() as conn:
    print(conn.execute("""
        SELECT 'docs' AS table_name, count(*) FILTER (WHERE embedding IS NOT NULL) AS embedded,
               count(*) FILTER (WHERE embedding IS NULL AND btrim(body) <> '') AS missing,
               round(avg(vector_norm(embedding))::numeric, 4) AS mean_norm
          FROM docs
        UNION ALL
        SELECT 'queries', count(*) FILTER (WHERE embedding IS NOT NULL),
               count(*) FILTER (WHERE embedding IS NULL AND btrim(body) <> ''),
               round(avg(vector_norm(embedding))::numeric, 4)
          FROM queries
    """).fetchall())

# %% [markdown]
# ## Compact, then build the indexes (sql/02_indexes.sql)
#
# 57,638 UPDATEs left a dead copy of every row. VACUUM FULL rewrites the table
# compactly before the indexes are built, so sizes and timings reflect a clean table.

# %%
from hybrid_lab.db import run_script

with connect(autocommit=True) as conn:
    conn.execute("VACUUM (FULL, ANALYZE) docs")
    for statement, elapsed_ms in run_script(conn, "02_indexes.sql"):
        print(f"{elapsed_ms / 1000:8.1f} s  {statement}")
