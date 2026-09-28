# fiqa scoreboard

648 test questions · PostgreSQL 18.6 · pgvector 0.8.6 · pg_textsearch 1.4.0
· Cohere Embed v4 (1536 dims) and Cohere Rerank 3.5 on Amazon Bedrock
· BAAI/bge-small-en-v1.5 (384 dims) on this laptop for the small-model rows.
Latency is local laptop wall time per question; rerank rows include the Bedrock call.

| Arm | NDCG@10 | Recall@50 | p50 ms | p95 ms | Better / worse than Vector |
| --- | ---: | ---: | ---: | ---: | ---: |
| Embed v4 · binary + rescore | 54.1 | 78.5 | 3.3 | 4.1 | 11 / 11 |
| Tuned blend · Embed v4 | 53.9 | 78.5 | 8.7 | 11.1 | 0 / 0 |
| Vector · Embed v4 | 53.9 | 78.5 | 3.5 | 5.0 | 0 / 0 |
| Embed v4 · halfvec | 53.7 | 78.3 | 3.4 | 4.4 | 2 / 3 |
| Embed v4 · 1024 dims | 53.4 | 78.1 | 2.9 | 5.8 | 100 / 122 |
| Embed v4 · 512 dims | 51.8 | 77.2 | 2.2 | 3.4 | 112 / 177 |
| RRF · ts_rank_cd + Rerank | 51.2 | 72.6 | 1634.6 | 4654.1 | 161 / 230 |
| RRF · BM25 + Rerank | 50.4 | 75.2 | 1092.5 | 6060.6 | 157 / 239 |
| Tuned blend · Embed v4 256 dims | 49.9 | 72.6 | 7.2 | 9.6 | 104 / 214 |
| Embed v4 + Rerank | 49.7 | 78.5 | 416.5 | 5015.9 | 158 / 241 |
| Embed v4 · 256 dims | 49.3 | 73.4 | 1.7 | 2.7 | 100 / 237 |
| Embed v4 ∪ BM25 + Rerank | 49.0 | 76.5 | 1207.5 | 5664.4 | 148 / 248 |
| RRF · BM25 + Embed v4 | 41.3 | 75.2 | 8.2 | 10.2 | 98 / 325 |
| Tuned blend · bge-small | 39.2 | 62.3 | 7.3 | 9.4 | 86 / 342 |
| Vector · bge-small (local) | 38.0 | 59.8 | 2.0 | 3.1 | 81 / 344 |
| Tuned blend · ts_rank_cd + bge-small | 37.9 | 58.6 | 137.5 | 375.4 | 80 / 344 |
| RRF · BM25 + bge-small | 34.9 | 61.8 | 6.6 | 8.4 | 73 / 381 |
| RRF · ts_rank_cd + Embed v4 | 33.8 | 72.6 | 149.9 | 397.2 | 37 / 443 |
| BM25 | 23.6 | 47.1 | 5.2 | 7.2 | 38 / 440 |
| Score sum | 5.6 | 15.8 | 142.3 | 398.0 | 8 / 512 |
| Keyword · all words | 4.3 | 6.7 | 0.4 | 3.6 | 6 / 506 |
| Concatenate | 2.9 | 14.9 | 150.5 | 403.2 | 6 / 518 |
| Keyword · ts_rank_cd | 2.8 | 14.6 | 165.8 | 433.4 | 6 / 518 |
