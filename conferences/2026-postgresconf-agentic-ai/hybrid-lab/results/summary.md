# Across datasets

NDCG@10 on each dataset's test questions. Hybrid rows show the difference from vector
search with the same embedding model and its 95% paired bootstrap interval. **↑** marks
an interval above zero; ↓ an interval below zero. Blend weights were tuned on each
dataset's dev questions (SCIDOCS has none, so its blends use 0.5).

| Arm | fiqa | scifact | nfcorpus | scidocs |
| --- | ---: | ---: | ---: | ---: |
| BM25 | 23.6 | 68.8 | 32.3 | 15.4 |
| Vector · Embed v4 | 53.9 | 77.5 | 40.1 | 20.6 |
| RRF · BM25 + Embed v4 | 41.3 (-12.5, -14.5…-10.6) ↓ | 74.6 (-2.9, -5.1…-0.6) ↓ | 39.0 (-1.1, -2.2…+0.1) | 19.4 (-1.2, -2.0…-0.5) ↓ |
| Tuned blend · Embed v4 | 53.9 (+0.0, +0.0…+0.0) | 77.7 (+0.2, -1.2…+1.4) | 40.9 (+0.8, +0.1…+1.5) **↑** | 19.8 (-0.8, -1.4…-0.2) ↓ |
| Embed v4 + Rerank | 49.7 (-4.1, -6.0…-2.3) ↓ | 77.1 (-0.4, -2.8…+1.9) | 38.2 (-1.9, -3.3…-0.4) ↓ | 20.2 (-0.4, -1.1…+0.3) |
| Vector · bge-small (local) | 38.0 | 72.0 | 33.8 | 19.6 |
| RRF · BM25 + bge-small | 34.9 (-3.1, -4.7…-1.5) ↓ | 73.7 (+1.7, -0.9…+4.3) | 36.1 (+2.3, +1.0…+3.7) **↑** | 19.4 (-0.3, -1.0…+0.5) |
| Tuned blend · bge-small | 39.2 (+1.2, +0.4…+2.1) **↑** | 74.2 (+2.1, +0.0…+4.3) **↑** | 35.9 (+2.1, +1.3…+3.0) **↑** | 19.8 (+0.2, -0.5…+0.8) |
