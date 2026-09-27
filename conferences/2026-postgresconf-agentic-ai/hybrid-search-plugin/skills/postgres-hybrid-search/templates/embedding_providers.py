"""Embedding providers for backfill_embeddings.py and evaluate.py.

bedrock (default): Cohere Embed v4 on Amazon Bedrock, asymmetric (document vs query).
openai:            text-embedding-3-*, symmetric. Run with: uv run --with openai ...
fastembed:         local BGE models, no network after download. uv run --with fastembed ...
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

Kind = Literal["document", "query"]
THROTTLE_WAITS = (15, 30, 60, 60, 120, 120)


@dataclass
class Provider:
    """A configured embedding model. Documents and queries may be embedded differently."""

    name: str
    model: str
    dims: int
    batch_size: int

    def embed(self, texts: list[str], kind: Kind) -> list[list[float]]:
        """Embed non-blank texts, in order, as documents or as queries."""
        if any(not text.strip() for text in texts):
            raise ValueError("Blank text cannot be embedded; filter it out first.")
        if self.name == "bedrock":
            return _bedrock_embed(self, texts, kind)
        if self.name == "openai":
            return _openai_embed(self, texts)
        return _fastembed_embed(self, texts, kind)


def make_provider(name: str, dims: int, model: str | None = None) -> Provider:
    """Build a provider by name ('bedrock', 'openai', or 'fastembed').

    Raises:
        ValueError: For an unknown provider name.
    """
    defaults = {
        "bedrock": ("us.cohere.embed-v4:0", 96),
        "openai": ("text-embedding-3-small", 256),
        "fastembed": ("BAAI/bge-small-en-v1.5", 64),
    }
    if name not in defaults:
        raise ValueError(f"Unknown provider {name!r}; choose one of {', '.join(defaults)}")
    default_model, batch_size = defaults[name]
    return Provider(name=name, model=model or default_model, dims=dims, batch_size=batch_size)


@lru_cache(maxsize=1)
def _bedrock_client():
    import boto3
    from botocore.config import Config

    config = Config(retries={"max_attempts": 10, "mode": "adaptive"}, read_timeout=120)
    return boto3.client(
        "bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"), config=config
    )


def _bedrock_embed(provider: Provider, texts: list[str], kind: Kind) -> list[list[float]]:
    from botocore.exceptions import ClientError

    body = json.dumps({
        "texts": texts,
        "input_type": "search_document" if kind == "document" else "search_query",
        "embedding_types": ["float"],
        "output_dimension": provider.dims,
    })
    client = _bedrock_client()
    for wait in (*THROTTLE_WAITS, None):
        try:
            response = client.invoke_model(modelId=provider.model, body=body)
            return json.loads(response["body"].read())["embeddings"]["float"]
        except ClientError as exc:
            throttled = exc.response.get("Error", {}).get("Code") == "ThrottlingException"
            if not throttled or wait is None:
                raise
            time.sleep(wait)
    raise AssertionError("unreachable")


def _openai_embed(provider: Provider, texts: list[str]) -> list[list[float]]:
    from openai import OpenAI

    response = OpenAI().embeddings.create(
        model=provider.model, input=texts, dimensions=provider.dims
    )
    return [item.embedding for item in response.data]


@lru_cache(maxsize=2)
def _fastembed_model(name: str):
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=name)


def _fastembed_embed(provider: Provider, texts: list[str], kind: Kind) -> list[list[float]]:
    model = _fastembed_model(provider.model)
    vectors = model.query_embed(texts) if kind == "query" else model.passage_embed(texts)
    return [list(map(float, vector)) for vector in vectors]
