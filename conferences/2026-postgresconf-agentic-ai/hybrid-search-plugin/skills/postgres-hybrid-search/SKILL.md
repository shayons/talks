---
name: postgres-hybrid-search
description: Add hybrid search to an existing PostgreSQL table (full-text tsvector + pgvector, fused with Reciprocal Rank Fusion in SQL) and prove whether it helps with an NDCG@10 evaluation on the user's own data. Use when someone wants keyword plus semantic search in Postgres, asks about pgvector with tsvector, RRF, BM25 or pg_textsearch in Postgres, or wants to measure search quality before changing it.
---

# PostgreSQL hybrid search

Add keyword + vector retrieval to one table, fuse the two rankings with RRF in a single SQL
statement, and grade it against known answers. Everything runs in the user's database; the
only external calls are embeddings (and optionally a reranker and a question writer).

The worked example, with measured results on 57,638 FiQA posts, is the hybrid-lab in the
same repository as this skill. Use its numbers only as an illustration; always measure on the
user's data.

## Ground rules

- **Show before you run.** Print every DDL statement and every backfill plan, then wait for
  the user's explicit go-ahead. Never run DDL against a database the user has not confirmed
  is safe to change. Recommend a staging copy for anything with production traffic.
- **Measure, don't assume.** Hybrid is not guaranteed to beat vector-only. Report what the
  evaluation shows, including when a simpler arm wins.
- **One embedding model per column.** Documents and queries must come from the same model
  and version, with the model's document/query input types used correctly.
- Read `references/pitfalls.md` before writing any search SQL. Load `references/providers.md`
  when choosing embeddings, and `references/evaluation.md` before step 6.

## Workflow

### 1. Inspect

Run `scripts/check_env.py` (PEP 723; `uv run scripts/check_env.py --table <schema.table>`)
with the user's `DATABASE_URL`. It reports the PostgreSQL version, whether `vector` and
`pg_textsearch` are available or installed, the table's columns, estimated row count,
existing indexes, and three sample rows. Stop and explain if PostgreSQL is older than 13 or
pgvector older than 0.8 (iterative index scans need 0.8).

### 2. Decide with the user

Ask, one at a time, only what the inspection could not answer:

1. Which text columns describe a row, and which matter most (they get weight A vs B/C/D).
2. Which filters real queries need (tenant, category, price, date). They go inside both
   candidate lists, before the LIMIT.
3. Embedding provider and dimensions (default: Cohere Embed v4 on Amazon Bedrock, 1536).
   See `references/providers.md` for OpenAI and local fastembed alternatives.
4. Keyword ranking: native `ts_rank_cd` (works everywhere, including RDS and Aurora) or
   pg_textsearch BM25 if the extension is available on their platform.

### 3. Migrate

Fill `templates/migration.sql` (placeholders are `{{like_this}}`). It adds a generated,
weighted `tsvector` column (any number of columns per weight tier A to D; `text[]` columns
go through the IMMUTABLE wrapper it defines) with a GIN index, and a `vector(<dims>)` column.
Build the HNSW index **after** the backfill. For large tables use `CREATE INDEX CONCURRENTLY`, raise
`maintenance_work_mem` for the session, and warn that adding a stored generated column
rewrites the table under an ACCESS EXCLUSIVE lock. Show the filled file; run it only after
confirmation.

### 4. Backfill embeddings

Fill and run `templates/backfill_embeddings.py`. It embeds rows where the vector is NULL in
resumable batches with the provider's document input type, waits out throttling, and never
sends blank text. Then run the HNSW part of the migration.

### 5. Search function

Fill `templates/hybrid_search.sql`: a `<table>_hybrid_search()` SQL function with any-word
keyword matching, cosine HNSW candidates, RRF (k = 60, candidate depth 50), explicit
`hnsw.ef_search`, and `hnsw.iterative_scan = relaxed_order` for filtered queries. Keep the
user's filters in both candidate lists. Then run `templates/try_search.py` with two or three
of the user's real questions: it embeds them with the query input type, calls the function,
and prints each row's RRF score with its keyword and vector rank.

### 6. Evaluate

Fill and run `templates/evaluate.py`. With labeled queries (CSV of query, relevant id), use
them. Without labels, it asks an LLM to write one realistic question per sampled row (that
row is the known answer), embeds the questions with the query input type, runs keyword,
vector, RRF and optional rerank arms, and scores them with `templates/scoreboard.sql`
(NDCG@10, Recall@50, p50 latency). Explain the synthetic-question bias from
`references/evaluation.md` when reporting.

### 7. Report

Show the scoreboard and a pass/fail line for each check in `references/pitfalls.md`:
every-word matching, raw score mixing, `ef_search` below the candidate depth, filtered HNSW
without iterative scans, non-indexable ORDER BY, document/query input-type mix-ups,
mismatched embedding model versions, and optional filters that force sequential scans
(confirm the function's inner plan with `auto_explain`, as the reference shows). Recommend
the simplest arm that performs within noise of the best, and say what would change that
recommendation.

### 8. Record it for future agents (ask first)

Offer to add `templates/agents-section.md`, filled in, to the project's `AGENTS.md`. If the
project has only a `CLAUDE.md`, add it there instead. If it has neither, create `AGENTS.md`
with the section and a `CLAUDE.md` containing the single line `@AGENTS.md`.
