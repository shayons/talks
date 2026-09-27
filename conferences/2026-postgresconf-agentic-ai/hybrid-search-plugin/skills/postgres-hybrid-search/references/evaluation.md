# Evaluating search on the user's data

Without known answers, "hybrid looks better" is an opinion. The evaluation turns it into two
numbers per arm.

## Metrics

- **NDCG@10.** For each question, `DCG = Σ relevance / log2(rank + 1)` over the top 10,
  divided by the best achievable DCG for that question. 1 means every known answer is at the
  top; 0 means none is in the top 10. Average over all questions; a question with no results
  scores 0.
- **Recall@50.** Share of a question's known answers anywhere in the top 50. It bounds what a
  reranker over 50 candidates can achieve.
- **Latency.** Client wall time per question, p50 and p95, after a warm-up pass. Report it
  as measured on the user's hardware, not as a service-level number.

`templates/scoreboard.sql` computes both metrics in SQL from `hybrid_eval.runs` and
`hybrid_eval.qrels`.

## Labeled questions (best)

A CSV with `question,relevant_id[,relevance]`, one row per relevant document. Sources: search
logs with clicks or purchases, support tickets linked to the article that resolved them,
or a domain expert labeling 50 to 100 questions. Even 50 labeled questions separates arms
that differ by a few NDCG points only when the difference is consistent; report the
per-question wins and losses, not just the mean.

## Synthetic questions (when there are no labels)

`templates/evaluate.py --synthetic N` samples N rows and asks an LLM to write one question
that the row answers, as a real user would ask it. That row becomes the single known answer.

Tell the user about the biases before showing numbers:

- **Lexical overlap.** Questions written while reading the document reuse its words, which
  favors keyword search. The prompt asks for paraphrase and forbids copying distinctive
  phrases; the bias remains.
- **One answer per question.** Other rows that also answer the question count as misses,
  which lowers every arm's score equally but hides near-duplicates.
- **Distribution.** Sampled rows are not the questions users actually ask. Replace them with
  real queries as soon as any exist.

Use synthetic results to compare arms against each other, not as an absolute quality score.

## Small tables and small question sets

- When the table has fewer rows than the candidate depth (50), every arm sees almost the whole
  table: Recall@50 is close to 100 by construction and says nothing.
- With fewer than about 100 questions, differences of a few NDCG points are noise. Report the
  per-question wins and losses, and say when the arms are indistinguishable.

## Reading the scoreboard

- If RRF does not beat the best single arm, check Recall@50 for the weak arm. A keyword arm
  that rarely finds answers mostly adds noise; try BM25, weights (for example vector 1.0,
  keyword 0.5), or drop it.
- Look at the questions where arms disagree most. They explain the averages and make the
  best demonstrations.
- Re-run the evaluation after every change to SQL, weights, embeddings, or indexes.
