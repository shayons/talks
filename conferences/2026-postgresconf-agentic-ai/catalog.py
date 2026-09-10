"""Public product details from canonical beans rows, independent of model prose."""

from db import conn, embed, EMBED_MODEL

PRODUCT_FIELDS = (
    "id", "name", "origin", "roast_level", "process", "flavor_notes",
    "price_cents", "in_stock",
)


def product_details(bean: dict) -> dict:
    """Project a verified catalog row; never expose embeddings or private context."""
    roast = bean["roast_level"]
    artwork = {
        "light": "light", "medium-light": "light", "medium": "medium",
        "medium-dark": "dark", "dark": "dark",
    }.get(roast, "medium")
    return {
        **{field: bean[field] for field in PRODUCT_FIELDS},
        "currency": "USD",
        "image_url": f"/static/products/coffee-{artwork}.webp",
    }


def read_catalog(bean_id: str | None = None) -> dict | None:
    """Read public catalog evidence; customer data never enters this projection."""
    with conn() as c, c.cursor() as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        cur.execute("SET LOCAL statement_timeout = '5s'")
        fields = ', '.join(PRODUCT_FIELDS)
        if bean_id is not None:
            cur.execute(f"SELECT {fields}, description, search_document::text, embedding FROM beans WHERE id = %s", (bean_id,))
            row = cur.fetchone()
            if row is None:
                return None
            bean = dict(zip(PRODUCT_FIELDS, row[:8]))
            return {**product_details(bean), 'description': row[8],
                    'search_document': row[9],
                    'weighted_fields': {'A': [bean['name'], bean['origin'], ' '.join(bean['flavor_notes'])], 'B': [row[8]]},
                    'embedding': row[10].tolist() if row[10] is not None else None,
                    'embedding_model': EMBED_MODEL}
        cur.execute('SELECT count(*) FROM beans')
        total = cur.fetchone()[0]
        cur.execute(f"SELECT {fields}, description, vector_dims(embedding) FROM beans ORDER BY name, id LIMIT 200")
        products = [{**product_details(dict(zip(PRODUCT_FIELDS, row[:8]))),
                     'description': row[8], 'embedding_dimensions': row[9]} for row in cur.fetchall()]
    return {'products': products, 'total': total, 'truncated': total > len(products), 'embedding_model': EMBED_MODEL}


def embedding_snapshot(query: str) -> dict:
    """Bounded public vectors for a teaching graph; no index topology is exposed."""
    query_embedding = [float(value) for value in embed(query)]
    with conn() as c, c.cursor() as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        cur.execute("SET LOCAL statement_timeout = '5s'")
        cur.execute("SELECT count(*) FROM beans WHERE embedding IS NOT NULL")
        total = cur.fetchone()[0]
        cur.execute("""SELECT id, name, embedding FROM beans
                       WHERE embedding IS NOT NULL ORDER BY name, id LIMIT 48""")
        products = [{'id': row[0], 'name': row[1], 'embedding': row[2].tolist()}
                    for row in cur.fetchall()]
    return {'query': query, 'query_embedding': query_embedding, 'products': products,
            'total': total, 'truncated': total > len(products), 'embedding_model': EMBED_MODEL}
