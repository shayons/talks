-- 10. Scoreboard: every arm graded against the dataset's human judgments, in SQL.
--
-- NDCG@10 (normalized discounted cumulative gain):
--   DCG  = Σ relevance / log2(rank + 1) over the top 10 results
--   IDCG = the same sum for the best possible ordering of that question's answers
--   NDCG = DCG / IDCG, from 0 (no answer in the top 10) to 1 (all answers first).
--   Averaged over every test question; a question with no results scores 0.
--
-- Recall@50: share of a question's relevant documents found anywhere in the top 50.
-- It is the ceiling for anything that only reorders those 50, like a reranker.
--
-- py/4_evaluate.py fills runs and run_timings, then runs this file. Latency is
-- measured on the client around each arm's SQL; rerank arms add the Bedrock call.
--
-- question_scores is materialized: grading every stored run takes seconds (SCIDOCS keeps
-- 900,000 rows of runs), and the UI reads it on every click. Re-running this file, as the
-- evaluator does after each run, rebuilds it.

DROP VIEW IF EXISTS scoreboard;
DROP MATERIALIZED VIEW IF EXISTS question_scores;

CREATE MATERIALIZED VIEW question_scores AS
WITH test_questions AS (
  SELECT id AS query_id FROM queries WHERE split = 'test'
),
ideal AS (
  SELECT query_id, sum(relevance / log(2, position + 1.0)) AS idcg
    FROM (SELECT query_id, relevance,
                 row_number() OVER (PARTITION BY query_id ORDER BY relevance DESC) AS position
            FROM qrels) ordered
   WHERE position <= 10
   GROUP BY query_id
),
relevant_counts AS (
  SELECT query_id, count(*) AS n_relevant FROM qrels GROUP BY query_id
)
SELECT s.stage,
       t.query_id,
       coalesce(sum(j.relevance / log(2, r.rank + 1.0)) FILTER (WHERE r.rank <= 10), 0)
         / i.idcg AS ndcg10,
       count(j.doc_id)::numeric / rc.n_relevant AS recall50
  FROM (SELECT DISTINCT stage FROM runs) s
 CROSS JOIN test_questions t
  JOIN ideal i ON i.query_id = t.query_id
  JOIN relevant_counts rc ON rc.query_id = t.query_id
  LEFT JOIN runs r ON r.stage = s.stage AND r.query_id = t.query_id
  LEFT JOIN qrels j ON j.query_id = r.query_id AND j.doc_id = r.doc_id
 GROUP BY s.stage, t.query_id, i.idcg, rc.n_relevant;

CREATE UNIQUE INDEX question_scores_stage_query ON question_scores (stage, query_id);

CREATE VIEW scoreboard AS
WITH versus_vector AS (
  SELECT a.stage,
         count(*) FILTER (WHERE a.ndcg10 > v.ndcg10) AS better_than_vector,
         count(*) FILTER (WHERE a.ndcg10 < v.ndcg10) AS worse_than_vector
    FROM question_scores a
    JOIN question_scores v ON v.query_id = a.query_id AND v.stage = 'vector'
   GROUP BY a.stage
),
latency AS (
  SELECT stage,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY elapsed_ms) AS p50_ms,
         percentile_cont(0.95) WITHIN GROUP (ORDER BY elapsed_ms) AS p95_ms
    FROM run_timings
   GROUP BY stage
)
SELECT q.stage,
       round(100 * avg(q.ndcg10), 1) AS ndcg_at_10,
       round(100 * avg(q.recall50), 1) AS recall_at_50,
       round(l.p50_ms::numeric, 1) AS p50_ms,
       round(l.p95_ms::numeric, 1) AS p95_ms,
       vv.better_than_vector,
       vv.worse_than_vector,
       count(*) AS questions
  FROM question_scores q
  LEFT JOIN latency l USING (stage)
  LEFT JOIN versus_vector vv USING (stage)
 GROUP BY q.stage, l.p50_ms, l.p95_ms, vv.better_than_vector, vv.worse_than_vector;

SELECT * FROM scoreboard ORDER BY ndcg_at_10 DESC, stage;
