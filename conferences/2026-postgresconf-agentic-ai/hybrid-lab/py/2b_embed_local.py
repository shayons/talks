# %% [markdown]
# # 2b. Embed with a small open-source model, on this laptop
#
# `BAAI/bge-small-en-v1.5` (MIT license, 384 dimensions) through fastembed (ONNX on the CPU).
# No API, no network after the first model download. Documents use `passage_embed`;
# questions use `query_embed`, which adds the model's retrieval instruction.
#
# Its vectors go in their own column, `embedding_local`, next to Cohere Embed v4's
# `embedding`: one column per model, never mixed. Install with `uv sync --extra local`.

# %%
import os
import time

from fastembed import TextEmbedding
from pgvector import Vector

from hybrid_lab.db import connect, dataset

MODEL = "BAAI/bge-small-en-v1.5"
CHUNK = 256
model = TextEmbedding(MODEL, threads=os.cpu_count())


def pending(table: str) -> list[tuple[str, str]]:
    """Rows without a local embedding (blank text can never be embedded)."""
    with connect() as conn:
        return conn.execute(
            f"SELECT id, body FROM {table} WHERE embedding_local IS NULL AND btrim(body) <> ''"
            " ORDER BY id"
        ).fetchall()


def fill(table: str, kind: str) -> None:
    """Embed pending rows chunk by chunk and write each chunk back in one transaction."""
    rows = pending(table)
    started = time.perf_counter()
    for start in range(0, len(rows), CHUNK):
        chunk = rows[start:start + CHUNK]
        texts = [body for _, body in chunk]
        vectors = model.query_embed(texts) if kind == "query" else model.passage_embed(texts)
        with connect() as conn:
            conn.cursor().executemany(
                f"UPDATE {table} SET embedding_local = %s WHERE id = %s",
                [(Vector(vector.tolist()), row_id)
                 for (row_id, _), vector in zip(chunk, vectors, strict=True)],
            )
        done = start + len(chunk)
        if done % (CHUNK * 20) < CHUNK or done == len(rows):
            rate = done / (time.perf_counter() - started)
            print(f"  {table}: {done:,}/{len(rows):,} ({rate:,.0f}/s)")


# %% Drop the index during the bulk update; rebuilding it afterwards is much faster.
with connect(autocommit=True) as conn:
    conn.execute("DROP INDEX IF EXISTS docs_embedding_local_hnsw")
print(f"{dataset()}: embedding with {MODEL}")
fill("queries", "query")
fill("docs", "passage")

# %%
with connect(autocommit=True) as conn:
    conn.execute("SET maintenance_work_mem = '1GB'")
    conn.execute("SET max_parallel_maintenance_workers = 7")
    started = time.perf_counter()
    conn.execute(
        "CREATE INDEX docs_embedding_local_hnsw ON docs"
        " USING hnsw (embedding_local vector_cosine_ops)"
    )
    conn.execute("VACUUM (ANALYZE) docs")
    print(f"{dataset()}: local HNSW index built in {time.perf_counter() - started:.1f} s")
