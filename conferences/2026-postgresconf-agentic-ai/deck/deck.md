---
marp: true
theme: hybrid-search
paginate: true
title: "Hybrid Search in PostgreSQL: Combining Vector and Full-Text for Real-World Applications"
author: "Shayon Sanyal"
description: "Postgres Summit US 2026, New York City, September 30, 2026"
footer: "Hybrid Search in PostgreSQL, Postgres Summit US 2026, NYC"
size: 16:9
transition: fade 250ms
---

<!-- _class: title -->
<!-- _paginate: false -->

# Hybrid Search in PostgreSQL

## Combining Vector and Full-Text for Real-World Applications

<div class="byline">
Shayon Sanyal, Principal Worldwide PostgreSQL Specialist SA
</div>

<div class="meta">
Postgres Summit US 2026, New York City<br>
September 30, 10:30–11:20 EDT, Letterpress
</div>

<!--
Say: Good morning. We're going to build hybrid search in PostgreSQL: words, meaning, and the
constraints an application needs. I'll show the SQL, three easy-to-miss pitfalls, and how to
decide whether combining results actually helps. The SQL runs on this laptop, with one database
per corpus. Some embeddings and reranks came from Bedrock. Every benchmark number comes from the
checked-in evaluation.
-->

---

## Two questions. Two different misses.

<div class="miss-grid">
<div class="miss">
<span class="eyebrow">Keyword search (BM25) misses</span>
<div class="window">
<div class="window-bar"><i></i><i></i><i></i><span>help.example.com</span></div>
<div class="searchbox">How do I cancel my subscription?</div>
<ol class="results">
<li class="wrong"><span class="hit"><b><mark>Cancel</mark> or change an order</b><small>You can <mark>cancel</mark> or change an order until it ships.</small></span><em>Wrong page</em></li>
<li class="wrong"><span class="hit"><b>Gift <mark>subscriptions</mark></b><small>Buy a <mark>subscription</mark> for someone else.</small></span><em>Wrong page</em></li>
<li class="wrong"><span class="hit"><b><mark>Subscription</mark> plans and pricing</b><small>Compare plans and prices.</small></span><em>Wrong page</em></li>
</ol>
<p class="missing">Never returned: <strong>How to end your membership</strong><br>No shared terms after stop-word removal.</p>
</div>
<p class="miss-note">Vector search (Embed v4) ranks the membership page first.</p>
</div>
<div class="miss" data-marpit-fragment>
<span class="eyebrow">Vector search (Embed v4) misses</span>
<div class="window">
<div class="window-bar"><i></i><i></i><i></i><span>shop.example.com</span></div>
<div class="searchbox">AA batteries</div>
<ol class="results">
<li><span class="thumb"><span class="cell aa"></span><span class="cell aa"></span></span><span class="hit"><b>AA alkaline batteries, 24 pack</b></span><em class="ok">✓</em></li>
<li class="wrong"><span class="thumb"><span class="cell aaa"></span><span class="cell aaa"></span></span><span class="hit"><b>AAA alkaline batteries, 48 pack</b></span><em>Wrong size</em></li>
<li class="wrong"><span class="thumb"><span class="cell aaa"></span><span class="cell aaa"></span></span><span class="hit"><b>AAA batteries, 12 pack</b></span><em>Wrong size</em></li>
<li class="wrong"><span class="thumb"><span class="cell aaa"></span><span class="cell aaa"></span></span><span class="hit"><b>AAA alkaline batteries, 24 pack</b></span><em>Wrong size</em></li>
<li><span class="thumb"><span class="cell aa"></span><span class="cell aa"></span></span><span class="hit"><b>AA lithium batteries, 8 pack</b></span><em class="ok">✓</em></li>
</ol>
</div>
<p class="miss-note">Embed v4 ranks AA packs at #1 and #5, with three AAA packs between them.</p>
</div>
</div>

<p class="miss-takeaway"><strong>Two constructed examples.</strong><br>
<strong>Today:</strong> See where each search method misses, then test whether combining them helps.</p>

<!--
Say: These are two small examples I constructed and ran through the lab. In the help center,
“cancel my subscription” misses “end your membership”: after stop-word removal, there are no
shared terms. Vector search finds it. [click] In the store, Embed v4 ranks AA at #1 and #5,
with three AAA packs at #2–#4. BM25 puts three AA packs in its first three spots. If AA is
mandatory, make it a filter. If words are ranking signals, measure whether fusion helps.
-->

---

<!-- _class: bio -->
<!-- _paginate: false -->

<div class="bio-grid">
<div class="bio-photo">

![Shayon Sanyal](assets/shayon-headshot.jpg)

</div>
<div class="bio-text">

## About me

# Shayon Sanyal

**Principal Worldwide PostgreSQL Specialist SA**

I help teams build on PostgreSQL, from relational applications to retrieval and agent workflows.

<div class="bio-links"><img src="assets/qr-linkedin.svg" alt="QR code: linkedin.com/in/shayonsanyal"><span>linkedin.com/in/shayonsanyal</span></div>

</div>
</div>

<!--
Say: I'm Shayon, a Principal Worldwide PostgreSQL Specialist Solutions Architect at AWS. I help
teams build on PostgreSQL, from relational applications to retrieval and agent workflows. Today
we're focusing on search over your own data. The QR code goes to my LinkedIn if you'd like to
connect afterwards.
-->

---

<!-- _class: split-evidence measure -->

## How we'll measure

<div class="evidence-grid">
<div>

# 2,271 questions with known answers.

Main example: **FiQA**, finance forums.

**SciFact, NFCorpus, SCIDOCS:** picked before measuring, where keyword search beat vector
search in BEIR's 2021 paper.

**NDCG@10** gives more credit when known answers rank near the top.

**We'll measure when combining beats either alone, and when it doesn't.**

</div>
<div>
<div class="evidence-image">

![NDCG@10 gives more credit to answers at higher ranks](assets/ndcg.svg)

</div>
<dl class="glossary">
<dt>FiQA</dt><dd>Financial Opinion Mining and Question Answering (2018)</dd>
<dt>SciFact</dt><dd>Science claims checked against research abstracts</dd>
<dt>NFCorpus</dt><dd>NutritionFacts.org questions answered by medical abstracts</dd>
<dt>SCIDOCS</dt><dd>Science paper titles matched to the papers they cite</dd>
<dt>BEIR</dt><dd>A public benchmark of 18 search datasets (Thakur et al., 2021)</dd>
<dt>NDCG@10</dt><dd>Normalized Discounted Cumulative Gain, top 10 results; 100 is perfect</dd>
</dl>
</div>
</div>

<!--
Say: We need questions with known answers to judge the ranking. There are 2,271 test questions
across four BEIR datasets. FiQA, finance forums, is our running example. I chose the other three
before measuring because keyword search did well on them in the original paper. That gives the
keyword side a favorable test. NDCG at 10 rewards putting known answers near the top; throughout
this talk I multiply it by 100.
-->

---

<!-- _class: dense datasets -->

## Four datasets, four kinds of question

| Dataset: what it searches | A typical test question | Test questions | Known answers per question | NDCG@10: BM25 vs vector (Embed v4) | Vector ahead by |
| --- | --- | ---: | ---: | ---: | ---: |
| **FiQA**: 57,638 finance forum posts | “Where should I park my rainy-day / emergency fund?” | 648 | 2.6 | 23.6 vs 53.9 | **30.3** |
| **SciFact**: 5,183 science abstracts | “Anthrax spores can be disposed of easily after they are dispersed.” A claim to check | 300 | 1.1 | 68.8 vs 77.5 | 8.7 |
| **NFCorpus**: 3,633 medical abstracts | “low-carb diets.” Half are two words or fewer | 323 | 38.2,<br>graded&nbsp;1&nbsp;or&nbsp;2 | 32.3 vs 40.1 | 7.8 |
| **SCIDOCS**: 25,657 paper abstracts | “A Fast Learning Algorithm for Deep Belief Nets.” A title; its answers are papers it cites | 1,000 | 4.9 | 15.4 vs 20.6 | 5.2 |

Vector search wins on all four, by **30.3 points** on FiQA but only **5 to 9** on the others. One dataset would have told a different story.

<!--
Say: These are four different retrieval tasks. FiQA asks forum questions. SciFact looks for
evidence that may support or refute a claim. NFCorpus has short medical topics. SCIDOCS starts
with a paper title and retrieves papers it cites. Look at the last column: Embed v4 beats BM25
on all four, but by 30 points on FiQA and only five to nine elsewhere. One dataset would tell an
incomplete story.
-->

---

<!-- _class: stack -->

## The stack: one PostgreSQL instance

| Piece | Version | Job |
| --- | --- | --- |
| PostgreSQL | **18.6** | `tsvector`, GIN, `ts_rank_cd`, the SQL that combines and scores results |
| pgvector | **0.8.6** | `vector(1536)`, HNSW, iterative index scans, `halfvec`, `bit` |
| pg_textsearch | **1.4.0** | BM25 index and `<@>` operator (PostgreSQL license) |
| Cohere Embed v4 on Amazon Bedrock | 1536 dims | Posts as `search_document`, questions as `search_query` |
| Cohere Rerank on Amazon Bedrock | 3.5 | Reorders a top 50 outside the database |
| bge-small-en-v1.5 with fastembed | 384 dims | A small open-source model, on this laptop |
| VS Code + SQLTools | | Numbered SQL files you can run yourself |

One database per corpus. PostgreSQL, pgvector, pg_textsearch and bge-small are open source.
Embed v4 and Rerank use Bedrock; SQL runs on this laptop.

<!--
Say: The database side is PostgreSQL, pgvector, and pg_textsearch for BM25, all open source. I
measured two embedding models: Embed v4 on Bedrock and a small open-source model, bge-small, on
the laptop. The reranker also uses Bedrock. We have one PostgreSQL instance and four databases.
Keep the small local model in mind: it is where adding BM25 helps most consistently in these
measurements.
-->

---

<!-- _class: code-first -->

## One row, three representations <span class="file">01_schema.sql</span> <span class="file">02_indexes.sql</span>

```sql
CREATE TABLE docs (
  id              text PRIMARY KEY,
  body            text NOT NULL,
  tsv             tsvector GENERATED ALWAYS AS (to_tsvector('english', body)) STORED,
  embedding       vector(1536),  -- Cohere Embed v4, input_type = 'search_document'
  embedding_local vector(384)    -- bge-small-en-v1.5, open source, local
);
CREATE INDEX ON docs USING gin (tsv);                                  --  1.0 s
CREATE INDEX ON docs USING hnsw (embedding vector_cosine_ops);         -- 46.5 s
CREATE INDEX ON docs USING hnsw (embedding_local vector_cosine_ops);   -- 14.3 s
CREATE INDEX ON docs USING bm25 (body) WITH (text_config = 'english'); --  5.7 s
```

The tsvector is **generated** and cannot drift from the text. Embeddings are not:
**one column per model**, re-embedded when the text changes.

<!--
Say: Each document has text, a generated tsvector, and an embedding column for each model.
PostgreSQL keeps the tsvector in sync with the text. Your application must refresh embeddings
when the text changes. Never compare vectors from different models, even if their dimensions
match. The indexes serve different jobs: GIN finds lexical matches, HNSW finds nearby vectors,
and the BM25 index ranks words using corpus statistics.
-->

---

<!-- _class: code-first -->

## Pitfall 1: every word must match <span class="file">03_keyword_and.sql</span>

```sql
SELECT websearch_to_tsquery('english', 'Where should I park my rainy-day / emergency fund?');
--  'park' & 'rainy-day' <-> 'raini' <-> 'day' & 'emerg' & 'fund'
```

Plain words are joined with **AND** by default. A natural question rarely has all its
words in one answer. `websearch_to_tsquery` also accepts `OR`, quoted phrases and negation.

<p class="formula">405 of 648 questions match no post at all. NDCG@10: 4.3</p>

<!--
Say: Plain text passed to either parser is ANDed by default. For a natural question, that can
require far too much: on FiQA, 405 of 648 questions match nothing. Let's run it. Web-search
syntax also supports OR, quoted phrases, and a minus sign for exclusions. Those are useful when
the user means them. The pitfall is treating every word of an ordinary question as a mandatory
constraint.
-->

---

<!-- _class: code-first -->

## Match any word, rank the matches <span class="file">04_keyword_or.sql</span>

```sql
WITH question AS (
  SELECT replace(plainto_tsquery('english', body)::text,
                 ' & ', ' | ')::tsquery AS tsq
    FROM active_query
)
SELECT d.id, ts_rank_cd(d.tsv, q.tsq) AS score
  FROM docs d, question q
 WHERE d.tsv @@ q.tsq
 ORDER BY score DESC
 LIMIT 50;
```

Known answers anywhere in the top 50 (Recall@50) double, **6.7% → 14.6%** (every word vs any word), but
NDCG@10 **falls to 2.8**. `ts_rank_cd` has no IDF (inverse document frequency): “fund”, in 5,564
posts, counts as much as “rainy-day”, in 5. The rainy-day question matches **10,460 posts**, and
`ts_rank_cd` scores every one of them: **81 ms**.

<!--
Say: Let's allow any word, then rank with ts_rank_cd. Recall at 50 doubles, from 6.7 to 14.6
percent, but NDCG falls to 2.8. Finding more answers and ranking them well are different jobs.
ts_rank_cd lacks inverse document frequency: it doesn't give a term more weight because it's
rare across the corpus. It also scores all 10,460 matches for this question. That takes 81
milliseconds.
-->

---

<!-- _class: code-first -->

## `ts_rank_cd` is not BM25 <span class="file">05_bm25.sql</span>

```sql
SELECT id, -(body <@> to_bm25query(:'question', 'docs_body_bm25')) AS bm25
  FROM docs
 ORDER BY body <@> to_bm25query(:'question', 'docs_body_bm25')
 LIMIT 50;
```

BM25 weighs rare terms up (IDF), saturates repeats, and normalizes for length. The index
keeps the corpus statistics and returns the top 50 **without scoring every match**.
23.6 is exactly BEIR's published BM25 score for FiQA (0.236).

| Keyword method | NDCG@10 | Execution time, rainy-day question |
| --- | ---: | ---: |
| `ts_rank_cd`, any word | 2.8 | 81 ms |
| BM25, pg_textsearch | **23.6** | **0.27 ms** |

<!--
Say: BM25 adds rarity, length normalization, and diminishing returns for repeated words. The
score rises from 2.8 to 23.6, matching BEIR's published FiQA baseline to the reported precision.
The index can find the best matches without scoring every match. This question's execution time
falls from 81 milliseconds to about a quarter of a millisecond. Those are one question's plan
timings; the later benchmark medians include planning and the database round trip.
-->

---

<!-- _class: code-first -->

## Vector search: the top 50 by meaning <span class="file">06_vector.sql</span>

```sql
SET hnsw.ef_search = 100;          -- default 40 limits a non-iterative HNSW scan
SELECT id, 1 - (embedding <=> (SELECT embedding FROM active_query)) AS cosine
  FROM docs
 WHERE embedding IS NOT NULL
 ORDER BY embedding <=> (SELECT embedding FROM active_query)
 LIMIT 50;
```

Keep the distance operator in `ORDER BY`, ascending, with a `LIMIT`. Embed questions as
`search_query` and posts as `search_document`.

NDCG@10 **53.9**, median SQL time **3.5 ms**; question embeddings precomputed.

<!--
Say: For vectors, order by distance and take the top 50. Keep that distance expression ascending
so the HNSW index can serve it. With iterative scans off, the default ef_search of 40 can leave
LIMIT 50 short; here we use 100. The question embedding is already stored. FiQA scores 53.9 at a
median SQL time of 3.5 milliseconds. That timing excludes creating the question embedding.
-->

---

## Pitfall 2: adding scores from different scales<br><span class="file">07a_naive_sum.sql</span> <span class="file">07b_concat_dedupe.sql</span>

| Rainy-day question, each list's top 50 | lowest score | highest score |
| --- | ---: | ---: |
| `ts_rank_cd` | 1.70 | 5.40 |
| cosine similarity | 0.478 | 0.598 |

The lowest keyword score beats the highest cosine, so the sum puts every keyword match above
every result only vector search found.

<table>
<thead><tr><th>How the two lists are combined</th><th style="text-align:right">NDCG@10, 648 questions</th></tr></thead>
<tbody data-marpit-fragment>
<tr><td>Add the scores: <code>ts_rank_cd + cosine</code></td><td style="text-align:right">5.6</td></tr>
<tr><td>Keyword list, then vector list, duplicates removed</td><td style="text-align:right">2.9</td></tr>
</tbody>
<tbody data-marpit-fragment>
<tr><td><strong>Reciprocal Rank Fusion (RRF)</strong>: each list adds 1 / (60 + rank)</td><td style="text-align:right"><strong>33.8</strong></td></tr>
</tbody>
</table>

<p data-marpit-fragment>Same inputs, 6× the score.</p>

<!--
Say: Here the keyword branch is ts_rank_cd. Its scores run from 1.7 to 5.4; cosine scores are
around 0.5. Adding them lets the keyword scale dominate. [click] Across the test questions, the
sum scores 5.6; concatenating the lists scores 2.9. [click] Reciprocal Rank Fusion uses ranks
instead and scores 33.8. [click] Six times the naive sum, on the same inputs. Still below vector
alone. Fixing the fusion formula doesn't guarantee a better search.
-->

---

<!-- _class: rrf -->

## Combine ranks, not scores

<p class="formula">RRF(d) = Σ 1 / (60 + rank<sub>list</sub>(d))</p>
<p class="caption rrf-depth">Top 10 shown; top 50 from each list fused.</p>

<div class="rrf-demo">
<div class="rrf-lane bm25"><h4>BM25</h4><ol>
<li><span class="n">1</span><span class="pill top">66626</span></li>
<li><span class="n">2</span><span class="pill">371922</span></li>
<li><span class="n">3</span><span class="pill">569342</span></li>
<li><span class="n">4</span><span class="pill answer">32811<span>known answer</span></span></li>
<li><span class="n">5</span><span class="pill">2128</span></li>
<li><span class="n">6</span><span class="pill">32671</span></li>
<li><span class="n">7</span><span class="pill">404800</span></li>
<li><span class="n">8</span><span class="pill">266457</span></li>
<li><span class="n">9</span><span class="pill">272840</span></li>
<li><span class="n">10</span><span class="pill">65567</span></li>
</ol></div>
<div class="rrf-lane vector"><h4>Vector</h4><ol>
<li><span class="n">1</span><span class="pill top">293687</span></li>
<li><span class="n">2</span><span class="pill">348514</span></li>
<li><span class="n">3</span><span class="pill">469809</span></li>
<li><span class="n">4</span><span class="pill">361639</span></li>
<li><span class="n">5</span><span class="pill">458063</span></li>
<li><span class="n">6</span><span class="pill">427365</span></li>
<li><span class="n">7</span><span class="pill">209789</span></li>
<li><span class="n">8</span><span class="pill">283692</span></li>
<li><span class="n">9</span><span class="pill answer">32811<span>known answer</span></span></li>
<li><span class="n">10</span><span class="pill">62897</span></li>
</ol></div>
<div class="rrf-lane fused"><h4>Combined by RRF</h4><ol>
<li><span class="n">1</span><span class="pill slot"></span></li>
<li><span class="n">2</span><span class="pill slot"></span></li>
<li><span class="n">3</span><span class="pill slot"></span></li>
<li><span class="n">4</span><span class="pill slot"></span></li>
<li><span class="n">5</span><span class="pill slot"></span></li>
<li><span class="n">6</span><span class="pill slot"></span></li>
<li><span class="n">7</span><span class="pill slot"></span></li>
<li><span class="n">8</span><span class="pill slot"></span></li>
<li><span class="n">9</span><span class="pill slot"></span></li>
<li><span class="n">10</span><span class="pill slot"></span></li>
</ol></div>
<div class="rrf-step" data-marpit-fragment>
<span class="pill answer fly from-bm25-4" style="top:37px">32811<span>known answer</span></span>
<span class="pill answer fly from-vector-9" style="top:37px">32811<span>known answer</span></span>
<p class="caption later" style="top:350px">Known answer: BM25 #4, vector #9 → 1/64 + 1/69 = <strong>0.03012</strong>, combined <strong>#1</strong>.</p>
</div>
<div class="rrf-step" data-marpit-fragment>
<span class="pill top fly from-vector-1" style="top:277px">293687<span class="score">0.01639</span></span>
<span class="pill top fly from-bm25-1" style="top:307px">66626<span class="score">0.01639</span></span>
<span class="pill placed later" style="top:67px">371922<span>0.02912</span></span>
<span class="pill placed later" style="top:97px">469809<span>0.02778</span></span>
<span class="pill placed later" style="top:127px">424427<span>0.02633</span></span>
<span class="pill placed later" style="top:157px">32671<span>0.02568</span></span>
<span class="pill placed later" style="top:187px">72960<span>0.02452</span></span>
<span class="pill placed later" style="top:217px">488737<span>0.02379</span></span>
<span class="pill placed later" style="top:247px">152096<span>0.02114</span></span>
<p class="caption later" style="top:382px">Each list's own #1 is missing from the other list: 1/61 = 0.01639, combined #9 and #10.</p>
</div>
</div>

<!--
Say: For this example we've switched the keyword branch to BM25. You see the top ten, but we
fuse the top fifty from each list. [click] The known answer is fourth in BM25 and ninth in
vector. Both contribute, so it rises to first. [click] Each list's own number one is absent from
the other top fifty and falls to ninth or tenth. This is the useful case for RRF: agreement
between two complementary lists.
-->

---

<!-- _class: code-first dense -->

## RRF is a full outer join <span class="file">08a_hybrid_rrf.sql</span>

```sql
WITH keyword AS (
  SELECT id, row_number() OVER (ORDER BY ts_rank_cd(tsv, q) DESC, id) AS rank
    FROM docs, (SELECT replace(plainto_tsquery('english', :'question')::text,
                                ' & ', ' | ')::tsquery AS q) question
   WHERE tsv @@ q ORDER BY rank LIMIT 50
),
semantic AS (
  SELECT id, row_number() OVER (ORDER BY distance, id) AS rank
    FROM (SELECT id, embedding <=> :'question_embedding' AS distance
            FROM docs WHERE embedding IS NOT NULL
           ORDER BY distance LIMIT 50) nearest
)
SELECT coalesce(k.id, v.id) AS id,
       coalesce(1.0 / (60 + k.rank), 0) + coalesce(1.0 / (60 + v.rank), 0) AS rrf
  FROM keyword k FULL OUTER JOIN semantic v USING (id)
 ORDER BY rrf DESC
 LIMIT 10;
```

One statement, two indexes. Median **150 ms** with `ts_rank_cd`; **8.2 ms** with BM25
(`08b_hybrid_rrf_bm25.sql`). In these plans, the two lists run **in sequence**.

<!--
Say: The mechanics fit in one statement: two candidate lists, a full outer join on document id,
and two reciprocal-rank contributions. This core-PostgreSQL example uses ts_rank_cd; the BM25
version is the next SQL file. Its median is 8.2 milliseconds. These measured plans execute the
branches in sequence. A WITH clause doesn't make them concurrent; inspect the plan. If you need
independent concurrent retrieval, two connections are an option.
-->

---

<!-- _class: code-first dense -->

## Tuned blend: choose the mixing weight <span class="file">08c_hybrid_blend.sql</span>

**Blend:** scale keyword and vector scores to 0–1, then take a weighted sum.
**Tuned:** choose the weight with the best NDCG@10 on **development questions**;
keep it fixed for the **test questions**.

```sql
keyword_norm AS (        -- min-max to [0, 1]; semantic_norm uses the same guard
  SELECT id, CASE WHEN hi > lo THEN (score - lo) / (hi - lo) ELSE 1 END AS s
    FROM (SELECT *, min(score) OVER () AS lo, max(score) OVER () AS hi FROM keyword) k
)
SELECT id, w * coalesce(v.s, 0) + (1 - w) * coalesce(k.s, 0) AS blend
  FROM keyword_norm k FULL OUTER JOIN semantic_norm v USING (id);
```

**Example: NFCorpus + bge-small = 65% vector + 35% BM25.** Same weight for every test question.

| Weight `w` on vector, chosen on **separate tuning questions** | FiQA | SciFact | NFCorpus | SCIDOCS |
| --- | ---: | ---: | ---: | ---: |
| Cohere Embed v4 (frontier) | **1.0** | 0.70 | 0.70 | 0.5, not tuned |
| bge-small (local) | 0.65 | 0.55 | 0.65 | 0.5, not tuned |

<!--
Say: A blend is a weighted mix of keyword and vector scores, each scaled to zero through one.
Tuned means we try different weights on separate development questions and choose the best NDCG
at ten. Then we freeze that weight for the test questions. For NFCorpus with bge-small, that
means 65 percent vector and 35 percent BM25 for every sample. The CASE prevents division by
zero. These normalized scores preserve relative gaps; they are not confidence probabilities.
-->

---

## Knobs that change different things

| Knob | Controls | Watch |
| --- | --- | --- |
| **Results per list** (50) | How many posts each list contributes | An answer outside both lists can't be recovered: measure candidate recall |
| **k** (60) | How fast credit falls with rank | Measured k = 5 to 200: at most 4.3 NDCG@10 (FiQA), 1.4 elsewhere. No k made equal-weight RRF beat Embed v4 alone |
| **Weights** | Contribution of each list | Equal-weight RRF scored below Embed v4 alone on all four datasets; 95% intervals exclude zero on three |
| **`hnsw.ef_search`** (100) | How hard each HNSW scan searches | Keep ≥ results per list; check filtered recall and iterative-scan budgets |

Tune one knob at a time on **development questions**. Evaluate the final choice on **held-out test questions**.

<!--
Say: Four knobs, four different effects. Candidate count sets what fusion and reranking can see.
RRF's k changes the credit by rank. Weights change each list's contribution. ef_search changes
the HNSW search effort. The k sweep is a sensitivity check, not test-set tuning. Change one knob
at a time on development questions, then evaluate the final choice on held-out questions. With
filters, check both recall and the iterative-scan budgets.
-->

---

<!-- _class: demo-slide -->

## Live on NFCorpus: stored embeddings, local retrieval

# Small model + BM25 beat Embed v4 on this question

![Hybrid search lab UI on NFCorpus: BM25 65, bge-small 77, tuned blend 97, Embed v4 71 NDCG@10](assets/ui-search.png)

<p class="stage-url">localhost:8018, pick NFCorpus, then “Local hybrid beats the frontier model”</p>

<!--
Say: Let's see the result, one question at a time. This is NFCorpus and the Vitamin D question.
BM25 scores 65, the small model 77, and their blend 97; Embed v4 scores 71. All four retrieval
queries run locally. The last column uses embeddings previously made on Bedrock. Follow the
answer letters across the lists, then open the blend's SQL. This is a selected teaching example;
the full-dataset averages are coming next.
-->
---

## From text to vector

- **Use the right input type.** Embed v4: posts as `search_document`, questions as
  `search_query`. The model is trained for that distinction.
- **Keep one model per column.** Embed v4: 1536 dimensions. Local bge-small: 384.
  Store the model id; never mix models or versions, even at the same dimension.
- **Keep embeddings current.** Re-embed changed text; resume interrupted jobs from empty
  rows. FiQA took about an hour on the laptop CPU, or 35 minutes on Bedrock under quota.

<!--
Say: Three rules. Use the input types your model expects: documents and queries have
different roles. Keep one model and version per column. And refresh embeddings when the text
changes, using a resumable job. Multilingual retrieval needs a model that supports your
languages. Our bge-small model and all four benchmarks are English; we haven't measured
cross-language retrieval. On the lexical side, use the appropriate language configuration
for both documents and queries.
-->

---

<!-- _class: code-first -->

## Pitfall 3: a filter is not a pre-filter <span class="file">09_filtered_hybrid.sql</span>

```sql
SELECT id FROM docs
 WHERE tsv @@ plainto_tsquery('english', 'mortgage')      -- 4.2% of posts
 ORDER BY embedding <=> :'question_embedding' LIMIT 10;
```

| Setting | Plan | Rows returned |
| --- | --- | ---: |
| defaults (`iterative_scan = off`, `ef_search = 40`) | HNSW, then filter: **Rows Removed by Filter: 39** | **1 of 10** |
| `SET hnsw.iterative_scan = relaxed_order` | HNSW continues searching within scan budgets | 10 of 10 |
| a rare term: `heloc` (0.2%) | GIN, then exact sort | 10 of 10 |

Iterative scans have tuple and memory budgets; they may still return too few rows.
With `relaxed_order`, re-sort the candidates by distance.

<!--
Say: A WHERE clause isn't necessarily a physical pre-filter. In this plan, HNSW finds forty
candidates and the mortgage filter removes thirty-nine. LIMIT ten returns one. Iterative
scanning continues the search and returns ten here, but tuple and memory budgets can still stop
it early. Relaxed ordering also needs a final distance sort. For the rarer term heloc,
PostgreSQL chooses GIN followed by an exact sort. Always inspect the actual plan.
-->

---

<!-- _class: code-first -->

## Similar to the question AND contains a word <span class="file">11_hybrid_function.sql</span>

```sql
SELECT h.*, left(d.body, 60)
  FROM hybrid_search(:'question', :'question_embedding',
                     match_count => 5, required_terms => 'mortgage') h
  JOIN docs d ON d.id = h.doc_id;
```

```sql
CREATE FUNCTION hybrid_search(...) ... LANGUAGE sql STABLE
  SET hnsw.ef_search = 100
  SET hnsw.iterative_scan = relaxed_order
  SET plan_cache_mode = force_custom_plan   -- keeps "required_terms IS NULL OR ..." indexable
```

The required word goes into **both** lists, before their LIMIT.
This example uses **`ts_rank_cd` + RRF**; the measured local blend is in `08e_hybrid_blend_local.sql`.

<!--
Say: Now separate two requirements: similarity determines ranking; mortgage is mandatory. Put
that condition into both candidate queries before their LIMIT. This wrapper demonstrates
ts_rank_cd plus RRF, with its own scan settings. The measured BM25/local-blend recipe is in 08e.
force_custom_plan lets optional filters simplify for this call; otherwise the cached generic
plan can miss the HNSW path. The logical filter belongs inside each branch, even though HNSW may
apply it after candidate discovery.
-->

---

<!-- _class: code-first dense patterns -->

## Boost and expand: two patterns on top of `hybrid_search()`

<div class="pattern-grid">
<div>

**Boost** by recency, popularity, preference

```sql
SELECT h.doc_id,
       h.score
       * power(0.5, extract(epoch FROM
           now() - d.published_at) / 86400 / 30)
       * (1 + ln(1 + d.likes) / 10)
       * CASE WHEN d.category = ANY(:'preferred')
              THEN 1.2 ELSE 1 END AS boosted
  FROM hybrid_search(:'question',
         :'question_embedding', match_count => 50) h
  JOIN docs d ON d.id = h.doc_id
 ORDER BY boosted DESC
 LIMIT 10;
```

</div>
<div>

**Expand** along links, two hops

```sql
WITH RECURSIVE related (doc_id, score, depth) AS (
  SELECT doc_id, score, 0
    FROM hybrid_search(:'question',
           :'question_embedding', match_count => 10)
  UNION ALL
  SELECT l.dst, r.score / 2, r.depth + 1
    FROM related r
    JOIN links l ON l.src = r.doc_id
   WHERE r.depth < 2
)
SELECT doc_id, max(score) AS score
  FROM related
 GROUP BY doc_id
 ORDER BY score DESC
 LIMIT 10;
```

</div>
</div>

Boost a larger pool than you show (50, then keep 10), or a boost can't lift anything. **Not measured here:** these datasets have no dates, popularity, or links.

<!--
Say: Two optional application patterns. A support search might favor recent guidance; a research
search might follow citations. Rerank a larger pool than you display, and cap and tune boosts
because they can dominate relevance. The recursive query follows two hops and discounts each
hop. The depth bound limits work; it doesn't detect cycles. These examples were syntax-checked
with synthetic metadata, not evaluated for relevance on these datasets.
-->

---

<!-- _class: gold -->

## Hybrid vs vector, same embedding model: NDCG@10 change on 2,271 test questions

<table class="gold-table">
<thead><tr><th></th><th>FiQA</th><th>SciFact</th><th>NFCorpus</th><th>SCIDOCS</th></tr></thead>
<tbody data-marpit-fragment>
<tr class="section"><td colspan="5">Small local model: bge-small, 384 dims, on this laptop</td></tr>
<tr><td>Tuned blend + BM25</td><td class="up">+1.2 ↑<small>+0.4…+2.1</small></td><td class="up">+2.1 ↑<small>+0.03…+4.3</small></td><td class="up">+2.1 ↑<small>+1.3…+3.0</small></td><td>+0.2 *<small>−0.5…+0.8</small></td></tr>
<tr><td>Equal-weight RRF + BM25</td><td class="down">−3.1 ↓<small>−4.7…−1.5</small></td><td>+1.7<small>−0.9…+4.3</small></td><td class="up">+2.3 ↑<small>+1.0…+3.7</small></td><td>−0.3<small>−1.0…+0.5</small></td></tr>
</tbody>
<tbody data-marpit-fragment>
<tr class="section"><td colspan="5">Frontier model cut to its first 256 dims: Cohere Embed v4</td></tr>
<tr><td>Tuned blend + BM25</td><td>+0.5<small>−0.04…+1.1</small></td><td class="up">+3.5 ↑<small>+1.3…+5.7</small></td><td class="up">+2.8 ↑<small>+1.5…+4.1</small></td><td class="up">+1.9 ↑ *<small>+1.3…+2.5</small></td></tr>
</tbody>
<tbody data-marpit-fragment>
<tr class="section"><td colspan="5">Frontier model: Cohere Embed v4, 1536 dims</td></tr>
<tr><td>Tuned blend + BM25</td><td>0.0<small>chose vector only</small></td><td>+0.2<small>−1.2…+1.4</small></td><td class="up">+0.8 ↑<small>+0.1…+1.5</small></td><td class="down">−0.8 ↓ *<small>−1.4…−0.2</small></td></tr>
<tr><td>Equal-weight RRF + BM25</td><td class="down">−12.5 ↓<small>−14.5…−10.6</small></td><td class="down">−2.9 ↓<small>−5.1…−0.6</small></td><td>−1.1<small>−2.2…+0.1</small></td><td class="down">−1.2 ↓<small>−2.0…−0.5</small></td></tr>
<tr><td>Cohere Rerank 3.5, top 50</td><td class="down">−4.1 ↓<small>−6.0…−2.3</small></td><td>−0.4<small>−2.8…+1.9</small></td><td class="down">−1.9 ↓<small>−3.3…−0.4</small></td><td>−0.4<small>−1.1…+0.3</small></td></tr>
</tbody>
</table>

<p class="caption">↑ / ↓: paired-bootstrap 95% interval excludes zero; no arrow: inconclusive. Individual intervals, unadjusted. * SCIDOCS: untuned, weight 0.5</p>

<!--
Say: Each cell compares hybrid against vector using the same embedding model. Arrows mark
paired-bootstrap 95 percent intervals that exclude zero; no arrow means the difference is
inconclusive. [click] The local blend improves three datasets, with SciFact only just clearing
zero. [click] At 256 dimensions, BM25 also helps on three. [click] With full Embed v4, gains are
limited and equal-weight RRF often hurts. These are individual, unadjusted intervals, not a
guarantee for your workload.
-->

---

## When hybrid pays: a smaller model

| NDCG@10 | FiQA | SciFact | NFCorpus | SCIDOCS |
| --- | ---: | ---: | ---: | ---: |
| bge-small alone (local, open source) | 38.0 | 72.0 | 33.8 | 19.6 |
| **bge-small + BM25, tuned blend (all local)** | **39.2** | **74.2** | **35.9** | 19.8 |
| bge-small + `ts_rank_cd`, tuned blend (core PostgreSQL only) | 37.9 | 72.4 | 34.4 | 16.0 ↓ |
| Cohere Embed v4 alone (frontier API) | 53.9 | 77.5 | 40.1 | 20.6 |
| **Share of the gap closed by BM25** | 8% | **39%** | **33%** | inconclusive |

PostgreSQL, BM25, and a 384-dimension model: adding keyword search closes **a third or more
of the gap** to Embed v4 on SciFact and NFCorpus. The `ts_rank_cd` blend showed no significant gain.

<!--
Say: Here is the practical opportunity. A small local model plus BM25 closes about a third of
the gap to Embed v4 on SciFact and NFCorpus. On FiQA the gain is smaller. The ts_rank_cd blend
shows no significant improvement, so the lexical ranker matters. This measured retrieval recipe
uses open-source components. Embed v4 alone still leads on average on all four datasets; choose
the model and complexity that fit your requirements.
-->

---

## Rerank on FiQA: measure it too

| What Cohere Rerank 3.5 reorders | NDCG@10 | Recall@50 | Median |
| --- | ---: | ---: | ---: |
| none: vector alone | **53.9** | 78.5 | **3.5 ms** |
| vector top 50 | 49.7 | 78.5 | 417 ms |
| RRF (BM25) top 50 | 50.4 | 75.2 | 1,093 ms |
| vector ∪ BM25, up to 100 | 49.0 | 76.5 | 1,208 ms |

It lifts the 403b question from #26 to #2, but puts a known answer at #1 on 47.5% of questions,
against 53.9% for Embed v4 alone. No reranked method showed a significant gain on any dataset.

- A reranker reads the question and each result **together**. It cannot recover answers missing from its candidate pool.
- It runs **outside PostgreSQL**: a network call per question, and the results' text leaves the database.

<!--
Say: A reranker can rescue individual questions: it moves the 403b answer from twenty-sixth to
second. Across FiQA, this model pair makes the average worse and adds a network call. None of
the reranked methods shows a significant gain over vector across these datasets. It also can't
retrieve an answer absent from its candidate pool. The reported rerank times include Bedrock,
measured with eight concurrent workers. Measure your own model pair before adding it.
-->

---

## Storage on FiQA: fewer bits or fewer dimensions?

| Index on `embedding` | Bytes per vector | HNSW size | NDCG@10 | Median ms |
| --- | ---: | ---: | ---: | ---: |
| `vector(1536)` | 6,148 | 450 MB | 53.9 | 3.5 |
| `halfvec(1536)` expression index | 3,080 | 225 MB | 53.7 | 3.4 |
| `binary_quantize()`, then re-sort 200 by full vector | 200 | 28 MB | 54.1 | 3.3 |
| first 1024 dims, `subvector()` | 4,104 | **450 MB** | 53.4 | 2.9 |
| first 512 dims | 2,056 | 150 MB | 51.8 ↓ | 2.2 |
| first 256 dims | 1,032 | 75 MB | 49.3 ↓ | 1.7 |

**Try fewer bits before fewer dimensions.** No significant quality loss detected for halfvec
or binary + rescore here; full vectors remain in the table. At 256 dims, adding BM25 recovered
46–64% of the quality loss on three datasets. Index savings are not total database savings.

<!--
Say: If index size is the problem, try fewer bits before fewer dimensions. On FiQA, halfvec
halves the index and binary plus full-vector rescoring cuts it to 28 megabytes, with no
significant quality loss detected. The full vectors remain in the table. At 1024 dimensions,
page packing leaves the index at 450 megabytes. Smaller dimensions do save space but lose
relevance. At 256 dimensions, adding BM25 recovers about half the loss on three datasets.
-->

---

<!-- _class: limits -->

## What these numbers do and don't prove

- **A measured comparison, on a limited sample.** Four English datasets, two embedding
  models, one reranker. SCIDOCS has no tuning split. Multilingual search, phrase quality,
  boosts and link expansion were not evaluated.
- **Retrieval timing, not production latency.** SQL: one client, warm runs, precomputed
  embeddings, up to 57,638 documents. Rerank: eight concurrent Bedrock calls.
- **Incomplete judgments, possible training overlap.** Good unjudged answers count as
  misses; that can favor some methods. Check disagreements and test on your own data.

<!--
Say: Three limits. First, four English datasets and these model versions don't represent every
application. Second, SQL timings use precomputed embeddings on one warm laptop, while reranking
uses concurrent Bedrock calls. Neither is a production latency promise. Third, judgments are
incomplete and training overlap is possible. A useful unjudged answer still counts as a miss,
and that can favor some methods. Use this harness on your own questions and inspect
disagreements.
-->

---

<!-- _class: takeaway -->

## Three things to take home

- **Start with strong baselines.**<br>BM25 for words, vectors for meaning. Required matches belong in filters.
- **Measure whether fusion helps.**<br>Try RRF; tune a blend on development questions. Here, local model + BM25 gained 1.2–2.1 points on three datasets.
- **Choose on held-out questions.**<br>Compare quality and latency. Keep the simpler method when fusion adds no value.

<!--
Say: Three things to take home. Start with strong baselines: BM25 for words, vectors for
meaning, explicit filters for must-match requirements. Then measure fusion: RRF is a simple
baseline; with development judgments, tune a blend. In this lab, the small local model benefited
most consistently. Finally, choose on held-out questions, checking quality and latency together.
If fusion adds no value, keep the simpler method. PostgreSQL lets you express those choices next
to the data.
-->

---

<!-- _class: split-evidence -->

## Take it home

<div class="evidence-grid">
<div>

**The lab:** `hybrid-lab/`. Numbered SQL, VS Code cells, the UI, and the scoreboard.

**The skill:** adds hybrid search to *your* table and measures it.

```text
/plugin marketplace add shayons/talks
/plugin install postgres-hybrid-search@shayons-talks
```

Other agents: copy `hybrid-search-plugin/skills/postgres-hybrid-search/`.

</div>
<div class="evidence-image qr">

![QR code: github.com/shayons/talks/tree/main/conferences/2026-postgresconf-agentic-ai](assets/qr-talk.svg)

</div>
</div>

<p class="caption">github.com/shayons/talks, in conferences/2026-postgresconf-agentic-ai</p>

<!--
Say: The repo has the numbered SQL, Python cells, UI, and evaluation results. This benchmark
setup includes Bedrock comparators; it isn't a turnkey local-only installer. The BM25 and
bge-small retrieval recipe itself is fully open source. The agent skill adapts the pattern to
your table and compares methods. Synthetic questions can help you get started, but validate the
choice on independently judged questions before relying on the result.
-->

---

<!-- _class: thanks -->
<!-- _paginate: false -->

# Thank you.

Which of your queries need both exact words and meaning?

<div class="thanks-contact">
<img src="assets/qr-linkedin.svg" alt="QR code: linkedin.com/in/shayonsanyal">
<div>
<p class="name">Shayon Sanyal</p>
<p><a href="https://www.linkedin.com/in/shayonsanyal/">linkedin.com/in/shayonsanyal</a></p>
<p><a href="https://github.com/shayons/talks">github.com/shayons/talks</a></p>
</div>
</div>

<!--
Say: Thank you. Which of your queries need both exact words and meaning? Start with that
requirement, then measure. I'm happy to take questions. The QR code goes to my LinkedIn, and the
repo link has the SQL and results.
-->

---

<!-- _class: references -->

## References

- **PostgreSQL 18:** [Full-text search](https://www.postgresql.org/docs/18/textsearch.html), [Using EXPLAIN](https://www.postgresql.org/docs/18/using-explain.html), [auto_explain](https://www.postgresql.org/docs/18/auto-explain.html)
- **pgvector 0.8.6:** [HNSW, filtering, iterative index scans](https://github.com/pgvector/pgvector); **pg_textsearch 1.4.0:** [BM25 for PostgreSQL](https://github.com/timescale/pg_textsearch)
- **RRF:** Cormack, Clarke & Büttcher, [SIGIR 2009](https://doi.org/10.1145/1571941.1572114); **HNSW:** Malkov & Yashunin, [arXiv:1603.09320](https://arxiv.org/abs/1603.09320)
- **Score blending:** Bruch, Gai & Ingber, “An Analysis of Fusion Functions for Hybrid Retrieval”, [ACM TOIS 2023](https://doi.org/10.1145/3596512); **bge-small-en-v1.5:** [BAAI, MIT license](https://huggingface.co/BAAI/bge-small-en-v1.5), run with [fastembed](https://github.com/qdrant/fastembed)
- **FiQA-2018, SciFact, NFCorpus, SCIDOCS** via [BEIR](https://github.com/beir-cellar/beir) (Thakur et al., NeurIPS 2021); Dave Ebbelaar, [hybrid-retrieval tutorial](https://github.com/daveebbelaar/ai-cookbook/tree/main/knowledge/hybrid-retrieval) (the FiQA + NDCG approach this lab moves into PostgreSQL)
- **This talk:** `hybrid-lab/sql/`, `hybrid-lab/results/`, `hybrid-search-plugin/`

<p class="caption">Measured on PostgreSQL 18.6, pgvector 0.8.6, pg_textsearch 1.4.0, September 2026</p>

<!--
Say: The documentation and papers are here and in the repo. Start with the original RRF paper
for rank fusion, and Bruch, Gai and Ingber for score blending. The checked-in results and SQL
show exactly what this talk measured.
-->
