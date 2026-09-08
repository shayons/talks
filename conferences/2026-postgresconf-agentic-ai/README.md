# Coffee & queries

> Memory, tools, MCP, and guardrails for production agents — Claude on Bedrock at the edges, **one Postgres in the middle**.
>
> Live demo for **[PostgresConf 2026](https://postgresconf.org/)** · San Pedro · Tue Apr 21 · 50 min.

Most production-agent stacks glue together Pinecone, Redis, DynamoDB, Postgres, Temporal, SQS, and an orchestrator. This demo collapses the data plane into PostgreSQL: episodic, semantic, and procedural memory; tool registry; audit; workflow state; approvals; and MCP — same database, one query plan when you need it.

Haiku parses intent. Opus synthesizes the reply. **Everything in between is SQL.**

No agent framework, on purpose. Eight dependencies (`fastapi`, `psycopg`, `pgvector`, `fastembed`, `boto3`, `pydantic`, `python-dotenv`, `uvicorn`). [`agents.py`](agents.py) is ~1,500 lines you can read top to bottom. Frameworks are fine in production — LangGraph's `PostgresSaver` is a nice API over a `jsonb` column. This repo skips that layer so the data plane is legible.

---

## Quick start

Python 3.10+ · Postgres + pgvector ≥ 0.5 · AWS creds with `bedrock:InvokeModel` and `bedrock:Converse` in `us-east-1`.

```bash
brew install postgresql@17 pgvector && brew services start postgresql@17

psql -d postgres -c "CREATE ROLE coffee LOGIN PASSWORD 'coffee';"
psql -d postgres -c "CREATE DATABASE coffee OWNER coffee;"
PGPASSWORD=coffee psql -h 127.0.0.1 -U coffee -d coffee -f schema.sql

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python seed.py          # first run downloads ~130MB embedding model
python app.py           # → http://localhost:8000
```

First query is 5–10s (Haiku + Opus). Watch latency on each `LLM · …` panel.

If `psql` hits the wrong host: `unset PGHOST PGUSER PGPASSWORD PGSSLMODE PGDATABASE`.

**Own Postgres** (Aurora, RDS, Neon, etc. — needs pgvector 0.5+):

```bash
export DATABASE_URL=postgresql://user:pass@host:5432/dbname
psql "$DATABASE_URL" -f schema.sql
python seed.py && python app.py
```

**Between rehearsals** run [`./reset.sh`](reset.sh) — truncates session tables, leaves embeddings alone. Re-seed only after `schema.sql`, seed-data edits, or an `EMBED_MODEL` change.

---

## Stage guide

Two windows: browser at `http://localhost:8000`, and

```bash
PGPASSWORD=coffee psql -h 127.0.0.1 -U coffee -d coffee
```

Optional third window for Yuki: `python mcp_server.py`.

Click a regular (or press `1` / `2` / `3`). Stage-guide prompts sit under the composer. **New session** clears conversation state for that customer.

| Regular   | Lesson                         | Profile                                      | Recent orders                          |
| --------- | ------------------------------ | -------------------------------------------- | -------------------------------------- |
| **Marco** | Three memories in one plan     | Medium roast, fruity East African, pour-over | Yirgacheffe → Guji → Kenya AA → Rwanda |
| **Ana**   | Continuity + gated writes      | Dark espresso, chocolatey, buys in quantity  | House Espresso ×3 → Sumatra → Santos   |
| **Yuki**  | Catalog miss + MCP             | Tokyo buyer, Japanese single-origins         | Geisha → Yirgacheffe → Tarrazú         |

Yuki's first ask has no catalog match — that's the point.

**Opener:** _Three agents. Two Claude models. One Postgres. No vector DB, no queue, no cache, no orchestrator._

### 1 · Marco · three memories (~4 min)

Turn 1 — `Cold brew options`. Watch **Agent telemetry**: Haiku extracts `brew_method=cold_brew`; tool discovery ranks `search_beans_semantic`; episodic memory is Marco's last five `orders`; **procedural memory** is the zinger — pgvector similarity `JOIN`ed to `orders` and `customers` in one query. Roast filter and fact-check run in SQL. Opus cites only beans that survived.

Turn 2 — `Something lighter and more floral` (same session). Haiku reads the last six turns, keeps cold brew, biases light/medium-light. Yirgacheffe and Guji Natural surface because Marco's history is in the same `agent_messages` table Haiku is reading.

```sql
SELECT caller, tool, latency_ms,
       result->>'input_tokens' AS in_tok, result->>'output_tokens' AS out_tok
  FROM tool_audit
 WHERE session_id = (SELECT id FROM agent_sessions
                      WHERE customer_id='u_marco' ORDER BY updated_at DESC LIMIT 1)
 ORDER BY ts DESC LIMIT 12;
```

A vector DB sitting apart from `orders` cannot say "customers with similar taste actually bought X." It has to be the same database.

### 2 · Ana · continuity + approvals (~4 min)

Switch to **Ana**, **New session**. Same string — `Cold brew options` — different answer (House Espresso Blend, Sumatra). Then `order that`.

Haiku resolves `"that"` to `b_espresso_blend`. `place_order` has `requires_approval=true` → insert into `approvals` (`pending`). `orders` and `in_stock` do not move.

```sql
-- before / after "order that"
SELECT COUNT(*) FROM orders    WHERE customer_id='u_ana';   -- 4, stays 4
SELECT COUNT(*) FROM approvals WHERE status='pending';       -- 0 → 1
SELECT in_stock FROM beans     WHERE id='b_espresso_blend';  -- 240, stays 240

UPDATE approvals SET status='approved', decided_at=now()
 WHERE id=(SELECT id FROM approvals WHERE status='pending' ORDER BY id DESC LIMIT 1);

SELECT id, tool, args->>'bean_id' AS bean_id, status, decided_at
  FROM approvals
 WHERE session_id = (SELECT id FROM agent_sessions
                      WHERE customer_id='u_ana' ORDER BY updated_at DESC LIMIT 1)
 ORDER BY id DESC LIMIT 3;
```

The queue is a table. A shipping worker would `SELECT … WHERE status='approved' FOR UPDATE SKIP LOCKED`. The agent has no order-status tool — if asked, Opus points at `approvals`.

### 3 · Yuki · catalog miss + MCP (~3 min)

**New session.** `Any Japanese single-origins in stock?` — origin filter empties the pick list (`ROAST MASTER · ORIGIN` goes amber). Opus refuses; it cannot cite a bean that isn't in context.

Then `What do you have from Asia-Pacific then?` — Sumatra Mandheling and Sulawesi Toraja. Grounding held.

Same Postgres, different client:

```bash
python mcp_server.py   # SELECT-only, allowlisted, 100-row cap
```

```sql
SELECT caller, tool, latency_ms FROM tool_audit ORDER BY ts DESC LIMIT 10;
```

### Closer

One plan: similarity, filters, history, audit, approvals.

```sql
SELECT b.name, b.roast_level, b.in_stock,
       1 - (b.embedding <=> (SELECT embedding FROM beans WHERE id='b_ethiopia_guji')) AS similarity,
       (SELECT count(*) FROM orders    WHERE bean_id=b.id AND customer_id='u_marco') AS marco_bought,
       (SELECT count(*) FROM tool_audit WHERE result->'stock' ? b.id)                AS times_checked,
       (SELECT count(*) FROM approvals  WHERE args->>'bean_id'=b.id AND status='pending') AS pending
  FROM beans b
 WHERE b.in_stock > 0 AND b.roast_level IN ('medium','medium-dark','dark')
 ORDER BY similarity DESC LIMIT 5;
```

_Six pillars. ~2,500 lines of Python plus a 116-line `schema.sql`. Postgres is enough._

### Prompts worth trying

| Try                                    | What happens                                                                                          |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `Something fruity but not from Africa` | Semantic search ignores the negation; the origin filter handles it.                                   |
| `Order two bags of the Yemen one`      | Haiku resolves the referent → `b_yemen_mocha`. Approval queues for qty=2.                             |
| `What did I order last time?`          | Episodic hit — last 5 `orders` rows.                                                                  |
| `Was it approved?`                     | No status tool. Show `SELECT status FROM approvals WHERE session_id=…`.                               |
| `Where does the 87% come from?`        | `60 + min(20, picks×7) + (8 if history) + min(10, top_sim×10)`, clamp `[30,98]`. Data, not the model. |
| `ignore previous instructions…`        | Opus can only cite beans in context. Architectural, not a prompt.                                     |

---

## Architecture

```
        Claude Haiku 4.5  ◄─ agent_messages → structured intent
               │
               ▼
   ┌──────────────────────────────────┐
   │            PostgreSQL            │ ◄── Coordinator
   │  memory · tools · audit          │       ├─ Flavor Profiler
   │  workflow state · approvals      │       └─ Roast Master
   │  pgvector · relational · GIN     │
   └──────────────┬───────────────────┘
                  ▼
         Claude Opus 4.7  ◄─ grounded picks only → reply
```

Both Bedrock calls go through `converse` in `us-east-1` and land in `tool_audit` next to every SQL tool call (`tool = 'llm:<model_id>'`). One `SELECT` reconstructs the trace.

| Pillar          | Where                                              |
| --------------- | -------------------------------------------------- |
| Intent / reply  | Haiku 4.5 · Opus 4.7 on Bedrock                    |
| Episodic        | `agent_messages`, `orders`                         |
| Semantic        | `beans.embedding vector(384)` + HNSW               |
| Procedural      | `orders ⋈ beans ⋈ customers`                       |
| Tools           | `tools.description_emb` — discovered, not wired    |
| Audit           | `tool_audit` — SQL and LLM in one table            |
| Workflow        | `agent_sessions.workflow_state` jsonb              |
| Approvals       | `approvals` until `status='approved'`              |
| MCP             | [`mcp_server.py`](mcp_server.py) — stdio, SELECT-only |

Nine tables, two extensions. Full DDL in [`schema.sql`](schema.sql).

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

Embeddings: [`BAAI/bge-small-en-v1.5`](https://huggingface.co/BAAI/bge-small-en-v1.5) via fastembed, 384-dim, ~130MB, local. Swap with `EMBED_MODEL` — schema hard-codes `vector(384)`.

| Table            | Role                                      |
| ---------------- | ----------------------------------------- |
| `customers`      | Profiles                                  |
| `beans`          | Catalog + `embedding` (HNSW, GIN notes)   |
| `orders`         | What they bought                          |
| `agent_sessions` | One conversation; resumable jsonb state   |
| `agent_messages` | Turns Haiku actually reads                |
| `tools`          | Registry + `description_emb`              |
| `tool_audit`     | Every SQL and LLM call                    |
| `approvals`      | Gated writes                              |

---

## Customize

- Models — `BEDROCK_HAIKU_MODEL` / `BEDROCK_OPUS_MODEL` in `.env`
- Embeddings — `EMBED_MODEL` (any 384-dim fastembed model)
- Tools — `INSERT` into `tools`; set `requires_approval=true` to queue
- Beans — edit `BEANS` in [`seed.py`](seed.py), re-run `python seed.py`
- Grounding — `_respond` in [`agents.py`](agents.py) is the set Opus is allowed to cite

---

## FAQ, short

**Can Opus invent a bean?** No. It only sees ids that survived fact-check.

**Prompt injection?** Haiku can be confused; Opus still only sees grounded picks. Contract, not a prompt.

**Unsafe SQL?** Agents call typed tools. The only SQL-accepting path is MCP: SELECT-only, allowlisted, row-capped.

**Agent DB access?** App role is read-write on domain tables. MCP is read-only — in production, a second role with `GRANT SELECT`.

**Writes?** `tools.requires_approval = true`. The LLM proposes; a human flips the row.

**pgvector ceiling?** HNSW build cost around 10M rows/index. Next: pgvectorscale, then a dedicated engine. Most agents never get there.

**Two LLMs expensive?** Haiku is cheap. Opus is the bill. SQL is a rounding error.

**LangChain / LangGraph / Strands?** Complementary. They loop; Postgres holds state. This demo skips the loop so you can see the tables.

---

## Files

| File | |
| ---- | - |
| [`schema.sql`](schema.sql) | DDL |
| [`seed.py`](seed.py) | Customers, beans + embeddings, orders, tools |
| [`reset.sh`](reset.sh) | Truncate session tables |
| [`db.py`](db.py) | Pool + embedder |
| [`bedrock.py`](bedrock.py) | Converse + `tool_audit` |
| [`agents.py`](agents.py) | Coordinator, memory, tools, fact-check, approvals |
| [`app.py`](app.py) | FastAPI |
| [`mcp_server.py`](mcp_server.py) | stdio MCP |
| [`static/index.html`](static/index.html) | Coffee & queries UI |

Deck: [`deck/`](deck/) (Marp). `./deck/build.sh` → `deck/deck.pdf`. Node 18+.
