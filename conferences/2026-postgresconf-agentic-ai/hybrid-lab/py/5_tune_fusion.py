# %% [markdown]
# # 5. Tune the score blend on dev questions, never on test
#
# RRF throws away how confident each list is. A convex combination keeps it: min-max
# normalize each list's scores to [0, 1] per question, then
#
#     score = w × vector_normalized + (1 − w) × bm25_normalized
#
# (Bruch, Gai & Ingber, "An Analysis of Fusion Functions for Hybrid Retrieval", ACM TOIS
# 2023.) The weight w is chosen per dataset on its held-out dev questions (FiQA: its dev
# split; SciFact: its train split) and stored in fusion_settings, where the blend files
# (08c, 08e, 08f) read it. Test questions are never looked at.
#
# Run per dataset: LAB_DATASET=scifact uv run python py/5_tune_fusion.py

# %%
from collections import defaultdict
from statistics import mean

from hybrid_lab.arms import BY_STAGE, run_sql_arm
from hybrid_lab.db import connect, dataset
from hybrid_lab.metrics import ndcg_at_k

conn = connect()
dev_ids = [r[0] for r in conn.execute("SELECT id FROM queries WHERE split = 'dev' ORDER BY id")]
relevance = defaultdict(dict)
for query_id, doc_id, grade in conn.execute(
    "SELECT q.query_id, q.doc_id, q.relevance FROM qrels q"
    " JOIN queries s ON s.id = q.query_id WHERE s.split = 'dev'"
):
    relevance[query_id][doc_id] = grade
conn.rollback()

def retrieve(stage: str) -> dict[str, list[tuple[str, float]]]:
    """Run one arm's SQL for every dev question and keep (doc_id, score) lists."""
    return {
        query_id: [(row["doc_id"], float(row["score"]))
                   for row in run_sql_arm(conn, BY_STAGE[stage], query_id).rows]
        for query_id in dev_ids
    }


if not dev_ids:
    raise SystemExit(f"{dataset()} has no dev questions; sql/08c uses the default weight 0.5.")
keyword_cache: dict[str, dict[str, list[tuple[str, float]]]] = {}
print(f"{dataset()}: {len(dev_ids)} dev questions")


# %%
def min_max(scored: list[tuple[str, float]]) -> dict[str, float]:
    """Scale one list's scores to [0, 1]; a list of equal scores maps to 1."""
    if not scored:
        return {}
    low, high = min(s for _, s in scored), max(s for _, s in scored)
    return {d: (s - low) / (high - low) if high > low else 1.0 for d, s in scored}


def blend(vector_list, keyword_list, weight: float) -> list[str]:
    """Rank the union of both lists by the weighted sum of normalized scores."""
    vector, keyword = min_max(vector_list), min_max(keyword_list)
    fused = {d: weight * vector.get(d, 0.0) + (1 - weight) * keyword.get(d, 0.0)
             for d in vector.keys() | keyword.keys()}
    return [d for d, _ in sorted(fused.items(), key=lambda item: (-item[1], item[0]))]


def dev_ndcg(ranking) -> float:
    return 100 * mean(ndcg_at_k(ranking(q), relevance[q]) for q in dev_ids)


def tune(vector_stage: str, setting: str, keyword_stage: str = "bm25") -> None:
    """Grid-search the weight on dev questions and store the best (ties favor vector)."""
    if keyword_stage not in keyword_cache:
        keyword_cache[keyword_stage] = retrieve(keyword_stage)
    keyword_lists = keyword_cache[keyword_stage]
    vector_lists = retrieve(vector_stage)
    baseline = dev_ndcg(lambda q: [d for d, _ in vector_lists[q]])
    grid = {w / 20: dev_ndcg(lambda q, w=w / 20: blend(vector_lists[q], keyword_lists[q], w))
            for w in range(0, 21)}
    best = max(grid, key=lambda w: (grid[w], w))
    note = (f"chosen on {len(dev_ids)} dev questions: NDCG@10 {grid[best]:.1f} "
            f"(vector alone {baseline:.1f}, {BY_STAGE[keyword_stage].label} alone "
            f"{grid[0.0]:.1f})")
    conn.execute(
        "INSERT INTO fusion_settings VALUES (%s, %s, %s)"
        " ON CONFLICT (name) DO UPDATE SET value = EXCLUDED.value, note = EXCLUDED.note",
        (setting, best, note),
    )
    conn.commit()
    print(f"{setting} = {best:.2f}: {note}")


# %% Cohere Embed v4 (sql/08c), its first 256 dimensions (08g), the small local model (08e),
# and core PostgreSQL only (08f)
tune("vector", "blend_vector_weight")
tune("vector_256", "blend_vector_weight_256")
local_ready = conn.execute("SELECT count(embedding_local) > 0 FROM docs").fetchone()[0]
conn.rollback()
if local_ready:
    tune("vector_local", "blend_vector_weight_local")
    tune("vector_local", "blend_vector_weight_native_local", keyword_stage="keyword_or")
else:
    print("Small-model vectors not filled yet; run py/2b_embed_local.py, then this file again.")
