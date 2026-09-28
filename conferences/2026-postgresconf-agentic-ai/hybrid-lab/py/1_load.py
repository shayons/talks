# %% [markdown]
# # 1. Load a BEIR dataset into PostgreSQL
#
# FiQA-2018 is the main example: 57,638 finance forum posts, 648 test questions, and human
# judgments of which posts answer which question. The judgments are what let us grade every
# search method with a number instead of eyeballing results.
#
# Set LAB_DATASET to load another one (scifact, nfcorpus, scidocs) into its own database,
# created first with `LAB_DB=<dataset> ./scripts/setup.sh`.
#
# Run each cell with Shift+Enter in the VS Code Interactive window.

# %%
from hybrid_lab import beir
from hybrid_lab.db import connect, dataset, sql_text

name = dataset()
archive = beir.download(name)  # cached in data/ and checksum-verified
all_questions = beir.questions(archive)
docs = dict(beir.corpus(archive))
available = beir.splits(archive)
# "dev" holds the questions used only for tuning fusion weights: the dataset's dev split,
# or its train split when it has no dev split (SciFact). Test questions are never tuned on.
tuning_split = next((split for split in ("dev", "train") if split in available), None)
judgments = {"test": beir.qrels(archive, "test")}
if tuning_split:
    judgments["dev"] = beir.qrels(archive, tuning_split)
for split, rows in judgments.items():
    print(f"{name} {split}: {len({q for q, _, _ in rows})} questions, {len(rows):,} judgments")
print(f"{len(docs):,} documents")

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
            for doc_id, body in docs.items():
                copy.write_row((doc_id, body))
        for split, rows in judgments.items():
            question_ids = sorted({query_id for query_id, _, _ in rows})
            with conn.cursor().copy("COPY queries (id, body, split) FROM STDIN") as copy:
                for query_id in question_ids:
                    copy.write_row((query_id, all_questions[query_id], split))
            kept = [row for row in rows if row[1] in docs]
            if len(kept) < len(rows):
                print(f"{split}: skipped {len(rows) - len(kept)} judgments for missing documents")
            with conn.cursor().copy("COPY qrels (query_id, doc_id, relevance) FROM STDIN") as copy:
                for row in kept:
                    copy.write_row(row)
        conn.execute("ANALYZE docs, queries, qrels")
        print("Loaded.")

# %% [markdown]
# What landed. Empty documents stay in the table (a judgment may point at one) but can never
# be found by any method, so they count against every arm equally.

# %%
with connect() as conn:
    print(conn.execute("""
        SELECT (SELECT count(*) FROM docs)                          AS docs,
               (SELECT count(*) FROM docs WHERE btrim(body) = '')   AS empty_docs,
               (SELECT count(*) FROM queries WHERE split = 'test')  AS test_questions,
               (SELECT count(*) FROM queries WHERE split = 'dev')   AS dev_questions,
               (SELECT count(*) FROM qrels)                         AS judgments,
               (SELECT count(*) FROM qrels q JOIN docs d ON d.id = q.doc_id
                 WHERE btrim(d.body) = '')                          AS unfindable_judgments,
               pg_size_pretty(pg_total_relation_size('docs'))       AS docs_size
    """).fetchone())
