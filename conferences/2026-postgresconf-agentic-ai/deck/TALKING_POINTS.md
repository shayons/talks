# Talking points · Postgres Summit US 2026

**Hybrid Search in PostgreSQL: Combining Vector and Full-Text for Real-World Applications**

Shayon Sanyal · Wednesday, September 30, 2026 · 10:30–11:20 EDT · Letterpress, Convene,
555 Broadway, New York City.

## What you are presenting

**Thesis, in one sentence:** hybrid search in PostgreSQL pays when you fuse correctly (BM25
plus a blend tuned on held-out questions), and it pays most when your embedding model is
small; with a frontier model, the tutorial default of equal-weight RRF makes results worse.

Three acts, all in one PostgreSQL 18.6 database on the laptop:

1. **The pitfalls (FiQA, VS Code).** Four ways hybrid search goes wrong without an error:
   every-word `tsquery` (405 of 648 questions match nothing), `ts_rank_cd` with no IDF
   (NDCG@10 2.8), adding scores from different scales (5.6), and a `WHERE` filter after an
   HNSW scan (1 of 10 rows). Each fix is a numbered SQL file.
2. **Fusion done right.** BM25 through pg_textsearch (23.6, BEIR's published number). RRF
   as a full outer join. A min-max blend whose weight is tuned on dev questions only. The
   `hybrid_search()` function that carries its own settings.
3. **When hybrid pays (the gold table).** 2,271 test questions on four BEIR datasets, two
   embedding models, 95% paired bootstrap intervals. Small local model plus BM25: better on
   three of four datasets. Frontier model: equal-weight RRF never won; a tuned blend won once.

The live demo is the NFCorpus Vitamin D question, where BM25 plus bge-small (all local)
scores 97 and Cohere Embed v4 alone scores 71. It is one question; the gold table is the
average, and you say so.

## The numbers you can say

All NDCG@10 × 100. "Significant" means the 95% paired bootstrap interval excludes 0.
Sources: `hybrid-lab/results/summary.md` and `results/scoreboard-*.md`.

| Claim | Numbers | Confidence |
| --- | --- | --- |
| Small model + BM25, tuned blend, beats small model alone | FiQA +1.2, SciFact +2.1, NFCorpus +2.1 (all significant); SCIDOCS +0.2 (not significant) | High |
| It closes part of the gap to the frontier model | 8% FiQA, 39% SciFact, 33% NFCorpus | High |
| Equal-weight RRF with Embed v4 loses to Embed v4 alone | −12.5 FiQA, −2.9 SciFact, −1.2 SCIDOCS (significant); −1.1 NFCorpus (not) | High |
| Tuned blend with Embed v4 | +0.8 NFCorpus (significant); FiQA 0.0 (tuning chose pure vector); SciFact +0.2 (not); SCIDOCS −0.8 (untuned, 0.5) | High |
| Rerank 3.5 never beat Embed v4 alone significantly | vector top 50: −4.1 FiQA, −1.9 NFCorpus (significant); best anywhere +0.4 (SciFact, not significant) | High |
| BM25 in PostgreSQL matches the published baseline | FiQA 23.6 = BEIR's 0.236 | High |
| Smaller index, same quality | FiQA: `halfvec` 225 MB, 53.7; binary + rescore 28 MB, 54.1; full 450 MB, 53.9 | High for FiQA |

Do not say:

- "Hybrid beats vector search." It depends on the model and the fusion; the table shows both
  directions.
- "BM25 plus a small model beats a frontier model." True on the demo question, false on
  average: bge-small + BM25 stays below Embed v4 alone on all four datasets.
- "A tuned blend never loses." With no dev questions (SCIDOCS) it ran untuned and lost 0.8.
- "Rerankers don't work." This reranker, with this embedding model, on these benchmarks.
- Any latency as a production number. One laptop, one client.

## Fifty-minute run of show

| Elapsed | Slides | What happens | Land this |
| --- | --- | --- | --- |
| 0:00–4:00 | 1–5 | Hook, bio, how we measure, stack | Two questions, two different misses; 2,271 questions with known answers |
| 4:00–13:00 | 6–10 | VS Code: `01`, `03`, `04`, `05`, `06` | AND matches nothing; `ts_rank_cd` has no IDF; BM25 in Postgres; vector 53.9 |
| 13:00–21:00 | 11–15 | `07a`, `08a`, `08c`, knobs | Adding scores 5.6 vs RRF 33.8 on the same lists; the blend and its weight |
| 21:00–26:00 | 16 | UI on NFCorpus, then FiQA 403b | Vitamin D: blend 97 vs Embed v4 71; 403b: BM25 #1, vector #26 |
| 26:00–31:00 | 17–19 | Embeddings, `09`, `11` | 1 of 10 rows; iterative scan; the function's own settings |
| 31:00–38:00 | 20–23 | Gold table, smaller model, rerank, storage | Hybrid pays on a small model; equal-weight RRF never paid; rerank didn't |
| 38:00–41:00 | 24–26 | Limits, takeaways, take it home | Measure on your data; the skill |
| 41:00–44:00 | | Buffer | |
| 44:00–50:00 | 27–30 | Q&A, appendix | |

## Preflight (the morning of the talk)

1. `cd hybrid-lab && ./scripts/setup.sh`. It must end with `pg_textsearch 1.4.0` and
   `vector 0.8.6`.
2. `uv run --extra local hybrid-lab` and open http://127.0.0.1:8018. The `local` extra lets
   typed questions get a bge-small embedding too.
3. In the header, pick **NFCorpus**: it should read "All 3,633 documents embedded". Click
   all four stage questions. Switch to **FiQA**: "All 57,600 documents embedded (38 empty in
   the source)". Those 38 FiQA posts are empty strings in BEIR, so there is nothing to embed.
   If the line ever reads "X of Y documents embedded", embedding is incomplete: re-run
   `py/2_embed.py`. Click all four FiQA stage questions. Open the Scoreboard tab on each.
4. Open VS Code on the `hybrid-lab` folder. SQLTools → connect "hybrid-lab · fiqa". In
   `py/3_ask.py`, run the first two cells with `"4641"` so the rainy-day question is active,
   then run `sql/06_vector.sql` with Cmd+E Cmd+E.
5. **Turn Wi-Fi off** and repeat step 3. Every column must still load, including Embed v4 and
   Rerank: stage questions use stored embeddings and stored rerank runs. Only typed questions
   call Bedrock.
6. Wi-Fi back on, `aws sts get-caller-identity` so a typed question works live.
7. Keep `deck.pdf` open as the fallback.

Stage links (paste into the open tab; the UI follows the link):

- http://127.0.0.1:8018/#d=nfcorpus&q=PLAIN-307 (Vitamin D)
- http://127.0.0.1:8018/#d=fiqa&q=9961 (403b to 401k)
- http://127.0.0.1:8018/#d=fiqa&q=8512 (Roth IRA, RRF agreement)

Backups: `pg_dump` of the `fiqa` database is in `.local/backups/`. The other three datasets
rebuild from `py/1_load.py`, `py/2_embed.py`, `py/2b_embed_local.py` and
`scripts/evaluate_all.sh` (Bedrock needed for Embed v4 and Rerank).

## Slide by slide

1. **Title.** "Everything today runs in one PostgreSQL 18.6 database on this laptop and is
   graded against known answers."
2. **Two questions, two misses.** Rainy-day: vector ranks the best answer #2, keyword #29,
   BM25 #40. 403b: BM25 #1, vector #26. "Which do you need? That's a measurement."
3. **About me.** Twenty seconds.
4. **How we'll measure.** 2,271 test questions. FiQA is the running example. The other three
   were picked by a rule written down before measuring: under 30,000 documents, and BM25
   beat every dense retriever in BEIR's 2021 paper. Say plainly that this rule favors keyword
   search, so it favors hybrid. NDCG@10 in one picture. Credit Dave Ebbelaar's tutorial.
5. **Stack.** Two embedding models on purpose: a frontier API model and a 384-dimension
   open-source model on the laptop. Everything except model calls is SQL.
6. **Schema (`01`).** Generated `tsvector` can't drift; embeddings can. One column per model.
7. **Pitfall 1 (`03`).** Run it: `&` between every word. 405 of 648 questions match nothing.
8. **Any word (`04`).** Recall doubles, NDCG falls to 2.8. 10,460 posts match; `ts_rank_cd`
   scores every one: 81 ms. "No IDF: 'fund' counts as much as 'rainy-day'." If someone
   reads the EXPLAIN: the planner chose a Seq Scan; the GIN scan alone is about 3 ms.
9. **BM25 (`05`).** 23.6, exactly BEIR's published BM25. Top 50 in 0.27 ms, because the
   index doesn't score every match.
10. **Vector (`06`).** 53.9 at 3.5 ms p50. Point at `SET hnsw.ef_search = 100`: with the
    default 40, LIMIT 50 returns 40 rows.
11. **Pitfall 2 (`07a`, `07b`).** Keyword scores 1.70–5.40, cosine 0.478–0.598. Adding them
    lets keyword decide: 5.6. Stacking lists: 2.9. RRF on the same lists: 33.8.
12. **Fuse ranks.** Question 8512: BM25 #4, vector #9, fused #1. "Agreement wins."
13. **RRF is a full outer join (`08a`).** One statement, two indexes. 150 ms with
    `ts_rank_cd`, 8.2 ms with BM25.
14. **Blend (`08c`).** RRF throws away how confident each list is. Min-max normalize each
    list per question, then weight. The weight is chosen on dev questions only. On FiQA the
    tuning chose 1.0, pure vector: "the data is allowed to say don't blend."
15. **Knobs.** Depth, k, weights, `ef_search`. Equal-weight RRF lost on all four datasets
    with Embed v4.
16. **Live UI.** See the demo script below.
17. **Text to vector.** Input types; one model per column; bge-small took about an hour on
    the laptop CPU for FiQA, Embed v4 35 minutes behind a quota.
18. **Pitfall 3 (`09`).** Run it: 1 of 10 rows, "Rows Removed by Filter: 39" (1 + 39 = 40,
    the `ef_search`). Relaxed iterative scan: 10 of 10. `heloc`: GIN plus a sort. The split
    varies between index builds; an earlier build returned 2 of 10.
19. **Similar AND contains (`11`).** The function carries its settings. `plan_cache_mode`
    came from measurement: planned generically, the vector list became a sequential scan,
    197 ms instead of 73 ms.
20. **The gold table.** Read it row by row, and say what the arrows mean before reading any
    number. Small model: tuned blend up on three datasets, never down. Frontier model:
    equal-weight RRF down on three, never up; the tuned blend up only on NFCorpus, down on
    SCIDOCS where it couldn't be tuned. Rerank never up.
21. **When hybrid pays.** "If you can use a better embedding model, do: it beats hybrid on a
    small one. If you run a small or local model, for cost, privacy or latency, BM25 in the
    same database closes a third or more of the gap on two of four datasets."
22. **Rerank.** Not a bug: rerank scores separate answers from non-answers (0.55 vs 0.26),
    and it lifts 403b from #26 to #2. But it puts a known answer first on 47.5% of FiQA
    questions against 53.9% for Embed v4 alone. Models improve; measure the pair you use.
23. **Storage.** `halfvec`: half the index, same NDCG within noise. Binary plus rescore:
    1/16 of the index, 54.1.
24. **Limits.** One laptop; public benchmarks with incomplete judgments; two embedding models
    and one reranker; possible training overlap; SCIDOCS blends untuned.
25. **Takeaways.** Rank words with BM25. Blend, tuned on held-out questions. Hybrid pays most
    on smaller models. Measure before you choose.
26. **Take it home.** QR code, the two install lines. The skill proposes the migration and
    waits for approval, then evaluates with labeled or synthetic questions and reports RRF,
    the tuned blend and vector alone side by side.
27. **Thank you.**

## Live demo script

VS Code, before slide 7:

- `py/3_ask.py` cell 2 with `"4641"` (rainy-day).
- `sql/03_keyword_and.sql` (all three statements), `sql/04_keyword_or.sql` (show EXPLAIN),
  `sql/05_bm25.sql`, `sql/06_vector.sql`.
- `sql/07a_naive_sum.sql`, first statement only (the score ranges).

UI, slide 16 (about five minutes):

1. Paste the Vitamin D link (`#d=nfcorpus&q=PLAIN-307`). Cards: BM25 65, bge-small 77,
   tuned blend · bge-small 97 (outlined in green, marked Highest), Embed v4 71. "Three cards
   ran on this laptop with no API. The last one is the frontier model." Green rows are the
   known answers; that is all the audience needs to track.
2. Hover answer letter A, then B and C, across the columns: the blend puts all three known
   answers in its top ranks because both lists agree on them.
3. Open **SQL** on the blend column: `08e`, the same query as `08c` with the local column.
   The dimmed part above the marker is exploration; the part below is what ran.
4. Say: "One question. Averages in five minutes." Click **Olive oil** (blend 71, Embed v4
   60) if time allows.
5. Switch the header to **FiQA**, click **Keyword wins** (403b). BM25 100, Embed v4 0,
   RRF · BM25 33, Embed v4 + Rerank 63. "Exact identifiers are what keyword search is for."
6. Optional: **Scoreboard** tab on NFCorpus to show every arm at once.

VS Code, slides 18–19: `sql/09_filtered_hybrid.sql` top to bottom, then the last statement
in `sql/11_hybrid_function.sql`.

Optional, if the network is good: type a question in the UI ("Is it worth paying off a
mortgage early?" on FiQA). It is embedded on Bedrock and by bge-small, and it is unjudged,
so no NDCG appears.

## If something fails

| Failure | Do this |
| --- | --- |
| Bedrock or Wi-Fi down | Use only the stage questions; their embeddings and rerank runs are stored. Don't type questions. |
| UI won't start | Run the same files in SQLTools; slide 16 has the screenshot and the numbers. |
| UI shows the wrong dataset | Pick it in the header, or paste a stage link with `#d=`. |
| Database won't start | `./scripts/setup.sh` prints why. Otherwise present from `deck.pdf`: every number and screenshot is in it. |
| SQLTools connection fails | Terminal: `psql "postgresql://coffee:coffee@127.0.0.1:5433/fiqa" -f sql/09_filtered_hybrid.sql`, after unsetting PG* variables. |

## Questions to expect

- **"Why not just use a better model?"** If you can, do. Embed v4 alone beat bge-small plus
  BM25 on every dataset. Hybrid is for when you can't or won't: documents that can't leave
  your network, embedding cost at volume, no network call per question, or a model you
  already run. And keyword search stays the tool for exact identifiers and required terms,
  whatever the model.
- **"So should I not use RRF?"** Not with equal weights and a strong model without measuring
  it. RRF discards how confident each list is. With the small model, the tuned blend beat
  RRF by 4.3 on FiQA and was within 0.5 on the other three. With the frontier model, the
  tuned blend never did worse than vector where it could be tuned. Bruch, Gai and Ingber
  (ACM TOIS 2023) found a tuned convex combination beat RRF and needed only a small set of
  examples to tune.
- **"Didn't you pick datasets where hybrid wins?"** The rule was written before measuring,
  and it favors keyword search: BM25 beat dense retrievers on those sets in 2021. Even there,
  equal-weight RRF with a current model lost. FiQA was picked first, from Dave Ebbelaar's
  tutorial, and it is the dataset where hybrid does worst.
- **"Is +2 NDCG worth it?"** About 3–6% relative on these sets. It costs an extra index and
  a few milliseconds (FiQA blend p50 7.3 ms vs 2.0 ms for bge-small alone). Whether that is
  worth it is a product question; the harness gives you the number.
- **"How did you tune without cheating?"** Weights were chosen on each dataset's dev split
  (SciFact: its train split) and applied once to the test split. SCIDOCS has no dev split,
  so its blend used 0.5 and it shows.
- **"Why is the reranker worse?"** Embed v4 already puts a known answer first more often than
  Rerank 3.5 reorders one into first place. Possible training overlap with public
  benchmarks. The harness tests any reranker; try a newer one.
- **"Is pg_textsearch available on RDS or Aurora?"** Check your platform's supported
  extensions list; I have not verified it for this talk. Native `tsvector` works everywhere,
  and the RRF and blend SQL work with it (NDCG is lower without IDF).
- **"Why not ParadeDB pg_search?"** Also BM25 in PostgreSQL (AGPL). This lab uses
  pg_textsearch (PostgreSQL license); the fusion SQL works with either.
- **"ts_rank instead of ts_rank_cd?"** Neither uses corpus statistics; both lack IDF.
- **"How does this scale?"** Latency here is one laptop and one client at up to 57,638 rows.
  HNSW and BM25 indexes return the top k without scoring every match; `ts_rank_cd` does not.
