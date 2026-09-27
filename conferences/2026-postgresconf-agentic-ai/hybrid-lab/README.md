# Hybrid search lab

Hybrid search in PostgreSQL 18, measured instead of asserted. Full-text search, pgvector,
BM25 (pg_textsearch), Reciprocal Rank Fusion in one SQL statement, and a reranker, each graded
on the 648 test questions of [FiQA-2018](https://sites.google.com/view/fiqa), a financial
Q&A benchmark whose questions come with human judgments of the right answers.

Companion to **Hybrid Search in PostgreSQL: Combining Vector and Full-Text for Real-World
Applications**, Postgres Summit US 2026, New York City.

## What it found

Every arm, all 648 FiQA test questions (full table: [`results/scoreboard.md`](results/scoreboard.md)):

| Arm | NDCG@10 | Recall@50 | p50 |
| --- | ---: | ---: | ---: |
| **Vector** (Cohere Embed v4, HNSW) | **54.0** | 78.9 | 3.9 ms |
| Vector, `halfvec` index / binary + rescore | 54.0 / 53.9 | 78.9 / 78.3 | 3.9 / 3.3 ms |
| RRF (`ts_rank_cd` + vector) + Cohere Rerank 3.5 | 51.4 | 72.7 | 1,079 ms |
| Vector + Cohere Rerank 3.5 | 50.0 | 78.9 | 425 ms |
| RRF (BM25 + vector) | 41.3 | 75.7 | 9.7 ms |
| RRF (`ts_rank_cd` + vector) | 33.8 | 72.7 | 158 ms |
| BM25 (pg_textsearch) | 23.6 | 47.1 | 5.2 ms |
| Pitfall: adding keyword and cosine scores | 5.6 | 16.0 | 145 ms |
| Pitfall: every word must match | 4.3 | 6.7 | 0.5 ms |
| Pitfall: any word, ranked with `ts_rank_cd` | 2.8 | 14.6 | 175 ms |

On this paraphrase-heavy benchmark, one vector query beat every hybrid and reranked
variant. Keyword search still wins individual questions with exact identifiers ("Employer
rollover from 403b to 401k?": BM25 #1, vector #26), and it is the right tool for "similar AND
contains this word" (`sql/09`, `sql/11`). The point of the lab is the harness: run it on your
own questions before deciding. Latency is one laptop and one client; rerank rows include
Bedrock calls made 8 at a time.


## What you need

- macOS with Homebrew (Linux works with `PG18_BIN` pointing at PostgreSQL 18)
- `brew install postgresql@18 pgvector uv`
- AWS credentials with Amazon Bedrock access to Cohere Embed v4 and Cohere Rerank 3.5 in
  us-east-1 (embedding the corpus once costs a few dollars)
- VS Code with SQLTools, the SQLTools PostgreSQL driver, Python, and Jupyter (the workspace
  recommends them)

## Set up (about 45 minutes, mostly embedding)

```bash
cd hybrid-lab
./scripts/setup.sh              # PostgreSQL 18 cluster on 127.0.0.1:5433, builds pg_textsearch
uv sync                         # Python environment
cp .env.example .env            # defaults work; set AWS_PROFILE if needed
uv run python py/1_load.py      # FiQA: 57,638 posts, 648 questions, 1,706 judgments (seconds)
uv run python py/2_embed.py     # Embed v4 on Bedrock, then VACUUM FULL and all indexes
uv run python py/4_evaluate.py  # every arm on every question -> results/scoreboard.md
uv run hybrid-lab               # UI at http://127.0.0.1:8018
```

`setup.sh` runs a project-owned cluster in `../.local/postgres18` and never touches other
PostgreSQL services. It builds pg_textsearch 1.4.0 into `../.local/extensions` and loads it
with PostgreSQL 18's `extension_control_path` and `dynamic_library_path`, so nothing is
installed into Homebrew's directories. It is safe to re-run.

If your shell exports `PGUSER`, `PGPASSWORD`, `PGHOST`, or `PGDATABASE`, the scripts ignore
them; the Python code always uses `DATABASE_URL`.

Embedding 7.7 million words hits Bedrock's tokens-per-minute quota. `py/2_embed.py` waits
out throttling and only embeds rows that are still NULL, so an interrupted run resumes.

## Walk through it in VS Code

Open this folder in VS Code. Run `py/3_ask.py` cells (Shift+Enter) to choose a question:
a FiQA test question is graded against its known answers; a typed question is embedded
live and is unjudged. Every file in `sql/` reads that question through the `active_query`
view. Run a file with SQLTools (Cmd+E Cmd+E), or select one statement and run just that.

| File | Shows |
| --- | --- |
| `01_schema.sql` | One row holds the text, its generated `tsvector`, and a `vector(1536)` |
| `02_indexes.sql` | GIN, HNSW, pg_textsearch BM25, plus halfvec and binary expression indexes |
| `03_keyword_and.sql` | Pitfall: `websearch_to_tsquery` requires every word |
| `04_keyword_or.sql` | Any-word matching ranked with `ts_rank_cd` |
| `05_bm25.sql` | BM25 inside PostgreSQL with pg_textsearch |
| `06_vector.sql` | HNSW cosine search; `hnsw.ef_search` caps the result count |
| `07a_naive_sum.sql` | Pitfall: adding scores from different scales |
| `07b_concat_dedupe.sql` | Pitfall: stacking one list on the other is not fusion |
| `08a_hybrid_rrf.sql` | Reciprocal Rank Fusion in one statement |
| `08b_hybrid_rrf_bm25.sql` | The same fusion with BM25 as the keyword list |
| `09_filtered_hybrid.sql` | "Similar AND contains a keyword": filters, HNSW, iterative scans |
| `10_scoreboard.sql` | NDCG@10 and Recall@50 for every arm, computed in SQL |
| `11_hybrid_function.sql` | `hybrid_search()`: the take-home function |
| `12a_halfvec.sql`, `12b_binary.sql` | Half-precision and 1-bit indexes, measured |

Each arm file has a line `-- == ARM QUERY ==`. Statements above it are for exploring. The
query below it is what the evaluator and the UI execute, byte for byte.

## The UI

`uv run hybrid-lab` serves a single page at http://127.0.0.1:8018. Pick a question, choose
arms, and compare their top 10 side by side. Known answers get a green row and a letter
(A, B, C) that follows the post across columns; hover a row to highlight the same post
everywhere. Hybrid rows show each post's keyword and vector rank, and clicking one shows the
RRF arithmetic. Each column's SQL button shows the file it ran. The Scoreboard tab shows every
arm over all 648 questions and the questions where hybrid gained or lost most against vector.

Test questions work offline, including the rerank column, which uses the stored evaluation
run. Typed questions need Bedrock. Picking a question in the UI also makes it the active
question for SQLTools.

## Tests

```bash
uv run pytest -q                  # creates and uses a separate fiqa_test database
uv run ruff check src py tests
```

The tests use a 20-post fixture with hand-built embeddings whose cosine similarities are
known exactly. They check the AND/OR behavior, the RRF arithmetic, BM25 filtering, the SQL
NDCG against a Python reference, the `ef_search` cap, iterative scans, the API with Bedrock
mocked, and one browser run of the UI.

## Credits

- Dave Ebbelaar's [hybrid-retrieval tutorial](https://github.com/daveebbelaar/ai-cookbook/tree/main/knowledge/hybrid-retrieval)
  in ai-cookbook: the FiQA-plus-NDCG approach and the numbered-file structure that this lab
  moves into PostgreSQL.
- [BEIR](https://github.com/beir-cellar/beir) and FiQA-2018 for the benchmark.
- [pgvector](https://github.com/pgvector/pgvector) and
  [pg_textsearch](https://github.com/timescale/pg_textsearch).
- Cormack, Clarke and Büttcher, *Reciprocal Rank Fusion outperforms Condorcet and individual
  rank learning methods*, SIGIR 2009.
