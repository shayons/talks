# SQL patterns behind the slides

These are read-only retrieval examples. The current application's complete RRF
query is [`SEARCH_SQL` in search.py](../search.py); the Lab exposes that same
statement and can run `EXPLAIN (ANALYZE, BUFFERS)` against it. Slide excerpts
omit optional filters to keep the SQL readable.

## RRF and candidate selection · slides 8–13

The application:

1. Applies budget, roast, origin and stock eligibility in **both** branches.
2. Limits candidates independently; semantic ordering uses ascending cosine
   distance, lexical ordering uses text rank and optional trigram name matches.
3. Assigns branch ranks with `row_number()` and an ID tie-break.
4. Full-outer-joins candidate IDs and sums `1 / (k + rank)`, with zero for an
   absent branch. Default candidate depth is 12 and default RRF k is 60.
5. Joins canonical `beans` rows for display facts and orders by RRF score,
   semantic score and ID.

An optional minimum cosine trims the semantic branch after candidate selection.
It does not require lexical-only candidates to pass the same threshold. The
comparison and its diagnostic reads use a repeatable-read snapshot; EXPLAIN
ANALYZE executes the statement a second time in that transaction.

## Required words plus semantic ranking · slide 21

Use this when the words are mandatory, rather than one signal in an RRF union.
`websearch_to_tsquery` uses normalized lexemes; quoted phrases have their own
text-search semantics. This example does not impose a minimum similarity.

Parameters: request embedding, required words, maximum price in cents, result
limit. The following uses psycopg's named placeholders, equivalent to the
numbered parameters on the slide.

```sql
SELECT id, name, embedding <=> %(embedding)s::vector AS distance
FROM beans
WHERE search_document @@ websearch_to_tsquery('english', %(required)s)
  AND embedding IS NOT NULL
  AND in_stock > 0 AND price_cents <= %(budget)s
ORDER BY embedding <=> %(embedding)s::vector
LIMIT %(limit)s;
```

Inspect the actual plan. A selective text/relational subset followed by exact
distance sorting can be useful; the SQL does not guarantee that execution
strategy. An HNSW path can visit rows later rejected by filtering.

## Relationship expansion before retrieval · slide 29

This is a small, explicitly illustrative taxonomy supplied as a CTE. It does
not create or alter application tables. `UNION` deduplicates name-only states.
A production taxonomy should use canonical IDs and explicit membership and
access rules. Add budget/roast constraints when the request requires them.

```sql
WITH RECURSIVE regions(name, parent) AS (
  VALUES ('Asia-Pacific', NULL::text),
         ('Indonesia', 'Asia-Pacific'), ('Sumatra', 'Indonesia')
), allowed(name) AS (
  SELECT name FROM regions WHERE name = %(root)s
  UNION
  SELECT r.name FROM regions r JOIN allowed a ON r.parent = a.name
)
SELECT b.id, b.name
FROM beans b
WHERE b.in_stock > 0 AND b.embedding IS NOT NULL
  AND EXISTS (SELECT 1 FROM allowed a
              WHERE strpos(lower(b.origin), lower(a.name)) > 0)
ORDER BY b.embedding <=> %(embedding)s::vector
LIMIT %(limit)s;
```

## Run the extension examples locally

From the project root with the README's Python environment and database
configuration in place. This embeds a real request, executes both SELECTs in a
read-only transaction, and prints their results. The SQL blocks above are the
authoritative extension examples; this runner extracts them without keeping a
second copy of the query text.

```python
import re
from pathlib import Path
from pgvector.psycopg import Vector
from db import conn, embed, close_pool

queries = re.findall(r"```sql\n(.*?)\n```", Path("deck/SQL_PATTERNS.md").read_text(), re.S)
params = {
    "embedding": Vector(embed("floral and citrus coffee")),
    "required": "bergamot", "budget": 2000, "limit": 5,
    "root": "Asia-Pacific",
}
try:
    with conn() as connection, connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        cursor.execute("SET LOCAL statement_timeout = '10s'")
        for query in queries:
            cursor.execute(query, params)
            print(cursor.fetchall())
finally:
    close_pool()
```

Results depend on the current catalog. An empty list can be correct. The
extension patterns are not separate modes in the Lab UI.
