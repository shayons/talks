# %% [markdown]
# # 9. The two misses on slide 2
#
# Two small mock sites, not from the BEIR datasets: an 8-article help center and a
# 20-product battery aisle that, like many stores, stocks more AAA packs than AA. Each is
# ranked three ways, the same three the talk measures: BM25 (pg_textsearch, on a temporary
# table), bge-small (local), and Cohere Embed v4 (Bedrock). The slide shows BM25's
# help-center results and Embed v4's battery results.
#
# Needs `uv sync --extra local` and Bedrock access. Writes results/opener_examples.md.

# %%
import numpy as np
from fastembed import TextEmbedding

from hybrid_lab import bedrock
from hybrid_lab.db import LAB_ROOT, connect

HELP_CENTER = [
    "How to end your membership. Go to Account, then Membership, and choose End membership. "
    "You keep access until the last day of the billing period.",
    "Cancel or change an order. You can cancel or change an order until it ships. "
    "Open Your orders and choose the item.",
    "Subscription plans and pricing. Compare plans and prices. You can switch plans at any "
    "time from Account.",
    "Pause your membership. Take a break for up to three months without losing your "
    "profile or history.",
    "Update your payment method. Change the card we charge each billing period in Account, "
    "then Payment.",
    "Request a refund. Refunds go back to your original payment method within 5 to 10 "
    "business days.",
    "Change your email or password. Update your sign-in details in Account, then Security.",
    "Gift subscriptions. Buy a subscription for someone else and choose the start date.",
]
BATTERIES = [
    "AA alkaline batteries, 24 pack",
    "AA rechargeable batteries, 8 pack",
    "AA lithium batteries, 8 pack",
    "Long-lasting AA batteries for toys and remotes, 48 pack",
    "AAA alkaline batteries, 24 pack",
    "AAA alkaline batteries, 48 pack",
    "AAA rechargeable batteries, 8 pack",
    "AAA lithium batteries, 8 pack",
    "AAA batteries for TV remotes, 4 pack",
    "AAA heavy duty batteries, 16 pack",
    "AAA batteries, 12 pack",
    "Premium AAA batteries, 36 pack",
    "C alkaline batteries, 8 pack",
    "D alkaline batteries, 8 pack",
    "9V alkaline batteries, 4 pack",
    "CR2032 lithium coin cell batteries, 6 pack",
    "Battery charger for AA and AAA rechargeable batteries",
    "Battery organizer case with tester",
    "Lantern battery, 6V",
    "Hearing aid batteries, size 312, 24 pack",
]
SCENARIOS = [
    ("Help center", "How do I cancel my subscription?", HELP_CENTER),
    ("Battery aisle", "AA batteries", BATTERIES),
]
TOP = 5


def bm25_ranking(conn, question: str, docs: list[str]) -> list[tuple[int, float]]:
    """Rank docs with pg_textsearch BM25 on a temporary table; only matches are returned."""
    conn.execute("CREATE TEMP TABLE opener (id int, body text) ON COMMIT DROP")
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO opener VALUES (%s, %s)", list(enumerate(docs)))
    conn.execute(
        "CREATE INDEX opener_bm25 ON opener USING bm25 (body) WITH (text_config = 'english')"
    )
    rows = conn.execute(
        "SELECT id, -(body <@> to_bm25query(%s, 'opener_bm25')) FROM opener"
        " ORDER BY body <@> to_bm25query(%s, 'opener_bm25') LIMIT %s",
        (question, question, TOP),
    ).fetchall()
    conn.rollback()
    return [(doc, float(score)) for doc, score in rows if score > 0]


def cosine_ranking(question_vec, doc_vecs) -> list[tuple[int, float]]:
    """Rank docs by cosine similarity to the question, highest first."""
    q = np.asarray(question_vec, dtype=float)
    d = np.asarray(doc_vecs, dtype=float)
    scores = d @ q / (np.linalg.norm(d, axis=1) * np.linalg.norm(q))
    return [(int(i), float(scores[i])) for i in np.argsort(-scores)[:TOP]]


def section(name: str, question: str, docs: list[str], rankings: dict) -> str:
    """One markdown section: each method's top results with scores."""
    lines = [f"## {name}: “{question}”", ""]
    for method, ranking in rankings.items():
        lines += [f"**{method}**", ""]
        lines += [f"{rank}. {score:.3f} {docs[doc]}" for rank, (doc, score) in
                  enumerate(ranking, start=1)] or ["(no results)"]
        lines.append("")
    return "\n".join(lines)


# %%
local = TextEmbedding("BAAI/bge-small-en-v1.5")
sections = []
with connect("fiqa") as conn:
    for name, question, docs in SCENARIOS:
        local_docs = list(local.passage_embed(docs))
        local_question = next(iter(local.query_embed([question])))
        rankings = {
            "BM25 (pg_textsearch)": bm25_ranking(conn, question, docs),
            "bge-small": cosine_ranking(local_question, local_docs),
            "Embed v4": cosine_ranking(
                bedrock.embed_query(question), bedrock.embed(docs, "search_document")
            ),
        }
        sections.append(section(name, question, docs, rankings))

report = "# Slide 2: the two misses\n\nTop 5 per method; scores are BM25 or cosine.\n\n"
report += "\n".join(sections)
(LAB_ROOT / "results" / "opener_examples.md").write_text(report)
print(report)
