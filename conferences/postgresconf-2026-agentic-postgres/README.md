# Building Agentic AI Applications with PostgreSQL as the Backbone

> Memory systems, tool registries, MCP integration, and guardrails for production agents — driven by Claude on Amazon Bedrock.
>
> Live demo for **[Postgres Conference: 2026](https://postgresconf.org/)** — San Pedro (Level C), Tuesday April 21, 15:00 PDT · 50 min · Dev track.

The AI landscape is shifting from chatbots to autonomous agents — systems that plan, use tools, maintain memory, and take actions. The model is only half the story. The real differentiator for production agents is the **data layer**. This demo argues the data layer doesn't need five systems. It needs one: **PostgreSQL**.

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
                  │                            └─► Roast Master
                  ▼                                (check_inventory, audited)
         Claude Opus 4.7   ◄─ grounded picks only → customer-facing reply
```

Two Claude models on Amazon Bedrock drive the pipeline — Haiku parses intent and resolves referential phrases like _"order that"_ against the conversation; Opus composes the customer-facing reply from grounded picks only. Every LLM call is audited in the same table as every SQL tool call. No AgentCore. No Pinecone. No Redis. No Lambda. One database, one query language, one transaction — playing every role a production agent needs.

> **Key takeaway — the split that matters.** The LLMs live at the edges: input parsing (Haiku) and output synthesis (Opus). **Everything in between is Postgres.** Memory lookups, tool discovery, similarity search, filters, inventory checks, fact-checking, approvals — none of it hits a model. The agent is mostly SQL, and SQL is the thing the audience already runs in production.

---

## The six pillars

The session is organized around six pillars, each one backed by a concrete table (or a Bedrock model) and a live, inspectable telemetry panel. The SQL shown in the UI is the SQL that actually ran. The LLMs at the edges are visible in the telemetry too — every Haiku and Opus call emits an `LLM · …` panel with model id, tokens, latency, and stop reason.

### 1. Two-model pipeline on Bedrock

| Stage                              | Model            | Bedrock inference profile                         | Role                                                                                                                                                                                                                                                                                                                                            |
| ---------------------------------- | ---------------- | ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Intent parse + referent resolution | Claude Haiku 4.5 | `global.anthropic.claude-haiku-4-5-20251001-v1:0` | Reads the latest customer message + last ~6 turns of chat history, returns structured JSON via [Converse tool-use](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html): `brew_method`, `explicit_roasts`, `budget_cents`, `wants_order`, and `order_referent_bean_id` (e.g. _"order that"_ → `b_espresso_blend`). |
| Response synthesis                 | Claude Opus 4.7  | `global.anthropic.claude-opus-4-7`                | Receives only the **grounded picks** (beans that passed roast/brew filters, inventory check, and fact-check) plus the customer's profile and recent orders. System prompt constrains it to cite only bean ids from that list and never invent prices or flavor notes.                                                                           |

Both calls go through `bedrock-runtime.converse` in `us-east-1` and are logged to `tool_audit` with `tool = 'llm:<model_id>'`, next to every SQL tool call. That means the audit table holds the complete execution trace in one place — model calls and database effects, same row format, same session id.

> **Key takeaway — LLMs at the edges, data in the middle.** Inference is where Claude earns its keep: natural-language → structured intent on the way in, grounded picks → warm-but-faithful reply on the way out. Replace either model tomorrow and nothing in Postgres changes. The data contract (`intent → picks → citations`) is stable.

### 2. Memory Architecture

Agents need three kinds of memory with different access patterns. All three live in Postgres.

| Memory                                                 | Where                                | Access pattern                         |
| ------------------------------------------------------ | ------------------------------------ | -------------------------------------- |
| **Episodic** — the conversation + recent actions       | `agent_messages`, `orders`           | `WHERE session_id=$1 ORDER BY ts DESC` |
| **Semantic** — domain knowledge retrievable by meaning | `beans.embedding vector(384)` + HNSW | `ORDER BY embedding <=> $1`            |
| **Procedural** — patterns learned from past behavior   | `orders ⋈ beans ⋈ customers`         | similarity + join in one query         |

The procedural panel is where Postgres wins loudest: one query joins a pgvector similarity result with `orders` and `customers` to surface _"cohorts similar to this request have actually bought X"_ as few-shot context for the response synthesizer.

> **Key takeaway — three memory types, one JOIN.** Episodic lives in `orders`, semantic lives in `beans.embedding`, procedural is the _relation between them_ — which only exists cleanly when both are in the same database. A vector DB holding embeddings separate from your orders table cannot express "customers with similar taste to this request actually bought X" in one query.

### 3. Tool and Function Registries

Tools aren't a hard-coded Python list. They live in a table:

```sql
CREATE TABLE tools (
  name              text PRIMARY KEY,
  description       text NOT NULL,
  description_emb   vector(384),   -- for semantic discovery
  input_schema      jsonb NOT NULL,
  requires_approval boolean NOT NULL DEFAULT false,
  enabled           boolean NOT NULL DEFAULT true,
  owner_agent       text
);
```

At query time the coordinator ranks `description_emb` against the user request and picks the top-k relevant tools — **dynamic discovery, not a static toolbox**. Every invocation is written to `tool_audit` in the same transaction as its effect, so the audit log and the state can never disagree.

> **Key takeaway — the audit table holds everything.** `tool_audit` captures SQL tool calls _and_ LLM calls (stored as `tool = 'llm:<model_id>'`). One `SELECT` reconstructs the full execution trace for any session — model inputs and outputs, SQL queries, latencies, token counts, all joinable on `session_id`. That's a post-incident review that doesn't require four dashboards.

### 4. Model Context Protocol (MCP) Integration

The same database is addressable from any MCP-compatible client. [`mcp_server.py`](mcp_server.py) is a small stdio MCP server exposing:

- `list_tables` — schema introspection with approximate row counts
- `describe(table)` — columns + indexes, gated by an allowlist
- `run_query(sql, params)` — **SELECT-only**, parameterized, DDL/DML rejected, 100-row cap

Claude Desktop, Cursor, or any MCP host can point at this process and query the agent's memory, tools, and audit log directly.

> **Key takeaway — the same Postgres is two interfaces.** The agent writes into it via the FastAPI pipeline; an external LLM reads it via MCP. No separate "agent data API" to build, version, rate-limit, or secure — the allowlist and SELECT-only guardrails live inside `mcp_server.py`, right next to the connection.

### 5. State Management

Complex agents maintain state across multi-step tasks. The plan and current step index are checkpointed to `agent_sessions.workflow_state` as JSONB after every step boundary:

```json
{
  "stage": "roast_master_filter",
  "step_index": 3,
  "query": "Cold brew options"
}
```

If the process dies mid-task, the next call can resume from the checkpoint rather than restarting. Same-transaction guarantees mean the checkpoint never drifts from the side effects.

> **Key takeaway — durable state is a column, not a service.** No separate state store, no Temporal, no Step Functions. The plan is a JSONB column; a `COMMIT` is your checkpoint. The demo even survives `Ctrl-C` mid-run and picks back up from `workflow_state->>'step_index'` on the next request.

### 6. Grounding and Guardrails

Agents hallucinate. Three layers keep them honest:

- **Fact-check pass** — every pick is re-read from `beans` and verified for stock before the reply is composed. Failed verifications are dropped, not papered over.
- **Confidence score** — derived from _data availability_ (row coverage, history match, similarity top score), not a fudge factor.
- **Approval workflow** — tools flagged `requires_approval=true` (like `place_order`) never execute inline. They insert a row into `approvals` with `status='pending'` and block until approved.

Try the **Place an order** quick query to watch an approval row get queued.

> **Key takeaway — grounding is the guardrail Opus can't bypass.** The synthesizer's system prompt hands it only the beans that already passed fact-check. It cannot reference a bean we don't have because we don't put one in its context. Hallucination gets engineered out at the SQL layer, not prompted away.

---

## Quick start

Prereqs:

- **Python 3.10+**
- **PostgreSQL with pgvector ≥ 0.5** (required for HNSW)
- **AWS credentials** with `bedrock:InvokeModel` and `bedrock:Converse` on the Claude global inference profiles in `us-east-1` (or whatever region you point at)

On macOS:

```bash
brew install postgresql@17 pgvector
brew services start postgresql@17
```

Provision the database:

```bash
psql -d postgres -c "CREATE ROLE coffee LOGIN PASSWORD 'coffee';"
psql -d postgres -c "CREATE DATABASE coffee OWNER coffee;"
PGPASSWORD=coffee psql -h 127.0.0.1 -U coffee -d coffee -f schema.sql
```

Configure AWS credentials — any standard boto3 resolution works (env vars, `~/.aws/credentials`, SSO, Isengard):

```bash
export AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
# or: export AWS_PROFILE=my-profile
```

Optionally override the model IDs in `.env`:

```bash
BEDROCK_HAIKU_MODEL=global.anthropic.claude-haiku-4-5-20251001-v1:0
BEDROCK_OPUS_MODEL=global.anthropic.claude-opus-4-7
```

Python deps + seed + run:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python seed.py          # first run downloads a ~130MB embedding model
python app.py           # → http://localhost:8000
```

The first query will be ~5–10 seconds because both Haiku and Opus are on the critical path. Subsequent queries are faster; watch the per-call latency in each `LLM · …` telemetry panel.

Optional — run the MCP server:

```bash
python mcp_server.py    # stdio; wire to any MCP client
```

> If `psql` connects to the wrong host (e.g. a work RDS), clear libpq env vars for that shell: `unset PGHOST PGUSER PGPASSWORD PGSSLMODE PGDATABASE`.

## Using your own Postgres

```bash
export DATABASE_URL=postgresql://user:pass@host:5432/dbname
psql "$DATABASE_URL" -f schema.sql
python seed.py && python app.py
```

Works with Aurora PostgreSQL, RDS PostgreSQL, Supabase, Neon, Crunchy Bridge, or vanilla Postgres. Needs pgvector **0.5+** for HNSW.

---

# Demo run script

A ~11 minute walkthrough mapped to the six pillars. Every callout below corresponds to something you can **point at on screen** — a panel in the right-hand Agent Telemetry tab, a row in the database, or a line of code.

Open two windows side by side:

- **Browser**: `http://localhost:8000`
- **psql**: `PGPASSWORD=coffee psql -h 127.0.0.1 -U coffee -d coffee` — for live _"look, it's really in Postgres"_ moments.

---

## 0. Set the stage (30 sec)

> "Three agents. Two Claude models on Bedrock. One Postgres. No vector DB, no queue, no cache, no orchestrator. Let's see what breaks — spoiler: nothing."

**Show** the layout:

- Left — the chat. Pick a customer, send a query.
- Right (default tab: **Architecture**) — the pillars of the agent, each backed by a Postgres table (plus the two Claude models at the edges).
- Right (**Agent Telemetry** tab) — every SQL query, tool call, grounding check, and approval in real time.
- Top — API endpoint, user selector, **New Session** button.

**Click** through the three users once. Marco is a fruity pour-over drinker, Ana does dark espresso, Jordan chases light-roast micro-lots.

---

## 1. Memory Architecture — one query fires, three kinds of memory fire (3 min)

Pick **Marco**. Click **Cold brew**.

The telemetry tab auto-flips and panels stream in. Walk through each:

### Panel: `PLAN`

> "Coordinator decomposes the request into five steps. Steps transition `queued → running → ok` as the agents work. This is the workflow plan."

### Panel: `LLM · HAIKU · INTENT`

> "Haiku 4.5 reads the user message and the recent conversation, then calls a `record_intent` tool with structured JSON. `brew_method=cold_brew`, no roast override, no budget, no order. The `reasoning` field in the panel is a one-sentence explanation — it's not for grounding, it's for _you_ when you debug."
>
> "Notice `order_referent_bean_id` is null here. It'll light up in the follow-up turn when we say 'order that'. Haiku handles coreference so the coordinator doesn't have to."

**Switch to psql**:

```sql
SELECT caller, tool, latency_ms, result->>'input_tokens' AS in_tok,
       result->>'output_tokens' AS out_tok
  FROM tool_audit
 WHERE tool LIKE 'llm:%'
 ORDER BY ts DESC LIMIT 3;
```

> "LLM calls live in the same audit table as SQL tool calls. One `SELECT` gets you the full trace."

### Panel: `TOOL REGISTRY · DISCOVER`

> "Dynamic tool discovery. We embed the request and rank `tools.description_emb` by cosine similarity. The coordinator picks tools at query time instead of hard-coding its toolbox. `check_inventory` and `search_beans_semantic` come out on top for cold brew. `place_order` sits near the bottom — it's not what was asked for."

**Switch to psql**:

```sql
SELECT name, owner_agent, requires_approval FROM tools;
```

> "Four tools. Three read, one writes. The write tool needs approval — we'll get to that."

### Panel: `MEMORY · EPISODIC`

> "Marco's last 5 orders — Yirgacheffe, Guji, Kenya AA, Rwanda. Plain index scan on `orders_customer_idx`. Episodic memory is just a join."

### Panel: `MEMORY · PROFILE`

> "And his `preferences_summary` — one-row PK lookup. In a lot of stacks this lives in Redis or a vector DB profile. Here it's a TEXT column."

### Panel: `MEMORY · PROCEDURAL` (the zinger)

> "Here's procedural memory. We embed the current request, then rank beans by similarity _while joining into the orders table_ to find which beans customers with similar taste actually bought. **One query, three sources of context** — pgvector, a join, and an aggregation."

Point at the SQL. This is the thing that is difficult when your vectors live in a separate system.

### Panel: `MEMORY · SEMANTIC`

> "Classic pgvector: embed the request, cosine similarity over `beans.embedding` with HNSW. Sub-millisecond at this scale, still fast at 10M rows."

**Switch to psql**:

```sql
\d+ beans
-- point out: beans_hnsw_idx (hnsw, embedding vector_cosine_ops)
```

### Panel: `ROAST MASTER · FILTER`

> "Roast Master applies the brew-method filter. Cold brew → medium / medium-dark / dark. **This filter runs in Postgres, not in the model.** Saves tokens, stays grounded."

### Panel: `TOOL · CHECK_INVENTORY`

> "A tool call — registered in `tools`, audited in `tool_audit`, scoped to Roast Master. Logged in the same transaction as its effect."

**Switch to psql**:

```sql
SELECT id, tool, caller, args, latency_ms FROM tool_audit ORDER BY ts DESC LIMIT 3;
```

> "Every invocation. Rolls back with the effect. Ask Pinecone to do that."

### Panel: `GUARDRAIL · FACT-CHECK`

> "Before we respond, we re-read every candidate from `beans` and verify stock. **Any pick that fails verification is dropped.** The agent doesn't rely on its own cached beliefs."

### Panel: `GROUNDING`

> "Every claim in the response ties back to a row. Confidence reflects data coverage — not a vibe."

### Panel: `LLM · OPUS · SYNTHESIZE`

> "Now — and only now — we call Opus 4.7. The prompt hands it three things: the customer's profile, the recent order history, and the **grounded picks** we just verified. The system prompt locks Opus to citing only those bean ids and forbids inventing prices, origins, or flavor notes."
>
> "Look at the tokens — in ≈ 700, out ≈ 300, ~3–5 seconds. That's the entire LLM cost for this turn. Intent and grounding happened earlier; this is just writing."

### Response

> "Dashed underlines are citations — hover to see the Postgres row key. Opus referenced Marco's run of Ethiopian lots because we handed it his order history; it didn't need to be told to personalize. But it _cannot_ mention a bean we didn't include in the grounded picks, because we didn't put one in its context."

---

## 2. State Management — check the workflow state (1 min)

**Switch to psql**:

```sql
SELECT id, customer_id, workflow_state, updated_at
  FROM agent_sessions ORDER BY updated_at DESC LIMIT 1;
```

> "The plan and current step index were checkpointed to `workflow_state` JSONB after every step. If this process died mid-run, the next call could resume from `step_index` instead of replaying the plan. Same transaction as the side effects — the checkpoint can't drift."

---

## 3. Memory that matters — switch users (1 min)

Change user to **Ana**. Send **Cold brew** again — same query string.

**Compare**: Ana gets a different set of picks and a different tone.

> "Query string is identical. What changed is the _memory_. Ana's history is dark roasts and the House Blend; her `preferences_summary` biases toward chocolate and low acid. So the procedural panel pulls different cohorts, the embedding input changes, cosine search lands in a different neighborhood, and Opus gets a different profile in its context. Same agents, same query, different memory, different answer."

---

## 3b. Chat continuity — "order that" (1 min)

Stay on **Ana**'s session. Click **Place an order** (which sends _"Order a bag of cold brew"_), or type **"order that"** into the input.

Point at two panels:

### Panel: `LLM · HAIKU · INTENT`

> "Look at `order_referent_bean_id`. Haiku read the last six turns of this session — the previous `coordinator` reply cited `beans.b_espresso_blend` — and resolved 'that' to the same bean id. No brittle coreference code on our side; it's a structured field in the tool-use output."

### Panel: `GUARDRAIL · APPROVAL`

> "The `approvals` row is for the bean we actually recommended last turn. Without the LLM-resolved referent, re-running semantic search on the string 'order a bag of cold brew' lands on a different top hit — Honduras Marcala — and the customer would see a bait-and-switch."

**Switch to psql**:

```sql
SELECT role, agent, content->>'text' AS text,
       jsonb_array_length(COALESCE(content->'citations','[]'::jsonb)) AS cites
  FROM agent_messages
 WHERE session_id = (SELECT id FROM agent_sessions ORDER BY updated_at DESC LIMIT 1)
 ORDER BY ts;
```

> "The conversation lives in `agent_messages`. Haiku reads this same table to resolve references. The LLM and the coordinator share a memory, and that memory is a boring SQL table."

---

## 4. Grounding and Guardrails — refusal + approval (2 min)

### Refusal path

Type **rare Japanese single-origin under $5**.

Grounding goes red-ish (_"No stocked bean matched"_), confidence drops to 30%, and Opus is called with an empty grounded-picks list. Its system prompt forces it to refuse briefly instead of pitching a substitute.

> "Opus is still in the loop — the demo never falls back to template strings. But the grounded picks we hand it are empty, so its prompt constrains it to a short, warm refusal. The agent either grounds against real rows or it refuses. No fallback to the closest plausible thing. Safety is enforced in code _and_ in the system prompt, not left to Opus's judgment."

### Approval workflow

Click **Place an order**.

A `GUARDRAIL · APPROVAL` panel appears — `place_order` queued with `status='pending'`. The effect is **not applied**.

**Switch to psql**:

```sql
SELECT id, tool, args, status, reason FROM approvals ORDER BY id DESC LIMIT 1;
```

> "A row in `approvals`, `status='pending'`. No inventory was deducted, no row inserted into `orders`. A human (or a supervising agent) flips the status to `approved` and a consumer executes it — all in the same database."

---

## 5. MCP integration — the same Postgres, different client (1 min)

**Terminal**:

```bash
python mcp_server.py
```

Hand it a JSON-RPC `tools/list` on stdin (or connect it to Claude Desktop). The three exposed tools:

- `list_tables` — schema introspection
- `describe(table)` — columns + indexes, allowlist-gated
- `run_query(sql, params)` — parameterized SELECT only; DDL/DML rejected; 100-row cap

> "The same database that stores the agent's memory, tools, and audit is a first-class MCP surface. No separate 'agent data API' to build. Your assistant can query `agent_messages`, `tool_audit`, `approvals` — with guardrails baked into the server."

---

## 6. The closer — one query, every pillar (1 min)

**Switch to psql**:

```sql
SELECT b.name,
       b.roast_level,
       b.in_stock,
       1 - (b.embedding <=> (SELECT embedding FROM beans WHERE id='b_ethiopia_guji')) AS similarity,
       (SELECT count(*) FROM orders o
          WHERE o.bean_id = b.id AND o.customer_id = 'u_marco') AS marco_has_bought,
       (SELECT count(*) FROM tool_audit ta
          WHERE ta.result->'stock' ? b.id) AS times_inventory_checked,
       (SELECT count(*) FROM approvals a
          WHERE a.args->>'bean_id' = b.id AND a.status='pending') AS pending_orders
  FROM beans b
 WHERE b.in_stock > 0
   AND b.roast_level IN ('medium','medium-dark','dark')
 ORDER BY similarity DESC
 LIMIT 5;
```

> "One query. Vector similarity, relational filters, customer history, tool audit, approval queue — joined in one plan, one transaction, one optimizer. Draw me that architecture when your vectors are in Pinecone, state is in Postgres, and your audit log is in DynamoDB."

---

## 7. Close (30 sec)

> "Six pillars of a production agent — two Claude models on Bedrock, memory, tool registry, MCP, state, guardrails — all anchored on the Postgres you already have. Claude does what LLMs are actually good at: parsing messy input into structure, and turning grounded facts into warm replies. The data plane in between is ~700 lines of Python plus a `schema.sql`. No orchestration service, no vector DB, no cache, no queue, no separate audit pipeline."
>
> "Postgres is enough."

---

# Architecture reference

| Pillar            | Table(s) / Component                    | Note                                                             |
| ----------------- | --------------------------------------- | ---------------------------------------------------------------- |
| LLM orchestration | Haiku 4.5 on Bedrock                    | Intent parse + `order that` referent resolution via tool-use     |
| LLM synthesis     | Opus 4.7 on Bedrock                     | Grounded response, cited against `beans.id`                      |
| Episodic memory   | `agent_messages`, `orders`              | Conversation + order history, indexed by `(session_id, ts DESC)` |
| Semantic memory   | `beans.embedding vector(384)` + HNSW    | pgvector cosine similarity                                       |
| Procedural memory | `orders ⋈ beans ⋈ customers`            | Similar-cohort few-shot context — one query                      |
| Tool registry     | `tools`, `tools.description_emb`        | JSON schemas + dynamic semantic discovery                        |
| Tool + LLM audit  | `tool_audit`                            | SQL tool calls + `tool='llm:<model_id>'` rows, same table        |
| Workflow state    | `agent_sessions.workflow_state` (JSONB) | Checkpointed at every step boundary; resumable                   |
| Approvals         | `approvals`                             | Blocks sensitive tools until `status='approved'`                 |
| MCP surface       | `mcp_server.py` over stdio              | list_tables / describe / run_query                               |
| Knowledge base    | `beans`, `customers`                    | Relational + vector + GIN in one query                           |

# Files

- [`schema.sql`](schema.sql) — full schema, ready to pipe into `psql`
- [`seed.py`](seed.py) — seeds customers, beans (with real embeddings), orders, tool registry
- [`db.py`](db.py) — Postgres pool + lazy embedder
- [`bedrock.py`](bedrock.py) — Bedrock Converse wrapper with per-call telemetry + `tool_audit` logging
- [`agents.py`](agents.py) — coordinator, roast master, flavor profiler + Haiku intent parsing + Opus synthesis + tool discovery, procedural memory, checkpointing, fact-check, approvals
- [`app.py`](app.py) — FastAPI server
- [`mcp_server.py`](mcp_server.py) — stdio MCP server exposing Postgres to any MCP host
- [`static/index.html`](static/index.html) — single-file frontend with live telemetry

# Customizing

- **Swap the Claude models**: set `BEDROCK_HAIKU_MODEL` and `BEDROCK_OPUS_MODEL` in `.env`. Any Converse-compatible Bedrock model works; the Opus prompt asks for HTML output, so keep that in mind if you swap to a very different family.
- **Swap the embedding model**: set `EMBED_MODEL` in `.env`. Any fastembed-supported 384-dim model is drop-in (schema uses `vector(384)`).
- **Add a tool**: insert into `tools` with a description — the coordinator will discover it on the next query via `description_emb` similarity. Mark `requires_approval=true` to route it through the approval queue.
- **Add a bean**: edit `BEANS` in `seed.py`, re-run `python seed.py`.
- **Change the grounding contract**: `_respond` in `agents.py` assembles the grounded picks that Opus sees. Tighten that set to narrow what Opus can say; loosen it (add procedural-memory cohorts, for instance) to give Opus more to reference. The system prompt enforces the constraint.

---

## Key takeaways

By the end of the session you'll have seen, in a single database:

1. Two Claude models on Bedrock driving the edges, with every invocation audited in the same table as every SQL tool call
2. A three-layer memory system (episodic / semantic / procedural) answering a single user request
3. A dynamic tool registry with embedding-based discovery and per-invocation audit
4. An MCP server exposing the same Postgres surface to external assistants
5. Multi-step workflow state checkpointed and resumable
6. Grounding, fact-checking, and an approval queue as real guardrails — not decorations
7. Conversational continuity (_"order that"_) resolved by Haiku reading the same `agent_messages` table the coordinator writes to

## Why not purpose-built vector DBs?

Joining a vector similarity result with relational filters, customer history, tool audit, approval state, and episodic messages — all in one query plan, one transaction — is something you **can't do cleanly** when your vectors live in Pinecone, your state lives in Postgres, and your queue lives in Redis.

One system. Fewer failure modes. Less to explain.

---

## When do I need to re-seed?

After the first `python seed.py`, day-to-day demoing is just `python app.py`. The seed data (customers, beans, embeddings, tool registry) is static across runs, and re-seeding `TRUNCATE`s everything including the session + audit trail you built up while rehearsing.

Re-seed only when:

- You blew away the DB or re-ran `schema.sql`
- You edited `BEANS`, `CUSTOMERS`, `ORDERS`, or `TOOLS` in `seed.py`
- You changed `EMBED_MODEL` — stored embeddings were produced by the old model and won't match new queries
- You want a completely clean slate for a stage rehearsal

If you want a fresh slate for **just** the session / audit tables (without re-embedding the catalog), run:

```sql
TRUNCATE approvals, tool_audit, agent_messages, agent_sessions RESTART IDENTITY;
```

That clears the demo trail but leaves `beans`, `tools`, `customers`, and `orders` intact — much faster than a full reseed, and ideal before going live on stage.

---

## Presenting this on stage

There's a dark-themed slide deck in [`deck/`](deck/) built with [Marp](https://marp.app/) — same content as the README, trimmed to slide-sized beats.

```bash
./deck/build.sh           # renders deck/deck.pdf (uses npx @marp-team/marp-cli)
```

Requires Node.js 18+. The script pulls `@marp-team/marp-cli` on demand via `npx`, so there's nothing to install globally. Palette is pure black with cream and amber accents — high contrast for projectors, matches the live demo UI.

Want to edit? `deck/deck.md` is the source, `deck/theme.css` is the styling. Re-run `./deck/build.sh` after any change.
