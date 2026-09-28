# nfcorpus scoreboard

323 test questions · PostgreSQL 18.6 · pgvector 0.8.6 · pg_textsearch 1.4.0
· Cohere Embed v4 (1536 dims) and Cohere Rerank 3.5 on Amazon Bedrock
· BAAI/bge-small-en-v1.5 (384 dims) on this laptop for the small-model rows.
Latency is local laptop wall time per question; rerank rows include the Bedrock call.

| Arm | NDCG@10 | Recall@50 | p50 ms | p95 ms | Better / worse than Vector |
| --- | ---: | ---: | ---: | ---: | ---: |
| Tuned blend · Embed v4 | 40.9 | 30.8 | 25.1 | 27.4 | 94 / 84 |
| Vector · Embed v4 | 40.1 | 31.2 | 17.7 | 19.3 | 0 / 0 |
| Embed v4 · halfvec | 40.1 | 31.2 | 17.6 | 18.7 | 1 / 0 |
| Embed v4 · binary + rescore | 39.8 | 31.0 | 2.4 | 2.9 | 3 / 1 |
| RRF · BM25 + Embed v4 | 39.0 | 30.2 | 25.0 | 26.5 | 88 / 118 |
| Embed v4 + Rerank | 38.2 | 31.2 | 406.6 | 913.0 | 97 / 122 |
| RRF · ts_rank_cd + Rerank | 38.1 | 29.6 | 920.0 | 6489.7 | 97 / 125 |
| RRF · BM25 + Rerank | 37.9 | 30.2 | 980.1 | 6442.3 | 96 / 126 |
| Embed v4 ∪ BM25 + Rerank | 37.2 | 30.6 | 1162.7 | 5512.3 | 93 / 130 |
| RRF · ts_rank_cd + Embed v4 | 36.3 | 29.6 | 20.9 | 34.1 | 77 / 139 |
| RRF · BM25 + bge-small | 36.1 | 26.8 | 13.9 | 17.2 | 83 / 148 |
| Tuned blend · bge-small | 35.9 | 26.5 | 15.4 | 23.2 | 80 / 142 |
| Tuned blend · ts_rank_cd + bge-small | 34.4 | 25.6 | 9.5 | 22.8 | 72 / 153 |
| Vector · bge-small (local) | 33.8 | 25.9 | 7.1 | 8.2 | 69 / 162 |
| BM25 | 32.3 | 21.7 | 5.9 | 7.2 | 61 / 173 |
| Score sum | 30.4 | 25.3 | 33.4 | 44.8 | 49 / 164 |
| Concatenate | 26.2 | 24.2 | 20.4 | 32.7 | 45 / 185 |
| Keyword · ts_rank_cd | 23.8 | 18.8 | 1.7 | 16.1 | 41 / 202 |
| Keyword · all words | 20.5 | 10.0 | 0.2 | 0.5 | 37 / 197 |
