"""Seed the coffee roastery DB with customers, beans (with real embeddings),
historical orders, and a tool registry.

Run:
    python seed.py

This will fully reset the data in the tables (but not the schema).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

import psycopg

from db import conn, embed_batch


# -----------------------------------------------------------------------
# Customers
# -----------------------------------------------------------------------
CUSTOMERS = [
    {
        "id": "u_marco",
        "name": "Marco",
        "preferences_summary": "Prefers medium roasts. Enjoys bright, fruity, floral Ethiopian and East-African coffees. Drinks mostly pour-over and the occasional cold brew.",
    },
    {
        "id": "u_ana",
        "name": "Ana",
        "preferences_summary": "Dark-roast espresso drinker. Likes chocolate, caramel, nutty, low-acid profiles. Buys in larger quantities.",
    },
    {
        "id": "u_yuki",
        "name": "Yuki",
        "preferences_summary": "Tokyo-based specialty buyer. Asks about Japanese single-origins, pour-over and siphon brewing, and small-lot washed coffees. Willing to stretch budget for provenance.",
    },
]

# -----------------------------------------------------------------------
# Beans — a realistic mini-catalog across the roast spectrum
# -----------------------------------------------------------------------
BEANS = [
    {
        "id": "b_ethiopia_yirg",
        "name": "Ethiopia Yirgacheffe",
        "origin": "Yirgacheffe, Ethiopia",
        "roast_level": "medium-light",
        "process": "washed",
        "flavor_notes": ["jasmine", "lemon", "bergamot", "honey"],
        "description": "Bright and tea-like with delicate jasmine aromatics, a crisp lemon-bergamot acidity, and a clean honey finish. A textbook washed Yirgacheffe — a reliable go-to for pour-over.",
        "price_cents": 1900,
        "in_stock": 42,
    },
    {
        "id": "b_ethiopia_guji",
        "name": "Ethiopia Guji Natural",
        "origin": "Guji, Ethiopia",
        "roast_level": "light",
        "process": "natural",
        "flavor_notes": ["strawberry", "blueberry", "cocoa nib", "red wine"],
        "description": "A natural-process fruit bomb — ripe strawberry, blueberry jam, and a red-wine body. Cocoa-nib finish keeps it grounded. Shines in pour-over and cold brew.",
        "price_cents": 2100,
        "in_stock": 18,
    },
    {
        "id": "b_kenya_aa",
        "name": "Kenya AA Nyeri",
        "origin": "Nyeri, Kenya",
        "roast_level": "medium-light",
        "process": "washed",
        "flavor_notes": ["blackcurrant", "grapefruit", "brown sugar", "tomato"],
        "description": "Juicy Kenyan classic with blackcurrant and grapefruit acidity, brown-sugar sweetness, and a surprising savory tomato edge. High-grown SL28/SL34 varietals.",
        "price_cents": 2300,
        "in_stock": 24,
    },
    {
        "id": "b_rwanda_musasa",
        "name": "Rwanda Musasa",
        "origin": "Musasa, Rwanda",
        "roast_level": "medium",
        "process": "washed",
        "flavor_notes": ["apple", "caramel", "almond", "brown sugar"],
        "description": "Balanced, approachable East African with red apple, caramel, and toasted almond. A forgiving bean that works as pour-over, drip, or a lighter espresso.",
        "price_cents": 1750,
        "in_stock": 30,
    },
    {
        "id": "b_colombia_huila",
        "name": "Colombia Huila",
        "origin": "Huila, Colombia",
        "roast_level": "medium",
        "process": "washed",
        "flavor_notes": ["chocolate", "red apple", "toffee", "vanilla"],
        "description": "Classic Colombian with milk-chocolate body, red apple sweetness, and toffee. Incredibly versatile — equally good as drip, pour-over, or espresso.",
        "price_cents": 1600,
        "in_stock": 120,
    },
    {
        "id": "b_brazil_santos",
        "name": "Brazil Santos",
        "origin": "Mogiana, Brazil",
        "roast_level": "medium-dark",
        "process": "natural",
        "flavor_notes": ["chocolate", "hazelnut", "peanut", "caramel"],
        "description": "Low-acid, heavy-bodied natural Brazil with dark chocolate, hazelnut, and caramel. The workhorse for espresso blends and French press. Forgiving in a moka pot.",
        "price_cents": 1400,
        "in_stock": 200,
    },
    {
        "id": "b_guatemala_antigua",
        "name": "Guatemala Antigua",
        "origin": "Antigua, Guatemala",
        "roast_level": "medium",
        "process": "washed",
        "flavor_notes": ["dark chocolate", "orange peel", "spice", "almond"],
        "description": "Volcanic-soil Guatemala with dark chocolate, orange-peel brightness, and a warm spice finish. Holds up beautifully in milk-based drinks.",
        "price_cents": 1850,
        "in_stock": 65,
    },
    {
        "id": "b_costarica_tarrazu",
        "name": "Costa Rica Tarrazú",
        "origin": "Tarrazú, Costa Rica",
        "roast_level": "medium-light",
        "process": "honey",
        "flavor_notes": ["honey", "orange", "brown sugar", "milk chocolate"],
        "description": "Honey-process Tarrazú with orange, honey sweetness, and milk chocolate. Clean, polished, and friendly — a crowd-pleaser for brunch service.",
        "price_cents": 1950,
        "in_stock": 38,
    },
    {
        "id": "b_panama_geisha",
        "name": "Panama Geisha Esmeralda",
        "origin": "Boquete, Panama",
        "roast_level": "light",
        "process": "washed",
        "flavor_notes": ["jasmine", "bergamot", "peach", "mandarin"],
        "description": "The iconic Esmeralda Geisha — floral jasmine, bergamot, tropical mandarin, and a silky peach finish. For the connoisseur: pour-over only, please.",
        "price_cents": 5800,
        "in_stock": 6,
    },
    {
        "id": "b_sumatra_mandheling",
        "name": "Sumatra Mandheling",
        "origin": "North Sumatra, Indonesia",
        "roast_level": "dark",
        "process": "washed",
        "flavor_notes": ["cedar", "dark chocolate", "tobacco", "earthy"],
        "description": "Wet-hulled Sumatran with cedar, dark chocolate, tobacco, and that signature earthy depth. Heavy body, very low acidity. Made for French press and cold brew.",
        "price_cents": 1700,
        "in_stock": 85,
    },
    {
        "id": "b_sulawesi_toraja",
        "name": "Sulawesi Toraja",
        "origin": "Tana Toraja, Indonesia",
        "roast_level": "medium-dark",
        "process": "washed",
        "flavor_notes": ["dark chocolate", "clove", "molasses", "cedar"],
        "description": "Spicy and deep — dark chocolate, clove, molasses, and cedar. Smooth, low-acid, syrupy. Pairs beautifully with pastries.",
        "price_cents": 1850,
        "in_stock": 44,
    },
    {
        "id": "b_honduras_marcala",
        "name": "Honduras Marcala",
        "origin": "La Paz, Honduras",
        "roast_level": "medium",
        "process": "washed",
        "flavor_notes": ["chocolate", "apple", "caramel", "almond"],
        "description": "Clean Honduras with chocolate, green apple brightness, caramel, and almond. A great everyday drip coffee that won't alienate anyone.",
        "price_cents": 1500,
        "in_stock": 150,
    },
    {
        "id": "b_mexico_chiapas",
        "name": "Mexico Chiapas",
        "origin": "Chiapas, Mexico",
        "roast_level": "medium-dark",
        "process": "washed",
        "flavor_notes": ["chocolate", "almond", "brown sugar", "mild"],
        "description": "Mild and mellow Chiapas — milk chocolate, almond, brown sugar. A low-acid, nutty cup that's easy to drink and great in blends.",
        "price_cents": 1350,
        "in_stock": 180,
    },
    {
        "id": "b_peru_cajamarca",
        "name": "Peru Cajamarca",
        "origin": "Cajamarca, Peru",
        "roast_level": "medium",
        "process": "washed",
        "flavor_notes": ["cocoa", "almond", "apple", "honey"],
        "description": "Smooth Peruvian with cocoa, almond, and apple brightness. Organic, small-holder sourced. Balanced body, gentle acidity.",
        "price_cents": 1600,
        "in_stock": 90,
    },
    {
        "id": "b_yemen_mocha",
        "name": "Yemen Mocha Matari",
        "origin": "Bani Matar, Yemen",
        "roast_level": "medium",
        "process": "natural",
        "flavor_notes": ["dried fruit", "cardamom", "dark chocolate", "wine"],
        "description": "Legendary natural Yemen — dried fruit, cardamom, dark chocolate, and a wine-like finish. Complex, funky, unforgettable. Small lot.",
        "price_cents": 3400,
        "in_stock": 9,
    },
    {
        "id": "b_espresso_blend",
        "name": "House Espresso Blend",
        "origin": "Brazil + Colombia + Sumatra",
        "roast_level": "dark",
        "process": "washed",
        "flavor_notes": ["dark chocolate", "caramel", "toasted nut", "smoke"],
        "description": "Our signature dark espresso blend — Brazil for body, Colombia for sweetness, Sumatra for depth. Thick crema, caramel sweetness, dark chocolate finish.",
        "price_cents": 1650,
        "in_stock": 240,
    },
]


# -----------------------------------------------------------------------
# Historical orders — seed episodic memory consistent with preferences
# -----------------------------------------------------------------------
def _days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


ORDERS = [
    # Marco — fruity East African, pour-over
    ("u_marco",  "b_ethiopia_yirg",   1, _days_ago(42)),
    ("u_marco",  "b_ethiopia_guji",   1, _days_ago(28)),
    ("u_marco",  "b_kenya_aa",        1, _days_ago(14)),
    ("u_marco",  "b_rwanda_musasa",   1, _days_ago(6)),
    # Ana — dark espresso drinker, buys bigger
    ("u_ana",    "b_espresso_blend",  3, _days_ago(35)),
    ("u_ana",    "b_sumatra_mandheling", 2, _days_ago(21)),
    ("u_ana",    "b_brazil_santos",   2, _days_ago(8)),
    ("u_ana",    "b_espresso_blend",  3, _days_ago(2)),
    # Yuki — Tokyo specialty buyer. No Japanese origin exists in our catalog
    # (that's the point of the refusal demo); her history is washed,
    # high-clarity single-origins from adjacent origins.
    ("u_yuki",   "b_panama_geisha",   1, _days_ago(55)),
    ("u_yuki",   "b_ethiopia_yirg",   1, _days_ago(28)),
    ("u_yuki",   "b_costarica_tarrazu", 1, _days_ago(11)),
    ("u_yuki",   "b_kenya_aa",        1, _days_ago(4)),
]


# -----------------------------------------------------------------------
# Tool registry
# -----------------------------------------------------------------------
TOOLS = [
    {
        "name": "search_beans_semantic",
        "description": "Semantic similarity search over the bean catalog. Accepts a free-text query plus optional roast_level filter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "roast_level_in": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
        "requires_approval": False,
        "owner_agent": "flavor_profiler",
    },
    {
        "name": "check_inventory",
        "description": "Return live stock levels for a set of beans by id.",
        "input_schema": {
            "type": "object",
            "properties": {"bean_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["bean_ids"],
        },
        "requires_approval": False,
        "owner_agent": "roast_master",
    },
    {
        "name": "get_customer_history",
        "description": "Fetch a customer's recent orders with bean details. Used by the coordinator to personalize recommendations.",
        "input_schema": {
            "type": "object",
            "properties": {"customer_id": {"type": "string"}, "limit": {"type": "integer", "default": 5}},
            "required": ["customer_id"],
        },
        "requires_approval": False,
        "owner_agent": "coordinator",
    },
    {
        "name": "place_order",
        "description": "Place a real order on behalf of a customer. Deducts inventory and writes to the orders table. Requires approval before execution.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "bean_id":     {"type": "string"},
                "qty":         {"type": "integer"},
            },
            "required": ["customer_id", "bean_id", "qty"],
        },
        "requires_approval": True,
        "owner_agent": "coordinator",
    },
]


# -----------------------------------------------------------------------
# helpers
# -----------------------------------------------------------------------
def _bean_corpus(b: dict) -> str:
    """The text we embed for each bean — this is what similarity search hits."""
    notes = ", ".join(b["flavor_notes"])
    return (
        f"{b['name']} from {b['origin']}. "
        f"Roast level: {b['roast_level']}. Process: {b['process']}. "
        f"Flavor notes: {notes}. "
        f"{b['description']}"
    )


def main() -> int:
    print("→ connecting to database…")
    with conn() as c:
        c.execute("TRUNCATE approvals, tool_audit, tools, agent_messages, agent_sessions, orders, beans, customers RESTART IDENTITY")

        print("→ inserting customers…")
        with c.cursor() as cur:
            cur.executemany(
                "INSERT INTO customers (id, name, preferences_summary) VALUES (%(id)s, %(name)s, %(preferences_summary)s)",
                CUSTOMERS,
            )

        print(f"→ embedding {len(BEANS)} beans (first run downloads ~130MB)…")
        corpora = [_bean_corpus(b) for b in BEANS]
        vectors = embed_batch(corpora)

        print("→ inserting beans…")
        with c.cursor() as cur:
            for b, vec in zip(BEANS, vectors):
                cur.execute(
                    """INSERT INTO beans
                       (id, name, origin, roast_level, process, flavor_notes,
                        description, price_cents, in_stock, embedding)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        b["id"], b["name"], b["origin"], b["roast_level"], b["process"],
                        b["flavor_notes"], b["description"],
                        b["price_cents"], b["in_stock"], vec,
                    ),
                )

        print(f"→ inserting {len(ORDERS)} historical orders…")
        with c.cursor() as cur:
            cur.executemany(
                "INSERT INTO orders (customer_id, bean_id, qty, placed_at) VALUES (%s,%s,%s,%s)",
                ORDERS,
            )

        print(f"→ embedding + inserting {len(TOOLS)} tools…")
        tool_vecs = embed_batch([t["description"] for t in TOOLS])
        with c.cursor() as cur:
            for t, v in zip(TOOLS, tool_vecs):
                cur.execute(
                    """INSERT INTO tools
                       (name, description, description_emb, input_schema,
                        requires_approval, enabled, owner_agent)
                       VALUES (%s,%s,%s,%s,%s,TRUE,%s)""",
                    (
                        t["name"], t["description"], v,
                        json.dumps(t["input_schema"]),
                        t["requires_approval"], t["owner_agent"],
                    ),
                )

        c.commit()

    print("✓ seed complete.")
    print(f"  {len(CUSTOMERS)} customers · {len(BEANS)} beans · {len(ORDERS)} orders · {len(TOOLS)} tools")

    # Close the pool cleanly so the script exits silently instead of
    # printing "couldn't stop thread" warnings on teardown.
    from db import get_pool
    try:
        get_pool().close()
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
