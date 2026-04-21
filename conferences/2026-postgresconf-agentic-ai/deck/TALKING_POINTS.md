# Talking Points · PostgresConf 2026

> Stage notes for the 50-min dev-track talk. Audience: Postgres devs, builders, committers, hackers.
> Speak their dialect — access patterns, query plans, index internals, autovacuum, MVCC. Don't sell Postgres _to_ Postgres people. Sell the idea that the agent stack is _ordinary Postgres work_.
>
> Scenario scripts (what to type, what to show in psql, what to say per panel) live in [../README.md](../README.md). This file is the **narrative through-line** — one paragraph per slide, plus the time budget.

---

## Time budget · 50 minutes total

| Block                           | Slides | Budget     | Notes                                                                  |
| ------------------------------- | ------ | ---------- | ---------------------------------------------------------------------- |
| Title + bio                     | 1–2    | 1 min      | 20–30 sec bio, move on                                                 |
| Problem → thesis → architecture | 3–7    | 6 min      | Frame the seven-system stack, land the one-DB claim, show the diagram  |
| Latency + cost                  | 8      | 2 min      | Shape of the distribution, not numbers                                 |
| Memory types                    | 9–10   | 4 min      | Three memory types, then the procedural JOIN — this is the first "wow" |
| Tools as a table                | 11–13  | 4 min      | Registry → discovery SQL → MCP                                         |
| Workflow state + limits         | 14–15  | 3 min      | JSONB checkpoint, then the honesty slide on when it's not enough       |
| Guardrails                      | 16     | 2 min      | Fact-check · confidence · approvals                                    |
| **Demo**                        | 17     | **12 min** | 3 scenarios · see README for per-turn scripts                          |
| Operational realities           | 18–21  | 8 min      | HNSW, autovacuum, pool sizing, coreference                             |
| Honesty slide                   | 22     | 2 min      | When _not_ to do this — buys credibility                               |
| Closer + references             | 23–26  | 3 min      | The "every role, one plan" SQL · where the pattern lands · Q&A         |
| **Buffer**                      |        | **3 min**  | Demo gods, a deep question, finding the right tab                      |

**Rule of thumb on stage:** 5 minutes behind at the demo → skip operational realities (18–21), jump to the closer. The demo is the payload. The tuning slides are appendix.

---

## Slide-by-slide narration

### 1. Title

_"Three agents, two Claude models, one Postgres, no framework. Next 50 minutes I want to convince you the data layer for a production agent is boring — and boring is the feature."_

### 2. Bio

20 seconds. Name, role, "I ship this pattern for a living, here's what works." Move.

### 3. The problem — seven systems

Read the list out loud. Pause. Then:

_"Seven auth boundaries. Seven failure modes. Seven things to page on at 2am. And before you ask — yes, I've run this stack. That's why I'm standing here."_

For the committers:

_"Every arrow between those boxes is an RPC, a serialization boundary, and an eventual-consistency window you have to reason about. Postgres solved this for OLTP decades ago. Agents are OLTP with vectors and a long tail of JSONB."_

### 4. The thesis

One database. One transactional snapshot. LLMs at the edges, SQL in the middle. That sentence is the whole talk.

### 5. Why one database, not five

The slide that matters for the hackers. Don't dunk on vector DBs — that's the weak version. Go strong:

- **One optimizer** sees vector ops, filters, joins together. It pushes predicates through HNSW, reorders joins by selectivity, shares sort orders. Pinecone + Postgres + Redis can't share a plan.
- **One transaction** — the audit row, the approval, the state checkpoint all commit or none do. No dual-write. No outbox. No compensating logic when Kafka lag spikes.
- **One MVCC snapshot** — your similarity score and your inventory count came from the _same_ visible state. Vector DB says bean X is close; Postgres says bean X is out of stock; they disagree because they were taken at different times. Here they can't.

_"This isn't a Postgres talk. It's a distributed-systems-avoidance talk. Postgres happens to be the thing we're avoiding distributing."_

### 6. Architecture

Point at the diagram. Haiku on top (intent, coref). Three agents in the dashed box, all reading and writing Postgres. Opus on the bottom (synthesis from grounded picks only). Everything the agents need — memory, tools, audit, state, approvals — in one Postgres box.

_"Two Bedrock calls per turn. Everything else is a SQL transaction."_

### 7. Haiku parses, Opus synthesizes

Two models, two jobs. Haiku is cheap and fast — structured extraction via Converse tool-use. Opus is slow and expensive — the generator. Split by what each is good at.

The contract between them — `intent → grounded picks → citations` — is a data shape, not a prompt. Swap either model without touching Postgres.

_"If you've ever built a pipeline where the cheap worker does extraction and the expensive worker does synthesis, this is that pattern. Claude happens to be the workers."_

### 8. Latency and cost

Don't quote Bedrock prices — they move. Show the shape: milliseconds of SQL, seconds of Opus.

_"Everyone in this room assumes agents are expensive because agents include LLMs. You're right about the cost. You're wrong about where it lives. The database work is free. The model is the tax."_

For a room that runs OLTP at p99s measured in milliseconds, this is where they realize the DB isn't the bottleneck they thought it was.

### 9. Three memory types, one database

Terminology honesty up front — "procedural memory" is cog-sci borrowed loosely. If someone corrects you from the floor, agree: _"cohort memory works too, the point is the access pattern."_ Move on.

Map each type to its access pattern:

- **Episodic** → `WHERE session_id=$1 ORDER BY ts DESC`. This is `pg_stat_statements`'s dream query.
- **Semantic** → `ORDER BY embedding <=> $1` on HNSW. Btree-shaped access, different index type.
- **Procedural** → the JOIN that falls out of having both in the same database.

_"So the three-memory-types framing isn't really a claim about how LLMs remember things. It's a claim about how many index types and access patterns your data layer has to support, and whether a single planner can see all of them at once. The cog-sci vocabulary is a hook to make it memorable; the query plan is the point."_

### 10. The procedural memory query

First "wow" slide. Read the SQL out loud — slowly — and name three things in one plan:

1. `SELECT %s::vector AS v` → the current request's embedding
2. `b.embedding <=> v` → pgvector cosine similarity (uses HNSW)
3. `JOIN orders JOIN customers` → relational cohort lookup

_"Three systems' worth of architecture diagrams, in one CTE. `EXPLAIN` this and you see an Index Scan on HNSW, a Hash Join on customers, an aggregate on orders — one plan. A vector DB can't express this without round-tripping to your OLTP store, and when it does, the scores are stale."_

For the planners in the room:

_"If you care about query planning, this is the slide. The planner has visibility into selectivity on both the vector side and the relational side. Push-down works. A separate vector store gives up that visibility the moment the score leaves the index."_

### 11. Tools are a table

Show the schema. Highlight three columns:

- `description_emb` — a vector column next to text columns. Normal.
- `input_schema jsonb` — JSON Schema validated client-side, stored server-side.
- `requires_approval boolean` — row-level flag, checked by the coordinator.

_"It's a table. If you know Postgres, you already know how to back it up, replicate it, audit it, grant on it, partition it. No new operational surface."_

### 12. Semantic tool discovery in one query

Dynamic discovery, not a static toolbox. Add a tool → INSERT a row → it's available on the next request. No code deploy, no prompt template change.

_"Your change-management window just became `BEGIN; INSERT; COMMIT;`."_

Plug the unification: `tool_audit` captures both SQL tool calls and LLM calls (as `tool='llm:<model_id>'`). One SELECT = complete execution trace. No correlating across four dashboards.

### 13. MCP — same Postgres, different client

Two interfaces, one store. Agent writes via FastAPI. External MCP hosts (Claude Desktop, Cursor) read via `mcp_server.py`.

The enforcement is the point:

- Read-only Postgres role (`GRANT SELECT`). The _database_ refuses writes.
- SQL parsed client-side to reject anything that isn't a single `SELECT`.
- Row cap enforced.

_"Belt and suspenders. The role is the belt. If the parser has a bug, the role still stops it. Same model we already trust for BI readers and exfil-sensitive reporting."_

### 14. Workflow state is a column

JSONB, checkpointed after every step. Same transaction as the side effects — the checkpoint cannot drift from the work it describes. Process dies mid-task? Next invocation reads `workflow_state->>'step_index'` and resumes.

_"Every time someone reaches for Temporal to solve 'what if the agent crashes mid-task,' they're solving a problem Postgres solves with a `COMMIT`. Look at the transaction boundary. The checkpoint is atomic with the side effect. You can't get that from a separate workflow service without a two-phase commit or an outbox."_

### 15. When JSONB stops being enough

The honesty slide before the honesty slide. Where Temporal, Cadence, and Step Functions earn their keep:

- Workflows measured in days or weeks with external callbacks
- Saga compensation across services you don't own
- High-fanout parallelism — hundreds of parallel steps per workflow

_"Most agents don't have these problems. The ones that do shouldn't pretend Postgres solves them. Pick your tool for the access pattern you actually have, not the one on the slide deck."_

### 16. Three guardrail layers

Fact-check → confidence from data → approval queue. Walk through the order:

1. Before calling Opus: re-read every candidate bean from `beans`, verify `in_stock > 0`. Failures are **dropped**. Not papered over.
2. Confidence from row coverage, history match, top similarity. Not a model-reported number. Not a fudge factor.
3. Write-intent tool with `requires_approval=true`? Don't execute. Insert into `approvals`, `status='pending'`. A human flips the bit.

_"Opus physically cannot hallucinate a bean we don't have, because the system prompt restricts it to the ids we pass in, and fact-check drops anything stale from that list. Safety isn't a prompt. It's a context boundary."_

### 17. DEMO (12 min)

Switch to browser + psql side-by-side. Full per-turn scripts with psql callouts and narration in **[README.md § Stage guide](../README.md#stage-guide--everything-you-need-while-presenting)**.

Condensed running order for stage timing:

- **Scenario 1 · Marco · ~4 min** — two turns on cold brew. Beat to land: the procedural memory panel. Episodic + semantic + procedural in one query plan. After turn 2, jump to psql and run the single-SELECT trace from the README. _"Twelve rows. That's the entire turn — every LLM call, every SQL tool call, latencies, tokens. No dashboards."_
- **Scenario 2 · Ana · ~4 min** — two turns, same "cold brew" prompt as Marco (different answer, because memory), then `order that`. Beat: the three-beat psql check — `orders` unchanged, `approvals +1`, `beans.in_stock` unchanged. _"The write didn't happen. The **intent to write** landed in a row. A human flips the bit."_ Finish with the `UPDATE approvals SET status='approved'` so people see the other end.
- **Scenario 3 · Yuki · ~3 min** — Japanese single-origins. Catalog doesn't have one. Fact-check drops everything. Opus refuses warmly. _"The guardrail isn't the system prompt. The guardrail is that Opus cannot cite a bean that isn't in its context — and an empty list stays empty."_ Pivot to the MCP terminal: same `tool_audit` table, different client. _"No new API. No new auth. One Postgres."_

**1 min floating buffer** for demo gods or a mid-turn hand-raise.

**Behind schedule?** Cut Scenario 3's MCP terminal, keep the refusal. The refusal is the point.

### 18. pgvector: HNSW tuning

The committers want this slide. Three knobs:

- `m` — graph connectivity. Build-time. Higher = better recall, bigger index, slower build.
- `ef_construction` — build-time candidate list. Higher = better recall, slower build.
- `hnsw.ef_search` — query-time candidate list. Tunable per session with `SET`.

Name the shape: recall climbs fast, saturates around 0.98. Latency climbs linearly with `ef_search`. Most agents are on the flat part at default. Real call: start at the default, measure recall against a small ground-truth set, don't tune until you have a problem.

Committer note: _"pgvector 0.7 shipped parallel HNSW builds. Still on 0.5 or 0.6 with single-threaded builds? That's your first easy upgrade."_

### 19. Autovacuum on append-heavy tables

`agent_messages` and `tool_audit` are write-mostly. Default autovacuum is tuned for OLTP mutation — it triggers on dead tuples you never create.

Turn on `autovacuum_vacuum_insert_scale_factor` (PG13+). Name the failure: without it, you get index bloat and query plan flips at ~10M rows because stats go stale.

_"Half the room nods because they've lived it. The other half just learned why their first agent prototype melted at 30 concurrent users."_

For the deeply-interested: TOAST on `content jsonb` in `agent_messages`. Long prompt histories toast — set `toast_tuple_target` to match your typical payload. Measure with `pg_column_size`.

### 20. Connection pooling

One turn = 8–15 queries. 50 concurrent sessions = ~500 queries in flight. Don't point those at raw backends.

PgBouncer in transaction mode, prepared statements on (1.21+), `default_pool_size` matched to your backend count. Or RDS Proxy if you're on AWS and don't want to run a pooler.

_"This is standard OLTP advice. Agents are OLTP with LLM calls on either side. The pooling story doesn't change."_

### 21. Chat continuity ("order that")

The coreference problem. Re-embedding turn 2 lands somewhere else, because "order a bag" semantically matches "generic order" more than "that espresso blend we just pitched." Naive implementation → customer sees a bait-and-switch.

The fix: Haiku's tool schema includes `order_referent_bean_id`. Haiku reads the last six turns from `agent_messages` and returns the bean id from the previous recommendation. Coordinator pins that id.

_"The LLM and the coordinator share a memory. That memory is a boring SQL table. The thing that would be a brittle state machine in some other architecture is a structured field in a tool schema — and the source of truth is `agent_messages`."_

### 22. When NOT to do this

Land all five bullets. This is the slide that buys you credibility. Read the fifth with a smile:

_"'Just use Postgres' assumes someone in your org knows how to operate Postgres. If your platform team only does DynamoDB, factor that in."_

Land the pivot:

_"I'm not here to tell you Postgres is the answer for every agent workload. I'm here to tell you it's the answer for most agent workloads, most of the time — and the tradeoff conversation should start with the access pattern, not the vendor logo."_

### 23. Every role, one plan

The closer SQL. Read it out loud — don't rush. Name each subquery:

- `b.embedding <=> (SELECT embedding FROM beans WHERE id='b_ethiopia_guji')` — semantic
- `SELECT count(*) FROM orders WHERE ... customer_id='u_marco'` — episodic
- `SELECT count(*) FROM tool_audit WHERE result->'stock' ? b.id` — audit
- `SELECT count(*) FROM approvals WHERE args->>'bean_id'=b.id AND status='pending'` — workflow

_"One plan. One optimizer. One transaction. Draw this when your vectors are in Pinecone, your state is in Postgres, and your audit is in DynamoDB."_

### 24. Where this pattern lands in practice

Softer framing than a war story. Observation across independent teams, not a personal victory lap. This slide is also where you reconcile the "no framework" repo with the "frameworks are fine" reality.

**Verbal bridge — say this before the bullets:**

_"The demo repo deliberately ships without a framework, so you can read the orchestration top-to-bottom. But in production, most teams pick one — LangChain, LangGraph, Strands, AgentCore — and the pattern I've been showing you slots underneath whatever they pick. It's not a choice between Postgres and LangGraph. It's a choice about what each layer is good for."_

Then land the clean-seam argument: **frameworks handle prompt orchestration and agent loops; Postgres handles state, memory, audit, approvals.** Name the integrations on stage — `PostgresSaver` is a JSONB column with a nice API, Strands memory backends, AgentCore session stores. The frameworks already know Postgres is the bottom half; they just don't always say it out loud.

Close with the humbler read: _"Smart teams keep reinventing this. That's the strongest signal it's right."_

Offer to share specifics off-stage on the three use-case bullets.

### 25. Architecture reference

Don't read the table. It's for the recording.

_"This is for when you're back at your desk trying to remember which column does what. Slides are on GitHub."_

### 26. Run it yourself + Thank you

Point at the URL.

_"Clone it, run it, break it. Schema is 116 lines. `agents.py` reads top to bottom. No framework to fight."_

Open the floor. Default to taking questions against the live demo (still on screen) so answers stay concrete.

---

## Anticipated questions (rehearse once)

| Question                                               | Answer anchor                                                                                                                                                                                                                                                                                                     |
| ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "What about at 100M vectors?"                          | HNSW builds slow down. Try **pgvectorscale** (StreamingDiskANN on Postgres) first — it's the least-disruptive jump. Beyond that, IVFFlat for faster builds, or shard. At that scale, the real question is "do my access patterns still need relational JOINs at query time?" If yes, stay Postgres. If no, leave. |
| "Why not pgvector.rs / DiskANN / ScaNN?"               | No strong opinion — they solve the index. The talk is about the _plan_ containing vectors + relational + audit. Any of those indexes plug into the same argument.                                                                                                                                                 |
| "Isn't JSONB for workflow state a footgun?"            | Only if you write unvalidated JSON. We validate on the way in (pydantic), query with `->>` and `?`, index with GIN where it matters. Same rules as every JSONB table.                                                                                                                                             |
| "What happens when agent_messages grows to 100M rows?" | Partition by month on `(session_id, ts)`. Old partitions go read-only or archived. HNSW on a partitioned table is fine as long as you query with the partition key.                                                                                                                                               |
| "Why Bedrock specifically?"                            | Incidental. The data layer doesn't care. Swap to OpenAI, Anthropic direct, or Ollama — the `tool_audit` row just has a different `tool='llm:…'` value.                                                                                                                                                            |
| "How do you handle PII in agent_messages?"             | Same way you handle PII anywhere in Postgres — column-level encryption, row-level security, audit the readers. Agents aren't a new PII problem; they just surface the existing one faster.                                                                                                                        |
| "pgvector locks on `UPDATE`?"                          | HNSW does not rebuild on UPDATE; it handles inserts incrementally. Bulk rebuilds use `REINDEX CONCURRENTLY`. The hot path we care about (agent reads) is not blocked by writes.                                                                                                                                   |
| "Procedural memory is just RAG on the orders table."   | Correct. The difference is the retrieval runs in the same plan as the candidate ranking — the planner can reorder. In RAG-over-API, the order is fixed by your code. Not a huge deal at small scale, real at scale.                                                                                               |
| "Why no LangChain/LangGraph?"                          | They're fine libraries — `PostgresSaver` is a wrapper around a JSONB column. If your JSONB column is right there, the wrapper is optional. Use it if you like; don't require it.                                                                                                                                  |
| "What's the one thing you'd do differently?"           | Start with `tool_audit` as a partitioned hypertable from day one. We didn't, and we've cut over in production. Not painful, but I'd skip the step.                                                                                                                                                                |

---

## Cadence notes

- **Pace check at slide 10.** Past 15 minutes into the talk? You're behind — the demo will run long. Skip slide 8 (latency/cost) to recover.
- **Don't read the SQL slides.** Name the three things in the query and move. The audience reads faster than you speak.
- **Demo running long?** Cut Scenario 3's MCP terminal. Keep the refusal.
- **psql misbehaving?** Slide 23 ("Every role, one plan") is the fallback. Same argument without the live DB.
- **Finished early?** Open questions. Don't pad.

---

## One-line version

If someone asks in the hallway to describe the talk in one sentence:

> _"The data plane for a production agent collapses into one Postgres — episodic, semantic, and procedural memory, tool registry, audit, workflow state, approvals, and an MCP surface — and the orchestration layer you'd otherwise import is ~2,200 lines of Python."_
