"""The small open-source embedding model (bge-small-en-v1.5), loaded only when needed."""

from __future__ import annotations

from functools import lru_cache

MODEL = "BAAI/bge-small-en-v1.5"


@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding

    return TextEmbedding(MODEL)


def available() -> bool:
    """True when fastembed is installed (uv sync --extra local)."""
    try:
        import fastembed  # noqa: F401
    except ImportError:
        return False
    return True


def embed_query(text: str) -> list[float]:
    """Embed one question with the model's query instruction (384 dimensions)."""
    return next(iter(_model().query_embed([text]))).tolist()
