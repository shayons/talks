# Embed v4 dimensions

Cohere Embed v4's first N dimensions, searched through expression indexes on the stored
1536-dimension column (the API's output_dimension returns the same prefix). NDCG@10 on each
dataset's test questions; the change is against the full 1536 with a 95% paired bootstrap
interval (↓: interval below zero). HNSW sizes are PostgreSQL relation sizes.

## fiqa

| Dims | Bytes per vector | HNSW index | NDCG@10 | Change | Recall@50 | p50 ms |
| ---: | ---: | ---: | ---: | --- | ---: | ---: |
| 1536 | 6,148 | 450 MB | 53.9 | baseline | 78.5 | 3.5 |
| 1024 | 4,104 | 450 MB | 53.4 | -0.4 (-1.3…+0.4) | 78.1 | 2.9 |
| 512 | 2,056 | 150 MB | 51.8 | -2.1 (-3.1…-1.0) ↓ | 77.2 | 2.2 |
| 256 | 1,032 | 75 MB | 49.3 | -4.5 (-5.8…-3.3) ↓ | 73.4 | 1.7 |

## scifact

| Dims | Bytes per vector | HNSW index | NDCG@10 | Change | Recall@50 |
| ---: | ---: | ---: | ---: | --- | ---: |
| 1536 | 6,148 | 40 MB | 77.5 | baseline | 95.3 |
| 1024 | 4,104 | 40 MB | 76.3 | -1.2 (-2.3…-0.2) ↓ | 95.0 |
| 512 | 2,056 | 14 MB | 74.8 | -2.7 (-4.4…-1.3) ↓ | 94.0 |
| 256 | 1,032 | 7 MB | 72.1 | -5.5 (-7.9…-3.1) ↓ | 92.0 |

## nfcorpus

| Dims | Bytes per vector | HNSW index | NDCG@10 | Change | Recall@50 |
| ---: | ---: | ---: | ---: | --- | ---: |
| 1536 | 6,148 | 28 MB | 40.1 | baseline | 31.2 |
| 1024 | 4,104 | 28 MB | 39.8 | -0.3 (-0.8…+0.3) | 31.1 |
| 512 | 2,056 | 9 MB | 38.1 | -2.1 (-3.3…-0.9) ↓ | 30.1 |
| 256 | 1,032 | 5 MB | 34.7 | -5.4 (-7.2…-3.8) ↓ | 26.0 |

## scidocs

| Dims | Bytes per vector | HNSW index | NDCG@10 | Change | Recall@50 |
| ---: | ---: | ---: | ---: | --- | ---: |
| 1536 | 6,148 | 200 MB | 20.6 | baseline | 38.9 |
| 1024 | 4,104 | 200 MB | 20.3 | -0.3 (-0.6…-0.0) ↓ | 38.4 |
| 512 | 2,056 | 67 MB | 19.0 | -1.6 (-2.1…-1.1) ↓ | 36.7 |
| 256 | 1,032 | 33 MB | 16.5 | -4.1 (-4.8…-3.4) ↓ | 32.2 |
