# SQL patterns from the talk

Copyable versions of the patterns on the slides. Every one runs, as written, in
[`hybrid-lab/sql/`](../hybrid-lab/sql/) against the FiQA table
`docs (id text, body text, tsv tsvector, embedding vector(1536))`, except the boost and
link-expansion patterns, which need columns (`published_at`, `likes`, `category`) and a
`links (src, dst)` table the lab doesn't have. Here `$1` is the question text and `$2` its
embedding (input type `search_query`).

## Match any word, not every word

```sql
-- websearch_to_tsquery / plainto_tsquery require ALL words: bad for questions.
SELECT id, ts_rank_cd(tsv, q) AS score
  FROM docs, CAST(replace(plainto_tsquery('english', $1)::text, ' & ', ' | ') AS tsquery) AS q
 WHERE tsv @@ q
 ORDER BY score DESC
 LIMIT 50;
```

`ts_rank_cd` scores every match before the LIMIT, and has no IDF. On common words that is
thousands of rows per question.

## BM25 with pg_textsearch

```sql
CREATE INDEX docs_body_bm25 ON docs USING bm25 (body) WITH (text_config = 'english');

SELECT id, -neg_score AS bm25
  FROM (SELECT id, body <@> to_bm25query($1, 'docs_body_bm25') AS neg_score
          FROM docs
         ORDER BY neg_score
         LIMIT 50) hits
 WHERE neg_score < 0;                     -- 0 means none of the query terms
```

Needs `shared_preload_libraries = 'pg_textsearch'`.

## Vector candidates that really return 50

```sql
SET hnsw.ef_search = 100;                 -- default 40 caps an HNSW scan at 40 rows
SELECT id, embedding <=> $2 AS distance
  FROM docs
 WHERE embedding IS NOT NULL
 ORDER BY embedding <=> $2                -- operator in ORDER BY, ascending
 LIMIT 50;
```

## Reciprocal Rank Fusion, weighted

```sql
WITH keyword AS (
  SELECT id, row_number() OVER (ORDER BY ts_rank_cd(tsv, q) DESC, id) AS rank
    FROM docs, CAST(replace(plainto_tsquery('english', $1)::text, ' & ', ' | ') AS tsquery) AS q
   WHERE tsv @@ q ORDER BY rank LIMIT 50
),
semantic AS (
  SELECT id, row_number() OVER (ORDER BY distance, id) AS rank
    FROM (SELECT id, embedding <=> $2 AS distance FROM docs
           WHERE embedding IS NOT NULL ORDER BY distance LIMIT 50) nearest
)
SELECT coalesce(k.id, v.id) AS id,
       coalesce($3::float8 / (60 + k.rank), 0)  -- $3 keyword weight, e.g. 1.0
     + coalesce($4::float8 / (60 + v.rank), 0) AS rrf  -- $4 vector weight, e.g. 1.0
  FROM keyword k FULL OUTER JOIN semantic v USING (id)
 ORDER BY rrf DESC, id
 LIMIT 10;
```

## A normalized blend, weight tuned on held-out questions

```sql
WITH keyword AS (
  SELECT id, -neg_score AS score
    FROM (SELECT id, body <@> to_bm25query($1, 'docs_body_bm25') AS neg_score
            FROM docs ORDER BY neg_score LIMIT 50) hits
   WHERE neg_score < 0
),
semantic AS (
  SELECT id, 1 - (embedding <=> $2) AS score
    FROM docs WHERE embedding IS NOT NULL
   ORDER BY embedding <=> $2 LIMIT 50
),
normalized AS (                            -- min-max to [0, 1], per list, per question
  SELECT 'k' AS list, id, CASE WHEN hi > lo THEN (score - lo) / (hi - lo) ELSE 1 END AS s
    FROM (SELECT *, min(score) OVER () AS lo, max(score) OVER () AS hi FROM keyword) k
  UNION ALL
  SELECT 'v', id, CASE WHEN hi > lo THEN (score - lo) / (hi - lo) ELSE 1 END
    FROM (SELECT *, min(score) OVER () AS lo, max(score) OVER () AS hi FROM semantic) v
)
SELECT id,
       sum(CASE list WHEN 'v' THEN $3::float8 ELSE 1 - $3::float8 END * s) AS blend
  FROM normalized                          -- $3 vector weight w, chosen on dev questions
 GROUP BY id
 ORDER BY blend DESC, id
 LIMIT 10;
```

A post missing from one list scores 0 there. Choose `w` by trying 0.0 to 1.0 on questions
that are not in your test set (`hybrid-lab/py/5_tune_fusion.py`); in the lab it ranged from
0.55 to 1.0. Bruch, Gai & Ingber, ACM TOIS 2023.

## Similar AND contains a required word

```sql
SET hnsw.iterative_scan = relaxed_order;  -- pgvector 0.8+: keep walking until LIMIT fills
WITH nearest AS MATERIALIZED (
  SELECT id, embedding <=> $2 AS distance
    FROM docs
   WHERE tsv @@ websearch_to_tsquery('english', $3)
   ORDER BY distance
   LIMIT 10
)
SELECT * FROM nearest ORDER BY distance + 0;   -- relaxed order: re-sort the few rows
```

Check the plan: a rare term may get GIN plus an exact sort instead, which is also correct.

## A function that carries its settings

```sql
CREATE FUNCTION hybrid_search(query_text text, query_embedding vector(1536),
                              match_count int DEFAULT 10, required_terms text DEFAULT NULL)
RETURNS TABLE (doc_id text, score float8, keyword_rank bigint, vector_rank bigint)
LANGUAGE sql STABLE
SET hnsw.ef_search = 100
SET hnsw.iterative_scan = relaxed_order
SET plan_cache_mode = force_custom_plan   -- lets "required_terms IS NULL OR ..." fold away
BEGIN ATOMIC
  ...  -- see hybrid-lab/sql/11_hybrid_function.sql
END;
```

Reference parameters directly in `WHERE`. Joining them in through a CTE, or a generic plan,
keeps the `OR`, and the vector list falls back to a parallel sequential scan instead of HNSW
(measured without a filter: 197 ms instead of 73 ms).

## See the plan inside a function

```sql
LOAD 'auto_explain';
SET auto_explain.log_min_duration = 0;
SET auto_explain.log_nested_statements = on;
SET auto_explain.log_analyze = on;
SET auto_explain.log_level = notice;      -- plans arrive in your client as NOTICEs
SELECT count(*) FROM hybrid_search($1, $2);
```

## Boost fused results by recency, popularity, and preference

```sql
SELECT h.doc_id,
       h.score
       * power(0.5, extract(epoch FROM now() - d.published_at) / 86400 / 30)  -- 30-day half-life
       * (1 + ln(1 + d.likes) / 10)                                          -- popularity, damped
       * CASE WHEN d.category = ANY($3) THEN 1.2 ELSE 1 END                  -- user preference
         AS boosted
  FROM hybrid_search($1, $2, match_count => 50) h
  JOIN docs d ON d.id = h.doc_id
 ORDER BY boosted DESC
 LIMIT 10;
```

Boost a larger pool than you show, or a boost can't lift anything into view. Multiply after
fusion so a boost scales relevance instead of replacing it. Not measured in the lab: BEIR has no
dates or popularity.

## Expand results along relationships (recursive CTE)

```sql
WITH RECURSIVE related (doc_id, score, depth) AS (
  SELECT doc_id, score, 0
    FROM hybrid_search($1, $2, match_count => 10)
  UNION ALL
  SELECT l.dst, r.score / 2, r.depth + 1          -- halve the score per hop
    FROM related r
    JOIN links l ON l.src = r.doc_id               -- citations, replies, related items
   WHERE r.depth < 2                               -- the depth bound also stops cycles
)
SELECT doc_id, max(score) AS score
  FROM related
 GROUP BY doc_id
 ORDER BY score DESC
 LIMIT 10;
```

Index `links (src)`. PostgreSQL 14+ can also detect loops with `CYCLE`. Not measured in the lab:
BEIR has no links between documents. Both patterns were run against the lab's `hybrid_search()`
with synthetic metadata.

## Operating checklist

| Area | Inspect before changing it |
| --- | --- |
| HNSW build | `maintenance_work_mem` (the graph must fit), parallel workers, `m`, `ef_construction`, index size |
| HNSW search | `ef_search` ≥ LIMIT, filtered recall, `iterative_scan`, `max_scan_tuples` |
| Full text | OR vs AND queries, match counts, `ts_rank_cd` cost on common terms, BM25 availability |
| Embeddings | Model id per column, input types, re-embedding on text change, quota and throttling |
| Functions | Inner plans with `auto_explain`; `plan_cache_mode` for optional filters |
| Evaluation | Re-run the question set after every change; keep per-question wins and losses |

## Score it

NDCG@10 and Recall@50 per arm, in SQL: [`10_scoreboard.sql`](../hybrid-lab/sql/10_scoreboard.sql).
