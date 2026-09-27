# SQL patterns from the talk

Copyable versions of the patterns on the slides. Every one runs, as written, in
[`hybrid-lab/sql/`](../hybrid-lab/sql/) against the FiQA table
`docs (id text, body text, tsv tsvector, embedding vector(1536))`. Here `$1` is the question
text and `$2` its embedding (input type `search_query`).

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
keeps the `OR` and disables both indexes (measured: 335 ms instead of 86 ms).

## See the plan inside a function

```sql
LOAD 'auto_explain';
SET auto_explain.log_min_duration = 0;
SET auto_explain.log_nested_statements = on;
SET auto_explain.log_analyze = on;
SET auto_explain.log_level = notice;      -- plans arrive in your client as NOTICEs
SELECT count(*) FROM hybrid_search($1, $2);
```

## Score it

NDCG@10 and Recall@50 per arm, in SQL: [`10_scoreboard.sql`](../hybrid-lab/sql/10_scoreboard.sql).
