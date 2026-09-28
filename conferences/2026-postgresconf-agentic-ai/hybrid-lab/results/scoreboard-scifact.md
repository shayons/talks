# scifact scoreboard

300 test questions · PostgreSQL 18.6 · pgvector 0.8.6 · pg_textsearch 1.4.0
· Cohere Embed v4 (1536 dims) and Cohere Rerank 3.5 on Amazon Bedrock
· BAAI/bge-small-en-v1.5 (384 dims) on this laptop for the small-model rows.
Latency is local laptop wall time per question; rerank rows include the Bedrock call.

| Arm | NDCG@10 | Recall@50 | p50 ms | p95 ms | Better / worse than Vector |
| --- | ---: | ---: | ---: | ---: | ---: |
| RRF · ts_rank_cd + Rerank | 78.0 | 96.0 | 1065.1 | 5647.9 | 46 / 46 |
| RRF · BM25 + Rerank | 77.9 | 96.3 | 1196.0 | 5137.2 | 48 / 47 |
| Tuned blend · Embed v4 | 77.7 | 96.3 | 9.7 | 11.5 | 36 / 33 |
| Embed v4 ∪ BM25 + Rerank | 77.6 | 96.4 | 1177.2 | 5477.0 | 46 / 47 |
| Vector · Embed v4 | 77.5 | 95.3 | 3.1 | 3.8 | 0 / 0 |
| Embed v4 · binary + rescore | 77.5 | 95.3 | 2.4 | 2.9 | 0 / 0 |
| Embed v4 · halfvec | 77.5 | 95.3 | 24.3 | 26.4 | 0 / 0 |
| Embed v4 + Rerank | 77.1 | 95.3 | 379.3 | 693.0 | 44 / 47 |
| RRF · BM25 + Embed v4 | 74.6 | 96.3 | 9.6 | 11.6 | 37 / 53 |
| Tuned blend · bge-small | 74.2 | 94.8 | 8.1 | 10.0 | 36 / 61 |
| RRF · BM25 + bge-small | 73.7 | 94.8 | 7.5 | 9.0 | 41 / 66 |
| Vector · bge-small (local) | 72.0 | 92.8 | 2.0 | 2.7 | 31 / 69 |
| BM25 | 68.8 | 89.0 | 6.4 | 8.6 | 36 / 91 |
| RRF · ts_rank_cd + Embed v4 | 63.2 | 96.0 | 36.7 | 92.5 | 26 / 120 |
| Score sum | 45.1 | 70.6 | 35.5 | 88.4 | 12 / 180 |
| Concatenate | 33.0 | 70.4 | 38.0 | 95.7 | 7 / 216 |
| Keyword · ts_rank_cd | 33.0 | 70.4 | 35.9 | 94.1 | 7 / 216 |
| Keyword · all words | 7.2 | 7.3 | 0.2 | 0.3 | 1 / 251 |
