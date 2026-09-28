# %% [markdown]
# # 6 · Summarize every dataset, with uncertainty
#
# For each dataset: NDCG@10 of the main arms on its test questions, and each hybrid arm's
# difference from vector search with the same embedding model. The 95% interval comes
# from a paired bootstrap over questions (10,000 resamples): a difference whose interval
# excludes 0 is unlikely to be noise. Writes results/summary.md.

# %%
import random
from statistics import mean

from hybrid_lab.arms import BY_STAGE
from hybrid_lab.db import LAB_ROOT, connect
from hybrid_lab.evaluate import refresh_scoreboard

DATASETS = ("fiqa", "scifact", "nfcorpus", "scidocs")
COMPARISONS = (  # (arm, baseline with the same embedding model)
    ("rrf_bm25", "vector"),
    ("blend_bm25", "vector"),
    ("vector_rerank", "vector"),
    ("rrf_local", "vector_local"),
    ("blend_local", "vector_local"),
    ("blend_native_local", "vector_local"),
    ("blend_256", "vector_256"),
)
SHOWN = ("bm25", "vector", "rrf_bm25", "blend_bm25", "vector_rerank",
         "vector_local", "rrf_local", "blend_local", "blend_native_local",
         "vector_256", "blend_256")


def per_question(conn) -> dict[str, dict[str, float]]:
    """NDCG@10 per question for every stage in question_scores."""
    scores: dict[str, dict[str, float]] = {}
    for stage, query_id, ndcg in conn.execute(
        "SELECT stage, query_id, ndcg10 FROM question_scores"
    ):
        scores.setdefault(stage, {})[query_id] = float(ndcg)
    return scores


def paired_interval(a: dict, b: dict, rounds: int = 10_000) -> tuple[float, float, float]:
    """Mean difference a − b (×100) and its 95% paired bootstrap interval."""
    ids = sorted(a.keys() & b.keys())
    diffs = [a[q] - b[q] for q in ids]
    rng = random.Random(7)
    samples = sorted(mean(rng.choices(diffs, k=len(diffs))) for _ in range(rounds))
    return 100 * mean(diffs), 100 * samples[int(0.025 * rounds)], 100 * samples[int(0.975 * rounds)]


# %%
tables, deltas = {}, {}
for name in DATASETS:
    try:
        conn = connect(name)
    except RuntimeError:
        print(f"{name}: not loaded, skipped")
        continue
    refresh_scoreboard(conn)
    scores = per_question(conn)
    conn.close()
    tables[name] = {s: 100 * mean(v.values()) for s, v in scores.items() if s in SHOWN}
    deltas[name] = {arm: paired_interval(scores[arm], scores[base])
                    for arm, base in COMPARISONS if arm in scores and base in scores}
    print(name, {s: round(v, 1) for s, v in tables[name].items()})


# %%
def cell(name: str, stage: str) -> str:
    value = tables[name].get(stage)
    if value is None:
        return "–"
    if stage not in deltas[name]:
        return f"{value:.1f}"
    diff, low, high = deltas[name][stage]
    marker = " **↑**" if low > 0 else (" ↓" if high < 0 else "")
    return f"{value:.1f} ({diff:+.1f}, {low:+.1f}…{high:+.1f}){marker}"


names = list(tables)
lines = [
    "# Across datasets",
    "",
    "NDCG@10 on each dataset's test questions. Hybrid rows show the difference from vector",
    "search with the same embedding model and its 95% paired bootstrap interval. **↑** marks",
    "an interval above zero; ↓ an interval below zero. Blend weights were tuned on each",
    "dataset's dev questions (SCIDOCS has none, so its blends use 0.5).",
    "",
    "| Arm | " + " | ".join(names) + " |",
    "| --- | " + " | ".join("---:" for _ in names) + " |",
]
for stage in SHOWN:
    lines.append(f"| {BY_STAGE[stage].label} | " + " | ".join(cell(n, stage) for n in names) + " |")
text = "\n".join(lines) + "\n"
(LAB_ROOT / "results" / "summary.md").write_text(text)
print(text)
