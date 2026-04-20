"""Multi-agent orchestration for AI Coffee Roastery.

Three agents cooperating, all backed by PostgreSQL:

    Coordinator       ── plans + loads customer context (episodic memory)
        │
        ├──► Flavor Profiler    ── pgvector similarity search over the catalog
        │
        └──► Roast Master       ── applies brew/roast filters + check_inventory tool
                 │
                 └──► Coordinator synthesizes, grounds every claim, replies

Every meaningful action emits a telemetry event, which the frontend renders
as a panel (plan, memory lookup, tool call, grounding check, response).
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

from pgvector.psycopg import Vector

from db import conn, embed


# =======================================================================
# Telemetry context
# =======================================================================
@dataclass
class AgentContext:
    session_id: str
    customer_id: str
    query: str
    events: list[dict] = field(default_factory=list)
    _plan_step_index: int = 0

    # ---- emission helpers --------------------------------------------
    def emit(self, ev: dict) -> None:
        ev["ts_ms"] = int(time.time() * 1000)
        self.events.append(ev)

    def emit_plan(self, steps: list[str], duration_ms: int, title: str | None = None) -> None:
        self.emit({
            "type": "plan",
            "agent": "coordinator",
            "title": title or f"Decomposed into {len(steps)} steps",
            "steps": steps,
            "duration_ms": duration_ms,
        })

    def step_done(self) -> None:
        """Mark the next step as done, in order."""
        self.emit({"type": "step", "index": self._plan_step_index, "state": "done"})
        self._plan_step_index += 1

    def step_active(self) -> None:
        self.emit({"type": "step", "index": self._plan_step_index, "state": "active"})

    def emit_panel(
        self,
        *,
        agent: str,
        tag: str,
        title: str,
        sql: str = "",
        columns: list[str] | None = None,
        rows: list[list[str]] | None = None,
        meta: str = "",
        duration_ms: int = 0,
        tag_class: str = "cyan",
    ) -> None:
        self.emit({
            "type": "panel",
            "agent": agent,
            "tag": tag,
            "tag_class": tag_class,
            "title": title,
            "sql": sql.strip(),
            "columns": columns or [],
            "rows": rows or [],
            "meta": meta,
            "duration_ms": duration_ms,
        })

    def emit_response(self, text: str, citations: list[dict], confidence: int) -> None:
        self.emit({
            "type": "response",
            "agent": "coordinator",
            "text": text,
            "citations": citations,
            "confidence": confidence,
        })


# =======================================================================
# Intent parsing — lookup tables + Haiku 4.5 tool-use
# =======================================================================
# Lookup tables below feed the Roast Master's filter and the Flavor
# Profiler's embedding anchor. The actual *intent parser* is Haiku-driven
# (see parse_intent below) — it reads the last 6 turns of agent_messages
# to resolve referential phrases like "order that" to a concrete bean id.

BREW_METHOD_PATTERNS: list[tuple[str, str, list[str]]] = [
    # (method_key, display_label, matching substrings — lowercase)
    ("cold_brew",    "cold brew",       ["cold brew", "iced coffee"]),
    ("espresso",     "espresso",        ["espresso", "shot"]),
    ("french_press", "French press",    ["french press", "press pot", "plunger"]),
    ("pour_over",    "pour-over",       ["pour over", "pour-over", "v60", "chemex", "kalita"]),
    ("moka",         "moka pot",        ["moka", "stovetop"]),
    ("drip",         "drip",            ["drip", "auto drip", "batch brew"]),
]

# brew_method → preferred roast levels
BREW_ROAST_MAP: dict[str, list[str]] = {
    "cold_brew":    ["medium", "medium-dark", "dark"],
    "espresso":     ["medium-dark", "dark"],
    "french_press": ["medium", "medium-dark", "dark"],
    "pour_over":    ["light", "medium-light", "medium"],
    "moka":         ["medium-dark", "dark"],
    "drip":         ["medium-light", "medium", "medium-dark"],
}

# Natural-language flavor seeds per brew method — used to give the embedding
# search a concrete anchor. Keeps the semantic search focused on the request
# instead of letting customer history dominate it.
BREW_FLAVOR_SEED: dict[str, str] = {
    "cold_brew":    "smooth, low-acid, chocolate, caramel, sweet, heavy body, long steep",
    "espresso":     "syrupy, dense crema, chocolate, caramel, nutty, concentrated shot",
    "french_press": "full body, heavy, chocolate, nutty, low-acid, coarse grind",
    "pour_over":    "bright, clean, floral, citrus, tea-like, delicate, washed process",
    "moka":         "bold, concentrated, chocolate, spice, stovetop",
    "drip":         "balanced, everyday, sweet, approachable, medium body",
}

ROAST_LEVEL_PATTERNS: list[tuple[str, list[str]]] = [
    ("light",         ["light roast", "light-roast"]),
    ("medium-light",  ["medium-light", "medium light"]),
    ("medium",        ["medium roast"]),
    ("medium-dark",   ["medium-dark", "medium dark"]),
    ("dark",          ["dark roast", "dark-roast"]),
]


ORDER_INTENT_PATTERNS = ["order", "buy", "purchase", "ship me", "place an order", "checkout"]


# ---- Haiku intent parser ------------------------------------------------
# The deterministic regex parser has been replaced by Haiku 4.5. The LLM
# version handles referential queries ("order that", "same as last time")
# by reading the session's recent messages — impossible with substring
# matching.
INTENT_TOOL_SPEC = {
    "toolSpec": {
        "name": "record_intent",
        "description": (
            "Record the parsed intent of the customer's latest message. "
            "Always call this once with all fields filled in."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "brew_method": {
                        "type": ["string", "null"],
                        "enum": [
                            "cold_brew", "espresso", "french_press",
                            "pour_over", "moka", "drip", None,
                        ],
                        "description": "Brew method the customer mentioned. Null if not specified.",
                    },
                    "explicit_roasts": {
                        "type": "array",
                        "items": {
                            "enum": ["light", "medium-light", "medium", "medium-dark", "dark"],
                        },
                        "description": "Explicit roast levels the customer asked for. Empty if none.",
                    },
                    "budget_cents": {
                        "type": ["integer", "null"],
                        "description": "Upper budget in US cents (e.g. $20 -> 2000). Null if no budget mentioned.",
                    },
                    "wants_order": {
                        "type": "boolean",
                        "description": "True if the customer is asking to place an order right now.",
                    },
                    "order_referent_bean_id": {
                        "type": ["string", "null"],
                        "description": (
                            "If wants_order=true and the customer is referring to a bean "
                            "that was previously recommended in this conversation (e.g. 'order that', "
                            "'order a bag', 'the cold brew you just showed me'), return the bean id "
                            "from the most recent recommendation. Null otherwise."
                        ),
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "One short sentence explaining the parse. Shown in telemetry.",
                    },
                },
                "required": [
                    "brew_method", "explicit_roasts", "budget_cents",
                    "wants_order", "order_referent_bean_id", "reasoning",
                ],
            }
        },
    }
}

_BREW_LABEL_MAP = {
    "cold_brew": "cold brew",
    "espresso": "espresso",
    "french_press": "French press",
    "pour_over": "pour-over",
    "moka": "moka pot",
    "drip": "drip",
}


# --- Haiku parser + recent-message loader ------------------------------

def _load_recent_messages(session_id: str, limit: int = 6) -> list[dict]:
    """Recent turn history for the LLM — user text + agent text + cited beans."""
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """SELECT role, agent, content FROM agent_messages
                WHERE session_id = %s
                ORDER BY ts DESC
                LIMIT %s""",
            (session_id, limit),
        )
        rows = cur.fetchall()
    rows.reverse()
    out: list[dict] = []
    for role, agent, content in rows:
        content = content or {}
        text = content.get("text", "")
        cites = content.get("citations") or []
        out.append({"role": role, "agent": agent, "text": text, "citations": cites})
    return out


def parse_intent(ctx: "AgentContext") -> dict:
    """Haiku-powered intent parser. Emits an LLM telemetry panel + audit row.

    Takes the full AgentContext (rather than just the query string) so it can
    read the session's recent messages and resolve references like "order
    that" to a concrete bean id.
    """
    from bedrock import HAIKU_MODEL, converse, emit_llm_panel, log_llm_audit

    recent = _load_recent_messages(ctx.session_id, limit=6)

    history_lines: list[str] = []
    for m in recent[:-0 or None]:  # include everything we got
        if m["role"] == "user":
            history_lines.append(f"[user] {m['text']}")
        elif m["role"] == "agent":
            cite_str = ""
            if m["citations"]:
                cite_str = " [cited: " + ", ".join(
                    f"{c.get('label','?')}={c.get('key','?')}" for c in m["citations"]
                ) + "]"
            history_lines.append(f"[{m['agent'] or 'agent'}] {m['text'][:300]}{cite_str}")
    history_block = "\n".join(history_lines) if history_lines else "(no prior turns)"

    system = (
        "You parse coffee-shop customer requests into structured intent. "
        "You always call the record_intent tool exactly once. "
        "You have access to the conversation so far — use it to resolve "
        "referential phrases like 'order that', 'the cold brew', 'same as last time' "
        "to the concrete bean id that was cited in the most recent agent reply."
    )
    user_msg = (
        f"Conversation so far (oldest → newest):\n{history_block}\n\n"
        f"Latest customer message: {ctx.query!r}\n\n"
        f"Parse the latest message into structured intent."
    )

    call = converse(
        model_id=HAIKU_MODEL,
        system=system,
        messages=[{"role": "user", "content": [{"text": user_msg}]}],
        tool=INTENT_TOOL_SPEC,
        max_tokens=500,
    )

    parsed = call["tool_input"] or {}

    # Normalize — ensure all expected keys exist
    intent = {
        "brew_method": parsed.get("brew_method"),
        "brew_label": _BREW_LABEL_MAP.get(parsed.get("brew_method") or ""),
        "explicit_roasts": parsed.get("explicit_roasts") or [],
        "budget_cents": parsed.get("budget_cents"),
        "wants_order": bool(parsed.get("wants_order")),
        "order_referent_bean_id": parsed.get("order_referent_bean_id"),
        "_llm_reasoning": parsed.get("reasoning", ""),
    }

    emit_llm_panel(
        ctx,
        tag="LLM · HAIKU · INTENT",
        title="Haiku 4.5 parsed the customer request via tool-use",
        call=call,
        preview_cols=["field", "value"],
        preview_rows=[
            ["brew_method", intent["brew_method"] or "(unspecified)"],
            ["explicit_roasts", ", ".join(intent["explicit_roasts"]) or "(none)"],
            ["budget_cents", str(intent["budget_cents"]) if intent["budget_cents"] else "(none)"],
            ["wants_order", "yes" if intent["wants_order"] else "no"],
            ["order_referent_bean_id", intent["order_referent_bean_id"] or "(none)"],
            ["reasoning", intent["_llm_reasoning"] or "—"],
        ],
        meta="structured JSON via Converse tool-use · referential 'order that' resolves here",
    )
    log_llm_audit(
        session_id=ctx.session_id,
        call=call,
        caller="coordinator",
        purpose="parse_intent",
        messages_in=[{"role": "user", "content": [{"text": user_msg}]}],
    )

    return intent


# =======================================================================
# Shared DB helpers — these are the "real" queries the audience cares about
# =======================================================================

def _rows_as_strings(rows: Iterable[Iterable]) -> list[list[str]]:
    out: list[list[str]] = []
    for r in rows:
        out.append([("—" if v is None else str(v)) for v in r])
    return out


def log_tool_call(
    *, session_id: str, tool: str, caller: str,
    args: dict, result: dict, latency_ms: int,
) -> str:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """INSERT INTO tool_audit (session_id, tool, caller, args, result, latency_ms)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (session_id, tool, caller, json.dumps(args), json.dumps(result), latency_ms),
        )
        audit_id = cur.fetchone()[0]
        c.commit()
    return f"aud_{audit_id:05d}"


def discover_tools(ctx: "AgentContext", query: str, limit: int = 4) -> list[dict]:
    """Dynamic tool discovery — cosine-rank the registry against the request.

    This is the "tool registry" pillar: tools + their description embeddings
    live in Postgres, and the agent picks relevant ones at query time
    instead of hard-coding a static toolbox.
    """
    sql = """
SELECT name, description, requires_approval, owner_agent,
       1 - (description_emb <=> $1) AS score
  FROM tools
 WHERE enabled = TRUE
 ORDER BY description_emb <=> $1
 LIMIT $2;""".strip()

    t0 = time.perf_counter()
    q_vec = embed(query)
    with conn() as c, c.cursor() as cur:
        cur.execute(
            sql.replace("$1", "%s").replace("$2", "%s"),
            (Vector(q_vec), Vector(q_vec), limit),
        )
        rows = cur.fetchall()
    dur = int((time.perf_counter() - t0) * 1000)

    display = [
        [r[0], r[3] or "—", "yes" if r[2] else "no", f"{r[4]:.2f}"]
        for r in rows
    ]
    ctx.emit_panel(
        agent="coordinator",
        tag="TOOL REGISTRY · DISCOVER",
        title="Ranked tools by semantic match against the request",
        sql=sql,
        columns=["tool", "owner", "approval?", "score"],
        rows=display,
        meta="one pgvector query over <b>tools.description_emb</b> · registry lives in Postgres, not code",
        duration_ms=dur,
    )
    return [
        {"name": r[0], "description": r[1], "requires_approval": r[2],
         "owner_agent": r[3], "score": float(r[4])}
        for r in rows
    ]


def save_workflow_state(session_id: str, state: dict) -> None:
    """Checkpoint the plan + current step index to Postgres.

    Every step boundary writes here. If the process dies, the next call to
    run_query could resume from `workflow_state->>'step_index'` — this is
    the "state management" pillar.
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """UPDATE agent_sessions
                  SET workflow_state = %s,
                      updated_at     = now()
                WHERE id = %s""",
            (json.dumps(state), session_id),
        )
        c.commit()


def request_approval(
    *, session_id: str, tool: str, caller: str, args: dict, reason: str,
) -> int:
    """Queue a sensitive tool call for human approval.

    The row lives in `approvals` with status='pending'. The effect is NOT
    executed until the row flips to 'approved'. This is the guardrail for
    destructive/expensive tool invocations.
    """
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """INSERT INTO approvals (session_id, tool, caller, args, reason)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (session_id, tool, caller, json.dumps(args), reason),
        )
        approval_id = cur.fetchone()[0]
        c.commit()
    return approval_id


# =======================================================================
# Coordinator
# =======================================================================
class CoordinatorAgent:
    def handle(self, ctx: AgentContext) -> None:
        # Step 0 is intent parsing (LLM). We emit the plan first so the panel
        # order in the UI still reads top-to-bottom.
        steps = [
            "Parse intent with Haiku 4.5 and discover relevant tools",
            f"Load {self._first_name(ctx)}'s episodic + procedural memory",
            "Flavor Profiler: semantic (pgvector) search over the catalog",
            "Roast Master: filter for brew method + audited check_inventory",
            "Fact-check picks, synthesize response with Opus 4.7",
        ]
        ctx.emit_plan(steps, duration_ms=45)

        # Step 0: intent (Haiku) + dynamic tool discovery -------------------
        ctx.step_active()
        intent = parse_intent(ctx)
        self._checkpoint(ctx, "planning", steps=steps, intent=intent)
        discover_tools(ctx, ctx.query)
        ctx.step_done()
        self._checkpoint(ctx, "memory_lookup")

        # Step 1: episodic + procedural memory ------------------------------
        ctx.step_active()
        history = self._load_history(ctx)
        self._load_procedural(ctx, intent)
        ctx.step_done()
        self._checkpoint(ctx, "semantic_search")

        # Step 2: flavor profiler -------------------------------------------
        ctx.step_active()
        candidates = FlavorProfilerAgent().profile(ctx, intent, history)
        ctx.step_done()
        self._checkpoint(ctx, "roast_master_filter")

        # Step 3: roast master ----------------------------------------------
        ctx.step_active()
        final = RoastMasterAgent().refine(ctx, intent, candidates)
        ctx.step_done()
        self._checkpoint(ctx, "grounding")

        # Step 4: ground & respond ------------------------------------------
        ctx.step_active()
        self._respond(ctx, intent, history, final)
        ctx.step_done()
        self._checkpoint(ctx, "done")

    def _checkpoint(self, ctx: AgentContext, stage: str, **extra: Any) -> None:
        state = {
            "stage": stage,
            "step_index": ctx._plan_step_index,
            "query": ctx.query,
            **extra,
        }
        save_workflow_state(ctx.session_id, state)

    # ------------------------------------------------------------------
    def _first_name(self, ctx: AgentContext) -> str:
        with conn() as c, c.cursor() as cur:
            cur.execute("SELECT name FROM customers WHERE id=%s", (ctx.customer_id,))
            r = cur.fetchone()
        return r[0] if r else "the customer"

    # ------------------------------------------------------------------
    def _load_history(self, ctx: AgentContext) -> list[dict]:
        sql = """
SELECT b.name, b.roast_level, o.qty, to_char(o.placed_at, 'YYYY-MM-DD') AS placed
  FROM orders o
  JOIN beans  b ON b.id = o.bean_id
 WHERE o.customer_id = $1
 ORDER BY o.placed_at DESC
 LIMIT 5;""".strip()

        t0 = time.perf_counter()
        with conn() as c, c.cursor() as cur:
            # real query (with %s binding for psycopg)
            cur.execute(
                sql.replace("$1", "%s"),
                (ctx.customer_id,),
            )
            rows = cur.fetchall()
            # also pull the preferences_summary for downstream use
            cur.execute("SELECT preferences_summary FROM customers WHERE id=%s", (ctx.customer_id,))
            prefs_row = cur.fetchone()
        dur = int((time.perf_counter() - t0) * 1000)

        prefs = prefs_row[0] if prefs_row else ""

        ctx.emit_panel(
            agent="coordinator",
            tag="MEMORY · EPISODIC",
            title=f"Most recent orders for {ctx.customer_id}",
            sql=sql,
            columns=["bean", "roast", "qty", "placed_at"],
            rows=_rows_as_strings(rows),
            meta=f"{len(rows)} rows  ·  index scan on <b>orders_customer_idx</b>",
            duration_ms=dur,
        )

        # also emit the preferences summary as a separate small panel
        ctx.emit_panel(
            agent="coordinator",
            tag="MEMORY · PROFILE",
            title="Preference summary (from customers.preferences_summary)",
            columns=["summary"],
            rows=[[prefs or "(empty)"]],
            meta="single-row lookup by PK",
            duration_ms=1,
        )

        return [
            {"bean": r[0], "roast": r[1], "qty": r[2], "placed_at": r[3], "prefs": prefs}
            for r in rows
        ]

    # ------------------------------------------------------------------
    def _load_procedural(self, ctx: AgentContext, intent: dict) -> None:
        """Procedural memory — what have *similar* customers done before?

        'Similar' is computed over the embedding of the current request; the
        join reaches into orders to find beans that cohorts with a matching
        preference summary actually bought. This is the few-shot context the
        synthesizer can lean on.
        """
        sql = """
WITH q AS (SELECT %s::vector AS v)
SELECT b.name, c.name AS customer, COUNT(*) AS times_ordered,
       MAX(1 - (b.embedding <=> (SELECT v FROM q))) AS similarity
  FROM orders   o
  JOIN beans    b ON b.id = o.bean_id
  JOIN customers c ON c.id = o.customer_id
 WHERE c.id <> %s
 GROUP BY b.name, c.name
 ORDER BY similarity DESC
 LIMIT 5;""".strip()

        t0 = time.perf_counter()
        q_vec = embed(ctx.query)
        with conn() as c, c.cursor() as cur:
            cur.execute(sql, (Vector(q_vec), ctx.customer_id))
            rows = cur.fetchall()
        dur = int((time.perf_counter() - t0) * 1000)

        display = [[r[0], r[1], str(r[2]), f"{r[3]:.2f}"] for r in rows]
        ctx.emit_panel(
            agent="coordinator",
            tag="MEMORY · PROCEDURAL",
            title="What similar customers actually bought (few-shot context)",
            sql=sql,
            columns=["bean", "customer", "times", "similarity"],
            rows=display,
            meta="vector similarity joined with <b>orders</b> — one query, three sources of context",
            duration_ms=dur,
        )

    # ------------------------------------------------------------------
    def _respond(
        self,
        ctx: AgentContext,
        intent: dict,
        history: list[dict],
        picks: list[dict],
    ) -> None:
        # ---- fact-check pass ------------------------------------------
        # Before we respond, re-read the canonical rows and re-verify stock.
        # A pick that fails to verify is dropped — the guardrail.
        verified: list[dict] = []
        if picks:
            sql = """
SELECT id, name, roast_level, in_stock, price_cents
  FROM beans
 WHERE id = ANY(%s);""".strip()
            t0 = time.perf_counter()
            with conn() as c, c.cursor() as cur:
                cur.execute(sql, ([p["id"] for p in picks],))
                canon = {r[0]: r for r in cur.fetchall()}
            dur = int((time.perf_counter() - t0) * 1000)

            check_rows = []
            for p in picks:
                row = canon.get(p["id"])
                ok = bool(row and row[3] > 0)
                check_rows.append([p["name"], "beans." + p["id"], "pass" if ok else "FAIL"])
                if ok:
                    verified.append(p)

            ctx.emit_panel(
                agent="coordinator",
                tag="GUARDRAIL · FACT-CHECK",
                tag_class="amber",
                title=f"Re-verify every pick against beans · {len(verified)}/{len(picks)} passed",
                sql=sql,
                columns=["claim", "source_row", "verdict"],
                rows=check_rows,
                meta="any pick failing verification is dropped before the reply",
                duration_ms=dur,
            )

        # ---- grounding panel ------------------------------------------
        # Chat continuity: if Haiku resolved "order that" to a specific bean
        # id from the conversation, pin that bean to the front of verified
        # so approval + response reference what the customer meant. Fall
        # back to reading the last agent citation if the LLM did not
        # return a referent (shouldn't happen, but belt and braces).
        if intent.get("wants_order") and verified:
            prior_id = intent.get("order_referent_bean_id")
            # Haiku sometimes returns the full citation key (beans.X) rather
            # than the bare bean id — normalize either shape.
            if prior_id and prior_id.startswith("beans."):
                prior_id = prior_id.removeprefix("beans.")
            prior: dict | None = None
            if prior_id:
                prior = {"id": prior_id, "name": ""}
            else:
                prior = self._last_recommended_bean(ctx)

            if prior:
                idx = next(
                    (i for i, p in enumerate(verified) if p["id"] == prior["id"]),
                    -1,
                )
                if idx > 0:
                    verified = [verified[idx]] + [p for i, p in enumerate(verified) if i != idx]
                elif idx == -1:
                    # prior bean dropped out of this turn's picks — re-hydrate
                    # it from the beans table so the order still references
                    # the thing we actually recommended.
                    hydrated = self._hydrate_bean(prior["id"])
                    if hydrated:
                        verified = [hydrated] + verified

        rows = [
            [p["name"], "beans." + p["id"], f"in_stock={p['in_stock']}"]
            for p in verified
        ]
        confidence = self._confidence(verified, history)
        ctx.emit_panel(
            agent="coordinator",
            tag="GROUNDING",
            tag_class="green",
            title=f"Every claim cited · {len(verified)}/{len(verified)} grounded"
                  if verified else "No stocked bean matched — refusing to invent one",
            columns=["bean", "source_row", "stock"],
            rows=rows,
            meta="grounded against the <b>beans</b> table · no invention",
            duration_ms=1,
        )

        # ---- order approval workflow (guardrail) ----------------------
        if intent.get("wants_order") and verified:
            top = verified[0]
            args = {"customer_id": ctx.customer_id, "bean_id": top["id"], "qty": 1}
            approval_id = request_approval(
                session_id=ctx.session_id,
                tool="place_order",
                caller="coordinator",
                args=args,
                reason=f"order requested for {top['name']} (qty 1)",
            )
            ctx.emit_panel(
                agent="coordinator",
                tag="GUARDRAIL · APPROVAL",
                tag_class="amber",
                title=f"place_order queued — awaiting approval (id {approval_id})",
                sql="-- INSERT INTO approvals (...) VALUES (status='pending')",
                columns=["field", "value"],
                rows=[
                    ["tool",        "place_order"],
                    ["customer_id", ctx.customer_id],
                    ["bean_id",     top["id"]],
                    ["qty",         "1"],
                    ["status",      "pending"],
                ],
                meta=f"row <b>approvals.{approval_id}</b> · effect blocked until approved",
                duration_ms=1,
            )

        # synthesize text (no LLM — template assembly)
        text = self._synthesize(ctx, intent, history, verified)
        citations = [{"key": f"beans.{p['id']}", "label": p["name"]} for p in verified]
        ctx.emit_response(text, citations, confidence)

    def _confidence(self, picks: list[dict], history: list[dict]) -> int:
        """Confidence based on data availability — not a fudge factor."""
        if not picks:
            return 30
        base = 60 + min(20, len(picks) * 7)          # up to +20 for breadth
        if history:
            base += 8                                 # +8 for personalization
        top_score = picks[0].get("score", 0) * 10    # up to +10 from similarity
        return max(30, min(98, int(base + top_score)))

    # ------------------------------------------------------------------
    def _last_recommended_bean(self, ctx: AgentContext) -> dict | None:
        """Return the top citation from this session's most recent agent reply.

        Conversational continuity: when the user says "order a bag" or
        "order that", the referent is the thing we just recommended — not
        whatever embeds closest to the new query. Reads episodic memory
        (agent_messages) to resolve the reference.
        """
        with conn() as c, c.cursor() as cur:
            cur.execute(
                """SELECT content FROM agent_messages
                    WHERE session_id = %s AND role = 'agent'
                    ORDER BY ts DESC LIMIT 1""",
                (ctx.session_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        content = row[0] or {}
        cites = content.get("citations") or []
        if not cites:
            return None
        top = cites[0]
        key = top.get("key", "")
        if not key.startswith("beans."):
            return None
        return {"id": key.removeprefix("beans."), "name": top.get("label", "")}

    def _hydrate_bean(self, bean_id: str) -> dict | None:
        """Fetch a bean row in the shape the rest of _respond expects."""
        with conn() as c, c.cursor() as cur:
            cur.execute(
                """SELECT id, name, roast_level, process, flavor_notes,
                          price_cents, in_stock
                     FROM beans WHERE id = %s""",
                (bean_id,),
            )
            r = cur.fetchone()
        if not r:
            return None
        return {
            "id": r[0], "name": r[1], "roast_level": r[2],
            "process": r[3], "flavor_notes": r[4],
            "price_cents": r[5], "in_stock": r[6],
            "score": 0.0,
            "one_liner": f"{r[2]} roast · {', '.join((r[4] or [])[:3])} · ${r[5]/100:.2f}/bag",
        }


    def _synthesize(self, ctx, intent, history, picks) -> str:
        """Opus 4.7 writes the customer-facing reply from the grounded picks.

        Everything that reaches this function has already been:
          * filtered by the Roast Master
          * fact-checked against the live `beans` table
          * re-verified for in-stock > 0

        Opus only composes text from that verified set — it cannot invent
        beans because the system prompt and the schema constrain it to
        bean ids we pass in. Citations are still enforced in code via the
        grounding panel.
        """
        from bedrock import OPUS_MODEL, converse, emit_llm_panel, log_llm_audit

        first_name = self._first_name(ctx)

        # ---- Refusal path ------------------------------------------------
        # No grounded picks → we still ask Opus for a graceful short refusal,
        # but tightly constrained. This keeps the demo consistent: every
        # visible response goes through the synthesizer.
        if not picks:
            system = (
                "You are a coffee shop assistant. Every word you say must be grounded "
                "in facts provided to you. You MUST NOT invent bean names, origins, or "
                "prices. When no stocked bean matches the request, say so briefly and "
                "suggest the customer broaden the request. Reply in one or two sentences. "
                "Plain text only, no HTML."
            )
            user_msg = (
                f"Customer name: {first_name}\n"
                f"Customer request: {ctx.query!r}\n"
                f"Grounded picks available: NONE\n\n"
                f"Write a brief, warm refusal."
            )
            call = converse(
                model_id=OPUS_MODEL,
                system=system,
                messages=[{"role": "user", "content": [{"text": user_msg}]}],
                max_tokens=200,
            )
            emit_llm_panel(
                ctx,
                tag="LLM · OPUS · SYNTHESIZE",
                title="Opus 4.7 composed the refusal (no grounded picks)",
                call=call,
                preview_cols=["output"],
                preview_rows=[[call["text"][:300]]],
                meta="constrained by system prompt to not invent beans",
            )
            log_llm_audit(
                session_id=ctx.session_id,
                call=call,
                caller="coordinator",
                purpose="synthesize_refusal",
                messages_in=[{"role": "user", "content": [{"text": user_msg}]}],
            )
            return call["text"].strip()

        # ---- Build grounded context for Opus -----------------------------
        bean_block = "\n".join(
            f"- id={p['id']} | name={p['name']} | roast={p['roast_level']} | "
            f"notes={', '.join(p['flavor_notes'])} | price=${p['price_cents']/100:.2f}/bag | "
            f"in_stock={p['in_stock']}"
            for p in picks
        )
        history_block = "\n".join(
            f"- {h['bean']} ({h['roast']} roast), qty={h['qty']}, {h['placed_at']}"
            for h in history
        ) or "(no prior orders)"
        prefs = history[0]["prefs"] if history else ""

        # ---- Order branch -----------------------------------------------
        if intent.get("wants_order"):
            top = picks[0]
            system = (
                "You are the coffee shop coordinator writing the customer-facing reply. "
                "The customer asked to place an order. An approval row has ALREADY been "
                "written to the `approvals` table in PostgreSQL with status='pending'. "
                "Nothing has shipped, nothing has been charged, no inventory has moved. "
                "\n\n"
                "Rules:\n"
                "1. Reference the bean by exactly the name/id provided below — no others.\n"
                "2. Wrap the bean name with <cite data-k=\"beans.{id}\">{name}</cite>.\n"
                "3. Make it clear the order is pending human approval.\n"
                "4. Tone: warm, concise, dev-savvy. Two to three sentences.\n"
                "5. Output HTML snippets only (use <b>, <code>, <cite>). No markdown."
            )
            user_msg = (
                f"Customer name: {first_name}\n"
                f"Customer latest message: {ctx.query!r}\n"
                f"Bean to order: id={top['id']} | name={top['name']} | qty=1\n"
                f"Write the confirmation reply."
            )
            call = converse(
                model_id=OPUS_MODEL,
                system=system,
                messages=[{"role": "user", "content": [{"text": user_msg}]}],
                max_tokens=400,
            )
            emit_llm_panel(
                ctx,
                tag="LLM · OPUS · SYNTHESIZE",
                title="Opus 4.7 composed the order confirmation",
                call=call,
                preview_cols=["output"],
                preview_rows=[[call["text"][:400]]],
                meta="constrained to the single bean already queued in approvals",
            )
            log_llm_audit(
                session_id=ctx.session_id,
                call=call,
                caller="coordinator",
                purpose="synthesize_order_ack",
                messages_in=[{"role": "user", "content": [{"text": user_msg}]}],
            )
            return call["text"].strip()

        # ---- Recommendation branch --------------------------------------
        brew_label = intent.get("brew_label") or "(unspecified)"
        system = (
            "You are the coffee shop coordinator writing a grounded recommendation "
            "for a customer.\n\n"
            "Hard rules — violating any of these is a bug:\n"
            "1. You may ONLY reference beans from the `grounded_picks` block. Do not "
            "   name any bean that is not in that list.\n"
            "2. Every bean name you mention MUST be wrapped in a citation tag: "
            "   <cite data-k=\"beans.{id}\">{name}</cite>\n"
            "3. Output HTML snippets (use <b>, <cite>, <br>). No markdown, no headings.\n"
            "4. Do not invent prices, origins, or flavor notes — only use what's in "
            "   grounded_picks.\n"
            "5. Be concise: ~3–5 sentences total. Mention 2–3 beans at most.\n"
            "6. If the customer has an order history, you may lightly reference what "
            "   they last bought — it helps them place today's pick in context.\n"
            "7. End with a one-line 'safest bet vs. something different' framing if "
            "   there are at least two picks.\n"
            "8. Warm, dev-savvy tone. No emoji, no exclamation points."
        )
        user_msg = (
            f"Customer name: {first_name}\n"
            f"Customer profile: {prefs or '(none)'}\n"
            f"Brew method: {brew_label}\n"
            f"Customer latest message: {ctx.query!r}\n\n"
            f"Recent order history (newest first):\n{history_block}\n\n"
            f"Grounded picks (the ONLY beans you may reference):\n{bean_block}\n\n"
            f"Compose the recommendation reply."
        )
        call = converse(
            model_id=OPUS_MODEL,
            system=system,
            messages=[{"role": "user", "content": [{"text": user_msg}]}],
            max_tokens=600,
        )
        emit_llm_panel(
            ctx,
            tag="LLM · OPUS · SYNTHESIZE",
            title=f"Opus 4.7 composed a grounded reply from {len(picks)} picks",
            call=call,
            preview_cols=["output"],
            preview_rows=[[call["text"][:600]]],
            meta="system prompt restricts output to the grounded picks · citations enforced",
        )
        log_llm_audit(
            session_id=ctx.session_id,
            call=call,
            caller="coordinator",
            purpose="synthesize_recommendation",
            messages_in=[{"role": "user", "content": [{"text": user_msg}]}],
        )
        return call["text"].strip()


# =======================================================================
# Flavor Profiler — pgvector semantic search
# =======================================================================
class FlavorProfilerAgent:
    def profile(self, ctx: AgentContext, intent: dict, history: list[dict]) -> list[dict]:
        # The embed input is anchored on the *request* and its brew-method flavor
        # seed. Customer history is applied as a soft bias via the procedural
        # memory panel and the Roast Master's filter — not by concatenating it
        # into the embedding, which lets strong preferences (Ana's dark espresso
        # history) overwhelm the actual request ("cold brew").
        seed = BREW_FLAVOR_SEED.get(intent["brew_method"] or "", "")
        embed_input = f"{ctx.query}. {seed}" if seed else ctx.query

        t0 = time.perf_counter()
        q_vec = embed(embed_input)
        embed_ms = int((time.perf_counter() - t0) * 1000)

        # Build the similarity SQL — real pgvector cosine distance
        sql = """
SELECT id, name, roast_level, process, flavor_notes, price_cents, in_stock,
       1 - (embedding <=> $1) AS score
  FROM beans
 ORDER BY embedding <=> $1
 LIMIT 6;""".strip()

        t1 = time.perf_counter()
        with conn() as c, c.cursor() as cur:
            vec = Vector(q_vec)
            cur.execute(sql.replace("$1", "%s"), (vec, vec))
            rows = cur.fetchall()
        search_ms = int((time.perf_counter() - t1) * 1000)

        # panel
        display_rows = [
            [r[1], r[2], ", ".join(r[4])[:36], f"{r[7]:.2f}"]  # name, roast, notes, score
            for r in rows
        ]
        ctx.emit_panel(
            agent="flavor_profiler",
            tag="MEMORY · SEMANTIC",
            title="pgvector cosine search over beans.embedding",
            sql=sql,
            columns=["bean", "roast", "flavor notes", "score"],
            rows=display_rows,
            meta=f"HNSW index · {embed_ms}ms embed + {search_ms}ms query · top-6 returned",
            duration_ms=embed_ms + search_ms,
        )

        return [
            {
                "id": r[0], "name": r[1], "roast_level": r[2],
                "process": r[3], "flavor_notes": r[4],
                "price_cents": r[5], "in_stock": r[6], "score": float(r[7]),
                "one_liner": self._one_liner(r),
            }
            for r in rows
        ]

    @staticmethod
    def _one_liner(row) -> str:
        notes = row[4][:3]
        return (
            f"{row[2]} roast · {', '.join(notes)} · ${row[5]/100:.2f}/bag"
        )


# =======================================================================
# Roast Master — filters by brew method, checks inventory
# =======================================================================
class RoastMasterAgent:
    def refine(
        self,
        ctx: AgentContext,
        intent: dict,
        candidates: list[dict],
    ) -> list[dict]:
        # build allowed roast-level set
        allowed = set()
        if intent["explicit_roasts"]:
            allowed = set(intent["explicit_roasts"])
        elif intent["brew_method"]:
            allowed = set(BREW_ROAST_MAP.get(intent["brew_method"], []))

        # Emit a filter panel
        if allowed:
            rows = [[r, "✓" if any(c["roast_level"] == r for c in candidates) else "—"] for r in sorted(allowed)]
            ctx.emit_panel(
                agent="roast_master",
                tag="ROAST MASTER · FILTER",
                title=f"Brew-method filter: {intent.get('brew_label') or 'explicit roasts'}",
                sql=f"-- roast_level IN {tuple(sorted(allowed))!r}",
                columns=["allowed_roast", "matched?"],
                rows=rows,
                meta="filter applied <b>in Postgres</b>, not in the model — saves tokens, stays grounded",
                duration_ms=0,
            )

        filtered = [
            c for c in candidates
            if (not allowed) or c["roast_level"] in allowed
        ]

        # budget filter
        if intent["budget_cents"]:
            filtered = [c for c in filtered if c["price_cents"] <= intent["budget_cents"]]

        # dedup while preserving order, pick up to 3
        seen = set()
        picks: list[dict] = []
        for c in filtered:
            if c["id"] in seen:
                continue
            seen.add(c["id"])
            picks.append(c)
            if len(picks) >= 3:
                break

        # inventory check via "tool" — one SELECT, audited
        if picks:
            bean_ids = [p["id"] for p in picks]
            sql = """
SELECT id, name, in_stock
  FROM beans
 WHERE id = ANY($1);""".strip()

            t0 = time.perf_counter()
            with conn() as c, c.cursor() as cur:
                cur.execute(sql.replace("$1", "%s"), (bean_ids,))
                inv = {r[0]: r[2] for r in cur.fetchall()}
            dur = int((time.perf_counter() - t0) * 1000)

            audit_id = log_tool_call(
                session_id=ctx.session_id,
                tool="check_inventory",
                caller="roast_master",
                args={"bean_ids": bean_ids},
                result={"stock": inv},
                latency_ms=dur,
            )

            # sync picks with live stock + drop zeros
            picks = [p for p in picks if inv.get(p["id"], 0) > 0]
            for p in picks:
                p["in_stock"] = inv[p["id"]]

            ctx.emit_panel(
                agent="roast_master",
                tag="TOOL · CHECK_INVENTORY",
                title="check_inventory(bean_ids)",
                sql=sql,
                columns=["id", "name", "in_stock"],
                rows=[[p["id"], p["name"], str(p["in_stock"])] for p in picks],
                meta=f"{len(picks)} in stock · audit entry <b>{audit_id}</b>",
                duration_ms=dur,
            )

        return picks


# =======================================================================
# Public entry point for FastAPI
# =======================================================================
def ensure_session(session_id: str | None, customer_id: str) -> str:
    """Create-or-load an agent session. Returns a uuid string."""
    with conn() as c, c.cursor() as cur:
        if session_id:
            cur.execute("SELECT id FROM agent_sessions WHERE id=%s", (session_id,))
            r = cur.fetchone()
            if r:
                return str(r[0])
        cur.execute(
            "INSERT INTO agent_sessions (customer_id) VALUES (%s) RETURNING id",
            (customer_id,),
        )
        new_id = cur.fetchone()[0]
        c.commit()
    return str(new_id)


def run_query(customer_id: str, query: str, session_id: str | None = None) -> dict:
    sid = ensure_session(session_id, customer_id)

    # record the user message (episodic memory)
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO agent_messages (session_id, role, content) VALUES (%s,'user',%s)",
            (sid, json.dumps({"text": query})),
        )
        c.commit()

    ctx = AgentContext(session_id=sid, customer_id=customer_id, query=query)
    CoordinatorAgent().handle(ctx)

    # record the agent message too
    with conn() as c, c.cursor() as cur:
        final = next((e for e in ctx.events if e["type"] == "response"), None)
        if final:
            cur.execute(
                "INSERT INTO agent_messages (session_id, role, agent, content) VALUES (%s,'agent','coordinator',%s)",
                (sid, json.dumps({"text": final["text"], "citations": final["citations"]})),
            )
            c.commit()

    return {"session_id": sid, "events": ctx.events}
