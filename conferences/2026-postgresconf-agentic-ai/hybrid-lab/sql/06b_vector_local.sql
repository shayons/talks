-- 06b. The same vector search with a small open-source model, run on this laptop.
--
-- BAAI/bge-small-en-v1.5: 384 dimensions, MIT license, embedded locally with fastembed
-- (py/2b_embed_local.py). Only the column changes: embedding_local instead of embedding.
-- Its HNSW index is docs_embedding_local_hnsw.

-- == ARM QUERY ==
SET hnsw.ef_search = 100;
WITH nearest AS (
  SELECT d.id, d.body,
         d.embedding_local <=> (SELECT embedding_local FROM active_query) AS distance
    FROM docs d
   WHERE d.embedding_local IS NOT NULL
   ORDER BY distance
   LIMIT 50
)
SELECT row_number() OVER (ORDER BY distance, id) AS rank,
       id AS doc_id,
       1 - distance AS score,
       left(body, 120) AS preview
  FROM nearest
 ORDER BY rank;
