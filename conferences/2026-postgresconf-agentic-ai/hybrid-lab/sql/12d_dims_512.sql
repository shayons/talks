-- 12d · Dimensions: Cohere Embed v4 cut to its first 512 of 1536 dimensions.
--
-- Embed v4 is trained so that a prefix of its vector is itself an embedding: asking
-- Bedrock for output_dimension = 512 returns these same 512 numbers (checked against
-- the API). So one stored 1536-dimension column can be searched at any smaller size, with no
-- re-embedding: an expression index covers the prefix (02_indexes.sql), and the query uses
-- the same expression. Cosine distance ignores vector length, so no renormalization.

SELECT pg_size_pretty(pg_relation_size('docs_embedding_hnsw'))      AS hnsw_1536,
       pg_size_pretty(pg_relation_size('docs_embedding_512_hnsw')) AS hnsw_512;

-- == ARM QUERY ==
SET hnsw.ef_search = 100;
WITH nearest AS (
  SELECT d.id, d.body,
         subvector(d.embedding, 1, 512)::vector(512)
           <=> (SELECT subvector(embedding, 1, 512)::vector(512) FROM active_query)
           AS distance
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
