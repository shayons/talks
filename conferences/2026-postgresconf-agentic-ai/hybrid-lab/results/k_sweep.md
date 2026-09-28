# RRF k sensitivity

NDCG@10 of equal-weight RRF on each dataset's test questions, recomputed from the stored
top-50 lists at each k. k = 60 reproduces the evaluated RRF arms exactly. Sensitivity only:
no k was chosen on these questions.

## BM25 + Embed v4

| k | fiqa | scifact | nfcorpus | scidocs |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 45.4 | 76.0 | 39.2 | 19.6 |
| 10 | 44.5 | 76.0 | 39.4 | 19.7 |
| 30 | 41.9 | 75.0 | 39.0 | 19.4 |
| 60 | 41.3 | 74.6 | 39.0 | 19.4 |
| 100 | 41.3 | 74.6 | 39.0 | 19.3 |
| 200 | 41.2 | 74.6 | 39.0 | 19.3 |
| spread | 4.3 | 1.4 | 0.4 | 0.4 |

## BM25 + bge-small

| k | fiqa | scifact | nfcorpus | scidocs |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 36.7 | 74.9 | 36.2 | 19.9 |
| 10 | 36.4 | 74.3 | 36.3 | 19.9 |
| 30 | 35.4 | 73.8 | 36.1 | 19.5 |
| 60 | 34.9 | 73.7 | 36.1 | 19.4 |
| 100 | 34.9 | 73.6 | 36.0 | 19.4 |
| 200 | 34.8 | 73.5 | 36.0 | 19.4 |
| spread | 1.9 | 1.4 | 0.3 | 0.5 |
