# %% [markdown]
# # 4 · Grade every arm on all 648 FiQA test questions
#
# Each SQL arm runs its file's `-- == ARM QUERY ==` section once per question to warm
# the cache, then again for timing. The rerank arms send each question's stored
# hybrid top 50 to Cohere Rerank on Bedrock. Results land in `runs` and `run_timings`;
# sql/10_scoreboard.sql turns them into NDCG@10 and Recall@50.

# %%
from hybrid_lab.arms import BY_STAGE
from hybrid_lab.db import connect
from hybrid_lab.evaluate import run_all, scoreboard, write_scoreboard_markdown

conn = connect()
run_all(conn)  # or run_all(conn, stages=["vector", "rrf"]) to redo a few

# %%
rows = scoreboard(conn)
labels = {stage: arm.label for stage, arm in BY_STAGE.items()}
print(write_scoreboard_markdown(rows, labels))

# %% [markdown]
# ## Where the arms disagree
#
# Candidates for stage questions, by per-question NDCG@10 margin. Short questions read
# better on a projector. Pick one per row type and store it in `demo_questions`.

# %%
CANDIDATES_SQL = """
WITH p AS (
  SELECT query_id,
         max(ndcg10) FILTER (WHERE stage = 'keyword_or') AS keyword,
         max(ndcg10) FILTER (WHERE stage = 'bm25')       AS bm25,
         max(ndcg10) FILTER (WHERE stage = 'vector')     AS vector,
         max(ndcg10) FILTER (WHERE stage = 'rrf')        AS rrf,
         max(ndcg10) FILTER (WHERE stage = 'rrf_rerank') AS rerank
    FROM question_scores
   GROUP BY query_id
),
c AS (
  SELECT 'keyword wins' AS kind, query_id, greatest(keyword, bm25) - vector AS margin FROM p
  UNION ALL
  SELECT 'vector wins', query_id, vector - greatest(keyword, bm25) FROM p
  UNION ALL
  SELECT 'hybrid beats both', query_id, rrf - greatest(keyword, vector) FROM p
  UNION ALL
  SELECT 'rerank rescues', query_id, rerank - rrf FROM p
)
SELECT kind, query_id, round(margin, 2) AS margin, length(q.body) AS chars, q.body
  FROM (SELECT *, row_number() OVER (PARTITION BY kind ORDER BY margin DESC,
                                     length((SELECT body FROM queries WHERE id = query_id)))
                    AS n
          FROM c WHERE margin > 0) ranked
  JOIN queries q ON q.id = ranked.query_id
 WHERE n <= 8
 ORDER BY kind, n
"""
for row in conn.execute(CANDIDATES_SQL):
    print(row)
conn.rollback()
