# Hybrid search pitfalls, each with a check

Every item was reproduced on FiQA-2018 (57,638 posts) in the hybrid-lab that accompanies
this skill. Run the check against the user's schema and report pass or fail.

## 1. Every word must match

`websearch_to_tsquery` and `plainto_tsquery` join words with AND. A natural-language question
rarely has all of its words in one document, so recall collapses.

Fix: match any of the question's lexemes and let the ranking sort them out.

```sql
replace(plainto_tsquery('english', $1)::text, ' & ', ' | ')::tsquery
```

Check: for 20 sample questions, count matches with the AND query. If most return fewer than
the candidate depth, the keyword arm is starving RRF.

## 2. Adding raw scores

`ts_rank_cd` is unbounded and depends on term counts; cosine similarity for a given model sits
in a narrow band. `keyword_score + vector_score` lets whichever scale is larger decide.
Concatenating one result list after the other and removing duplicates is not fusion either;
the list appended first wins.

Fix: Reciprocal Rank Fusion, `score = Σ 1 / (k + rank)` with k = 60 over each list's top N
(missing from a list contributes 0), or better, a normalized blend: min-max each list's scores
per question, then `w · vector + (1 − w) · keyword` with w tuned on held-out questions
(`templates/hybrid_blend.sql`). In the talk's lab, with Cohere Embed v4, equal-weight RRF lost
to vector search on all four BEIR datasets tested (significantly on three). A blend tuned on
dev questions never lost; on the one dataset without dev questions, an untuned 0.5 blend lost
0.8 NDCG@10. With a small local model (bge-small), the tuned blend beat vector search on three
of four datasets.

Check: grep the search SQL for `+` between a text rank and a distance, or for UNION of the
two lists without a rank-based score.

## 3. `ts_rank_cd` is not BM25

`ts_rank` and `ts_rank_cd` score each document alone. They have no corpus statistics, so a
common word counts as much as a rare one (no IDF). BM25 needs document frequencies and
average length: pg_textsearch (PostgreSQL license, PG 17/18) provides a `bm25` index and the
`<@>` operator. `<@>` returns the negative score; documents with none of the terms score 0
and can still fill the LIMIT, so filter `score < 0`.

Check: is pg_textsearch available (`pg_available_extensions`)? If yes, evaluate both.

## 4. HNSW returns at most `ef_search` rows

`hnsw.ef_search` defaults to 40. `ORDER BY embedding <=> $1 LIMIT 50` silently returns 40.

Fix: `SET hnsw.ef_search` to at least the candidate depth (the lab uses 100 for 50), or set it
on the search function: `CREATE FUNCTION ... SET hnsw.ef_search = 100`.

Check: `SHOW hnsw.ef_search` in the application's session versus its candidate LIMIT.

## 5. Filters after an approximate index

With `WHERE tenant_id = $2 ORDER BY embedding <=> $1 LIMIT 50`, HNSW finds ~ef_search
neighbors first and filters afterwards, so a selective filter returns too few rows.

Fix: pgvector 0.8+ iterative scans: `SET hnsw.iterative_scan = relaxed_order` (bounded by
`hnsw.max_scan_tuples`, default 20,000). Relaxed order is safe inside RRF because ranks are
recomputed from distance. Also check the plan: for very selective filters the planner may
correctly prefer a B-tree or GIN index plus an exact sort.

Check: run the filtered query with iterative scan off and on; compare row counts and
`EXPLAIN (ANALYZE)`.

## 6. An ORDER BY the index cannot use

HNSW serves `ORDER BY <column> <op> <constant or parameter> LIMIT n`, ascending distance.
`ORDER BY 1 - (embedding <=> $1) DESC`, a distance computed in a join, or a non-constant
LIMIT can push the planner to a sequential scan and sort.

Fix: keep the operator expression (or its alias) in ORDER BY, ascending, with a literal or
parameter LIMIT; compute similarity for display after the LIMIT. Take the query vector from a
parameter or a scalar subquery, not from a joined row.

Check: `EXPLAIN` shows `Index Scan using <hnsw index>`.

## 7. Document and query input types mixed up

Asymmetric embedding models (Cohere Embed v4, E5, BGE with instructions) expect different
input types or prefixes for documents and for queries. Embedding questions as documents, or
the reverse, quietly lowers relevance.

Check: find the embedding calls; documents use the document type, questions the query type.

## 8. Different models or versions in one column

Vectors from two models are not comparable even when the dimension count matches. Re-embed
everything when changing model, dimension, or quantization, and record the model id.

Check: store the model id in a column or table comment; `SELECT DISTINCT` it.

## 9. Candidate depth hides answers from fusion

A document outside both top-N lists cannot be rescued by RRF or a reranker. Recall@50 is the
ceiling for anything that only reorders 50 candidates.

Check: report Recall@50 next to NDCG@10.

## 10. Optional filters that switch off the indexes

`WHERE (p_category IS NULL OR category = p_category)` inside a function is fine only when the
planner sees the argument's value. With a generic plan, or with the argument joined in through
a CTE, the OR survives and the planner falls back to sequential scans: in the lab, a
`hybrid_search()` with an optional keyword filter sorted all 57,600 distances instead of
walking HNSW, and took 197 ms instead of 73 ms (67 ms instead of 15 ms with the filter set).

Fix: reference parameters directly in WHERE and add `SET plan_cache_mode = force_custom_plan`
to the function, so every call is planned with its real arguments and `NULL IS NULL` folds
away. Alternatively, write separate queries for the filtered and unfiltered cases.

Check: `LOAD 'auto_explain'; SET auto_explain.log_min_duration = 0;
SET auto_explain.log_nested_statements = on; SET auto_explain.log_analyze = on;
SET auto_explain.log_level = notice;` then call the function and look for `Seq Scan` on the
table.
