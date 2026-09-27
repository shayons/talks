# FiQA scoreboard

648 FiQA-2018 test questions · PostgreSQL 18.6 · pgvector 0.8.6 · pg_textsearch 1.4.0
· Cohere Embed v4 (1536 dims) and Cohere Rerank 3.5 on Amazon Bedrock.
Latency is local laptop wall time per question; rerank rows include the Bedrock call.

| Arm | NDCG@10 | Recall@50 | p50 ms | p95 ms | Better / worse than Vector |
| --- | ---: | ---: | ---: | ---: | ---: |
| Vector | 54.0 | 78.9 | 3.9 | 5.1 | 0 / 0 |
| Vector · halfvec | 54.0 | 78.9 | 3.9 | 5.7 | 1 / 2 |
| Vector · binary + rescore | 53.9 | 78.3 | 3.3 | 4.9 | 4 / 5 |
| RRF · ts_rank_cd + Rerank | 51.4 | 72.7 | 1079.1 | 3669.7 | 163 / 228 |
| RRF · BM25 + Rerank | 50.7 | 75.7 | 1119.3 | 5973.2 | 158 / 239 |
| Vector + Rerank | 50.0 | 78.9 | 424.9 | 4902.4 | 160 / 242 |
| Vector ∪ BM25 + Rerank | 49.3 | 76.9 | 1036.1 | 5776.3 | 150 / 251 |
| RRF · BM25 | 41.3 | 75.7 | 9.7 | 12.1 | 98 / 329 |
| RRF · ts_rank_cd | 33.8 | 72.7 | 158.0 | 429.3 | 37 / 445 |
| BM25 | 23.6 | 47.1 | 5.2 | 7.3 | 39 / 442 |
| Score sum | 5.6 | 16.0 | 144.7 | 395.3 | 8 / 512 |
| Keyword · all words | 4.3 | 6.7 | 0.5 | 3.6 | 6 / 506 |
| Concatenate | 2.9 | 14.9 | 154.3 | 404.5 | 6 / 518 |
| Keyword · ts_rank_cd | 2.8 | 14.6 | 174.8 | 460.9 | 6 / 518 |
