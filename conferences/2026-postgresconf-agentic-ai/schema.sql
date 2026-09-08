-- =========================================================================
-- AI Coffee Roastery — database schema
-- Demonstrates: pgvector semantic search, PostgreSQL full-text search,
--               reciprocal-rank fusion, episodic memory, tool registry,
--               tool audit, relational filters, and HNSW/GIN indexing.
-- =========================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- The input is text[] (no locale-sensitive conversion of dates/numbers).
CREATE OR REPLACE FUNCTION coffee_flavor_text(notes text[])
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT array_to_string(notes, ' ') $$;

-- ---- customers ---------------------------------------------------------
DROP TABLE IF EXISTS approvals        CASCADE;
DROP TABLE IF EXISTS tool_audit       CASCADE;
DROP TABLE IF EXISTS tools            CASCADE;
DROP TABLE IF EXISTS agent_messages   CASCADE;
DROP TABLE IF EXISTS agent_sessions   CASCADE;
DROP TABLE IF EXISTS orders           CASCADE;
DROP TABLE IF EXISTS beans            CASCADE;
DROP TABLE IF EXISTS customers        CASCADE;

CREATE TABLE customers (
  id                  text PRIMARY KEY,
  name                text NOT NULL,
  preferences_summary text,
  created_at          timestamptz NOT NULL DEFAULT now()
);

-- ---- beans (the product catalog + knowledge base) ---------------------
CREATE TABLE beans (
  id            text PRIMARY KEY,
  name          text NOT NULL,
  origin        text NOT NULL,
  roast_level   text NOT NULL  CHECK (roast_level IN ('light','medium-light','medium','medium-dark','dark')),
  process       text NOT NULL  CHECK (process IN ('washed','natural','honey','anaerobic')),
  flavor_notes  text[] NOT NULL,
  description   text NOT NULL,
  price_cents   int NOT NULL,
  in_stock      int NOT NULL DEFAULT 0,
  search_document tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(name, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(origin, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(coffee_flavor_text(flavor_notes), '')), 'A') ||
    setweight(to_tsvector('english', coalesce(description, '')), 'B')
  ) STORED,
  embedding     vector(384)  -- produced from: name + origin + roast + notes + description
);

CREATE INDEX beans_hnsw_idx ON beans USING hnsw (embedding vector_cosine_ops);
CREATE INDEX beans_search_document_gin ON beans USING gin (search_document);
CREATE INDEX beans_notes_gin ON beans USING gin (flavor_notes);
CREATE INDEX beans_name_trgm ON beans USING gin (name gin_trgm_ops);
CREATE INDEX beans_desc_trgm ON beans USING gin (description gin_trgm_ops);

-- ---- orders (episodic memory: what each customer actually bought) -----
CREATE TABLE orders (
  id          bigserial PRIMARY KEY,
  customer_id text NOT NULL REFERENCES customers(id),
  bean_id     text NOT NULL REFERENCES beans(id),
  qty         int  NOT NULL,
  placed_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX orders_customer_idx ON orders (customer_id, placed_at DESC);

-- ---- agent sessions & episodic message history -----------------------
-- workflow_state holds the latest serialized plan + step index so progress is
-- inspectable and a production recovery loop has a durable starting point.
-- This demo checkpoints state but does not automatically replay partial turns.
CREATE TABLE agent_sessions (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id    text NOT NULL REFERENCES customers(id),
  started_at     timestamptz NOT NULL DEFAULT now(),
  workflow_state jsonb,
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agent_messages (
  id          bigserial PRIMARY KEY,
  session_id  uuid NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
  role        text NOT NULL,     -- 'user' | 'agent' | 'tool'
  agent       text,              -- coordinator | roast_master | flavor_profiler
  content     jsonb NOT NULL,
  ts          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX agent_messages_session_idx ON agent_messages (session_id, ts DESC);

-- ---- tool registry ----------------------------------------------------
CREATE TABLE tools (
  name               text PRIMARY KEY,
  description        text NOT NULL,
  description_emb    vector(384),
  input_schema       jsonb NOT NULL,
  requires_approval  boolean NOT NULL DEFAULT false,
  enabled            boolean NOT NULL DEFAULT true,
  owner_agent        text
);

-- ---- tool audit (invocations recorded in separate visible commits) ----
CREATE TABLE tool_audit (
  id         bigserial PRIMARY KEY,
  session_id uuid REFERENCES agent_sessions(id) ON DELETE SET NULL,
  tool       text NOT NULL,
  caller     text NOT NULL,
  args       jsonb NOT NULL,
  result     jsonb,
  latency_ms int,
  ts         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX tool_audit_session_idx ON tool_audit (session_id, ts DESC);

-- ---- approval queue (for tools marked requires_approval=true) ---------
-- A pending row here is a guardrail: the effect-bearing tool call is NOT
-- executed until status='approved'. The frontend renders these; a human
-- (or a supervising agent) approves. Everything is auditable.
CREATE TABLE approvals (
  id         bigserial PRIMARY KEY,
  session_id uuid NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
  tool       text NOT NULL,
  caller     text NOT NULL,
  args       jsonb NOT NULL,
  status     text NOT NULL DEFAULT 'pending'
             CHECK (status IN ('pending','approved','rejected','executed')),
  reason     text,
  created_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz
);
CREATE INDEX approvals_status_idx ON approvals (status, created_at DESC);
