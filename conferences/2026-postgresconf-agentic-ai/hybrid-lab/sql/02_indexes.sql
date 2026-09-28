-- 02. Indexes: one table, three kinds of index.
-- Build after loading and embedding. py/2_embed.py runs this file and times each index.

-- HNSW keeps its graph in memory while it builds; 57,638 × 1536 dims fits in 1 GB.
SET maintenance_work_mem = '1GB';
SET max_parallel_maintenance_workers = 7;

-- Full-text: GIN maps every lexeme to the rows that contain it.
CREATE INDEX IF NOT EXISTS docs_tsv_gin ON docs USING gin (tsv);

-- Vectors: an HNSW graph for approximate nearest neighbors by cosine distance.
-- m and ef_construction are pgvector's defaults, written out so they are visible.
CREATE INDEX IF NOT EXISTS docs_embedding_hnsw ON docs
  USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- BM25: pg_textsearch stores corpus statistics (how many posts contain each term,
-- average post length), so rare terms weigh more. ts_rank_cd has no such statistics.
CREATE EXTENSION IF NOT EXISTS pg_textsearch;
CREATE INDEX IF NOT EXISTS docs_body_bm25 ON docs USING bm25 (body) WITH (text_config = 'english');

-- The small local model's vectors get their own index (py/2b_embed_local.py fills them).
CREATE INDEX IF NOT EXISTS docs_embedding_local_hnsw ON docs
  USING hnsw (embedding_local vector_cosine_ops);

-- Optional storage experiments (sql/12a, sql/12b): the same embedding indexed at
-- half precision and at one bit per dimension, as expression indexes.
CREATE INDEX IF NOT EXISTS docs_embedding_halfvec_hnsw ON docs
  USING hnsw ((embedding::halfvec(1536)) halfvec_cosine_ops);
CREATE INDEX IF NOT EXISTS docs_embedding_bit_hnsw ON docs
  USING hnsw ((binary_quantize(embedding)::bit(1536)) bit_hamming_ops);

-- Optional dimension experiments (sql/12c-12e): Embed v4's first 1024, 512, and 256
-- dimensions, which are what its output_dimension option returns, indexed as expressions.
CREATE INDEX IF NOT EXISTS docs_embedding_1024_hnsw ON docs
  USING hnsw ((subvector(embedding, 1, 1024)::vector(1024)) vector_cosine_ops);
CREATE INDEX IF NOT EXISTS docs_embedding_512_hnsw ON docs
  USING hnsw ((subvector(embedding, 1, 512)::vector(512)) vector_cosine_ops);
CREATE INDEX IF NOT EXISTS docs_embedding_256_hnsw ON docs
  USING hnsw ((subvector(embedding, 1, 256)::vector(256)) vector_cosine_ops);

ANALYZE docs;

SELECT indexrelid::regclass AS index_name,
       pg_size_pretty(pg_relation_size(indexrelid)) AS size
  FROM pg_index
 WHERE indrelid = 'docs'::regclass
 ORDER BY pg_relation_size(indexrelid) DESC;
