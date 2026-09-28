# Hybrid search lab

Hybrid search in PostgreSQL 18, measured instead of asserted. Full-text search, BM25
(pg_textsearch), pgvector, Reciprocal Rank Fusion and a tuned score blend in SQL, and a
reranker, each graded on 2,271 test questions from four [BEIR](https://github.com/beir-cellar/beir)
datasets whose questions come with human judgments of the right answers. Two embedding
models: Cohere Embed v4 on Amazon Bedrock, and bge-small-en-v1.5 running on the laptop.

Companion to **Hybrid Search in PostgreSQL: Combining Vector and Full-Text for Real-World
Applications**, Postgres Summit US 2026, New York City.

## What it found

NDCG@10 on each dataset's test questions. In parentheses: the difference from vector search
with the same embedding model, and its 95% paired bootstrap interval. **↑** / ↓ mark an
interval above / below zero. Full table: [`results/summary.md`](results/summary.md).

| Arm | FiQA | SciFact | NFCorpus | SCIDOCS |
| --- | ---: | ---: | ---: | ---: |
| BM25 (pg_textsearch) | 23.6 | 68.8 | 32.3 | 15.4 |
| **bge-small, local** | 38.0 | 72.0 | 33.8 | 19.6 |
| bge-small + BM25, tuned blend | **39.2** (+1.2 **↑**) | **74.2** (+2.1 **↑**) | **35.9** (+2.1 **↑**) | 19.8 (+0.2) * |
| bge-small + BM25, equal-weight RRF | 34.9 (−3.1 ↓) | 73.7 (+1.7) | 36.1 (+2.3 **↑**) | 19.4 (−0.3) |
| bge-small + `ts_rank_cd` (core PostgreSQL), tuned blend | 37.9 (−0.1) | 72.4 (+0.4) | 34.4 (+0.7) | 16.0 (−3.6 ↓) * |
| Embed v4, first 256 dims | 49.3 | 72.1 | 34.7 | 16.5 |
| Embed v4, first 256 dims + BM25, tuned blend | 49.9 (+0.5) | **75.5** (+3.5 **↑**) | **37.5** (+2.8 **↑**) | **18.4** (+1.9 **↑**) * |
| **Embed v4** | 53.9 | 77.5 | 40.1 | 20.6 |
| Embed v4 + BM25, tuned blend | 53.9 (0.0, chose w = 1) | 77.7 (+0.2) | 40.9 (+0.8 **↑**) | 19.8 (−0.8 ↓) * |
| Embed v4 + BM25, equal-weight RRF | 41.3 (−12.5 ↓) | 74.6 (−2.9 ↓) | 39.0 (−1.1) | 19.4 (−1.2 ↓) |
| Embed v4 + Cohere Rerank 3.5 | 49.7 (−4.1 ↓) | 77.1 (−0.4) | 38.2 (−1.9 ↓) | 20.2 (−0.4) |

\* SCIDOCS has no dev questions, so its blend weight is an untuned 0.5.

- **With a small local model, hybrid pays.** BM25 blended with bge-small beat bge-small alone
  on three of four datasets and closed 39% (SciFact) and 33% (NFCorpus) of the gap to Embed v4.
- **With a frontier model, equal-weight RRF does not.** It never beat Embed v4 alone and lost
  significantly on three datasets. A blend tuned on dev questions won once (NFCorpus) and on
  FiQA chose pure vector.
- **Without BM25, the keyword side adds almost nothing.** A blend with core PostgreSQL's
  `ts_rank_cd` (no IDF) gained nothing significant, and cost 137 ms p50 on FiQA.
- **RRF's k matters little.** From 5 to 200 it moved NDCG@10 by at most 4.3 (FiQA, Embed v4),
  1.4 elsewhere, and no k made equal-weight RRF beat Embed v4 alone
  ([`results/k_sweep.md`](results/k_sweep.md)).
- **The reranker never beat vector search** by more than noise on any dataset.
- **Quantize before you truncate.** Embed v4's shorter outputs are prefixes of its 1536
  vector, so `12c_dims_1024.sql` to `12e_dims_256.sql` search 1024, 512, and 256 dimensions of the stored column. 1024
  costs little but saves no HNSW space (one vector per 8 KB page either way); 512 and 256
  shrink the index 3× and 6× and lose 1.6 to 5.5 NDCG@10 on every dataset. `halfvec` and
  binary + rescore kept quality within noise ([`results/dimensions.md`](results/dimensions.md)).
- **BM25 pays more on weaker vectors, including fewer dimensions.** Embed v4 cut to 256
  dimensions plus BM25 (`08g_hybrid_blend_256.sql`) gained 1.9 to 3.5 NDCG@10 on three datasets and won back
  46–64% of what truncation cost.
- **Keyword search still earns its place** for exact identifiers ("Employer rollover from 403b
  to 401k?": BM25 #1, Embed v4 #26) and for "similar AND contains this word" (`sql/09`,
  `sql/11`).

The four ways hybrid search goes wrong, measured on FiQA's 648 questions (every method:
[`results/scoreboard-fiqa.md`](results/scoreboard-fiqa.md)):

| Pitfall | NDCG@10 | Fix | NDCG@10 |
| --- | ---: | --- | ---: |
| Every word must match (`websearch_to_tsquery`) | 4.3 | Any word, BM25 | 23.6 |
| Any word, ranked with `ts_rank_cd` (no IDF) | 2.8 | BM25 | 23.6 |
| Adding keyword and cosine scores | 5.6 | RRF of the same two lists | 33.8 |
| Stacking one list on the other | 2.9 | RRF of the same two lists | 33.8 |
| `WHERE` filter after an HNSW scan | 1 of 10 rows | `hnsw.iterative_scan = relaxed_order` | 10 of 10 |

Scope: public benchmarks with incomplete judgments, two embedding models and one reranker,
one laptop and one client. The datasets were chosen by a rule that favors keyword search.
Run the harness on your own questions before deciding.

## What you need

- macOS with Homebrew (Linux works with `PG18_BIN` pointing at PostgreSQL 18)
- `brew install postgresql@18 pgvector uv`
- AWS credentials with Amazon Bedrock access to Cohere Embed v4 and Cohere Rerank 3.5 in
  us-east-1 (embedding the corpus once costs a few dollars)
- VS Code with SQLTools, the SQLTools PostgreSQL driver, Python, and Jupyter (the workspace
  recommends them)

## Set up (FiQA: about 35 minutes of Bedrock embedding, plus about an hour for the local model)

```bash
cd hybrid-lab
./scripts/setup.sh              # PostgreSQL 18 cluster on 127.0.0.1:5433, builds pg_textsearch
uv sync --extra local           # Python environment (+ fastembed for the small local model)
cp .env.example .env            # defaults work; set AWS_PROFILE if needed
uv run python py/1_load.py      # FiQA: 57,638 posts, 648 test + 500 dev questions (seconds)
uv run python py/2_embed.py     # Embed v4 on Bedrock, then VACUUM FULL and all indexes
uv run --extra local python py/2b_embed_local.py   # bge-small on this laptop (optional)
uv run --extra local python py/5_tune_fusion.py     # blend weights, chosen on dev questions
uv run python py/4_evaluate.py  # every method on every test question -> results/
uv run hybrid-lab               # UI at http://127.0.0.1:8018
./scripts/preflight.sh          # later: start the database and UI, check everything
./scripts/postgres18.sh stop    # when you're done (start | stop | status)
```

### More datasets

The same schema and SQL files work for any BEIR dataset; each gets its own database. Besides
FiQA the lab supports three more, chosen before any measurement by one rule: under 30,000
documents, and BM25 beat every dense retriever in the BEIR paper.

```bash
for d in scifact nfcorpus scidocs; do
  LAB_DB=$d ./scripts/setup.sh
  LAB_DATASET=$d uv run python py/1_load.py
  LAB_DATASET=$d uv run python py/2_embed.py
  LAB_DATASET=$d uv run --extra local python py/2b_embed_local.py
done
./scripts/evaluate_all.sh       # clean rebuild, tune on dev, evaluate on test, results/summary.md
```

The UI serves every dataset whose database exists; pick one in the header.

## Walk through it in VS Code

Open this folder in VS Code. Run `py/3_ask.py` cells (Shift+Enter) to choose a question:
a FiQA test question is graded against its known answers; a typed question is embedded
live and is unjudged. Every file in `sql/` reads that question through the `active_query`
view. Run a file with SQLTools (Cmd+E Cmd+E), or select one statement and run just that.

| File | Shows |
| --- | --- |
| `01_schema.sql` | One row holds the text, its generated `tsvector`, and one vector column per model |
| `02_indexes.sql` | GIN, HNSW, pg_textsearch BM25, plus halfvec and binary expression indexes |
| `03_keyword_and.sql` | Pitfall: `websearch_to_tsquery` requires every word |
| `04_keyword_or.sql` | Any-word matching ranked with `ts_rank_cd` |
| `05_bm25.sql` | BM25 inside PostgreSQL with pg_textsearch |
| `06_vector.sql` | HNSW cosine search; `hnsw.ef_search` caps the result count |
| `07a_naive_sum.sql` | Pitfall: adding scores from different scales |
| `07b_concat_dedupe.sql` | Pitfall: stacking one list on the other is not fusion |
| `08a_hybrid_rrf.sql` | Reciprocal Rank Fusion in one statement |
| `08b_hybrid_rrf_bm25.sql` | The same fusion with BM25 as the keyword list |
| `08c_hybrid_blend.sql` | A normalized score blend, its weight tuned on dev questions |
| `06b_vector_local.sql`, `08d_hybrid_rrf_local.sql`, `08e_hybrid_blend_local.sql` | Vector, RRF, and blend with the small local model's column |
| `08f_hybrid_blend_native_local.sql` | The blend with core PostgreSQL's `ts_rank_cd` instead of BM25 |
| `09_filtered_hybrid.sql` | "Similar AND contains a keyword": filters, HNSW, iterative scans |
| `10_scoreboard.sql` | NDCG@10 and Recall@50 for every method, computed in SQL |
| `11_hybrid_function.sql` | `hybrid_search()`: the take-home function |
| `12a_halfvec.sql`, `12b_binary.sql` | Half-precision and 1-bit indexes, measured |
| `12c_dims_1024.sql`, `12d_dims_512.sql`, `12e_dims_256.sql` | Embed v4's first 1024, 512, and 256 dimensions, through `subvector()` indexes |
| `08g_hybrid_blend_256.sql` | The tuned blend with Embed v4's first 256 dimensions |
| `demo_questions.sql` | The stage questions the UI lists, per dataset |

Each arm file has a line `-- == ARM QUERY ==`. Statements above it are for exploring. The
query below it is what the evaluator and the UI execute, byte for byte.

## The UI

`uv run hybrid-lab` serves a single page at http://127.0.0.1:8018. Pick a question, choose
a dataset in the header, pick a question, choose methods, and compare their top 10 side by side,
one card per method. Known answers get a green row and a letter (A, B, C) that follows the
document across cards; hover a row to highlight the same document everywhere. The card with
the single highest NDCG@10 is outlined in green and marked Highest. Hybrid rows show each
document's keyword and vector rank, and clicking an RRF row shows the arithmetic. Each
column's SQL button shows the file it ran. The Scoreboard tab shows every method over the
dataset's test questions, the cross-dataset summary, and the questions where BM25 helped or
hurt the small model most. Links keep the dataset and question (`#d=nfcorpus&q=PLAIN-307`).

Test questions work offline, including the Embed v4 and rerank columns, which use stored
embeddings and the stored evaluation run. Typed questions need Bedrock (and the `local` extra
for the bge-small columns). Picking a question in the UI also makes it the active question
for SQLTools in that dataset's database.

## Tests

```bash
uv run --extra local pytest -q   # creates and uses a separate fiqa_test database
uv run ruff check src py tests
```

The tests use a 20-post fixture with hand-built embeddings whose cosine similarities are
known exactly. They check the AND/OR behavior, the RRF arithmetic, the blend against a Python
reference, BM25 filtering, the SQL NDCG against a Python reference, the `ef_search` cap,
iterative scans, the local-model arms, the API with Bedrock mocked, and the UI in a browser.

## Credits

- Dave Ebbelaar's [hybrid-retrieval tutorial](https://github.com/daveebbelaar/ai-cookbook/tree/main/knowledge/hybrid-retrieval)
  in ai-cookbook: the FiQA-plus-NDCG approach and the numbered-file structure that this lab
  moves into PostgreSQL.
- [BEIR](https://github.com/beir-cellar/beir) (Thakur et al., NeurIPS 2021) for FiQA-2018,
  SciFact, NFCorpus and SCIDOCS.
- [bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) (BAAI, MIT license) through
  [fastembed](https://github.com/qdrant/fastembed).
- [pgvector](https://github.com/pgvector/pgvector) and
  [pg_textsearch](https://github.com/timescale/pg_textsearch).
- Cormack, Clarke and Büttcher, *Reciprocal Rank Fusion outperforms Condorcet and individual
  rank learning methods*, SIGIR 2009.
- Bruch, Gai and Ingber, *An Analysis of Fusion Functions for Hybrid Retrieval*, ACM TOIS 2023:
  the normalized convex combination in `08c_hybrid_blend.sql`.
