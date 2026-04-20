"""Bedrock Converse wrapper — one place for model IDs, auth, telemetry, audit.

Two models in play:

    Haiku 4.5  — orchestrator / intent parser (fast, cheap, tool-use)
    Opus  4.7  — response synthesizer (grounded picks → customer-facing text)

Both are addressed through global cross-Region inference profiles in us-east-1.
Every call is:
    1. timed + token-counted
    2. emitted as a telemetry panel for the UI
    3. logged to tool_audit in the same session

There is no fallback. If Bedrock is unreachable the request fails loudly —
the whole point of the demo is that the agent is LLM-driven end-to-end.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

import boto3
from botocore.config import Config

# ---- Model IDs (global cross-region inference profiles) ----------------
HAIKU_MODEL = os.getenv(
    "BEDROCK_HAIKU_MODEL",
    "global.anthropic.claude-haiku-4-5-20251001-v1:0",
)
OPUS_MODEL = os.getenv(
    "BEDROCK_OPUS_MODEL",
    "global.anthropic.claude-opus-4-7",
)
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


# Opus 4.7 dropped the temperature knob; other models still accept it.
def _inference_config(model_id: str, *, max_tokens: int, temperature: float = 0.0) -> dict:
    cfg: dict[str, Any] = {"maxTokens": max_tokens}
    if "opus-4-7" not in model_id:
        cfg["temperature"] = temperature
    return cfg


_runtime = None


def runtime():
    global _runtime
    if _runtime is None:
        _runtime = boto3.client(
            "bedrock-runtime",
            region_name=AWS_REGION,
            config=Config(
                read_timeout=120,
                connect_timeout=10,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )
    return _runtime


# ------------------------------------------------------------------------
# Core call: converse with telemetry + audit
# ------------------------------------------------------------------------
def converse(
    *,
    model_id: str,
    system: str,
    messages: list[dict],
    tool: dict | None = None,
    max_tokens: int = 1024,
) -> dict:
    """Thin wrapper around bedrock-runtime.converse.

    Returns a dict with the response plus {latency_ms, usage, stop_reason,
    text, tool_input}. Raises on any Bedrock error — no fallback.
    """
    kwargs: dict[str, Any] = {
        "modelId": model_id,
        "system": [{"text": system}],
        "messages": messages,
        "inferenceConfig": _inference_config(model_id, max_tokens=max_tokens),
    }
    if tool:
        kwargs["toolConfig"] = {
            "tools": [tool],
            "toolChoice": {"tool": {"name": tool["toolSpec"]["name"]}},
        }

    t0 = time.perf_counter()
    resp = runtime().converse(**kwargs)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    # Extract text + tool-use output blocks
    text_parts: list[str] = []
    tool_input: dict | None = None
    for block in resp["output"]["message"]["content"]:
        if "text" in block:
            text_parts.append(block["text"])
        elif "toolUse" in block:
            tool_input = block["toolUse"]["input"]

    return {
        "model_id": model_id,
        "latency_ms": latency_ms,
        "usage": resp.get("usage", {}),
        "stop_reason": resp.get("stopReason"),
        "text": "".join(text_parts),
        "tool_input": tool_input,
        "raw": resp,
    }


def emit_llm_panel(
    ctx,
    *,
    tag: str,
    title: str,
    call: dict,
    preview_cols: list[str],
    preview_rows: list[list[str]],
    meta: str,
) -> None:
    """Render an `LLM · …` telemetry panel for the UI."""
    usage = call.get("usage", {})
    latency = call.get("latency_ms", 0)
    footer = (
        f"{call['model_id']}  ·  "
        f"in={usage.get('inputTokens', 0)}  "
        f"out={usage.get('outputTokens', 0)}  "
        f"·  stop={call.get('stop_reason', '?')}  ·  {meta}"
    )
    ctx.emit_panel(
        agent="coordinator",
        tag=tag,
        tag_class="amber",
        title=title,
        columns=preview_cols,
        rows=preview_rows,
        meta=footer,
        duration_ms=latency,
    )


def log_llm_audit(
    *,
    session_id: str,
    call: dict,
    caller: str,
    purpose: str,
    messages_in: list[dict],
) -> None:
    """Log the LLM invocation to tool_audit so every model call sits next to
    every SQL call in the same table."""
    # Lazy import to avoid circular dep
    from db import conn

    usage = call.get("usage", {})
    args = {
        "purpose": purpose,
        "messages": [
            {
                "role": m["role"],
                "text": "".join(b.get("text", "") for b in m.get("content", [])),
            }
            for m in messages_in
        ],
    }
    result = {
        "stop_reason": call.get("stop_reason"),
        "input_tokens": usage.get("inputTokens", 0),
        "output_tokens": usage.get("outputTokens", 0),
        "text_preview": (call.get("text") or "")[:400],
        "tool_input": call.get("tool_input"),
    }
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """INSERT INTO tool_audit (session_id, tool, caller, args, result, latency_ms)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                session_id,
                f"llm:{call['model_id']}",
                caller,
                json.dumps(args),
                json.dumps(result),
                call.get("latency_ms", 0),
            ),
        )
        c.commit()
