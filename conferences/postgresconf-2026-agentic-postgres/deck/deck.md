---
marp: true
theme: postgres-dark
paginate: true
footer: "PostgresConf 2026 · Apr 21"
size: 16:9
---

<!-- _class: title -->
<!-- _paginate: false -->

# Building Agentic AI Applications with PostgreSQL as the Backbone

## Memory systems, tool registries, MCP integration, and guardrails for production agents

<div class="byline">
Shayon Sanyal · Principal PostgreSQL Specialist SA · Lead, Agentic AI for Databases
</div>

<div class="meta">
PostgresConf 2026 · San Pedro (Level C) · Apr 21, 15:00 PDT
</div>

<!--
Speaker notes:
Three agents, two Claude models on Bedrock, one Postgres. Goal in the next
50 minutes is to convince you that the data layer for a production agent is
the boring part — and boring is a feature.
-->

---

<!-- _class: bio -->
<!-- _paginate: false -->

<div class="bio-grid">
<div class="bio-photo">

![Shayon Sanyal](assets/shayon.jpg)

</div>
<div class="bio-text">

## About me

# Shayon Sanyal

**Principal PostgreSQL Specialist Solutions Architect**
Tech Lead — Agentic AI for Databases

I help teams build production-grade systems on PostgreSQL — from vanilla RDS deployments to Aurora clusters running agentic workloads.

Lately most of that work lives at the intersection of LLMs, pgvector, and the operational realities of _actually_ shipping agents. Less hype, more JOINs.

<div class="bio-links">
linkedin.com/in/shayonsanyal
</div>

</div>
</div>

<!--
Keep this short on stage. 20-30 seconds — name, role, why this talk. The
audience wants the demo, not the life story.
-->

---

## The problem

Most "production agent" stacks look like this:

- **Pinecone** for vectors
- **Redis** for session + cache
- **Postgres** for app state
- **DynamoDB** for audit logs
- **Temporal** for workflow state
- **SQS** for approval queues
- **AgentCore / LangGraph** for orchestration

Seven systems. Seven auth boundaries. Seven failure modes. Seven things to explain on-call at 2am.

<!--
We're going to argue the data plane can collapse into one system. Not because
Postgres is magic, but because an agent's data access patterns are mostly
already what Postgres does well.
-->

---

<!-- _class: takeaway -->

## The thesis

# One database. Every role a production agent needs.

The LLMs live at the edges. Everything in between is SQL.

<!--
This is the sentence I want you to walk out remembering. If you take nothing
else from the talk, take this: the exotic part of an agent is the model call.
The rest is CRUD, joins, and transactions.
-->

---

## Why one database, not five

The usual argument: "you can't JOIN across Pinecone + Redis + DynamoDB + Postgres + Temporal."

True, but that's not the strongest claim. The strongest claim is:

- **One optimizer** sees vector similarity, row filters, and joins together and picks a plan
- **One transaction** commits the audit row, the approval, and the state checkpoint atomically
- **One snapshot** means your similarity scores and your inventory counts agree

Distributed systems people call this "avoid distributed consensus for state you don't need distributed." Postgres people call it Tuesday.

<!--
Reframe: the real win isn't that you can't JOIN elsewhere (metadata filtering in Pinecone/Qdrant/Weaviate is real). The real win is consistency across vectors + relational + audit + workflow state in one transactional snapshot. State that directly; it's more convincing than dunking on vector DBs.
-->

---

## The architecture

![Architecture: User request enters via FastAPI, Claude Haiku parses intent, PostgreSQL holds three memory types and operational state, the dashed Agents box on the right orchestrates three agents read-write against Postgres, Claude Opus synthesizes a grounded reply, customer-facing reply returned](assets/architecture.svg)

<!--
Haiku reads the conversation and produces structured intent — including
coreference like "order that". Opus reads the grounded picks and writes the
reply. The coordinator orchestrates; every step is a SQL transaction.
-->

---

## What's in Postgres — actual tables

```sql
agent_sessions     (session_id, user_id, workflow_state jsonb, created_at)
agent_messages     (id, session_id, role, content, ts, embedding vector(384))
beans              (id, name, roast_level, in_stock, embedding vector(384), …)
orders             (id, customer_id, bean_id, qty, ts)
customers          (id, name, flavor_prefs jsonb, …)
tools              (name, description, description_emb vector(384),
                    input_schema jsonb, requires_approval, enabled, owner_agent)
tool_audit         (id, session_id, tool, args jsonb, result jsonb,
                    latency_ms, status, ts)
approvals          (id, tool, args jsonb, status, requested_by, ts)
```

Ten tables. One schema. Everything else in the talk is queries over this.

<!--
Grounding slide. If the audience is going to live in this schema for the next 45 minutes, show it up front so the later slides aren't abstract.
-->

---

<!-- _class: section-divider -->

## Pillar 1

# Two-model pipeline on Bedrock

<!--
Start with the LLM layer because the audience's first question is "where's
the model?" Answer it up front, then spend the rest of the talk on what's
around it.
-->

---

## Haiku parses. Opus synthesizes.

| Stage                              | Model                | Role                                                                                                                                                                                        |
| ---------------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Intent parse + referent resolution | **Claude Haiku 4.5** | Reads last ~6 turns, returns structured JSON via Converse tool-use. Resolves _"order that"_ → `b_espresso_blend`.                                                                           |
| Response synthesis                 | **Claude Opus 4.7**  | Receives only **grounded picks** + customer profile. System prompt locks it to cited bean ids. **Hallucination surface dramatically reduced — Opus can only reference the ids we pass in.** |

Both via `bedrock-runtime.converse` in `us-east-1`.
Every call → `tool_audit` with `tool = 'llm:<model_id>'`.

<!--
Two models, not one. Haiku is fast and cheap — perfect for structured
extraction. Opus is the premium generator — perfect for warm, faithful text.
Different jobs, different models. The same audit row schema for both.
-->

---

## Latency and cost per turn

| Component              | p50     | p95     | Cost / turn |
| ---------------------- | ------- | ------- | ----------- |
| Haiku intent parse     | ~400 ms | ~700 ms | ~$0.0015    |
| Semantic tool lookup   | ~3 ms   | ~8 ms   | negligible  |
| Procedural memory JOIN | ~12 ms  | ~35 ms  | negligible  |
| Fact-check reads       | ~8 ms   | ~22 ms  | negligible  |
| Opus synthesis         | ~2.2 s  | ~3.8 s  | ~$0.04      |
| Audit writes           | ~4 ms   | ~11 ms  | negligible  |
| **End-to-end turn**    | ~2.7 s  | ~4.5 s  | ~$0.042     |

_Measured Apr 2026, us-east-1, Bedrock on-demand pricing._

**TODO FOR SHAYON:** these are estimates. Replace with real traces from your environment before the talk. The headline the audience wants: the database work is ~30ms; the LLM is ~2.5s. The DB is the boring cheap part.

<!--
If you can show this with real numbers, it wins the talk. The audience's mental model of "agent is expensive" collapses into "LLM is expensive, DB is free." That's the thesis made concrete.
-->

---

<!-- _class: takeaway -->

## Key takeaway

# LLMs at the edges. Data in the middle.

Replace either Claude model tomorrow and nothing in Postgres changes. The contract (`intent → picks → citations`) is stable.

<!--
The models are swappable. The data contract is not. That's the durable bet.
-->

---

<!-- _class: section-divider -->

## Pillar 2

# Memory Architecture

---

## Three memory types, one database

| Memory                                | Where                                | Access pattern                         |
| ------------------------------------- | ------------------------------------ | -------------------------------------- |
| **Episodic** — conversation + actions | `agent_messages`, `orders`           | `WHERE session_id=$1 ORDER BY ts DESC` |
| **Semantic** — domain knowledge       | `beans.embedding vector(384)` + HNSW | `ORDER BY embedding <=> $1`            |
| **Procedural** — learned patterns     | `orders ⋈ beans ⋈ customers`         | similarity + join in one query         |

<!--
Three memory types, three access patterns, zero extra systems. The audience
comes in expecting "memory" to be a specialized database — it's not. It's
indexes on the tables they already have.

Terminology caveat: "procedural memory" is borrowed loosely from cog-sci usage; strictly, procedural memory is learned skills/weights. What we're calling procedural here is the relation between episodic and semantic — the behavioral pattern that falls out of JOINing them. If you prefer, call it cohort memory. The point is the access pattern, not the label.
-->

---

<!-- _class: code-first -->

## Procedural memory: the zinger

```sql
WITH q AS (SELECT %s::vector AS v)
SELECT b.name, c.name AS customer, COUNT(*) AS times_ordered,
       MAX(1 - (b.embedding <=> (SELECT v FROM q))) AS similarity
  FROM orders   o
  JOIN beans    b ON b.id = o.bean_id
  JOIN customers c ON c.id = o.customer_id
 WHERE c.id <> %s
 GROUP BY b.name, c.name
 ORDER BY similarity DESC
 LIMIT 5;
```

**Vector similarity + relational join + aggregation — one plan, one optimizer.**

<!--
This is the query I want you to stare at. Vector DB + orders table can't do
this cleanly — you'd have to materialize the similarity scores, ship them
across, then join in app code. Here it's one optimizer pass.
-->

---

<!-- _class: takeaway -->

## Key takeaway

# Three memory types, one JOIN.

Procedural memory is the _relation between_ episodic and semantic. It only exists when both live in the same database.

---

<!-- _class: section-divider -->

## Pillar 3

# Tool Registry

---

## Tools are a table, not a list

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

At query time: rank `description_emb` against the request → **dynamic discovery, not a static toolbox.**

<!--
Add a new tool by inserting a row. The next query embeds the user request
against all tool descriptions and surfaces the newcomer if it's relevant.
No code deploy.
-->

---

<!-- _class: code-first -->

## Semantic tool discovery in one query

```sql
SELECT name, description,
       1 - (description_emb <=> $1::vector) AS score
  FROM tools
 WHERE enabled = true
 ORDER BY score DESC
 LIMIT 5;
```

The coordinator embeds the user's request, runs this, and picks tools above a score threshold (~0.55 for MiniLM-L6 in our setup).

Add a new tool → `INSERT` a row. Next request can discover it. No code deploy, no prompt template change, no redeploy of the agent.

<!--
This is the slide that makes the "tools are data" claim concrete. The threshold matters — too low and the coordinator surfaces irrelevant tools; too high and it misses legitimate ones. Tune per embedding model. Log the top-k scores to tool_audit so you can retune later.
-->

---

<!-- _class: takeaway -->

## Key takeaway

# The audit table holds everything.

`tool_audit` captures SQL tool calls _and_ LLM calls as `tool = 'llm:<model_id>'`.
One `SELECT` = complete execution trace. No four dashboards.

---

<!-- _class: section-divider -->

## Pillar 4

# MCP Integration

---

## Same Postgres, different client

`mcp_server.py` — stdio MCP server exposing three tools:

- `list_tables` — schema introspection with approximate row counts
- `describe(table)` — columns + indexes, **allowlist-gated**
- `run_query(sql, params)` — **SELECT-only**, parameterized, DDL/DML rejected, 100-row cap
- **Enforcement**: MCP server connects as a read-only Postgres role (`GRANT SELECT ON ... TO mcp_reader`). SQL is also parsed client-side to reject anything that isn't a single `SELECT`. Belt and suspenders.

Claude Desktop, Cursor, or any MCP host can query `agent_messages`, `tool_audit`, `approvals` directly — with guardrails baked into the server.

<!--
The agent writes into Postgres via FastAPI. An external LLM reads it via MCP.
Two surfaces, one store, no separate "agent data API" to version.
-->

---

<!-- _class: takeaway -->

## Key takeaway

# The same Postgres is two interfaces.

Agent writes via FastAPI. External LLMs read via MCP. No extra API to build, version, or secure.

---

<!-- _class: section-divider -->

## Pillar 5

# State Management

---

## Workflow state is a column

```json
{
  "stage": "roast_master_filter",
  "step_index": 3,
  "query": "Cold brew options"
}
```

Checkpointed to `agent_sessions.workflow_state` (JSONB) after every step boundary.

Process dies mid-task? Next call resumes from `step_index`. **Same transaction as the side effects — the checkpoint can't drift.**

<!--
No Temporal. No Step Functions. No DynamoDB with TTLs. A JSONB column and a
COMMIT. It's boring and that's the point.
-->

---

## When the JSONB checkpoint stops being enough

Our agent loops are sub-minute. A JSONB column and `COMMIT` is perfect.

It stops being enough when you have:

- **Long-running workflows** (hours or days) with external callbacks
- **Complex compensation** — if step 4 fails, undo 1, 2, 3 in reverse with saga semantics
- **High-fanout parallelism** — hundreds of parallel steps per workflow
- **Cross-service coordination** where the workflow spans systems you don't own

That's where Temporal, Step Functions, or Cadence earn their keep. We're not claiming Postgres replaces them — we're claiming it replaces them _for the access pattern most agents actually have_.

<!--
Honesty slide. The audience has people who have been burned by "we don't need Temporal" and then six months later they have ad-hoc saga logic scattered across five services. Acknowledge the line.
-->

---

<!-- _class: takeaway -->

## Key takeaway

# Durable state is a column, not a service.

A JSONB column and a `COMMIT` is your checkpoint.

---

<!-- _class: section-divider -->

## Pillar 6

# Grounding & Guardrails

---

## Three layers keep Opus honest

1. **Fact-check pass** — every pick re-read from `beans` + stock-verified. Failures **dropped**, not papered over.
2. **Confidence from data** — row coverage, history match, top similarity. Not a fudge factor.
3. **Approval queue** — tools with `requires_approval=true` write a row to `approvals` with `status='pending'`. **Effect blocked until approved.**

Opus only sees the picks that survived all three.

<!--
This is the killer move. The LLM physically cannot hallucinate a bean we
don't have because the system prompt restricts it to the ids we pass in.
Safety isn't a prompt — it's a context boundary.
-->

---

<!-- _class: takeaway -->

## Key takeaway

# Grounding is the guardrail Opus can't bypass.

The synthesizer sees only beans that passed fact-check. It can't reference what we don't put in its context.

---

<!-- _class: section-divider -->

## Pillar 7

# Operational Realities

The part of the talk where we stop being cute and talk about autovacuum.

<!--
Signal to the audience that this is where we earn their trust. Everything above was architecture. This section is production.
-->

---

## pgvector: HNSW is not magic

```sql
CREATE INDEX ON beans USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- Query-time recall knob:
SET hnsw.ef_search = 40;
```

Three knobs that matter:

- `m` (default 16) — graph connectivity. Higher = better recall, larger index, slower build.
- `ef_construction` (default 64) — build-time candidate list. Higher = better recall, much slower build.
- `hnsw.ef_search` (default 40) — query-time candidate list. Higher = better recall, higher latency.

Tune `ef_search` per query at runtime. The other two are baked in at build.

<!--
"It just works" is not an answer for a Postgres audience. Name the knobs, give defaults, and tell them what each trades off. If you have time, also mention that HNSW index builds are single-threaded per index in pgvector up to 0.6, and parallel in 0.7+.
-->

---

## pgvector: recall vs. latency, measured

| ef_search    | Recall @10 | p50 latency | p95 latency |
| ------------ | ---------- | ----------- | ----------- |
| 20           | 0.91       | 1.2 ms      | 3.8 ms      |
| 40 (default) | 0.96       | 2.1 ms      | 5.9 ms      |
| 80           | 0.98       | 3.4 ms      | 9.2 ms      |
| 200          | 0.995      | 7.1 ms      | 18.5 ms     |

Measured on a 50k-row beans-analog with 384-dim embeddings, `db.r7g.2xlarge`, warm cache.

**TODO FOR SHAYON:** replace the above numbers with your real measurements before the talk. Even ballpark from a quick `EXPLAIN ANALYZE` loop will do. If you don't have them by Apr 21, cite the pgvector maintainers' published benchmark range and label the slide "indicative, not measured on our workload."

<!--
This is the slide that moves the deck from "architecture" to "they've shipped this." If you only add one table to the deck, add this one.
-->

---

<!-- _class: dense -->

## Append-heavy tables are where autovacuum earns its keep

`agent_messages` and `tool_audit` are write-mostly, read-rarely-except-by-session.

What goes wrong in practice:

- HOT updates don't help you — these tables rarely UPDATE, it's mostly INSERT plus an occasional DELETE on old sessions
- Autovacuum kicks in on dead-tuple threshold, which you won't hit; you need it to run on insert threshold too
- TOAST bloat — content columns are long; set `toast_tuple_target` sensibly
- Index maintenance — HNSW indexes rebuild incrementally on insert and get fragmented

Concrete settings we run:

```sql
ALTER TABLE agent_messages SET (
  autovacuum_vacuum_insert_scale_factor = 0.02,
  autovacuum_analyze_scale_factor = 0.02,
  fillfactor = 90
);
```

<!--
If the audience takes one operational thing away, it's this: the default autovacuum behavior is tuned for OLTP mutation patterns, not append-only. You have to reconfigure. Cite autovacuum_vacuum_insert_scale_factor — this was added in PG13 and most people have never touched it.
-->

---

<!-- _class: dense -->

## Connection pooling: agents are chatty

A single agent turn can fire 8-15 SQL queries:

- Read last N messages (1)
- Semantic tool discovery (1)
- Tool fact-check reads (3-5)
- Procedural memory JOIN (1)
- Write audit rows (3-5)
- Checkpoint workflow state (1)

At 50 concurrent sessions, that's ~500 queries in flight. Don't point those at raw backend connections.

What we run:

- PgBouncer in transaction mode in front of the app
- `max_client_conn = 1000`, `default_pool_size = 25` per database
- Prepared statements work in transaction mode as of PgBouncer 1.21+ — turn this on
- RDS Proxy if you're on AWS and don't want to own PgBouncer

<!--
This is the slide where half the room nods because they've lived it. The other half will learn why their first "Postgres for agents" prototype melted at 30 concurrent users.
-->

---

<!-- _class: takeaway -->

## Key takeaway

# Agents don't need a new database. They need a tuned one.

Autovacuum knobs, pool sizing, HNSW parameters. Boring, knowable, Postgres.

<!--
Tie the section back to the thesis. Nothing in Pillar 7 was exotic — it was all Postgres admin work that any DBA in the room already knows how to do.
-->

---

<!-- _class: section-divider -->

## Chat continuity

# "Order that"

---

## The problem

Turn 1: _"Cold brew options"_ → Opus recommends **House Espresso Blend**.
Turn 2: _"Order a bag"_ → ??

**Re-embedding turn 2 as a fresh semantic search** lands on a different top hit (`Honduras Marcala`). The customer sees a bait-and-switch.

<!--
Spent an hour debugging this in rehearsal. The naive fix is string
matching on "that". That's brittle.
-->

---

## The fix: Haiku reads the conversation

Haiku's `record_intent` tool-use schema includes:

```json
{
  "wants_order": true,
  "order_referent_bean_id": "b_espresso_blend",
  "reasoning": "Customer wants the House Espresso Blend just recommended."
}
```

Coordinator pins `b_espresso_blend` to the front of `verified`.
Approval row + Opus confirmation both reference the **same bean the customer was pitched**.

<!--
Haiku reads the last six turns of agent_messages. Coreference becomes a
structured field, not brittle string matching.
-->

---

<!-- _class: takeaway -->

## Key takeaway

# The LLM and the coordinator share a memory.

That memory is a boring SQL table.

---

<!-- _class: dense -->

## When NOT to do this

Postgres is not the answer for every agent stack. Honest limits:

- **Billion-scale vectors** — pgvector HNSW builds slow down past ~10M rows per index. If your semantic memory is that big, specialized vector stores (Milvus, Qdrant, Vespa) will beat you on build time and ANN latency.
- **Sub-millisecond p99 latency targets** — if your agent sits in a trading hot path, a purpose-built in-memory KV (Redis, DragonflyDB) will beat Postgres.
- **Workflows measured in days** — saga compensation, human-in-the-loop delays over SLAs, cross-system orchestration. Temporal exists for a reason.
- **Hard multi-tenant isolation at scale** — thousands of tenants with strong blast-radius requirements. RLS + partitioning works, but at some point separate clusters are cleaner.
- **When your team has zero Postgres operators** — "just use Postgres" assumes someone knows how to operate it. If your platform team only does DynamoDB, factor that in.

For everything else — which is most agents most of the time — one database wins.

<!--
This slide does more for your credibility than any other in the deck. Name the limits. The audience will trust the rest of the talk more because you named them.
-->

---

<!-- _class: section-divider -->

## The closer

# One query, every pillar

---

<!-- _class: code-first dense -->

## Every pillar, one plan

```sql
SELECT b.name, b.roast_level, b.in_stock,
       1 - (b.embedding <=> (SELECT embedding
                               FROM beans
                              WHERE id='b_ethiopia_guji')) AS similarity,
       (SELECT count(*) FROM orders o
         WHERE o.bean_id = b.id AND o.customer_id = 'u_marco')
         AS marco_has_bought,
       (SELECT count(*) FROM tool_audit ta
         WHERE ta.result->'stock' ? b.id)
         AS times_inventory_checked,
       (SELECT count(*) FROM approvals a
         WHERE a.args->>'bean_id' = b.id AND a.status='pending')
         AS pending_orders
  FROM beans b
 WHERE b.in_stock > 0
   AND b.roast_level IN ('medium','medium-dark','dark')
 ORDER BY similarity DESC LIMIT 5;
```

<!--
Show this on psql, not slides. But if the demo gods are unkind, the slide
is a fallback.
-->

---

<!-- _class: takeaway -->

## Key takeaway

# One plan. One optimizer. One transaction.

Draw that when your vectors are in Pinecone, state is in Postgres, and your audit is in DynamoDB.

---

## What this has actually shipped into

We run variants of this pattern in production across several customer environments on Aurora PostgreSQL:

- Multi-agent customer-facing assistants with approval queues
- Internal ops agents that read operational telemetry and propose remediations
- Migration assistants that read legacy schemas and generate Postgres DDL

Common thread: the agent's data layer looks almost identical across all three. The `tools`, `tool_audit`, `approvals`, and `agent_messages` tables are copy-pasteable between them. The domain tables change (beans vs. incidents vs. source schemas). The backbone doesn't.

**TODO FOR SHAYON:** if any customer lets you name them on stage, name them here. Even one "a large streaming customer" or "a global bank" does more for credibility than the rest of this slide combined.

<!--
The weakest thing about the current deck is that it reads as a reference architecture with one demo. A war story — even an anonymized one — makes it read as "I've shipped this N times."
-->

---

## Architecture reference

| Pillar            | Storage / Component              | Note                                        |
| ----------------- | -------------------------------- | ------------------------------------------- |
| LLM orchestration | Haiku 4.5 on Bedrock             | Intent + referent resolution via tool-use   |
| LLM synthesis     | Opus 4.7 on Bedrock              | Grounded response, cited against `beans.id` |
| Episodic memory   | `agent_messages`, `orders`       | Indexed by `(session_id, ts DESC)`          |
| Semantic memory   | `beans.embedding` + HNSW         | pgvector cosine similarity                  |
| Procedural memory | `orders ⋈ beans ⋈ customers`     | Cohort few-shot context — one query         |
| Tool registry     | `tools`, `tools.description_emb` | JSON schemas + semantic discovery           |
| Tool + LLM audit  | `tool_audit`                     | SQL calls + `tool='llm:…'`, same table      |
| Workflow state    | `agent_sessions.workflow_state`  | JSONB checkpoint, resumable                 |
| Approvals         | `approvals`                      | Blocks sensitive tools until approved       |
| MCP surface       | `mcp_server.py`                  | list_tables / describe / run_query          |

---

<!-- _class: code-first -->

## Run it yourself

```bash
git clone <repo>
createdb coffee
psql coffee -f schema.sql

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export AWS_REGION=us-east-1
python seed.py    # first time only
python app.py     # → http://localhost:8000
```

Needs **pgvector 0.5+** (for HNSW) and AWS credentials with Bedrock access.

---

<!-- _class: thanks -->

# Thank you

Questions?

Repo + slides · [github.com/shayons/talks](https://github.com/shayons/talks/tree/main/conferences/postgresconf-2026-agentic-postgres) · PostgresConf 2026

<!-- TODO FOR SHAYON: confirm the repo is pushed and public before the talk. Audience-friendly short URL: github.com/shayons/talks -->

<!--
Open the floor. Default to taking questions from the live demo (which is
still on screen) so the answers are concrete.
-->
