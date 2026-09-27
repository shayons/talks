"""Cohere Embed v4 and Cohere Rerank on Amazon Bedrock.

Documents and questions are embedded differently on purpose: Embed v4 is trained with
input_type='search_document' for the corpus and 'search_query' for questions. Mixing them
up is a silent relevance bug, so callers must say which one they want.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Literal

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    TokenRetrievalError,
)

EMBED_MODEL_ID = os.getenv("EMBED_MODEL_ID", "us.cohere.embed-v4:0")
RERANK_MODEL_ID = os.getenv("RERANK_MODEL_ID", "cohere.rerank-v3-5:0")
REGION = os.getenv("AWS_REGION", "us-east-1")
DIMENSIONS = 1536
MAX_TEXTS_PER_CALL = 96

InputType = Literal["search_document", "search_query"]
_CREDENTIAL_CODES = {
    "ExpiredTokenException",
    "UnrecognizedClientException",
    "InvalidSignatureException",
}


class BedrockError(RuntimeError):
    """A Bedrock call failed; the message says what to do next."""


class BedrockThrottled(BedrockError):
    """Bedrock rejected the call for exceeding a requests or tokens per minute quota."""


@lru_cache(maxsize=1)
def _client():
    retries = {"max_attempts": 10, "mode": "adaptive"}
    config = Config(region_name=REGION, retries=retries, read_timeout=120)
    return boto3.Session(profile_name=os.getenv("AWS_PROFILE") or None).client(
        "bedrock-runtime", config=config
    )


def _invoke(model_id: str, body: dict) -> dict:
    try:
        response = _client().invoke_model(modelId=model_id, body=json.dumps(body))
    except (NoCredentialsError, TokenRetrievalError) as exc:
        raise BedrockError(_credentials_hint(str(exc))) from exc
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in _CREDENTIAL_CODES:
            raise BedrockError(_credentials_hint(code)) from exc
        if code == "ThrottlingException":
            raise BedrockThrottled(f"{model_id} is throttled in {REGION}: {exc}") from exc
        if code == "AccessDeniedException":
            raise BedrockError(
                f"Access denied for {model_id} in {REGION}. Enable model access in the "
                "Bedrock console for this account, or set AWS_PROFILE to one that has it."
            ) from exc
        raise BedrockError(f"{model_id} failed in {REGION}: {code}: {exc}") from exc
    except BotoCoreError as exc:
        raise BedrockError(f"Cannot reach Bedrock in {REGION}: {exc}") from exc
    return json.loads(response["body"].read())


def _credentials_hint(detail: str) -> str:
    profile = os.getenv("AWS_PROFILE") or "default"
    return (
        f"AWS credentials are missing or expired ({detail}). "
        f"Refresh them, for example: aws sso login --profile {profile}"
    )


def embed(texts: list[str], input_type: InputType) -> list[list[float]]:
    """Embed up to 96 non-empty texts with Cohere Embed v4 (1536 dimensions).

    Args:
        texts: The texts to embed, in order.
        input_type: 'search_document' for corpus rows, 'search_query' for questions.

    Returns:
        One 1536-dimension vector per input text, in the same order.

    Raises:
        ValueError: If the batch is empty, too large, or contains blank text.
        BedrockError: If the call fails, with the next action in the message.
    """
    if not texts or len(texts) > MAX_TEXTS_PER_CALL:
        raise ValueError(f"embed() takes 1..{MAX_TEXTS_PER_CALL} texts, got {len(texts)}")
    if any(not text.strip() for text in texts):
        raise ValueError("embed() received blank text; Embed v4 rejects empty inputs")
    body = {
        "texts": texts,
        "input_type": input_type,
        "embedding_types": ["float"],
        "output_dimension": DIMENSIONS,
    }
    return _invoke(EMBED_MODEL_ID, body)["embeddings"]["float"]


def embed_query(text: str) -> list[float]:
    """Embed one question with input_type='search_query'."""
    return embed([text], "search_query")[0]


def rerank(query: str, documents: list[str], top_n: int | None = None) -> list[tuple[int, float]]:
    """Score documents against a query with Cohere Rerank.

    Returns:
        (index into documents, relevance score) pairs, most relevant first.
    """
    if not documents:
        return []
    body = {
        "query": query,
        "documents": documents,
        "top_n": top_n or len(documents),
        "api_version": 2,
    }
    results = _invoke(RERANK_MODEL_ID, body)["results"]
    return [(item["index"], float(item["relevance_score"])) for item in results]
