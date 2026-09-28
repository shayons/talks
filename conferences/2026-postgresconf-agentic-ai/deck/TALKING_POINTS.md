# Talking points: Postgres Summit US 2026

**Hybrid Search in PostgreSQL: Combining Vector and Full-Text for Real-World Applications**

Shayon Sanyal, Wednesday, September 30, 2026, 10:30–11:20 EDT, Letterpress, Convene,
555 Broadway, New York City.

## What you are presenting

**Thesis, in one sentence:** hybrid search in PostgreSQL pays when you fuse correctly (BM25
plus a blend tuned on separate tuning questions), and it pays most when your embedding model is
small; with a frontier model, the tutorial default of equal-weight RRF makes results worse.

Three acts, all in one PostgreSQL 18.6 database on the laptop:

1. **The pitfalls (FiQA, VS Code).** Four ways hybrid search goes wrong without an error:
   every-word `tsquery` (405 of 648 questions match nothing), `ts_rank_cd` with no IDF
   (NDCG@10 2.8), adding scores from different scales (5.6), and a `WHERE` filter after an
   HNSW scan (1 of 10 rows). Each fix is a numbered SQL file.
2. **Fusion done right.** BM25 through pg_textsearch (23.6, BEIR's published number). RRF
   as a full outer join. A min-max blend whose weight is tuned on tuning questions only. The
   `hybrid_search()` function that carries its own settings.
3. **When hybrid pays (the gold table).** 2,271 test questions on four BEIR datasets, two
   embedding models, 95% paired bootstrap intervals. Small local model plus BM25: better on
   three of four datasets. Frontier model: equal-weight RRF never won; a tuned blend won once.

The live demo is the NFCorpus Vitamin D question, where BM25 plus bge-small (all local)
scores 97 and Cohere Embed v4 alone scores 71. It is one question; the gold table is the
average, and you say so.

## The numbers you can say

All NDCG@10 × 100. "Beyond noise" (statistically significant) means the 95% confidence range, from a paired
bootstrap over questions, doesn't include 0.
Sources: `hybrid-lab/results/summary.md` and `results/scoreboard-*.md`.

| Claim | Numbers | Confidence |
| --- | --- | --- |
| Small model + BM25, tuned blend, beats small model alone | FiQA +1.2, SciFact +2.1, NFCorpus +2.1 (all significant); SCIDOCS +0.2 (not significant) | High |
| It closes part of the gap to the frontier model | 8% FiQA, 39% SciFact, 33% NFCorpus | High |
| Equal-weight RRF with Embed v4 loses to Embed v4 alone | −12.5 FiQA, −2.9 SciFact, −1.2 SCIDOCS (significant); −1.1 NFCorpus (not) | High |
| Tuned blend with Embed v4 | +0.8 NFCorpus (significant); FiQA 0.0 (tuning chose pure vector); SciFact +0.2 (not); SCIDOCS −0.8 (not tuned, 0.5) | High |
| Rerank 3.5 never beat Embed v4 alone significantly | vector top 50: −4.1 FiQA, −1.9 NFCorpus (significant); best anywhere +0.4 (SciFact, not significant) | High |
| BM25 in PostgreSQL matches the published baseline | FiQA 23.6 = BEIR's 0.236 | High |
| Smaller index, same quality | FiQA: `halfvec` 225 MB, 53.7; binary + rescore 28 MB, 54.1; full 450 MB, 53.9 (both within noise) | High for FiQA |
| Fewer dimensions cost quality | Embed v4 at 512 dims: −1.6 to −2.7; at 256: −4.1 to −5.5 (all four datasets, significant). 1024: −0.3 to −1.2 | High |
| BM25 pays more on fewer dimensions | Embed v4 at 256 dims + BM25, tuned blend: +3.5 SciFact, +2.8 NFCorpus, +1.9 SCIDOCS (beyond noise), +0.5 FiQA (noise); wins back 46–64% of the 256-dim loss | High |
| 1024 dims saves no HNSW space | 450 MB at both 1536 and 1024 (one entry per 8 KB page); 512 → 150 MB, 256 → 75 MB | High |
| RRF's k matters little | k = 5 to 200 moves NDCG@10 by at most 4.3 (FiQA, Embed v4), 1.4 elsewhere; no k makes equal-weight RRF beat Embed v4 alone | High (sensitivity on test, not tuned) |
| Without BM25, the keyword side adds almost nothing | `ts_rank_cd` + bge-small, tuned blend: −0.1 / +0.4 / +0.7 (none significant); SCIDOCS −3.6 not tuned; 137 ms p50 on FiQA | High |
| Query shape didn't decide it | FiQA's 177 questions with a number or acronym: vector 57.7, RRF (BM25) 46.5 | High for FiQA |
| One statement runs the two lists in sequence | No Gather node; `08b` p50 8.2 ms ≈ BM25 5.2 + vector 3.5 | High |

Do not say:

- "Hybrid beats vector search." It depends on the model and the fusion; the table shows both
  directions.
- "BM25 plus a small model beats a frontier model." True on the demo question, false on
  average: bge-small + BM25 stays below Embed v4 alone on all four datasets.
- "A tuned blend never loses." With no tuning questions (SCIDOCS) it ran not tuned and lost 0.8.
- "Rerankers don't work." This reranker, with this embedding model, on these benchmarks.
- Any latency as a production number. One laptop, one client.
- "PostgreSQL runs the vector and text searches in parallel." Not inside one statement.
- "Boosting or link expansion improved results." Shown as patterns only; not measured.

## Fifty-minute run of show

| Elapsed | Slides | What happens | Land this |
| --- | --- | --- | --- |
| 0:00–5:00 | 1–6 | Hook, bio, how we measure, the four datasets, stack | Keyword misses paraphrases, vectors blur exact terms; 2,271 questions with known answers; four kinds of question |
| 5:00–13:30 | 7–11 | VS Code: `01`, `03`, `04`, `05`, `06` | AND matches nothing; `ts_rank_cd` has no IDF; BM25 in Postgres; vector 53.9 |
| 13:30–21:00 | 12–16 | `07a`, `08a`, `08c`, knobs | Adding scores 5.6 vs RRF 33.8 on the same lists; the blend and its weight |
| 21:00–26:00 | 17 | UI on NFCorpus, then FiQA 403b | Vitamin D: blend 97 vs Embed v4 71; 403b: BM25 #1, vector #26 |
| 26:00–32:00 | 18–21 | Embeddings, `09`, `11`, boost and expand | 1 of 10 rows; iterative scan; the function's own settings; two more patterns |
| 32:00–38:30 | 22–25 | Results table, smaller model, rerank, storage | Hybrid pays on a small model; equal-weight RRF never paid; rerank didn't |
| 38:30–41:30 | 26–28 | Limits, takeaways, take it home | Measure on your data; the skill |
| 41:30–44:00 | | Buffer | |
| 44:00–50:00 | 29–30 | Q&A, references | The live UI's Scoreboard tab shows every method |

## Preflight (the morning of the talk)

**One command does steps 1, 2 and 4:** `cd hybrid-lab && ./scripts/preflight.sh --open`. It
starts the database and the UI if they aren't running, checks every dataset, runs every stage
question through the UI, makes the rainy-day question active for VS Code, tests Bedrock, and
opens the deck and the Vitamin D question in Chrome. Every line should show ✓; a ✗ says what
to run. Then do steps 3, 5 and 6 by hand.

1. `cd hybrid-lab && ./scripts/setup.sh`. It must end with `pg_textsearch 1.4.0` and
   `vector 0.8.6`.
2. `uv run --extra local hybrid-lab` and open http://127.0.0.1:8018. The `local` extra lets
   typed questions get a bge-small embedding too.
3. In the header, pick **NFCorpus**: it should read "All 3,633 documents embedded". Click
   all four stage questions. Switch to **FiQA**: "All 57,600 documents embedded (38 empty in
   the source)". Those 38 FiQA posts are empty strings in BEIR, so there is nothing to embed.
   If the line ever reads "X of Y documents embedded", embedding is incomplete: re-run
   `py/2_embed.py`. Click all four FiQA stage questions. Open the Scoreboard tab on each.
4. Open VS Code on the `hybrid-lab` folder. SQLTools → connect "hybrid-lab (fiqa)". In
   `py/3_ask.py`, run the first two cells with `"4641"` so the rainy-day question is active,
   then run `sql/06_vector.sql` with Cmd+E Cmd+E.
5. **Turn Wi-Fi off** and repeat step 3. Every column must still load, including Embed v4 and
   Rerank: stage questions use stored embeddings and stored rerank runs. Only typed questions
   call Bedrock.
6. Wi-Fi back on, `aws sts get-caller-identity` so a typed question works live.
7. Present from `deck/deck.html` in Chrome: `f` for fullscreen, `p` for presenter view (notes
   and the next slide in a second window), `o` for the overview. It has 250 ms fades and click
   steps on slides 2, 12, 13 and 22; rehearse those clicks once. Keep `deck.pdf` open as the
   fallback: it shows every step in its final state.

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
2. **Two questions, two misses.** Everyday searches, not from the datasets. The slide opens
   on the keyword card: "Cancel my subscription" shares no word with "How to end your
   membership": keyword search can't see it, vector search matches the meaning. One click
   brings up "AA batteries" (to an embedding, AAA looks almost the same) and the closing
   line. Ask the room who has hit either one. Then: "You'll see real ones from the data:
   rainy-day in VS Code, and 403b, where vector search ranks the only answer #26. Which do
   you need? That's a measurement." If asked whether the examples were checked: yes, in
   PostgreSQL and with both models; the numbers are in the slide's presenter note.
3. **About me.** Twenty seconds.
4. **How we'll measure.** 2,271 test questions. FiQA is the running example. The other three
   were picked by a rule written down before measuring: under 30,000 documents, and BM25
   beat every dense retriever in BEIR's 2021 paper. Say plainly that this rule favors keyword
   search, so it favors hybrid. If asked: ColBERT, a multi-vector model, did beat BM25 on
   SciFact in that paper (0.671 vs 0.665); the rule is about one vector per document.
   NDCG@10 in one picture. Credit Dave Ebbelaar's tutorial.
   Then say the abstract's promise out loud: "combining beats either alone". Today measures
   when that's true.
5. **The four datasets.** Four kinds of question: forum questions (FiQA), science claims to
   check (SciFact), two-word health topics (NFCorpus), and paper titles whose answers are the
   papers they cite (SCIDOCS). BM25 reaches 89% of vector search on SciFact but 44% on FiQA:
   "one dataset would have told a different story." Don't claim why; the word-overlap numbers
   don't explain it.
6. **Stack.** Two embedding models on purpose: a frontier API model and a 384-dimension
   open-source model on the laptop. The database side is all open source, and the fully open
   path (bge-small + BM25) is where hybrid pays most.
7. **Schema (`01`).** Generated `tsvector` can't drift; embeddings can. One column per model.
8. **Pitfall 1 (`03`).** Run it: `&` between every word. 405 of 648 questions match nothing.
9. **Any word (`04`).** Recall doubles, NDCG falls to 2.8. 10,460 posts match; `ts_rank_cd`
   scores every one: 81 ms. "No IDF: 'fund' counts as much as 'rainy-day'." If someone
   reads the EXPLAIN: the planner chose a Seq Scan; the GIN scan alone is about 3 ms.
10. **BM25 (`05`).** 23.6, exactly BEIR's published BM25. Top 50 in 0.27 ms, because the
   index doesn't score every match.
11. **Vector (`06`).** 53.9 at 3.5 ms p50. Point at `SET hnsw.ef_search = 100`: with the
    default 40, LIMIT 50 returns 40 rows.
12. **Pitfall 2 (`07a`, `07b`).** Keyword scores 1.70–5.40, cosine 0.478–0.598. Adding them
    lets keyword decide: 5.6. Stacking lists: 2.9. RRF on the same lists: 33.8. Three
    clicks: the two score-mixing rows, then RRF, then the punchline.
13. **Fuse ranks.** Question 8512, three real top 10s. Click 1: the known answer leaves BM25
    #4 and vector #9 and lands at fused #1 (1/64 + 1/69). Click 2: each list's own #1 drops
    to #9 and #10, and the rest fills in. "Agreement wins."
14. **RRF is a full outer join (`08a`).** One statement, two indexes. 150 ms with
    `ts_rank_cd`, 8.2 ms with BM25. The abstract says "parallel execution": inside one
    statement the two lists run in sequence (no Gather node). For concurrency, two queries on
    two connections, fused in the application.
15. **Blend (`08c`).** RRF throws away how confident each list is. Min-max normalize each
    list per question, then weight. The weight is chosen on tuning questions only. On FiQA the
    tuning chose 1.0, pure vector: "the data is allowed to say don't blend."
16. **Knobs.** Depth, k, weights, `ef_search`. k measured from 5 to 200: it moves NDCG@10
    by 4.3 at most, and no k rescues equal-weight RRF with Embed v4. Weights matter more.
17. **Live UI.** See the demo script below.
18. **Text to vector.** Input types; one model per column; bge-small took about an hour on
    the laptop CPU for FiQA, Embed v4 35 minutes behind a quota.
19. **Pitfall 3 (`09`).** Run it: 1 of 10 rows, "Rows Removed by Filter: 39" (1 + 39 = 40,
    the `ef_search`). Relaxed iterative scan: 10 of 10. `heloc`: GIN plus a sort. The split
    varies between index builds; an earlier build returned 2 of 10.
20. **Similar AND contains (`11`).** The function carries its settings. `plan_cache_mode`
    came from measurement: planned generically, the vector list became a sequential scan,
    197 ms instead of 73 ms.
21. **Boost and expand.** The abstract's advanced techniques, as SQL on top of
    `hybrid_search()`: recency, popularity and preference boosts; a recursive CTE that follows
    links two hops. Both run as written; neither is measured, because BEIR has no dates or
    links. Boost a larger pool than you show.
22. **The gold table.** Read it row by row, and say what the arrows mean before reading any
    number. Three clicks: small model, frontier cut to 256 dims, full frontier. The weaker the
    vectors, the more BM25 pays: at 256 dims the blend gained 1.9 to 3.5 on three datasets.
    Small model: tuned blend up on
    three datasets, never down. Frontier model:
    equal-weight RRF down on three, never up; the tuned blend up only on NFCorpus, down on
    SCIDOCS where it couldn't be tuned. Rerank never up. If asked about SciFact's "+0.0…":
    the low end is +0.03, so it clears zero, but it is the weakest of the up arrows.
23. **When hybrid pays.** "If you can use a better embedding model, do: it beats hybrid on a
    small one. If you run a small or local model, for cost, privacy or latency, BM25 in the
    same database closes a third or more of the gap on two of four datasets." Core
    PostgreSQL alone (`ts_rank_cd`, no IDF) gained nothing significant: BM25 is what pays.
24. **Rerank.** Not a bug: rerank scores separate answers from non-answers (0.55 vs 0.26),
    and it lifts 403b from #26 to #2. But it puts a known answer first on 47.5% of FiQA
    questions against 53.9% for Embed v4 alone. Models improve; measure the pair you use.
25. **Storage.** "Quantize before you truncate." `halfvec`: half the index, same NDCG within
    noise. Binary plus rescore: 1/16 of the index, 54.1. Embed v4's shorter outputs are
    prefixes of the full vector, so one column serves every size through `subvector()`
    expression indexes. 1024 dims: same 450 MB index, because an 8 KB page still holds one
    vector. 512 and 256 shrink it 3× and 6× but lose 2 and 5 points. If you do cut to 256, add
    BM25: it won back 46% to 64% of the loss on three datasets, with 91 MB of indexes on FiQA
    against 450 MB.
26. **Limits.** One laptop; public benchmarks with incomplete judgments; two embedding models
    and one reranker; possible training overlap; SCIDOCS blends not tuned; English only, no
    phrase search; boost and link patterns unmeasured.
27. **Takeaways.** Rank words with BM25. Blend, tuned on separate tuning questions. Hybrid pays most
    on smaller models. Measure before you choose. The abstract's takeaway "choose based on
    query characteristics": on FiQA, even the 177 questions with a number or acronym favored
    vector (57.7 vs 46.5). Measure; don't guess from query shape.
28. **Take it home.** QR code, the two install lines. The skill proposes the migration and
    waits for approval, then evaluates with labeled or synthetic questions and reports RRF,
    the tuned blend and vector alone side by side.
29. **Thank you.**

## Live demo script

VS Code, before slide 8:

- `py/3_ask.py` cell 2 with `"4641"` (rainy-day).
- `sql/03_keyword_and.sql` (all three statements), `sql/04_keyword_or.sql` (show EXPLAIN),
  `sql/05_bm25.sql`, `sql/06_vector.sql`.
- `sql/07a_naive_sum.sql`, first statement only (the score ranges).

UI, slide 17 (about five minutes):

1. Paste the Vitamin D link (`#d=nfcorpus&q=PLAIN-307`). Cards: BM25 65, bge-small 77,
   tuned blend (bge-small) 97 (outlined in green, marked Highest), Embed v4 71. "Three cards
   ran on this laptop with no API. The last one is the frontier model." Green rows are the
   known answers; that is all the audience needs to track.
2. Hover answer letter A, then B and C, across the columns: the blend puts all three known
   answers in its top ranks because both lists agree on them.
3. Open **SQL** on the blend column: `08e`, the same query as `08c` with the local column.
   The dimmed part above the marker is exploration; the part below is what ran.
4. Optional: under **More methods**, tick "Tuned blend (ts_rank_cd + bge-small)" and search
   again. It scores 77, the same as bge-small alone; the BM25 blend scored 97. "Same fusion,
   no IDF: that's what BM25 buys."
5. Say: "One question. Averages in five minutes." Click **Olive oil** (blend 71, Embed v4
   60) if time allows.
6. Switch the header to **FiQA**, click **Keyword wins** (403b). BM25 100, Embed v4 0,
   RRF (BM25) 33, Embed v4 + Rerank 63. "Exact identifiers are what keyword search is for."
7. Optional: **Scoreboard** tab on NFCorpus to show every method at once.

VS Code, slides 19–20: `sql/09_filtered_hybrid.sql` top to bottom, then the last statement
in `sql/11_hybrid_function.sql`.

Optional, if the network is good: type a question in the UI ("Is it worth paying off a
mortgage early?" on FiQA). It is embedded on Bedrock and by bge-small, and it is unjudged,
so no NDCG appears.

## If something fails

| Failure | Do this |
| --- | --- |
| Bedrock or Wi-Fi down | Use only the stage questions; their embeddings and rerank runs are stored. Don't type questions. |
| UI won't start | Run the same files in SQLTools; slide 17 has the screenshot and the numbers. |
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
- **"How did you tune without cheating?"** Weights were chosen on each dataset's tuning questions
  (SciFact: its train split) and applied once to the test split. SCIDOCS has no tuning questions,
  so its blend used 0.5 and it shows.
- **"Why is the reranker worse?"** Embed v4 already puts a known answer first more often than
  Rerank 3.5 reorders one into first place. Possible training overlap with public
  benchmarks. The harness tests any reranker; try a newer one.
- **"Is pg_textsearch available on RDS or Aurora?"** It isn't in their published extension
  lists today. Core `tsvector` search works everywhere and the fusion SQL runs on it, but in
  this lab a blend with `ts_rank_cd` gained nothing significant: use BM25 where you can
  install it.
- **"The abstract said combining beats either alone."** Sometimes. With the small local model,
  a tuned blend with BM25 did, beyond noise, on three of four datasets. With the frontier
  model, equal-weight RRF never did. That is the point of measuring.
- **"Does PostgreSQL run the two searches in parallel?"** Not inside one statement: the plan
  has no Gather node, and `08b`'s 8.2 ms is about BM25's 5.2 plus vector's 3.5. Run two
  queries on two connections if the latency matters.
- **"How many dimensions should I use?"** Measure on your data, but in this lab 1024 was
  close to free in quality (−0.3 to −1.2) and saved no index space; 512 and 256 lost 2 and 5
  points. If the index is the problem, `halfvec` or binary + rescore kept quality. If you do
  cut dimensions, add BM25: at 256 it won back 46% to 64% of the loss on three datasets. With
  Embed v4 you don't need to re-embed to test it: the shorter outputs are prefixes.
- **"What k should I use?"** 60 is fine to start. From 5 to 200, k moved NDCG@10 by at most
  4.3, and no k made equal-weight RRF beat vector with Embed v4. Weights matter more.
- **"Why not ParadeDB pg_search?"** Also BM25 in PostgreSQL (AGPL). This lab uses
  pg_textsearch (PostgreSQL license); the fusion SQL works with either.
- **"ts_rank instead of ts_rank_cd?"** Neither uses corpus statistics; both lack IDF.
- **"How does this scale?"** Latency here is one laptop and one client at up to 57,638 rows.
  HNSW and BM25 indexes return the top k without scoring every match; `ts_rank_cd` does not.
