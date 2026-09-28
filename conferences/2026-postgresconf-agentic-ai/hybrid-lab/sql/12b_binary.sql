-- 12b. Storage: one bit per dimension, then re-score with the full vector.
--
-- binary_quantize() keeps only the sign of each dimension: 1536 bits = 192 bytes
-- instead of 6 KB. Hamming distance (<~>) on bits is a coarse first pass, so we
-- take 4× the candidates from the bit index and re-order them by exact cosine
-- distance on the full vectors still stored in the table.

SELECT pg_column_size(embedding)                  AS vector_bytes,
       pg_column_size(embedding::halfvec(1536))   AS halfvec_bytes,
       pg_column_size(binary_quantize(embedding)) AS bit_bytes
  FROM docs
 WHERE embedding IS NOT NULL
 LIMIT 1;

-- == ARM QUERY ==
SET hnsw.ef_search = 200;
WITH candidates AS (
  SELECT d.id, d.body, d.embedding
    FROM docs d
   WHERE d.embedding IS NOT NULL
   ORDER BY binary_quantize(d.embedding)::bit(1536)
            <~> (SELECT binary_quantize(embedding) FROM active_query)
   LIMIT 200
),
rescored AS (
  SELECT id, body, embedding <=> (SELECT embedding FROM active_query) AS distance
    FROM candidates
   ORDER BY distance
   LIMIT 50
)
SELECT row_number() OVER (ORDER BY distance, id) AS rank,
       id AS doc_id,
       1 - distance AS score,
       left(body, 120) AS preview
  FROM rescored
 ORDER BY rank;
