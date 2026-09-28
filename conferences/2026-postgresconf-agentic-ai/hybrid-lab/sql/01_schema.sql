-- 01. Schema: one row holds the text, its lexemes, and its embedding.
--
-- One database per BEIR dataset, same schema. FiQA-2018: 57,638 finance forum posts,
-- 648 test questions, and human judgments (qrels) of which posts answer which question.
-- Run once on an empty database; py/1_load.py applies it for you.

CREATE EXTENSION IF NOT EXISTS vector;

-- The corpus. The tsvector is derived by PostgreSQL and can never drift from
-- the text. One column per embedding model, never mixed:
--   embedding        Cohere Embed v4 on Bedrock (input_type 'search_document'), py/2_embed.py
--   embedding_local  BAAI/bge-small-en-v1.5, open source, on this laptop, py/2b_embed_local.py
CREATE TABLE docs (
  id              text PRIMARY KEY,
  body            text NOT NULL,
  tsv             tsvector GENERATED ALWAYS AS (to_tsvector('english', body)) STORED,
  embedding       vector(1536),
  embedding_local vector(384)
);

-- Questions: the test split (FiQA: 648), the dev split when a dataset has one
-- (FiQA: 500, used only to tune fusion weights), and questions typed on stage
-- (split = 'demo'). Questions are embedded with input_type = 'search_query'.
CREATE TABLE queries (
  id        text PRIMARY KEY,
  body      text NOT NULL,
  split     text NOT NULL CHECK (split IN ('test', 'dev', 'demo')),
  embedding vector(1536),
  embedding_local vector(384)
);

-- Ground truth: which documents answer which test question.
CREATE TABLE qrels (
  query_id  text NOT NULL REFERENCES queries (id),
  doc_id    text NOT NULL REFERENCES docs (id),
  relevance int  NOT NULL CHECK (relevance > 0),
  PRIMARY KEY (query_id, doc_id)
);

-- Evaluation output: every arm's top 50 for every test question.
CREATE TABLE runs (
  stage     text   NOT NULL,
  query_id  text   NOT NULL REFERENCES queries (id),
  rank      int    NOT NULL CHECK (rank BETWEEN 1 AND 50),
  doc_id    text   NOT NULL REFERENCES docs (id),
  score     float8,
  PRIMARY KEY (stage, query_id, rank)
);

CREATE TABLE run_timings (
  stage      text   NOT NULL,
  query_id   text   NOT NULL REFERENCES queries (id),
  elapsed_ms float8 NOT NULL,
  PRIMARY KEY (stage, query_id)
);

-- Fusion weights chosen on held-out dev questions by py/5_tune_fusion.py, never on test.
CREATE TABLE fusion_settings (
  name  text PRIMARY KEY,
  value float8 NOT NULL,
  note  text
);

-- Curated stage questions, chosen from measured per-question results.
CREATE TABLE demo_questions (
  query_id text PRIMARY KEY REFERENCES queries (id),
  label    text NOT NULL,
  reason   text NOT NULL,
  position int  NOT NULL UNIQUE
);

-- The question every arm file reads. In VS Code, py/3_ask.py sets lab_state.
-- The evaluator and the UI instead run SET LOCAL lab.query_id = '...'
-- inside a transaction, so the same file serves the stage and the benchmark.
CREATE TABLE lab_state (
  singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  query_id  text REFERENCES queries (id)
);
INSERT INTO lab_state DEFAULT VALUES;

CREATE VIEW active_query AS
SELECT q.id, q.body, q.embedding, q.embedding_local
  FROM queries q
 WHERE q.id = coalesce(nullif(current_setting('lab.query_id', true), ''),
                       (SELECT query_id FROM lab_state));
