# %% [markdown]
# # 7 · How much does RRF's k matter?
#
# RRF scores each document Σ 1 / (k + rank). The stored runs already hold every test
# question's BM25 and vector top 50, so RRF at any k is recomputed here in SQL, with no new
# searches. At k = 60 it must reproduce the stored RRF arms exactly; the script checks that.
#
# This is a sensitivity check on test questions, not tuning: no k is chosen here.
# Writes results/k_sweep.md.

# %%
from statistics import mean

from hybrid_lab.db import LAB_ROOT, connect

DATASETS = ("fiqa", "scifact", "nfcorpus", "scidocs")
KS = (5, 10, 30, 60, 100, 200)
PAIRS = {  # label: (keyword stage, vector stage, stored RRF stage at k = 60)
    "BM25 + Embed v4": ("bm25", "vector", "rrf_bm25"),
    "BM25 + bge-small": ("bm25", "vector_local", "rrf_local"),
}

SWEEP_SQL = """
WITH ks AS (SELECT unnest(%(ks)s::int[]) AS k),
lists AS (
  SELECT r.query_id, r.doc_id, r.rank
    FROM runs r JOIN queries q ON q.id = r.query_id AND q.split = 'test'
   WHERE r.stage IN (%(keyword)s, %(vector)s)
),
fused AS (
  SELECT ks.k, l.query_id, l.doc_id, sum(1.0 / (ks.k + l.rank)) AS score
    FROM lists l CROSS JOIN ks
   GROUP BY ks.k, l.query_id, l.doc_id
),
ranked AS (
  SELECT k, query_id, doc_id,
         row_number() OVER (PARTITION BY k, query_id ORDER BY score DESC, doc_id) AS rank
    FROM fused
),
ideal AS (
  SELECT query_id, sum(relevance / log(2, position + 1.0)) AS idcg
    FROM (SELECT query_id, relevance,
                 row_number() OVER (PARTITION BY query_id ORDER BY relevance DESC) AS position
            FROM qrels) ordered
   WHERE position <= 10
   GROUP BY query_id
),
test AS (
  SELECT q.id AS query_id, i.idcg FROM queries q JOIN ideal i ON i.query_id = q.id
   WHERE q.split = 'test'
),
dcg AS (
  SELECT r.k, r.query_id, sum(j.relevance / log(2, r.rank + 1.0)) AS dcg
    FROM ranked r JOIN qrels j ON j.query_id = r.query_id AND j.doc_id = r.doc_id
   WHERE r.rank <= 10
   GROUP BY r.k, r.query_id
)
SELECT ks.k, t.query_id, coalesce(d.dcg, 0) / t.idcg AS ndcg10
  FROM ks CROSS JOIN test t
  LEFT JOIN dcg d ON d.k = ks.k AND d.query_id = t.query_id
"""


def sweep(conn, keyword: str, vector: str) -> dict[int, dict[str, float]]:
    """NDCG@10 per k per test question for RRF over two stored lists."""
    scores: dict[int, dict[str, float]] = {}
    params = {"ks": list(KS), "keyword": keyword, "vector": vector}
    for k, query_id, ndcg in conn.execute(SWEEP_SQL, params):
        scores.setdefault(k, {})[query_id] = float(ndcg)
    return scores


def stored(conn, stage: str) -> float:
    """Mean NDCG@10 of a stored arm, from sql/10_scoreboard.sql's question_scores."""
    row = conn.execute(
        "SELECT avg(ndcg10) FROM question_scores WHERE stage = %s", (stage,)
    ).fetchone()
    return float(row[0])


# %%
results: dict[str, dict[str, dict[int, float]]] = {}
for name in DATASETS:
    conn = connect(name)
    for label, (keyword, vector, rrf_stage) in PAIRS.items():
        by_k = {k: 100 * mean(v.values()) for k, v in sweep(conn, keyword, vector).items()}
        reference = 100 * stored(conn, rrf_stage)
        if abs(by_k[60] - reference) > 1e-9:
            raise AssertionError(
                f"{name} {label}: k = 60 gives {by_k[60]:.4f}, stored {rrf_stage} is "
                f"{reference:.4f}; the recomputation does not match the arm."
            )
        results.setdefault(label, {})[name] = by_k
    conn.close()
    print(name, "checked against the stored RRF arms")

# %%
lines = [
    "# RRF k sensitivity",
    "",
    "NDCG@10 of equal-weight RRF on each dataset's test questions, recomputed from the stored",
    "top-50 lists at each k. k = 60 reproduces the evaluated RRF arms exactly. Sensitivity only:",
    "no k was chosen on these questions.",
    "",
]
for label, per_dataset in results.items():
    lines += [f"## {label}", "", "| k | " + " | ".join(per_dataset) + " |",
              "| ---: | " + " | ".join("---:" for _ in per_dataset) + " |"]
    for k in KS:
        lines.append(f"| {k} | " + " | ".join(f"{v[k]:.1f}" for v in per_dataset.values()) + " |")
    spread = " | ".join(f"{max(v.values()) - min(v.values()):.1f}" for v in per_dataset.values())
    lines += [f"| spread | {spread} |", ""]
text = "\n".join(lines)
(LAB_ROOT / "results" / "k_sweep.md").write_text(text)
print(text)
