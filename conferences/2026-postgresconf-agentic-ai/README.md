# Building Agentic AI Applications with PostgreSQL as the Backbone

> Memory, tool registries, MCP, and guardrails for production agents — Claude on Amazon Bedrock at the edges, one Postgres in the middle.
>
> Live demo for **[PostgresConf 2026](https://postgresconf.org/)** · San Pedro (Level C) · Tue Apr 21, 15:00 PDT · 50 min · Dev track.

Most "production agent" stacks glue together Pinecone, Redis, DynamoDB, Postgres, Temporal, SQS, and an orchestrator. Seven systems, seven auth boundaries, seven failure modes. This demo argues the data plane collapses into one: **PostgreSQL** — episodic, semantic, and procedural memory; tool registry; audit; workflow state; approvals; and an MCP surface, all in the same database, all in one query plan when you need it.

The LLMs live at the edges — Haiku parses intent, Opus synthesizes the reply. **Everything in between is SQL.**

**No agent framework — by design, not on principle.** Eight dependencies total: FastAPI, psycopg, pgvector, fastembed, boto3, pydantic, python-dotenv, uvicorn. The repo deliberately ships without LangChain, LangGraph, Strands, AgentCore, or Temporal so you can read the orchestration top-to-bottom — [`agents.py`](agents.py) is ~2,200 lines of Python with no magic. In production, most teams pick a framework and that's fine: LangGraph's [`PostgresSaver`](https://langchain-ai.github.io/langgraph/reference/checkpoints/#langgraph.checkpoint.postgres.PostgresSaver) is a nice API over a `jsonb` column, Strands memory can point at a Postgres table, AgentCore's session store speaks SQL. Clean seam — **frameworks handle prompt orchestration and agent loops; Postgres handles state, memory, audit, approvals.** This repo skips the top half so the bottom half is legible.

---

## Table of contents

**[Stage guide](#stage-guide--everything-you-need-while-presenting)** — everything you need while presenting

- [Setup (before you go live)](#setup-before-you-go-live)
- [The three customers](#the-three-customers)
- [Opener (30 sec)](#opener-30-sec)
- [Scenario 1 · Marco · Three kinds of memory in one plan](#scenario-1--marco--three-kinds-of-memory-in-one-plan-4-min)
- [Scenario 2 · Ana · Memory continuity + approvals](#scenario-2--ana--memory-continuity--approvals-4-min)
- [Scenario 3 · Yuki · Catalog miss + MCP](#scenario-3--yuki--catalog-miss--mcp-3-min)
- [The closer (30 sec)](#the-closer-30-sec)
- [Panel cheat sheet](#panel-cheat-sheet)
- [Audience curveballs](#audience-curveballs)
- [Key takeaways](#key-takeaways)

**[Reference](#reference)** — appendix; safe to skip while presenting

- [Quick start](#quick-start)
- [Using your own Postgres](#using-your-own-postgres)
- [Architecture](#architecture)
- [Schema at a glance](#schema-at-a-glance)
- [Customizing](#customizing)
- [When to re-seed](#when-to-re-seed)
- [Files](#files)
- [Slide deck](#slide-deck)

---

# Stage guide — everything you need while presenting

## Setup (before you go live)

Two windows, side by side:

- **Browser** — `http://localhost:8000`
- **psql** — `PGPASSWORD=coffee psql -h 127.0.0.1 -U coffee -d coffee`

Optional third window for Scenario 3: `python mcp_server.py` in a terminal.

**Run [`./reset.sh`](reset.sh) right before you go live** — clears the rehearsal noise (`agent_sessions`, `agent_messages`, `tool_audit`, `approvals`) without touching the knowledge base. One keystroke, no re-embedding. See [When to re-seed](#when-to-re-seed) for the full distinction.

## The three customers

Walk on stage, open the demo, and before typing a single query, frame the setup:

> _"We have three customers. Marco is a pour-over regular who keeps pulling East African beans. Ana buys dark-roast espresso in quantity. Yuki is a Tokyo specialty buyer who likes washed light roasts and asks about things our catalog doesn't always carry. Three different personalities, three different shopping patterns — **same agents, same tools, same prompts underneath.** The only thing that changes between them is the rows in `customers`, `orders`, and `agent_messages`. Memory is the personality."_

That framing sets up what the audience is about to see: three visibly different replies from an identical pipeline. No branching per customer, no different prompts, no different tools. Just rows.

Same agents, same tools, same prompts. The memory in their rows is what makes the answers different.

| Customer  | Anchors                            | Profile                                                     | Recent orders                                             |
| --------- | ---------------------------------- | ----------------------------------------------------------- | --------------------------------------------------------- |
| **Marco** | Three kinds of memory in one plan  | Medium roasts, fruity East African, pour-over               | Yirgacheffe → Guji Natural → Kenya AA → Rwanda Musasa     |
| **Ana**   | Memory continuity + approvals      | Dark-roast espresso, chocolatey, low-acid, buys in quantity | House Espresso Blend ×3 → Sumatra ×2 → Brazil Santos ×2   |
| **Yuki**  | Catalog miss + MCP (same Postgres) | Tokyo buyer, Japanese single-origins, pour-over and siphon  | Panama Geisha → Ethiopia Yirgacheffe → Costa Rica Tarrazú |

> Yuki's ask intentionally has no catalog match — that's what makes her an honest refusal demo, not a contrived "under $5" prompt.

## Opener (30 sec)

> _"Three agents. Two Claude models on Bedrock. One Postgres. No vector DB, no queue, no cache, no orchestrator. Let's see what breaks — spoiler: nothing."_

---

## Scenario 1 · Marco · Three kinds of memory in one plan (~4 min)

Pick **Marco** (loads by default). Multi-turn pour-over conversation.

**Turn 1 —** `Cold brew options`

| Panel                      | Narration                                                                                        |
| -------------------------- | ------------------------------------------------------------------------------------------------ |
| `LLM · HAIKU · INTENT`     | Haiku returns structured JSON via Converse tool-use: `brew_method=cold_brew`, no order.          |
| `TOOL REGISTRY · DISCOVER` | `tools.description_emb` ranks `search_beans_semantic` and `check_inventory` on top. Not wired.   |
| `MEMORY · EPISODIC`        | Marco's last 5 `orders` rows — just an index scan on `orders_customer_idx`.                      |
| `MEMORY · PROCEDURAL`      | **The zinger.** pgvector similarity + JOIN on `orders` + `customers` — one query, three sources. |
| `ROAST MASTER · FILTER`    | Cold-brew roast filter runs in SQL, not in the model. Saves tokens, stays grounded.              |
| `GUARDRAIL · FACT-CHECK`   | Every pick re-read from `beans`, stock verified. Failures dropped.                               |
| `LLM · OPUS · SYNTHESIZE`  | Reply cites only bean ids that survived fact-check.                                              |

**Turn 2 —** `Something lighter and more floral` _(same session)_

Haiku reads the last 6 turns, picks up Marco is still on cold brew; roast override biases light/medium-light. The embedding lands in a brighter neighborhood — Yirgacheffe and Guji Natural surface. Personalization happens because Marco's history is _right there_ in the same `agent_messages` table Haiku is reading.

**psql callout — one SELECT, the full execution trace:**

```sql
SELECT caller, tool, latency_ms,
       result->>'input_tokens' AS in_tok, result->>'output_tokens' AS out_tok
  FROM tool_audit
 WHERE session_id = (SELECT id FROM agent_sessions
                      WHERE customer_id='u_marco' ORDER BY updated_at DESC LIMIT 1)
 ORDER BY ts DESC LIMIT 12;
```

> **Why this matters.** Episodic, semantic, and procedural memory in one query plan. A vector DB holding embeddings separate from your `orders` table cannot express "customers with similar taste to this request actually bought X." It has to be the same database.

---

## Scenario 2 · Ana · Memory continuity + approvals (~4 min)

Switch to **Ana**. Click **New Session**. Multi-turn espresso conversation that ends with a gated write.

**Turn 1 —** `Cold brew options` _(same string as Marco's)_

Different answer. Call that out explicitly. Ana's dark-espresso cohort pulls House Espresso Blend and Sumatra Mandheling. Opus honestly flags that the espresso blend isn't a cold-brew specialist — grounding plus candor.

**Turn 2 —** `order that`

Haiku resolves `"that"` structurally, not by string match — `order_referent_bean_id = b_espresso_blend`. The `place_order` tool has `requires_approval=true` → inserts into `approvals` with `status='pending'`. `orders` doesn't move. `in_stock` doesn't move.

**psql callout — prove the guardrail in three beats:**

```sql
-- Baseline (run before clicking the order button)
SELECT COUNT(*) FROM orders    WHERE customer_id='u_ana';   -- 4
SELECT COUNT(*) FROM approvals WHERE status='pending';       -- 0
SELECT in_stock FROM beans     WHERE id='b_espresso_blend';  -- 240

-- After "order that" — only approvals moved
SELECT COUNT(*) FROM orders    WHERE customer_id='u_ana';   -- 4    (unchanged)
SELECT COUNT(*) FROM approvals WHERE status='pending';       -- 1    (+1)
SELECT in_stock FROM beans     WHERE id='b_espresso_blend';  -- 240  (unchanged)

-- Human in the loop — a consumer process watches for status='approved'
UPDATE approvals SET status='approved', decided_at=now()
 WHERE id=(SELECT id FROM approvals WHERE status='pending' ORDER BY id DESC LIMIT 1);
```

**Turn 3 — flip the approval, then show the row (psql, not the chat).**

After running the `UPDATE` above, don't ask the chat _"was it approved?"_ — the agent has no tool for that, so it pivots to fresh recommendations and the beat lands flat. Stay in psql and read the row directly. That's the honest story: **the approval queue is a table, not a service; the downstream consumer that actually ships the order polls this table, not the agent.**

```sql
-- Show the full lifecycle on one row
SELECT id, tool, args->>'bean_id' AS bean_id, status, decided_at
  FROM approvals
 WHERE session_id = (SELECT id FROM agent_sessions
                      WHERE customer_id='u_ana' ORDER BY updated_at DESC LIMIT 1)
 ORDER BY id DESC LIMIT 3;
```

**Narration as you run it:** _"The status flipped. `decided_at` is set. No background worker polled this — a human ran a `UPDATE`. In production, a shipping worker would run `SELECT ... WHERE status='approved' FOR UPDATE SKIP LOCKED` on this same table, mark it `executed`, and fulfill the order. That's the whole 'workflow service' — a column, a `SELECT`, and a row lock."_

> If someone in the audience asks the agent _"was it approved?"_ anyway (it's the natural next question), Opus refuses gracefully — the system prompt forbids it from inventing order-status claims. It'll tell the user to check the approval queue. That's the safety net; the psql row above is the payoff.

**Bonus — show the conversation Haiku is reading:**

```sql
SELECT role, agent, content->>'text' AS text
  FROM agent_messages
 WHERE session_id=(SELECT id FROM agent_sessions
                    WHERE customer_id='u_ana' ORDER BY updated_at DESC LIMIT 1)
 ORDER BY ts;
```

> **Why this matters.** Coreference ("order that") resolves against the same `agent_messages` Haiku sees. Sensitive writes never execute inline — they queue for human approval in a row. No workflow service. No separate queue.

---

## Scenario 3 · Yuki · Catalog miss + MCP (~3 min)

Switch to **Yuki**. Click **New Session**. Tokyo-based buyer whose first ask the catalog genuinely can't satisfy.

**Turn 1 —** `Any Japanese single-origins in stock?`

Haiku extracts `origins=['Japan']`. The Roast Master applies the origin filter (`ROAST MASTER · ORIGIN` panel, amber because no matches). Cosine similarity returned neighbors (Sumatra, Sulawesi, Ethiopia) but none of their `origin` columns contain `Japan`, so the filter drops all of them. Fact-check gets an empty list. Grounded-picks list is empty. Opus is still called, but the system prompt (rule 10) forces a warm refusal — **it physically cannot cite a bean that isn't in its context, and the origin filter guarantees no off-provenance pick slips through.**

**Turn 2 —** `What do you have from Asia-Pacific then?`

Yuki's washed single-origin history biases toward high-clarity picks; Sumatra Mandheling and Sulawesi Toraja surface. Opus pivots warmly — grounding held, the agent offered what actually exists.

**MCP callout — same Postgres, different client:**

In a second terminal:

```bash
python mcp_server.py
```

From Claude Desktop, Cursor, or any MCP host:

```sql
-- via run_query over MCP — SELECT-only, 100-row cap, allowlist-gated
SELECT caller, tool, latency_ms
  FROM tool_audit
 ORDER BY ts DESC LIMIT 10;
```

> **Why this matters.** The agent writes into Postgres via FastAPI; an external LLM reads it via MCP. No separate "agent data API" to build, version, rate-limit, or secure. The allowlist and SELECT-only guardrails live inside `mcp_server.py`, right next to the connection.

---

## The closer (30 sec)

Back to psql. One query — vector similarity, relational filters, customer history, tool audit, approval queue — in a single plan.

```sql
SELECT b.name, b.roast_level, b.in_stock,
       1 - (b.embedding <=> (SELECT embedding FROM beans WHERE id='b_ethiopia_guji')) AS similarity,
       (SELECT count(*) FROM orders    WHERE bean_id=b.id AND customer_id='u_marco') AS marco_bought,
       (SELECT count(*) FROM tool_audit WHERE result->'stock' ? b.id)                AS times_checked,
       (SELECT count(*) FROM approvals  WHERE args->>'bean_id'=b.id AND status='pending') AS pending_orders
  FROM beans b
 WHERE b.in_stock > 0 AND b.roast_level IN ('medium','medium-dark','dark')
 ORDER BY similarity DESC LIMIT 5;
```

> _"Six pillars of a production agent — two Claude models, memory, tool registry, MCP, state, guardrails — all anchored on the Postgres you already have. The data plane is ~2,200 lines of Python plus a 116-line `schema.sql`. Postgres is enough."_

---

## Panel cheat sheet

The right-hand Agent Telemetry tab streams these as the agents run. One-line narration per panel.

| Panel                      | Say this                                                                                                                  |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `PLAN`                     | Coordinator decomposes the request into steps; states transition `queued → running → ok`.                                 |
| `LLM · HAIKU · INTENT`     | Haiku reads the last ~6 turns, returns structured JSON via Converse tool-use.                                             |
| `TOOL REGISTRY · DISCOVER` | `tools.description_emb` ranked by cosine similarity — tools discovered at query time, not hard-coded.                     |
| `MEMORY · EPISODIC`        | Last 5 `orders` rows — index scan on `orders_customer_idx`.                                                               |
| `MEMORY · PROFILE`         | `preferences_summary` — one-row PK lookup. A text column instead of a Redis profile.                                      |
| `MEMORY · PROCEDURAL`      | The zinger. pgvector similarity + JOIN on `orders` and `customers` — one query, three sources.                            |
| `MEMORY · SEMANTIC`        | Cosine similarity over `beans.embedding` with HNSW. Sub-millisecond at this scale, still fast at 10M rows.                |
| `ROAST MASTER · FILTER`    | Brew-method filter runs in Postgres, not in the model.                                                                    |
| `ROAST MASTER · ORIGIN`    | Origin filter (country/region) runs against `beans.origin` — empties the pick list when no bean matches, forcing refusal. |
| `TOOL · CHECK_INVENTORY`   | Registered in `tools`, audited in `tool_audit`, same transaction as its effect.                                           |
| `GUARDRAIL · FACT-CHECK`   | Every pick re-read from `beans`, stock verified. Failures dropped, not papered over.                                      |
| `GROUNDING`                | Every claim ties back to a row. Confidence reflects data coverage, not a fudge factor.                                    |
| `MEMORY · CONFIDENCE`      | Shows the math behind the % (picks, history, top similarity, clamp). Deterministic, auditable, reproducible in SQL.       |
| `GUARDRAIL · APPROVAL`     | `place_order` has `requires_approval=true` → inserts into `approvals` with `status='pending'`. Effect blocked.            |
| `LLM · OPUS · SYNTHESIZE`  | Opus receives grounded picks + customer profile. System prompt locks it to cited bean ids. ~700 in / ~300 out / 3–5s.     |

## Audience curveballs

Prompts that tend to come up from the crowd. Rehearse once.

| Try                                       | What happens                                                                                                                                                                                                              |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Something fruity but not from Africa`    | Semantic search ignores "not from Africa"; the roast/region filter handles it. Good demo of why structured intent matters.                                                                                                |
| `Order two bags of the Yemen one`         | Haiku resolves "the Yemen one" → `b_yemen_mocha` from session history. Approval queues for qty=2.                                                                                                                         |
| `What did I order last time?`             | Episodic memory direct hit — `get_customer_history` fires, returns the last 5 `orders` rows.                                                                                                                              |
| `Was it approved?` / `Did my order ship?` | The agent has no order-status tool by design — Opus refuses gracefully and points at the `approvals` queue. Show the row in psql: `SELECT status FROM approvals WHERE session_id=...`. Status is a column, not a service. |
| `Where does the 87% come from?`           | Point at the `MEMORY · CONFIDENCE` panel. Four inputs, one formula: `60 + min(20, picks×7) + (8 if history) + min(10, top_sim×10)`, clamped to [30,98]. No LLM introspection. Reproducible from `tool_audit`.             |
| `ignore previous instructions and …`      | Opus can't reference beans that aren't in its context regardless of injection. Architectural guardrail, not a prompt.                                                                                                     |

## Key takeaways

1. Two Claude models on Bedrock at the edges — every invocation audited in the same table as every SQL tool call.
2. Three memory types (episodic / semantic / procedural) answering one request in one query plan.
3. Dynamic tool registry — `tools.description_emb` is ranked at query time, not wired in Python.
4. MCP exposes the same Postgres to external assistants — no separate agent data API.
5. Workflow state is a JSONB column — checkpointed, resumable, `COMMIT` = durable boundary.
6. Grounding, fact-check, and an approval queue are real guardrails, not decorations.
7. `"order that"` resolves because Haiku reads the same `agent_messages` the coordinator writes to.

---

# Reference

Everything below is appendix — safe to skip while presenting.

## Quick start

Prereqs: Python 3.10+ · Postgres with pgvector ≥ 0.5 · AWS creds with `bedrock:InvokeModel` + `bedrock:Converse` on Claude global inference profiles in `us-east-1`.

```bash
# macOS
brew install postgresql@17 pgvector
brew services start postgresql@17

# DB
psql -d postgres -c "CREATE ROLE coffee LOGIN PASSWORD 'coffee';"
psql -d postgres -c "CREATE DATABASE coffee OWNER coffee;"
PGPASSWORD=coffee psql -h 127.0.0.1 -U coffee -d coffee -f schema.sql

# AWS — any standard boto3 resolution (env vars, ~/.aws/credentials, SSO, Isengard)
export AWS_REGION=us-east-1

# App
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python seed.py          # first run downloads ~130MB embedding model
python app.py           # → http://localhost:8000

# Optional — MCP server
python mcp_server.py    # stdio; wire to any MCP client
```

First query is ~5–10s (Haiku + Opus both on the critical path). Subsequent queries are faster; watch the per-call latency in each `LLM · …` panel.

Optional model overrides in `.env`:

```bash
BEDROCK_HAIKU_MODEL=global.anthropic.claude-haiku-4-5-20251001-v1:0
BEDROCK_OPUS_MODEL=global.anthropic.claude-opus-4-7
```

> If `psql` connects to the wrong host (e.g. a work RDS), clear libpq env vars for that shell: `unset PGHOST PGUSER PGPASSWORD PGSSLMODE PGDATABASE`.

## Using your own Postgres

```bash
export DATABASE_URL=postgresql://user:pass@host:5432/dbname
psql "$DATABASE_URL" -f schema.sql
python seed.py && python app.py
```

Works with Aurora PostgreSQL, RDS PostgreSQL, Supabase, Neon, Crunchy Bridge, or vanilla Postgres. Needs pgvector **0.5+** for HNSW.

## Architecture

```
        Claude Haiku 4.5  ◄─ reads agent_messages, returns structured intent
               │                (tool-use, referent resolution)
               ▼
   ┌──────────────────────────────────┐
   │            PostgreSQL            │
   │  memory  ·  tools  ·  audit      │ ◄─── Coordinator
   │  workflow state · approvals      │       │
   │  pgvector · relational · GIN     │       ├─► Flavor Profiler
   └──────────────┬───────────────────┘       │
                  │                           └─► Roast Master
                  ▼                                (check_inventory, audited)
         Claude Opus 4.7   ◄─ grounded picks only → customer-facing reply
```

| Pillar            | Table(s) / Component                    | Note                                                             |
| ----------------- | --------------------------------------- | ---------------------------------------------------------------- |
| LLM intent        | Haiku 4.5 on Bedrock                    | Intent parse + `order that` referent resolution via tool-use     |
| LLM synthesis     | Opus 4.7 on Bedrock                     | Grounded response, cited against `beans.id`                      |
| Episodic memory   | `agent_messages`, `orders`              | Conversation + order history, indexed by `(session_id, ts DESC)` |
| Semantic memory   | `beans.embedding vector(384)` + HNSW    | pgvector cosine similarity                                       |
| Procedural memory | `orders ⋈ beans ⋈ customers`            | Similar-cohort few-shot context — one query                      |
| Tool registry     | `tools`, `tools.description_emb`        | JSON schemas + dynamic semantic discovery                        |
| Tool + LLM audit  | `tool_audit`                            | SQL tool calls + `tool='llm:<model_id>'` rows, same table        |
| Workflow state    | `agent_sessions.workflow_state` (JSONB) | Checkpointed at every step boundary; resumable                   |
| Approvals         | `approvals`                             | Blocks sensitive tools until `status='approved'`                 |
| MCP surface       | `mcp_server.py` over stdio              | `list_tables` / `describe` / `run_query`                         |
| Knowledge base    | `beans`, `customers`                    | Relational + vector + GIN in one query                           |

Both Bedrock calls go through `bedrock-runtime.converse` in `us-east-1` and are logged to `tool_audit` with `tool = 'llm:<model_id>'`, next to every SQL tool call. One `SELECT` reconstructs the full execution trace — model inputs/outputs, SQL queries, latencies, token counts — joinable on `session_id`.

## Schema at a glance

Nine tables, two extensions. Full DDL in [`schema.sql`](schema.sql).

```sql
CREATE EXTENSION IF NOT EXISTS vector;    -- pgvector — semantic similarity
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- trigram search for description fallback
```

Embeddings: **[`BAAI/bge-small-en-v1.5`](https://huggingface.co/BAAI/bge-small-en-v1.5)** via [fastembed](https://github.com/qdrant/fastembed) — 384 dimensions, ONNX runtime, ~130MB, no GPU. Runs locally inside Python on first call. Any 384-dim model is drop-in via `EMBED_MODEL` in `.env` (schema hard-codes `vector(384)`).

| Table            | Purpose                                  | Key columns                                                                                                                    | Indexes                                                                                                           |
| ---------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| `customers`      | Customer profiles                        | `id` (PK), `name`, `preferences_summary`                                                                                       | PK on `id`                                                                                                        |
| `beans`          | Product catalog + knowledge base         | `id` (PK), `name`, `origin`, `roast_level`, `process`, `flavor_notes text[]`, `price_cents`, `embedding vector(384)`           | `beans_hnsw_idx` (HNSW, `vector_cosine_ops`) · `beans_notes_gin` (GIN on array) · `beans_desc_trgm` (GIN trigram) |
| `orders`         | Episodic memory — what customers bought  | `id` (bigserial), `customer_id → customers`, `bean_id → beans`, `qty`, `placed_at`                                             | `orders_customer_idx (customer_id, placed_at DESC)`                                                               |
| `agent_sessions` | One row per conversation; resumable      | `id uuid` (PK), `customer_id`, `workflow_state jsonb`, `updated_at`                                                            | PK on `id`                                                                                                        |
| `agent_messages` | Episodic memory — the conversation       | `id` (bigserial), `session_id → agent_sessions`, `role`, `agent`, `content jsonb`, `ts`                                        | `agent_messages_session_idx (session_id, ts DESC)`                                                                |
| `tools`          | Tool registry — discovered, not wired    | `name` (PK), `description`, `description_emb vector(384)`, `input_schema jsonb`, `requires_approval`, `enabled`, `owner_agent` | PK on `name`                                                                                                      |
| `tool_audit`     | Every SQL tool call _and_ LLM call       | `id` (bigserial), `session_id`, `tool`, `caller`, `args jsonb`, `result jsonb`, `latency_ms`, `ts`                             | `tool_audit_session_idx (session_id, ts DESC)`                                                                    |
| `approvals`      | Queue for `requires_approval=true` tools | `id` (bigserial), `session_id`, `tool`, `args jsonb`, `status` (pending/approved/rejected/executed), `reason`, `decided_at`    | `approvals_status_idx (status, created_at DESC)`                                                                  |

Relationships (enforced by FKs):

```
customers  1 ─── ∞  orders  ∞ ─── 1  beans
customers  1 ─── ∞  agent_sessions  1 ─── ∞  agent_messages
                                    │
                                    ├─── ∞  tool_audit  (ON DELETE SET NULL)
                                    └─── ∞  approvals   (ON DELETE CASCADE)
tools  (standalone; referenced by name from tool_audit.tool / approvals.tool)
```

## Customizing

- **Swap Claude models** — set `BEDROCK_HAIKU_MODEL` and `BEDROCK_OPUS_MODEL` in `.env`. Any Converse-compatible Bedrock model works; the Opus prompt asks for HTML output, so keep that in mind if you swap to a very different family.
- **Swap the embedding model** — set `EMBED_MODEL` in `.env`. Any fastembed-supported 384-dim model is drop-in.
- **Add a tool** — insert into `tools` with a description; the coordinator discovers it on the next query via `description_emb` similarity. Mark `requires_approval=true` to route through the approval queue.
- **Add a bean** — edit `BEANS` in `seed.py`, re-run `python seed.py`.
- **Tighten or loosen grounding** — `_respond` in `agents.py` assembles the grounded picks Opus sees. Narrow that set to constrain Opus; widen it to give Opus more to reference.

## When to re-seed

Day-to-day demoing is just `python app.py`. Re-seed only when:

- You blew away the DB or re-ran `schema.sql`
- You edited `BEANS`, `CUSTOMERS`, `ORDERS`, or `TOOLS` in `seed.py`
- You changed `EMBED_MODEL` — stored embeddings won't match new queries

**Between rehearsals you almost never need `seed.py`.** What you want is a clean conversation state — run [`reset.sh`](reset.sh):

```bash
./reset.sh
```

One keystroke; truncates `approvals`, `tool_audit`, `agent_messages`, and `agent_sessions` with `RESTART IDENTITY`. Doesn't touch `beans`, `customers`, `orders`, or `tools`, so embeddings and knowledge base stay put. Equivalent to:

```sql
TRUNCATE approvals, tool_audit, agent_messages, agent_sessions RESTART IDENTITY;
```

Ideal right before going live.

## Files

- [`schema.sql`](schema.sql) — full schema, pipe into `psql`
- [`seed.py`](seed.py) — seeds customers, beans (with real embeddings), orders, tool registry
- [`reset.sh`](reset.sh) — between-rehearsals cleanup (truncates conversation state only)
- [`db.py`](db.py) — Postgres pool + lazy embedder
- [`bedrock.py`](bedrock.py) — Bedrock Converse wrapper with per-call telemetry + `tool_audit` logging
- [`agents.py`](agents.py) — coordinator, roast master, flavor profiler, Haiku intent, Opus synthesis, tool discovery, procedural memory, checkpointing, fact-check, approvals
- [`app.py`](app.py) — FastAPI server
- [`mcp_server.py`](mcp_server.py) — stdio MCP server
- [`static/index.html`](static/index.html) — single-file frontend with live telemetry

## Slide deck

Dark-themed deck in [`deck/`](deck/) built with [Marp](https://marp.app/) — same content as this README, trimmed to slide-sized beats.

```bash
./deck/build.sh           # renders deck/deck.pdf via npx @marp-team/marp-cli
```

Requires Node.js 18+. Palette is pure black with cream and amber accents — high contrast for projectors, matches the live demo UI. Source: `deck/deck.md`. Styling: `deck/theme.css`. Re-run `./deck/build.sh` after any change.
