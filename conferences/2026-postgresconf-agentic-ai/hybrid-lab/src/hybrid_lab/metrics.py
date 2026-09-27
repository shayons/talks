"""Retrieval metrics for one question. sql/10_scoreboard.sql computes the same in SQL."""

from __future__ import annotations

import math


def ndcg_at_k(ranked_ids: list[str], relevance: dict[str, int], k: int = 10) -> float:
    """Normalized discounted cumulative gain of a ranking.

    Args:
        ranked_ids: Document ids, best first.
        relevance: Judged relevance by document id; unjudged documents count as 0.
        k: Cutoff rank.

    Returns:
        A value in [0, 1]; 0 when the question has no judged-relevant documents.
    """
    dcg = sum(
        relevance.get(doc_id, 0) / math.log2(rank + 1)
        for rank, doc_id in enumerate(ranked_ids[:k], start=1)
    )
    ideal = sorted(relevance.values(), reverse=True)[:k]
    idcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(ideal, start=1))
    return dcg / idcg if idcg else 0.0


def recall_at_k(ranked_ids: list[str], relevance: dict[str, int], k: int = 50) -> float:
    """Share of judged-relevant documents that appear in the top k."""
    if not relevance:
        return 0.0
    found = sum(1 for doc_id in ranked_ids[:k] if relevance.get(doc_id, 0) > 0)
    return found / len(relevance)
