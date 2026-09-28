-- 08c. A tuned blend: normalize each list's scores, then weight them.
--
-- RRF uses only ranks, so a list that is sure of its top hit counts the same as a list
-- that is guessing. A convex combination keeps that confidence:
--
--     min-max normalize each list's scores to [0, 1] for this question, then
--     score = w × vector + (1 − w) × bm25
--
-- (Bruch, Gai & Ingber, "An Analysis of Fusion Functions for Hybrid Retrieval", ACM TOIS
-- 2023.) This is the correct way to "add scores": pitfall 2 (07a) skipped both the
-- normalization and the weight.
--
-- w is chosen per dataset on held-out dev questions by py/5_tune_fusion.py and stored in
-- fusion_settings; it is never tuned on test questions. Datasets without a dev split
-- use 0.5.

SELECT name, value, note FROM fusion_settings;

-- == ARM QUERY ==
SET hnsw.ef_search = 100;
WITH settings AS (
  SELECT coalesce((SELECT value FROM fusion_settings WHERE name = 'blend_vector_weight'), 0.5)
           AS w
),
keyword AS (
  SELECT id, -neg_score AS score, row_number() OVER (ORDER BY neg_score, id) AS rank
    FROM (SELECT id,
                 body <@> to_bm25query((SELECT body FROM active_query), 'docs_body_bm25')
                   AS neg_score
            FROM docs
           ORDER BY neg_score
           LIMIT 50) hits
   WHERE neg_score < 0
),
semantic AS (
  SELECT id, 1 - distance AS score, row_number() OVER (ORDER BY distance, id) AS rank
    FROM (SELECT id, embedding <=> (SELECT embedding FROM active_query) AS distance
            FROM docs
           WHERE embedding IS NOT NULL
           ORDER BY distance
           LIMIT 50) nearest
),
keyword_norm AS (
  SELECT id, rank, CASE WHEN hi > lo THEN (score - lo) / (hi - lo) ELSE 1 END AS s
    FROM (SELECT *, min(score) OVER () AS lo, max(score) OVER () AS hi FROM keyword) k
),
semantic_norm AS (
  SELECT id, rank, CASE WHEN hi > lo THEN (score - lo) / (hi - lo) ELSE 1 END AS s
    FROM (SELECT *, min(score) OVER () AS lo, max(score) OVER () AS hi FROM semantic) v
),
fused AS (
  SELECT coalesce(k.id, v.id) AS id,
         k.rank AS keyword_rank,
         v.rank AS vector_rank,
         st.w * coalesce(v.s, 0) + (1 - st.w) * coalesce(k.s, 0) AS blend
    FROM keyword_norm k
    FULL OUTER JOIN semantic_norm v USING (id)
   CROSS JOIN settings st
)
SELECT row_number() OVER (ORDER BY f.blend DESC, f.id) AS rank,
       f.id AS doc_id,
       f.blend::float8 AS score,
       f.keyword_rank,
       f.vector_rank,
       left(d.body, 120) AS preview
  FROM fused f
  JOIN docs d USING (id)
 ORDER BY rank
 LIMIT 50;
