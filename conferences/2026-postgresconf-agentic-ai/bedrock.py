"""Shared model telemetry and PostgreSQL audit helpers.

The historical module name is retained; invocation now lives in llm.py and
uses Strands for Bedrock and the direct OpenAI API alike.
"""
from __future__ import annotations

import json

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
        f"·  {call.get('provider', 'bedrock')} / Strands  "
        f"·  stop={call.get('stop_reason', '?')}  ·  {meta}"
    )
    if call.get("first_text_ms") is not None:
        footer += f" · first text {call['first_text_ms']} ms"
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
        "provider": call.get("provider"),
        "framework": call.get("framework"),
        "first_text_ms": call.get("first_text_ms"),
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
