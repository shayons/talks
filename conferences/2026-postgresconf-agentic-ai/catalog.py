"""Public product details from canonical beans rows, independent of model prose."""

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
