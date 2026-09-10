# Talking points · Postgres Summit US 2026

**Hybrid Search in PostgreSQL: Combining Vector and Full-Text for Real-World Applications**

Shayon Sanyal · September 30, 2026 · 10:30–11:20 EDT · Letterpress, Convene,
555 Broadway, New York City. Session details checked against the
[official listing](https://postgresql.us/events/postgressummitus2026/schedule/session/2349-hybrid-search-in-postgresql-combining-vector-and-full-text-for-real-world-applications/)
on September 10, 2026.

The story: **words find explicit matches, vectors find related meaning, and
PostgreSQL keeps candidates inside the customer's constraints.** The agent
applies that retrieval contract in a conversation.

Use [deck.md](deck.md), the [paper PDF](deck.pdf), or the
[black-and-cream PDF](deck-dark.pdf) for the same slides,
[the seven-minute demo](../docs/DEMO.md) for the browser sequence, and
[SQL patterns](SQL_PATTERNS.md) for parameterized examples. Slide numbers below
are physical PDF page numbers, including title and divider slides.

## Fifty-minute run of show

| Elapsed | Slides | Budget | What to land |
| --- | --- | --- | --- |
| 0:00–4:00 | 1–5 | 4 min | The request, the two comparisons, the people |
| 4:00–15:00 | 6–13 | 11 min | Schema, candidate branches, eligibility, RRF, tuning |
| 15:00–22:00 | 14 | 7 min | Lab → one explanation → Concierge |
| 22:00–32:00 | 15–20 | 10 min | Embeddings, HNSW, two-minute clickthrough, plans and measurements |
| 32:00–35:00 | 21–22 | 3 min | Required terms, relevance evaluation and extensions |
| 35:00–40:00 | 23–25 | 5 min | Conversation, continuity, pending approvals, honest boundaries |
| 40:00–42:00 | 26–28 | 2 min | Takeaways, runnable repo, questions |
| 42:00–44:00 | — | 2 min | Buffer |
| 44:00–50:00 | 28; 29–31 as needed | 6 min | Q&A and optional appendix |

The ten-minute index block includes the **two-minute Catalog walkthrough**.
Do not add fixture preparation or the price mutation to the main run.

## Rehearsal setup

1. Start the project database with `./scripts/postgres18.sh start`, then
   `./run-demo.sh`. Open Lab at `http://localhost:8017/`, Catalog at `/catalog`,
   and Concierge at `/concierge`. Status should report PostgreSQL 18.
2. Warm Leo's Lab request and Catalog's default bergamot walkthrough. Confirm
   status reports embeddings and the expected catalog. The first embedding
   use may download the model.
3. Check the example price. If a previous stage price experiment is active,
   use its restore control before rehearsing; do not overwrite unrelated edits.
4. Select the intended Concierge model route and complete one recommendation.
   A healthy database does not establish model access. Use **New session** for
   the stage conversation; do not delete history to create a fresh session.
5. Keep `deck.pdf` open as the offline fallback. Embedded screenshots show
   actual UI with the HNSW illustration explicitly identified.
6. Optional: prepare the synthetic index fixture in advance with stage controls
   enabled, then confirm the measured HNSW plan. Never prepare it while filling
   a pause on stage.

The Lab examples are Leo, Maya, and Yuki. Concierge names come from PostgreSQL;
fresh seeds use Marco, Ana, and Yuki. Introduce the **espresso regular** in
Concierge rather than assuming a display name. The portrait/personality is a
fictional narrative aid; catalog and preference facts have a separate source.

## Slide-by-slide narration

### 1. Hybrid Search in PostgreSQL

“Coffee & queries is our working example. A recommendation needs relevant
meaning, explicit terms, and current price and stock. We'll follow those
requirements through two retrieval methods, RRF, and the query plan.”

### 2. Start with the customer's request

Read the request. Bergamot is an explicit word; related citrus and floral notes
may be useful too. Twenty dollars is a requirement. Establish these separate
jobs before showing a model or an architecture diagram.

### 3. About me

Twenty seconds: name, role, why retrieval and PostgreSQL matter to your work.
Move to the example.

### 4. Two questions. Two comparisons.

Model-only versus catalog-grounded explains **why retrieval matters**. Without
catalog access, a model cannot establish this shop's current inventory and
prices. It may guess, offer general advice, or correctly ask for that data.
Do not manufacture a failure or equate eloquence with factual support.

Keyword versus vector versus hybrid explains **why combine retrieval methods**.
A grounded answer alone does not prove hybrid beats vector retrieval.

A before/after control is a useful future UI extension, not a shipped toggle
in this version. Hold model, request, generation settings, and shared system
instructions constant; disclose catalog/history/tools available to each side.
For a clean stage demo, a labeled captured run is more predictable than two
fresh model calls. See the comparison design in `docs/DEMO.md`.

### 5. Meet the regulars

Leo: curious and precise, with a budget. Maya: looking for the idea of dessert.
Yuki: wants a particular origin. Their briefs give the audience a reason to care
about the filters and vocabulary mismatch. Don't read the full profiles.

### 6. One row, two search representations

Point to text, vector, and relational columns. The same domain row carries
multiple representations. The demo uses 384 dimensions from
`BAAI/bge-small-en-v1.5`; dimensions are a model choice, not a universal optimum.
Evaluate your domain and languages. Equal dimensions do not make embeddings
from different models compatible.

### 7. Give important text more weight

Name, origin, and flavor notes are A; description is B. This is an excerpt of
the generated column in `schema.sql`; null handling is omitted for readability.
`coffee_flavor_text` is the repo's immutable text-array helper. Show stored
lexemes in Catalog later. English full-text matching uses normalized lexemes,
not exact byte equality. Refresh embeddings when their source content changes.

### 8. Retrieve lexical candidates

Name the match predicate, lexical ranking, eligibility, and candidate limit.
Parameter 32 in `ts_rank_cd` is normalization, not a hybrid weighting factor.
`websearch_to_tsquery` supports quoted phrases, OR and exclusions. The optional
trigram feature in Lab adds name candidates; keep it off for the first demo.

### 9. Retrieve semantic candidates

The ascending distance operator plus LIMIT leaves an indexable query form.
The planner can still choose a sequential scan. Display similarity as
`1 - distance`; it is not calibrated confidence. Semantic matching depends on
the selected model, corpus, and request, including language support.

### 10. Eligibility comes first

Apply the same predicates inside both branches before their candidate limits.
Filtering after top-N selection can miss eligible alternatives. This is a
logical SQL property, not a promise that HNSW visits only eligible nodes.
The ANN distinction comes on slide 18. Origin matching in this demo is a
case-insensitive substring; production country rules should use canonical codes.

### 11. Fuse ranks, not incompatible raw scores

Read one arithmetic row. Coffee A contributes from keyword rank 1 and vector
rank 3. Coffee B appears only in vector and contributes zero from keyword.
These are illustrative candidates, not a stored catalog result.

RRF rewards agreement without requiring raw score calibration. It discards
score-gap information, so evaluate it against a baseline. “Hybrid always wins”
is not a conclusion this demo supports.

### 12. RRF is a full outer join

Walk through candidate selection, `row_number`, `FULL OUTER JOIN`, zero for a
missing branch, and the final ordering. The complete query is in `search.py`
and Lab's **SQL** tab. No need to fit the entire statement on a slide.

The comparison and diagnostic reads use a repeatable-read snapshot. EXPLAIN
runs the statement again. CTEs are not a declaration that both branches execute
simultaneously; look for workers and actual scan nodes in the plan.

### 13. Three knobs that change different things

Candidate depth determines who can enter fusion; RRF k determines rank decay;
minimum cosine trims the semantic branch. Defaults are 12 candidates and k=60.
An optional cosine threshold does not apply to the lexical branch of the union.
HNSW `ef_search` is separate from all three. Vary one knob per comparison.

### 14. Live demo · seven minutes

Follow [docs/DEMO.md](../docs/DEMO.md). The order is deliberate:

1. Leo: brief → **Compare this request**, then compare three rankings.
2. Maya: “dessert,” then inspect returned flavors rather than assuming a winner.
3. One coffee: **Why this coffee** → **SQL**. Save a lengthy plan read for later.
4. Yuki: origin constraint, eligible count, appropriate empty result if absent.
5. Concierge: espresso regular → **Use this request** → Send. Wait for the
   completed recommendation, note its bean ID, then **Order that**.

Opening/closing a brief preserves the draft and current conversation. `1/2/3`
open the same briefs. **Use this request** prepares text without sending;
switching customers starts a new conversation. Follow-up controls require a
completed reply; ordering additionally requires a product recommendation.

Show the pending approval for that actual ID. The acknowledgment and product
card should agree. There is no payment, fulfillment, or stock decrement.

### 15. From a coffee's text to its vector

Open Catalog, select a coffee, compare its source text with weighted fields,
and inspect the semantic embedding. The slide screenshot is an actual stored
vector heatmap. Components are learned values without assigned flavor names.
Continue below the semantic embedding using **Follow a query through HNSW →**.

### 16. HNSW: navigate broadly, then search locally

Expand the acronym once: Hierarchical Navigable Small World. Sparse upper
layers help navigate to a region. Descent keeps the current entry point. The
base search explores multiple candidate alternatives. The schematic is a
teaching picture, not a graph exported from the PostgreSQL index.

### 17. Follow this query through the graph

Use the two-minute extension in `docs/DEMO.md`:

- Query `bergamot`, ef=4. **Trace query** if needed.
- **Next step**: inspect the full-vector distances of neighbors at an upper layer.
- Advance until descent; identify the same point on the next level.
- At layer 0, show the bounded candidate set and highlighted examined links.
- Jump to the final step. Compare its top three with exhaustive neighbors.
- Set ef=16; this resets the illustration. Jump to the final step and compare.

Rotate once and click a coffee to make the illustration tangible. Avoid
spending the whole segment on the camera controls.

The query and catalog embeddings are real. Layer membership, links and bridges
are constructed by the demo. Coordinates use PCA and small display offsets;
all distance calculations still use 384 dimensions. This is **not pgvector's
stored graph or a recorded index traversal**. The walkthrough has no budget,
stock, or origin filters and changes no database configuration. Do not transfer
its recovery numbers to a claim about pgvector.

### 18. A SQL filter is not an ANN pre-filter

Approximate index scans may visit neighbors later rejected by executor filters.
More search breadth or iterative scanning can help produce enough eligible
results, but still does not establish exact recall. Iterative scans require
pgvector 0.8+ and remain subject to scan/memory limits. Use `SET LOCAL` inside
a transaction when experimenting with a query-specific setting.

For selective filters, compare a relationally filtered exact scan. Partial
indexes or partitioning can help when their shape matches the workload; neither
is a blanket prescription.

### 19. Read the plan that actually ran

Inspect the Lab's **EXPLAIN** output. Identify scan type, index name, rows,
filters, sorts, buffers, and workers. A 16-row catalog can sensibly use a table
scan. Do not force HNSW and present the forced plan as the natural choice.
Explain that embedding, SQL, diagnostics, and model latency are separate costs.
A warm single query is not a production latency percentile.

### 20. Measure the index separately

The separate experiment creates 12,000 synthetic 384-d vectors and a real HNSW
index. The baseline is exact neighbors, not relevance labels. Recall@20 asks
how many exact neighbors ANN recovered for that query and filter.

If prepared, show **Compare indexes**, `hnsw_used`, and the plan. Both methods
use explicit planner settings, exact runs first, and cache/order effects are
reported. The fixture is a demonstration of measurement, not a benchmark of a
representative customer corpus. No unsourced latency or recall curve belongs
on stage.

### 21. Need an exact term? Make it a constraint.

RRF combines the union of two candidate sets. The published session also asks
about “similar to this question AND contains these terms.” Put the required
text predicate inside semantic retrieval for that stricter contract. It uses
lexemes, so explain quoted phrases or identifiers according to the actual text
configuration. If a semantic acceptance threshold is required, specify it too.

This is a parameterized extension pattern, not a shipped Lab mode. The runnable
example is in `SQL_PATTERNS.md`. GIN plus distance sorting may be effective for
a selective subset; the actual plan settles the physical execution question.

### 22. Evaluate the result, then add complexity

Keep relevance judgments separate from eligibility checks and ANN recovery.
Blind judging hides method labels; a handful of clicks is not a rigorous study.
Include paraphrases, exact terms, empty cases, and representative constraints.

After establishing a baseline, try bounded preference/popularity tie-breaks or
separately ranked metadata signals. Relationship expansion can define allowed
categories before retrieval; appendix slide 29 shows the SQL. These are design
extensions, not currently exposed Lab controls.

### 23. Add a conversation around the same retrieval

The architecture matches current source: FastAPI, Strands model calls, Python
orchestration, PostgreSQL retrieval, canonical rechecks, structured product
cards, and streamed prose. Intent and response are separate model roles;
models are selected by route, not fixed by the slide deck.

The agent uses history and stores audits/checkpoints/pending approvals. It does
not put the entire turn into one database transaction. Avoid claiming prompt
constraints make generated prose incapable of hallucination.

### 24. “Order that” should refer to the same coffee

Follow-up intent resolves a bean ID from the same customer's session. The
coordinator rechecks current facts and queues one bag for one verified bean.
The reply, cards, and pending approval should match. Use whichever coffee the
live run actually returned.

An approval row is an inspectable request. Manually setting its status does not
execute a fulfillment worker; none is provided here.

### 25. Be precise about what the app proves

Read the distinction most relevant to the room. Canonical cards are stronger
than generated prose. Checkpoints are inspectable but not an automatic recovery
engine. SQL/model audits use separate commits; they are not an atomic whole-turn
ledger. Data coverage is a heuristic, not confidence calibration. Authentication,
tenant isolation and load targets need work beyond this local demo.

### 26. Three things to take home

“Retrieve for meaning. Filter for eligibility. Measure before you tune.”
Tie each line back to the opening request. The evidence is the returned rows
and the plan, not the number of components on the architecture diagram.

### 27. Run it yourself

Point to the repo and README. The slide starts after dedicated database setup.
Use Python 3.11+, PostgreSQL 18, the initializer and `./run-demo.sh`; the browser
address is **8017**, not the old 8000. The project database listens on 5433.
Existing databases use documented migrations.
Do not run the destructive `schema.sql` to refresh an existing populated demo.

### 28. Thank you.

“What does your query need to preserve?” Invite questions against the live Lab,
then use the appendix if needed.

### 29. Appendix · expand a relationship before retrieval

The synthetic category tree maps Asia-Pacific → Indonesia → Sumatra. Recursive
expansion yields names used to constrain semantic ranking. `UNION` deduplicates
names in this name-only traversal; it terminates even with cycles. Production
needs canonical relationships and access rules, not substring geography.
This extension is not implemented as a Lab mode.

### 30. Appendix · operate the measured workload

HNSW m and ef_construction change graph construction. ef_search changes search
breadth. Measure recall, filtered returned count, build/update costs, and memory.
Manage text weights and document refresh alongside embeddings. Observe pool
waits, concurrent SQL, maintenance and retention. Do not infer 500 queries in
flight from 50 sessions with ten sequential queries each.

### 31. References and reproducible paths

The technical references are primary sources. Versioned PostgreSQL/pgvector
links anchor the SQL behavior. Repo source anchors the app behavior; recorded
plans anchor performance claims. Rehearse again after changing data or models.

## Questions to prepare for

| Question | Answer anchor |
| --- | --- |
| Why not just ask the model? | Without catalog access, it cannot establish current shop facts. It may correctly ask for data. Grounding versus model-only and hybrid versus vector are separate comparisons. |
| Does hybrid always beat vector? | No. Evaluate per query class. Exact terms and paraphrases create different strengths; fusion can also dilute a strong branch. |
| Why RRF instead of adding scores? | Ranks avoid assuming lexical and cosine scores share a scale. RRF loses score-gap information; evaluate weighted/reranked alternatives only against a baseline. |
| Why not require text matches in every result? | That is valid when terms are mandatory. Slide 21 shows that candidate-set change. It can exclude useful paraphrases when words are only hints. |
| Are the 3D graph's edges real? | Embeddings and distances are real. Topology/layout/traversal belong to the teaching implementation; pgvector's index is not instrumented. |
| Why doesn't the coffee query use HNSW? | Check EXPLAIN. A table scan may be cheaper on 16 rows. The separate fixture demonstrates a real HNSW scan. |
| Does a WHERE clause pre-filter HNSW? | Not necessarily. pgvector can scan approximate neighbors before executor filtering. Measure recall and returned count; consider iterative scans and selective exact search. |
| Can the two branches run in parallel? | They are logically independent, but the CTE syntax makes no concurrency promise. Inspect the plan. Separate application requests also require snapshot-consistency choices. |
| Is it multilingual? | The SQL pattern is reusable, but this demo uses English FTS and a particular embedding model. Evaluate language support; don't generalize from this corpus. |
| How large can this go? | This repo does not establish a row-count limit. Measure representative dimensions, selectivity, recall, memory, update rates and concurrency before choosing a scale strategy. |
| Is the response guaranteed correct? | No. Canonical cards constrain product facts, but generated prose can still be wrong. A data-coverage heuristic is not a probability of truth. |
| Does an approved order execute? | No. The demo stops at pending approvals; there is no payment or fulfillment worker. |
| Does a crash resume automatically? | No. Messages/checkpoints are persisted; automatic replay and side-effect idempotency need a recovery design. |
| Why no framework? | The repo uses Strands for model calls. Python controls the database steps. The retrieval contract is independent of that choice. |

## Pace and failure fallbacks

- **At 15 minutes:** start slide 14's core demo. If behind, inspect one coffee
  and one trace; keep Yuki's eligibility lesson and the approval boundary.
- **Model failure:** finish Lab; explain Concierge using slides 23–25. Never
  present an incomplete stream as proof of continuity or an approval.
- **Graph/API failure:** use slides 16–17. Label the screenshot as a captured
  illustration; do not claim a current index trace.
- **Database unavailable:** use the SQL and arithmetic slides. They explain the
  design but do not establish a successful live run.
- **At 32 minutes:** move to slide 21. Do not start fixture preparation or a
  price change. The experiment can be discussed from slide 20.
- **At 42 minutes:** finish at slide 28. Appendix is for questions.
