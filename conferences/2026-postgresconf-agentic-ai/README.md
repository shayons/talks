# Hybrid Search in PostgreSQL

Conference material for **[Postgres Summit US 2026](https://2026.postgressummit.us/)**, New York City.

**Session:** [Hybrid Search in PostgreSQL: Combining Vector and Full-Text for Real-World Applications](https://postgresql.us/events/postgressummitus2026/schedule/session/2349-hybrid-search-in-postgresql-combining-vector-and-full-text-for-real-world-applications/)

**Speaker:** Shayon Sanyal · **When:** Wednesday, September 30, 2026, 10:30–11:20 EDT · **Where:** Letterpress, Convene, 555 Broadway

| Start here | What it is |
| --- | --- |
| [`hybrid-lab/`](hybrid-lab/) | The live demo: full-text, BM25, pgvector, RRF, a tuned blend and rerank in PostgreSQL 18, each graded on 2,271 questions with known answers from four BEIR datasets. Numbered SQL files, VS Code cells, and a small UI. |
| [`hybrid-search-plugin/`](hybrid-search-plugin/) | A downloadable agent skill that adds hybrid search to **your** table and measures it. |
| [`deck/`](deck/) | Slides ([HTML, with animations](deck/deck.html), [PDF](deck/deck.pdf), [Marp source](deck/deck.md)) and [talking points](deck/TALKING_POINTS.md). |

## What the talk shows

Hybrid search in PostgreSQL pays when you fuse correctly, and pays most when your embedding
model is small. Measured on four BEIR datasets with 95% bootstrap intervals:

- **Small local model (bge-small) + BM25, tuned blend:** +1.2 to +2.1 NDCG@10 over the small
  model alone on three of four datasets, closing up to 39% of the gap to a frontier model.
- **Frontier model (Cohere Embed v4) + BM25, equal-weight RRF:** never better than vector
  search alone, and significantly worse on three datasets. A blend tuned on dev questions
  won once.
- **Cohere Rerank 3.5:** never better than Embed v4 alone by more than noise.
- **Four pitfalls** that fail silently: every-word `tsquery`, `ts_rank_cd` without IDF,
  adding scores from different scales, and filtering after an HNSW scan.

Details and every number: [`hybrid-lab/README.md`](hybrid-lab/README.md#what-it-found).

## Take the skill home

In Claude Code:

```text
/plugin marketplace add shayons/talks
/plugin install postgres-hybrid-search@shayons-talks
```

Then ask: "Add hybrid search to my `articles` table and tell me if it helps." Other agents
that read `SKILL.md` folders can use
[`hybrid-search-plugin/skills/postgres-hybrid-search/`](hybrid-search-plugin/skills/postgres-hybrid-search/)
directly.

## Earlier demo

The first demo for this talk, a coffee catalog with an agentic concierge, is no longer in this
folder. It is in the git history up to commit `46c7254`.
