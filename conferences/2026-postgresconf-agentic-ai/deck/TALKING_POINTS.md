# Talking points: Postgres Summit US 2026

**Hybrid Search in PostgreSQL: Combining Vector and Full-Text for Real-World Applications**

Shayon Sanyal, Wednesday, September 30, 2026, 10:30–11:20 EDT, Letterpress, Convene,
555 Broadway, New York City.

## What you are presenting

**Thesis, in one sentence:** PostgreSQL can combine meaning, words and hard constraints next
to the data; measure the baselines and their combination, then keep the simplest method that
meets the application's needs.

Three acts, in one PostgreSQL 18.6 instance with one database per corpus:

1. **The pitfalls (FiQA, VS Code).** Four ways hybrid search goes wrong without an error:
   every-word `tsquery` (405 of 648 questions match nothing), `ts_rank_cd` with no IDF
   (NDCG@10 2.8), adding scores from different scales (5.6), and a `WHERE` filter after an
   HNSW scan (1 of 10 rows). Each fix is a numbered SQL file.
2. **Fusion done right.** BM25 through pg_textsearch (23.6, BEIR's published number). RRF
   as a full outer join. A min-max blend whose weight is tuned on tuning questions only. The
   `hybrid_search()` RRF/filtering example that carries its own settings.
3. **When hybrid pays (the gold table).** 2,271 test questions on four BEIR datasets, two
   embedding models, 95% paired bootstrap intervals. Small local model plus BM25: better on
   three of four datasets. Frontier model: equal-weight RRF never won; a tuned blend won once.

The live demo is the NFCorpus Vitamin D question, where BM25 plus bge-small (all local)
scores 97 and Cohere Embed v4 alone scores 71. It is one question; the gold table is the
average, and you say so.

## The numbers you can say

All NDCG@10 × 100. Arrows mark paired-bootstrap 95% intervals that exclude zero. No arrow
means inconclusive, not equivalent. These are individual intervals without a multiple-comparison
adjustment; SciFact's local-blend lower bound is only +0.03. Keep every claim scoped to this lab.
Sources: `hybrid-lab/results/summary.md` and `results/scoreboard-*.md`.

| Claim | Numbers | Scope / evidence |
| --- | --- | --- |
| Small model + BM25, tuned blend, beats small model alone | FiQA +1.2, SciFact +2.1, NFCorpus +2.1 (all significant); SCIDOCS +0.2 (not significant) | Measured in this lab |
| It closes part of the gap to the frontier model | 8% FiQA, 39% SciFact, 33% NFCorpus | Measured in this lab |
| Equal-weight RRF with Embed v4 loses to Embed v4 alone | −12.5 FiQA, −2.9 SciFact, −1.2 SCIDOCS (significant); −1.1 NFCorpus (not) | Measured in this lab |
| Tuned blend with Embed v4 | +0.8 NFCorpus (significant); FiQA 0.0 (tuning chose pure vector); SciFact +0.2 (not); SCIDOCS −0.8 (not tuned, 0.5) | Measured in this lab |
| Rerank 3.5 never beat Embed v4 alone significantly | vector top 50: −4.1 FiQA, −1.9 NFCorpus (significant); best anywhere +0.4 (SciFact, not significant) | Measured in this lab |
| BM25 in PostgreSQL matches the published baseline | FiQA 23.6 = BEIR's 0.236 | Measured in this lab |
| Smaller index, no significant quality loss detected | FiQA: `halfvec` 225 MB, 53.7; binary + rescore 28 MB, 54.1; full 450 MB, 53.9; full vectors remain stored | Measured on FiQA |
| Fewer dimensions cost quality | Embed v4 at 512 dims: −1.6 to −2.7; at 256: −4.1 to −5.5 (all four datasets, significant). 1024: −0.3 to −1.2 | Measured in this lab |
| BM25 pays more on fewer dimensions | Embed v4 at 256 dims + BM25, tuned blend: +3.5 SciFact, +2.8 NFCorpus, +1.9 SCIDOCS (significant), +0.5 FiQA (inconclusive); wins back 46–64% of the 256-dim loss | Measured in this lab |
| 1024 dims saves no HNSW space | 450 MB at both 1536 and 1024 (one entry per 8 KB page); 512 → 150 MB, 256 → 75 MB | Measured in this lab |
| RRF's k matters little | k = 5 to 200 moves NDCG@10 by at most 4.3 (FiQA, Embed v4), 1.4 elsewhere; no k makes equal-weight RRF beat Embed v4 alone | Test-set sensitivity, not tuning |
| Without BM25, the keyword side adds almost nothing | `ts_rank_cd` + bge-small, tuned blend: −0.1 / +0.4 / +0.7 (none significant); SCIDOCS −3.6 not tuned; 137 ms p50 on FiQA | Measured in this lab |
| Query shape didn't decide it | FiQA's 177 questions with a number or acronym: vector 57.7, RRF (BM25) 46.5 | FiQA only |
| These plans run the two lists in sequence | No Gather node; `08b_hybrid_rrf_bm25.sql` p50 8.2 ms ≈ BM25 5.2 + vector 3.5 | Measured plans |

Do not say:

- "Hybrid beats vector search." It depends on the model and the fusion; the table shows both
  directions.
- "BM25 plus a small model beats a frontier model." True on the demo question, false on
  average: bge-small + BM25 stays below Embed v4 alone on all four datasets.
- "A tuned blend never loses." A weight chosen on development questions can still lose on
  new questions. SCIDOCS is a separate case: its untuned 50/50 Embed v4 blend lost 0.8.
- "Rerankers don't work." This reranker, with this embedding model, on these benchmarks.
- Any latency as a production number. SQL uses one client and precomputed embeddings;
  rerank uses eight concurrent Bedrock calls. Typed-question latency includes embedding too.
- "A CTE makes the searches parallel." These measured plans execute the branches in sequence.
- "No arrow means no difference." It means the interval includes zero.
- "Boosting or link expansion improved results." Shown as patterns only; not measured.

## Fifty-minute run of show

| Elapsed | Slides | What happens | Land this |
| --- | --- | --- | --- |
| 0:00–5:00 | 1–6 | Hook, bio, how we measure, the four datasets, stack | Keyword search misses reworded questions; vector search confuses close terms like AA and AAA; 2,271 questions with known answers; four kinds of question |
| 5:00–13:30 | 7–11 | Schema on the slide; VS Code: `03_keyword_and.sql`, `04_keyword_or.sql`, `05_bm25.sql`, `06_vector.sql` | AND matches nothing; `ts_rank_cd` has no IDF; BM25 in Postgres; vector 53.9 |
| 13:30–21:00 | 12–16 | VS Code: `07a_naive_sum.sql` (first statement); RRF, the SQL join and the blend on the slides; knobs | Adding scores 5.6 vs RRF 33.8 on the same lists; the blend and its weight |
| 21:00–26:00 | 17 | UI on NFCorpus, then FiQA 403b | Vitamin D: blend 97 vs Embed v4 71; 403b: BM25 #1, vector #26 |
| 26:00–32:00 | 18–21 | Embeddings, `09_filtered_hybrid.sql`, `11_hybrid_function.sql`, boost and expand | 1 of 10 rows; iterative scan; the function's own settings; two more patterns |
| 32:00–38:30 | 22–25 | Results table, smaller model, rerank, storage | Local-model blends helped most consistently; full Embed v4 needed less help |
| 38:30–41:30 | 26–28 | Limits, three takeaways, take it home | Baselines → measure fusion → held-out choice; the skill |
| 41:30–44:00 | | Buffer | |
| 44:00–50:00 | 29–30 | Q&A, references | The live UI's Scoreboard tab shows every method |

## Preflight (the morning of the talk)

**One command does steps 1 and 2:** `cd hybrid-lab && ./scripts/preflight.sh --open`. It
starts the database and the UI if they aren't running, checks every dataset, runs every stage
question through the UI, makes the rainy-day question active for VS Code, tests Bedrock, and
opens the deck and the Vitamin D question in Chrome. Every line should show ✓; a ✗ says what
to run. Then do steps 3 to 6 by hand, in order: clicking a stage question in the UI makes it
the active question for VS Code too, so step 6 sets the rainy-day question last.

1. `cd hybrid-lab && ./scripts/setup.sh`. It must end with `pg_textsearch 1.4.0` and
   `vector 0.8.6`.
2. `uv run --extra local hybrid-lab` and open http://127.0.0.1:8018. The `local` extra lets
   typed questions get a bge-small embedding too.
3. In the header, pick **NFCorpus**: it should read "All 3,633 documents embedded". Click
   all four stage questions. Switch to **FiQA**: "All 57,600 documents embedded (38 empty in
   the source)". Those 38 FiQA posts are empty strings in BEIR, so there is nothing to embed.
   If the line ever reads "X of Y documents embedded", embedding is incomplete: re-run
   `py/2_embed.py`. Click all four FiQA stage questions. Open the Scoreboard tab on each. If
   you ticked anything under **More methods** while rehearsing, untick it: the UI remembers
   the choice in this browser. SciFact and SCIDOCS each have four stage questions too;
   check those if you plan to use them in Q&A. Preflight checks all 16 questions.
4. **Turn Wi-Fi off** and repeat step 3. Every column must still load, including Embed v4 and
   Rerank: stage questions use stored embeddings and stored rerank runs. Only typed questions
   call Bedrock.
5. Wi-Fi back on, `aws sts get-caller-identity` so a typed question works live.
6. Open VS Code on the talk folder. SQLTools → connect "hybrid-lab (fiqa)". In
   `hybrid-lab/py/3_ask.py`, run the first two cells: cell 2 makes `"4641"`, the rainy-day question,
   active. Then run `sql/06_vector.sql` with Cmd+E Cmd+E. Don't click stage questions after
   this, or the VS Code files will use that question instead. **Reset demo** also changes
   the active FiQA question to the “Vector wins” sample.
7. Present from `deck/deck.html` in Chrome: `f` for fullscreen, `p` for presenter view (notes
   and the next slide in a second window), `o` for the overview. It has 250 ms fades and click
   steps on slides 2, 12, 13 and 22; rehearse those clicks once. Keep `deck.pdf` open as the
   fallback: it shows every step in its final state.

Stage links (paste into the open tab; the UI follows the link):

- http://127.0.0.1:8018/#d=nfcorpus&q=PLAIN-307 (Vitamin D)
- http://127.0.0.1:8018/#d=fiqa&q=9961 (403b to 401k)
- http://127.0.0.1:8018/#d=fiqa&q=8512 (Roth IRA, RRF agreement)

The pills illustrate selected contrasts; use the full scoreboard for average-quality claims.
The rainy-day question (`4641`) and filter question (`988`) are the fixed SQL demonstrations.

Optional examples for Q&A:

- **FiQA:** “Vector wins” scores 100 versus BM25's 0; “Reranker rescues” moves the answer
  from vector #11 to rerank #1.
- **SciFact:** “Hybrid finds agreement” moves the evidence from #4/#3 to blend #2;
  “Blending can hurt” drops vector's #1 to blend #5.
- **NFCorpus:** “Fresh or frozen fruit” moves a second answer from local vector #11 to
  blend #3; for “Only the frontier finds it” (okra), only Embed v4 succeeds among the four
  displayed methods.
- **SCIDOCS:** “Hybrid recovers citations” finds four of five citations in the top 10;
  “Blending can hurt” loses two of the three citations found by the local vector method.

For Olive Oil, the compact legend shows the eight known answers appearing in at least one
displayed top 10. **Browse all 64 answers** opens the complete list, including the 56 not
shown. Match letters across columns. SciFact retrieves evidence that may support or refute
a claim; SCIDOCS retrieves cited papers and uses an **untuned 50/50 blend**.

Backups: `pg_dump` of the `fiqa` database is in `.local/backups/`. The other three datasets
rebuild from `py/1_load.py`, `py/2_embed.py`, `py/2b_embed_local.py` and
`scripts/evaluate_all.sh` (Bedrock needed for Embed v4 and Rerank).

## Say this: about 30 seconds a slide

These are the same words as each slide's presenter note (press `p` in `deck.html`).
[click] marks a reveal. Slides with live SQL and the UI run longer; the expanded cues
and exact demo steps follow below. Keep slide 21 and storage details brief if time is tight.

1. **Title.** Good morning. We're going to build hybrid search in PostgreSQL: words, meaning,
   and the constraints an application needs. I'll show the SQL, three easy-to-miss pitfalls,
   and how to decide whether combining results actually helps. The SQL runs on this laptop,
   with one database per corpus. Some embeddings and reranks came from Bedrock. Every
   benchmark number comes from the checked-in evaluation.
2. **Two questions, two misses.** These are two small examples I constructed and ran through
   the lab. In the help center, “cancel my subscription” misses “end your membership”: after
   stop-word removal, there are no shared terms. Vector search finds it. [click] In the store,
   vector search puts three AAA packs in the top five for “AA batteries.” BM25 gets the AA
   packs first. If AA is mandatory, make it a filter. If words are ranking signals, measure
   whether fusion helps.
3. **About me.** I'm Shayon, a Principal Worldwide PostgreSQL Specialist Solutions Architect
   at AWS. I help teams build on PostgreSQL, from relational applications to retrieval and
   agent workflows. Today we're focusing on search over your own data. The QR code goes to my
   LinkedIn if you'd like to connect afterwards.
4. **How we measure.** We need questions with known answers to judge the ranking. There are
   2,271 test questions across four BEIR datasets. FiQA, finance forums, is our running
   example. I chose the other three before measuring because keyword search did well on them
   in the original paper. That gives the keyword side a favorable test. NDCG at 10 rewards
   putting known answers near the top; throughout this talk I multiply it by 100.
5. **Four datasets.** These are four different retrieval tasks. FiQA asks forum questions.
   SciFact looks for evidence that may support or refute a claim. NFCorpus has short medical
   topics. SCIDOCS starts with a paper title and retrieves papers it cites. Look at the last
   column: Embed v4 beats BM25 on all four, but by 30 points on FiQA and only five to nine
   elsewhere. One dataset would tell an incomplete story.
6. **Stack.** The database side is PostgreSQL, pgvector, and pg_textsearch for BM25, all open
   source. I measured two embedding models: Embed v4 on Bedrock and a small open-source model,
   bge-small, on the laptop. The reranker also uses Bedrock. We have one PostgreSQL instance
   and four databases. Keep the small local model in mind: it is where adding BM25 helps most
   consistently in these measurements.
7. **Schema.** Each document has text, a generated tsvector, and an embedding column for each
   model. PostgreSQL keeps the tsvector in sync with the text. Your application must refresh
   embeddings when the text changes. Never compare vectors from different models, even if
   their dimensions match. The indexes serve different jobs: GIN finds lexical matches, HNSW
   finds nearby vectors, and the BM25 index ranks words using corpus statistics.
8. **Pitfall 1.** Plain text passed to either parser is ANDed by default. For a natural
   question, that can require far too much: on FiQA, 405 of 648 questions match nothing. Let's
   run it. Web-search syntax also supports OR, quoted phrases, and a minus sign for
   exclusions. Those are useful when the user means them. The pitfall is treating every word
   of an ordinary question as a mandatory constraint.
9. **Match any word.** Let's allow any word, then rank with ts_rank_cd. Recall at 50 doubles,
   from 6.7 to 14.6 percent, but NDCG falls to 2.8. Finding more answers and ranking them well
   are different jobs. ts_rank_cd lacks inverse document frequency: it doesn't give a term
   more weight because it's rare across the corpus. It also scores all 10,460 matches for this
   question. That takes 81 milliseconds.
10. **BM25.** BM25 adds rarity, length normalization, and diminishing returns for repeated
    words. The score rises from 2.8 to 23.6, matching BEIR's published FiQA baseline to the
    reported precision. The index can find the best matches without scoring every match. This
    question's execution time falls from 81 milliseconds to about a quarter of a millisecond.
    Those are one question's plan timings; the later benchmark medians include planning and
    the database round trip.
11. **Vector search.** For vectors, order by distance and take the top 50. Keep that distance
    expression ascending so the HNSW index can serve it. With iterative scans off, the default
    ef_search of 40 can leave LIMIT 50 short; here we use 100. The question embedding is
    already stored. FiQA scores 53.9 at a median SQL time of 3.5 milliseconds. That timing
    excludes creating the question embedding.
12. **Pitfall 2.** Here the keyword branch is ts_rank_cd. Its scores run from 1.7 to 5.4;
    cosine scores are around 0.5. Adding them lets the keyword scale dominate. [click] Across
    the test questions, the sum scores 5.6; concatenating the lists scores 2.9. [click]
    Reciprocal Rank Fusion uses ranks instead and scores 33.8. [click] Six times the naive
    sum, on the same inputs. Still below vector alone. Fixing the fusion formula doesn't
    guarantee a better search.
13. **Fuse ranks.** For this example we've switched the keyword branch to BM25. You see the
    top ten, but we fuse the top fifty from each list. [click] The known answer is fourth in
    BM25 and ninth in vector. Both contribute, so it rises to first. [click] Each list's own
    number one is absent from the other top fifty and falls to ninth or tenth. This is the
    useful case for RRF: agreement between two complementary lists.
14. **RRF in SQL.** The mechanics fit in one statement: two candidate lists, a full outer join
    on document id, and two reciprocal-rank contributions. This core-PostgreSQL example uses
    ts_rank_cd; the BM25 version is the next SQL file. Its median is 8.2 milliseconds. These
    measured plans execute the branches in sequence. A WITH clause doesn't make them
    concurrent; inspect the plan. If you need independent concurrent retrieval, two
    connections are an option.
15. **Tuned blend.** A blend is a weighted mix of keyword and vector scores, each scaled to
    zero through one. Tuned means we try different weights on separate development questions
    and choose the best NDCG at ten. Then we freeze that weight for the test questions. For
    NFCorpus with bge-small, that means 65 percent vector and 35 percent BM25 for every
    sample. The CASE prevents division by zero. These normalized scores preserve relative
    gaps; they are not confidence probabilities.
16. **Knobs.** Four knobs, four different effects. Candidate count sets what fusion and
    reranking can see. RRF's k changes the credit by rank. Weights change each list's
    contribution. ef_search changes the HNSW search effort. The k sweep is a sensitivity
    check, not test-set tuning. Change one knob at a time on development questions, then
    evaluate the final choice on held-out questions. With filters, check both recall and the
    iterative-scan budgets.
17. **Live UI.** Let's see the result, one question at a time. This is NFCorpus and the
    Vitamin D question. BM25 scores 65, the small model 77, and their blend 97; Embed v4
    scores 71. All four retrieval queries run locally. The last column uses embeddings
    previously made on Bedrock. Follow the answer letters across the lists, then open the
    blend's SQL. This is a selected teaching example; the full-dataset averages are coming
    next.
18. **Text to vector.** Three rules. Use the input types your model expects: documents and
    queries have different roles. Keep one model and version per column. And refresh
    embeddings when the text changes, using a resumable job. Multilingual retrieval needs a
    model that supports your languages. Our bge-small model and all four benchmarks are
    English; we haven't measured cross-language retrieval. On the lexical side, use the
    appropriate language configuration for both documents and queries.
19. **Pitfall 3.** A WHERE clause isn't necessarily a physical pre-filter. In this plan, HNSW
    finds forty candidates and the mortgage filter removes thirty-nine. LIMIT ten returns one.
    Iterative scanning continues the search and returns ten here, but tuple and memory budgets
    can still stop it early. Relaxed ordering also needs a final distance sort. For the rarer
    term heloc, PostgreSQL chooses GIN followed by an exact sort. Always inspect the actual
    plan.
20. **Similar and required.** Now separate two requirements: similarity determines ranking;
    mortgage is mandatory. Put that condition into both candidate queries before their LIMIT.
    This wrapper demonstrates ts_rank_cd plus RRF, with its own scan settings. The measured
    BM25/local-blend recipe is in 08e. force_custom_plan lets optional filters simplify for
    this call; otherwise the cached generic plan can miss the HNSW path. The logical filter
    belongs inside each branch, even though HNSW may apply it after candidate discovery.
21. **Boost and expand.** Two optional application patterns. A support search might favor
    recent guidance; a research search might follow citations. Rerank a larger pool than you
    display, and cap and tune boosts because they can dominate relevance. The recursive query
    follows two hops and discounts each hop. The depth bound limits work; it doesn't detect
    cycles. These examples were syntax-checked with synthetic metadata, not evaluated for
    relevance on these datasets.
22. **Results.** Each cell compares hybrid against vector using the same embedding model.
    Arrows mark paired-bootstrap 95 percent intervals that exclude zero; no arrow means the
    difference is inconclusive. [click] The local blend improves three datasets, with SciFact
    only just clearing zero. [click] At 256 dimensions, BM25 also helps on three. [click] With
    full Embed v4, gains are limited and equal-weight RRF often hurts. These are individual,
    unadjusted intervals, not a guarantee for your workload.
23. **When hybrid pays.** Here is the practical opportunity. A small local model plus BM25
    closes about a third of the gap to Embed v4 on SciFact and NFCorpus. On FiQA the gain is
    smaller. The ts_rank_cd blend shows no significant improvement, so the lexical ranker
    matters. This measured retrieval recipe uses open-source components. Embed v4 alone still
    leads on average on all four datasets; choose the model and complexity that fit your
    requirements.
24. **Rerank.** A reranker can rescue individual questions: it moves the 403b answer from
    twenty-sixth to second. Across FiQA, this model pair makes the average worse and adds a
    network call. None of the reranked methods shows a significant gain over vector across
    these datasets. It also can't retrieve an answer absent from its candidate pool. The
    reported rerank times include Bedrock, measured with eight concurrent workers. Measure
    your own model pair before adding it.
25. **Storage.** If index size is the problem, try fewer bits before fewer dimensions. On
    FiQA, halfvec halves the index and binary plus full-vector rescoring cuts it to 28
    megabytes, with no significant quality loss detected. The full vectors remain in the
    table. At 1024 dimensions, page packing leaves the index at 450 megabytes. Smaller
    dimensions do save space but lose relevance. At 256 dimensions, adding BM25 recovers about
    half the loss on three datasets.
26. **Limits.** Three limits. First, four English datasets and these model versions don't
    represent every application. Second, SQL timings use precomputed embeddings on one warm
    laptop, while reranking uses concurrent Bedrock calls. Neither is a production latency
    promise. Third, judgments are incomplete and training overlap is possible. A useful
    unjudged answer still counts as a miss, and that can favor some methods. Use this harness
    on your own questions and inspect disagreements.
27. **Takeaways.** Three things to take home. Start with strong baselines: BM25 for words,
    vectors for meaning, explicit filters for must-match requirements. Then measure fusion:
    RRF is a simple baseline; with development judgments, tune a blend. In this lab, the small
    local model benefited most consistently. Finally, choose on held-out questions, checking
    quality and latency together. If fusion adds no value, keep the simpler method. PostgreSQL
    lets you express those choices next to the data.
28. **Take it home.** The repo has the numbered SQL, Python cells, UI, and evaluation results.
    This benchmark setup includes Bedrock comparators; it isn't a turnkey local-only
    installer. The BM25 and bge-small retrieval recipe itself is fully open source. The agent
    skill adapts the pattern to your table and compares methods. Synthetic questions can help
    you get started, but validate the choice on independently judged questions before relying
    on the result.
29. **Thank you.** Thank you. Which of your queries need both exact words and meaning? Start
    with that requirement, then measure. I'm happy to take questions. The QR code goes to my
    LinkedIn, and the repo link has the SQL and results.
30. **References.** The documentation and papers are here and in the repo. Start with the
    original RRF paper for rank fusion, and Bruch, Gai and Ingber for score blending. The
    checked-in results and SQL show exactly what this talk measured.

## Slide by slide

1. **Title.** One local PostgreSQL instance, four corpus databases. SQL runs locally;
   Embed v4 embeddings and rerank scores were made on Bedrock. Stage questions work offline.
2. **Two questions, two misses.** Everyday searches, not from the datasets: two small mock
   sites, an 8-article help center and a 20-product battery aisle that, like many stores, stocks
   more AAA packs than AA, ranked in the lab with BM25 (pg_textsearch), bge-small and Embed v4.
   The slide opens on the help center; one click brings up the store and the closing line. Ask
   the room who has hit either one. Then: "You'll see real ones from the data: rainy-day in VS
   Code, and 403b, where vector search ranks the only answer #26." If asked whether the results
   are real (from `py/9_opener_examples.py`, in `results/opener_examples.md`): BM25 returns only
   the three pages that share a word ("Cancel or change an order" 2.45, "Gift subscriptions"
   1.85, "Subscription plans and pricing" 1.32) and never the membership page. Embed v4 ranks it
   first (0.412, against 0.342 for "Pause your membership"); bge-small ranks it second, behind
   "Gift subscriptions" (0.694 vs 0.726). For "AA batteries" Embed v4 still puts the AA alkaline
   24 pack first (0.551), then three AAA packs (0.529, 0.529, 0.519) above the other AA packs;
   bge-small has two AAA packs in its top 5. BM25's top 5 is the four AA packs and the AA and
   AAA charger; its first AAA pack is #7.
3. **About me.** About 30 seconds.
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
   papers they cite (SCIDOCS). Vector search leads BM25 by 30.3 points on FiQA and by 5.2 to 8.7
   on the other three: "one dataset would have told a different story." Don't claim why: the share of a
   question's words that appear in its answers (59 to 70%) doesn't explain it. Medians:
   question words 10 / 12 / 2 / 9; document words 90 / 204 / 237 / 161.
6. **Stack.** Two embedding models on purpose: a frontier API model and a 384-dimension
   open-source model on the laptop. The database side is all open source, and the fully open
   path (bge-small + BM25) is where hybrid pays most. PostgreSQL 19 is in beta and not used.
7. **Schema (`01_schema.sql`).** Generated `tsvector` can't drift; embeddings can. One column
   per model. Build times are for 57,638 posts on an M-series laptop, `maintenance_work_mem =
   1GB`, 7 parallel workers: all four timed in one session, fastest of two builds each. The
   small model's 384-dimension index builds about 3x faster than Embed v4's 1536. `m = 16` and
   `ef_construction = 64` are pgvector's defaults.
8. **Pitfall 1 (`03_keyword_and.sql`).** Run it: `&` between every word. 405 of 648 questions
   match nothing. Many tutorials, including the pgvectorscale hybrid-search example, use exactly
   this call. Plain terms default to AND. `websearch_to_tsquery` also supports `OR`,
   `"quoted phrases"` and `-excluded`; use these when the user intends a hard requirement.
   For example, `websearch_to_tsquery('english', '"mortgage insurance" -private')` produces
   `'mortgag' <-> 'insur' & !'privat'`: adjacent normalized terms, excluding private.
   Full-text matching works on lexemes, not byte-exact strings. Use an equality filter on
   a dedicated column for a mandatory product code or identifier. Phrase quality was not
   benchmarked. [PostgreSQL's query syntax](https://www.postgresql.org/docs/18/textsearch-controls.html#TEXTSEARCH-PARSING-QUERIES).
9. **Any word (`04_keyword_or.sql`).** Recall@50 doubles, 6.7 (every word, slide 8) to 14.6;
   NDCG@10 falls from 4.3 to 2.8. Both from `results/scoreboard-fiqa.md`. 10,460 posts match;
   `ts_rank_cd` scores every one: 81 ms. "No IDF: 'fund' counts as much as 'rainy-day'."
   Posts containing each word, of 57,638: rainy-day 5, park 339, emergency 1,137, day 4,991,
   fund 5,564. The standard BM25 IDF formula gives rainy-day 9.26 and fund 2.34, about 4x. If
   someone reads the EXPLAIN: the planner may pick a Bitmap Index Scan on the GIN index or
   a Seq Scan; either way finding the 10,460 matches takes a few milliseconds, and scoring
   every one with `ts_rank_cd` is the rest.
10. **BM25 (`05_bm25.sql`).** 23.6, matching BEIR's published BM25 to the reported precision.
    Top 50 in 0.27 ms, because
    the index doesn't score every match. That is execution time for this one question; slide
    14's 5.2 ms is the median wall time per question, including planning and the round trip.
    `<@>` returns the negative score so an ascending ORDER BY can use the index. Posts with none
    of the terms score 0 and can fill the LIMIT; the lab filters them out.
11. **Vector (`06_vector.sql`).** 53.9 at 3.5 ms p50. Point at `SET hnsw.ef_search = 100`: with the
    default 40 and iterative scans off, an HNSW scan can leave LIMIT 50 at 40 rows. Posts
    without an embedding are excluded explicitly so sequential and index plans agree.
    The SQL timer excludes query embedding; stage questions use stored vectors.
12. **Pitfall 2 (`07a_naive_sum.sql`, `07b_concat_dedupe.sql`).** Keyword scores 1.70–5.40,
    cosine 0.478–0.598. Adding them lets keyword decide: 5.6. Stacking lists: 2.9. RRF on the
    same lists: 33.8. The three results are NDCG@10 over 648 questions, not sums: say "out of
    100" so nobody reads 5.6 as 5.40 + 0.598. The sum uses 0 for a list that missed a document,
    so on this question a keyword-only document scores at least 1.70 and a vector-only one at
    most 0.598. If asked about `ts_rank_cd`'s normalization flags: they keep its scores in a
    range, but the range still isn't comparable to cosine. Three clicks: the two score-mixing
    rows, then RRF, then the punchline. The concatenation pattern is the one in the
    pgvectorscale hybrid-search branch: it relies on a reranker afterwards. Without one,
    whichever list goes first wins.
13. **Fuse ranks.** Question 8512, top 10 shown, top 50 fused. This switches the keyword
    input from `ts_rank_cd` to BM25. Click 1: the known answer leaves BM25
    #4 and vector #9 and lands at fused #1 (1/64 + 1/69). Click 2: each list's own #1 drops
    to #9 and #10, and the rest fills in. The question: "Is it possible to transfer stock I
    already own into my Roth IRA without having to sell the stock?" k = 60 comes from
    Cormack, Clarke and
    Büttcher (SIGIR 2009).
14. **RRF is a full outer join (`08a_hybrid_rrf.sql`).** One statement, two indexes. 150 ms with
    `ts_rank_cd`, 8.2 ms with BM25. The slide code uses `ts_rank_cd` again; call out the switch.
    The abstract says "parallel execution": these measured plans execute the lists in
    sequence. For independent concurrency, run two queries on two connections and fuse in
    the application. Do not generalize this plan to every PostgreSQL query.
15. **Blend (`08c_hybrid_blend.sql`).** RRF discards score gaps. Min-max normalization preserves
    their relative spacing, not calibrated confidence. The `hi > lo` guard handles a flat list
    or single hit. Choose the weight on development questions only, then evaluate on held-out
    test questions. On FiQA tuning chose 1.0, pure vector: that is a valid outcome.
16. **Knobs.** Depth, k, weights, `ef_search`. k measured from 5 to 200: it moves NDCG@10
    by 4.3 at most, and no k rescues equal-weight RRF with Embed v4. Weights matter more.
    Smaller k helps a little (FiQA with Embed v4: 41.3 at k = 60, 45.4 at k = 5), still far
    below vector's 53.9. The sweep (`py/7_k_sweep.py`) is a sensitivity check recomputed from
    the stored lists; no k was chosen on test questions. Tune new choices on development
    questions and keep the final test set separate.
17. **Live UI.** See the demo script below.
18. **Text to vector.** Input types; one model and version per column; bge-small took about an hour on
    the laptop CPU for FiQA, Embed v4 35 minutes behind a quota. Blank posts (38 in FiQA)
    can't be embedded and stay NULL. One judged answer is a blank post, so no method can
    find it. For multilingual retrieval, choose a model that supports the target languages
    and evaluate the language pairs your application needs. This lab's
    [bge-small-en-v1.5 is English](https://huggingface.co/BAAI/bge-small-en-v1.5);
    [Embed v4 supports multilingual retrieval](https://docs.cohere.com/docs/cohere-embed),
    but these four datasets test English only. On the lexical side, use a suitable text-search
    configuration consistently for documents and queries; it does not translate between languages.
19. **Pitfall 3 (`09_filtered_hybrid.sql`).** Run it: 1 of 10 rows, "Rows Removed by Filter: 39"
    (1 + 39 = 40, the `ef_search`). Relaxed iterative scan: 10 of 10. `heloc`: GIN plus a sort.
    The split varies between index builds; an earlier build returned 2 of 10.
    Iterative scans can stop at tuple or memory budgets before filling the LIMIT; relaxed
    ordering needs the final distance sort shown in the file.
20. **Similar AND contains (`11_hybrid_function.sql`).** The function carries its settings.
    It is a `ts_rank_cd`/Embed v4/RRF filtering example, not the BM25/local-blend recipe from
    `08e_hybrid_blend_local.sql`. The required condition is inside each branch before LIMIT;
    HNSW can still apply it after discovering candidates. Keep ranking and hard filters distinct.
    `plan_cache_mode` came from measurement: planned generically, the vector list became a
    sequential scan, 197 ms instead of 73 ms with no filter, 67 ms instead of 15 ms with
    'mortgage' (question 988, medians of 7 calls). `auto_explain` shows the plans inside the
    function.
21. **Boost and expand.** The abstract's advanced techniques, as SQL on top of
    `hybrid_search()`: recency, popularity and preference boosts; a recursive CTE that follows
    links two hops. The lab does not load application metadata or a document-link graph to
    evaluate these patterns. Boost a larger pool than you show. Both were tested with synthetic dates, likes,
    categories and links in a rolled-back session. Boost: a 30-day half-life, a log-damped
    popularity factor, and a 1.2x lift for preferred categories. Multiplication can still
    dominate relevance: cap and tune the factors. Expand: the depth bound limits work but
    does not detect cycles or prevent repeated paths before the bound, and `links` needs
    an index on `src`. PostgreSQL 14+ also has the CYCLE clause for graphs with loops.
22. **The results table.** Read it row by row, and say what the arrows mean before reading any
    number: individual paired-bootstrap 95% intervals excluding zero, without a multiple-
    comparison adjustment. No arrow means inconclusive. Three clicks: small model, Embed v4
    cut to 256 dims, full Embed v4. In this comparison, the weaker the
    vectors, the more BM25 pays: at 256 dims the blend gained 1.9 to 3.5 on three datasets.
    Small model: tuned blend up on three datasets, never down. Frontier model: equal-weight
    RRF down on three, never up; the tuned blend up only on NFCorpus, down on SCIDOCS where
    it couldn't be tuned. Rerank never up. SciFact's small-model interval starts at +0.03, so
    it clears zero, but it is the weakest of the up arrows. Blend weights at 256 dims,
    chosen on tuning questions: FiQA 0.80, SciFact 0.50, NFCorpus 0.50; SCIDOCS untuned at
    0.5. Vector-alone baselines (FiQA / SciFact / NFCorpus / SCIDOCS): small 38.0 / 72.0 /
    33.8 / 19.6; frontier 53.9 / 77.5 / 40.1 / 20.6.
23. **When hybrid pays.** "If you can use a better embedding model, do: it beats hybrid on a
    small one. If you run a small or local model, for cost, privacy or latency, BM25 in the
    same database closes a third or more of the gap on two of four datasets." Core
    PostgreSQL alone (`ts_rank_cd`, no IDF) gained nothing significant: BM25 is what pays.
    That row (`08f_hybrid_blend_native_local.sql`): -0.1, +0.4, +0.7, none significant;
    SCIDOCS, untuned at 0.5, lost 3.6. It also costs 137 ms (median) on FiQA, against 7.3 ms
    for the BM25 blend.
24. **Rerank.** Not a bug: rerank scores separate answers from non-answers (0.55 vs 0.26),
    and it lifts 403b from #26 to #2. But it puts a known answer first on 47.5% of FiQA
    questions against 53.9% for Embed v4 alone. Models improve; measure the pair you use.
    The 400 ms was measured with 8 concurrent calls from a laptop. A reranker cannot recover
    missing candidates, but candidate recall is not a numeric ceiling on NDCG@10. The union
    row takes up to 100 candidates; its Recall@50 describes the retained output.
25. **Storage.** "Try fewer bits before fewer dimensions." `halfvec`: half the index, no
    significant quality loss detected. Binary plus rescore: 1/16 of the index, 54.1. Full
    vectors remain in the table; these are index savings. Embed v4's shorter outputs are prefixes
    of the full vector, so one column serves every size through `subvector()` expression
    indexes. 1024 dims: same 450 MB index, because an 8 KB page still holds one vector. 512 and
    256 shrink it 3× and 6× but lose 2 and 5 points. If you do cut to 256, add BM25: it won back
    46% to 64% of the loss on three datasets, with 91 MB of indexes on FiQA against 450 MB. Page
    math: an HNSW entry, the vector plus its neighbor list, is about 6.3 KB at 1536 dims and 4.3
    KB at 1024, so either way one fits per 8 KB page; 512 fits three, 256 six, `halfvec(1536)`
    two. The prefix claim was checked against the API: cosine 1.0000 between the 256/512/1024
    outputs and the first N numbers. Binary takes 200 Hamming candidates and re-orders them by
    exact cosine. Embed v4 at 256 dims still beats bge-small (384) by 11 points on FiQA.
26. **Limits.** One laptop; public benchmarks with incomplete judgments; two embedding models
    and one reranker; possible training overlap; SCIDOCS blends not tuned; English only, no
    phrase evaluation; boost and link patterns unmeasured. Unjudged answers can penalize methods
    differently; inspect disagreements. SQL: one client, warm runs, precomputed embeddings.
    Rerank: eight concurrent Bedrock calls. Neither establishes production latency.
27. **Takeaways.** Three actions: establish BM25/vector baselines and explicit hard filters;
    measure RRF or a blend tuned on development questions; select on held-out quality and
    latency. If fusion does not help, keep the simpler method. On FiQA, even the 177 questions
    with a number or acronym favored vector (57.7 vs 46.5), so query shape alone is not a
    reliable routing rule. The local-model gains are evidence for a recipe to test, not a
    reason to skip that decision process.
28. **Take it home.** QR code, the two install lines. The skill proposes the migration and
    waits for approval, then evaluates with labeled or synthetic questions and reports RRF,
    the tuned blend and vector alone side by side. The current lab setup requires Bedrock;
    there is no turnkey local-only setup path. The BM25/bge-small retrieval pattern is open
    source. Synthetic questions bootstrap evaluation; independently judged questions should
    decide the final method.
29. **Thank you.**
30. **References.** The two to read first: Cormack, Clarke and Büttcher on RRF (SIGIR 2009),
    and Bruch, Gai and Ingber on blending scores (ACM TOIS 2023).

## Live demo script

VS Code, before slide 8:

- `py/3_ask.py` cell 2, which makes `"4641"` (rainy-day) active. Preflight step 6 already did.
- `sql/03_keyword_and.sql` (all three statements), `sql/04_keyword_or.sql` (show EXPLAIN),
  `sql/05_bm25.sql`, `sql/06_vector.sql`.
- `sql/07a_naive_sum.sql`, first statement only (the score ranges).

UI, slide 17 (about five minutes):

1. Paste the Vitamin D link (`#d=nfcorpus&q=PLAIN-307`). Cards: BM25 65, bge-small 77,
   tuned blend (bge-small) 97 (outlined in green, marked Highest), Embed v4 71. "All four
   retrieval queries run locally; the last column uses embeddings made on Bedrock." Green rows are the
   known answers; that is all the audience needs to track. Point to the blend explanation:
   "65% vector, 35% BM25, chosen on development questions and fixed for every test question."
2. Hover answer letter A, then B and C, across the columns: the blend puts all three known
   answers in its top ranks because both lists agree on them.
3. Open **SQL** on the blend column: `08e_hybrid_blend_local.sql`, the same query as `08c_hybrid_blend.sql` with the local column.
   The dimmed part above the marker is exploration; the part below is what ran.
4. Optional: under **More methods**, tick "Tuned blend (ts_rank_cd + bge-small)" and search
   again. It scores 77, the same as bge-small alone; the BM25 blend scored 97. "The same
   fusion recipe with ts_rank_cd and its separately tuned weight scores 77; with BM25 it
   scores 97. The lexical ranker matters too." Untick it afterwards: the UI
   remembers the choice in this browser.
5. Point to **Why this result**, then say: "One question. Averages in five minutes."
   Click **Olive oil** (blend 71, Embed v4 60) if time allows. Its legend shows eight of
   64 known answers across these top 10s; **Browse all 64 answers** opens the complete list.
6. Switch the header to **FiQA**, click **Keyword wins** (403b). BM25 100, Embed v4 0,
   RRF (BM25 + Embed v4) 33, Embed v4 + Rerank 63. "Matching 403b and 401k helps keyword search
   on this question." This one example is not a general rule for routing questions.
   The rerank card shows about 2 s: that is this question's stored run. Slide 24's
   400 ms is the median over FiQA's questions.
7. Optional: **Scoreboard** tab on NFCorpus to show every method at once.

VS Code, slides 19–20: `sql/09_filtered_hybrid.sql` top to bottom, then the last statement
in `sql/11_hybrid_function.sql`: the call on slide 20, on question 988 with
`required_terms => 'mortgage'`, 5 rows.

Optional, if the network is good: type a question in the UI ("Is it worth paying off a
mortgage early?" on FiQA). It is embedded on Bedrock and by bge-small, and it is unjudged,
so no NDCG appears.

## If something fails

| Failure | Do this |
| --- | --- |
| Bedrock or Wi-Fi down | Use only the stage questions; their embeddings and rerank runs are stored. Don't type questions. |
| UI won't start | Run the same files in SQLTools; slide 17 has the screenshot and the numbers. |
| UI shows the wrong dataset | Pick it in the header, or paste a stage link with `#d=`. |
| Need a clean demo starting point | **Reset demo** restores FiQA, the four default methods and “Vector wins”; closes panels and returns to Search. |
| Database won't start | `./scripts/setup.sh` prints why. Otherwise present from `deck.pdf`: every number and screenshot is in it. |
| SQLTools connection fails | Terminal: `psql "postgresql://postgres:postgres@127.0.0.1:5433/fiqa" -f sql/09_filtered_hybrid.sql`, after unsetting PG* variables. |

## Questions to expect

- **"Why not just use a better model?"** If you can, do. Embed v4 alone beat bge-small plus
  BM25 on every dataset. Hybrid is for when you can't or won't: documents that can't leave
  your network, embedding cost at volume, no network call per question, or a model you
  already run. Lexical ranking is useful for shared terms. For mandatory identifiers, use
  an explicit filter on an identifier column; full-text tokenization is not byte-exact matching.
- **"So should I not use RRF?"** Use it as a simple baseline, especially without development
  judgments. It discards score gaps, so measure it against each individual list. With the small model, the tuned blend beat
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
- **"Why is the reranker worse?"** We can observe that it rescues some answers and demotes
  others; Embed v4 puts a known answer first more often overall. These measurements do not
  establish the cause. Training overlap is a benchmark limitation, not a demonstrated
  explanation. Evaluate the model pair you intend to use.
- **"Is pg_textsearch available on RDS or Aurora?"** It isn't in the published
  [RDS](https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-extensions.html)
  or [Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraPostgreSQLReleaseNotes/AuroraPostgreSQL.Extensions.html)
  extension lists checked September 29, 2026. Core `tsvector` search works on both and the fusion SQL runs on it, but in
  this lab a blend with `ts_rank_cd` gained nothing significant: use BM25 where you can
  install it.
- **"The abstract said combining beats either alone."** Sometimes. With the small local model,
  a tuned blend with BM25 did on three datasets, with 95% intervals excluding zero. With the frontier
  model, equal-weight RRF never did. That is the point of measuring.
- **"Does PostgreSQL run the two searches in parallel?"** These measured plans run them in
  sequence: no Gather node, and `08b_hybrid_rrf_bm25.sql`'s 8.2 ms is close to both lists added
  together (5.2 + 3.5 = 8.7 ms), not to the slower one alone (5.2 ms). The sum overshoots a
  little because each list's own median includes its own planning and round trip. Run two
  queries on two connections if the latency matters.
- **"How many dimensions should I use?"** Measure on your data, but in this lab 1024 was
  close to free in quality (−0.3 to −1.2) and saved no index space; 512 and 256 lost 2 and 5
  points. If the index is the problem, `halfvec` or binary + rescore kept quality. If you do
  cut dimensions, add BM25: at 256 it won back 46% to 64% of the loss on three datasets. With
  Embed v4 you don't need to re-embed to test it: the shorter outputs are prefixes.
- **"What k should I use?"** 60 is fine to start. From 5 to 200, k moved NDCG@10 by at most
  4.3, and no k made equal-weight RRF beat vector with Embed v4. Weights matter more.
- **"Why not ParadeDB pg_search?"** Also BM25 in PostgreSQL (AGPL). This lab uses
  pg_textsearch (PostgreSQL license); the fusion pattern works with either, with the
  keyword branch adapted to the extension's query syntax.
- **"ts_rank instead of ts_rank_cd?"** Neither uses corpus statistics; both lack IDF.
- **"How does this scale?"** SQL latency here uses one laptop and one client at up to 57,638 rows;
  rerank uses eight concurrent Bedrock calls. We have not measured production-scale load.
  HNSW and BM25 indexes return the top k without scoring every match; `ts_rank_cd` does not.
