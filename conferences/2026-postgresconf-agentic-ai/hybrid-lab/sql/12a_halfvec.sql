-- 12a. Storage: the same embedding indexed at half precision (halfvec).
--
-- vector(1536) stores 4 bytes per dimension; halfvec(1536) stores 2. Here the
-- table keeps full precision and only the index uses halfvec, through an
-- expression index (created in 02_indexes.sql). The query must use the same
-- expression so the planner can match it to the index.

SELECT pg_size_pretty(pg_relation_size('docs_embedding_hnsw'))         AS vector_hnsw,
       pg_size_pretty(pg_relation_size('docs_embedding_halfvec_hnsw')) AS halfvec_hnsw,
       pg_size_pretty(pg_relation_size('docs_embedding_bit_hnsw'))     AS bit_hnsw;

-- == ARM QUERY ==
SET hnsw.ef_search = 100;
WITH nearest AS (
  SELECT d.id, d.body,
         d.embedding::halfvec(1536)
           <=> (SELECT embedding::halfvec(1536) FROM active_query) AS distance
    FROM docs d
   WHERE d.embedding IS NOT NULL
   ORDER BY distance
   LIMIT 50
)
SELECT row_number() OVER (ORDER BY distance, id) AS rank,
       id AS doc_id,
       1 - distance AS score,
       left(body, 120) AS preview
  FROM nearest
 ORDER BY rank;
