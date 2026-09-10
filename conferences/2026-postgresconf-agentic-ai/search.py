"""Shared PostgreSQL retrieval for the search lab and the agent pipeline.

Ranks are assigned after eligibility filters and candidate selection. The
comparison uses one statement/snapshot; EXPLAIN is an optional second execution.
"""
from __future__ import annotations

import time
import re

from pgvector.psycopg import Vector

from db import EMBED_MODEL, conn, embed
from catalog import product_details


FILTER_SQL = """
      AND (%(budget)s::int IS NULL OR b.price_cents <= %(budget)s)
      AND (cardinality(%(roasts)s::text[]) = 0 OR b.roast_level = ANY(%(roasts)s))
      AND (cardinality(%(origins)s::text[]) = 0 OR EXISTS (
        SELECT 1 FROM unnest(%(origins)s::text[]) AS o(origin)
        WHERE strpos(lower(b.origin), lower(o.origin)) > 0
      ))
      AND (NOT %(stock_only)s OR b.in_stock > 0)
""".rstrip()

# Keep the vector distance directly in ORDER BY so an HNSW path is available.
# The planner may correctly prefer sequential scans for this 16-row catalog.
SEARCH_SQL = f"""
WITH semantic_candidates AS MATERIALIZED (
  SELECT b.id, b.embedding <=> %(embedding)s::vector AS distance
    FROM beans b
   WHERE b.embedding IS NOT NULL
{FILTER_SQL}
   ORDER BY b.embedding <=> %(embedding)s::vector
   LIMIT %(candidates)s
),
semantic AS (
  SELECT id, 1 - distance AS semantic_score,
         row_number() OVER (ORDER BY distance, id) AS semantic_rank
    FROM semantic_candidates
   WHERE (%(min_cosine)s::float IS NULL OR 1 - distance >= %(min_cosine)s)
),
lexical_candidates AS MATERIALIZED (
  SELECT b.id,
         ts_rank_cd(b.search_document,
           websearch_to_tsquery('english', %(query)s), 32) AS lexical_score,
         CASE WHEN %(fuzzy)s THEN similarity(b.name, %(query)s)
              ELSE 0 END AS trigram_score,
         b.search_document @@ websearch_to_tsquery('english', %(query)s) AS text_match
    FROM beans b
   WHERE (b.search_document @@ websearch_to_tsquery('english', %(query)s)
          OR (%(fuzzy)s AND b.name %% %(query)s))
{FILTER_SQL}
   ORDER BY lexical_score DESC, trigram_score DESC, b.id
   LIMIT %(candidates)s
),
lexical AS (
  SELECT *, row_number() OVER (
    ORDER BY lexical_score DESC, trigram_score DESC, id
  ) AS lexical_rank
    FROM lexical_candidates
),
fused AS (
  SELECT coalesce(s.id, l.id) AS id,
         s.semantic_score, s.semantic_rank,
         l.lexical_score, l.lexical_rank, l.trigram_score, l.text_match,
         coalesce(1.0 / (%(rrf_k)s + s.semantic_rank), 0) +
         coalesce(1.0 / (%(rrf_k)s + l.lexical_rank), 0) AS rrf_score
    FROM semantic s FULL OUTER JOIN lexical l USING (id)
)
SELECT b.id, b.name, b.roast_level, b.process, b.flavor_notes,
       b.price_cents, b.in_stock, b.origin,
       f.semantic_score, f.semantic_rank, f.lexical_score, f.lexical_rank,
       f.trigram_score, f.rrf_score, coalesce(f.text_match, false), b.description,
       CASE WHEN f.text_match THEN ts_headline('english',
         translate(array_to_string(b.flavor_notes, ', ') || '. ' || b.name || '. ' ||
                   b.origin || '. ' || b.description, chr(1) || chr(2), ''),
         websearch_to_tsquery('english', %(query)s),
         'StartSel=' || chr(1) || ', StopSel=' || chr(2) ||
         ', MaxFragments=1, MaxWords=16, MinWords=6, ShortWord=0') END
  FROM fused f JOIN beans b USING (id)
 ORDER BY f.rrf_score DESC, f.semantic_score DESC NULLS LAST, b.id
""".strip()

# This diagnostic is a separate read in the comparison's repeatable-read snapshot.
# It includes excluded lexical/fuzzy matches, not every semantic neighbor.
EXCLUDED_SQL = f"""
SELECT b.id, b.name, b.price_cents, b.roast_level, b.origin, b.in_stock,
       %(budget)s::int IS NOT NULL AND b.price_cents > %(budget)s AS over_budget,
       cardinality(%(roasts)s::text[]) > 0 AND NOT (b.roast_level = ANY(%(roasts)s)) AS wrong_roast,
       cardinality(%(origins)s::text[]) > 0 AND NOT EXISTS (
         SELECT 1 FROM unnest(%(origins)s::text[]) AS o(origin)
         WHERE strpos(lower(b.origin), lower(o.origin)) > 0) AS wrong_origin,
       %(stock_only)s AND b.in_stock <= 0 AS no_stock,
       b.search_document @@ websearch_to_tsquery('english', %(query)s) AS text_match,
       count(*) OVER () AS total
  FROM beans b
 WHERE (b.search_document @@ websearch_to_tsquery('english', %(query)s)
        OR (%(fuzzy)s AND b.name %% %(query)s))
   AND NOT (TRUE
{FILTER_SQL})
 ORDER BY b.price_cents, b.id
 LIMIT 20
""".strip()


def headline_parts(value):
    """Return text tokens, never HTML. Only PostgreSQL inserts the stripped markers."""
    if not value:
        return []
    return [{"text": part, "highlight": i % 2 == 1}
            for i, part in enumerate(re.split(r'\x01(.*?)\x02', value, flags=re.S)) if part]


def excluded_from_row(row, params):
    reasons = []
    if row[6]:
        reasons.append(f"${row[2]/100:.2f} exceeds the ${params['budget']/100:.2f} maximum")
    if row[7]:
        reasons.append(f"{row[3]} roast does not match the selected roasts")
    if row[8]:
        reasons.append(f"{row[4]} does not match the selected origins")
    if row[9]:
        reasons.append("Out of stock")
    return {"id": row[0], "name": row[1], "price_cents": row[2],
            "reasons": reasons, "text_match": row[10]}


def search_params(vector, query, *, budget=None, roasts=(), origins=(),
                  stock_only=True, fuzzy=False, candidates=12, rrf_k=60, min_cosine=None):
    return {
        "embedding": Vector(vector), "query": query, "budget": budget,
        "roasts": list(roasts), "origins": list(origins),
        "stock_only": stock_only, "fuzzy": fuzzy,
        "candidates": candidates, "rrf_k": rrf_k,
        "min_cosine": min_cosine,
    }


def result_from_row(row) -> dict:
    return {
        "id": row[0], "name": row[1], "roast_level": row[2],
        "process": row[3], "flavor_notes": row[4], "price_cents": row[5],
        "in_stock": row[6], "origin": row[7], "score": float(row[8] or 0),
        "semantic_rank": row[9], "lexical_score": float(row[10] or 0),
        "lexical_rank": row[11], "trigram_score": float(row[12] or 0),
        "hybrid_score": float(row[13]), "text_match": bool(row[14]),
        "description": row[15],
        "match_excerpt": headline_parts(row[16]) if len(row) > 16 else [],
        "one_liner": f"{row[2]} roast · {', '.join(row[4][:3])} · ${row[5]/100:.2f}/bag",
    }


def compare_search(query: str, *, explain=False, **options) -> dict:
    start = time.perf_counter()
    vector = embed(query)
    embed_ms = (time.perf_counter() - start) * 1000
    params = search_params(vector, query, **options)
    with conn() as c, c.cursor() as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        cur.execute("SET LOCAL statement_timeout = '10s'")
        # Fix the fuzzy threshold for reproducible demos regardless of session defaults.
        cur.execute("SET LOCAL pg_trgm.similarity_threshold = 0.3")
        start_sql = time.perf_counter()
        cur.execute(SEARCH_SQL, params)
        results = [result_from_row(row) for row in cur.fetchall()]
        results = [{**row, **product_details(row)} for row in results]
        query_ms = (time.perf_counter() - start_sql) * 1000
        start_diagnostics = time.perf_counter()
        cur.execute(EXCLUDED_SQL, params)
        excluded_rows = cur.fetchall()
        excluded = [excluded_from_row(row, params) for row in excluded_rows]
        cur.execute('SELECT count(*) FROM beans b WHERE TRUE\n' + FILTER_SQL, params)
        eligible_count = cur.fetchone()[0]
        cur.execute("SELECT websearch_to_tsquery('english', %s)::text", (query,))
        parsed_query = cur.fetchone()[0]
        diagnostics_ms = (time.perf_counter() - start_diagnostics) * 1000
        plan = None
        if explain:
            cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + SEARCH_SQL, params)
            plan = cur.fetchone()[0][0]
    return {
        "query": query, "results": results, "excluded": excluded,
        "eligible_count": eligible_count, "parsed_query": parsed_query,
        "excluded_total": excluded_rows[0][11] if excluded_rows else 0,
        "excluded_sql": EXCLUDED_SQL.replace("%%", "%"),
        "timing": {"embedding_ms": round(embed_ms, 2), "query_ms": round(query_ms, 2),
                   "diagnostics_ms": round(diagnostics_ms, 2),
                   "total_ms": round((time.perf_counter() - start) * 1000, 2)},
        "settings": {key: value for key, value in params.items() if key != "embedding"},
        "sql": SEARCH_SQL.replace("%%", "%"), "plan": plan,
        "embedding_model": EMBED_MODEL,
    }


def search_status() -> dict:
    with conn() as c, c.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute("SET LOCAL statement_timeout = '5s'")
        cur.execute("SELECT current_setting('server_version')")
        version = cur.fetchone()[0]
        cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector','pg_trgm') ORDER BY extname")
        extensions = dict(cur.fetchall())
        cur.execute("SELECT count(*), count(embedding), count(search_document), count(*) FILTER (WHERE in_stock > 0) FROM beans")
        count, embedded, searchable, stocked = cur.fetchone()
        cur.execute("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'beans' ORDER BY indexname")
        indexes = [{"name": row[0], "definition": row[1]} for row in cur.fetchall()]
    return {"ok": True, "postgres_version": version, "extensions": extensions,
            "catalog_count": count, "embedded_count": embedded, "searchable_count": searchable,
            "stocked_count": stocked, "indexes": indexes, "embedding_model": EMBED_MODEL}
