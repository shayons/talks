# scidocs scoreboard

1000 test questions · PostgreSQL 18.6 · pgvector 0.8.6 · pg_textsearch 1.4.0
· Cohere Embed v4 (1536 dims) and Cohere Rerank 3.5 on Amazon Bedrock
· BAAI/bge-small-en-v1.5 (384 dims) on this laptop for the small-model rows.
Latency is local laptop wall time per question; rerank rows include the Bedrock call.

| Arm | NDCG@10 | Recall@50 | p50 ms | p95 ms | Better / worse than Vector |
| --- | ---: | ---: | ---: | ---: | ---: |
| Vector · Embed v4 | 20.6 | 38.9 | 4.5 | 5.7 | 0 / 0 |
| Embed v4 · binary + rescore | 20.6 | 38.7 | 3.9 | 4.8 | 8 / 9 |
| Embed v4 · halfvec | 20.6 | 39.0 | 4.5 | 5.8 | 3 / 2 |
| RRF · ts_rank_cd + Rerank | 20.3 | 34.1 | 1619.5 | 4845.7 | 285 / 311 |
| Embed v4 · 1024 dims | 20.3 | 38.4 | 3.0 | 4.0 | 177 / 244 |
| Embed v4 + Rerank | 20.2 | 38.9 | 671.8 | 5424.2 | 281 / 318 |
| RRF · BM25 + Rerank | 19.9 | 37.2 | 949.6 | 6241.4 | 278 / 329 |
| Tuned blend · Embed v4 | 19.8 | 37.3 | 10.5 | 12.2 | 240 / 303 |
| Tuned blend · bge-small | 19.8 | 36.6 | 8.2 | 10.2 | 287 / 330 |
| Embed v4 ∪ BM25 + Rerank | 19.6 | 38.8 | 1100.7 | 5858.3 | 269 / 335 |
| Vector · bge-small (local) | 19.6 | 37.7 | 1.8 | 2.4 | 313 / 339 |
| RRF · BM25 + Embed v4 | 19.4 | 37.2 | 10.4 | 12.1 | 273 / 289 |
| RRF · BM25 + bge-small | 19.4 | 36.3 | 7.8 | 9.2 | 274 / 327 |
| Embed v4 · 512 dims | 19.0 | 36.7 | 2.4 | 3.6 | 201 / 312 |
| Tuned blend · Embed v4 256 dims | 18.4 | 33.7 | 7.8 | 9.8 | 226 / 339 |
| Embed v4 · 256 dims | 16.5 | 32.2 | 1.8 | 2.9 | 168 / 408 |
| Tuned blend · ts_rank_cd + bge-small | 16.0 | 33.4 | 123.0 | 319.8 | 213 / 427 |
| BM25 | 15.4 | 28.5 | 5.9 | 7.4 | 189 / 424 |
| RRF · ts_rank_cd + Embed v4 | 14.2 | 34.1 | 133.2 | 331.1 | 170 / 457 |
| Score sum | 5.1 | 13.6 | 129.7 | 328.0 | 46 / 587 |
| Concatenate | 3.2 | 13.6 | 133.1 | 331.7 | 32 / 604 |
| Keyword · ts_rank_cd | 3.2 | 13.6 | 149.6 | 377.0 | 32 / 604 |
| Keyword · all words | 0.5 | 0.5 | 0.4 | 0.6 | 4 / 619 |
