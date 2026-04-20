"""Minimal MCP server exposing PostgreSQL to an AI assistant.

Speaks the Model Context Protocol over stdio. Three tools:

    list_tables   — schema introspection, no args
    describe      — per-table column + index detail
    run_query     — parameterized SELECT only (no DDL/DML)

This is intentionally small and dependency-free — a single stdin/stdout loop
that reads JSON-RPC frames and writes JSON-RPC responses. The point for the
session is to show that a Postgres-backed agent is trivially MCP-addressable:
the same database that holds memory/tools/audit is also the surface an
external assistant (Claude Desktop, Cursor, etc.) talks to.

Run:
    python mcp_server.py
Then point an MCP-compatible client at this process over stdio.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any

from db import conn


# ---------------------------------------------------------------------------
# Safety: SELECT-only on a strict allowlist of tables
# ---------------------------------------------------------------------------
ALLOWED_TABLES = {
    "customers", "beans", "orders",
    "agent_sessions", "agent_messages",
    "tools", "tool_audit", "approvals",
}
SELECT_RE = re.compile(r"^\s*select\b", re.IGNORECASE)
FORBIDDEN_RE = re.compile(
    r"\b(insert|update|delete|drop|truncate|alter|create|grant|revoke)\b",
    re.IGNORECASE,
)


def _safe_query(sql: str) -> tuple[bool, str]:
    if not SELECT_RE.match(sql):
        return False, "only SELECT statements are permitted"
    if FORBIDDEN_RE.search(sql):
        return False, "write/DDL keywords are forbidden"
    if ";" in sql.strip().rstrip(";"):
        return False, "multiple statements are forbidden"
    return True, "ok"


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def tool_list_tables(_args: dict) -> dict:
    sql = """
SELECT table_name,
       (SELECT reltuples::bigint FROM pg_class WHERE relname = table_name) AS est_rows
  FROM information_schema.tables
 WHERE table_schema = 'public'
 ORDER BY table_name;"""
    with conn() as c, c.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    return {"tables": [{"name": r[0], "est_rows": int(r[1] or 0)} for r in rows]}


def tool_describe(args: dict) -> dict:
    table = args.get("table", "")
    if table not in ALLOWED_TABLES:
        return {"error": f"table {table!r} not in allowlist"}
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """SELECT column_name, data_type, is_nullable
                 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position""",
            (table,),
        )
        cols = [
            {"name": r[0], "type": r[1], "nullable": r[2] == "YES"}
            for r in cur.fetchall()
        ]
        cur.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = %s",
            (table,),
        )
        idx = [{"name": r[0], "definition": r[1]} for r in cur.fetchall()]
    return {"table": table, "columns": cols, "indexes": idx}


def tool_run_query(args: dict) -> dict:
    sql = args.get("sql", "")
    params = args.get("params") or []
    ok, reason = _safe_query(sql)
    if not ok:
        return {"error": reason}
    with conn() as c, c.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in (cur.description or [])]
        rows = cur.fetchall()[:100]  # cap for safety
    return {"columns": cols, "rows": [list(map(_jsonable, r)) for r in rows]}


def _jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


TOOLS = {
    "list_tables": {
        "description": "List all public tables with approximate row counts.",
        "inputSchema": {"type": "object", "properties": {}},
        "fn": tool_list_tables,
    },
    "describe": {
        "description": "Return columns + indexes for a single table from an allowlist.",
        "inputSchema": {
            "type": "object",
            "properties": {"table": {"type": "string"}},
            "required": ["table"],
        },
        "fn": tool_describe,
    },
    "run_query": {
        "description": "Execute a parameterized SELECT against Postgres. Writes and DDL are rejected; rows capped at 100.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql":    {"type": "string"},
                "params": {"type": "array",  "items": {}},
            },
            "required": ["sql"],
        },
        "fn": tool_run_query,
    },
}


# ---------------------------------------------------------------------------
# MCP JSON-RPC loop (subset — initialize, tools/list, tools/call)
# ---------------------------------------------------------------------------
def _write(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _result(rid: Any, result: dict) -> None:
    _write({"jsonrpc": "2.0", "id": rid, "result": result})


def _error(rid: Any, code: int, message: str) -> None:
    _write({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})


def handle(msg: dict) -> None:
    method = msg.get("method")
    rid = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        _result(rid, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "coffee-postgres-mcp", "version": "1.0"},
        })
    elif method == "tools/list":
        _result(rid, {
            "tools": [
                {"name": n, "description": t["description"], "inputSchema": t["inputSchema"]}
                for n, t in TOOLS.items()
            ],
        })
    elif method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        tool = TOOLS.get(name)
        if not tool:
            _error(rid, -32601, f"unknown tool: {name}")
            return
        try:
            out = tool["fn"](args)
        except Exception as e:
            _error(rid, -32000, f"{type(e).__name__}: {e}")
            return
        _result(rid, {
            "content": [{"type": "text", "text": json.dumps(out, indent=2)}],
        })
    elif method == "notifications/initialized":
        return  # no-op notification
    else:
        _error(rid, -32601, f"unknown method: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        handle(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
