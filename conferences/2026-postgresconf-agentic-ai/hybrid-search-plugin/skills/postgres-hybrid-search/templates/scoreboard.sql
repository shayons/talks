-- Scoreboard for hybrid_eval (written by evaluate.py): NDCG@10, Recall@50, p50/p95 latency.
--   DCG  = Σ relevance / log2(rank + 1) over the top 10
--   NDCG = DCG / best possible DCG for that question; a question with no results scores 0.
--   Recall@50 = share of a question's known answers anywhere in the top 50.

WITH ideal AS (
  SELECT question_id, sum(relevance / log(2, position + 1.0)) AS idcg
    FROM (SELECT question_id, relevance,
                 row_number() OVER (PARTITION BY question_id ORDER BY relevance DESC) AS position
            FROM hybrid_eval.qrels) ordered
   WHERE position <= 10
   GROUP BY question_id
),
relevant_counts AS (
  SELECT question_id, count(*) AS n_relevant FROM hybrid_eval.qrels GROUP BY question_id
),
per_question AS (
  SELECT a.arm, i.question_id,
         coalesce(sum(j.relevance / log(2, r.rank + 1.0)) FILTER (WHERE r.rank <= 10), 0)
           / i.idcg AS ndcg10,
         count(j.doc_id)::numeric / rc.n_relevant AS recall50
    FROM (SELECT DISTINCT arm FROM hybrid_eval.runs) a
   CROSS JOIN ideal i
    JOIN relevant_counts rc ON rc.question_id = i.question_id
    LEFT JOIN hybrid_eval.runs r ON r.arm = a.arm AND r.question_id = i.question_id
    LEFT JOIN hybrid_eval.qrels j ON j.question_id = r.question_id AND j.doc_id = r.doc_id
   GROUP BY a.arm, i.question_id, i.idcg, rc.n_relevant
),
latency AS (
  SELECT arm,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY elapsed_ms) AS p50_ms,
         percentile_cont(0.95) WITHIN GROUP (ORDER BY elapsed_ms) AS p95_ms
    FROM hybrid_eval.timings
   GROUP BY arm
)
SELECT p.arm,
       round(100 * avg(p.ndcg10), 1) AS ndcg_at_10,
       round(100 * avg(p.recall50), 1) AS recall_at_50,
       round(l.p50_ms::numeric, 1) AS p50_ms,
       round(l.p95_ms::numeric, 1) AS p95_ms,
       count(*) AS questions
  FROM per_question p
  LEFT JOIN latency l USING (arm)
 GROUP BY p.arm, l.p50_ms, l.p95_ms
 ORDER BY ndcg_at_10 DESC, p.arm;
