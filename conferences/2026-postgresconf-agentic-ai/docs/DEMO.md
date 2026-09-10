# A seven-minute Coffee & queries demo

The through-line: **words find explicit matches, vectors find related meaning,
and PostgreSQL keeps the results inside the customer's constraints.** Show that
comparison before introducing the agent.

## Before presenting

- Start `./scripts/postgres18.sh start`, then `./run-demo.sh`, and open
  `http://localhost:8017/`. Confirm status reports PostgreSQL 18.
- Rehearse Leo's Lab request once to warm the local embedding model.
- Check the catalog price used in the example. If a previous price experiment
  is still active, restore it from Experiments before rehearsing Leo.
- In Concierge, select the model route you intend to use and complete one
  recommendation. A connected database does not establish model access.
- Start a **New session** before the live conversation. This clears the visible
  session without deleting saved history.

Persona cards open a brief. **Close** or **Escape** returns to the current work.
**Compare this request** runs a Lab comparison; **Use this request** prepares
the Concierge composer without sending. The `1`, `2`, and `3` shortcuts open
the same briefs.

## The run of show

| Time | Action | Point to land |
| --- | --- | --- |
| 0:00–1:30 | In **Lab**, meet **Leo** and compare his bergamot request with a $20 maximum. Point to the three rankings and any excluded word matches. | “An exact word match matters. So does the budget. We apply the same eligibility rules before each method chooses candidates.” |
| 1:30–2:30 | Meet **Maya** and compare “dessert.” Check the actual keyword list and the related flavors in vector results. | “People don't always use the catalog's vocabulary. Related meaning can recover candidates that an exact word search misses.” |
| 2:30–3:30 | Select a coffee, open **Why this coffee**, then **SQL**. Use **EXPLAIN** if the audience asks about execution. | “Hybrid combines ranks with RRF. We can inspect the contributions and the statement that produced them.” |
| 3:30–4:30 | Meet **Yuki** and compare “Coffee from Japan.” Inspect the origin filter and eligible count. | “Similarity cannot turn a coffee from another country into Japanese coffee. If the catalog has no eligible rows, empty is the correct result.” |
| 4:30–6:30 | Open **Concierge**, meet the espresso regular, choose **Use this request**, and send “Cold brew options.” Note the recommended coffee, then use **Order that**. | “The conversation refers back to the recommendation. Inspect the pending approval and its bean ID. The demo queues a request; it does not fulfill a purchase.” |
| 6:30–7:00 | Return to **Demo guide** or the Lab comparison. | “The agent adds a conversation. The database still owns the facts, eligibility, and action record.” |

Names in Concierge come from PostgreSQL. The standard Lab examples are Leo,
Maya, and Yuki; fresh Concierge seeds may display Marco, Ana, and Yuki.

## Keep the story bounded

- Open each brief long enough to introduce the person; don't read every line.
- Inspect one coffee's rank contributions and one trace. Let the audience ask
  for more SQL.
- **Order that** becomes available after a completed reply contains a product.
  If no coffee is recommended, refine the request before trying the order.
- Keep blind judging, the price experiment, the measured HNSW fixture, and MCP
  for questions or a longer session. The full conference deck adds the bounded
  Catalog walkthrough below after the seven-minute sequence.
- Describe the rows actually returned. A changed catalog can change a ranking
  or turn an empty result into a match.
- If model access fails, finish with the Lab, SQL, and EXPLAIN. They use the local
  embedding model and PostgreSQL. Do not present a failed Concierge run as proof
  of memory or approval behavior.

## Add two minutes: follow the query through HNSW

The conference deck uses this extension on slide 17, after the core demo and
the embedding/hierarchy explanation.

| Time | Action | Point to land |
| --- | --- | --- |
| 0:00–0:30 | Open **Catalog**, select a coffee, and go below **Semantic embedding** using **Follow a query through HNSW →**. Keep `bergamot` and ef=4. | “These are stored catalog vectors and a real query embedding. The links are a teaching construction.” |
| 0:30–1:00 | Use **Next step** through an upper-layer comparison and a descent. Rotate once; click a coffee to inspect its distance. | “Move toward closer neighbors, then use the same point to enter a more detailed layer.” |
| 1:00–1:30 | Step into layer 0. Inspect the candidates and highlighted links. | “The base search explores alternatives within a bounded candidate set. Distances use all 384 dimensions.” |
| 1:30–2:00 | Use the step slider to reach the final step. Change ef to 16, then jump to the final step again. | “Compare the neighbors this teaching search recovered with exhaustive search. More search work can improve recovery.” |

The view uses projected coordinates, constructed layers/links, and visual
offsets. It is **not pgvector's stored graph or an observed index traversal**.
It applies no eligibility filters and changes no database settings. Use
**Experiments** for a real HNSW scan and measured recall; don't attribute the
illustration's numbers to the database index.

## Proposed before/after comparison: model only versus grounded

This comparison explains why an application needs access to current facts.
It is a proposed UI addition, not a control available in the current app.
The Lab's **Keyword / Vector / Hybrid** comparison separately explains why
retrieval methods are combined.

Use one request, such as “Which coffee in this shop has bergamot notes and
costs at most $20?” Hold the model, generation settings, and shared instructions
constant. Disclose each side's inputs:

- **Model only:** the request, without catalog, database tools, or prior
  recommendations. The model may offer general advice or correctly say that
  it needs the catalog. Preserve that outcome.
- **Grounded in PostgreSQL:** the same request with retrieved, eligible catalog
  rows. Show supported names, prices, stock and the evidence behind them.

Compare factual support, constraint satisfaction, and appropriate uncertainty;
do not score a more fluent answer as a better answer. Keep ordering disabled
on both comparison panels. Do not leak retrieved results or session history
into the model-only prompt.

For stage reliability, use an actual captured comparison with its query,
model/settings, timestamp, context disclosure and catalog snapshot visible;
label it **Recorded example**. A later live option should show genuine output
and errors independently on each side. Never invent a model response to make
the “before” panel look worse.
