# Talking points · Postgres Summit US 2026

**Hybrid Search in PostgreSQL: Combining Vector and Full-Text for Real-World Applications**

Shayon Sanyal · Wednesday, September 30, 2026 · 10:30–11:20 EDT · Letterpress, Convene,
555 Broadway, New York City.

The story: **words find exact terms, vectors find paraphrases, and whether combining them
helps is a measurement.** On FiQA, with Cohere Embed v4, one vector query beat every hybrid
and reranked variant; keyword search still earns its place for exact identifiers and as a
required-term filter. Every number on the slides comes from `hybrid-lab/results/scoreboard.md`.

## Fifty-minute run of show

| Elapsed | Slides | What happens | Land this |
| --- | --- | --- | --- |
| 0:00–5:00 | 1–5 | Hook, bio, how we measure, stack | Two questions, two different misses; 648 questions with known answers |
| 5:00–17:00 | 6–10 | Slides with VS Code: `01`, `03`, `04`, `05`, `06` | AND starves recall; `ts_rank_cd` can't rank OR; BM25 in Postgres; vector 54.0 |
| 17:00–27:00 | 11–15 | `07a`, `07b`, `08a`, then the UI | Adding scores 5.6 vs RRF 33.8 on the same lists; the 403b question live |
| 27:00–33:00 | 16–20 | `09`, `11`, plans | 2 of 10 rows; iterative scan; the function's own settings |
| 33:00–39:00 | 21–23 | UI Scoreboard, rerank, storage | Vector wins on FiQA; rerank is not free; halfvec is |
| 39:00–42:00 | 24–26 | Limits, takeaways, take it home | Measure on your data; the skill |
| 42:00–44:00 | — | Buffer | |
| 44:00–50:00 | 27–29 | Q&A, appendix | |

## Preflight (the morning of the talk)

1. `cd hybrid-lab && ./scripts/setup.sh`. It must end with `pg_textsearch 1.4.0` and
   `vector 0.8.6`.
2. `uv run hybrid-lab` and open http://127.0.0.1:8018. Header should read "57,600 of 57,638
   posts embedded". Click each of the four stage questions; the Scoreboard tab must load.
3. Open VS Code on the `hybrid-lab` folder. SQLTools → connect "hybrid-lab · fiqa". In
   `py/3_ask.py`, run the first two cells with `"4641"` so the rainy-day question is active,
   then run `sql/06_vector.sql` with Cmd+E Cmd+E.
4. **Turn Wi-Fi off** and repeat step 2 with a stage question: every column, including
   Vector + Rerank, must still load (stored runs). Only typed questions need Bedrock.
5. Wi-Fi back on, run `aws sts get-caller-identity` so a typed question works live.
6. Keep `deck.pdf` open as the fallback; the coffee app remains in the repo root but is not
   part of this talk.

Backups: `pg_dump` of the `fiqa` database is in `.local/backups/` (restore with `pg_restore`
into a fresh `fiqa` database; embeddings included).

## Slide by slide

1. **Title.** "Everything today runs in one PostgreSQL 18.6 database on this laptop and is
   graded against known answers."
2. **Two questions, two misses.** Read the rainy-day question; vector ranks the best answer
   #2, keyword search #29. Read the 403b question; BM25 #1, vector #26. "So which do you
   need? That's a measurement."
3. **About me.** Twenty seconds.
4. **648 questions with known right answers.** FiQA, human judgments, NDCG@10 in one picture:
   an answer at rank 1 is worth more than three at rank 10. Credit Dave Ebbelaar's tutorial
   for the FiQA-and-NDCG approach.
5. **Stack.** Everything except two model calls is SQL. PostgreSQL 19 is in beta; not used.
6. **Schema (`01`).** Generated `tsvector` can't drift; the embedding can. Index build times.
7. **Pitfall 1 (`03`).** Run `03` in VS Code: the tsquery has `&` between every word. 405 of
   648 questions match nothing.
8. **Any word (`04`).** Recall doubles, NDCG falls to 2.8. Show the EXPLAIN: 10,460 rows
   ranked, 115 ms. "No IDF: 'fund' counts as much as 'rainy-day'."
9. **BM25 (`05`).** Same corpus: 23.6 NDCG, top 50 in 0.56 ms. In line with published BM25
   results on FiQA. Check platform availability before depending on pg_textsearch.
10. **Vector (`06`).** 54.0 at 3.9 ms. Point at `SET hnsw.ef_search = 100`: with the default
    40, LIMIT 50 returns 40.
11. **Pitfall 2 (`07a`, `07b`).** Keyword scores 1.70–5.40, cosine 0.478–0.598. Adding them
    lets keyword decide: 5.6. Stacking lists: 2.9. RRF on the same lists: 33.8.
12. **RRF with real rows.** Question 8512: BM25 4, vector 9, fused #1. "Agreement wins."
13. **RRF is a full outer join (`08a`).** One statement, two indexes.
14. **Knobs.** Lowering keyword weight gets RRF · BM25 from 41.3 to 52.0, never past 54.0.
15. **Live UI.** Pick "Keyword wins" (403b). BM25 100, vector 0, RRF · BM25 33, Vector +
    Rerank 63 ("up 24, was 26"). Hover the answer letter A across columns. Open SQL on the
    RRF column: dimmed exploration above, the executed query below the marker.
16. **Text to vector.** Input types; one model per column; 35 minutes to embed 7.7M words
    behind a tokens-per-minute quota.
17. **HNSW.** `ef_search` bounds the candidate queue and the rows returned.
18. **Pitfall 3 (`09`).** Run `09`: 2 of 10 rows, "Rows Removed by Filter: 38" (2 + 38 = 40,
    the `ef_search`). Relaxed iterative scan: 10. `heloc`: GIN plus a sort.
19. **Similar AND contains (`11`).** The function carries its settings. The
    `plan_cache_mode` line came from measurement: without it the optional filter disabled
    both indexes (335 ms instead of 86 ms).
20. **Read the plan.** Same EXPLAIN. `auto_explain` for plans inside functions.
21. **Scoreboard.** Top to bottom. Hybrid with BM25 beat vector on 98 questions, lost on 329.
    Even on the 177 questions with numbers or acronyms, vector wins 57.6 to 46.3.
22. **Rerank.** Not a bug: scores separate answers (0.55 vs 0.26), and it fixes 403b, but it
    puts a known answer first less often than Embed v4 alone. Measure the pair you use.
23. **Storage.** halfvec: same 54.0, half the index. Binary plus rescore: 53.9 at 1/16.
24. **Limits.** One laptop, one benchmark, one model pair, possible training overlap.
25. **Takeaways.** Rank words with BM25. Fuse only what earns its place. Measure before you
    ship.
26. **Take it home.** The QR code, the two install lines. The skill proposes the migration
    and waits for approval; it evaluates with labeled or synthetic questions.
27. **Thank you.**

## Live demo script

- VS Code: `py/3_ask.py` cell 2 with `"4641"`, then `sql/03_keyword_and.sql` (all three
  statements), `sql/04_keyword_or.sql` (show EXPLAIN), `sql/06_vector.sql`.
- VS Code: `sql/07a_naive_sum.sql`, first statement only (score ranges).
- UI: "Keyword wins" (9961), then "Hybrid beats both" (8512); click the fused #1 row to show
  1/(60+4) + 1/(60+9).
- VS Code: `sql/09_filtered_hybrid.sql` top to bottom.
- UI: Scoreboard tab.
- Optional, if the network is good: type a question in the UI ("Is it worth paying off a
  mortgage early?"). It is embedded on Bedrock and is unjudged.

## If something fails

| Failure | Do this |
| --- | --- |
| Bedrock or Wi-Fi down | Use only the four stage questions; everything is stored. Skip typed questions. |
| UI won't start | Run the same files in SQLTools; the slides carry the numbers and screenshots. |
| Database won't start | `./scripts/setup.sh` prints why. Otherwise present from `deck.pdf`: every number and screenshot is in it. |
| SQLTools connection fails | Terminal: `psql "postgresql://coffee:coffee@127.0.0.1:5433/fiqa" -f sql/09_filtered_hybrid.sql`, after unsetting PG* variables. |

## Questions to expect

- **"So should I not use hybrid search?"** Measure. On this paraphrase-heavy benchmark with
  a strong embedding model, blind fusion cost 13 points. Keyword search is still the tool for
  exact identifiers, for required terms as a filter, and when embeddings are weak or absent.
  Weighted fusion or routing only helps if your own evaluation says so.
- **"Why is the reranker worse?"** On FiQA, Embed v4 puts a known answer first more often
  than Rerank 3.5 reorders into first place. Newer models, and possible training overlap with
  a public benchmark. The harness is there to test any reranker, including a newer one.
- **"Is pg_textsearch available on RDS or Aurora?"** Check your platform's supported
  extensions list; I have not verified it for this talk. Native `tsvector` works everywhere.
- **"Why not ParadeDB pg_search?"** Also BM25 in PostgreSQL (AGPL). This lab uses
  pg_textsearch (PostgreSQL license); the RRF SQL works with either.
- **"ts_rank instead of ts_rank_cd?"** Neither uses corpus statistics; both lack IDF.
- **"How does this scale?"** Latency here is one laptop and one client at 57,638 rows. HNSW
  and BM25 indexes return top k without scoring every match; `ts_rank_cd` does not.
