"""Strands model adapters for the intent and reply edges of the SQL pipeline.

Intent uses one forced tool call; synthesis uses a Strands Agent with no tools.
Database reads, eligibility, memory and approvals remain application-controlled.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from botocore.config import Config
from jsonschema import validate
from strands import Agent
from strands.models import BedrockModel
from strands.models.openai import OpenAIModel

from bedrock import emit_llm_panel, log_llm_audit


class RunCancelled(Exception):
    """The browser disconnected or the request exceeded its deadline."""


@dataclass(frozen=True)
class ModelRoute:
    id: str
    label: str
    provider: str
    intent_model: str
    response_model: str


def model_routes() -> dict[str, ModelRoute]:
    return {
        "bedrock-openai": ModelRoute(
            "bedrock-openai", "GPT-5.6 Luna + Sol · Bedrock", "bedrock",
            os.getenv("BEDROCK_INTENT_MODEL", "us.openai.gpt-5.6-luna"),
            os.getenv("BEDROCK_RESPONSE_MODEL", "us.openai.gpt-5.6-sol"),
        ),
        "bedrock-claude": ModelRoute(
            "bedrock-claude", "Haiku 4.5 + Sonnet 5 · Bedrock", "bedrock",
            os.getenv("BEDROCK_HAIKU_MODEL", "global.anthropic.claude-haiku-4-5-20251001-v1:0"),
            os.getenv("BEDROCK_SONNET_MODEL", "us.anthropic.claude-sonnet-5"),
        ),
        "openai": ModelRoute(
            "openai", "GPT-5.6 Luna + Sol · OpenAI API", "openai",
            os.getenv("OPENAI_INTENT_MODEL", "gpt-5.6-luna"),
            os.getenv("OPENAI_RESPONSE_MODEL", "gpt-5.6-sol"),
        ),
    }


def resolve_route(route_id: str | None = None) -> ModelRoute:
    selected = route_id or os.getenv("CHAT_MODEL_ROUTE", "bedrock-openai")
    route = model_routes().get(selected)
    if route is None:
        raise ValueError("Unknown chat model route.")
    if route.provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OpenAI API needs OPENAI_API_KEY on the server. Choose a Bedrock route or configure the key locally.")
    return route


def chat_configuration() -> dict:
    routes = []
    for route in model_routes().values():
        configured = route.provider != "openai" or bool(os.getenv("OPENAI_API_KEY"))
        routes.append({**vars(route), "configured": configured})
    return {"default": os.getenv("CHAT_MODEL_ROUTE", "bedrock-openai"), "routes": routes,
            "transport": "sse", "framework": "Strands Agents"}


@lru_cache(maxsize=12)
def _bedrock_model(model_id: str, max_tokens: int, region: str) -> BedrockModel:
    # Omit sampling knobs: reasoning models differ in which knobs they accept.
    # No transparent replay after text has already reached the browser.
    return BedrockModel(
        model_id=model_id, region_name=region, streaming=True, max_tokens=max_tokens,
        boto_client_config=Config(connect_timeout=10, read_timeout=120,
                                  retries={"total_max_attempts": 1, "mode": "standard"}),
    )


def make_model(route: ModelRoute, model_id: str, max_tokens: int):
    if route.provider == "bedrock":
        return _bedrock_model(model_id, max_tokens, os.getenv("AWS_REGION", "us-east-1"))
    return OpenAIModel(
        model_id=model_id, stream=True,
        client_args={"api_key": os.environ["OPENAI_API_KEY"], "timeout": 120, "max_retries": 0},
        params={"max_completion_tokens": max_tokens, "reasoning_effort": "low"},
    )


def _normalize_enum_spellings(value, schema: dict):
    """Accept spelling variants of declared enums, without guessing new values.

    Some providers return 'pour-over' for the schema's 'pour_over'. Only
    case and separators may vary; types, required fields and unknown enums
    still pass through the JSON Schema validator unchanged.
    """
    if isinstance(value, str) and "enum" in schema:
        def spelling(text):
            return text.strip().casefold().replace("-", "_").replace(" ", "_")
        matches = [item for item in schema["enum"]
                   if isinstance(item, str) and spelling(item) == spelling(value)]
        return matches[0] if len(matches) == 1 else value
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        return {key: _normalize_enum_spellings(item, properties.get(key, {}))
                for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_enum_spellings(item, schema.get("items", {})) for item in value]
    return value


async def _invoke(*, route: ModelRoute, model_id: str, system: str, messages: list[dict],
                  tool: dict | None, max_tokens: int, on_text: Callable[[str], None] | None,
                  cancelled: threading.Event | None) -> dict:
    model = make_model(route, model_id, max_tokens)
    started = time.perf_counter()
    first_text_ms = None
    text_parts = []
    usage = {}
    stop_reason = None
    tool_input = None

    def check_cancelled():
        if cancelled and cancelled.is_set():
            raise RunCancelled()

    check_cancelled()
    if tool:
        # Parse the Strands provider's normalized tool stream. The model never
        # executes an order tool; this tool only records validated intent data.
        blocks = {}
        spec = tool["toolSpec"]
        stream = model.stream(messages, tool_specs=[spec], system_prompt=system,
                              tool_choice={"tool": {"name": spec["name"]}})
        try:
            async for event in stream:
                check_cancelled()
                if "contentBlockStart" in event:
                    block = event["contentBlockStart"]
                    use = block.get("start", {}).get("toolUse")
                    if use:
                        blocks[block["contentBlockIndex"]] = {"name": use["name"], "input": ""}
                if "contentBlockDelta" in event:
                    block = event["contentBlockDelta"]
                    delta = block["delta"]
                    if "toolUse" in delta:
                        blocks[block["contentBlockIndex"]]["input"] += delta["toolUse"].get("input", "")
                if "metadata" in event:
                    usage = event["metadata"].get("usage", {})
                if "messageStop" in event:
                    stop_reason = event["messageStop"]["stopReason"]
        finally:
            await stream.aclose()
        if stop_reason != "tool_use" or len(blocks) != 1:
            raise ValueError("Intent model did not complete exactly one intent tool call.")
        block = next(iter(blocks.values()))
        if block["name"] != spec["name"]:
            raise ValueError("Unexpected intent tool.")
        schema = spec["inputSchema"]["json"]
        tool_input = _normalize_enum_spellings(json.loads(block["input"]), schema)
        validate(tool_input, schema)
    else:
        agent = Agent(model=model, system_prompt=system, tools=[], callback_handler=None,
                      retry_strategy=None, name="Coffee concierge")
        # This application supplies its own bounded, database-backed context.
        stream = agent.stream_async(messages)
        try:
            async for event in stream:
                check_cancelled()
                if event.get("data"):
                    delta = event["data"]
                    if first_text_ms is None:
                        first_text_ms = int((time.perf_counter() - started) * 1000)
                    text_parts.append(delta)
                    if on_text:
                        on_text(delta)
                if "result" in event:
                    result = event["result"]
                    stop_reason = result.stop_reason
                    usage = result.metrics.accumulated_usage
        finally:
            await stream.aclose()
        if stop_reason != "end_turn" or not "".join(text_parts).strip():
            raise ValueError("Reply stream ended without a complete answer.")
    return {"model_id": model_id, "provider": route.provider, "framework": "strands",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "first_text_ms": first_text_ms, "usage": usage, "stop_reason": stop_reason,
            "text": "".join(text_parts), "tool_input": tool_input}


def converse(*, route: ModelRoute, model_id: str, system: str, messages: list[dict],
             tool: dict | None = None, max_tokens: int = 2048,
             on_text: Callable[[str], None] | None = None,
             cancelled: threading.Event | None = None) -> dict:
    """Called from the pipeline worker, never on FastAPI's event loop."""
    return asyncio.run(_invoke(route=route, model_id=model_id, system=system,
                               messages=messages, tool=tool, max_tokens=max_tokens,
                               on_text=on_text, cancelled=cancelled))
