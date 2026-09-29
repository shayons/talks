# Hybrid Search in PostgreSQL

Conference demo and materials for **[Postgres Summit US 2026](https://2026.postgressummit.us/)**.

**Session:** [Hybrid Search in PostgreSQL: Combining Vector and Full-Text for Real-World Applications](https://postgresql.us/events/postgressummitus2026/schedule/session/2349-hybrid-search-in-postgresql-combining-vector-and-full-text-for-real-world-applications/) · **Speaker:** Shayon Sanyal · September 30, 2026 · New York City

Compare full-text search, BM25, pgvector, reciprocal rank fusion, and tuned score blending in PostgreSQL, then measure when combining methods improves retrieval.

## Explore

- [Slide deck (PDF)](deck/deck.pdf) · [Web presentation](deck/deck.html) · [Marp source](deck/deck.md) · [Speaker notes](deck/TALKING_POINTS.md)
- [Hybrid search lab](hybrid-lab/): SQL examples, Python evaluation, interactive UI, and benchmark results.
- [Claude Code plugin](hybrid-search-plugin/): adapt the search pattern to your own PostgreSQL table.

## Findings

On 2,271 test questions across four BEIR datasets, a tuned blend of local bge-small embeddings and BM25 improved NDCG@10 by 1.2–2.1 points on three datasets. Equal-weight RRF with Cohere Embed v4 did not outperform vector search alone. These public benchmarks have incomplete relevance judgments and favor keyword search; see the [lab README](hybrid-lab/README.md#what-it-found) for results and limitations.

## Install the plugin

In a Claude Code session, add the marketplace and open the plugin:

```text
/plugin marketplace add shayons/talks
/plugin install postgres-hybrid-search@shayons-talks
```

The second command opens the plugin details; select **Install** to finish. Other agents can use the [skill files](hybrid-search-plugin/skills/postgres-hybrid-search/).

For database setup and reproduction instructions, see the [hybrid search lab README](hybrid-lab/README.md).
