# Embedding providers

Pick one model per column and record its id. `templates/backfill_embeddings.py` and
`templates/evaluate.py` support all three providers below through `--provider`.

## Cohere Embed v4 on Amazon Bedrock (default)

- Model: `us.cohere.embed-v4:0` (cross-region profile; `cohere.embed-v4:0` in-region).
- Dimensions: 256, 512, 1024, or 1536 (`output_dimension`). Vectors are unit length, so
  cosine distance and inner product rank identically.
- Input types: `search_document` for rows, `search_query` for questions.
- Up to 96 texts per call. Blank strings are rejected: skip them.
- Accounts have tokens-per-minute quotas; expect `ThrottlingException: Too many tokens` on
  large backfills. Wait and retry the batch rather than failing the run. In the lab, 57,638
  posts (7.7M words) took about 35 minutes with 4 to 8 concurrent calls.
- Needs AWS credentials with `bedrock:InvokeModel` and model access in the region.

Rerank (optional): `cohere.rerank-v3-5:0` through `InvokeModel` with
`{"query", "documents", "top_n", "api_version": 2}`.

## OpenAI

- Model: `text-embedding-3-small` (1536) or `text-embedding-3-large` (3072; store as
  `halfvec(3072)` because HNSW on `vector` supports at most 2,000 dimensions).
- Symmetric: the same call for documents and questions.
- Needs `OPENAI_API_KEY`.

## Local: fastembed

- Model: `BAAI/bge-small-en-v1.5` (384) or `BAAI/bge-base-en-v1.5` (768). No network after
  the first model download; useful offline.
- CPU throughput on a laptop is low (the lab measured about 26 long posts per second for
  bge-small), so budget time for large tables.

## pgvector storage choices

| Type | Bytes per 1536 dims (measured) | HNSW limit | Notes |
| --- | ---: | ---: | --- |
| `vector` | 6,148 | 2,000 dims | Full precision |
| `halfvec` | 3,080 | 4,000 dims | Usually indistinguishable in ranking; measure it |
| `bit` via `binary_quantize()` | 200 | 64,000 dims | Re-score candidates with full vectors |

Index a cheaper type with an expression index while keeping the full vector in the table:
`CREATE INDEX ON t USING hnsw ((embedding::halfvec(1536)) halfvec_cosine_ops);` and query
with the same expression.
