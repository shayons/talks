# %% [markdown]
# # 1 · Load FiQA into PostgreSQL
#
# FiQA-2018 from the BEIR benchmark: 57,638 finance forum posts, 648 test questions,
# and human judgments of which posts answer which question. The judgments are what let
# us grade every search method with a number instead of eyeballing results.
#
# Run each cell with Shift+Enter in the VS Code Interactive window.

# %%
from hybrid_lab import fiqa
from hybrid_lab.db import connect, sql_text

archive = fiqa.download()  # 18 MB, cached in data/ and checksum-verified
all_questions = fiqa.questions(archive)
judgments = fiqa.test_qrels(archive)
test_ids = sorted({query_id for query_id, _, _ in judgments}, key=int)
print(f"{len(all_questions):,} questions, {len(test_ids)} in the test split, "
      f"{len(judgments):,} judgments")
print("Example:", all_questions[test_ids[0]])

# %% [markdown]
# Create the schema (sql/01_schema.sql), then bulk-load with COPY. The generated
# `tsv` column is computed by PostgreSQL as each row arrives.

# %%
with connect() as conn:
    loaded = conn.execute("SELECT to_regclass('docs') IS NOT NULL").fetchone()[0]
    if loaded:
        print("Already loaded:", conn.execute("SELECT count(*) FROM docs").fetchone()[0], "docs")
    else:
        conn.execute(sql_text("01_schema.sql"))
        with conn.cursor().copy("COPY docs (id, body) FROM STDIN") as copy:
            for doc_id, body in fiqa.corpus(archive):
                copy.write_row((doc_id, body))
        with conn.cursor().copy("COPY queries (id, body, split) FROM STDIN") as copy:
            for query_id in test_ids:
                copy.write_row((query_id, all_questions[query_id], "test"))
        with conn.cursor().copy("COPY qrels (query_id, doc_id, relevance) FROM STDIN") as copy:
            for row in judgments:
                copy.write_row(row)
        conn.execute("ANALYZE docs, queries, qrels")
        print("Loaded.")

# %% [markdown]
# What landed. Empty posts stay in the table (a judgment points at one) but can never
# be found by any method, so they count against every arm equally.

# %%
with connect() as conn:
    print(conn.execute("""
        SELECT (SELECT count(*) FROM docs)                          AS docs,
               (SELECT count(*) FROM docs WHERE btrim(body) = '')   AS empty_docs,
               (SELECT count(*) FROM queries WHERE split = 'test')  AS test_questions,
               (SELECT count(*) FROM qrels)                         AS judgments,
               (SELECT count(*) FROM qrels q JOIN docs d ON d.id = q.doc_id
                 WHERE btrim(d.body) = '')                          AS unfindable_judgments,
               pg_size_pretty(pg_total_relation_size('docs'))       AS docs_size
    """).fetchone())
