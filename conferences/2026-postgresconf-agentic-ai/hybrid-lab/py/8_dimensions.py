# %% [markdown]
# # 8 · How many dimensions do you need?
#
# Cohere Embed v4 returns 256, 512, 1024, or 1536 dimensions (output_dimension), and the
# shorter vectors are prefixes of the 1536 one: the same numbers, checked against the API.
# So sql/12c-12e search the stored 1536-dimension column at 1024, 512, and 256 dimensions
# through expression indexes, with no re-embedding.
#
# For each dataset: NDCG@10 with a 95% paired bootstrap interval against the full 1536,
# Recall@50, bytes per stored vector, and HNSW index size. Latency is reported for FiQA
# only: on the small datasets the planner sometimes prefers an exact scan to the index.
# Writes results/dimensions.md. Run after py/4_evaluate.py (or scripts/evaluate_all.sh).

# %%
import random
from statistics import mean

from hybrid_lab.db import LAB_ROOT, connect

DATASETS = ("fiqa", "scifact", "nfcorpus", "scidocs")
ARMS = (  # stage, dimensions, index, stored-vector expression
    ("vector", 1536, "docs_embedding_hnsw", "embedding"),
    ("vector_1024", 1024, "docs_embedding_1024_hnsw", "subvector(embedding, 1, 1024)"),
    ("vector_512", 512, "docs_embedding_512_hnsw", "subvector(embedding, 1, 512)"),
    ("vector_256", 256, "docs_embedding_256_hnsw", "subvector(embedding, 1, 256)"),
)


def paired_interval(a: dict, b: dict, rounds: int = 10_000) -> tuple[float, float, float]:
    """Mean difference a − b (×100) and its 95% paired bootstrap interval (seed 7)."""
    ids = sorted(a.keys() & b.keys())
    diffs = [a[q] - b[q] for q in ids]
    rng = random.Random(7)
    samples = sorted(mean(rng.choices(diffs, k=len(diffs))) for _ in range(rounds))
    return 100 * mean(diffs), 100 * samples[int(0.025 * rounds)], 100 * samples[int(0.975 * rounds)]


def measure(name: str) -> list[dict]:
    """One row per dimension count for one dataset."""
    conn = connect(name)
    per_question: dict[str, dict[str, float]] = {}
    for stage, query_id, ndcg in conn.execute(
        "SELECT stage, query_id, ndcg10 FROM question_scores WHERE stage = ANY(%s)",
        ([arm[0] for arm in ARMS],),
    ):
        per_question.setdefault(stage, {})[query_id] = float(ndcg)
    board = {row[0]: row[1:] for row in conn.execute(
        "SELECT stage, recall_at_50, p50_ms FROM scoreboard WHERE stage = ANY(%s)",
        ([arm[0] for arm in ARMS],),
    )}
    rows = []
    for stage, dims, index, expression in ARMS:
        size, vector_bytes = conn.execute(
            f"SELECT pg_relation_size(%s::regclass),"
            f" (SELECT pg_column_size({expression}) FROM docs WHERE embedding IS NOT NULL LIMIT 1)",
            (index,),
        ).fetchone()
        rows.append({
            "dims": dims,
            "ndcg": 100 * mean(per_question[stage].values()),
            "delta": None if stage == "vector"
            else paired_interval(per_question[stage], per_question["vector"]),
            "recall": float(board[stage][0]),
            "p50": float(board[stage][1]),
            "index_mb": size / 1024 / 1024,
            "bytes": vector_bytes,
        })
    conn.close()
    return rows


# %%
results = {name: measure(name) for name in DATASETS}
for name, rows in results.items():
    print(name, [(r["dims"], round(r["ndcg"], 1)) for r in rows])


# %%
def delta_cell(row: dict) -> str:
    if row["delta"] is None:
        return "baseline"
    diff, low, high = row["delta"]
    marker = " ↓" if high < 0 else (" **↑**" if low > 0 else "")
    return f"{diff:+.1f} ({low:+.1f}…{high:+.1f}){marker}"


lines = [
    "# Embed v4 dimensions",
    "",
    "Cohere Embed v4's first N dimensions, searched through expression indexes on the stored",
    "1536-dimension column (the API's output_dimension returns the same prefix). NDCG@10 on each",
    "dataset's test questions; the change is against the full 1536 with a 95% paired bootstrap",
    "interval (↓: interval below zero). HNSW sizes are PostgreSQL relation sizes.",
    "",
]
for name, rows in results.items():
    latency = name == "fiqa"
    lines += [f"## {name}", "",
              "| Dims | Bytes per vector | HNSW index | NDCG@10 | Change | Recall@50 |"
              + (" p50 ms |" if latency else ""),
              "| ---: | ---: | ---: | ---: | --- | ---: |" + (" ---: |" if latency else "")]
    for r in rows:
        lines.append(
            f"| {r['dims']} | {r['bytes']:,} | {r['index_mb']:.0f} MB | {r['ndcg']:.1f} | "
            f"{delta_cell(r)} | {r['recall']:.1f} |" + (f" {r['p50']:.1f} |" if latency else "")
        )
    lines.append("")
text = "\n".join(lines)
(LAB_ROOT / "results" / "dimensions.md").write_text(text)
print(text)
