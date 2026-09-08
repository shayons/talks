"""Minimal MCP server exposing PostgreSQL to an AI assistant.

Speaks the Model Context Protocol over stdio. Three tools:

    list_tables   — schema introspection, no args
    describe      — per-table column + index detail
    run_query     — parameterized SELECT only (no DDL/DML)

This is intentionally small — a single stdin/stdout loop
that reads JSON-RPC frames and writes JSON-RPC responses. The point for the
session is to show that a Postgres-backed agent is trivially MCP-addressable:
the same database that holds memory/tools/audit is also the surface an
external assistant (Claude Desktop, Cursor, etc.) talks to.

Run:
    python mcp_server.py
Then point an MCP-compatible client at this process over stdio.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
from typing import Any

from pglast import ast, parse_sql
from pglast.visitors import Visitor

from db import conn, demo_mode

MAX_ROWS = 100
STATEMENT_TIMEOUT_MS = 10_000


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
    r"\b(insert|update|delete|drop|truncate|alter|create|grant|revoke|"
    r"copy|call|do|execute|prepare|deallocate|listen|notify|refresh|"
    r"vacuum|analyze|cluster|reindex|into)\b",
    re.IGNORECASE,
)
COMMENT_OR_DOLLAR_QUOTE_RE = re.compile(r"--|/\*|\*/|\$[A-Za-z_0-9]*\$")
UNSAFE_FUNCTION_RE = re.compile(
    r"\b(?:nextval|setval|pg_advisory_lock|pg_advisory_xact_lock|"
    r"pg_cancel_backend|pg_terminate_backend|pg_reload_conf|pg_read_file|"
    r"pg_read_binary_file|pg_ls_dir|pg_stat_file|lo_import|lo_export|"
    r"dblink)\s*\(",
    re.IGNORECASE,
)

# A syntax gate, not a security sandbox: connect untrusted MCP clients with
# a dedicated role and only trusted schemas in search_path. Read-only mode
# alone does not prohibit every function with external side effects.
ALLOWED_FUNCTIONS = {
    "count", "sum", "min", "max", "avg", "round", "abs", "ceil", "floor",
    "lower", "upper", "length", "char_length", "concat", "concat_ws",
    "substring", "strpos", "replace", "trim", "btrim", "to_char", "now",
    "date_trunc", "date_part", "extract", "row_number", "rank", "dense_rank",
    "jsonb_array_length", "jsonb_typeof", "jsonb_build_object", "jsonb_agg",
    "array_agg", "array_length", "cardinality", "unnest", "string_agg",
    "similarity", "word_similarity", "to_tsvector", "to_tsquery",
    "plainto_tsquery", "websearch_to_tsquery", "ts_rank", "ts_rank_cd",
}


class _ReadQueryVisitor(Visitor):
    def visit_RangeVar(self, _ancestors, node):
        if node.catalogname or (node.schemaname or "public") != "public" or node.relname not in ALLOWED_TABLES:
            raise ValueError(f"table {node.relname!r} not in allowlist")

    def visit_FuncCall(self, _ancestors, node):
        names = [part.sval for part in node.funcname]
        if len(names) > 2 or (len(names) == 2 and names[0] not in {"pg_catalog", "public"}) or names[-1] not in ALLOWED_FUNCTIONS:
            raise ValueError(f"function {'.'.join(names)!r} not in allowlist")

    def visit_SelectStmt(self, _ancestors, node):
        if node.intoClause or node.lockingClause:
            raise ValueError("locking SELECT and SELECT INTO are forbidden")

    def visit(self, _ancestors, node):
        if type(node).__name__.endswith("Stmt") and not isinstance(node, (ast.RawStmt, ast.SelectStmt)):
            raise ValueError("only SELECT statements are permitted")


def use_data_api() -> bool:
    return demo_mode() == "aurora"


def _strip_string_literals(sql: str) -> str:
    """Replace single-quoted literal contents while preserving SQL shape."""
    out: list[str] = []
    i = 0
    in_string = False
    while i < len(sql):
        char = sql[i]
        if char == "'":
            out.append(" ")
            if in_string and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append(" ")
                i += 2
                continue
            in_string = not in_string
            i += 1
            continue
        out.append(" " if in_string else char)
        i += 1
    if in_string:
        raise ValueError("unterminated SQL string literal")
    return "".join(out)


def _normalized_select(sql: str) -> tuple[str | None, str]:
    if not isinstance(sql, str):
        return None, "sql must be a string"
    sql = sql.strip()
    if not sql:
        return None, "sql is required"
    if COMMENT_OR_DOLLAR_QUOTE_RE.search(sql):
        return None, "SQL comments and dollar-quoted strings are not permitted"
    if '"' in sql:
        return None, "quoted identifiers are not supported"
    try:
        scrubbed = _strip_string_literals(sql)
    except ValueError as exc:
        return None, str(exc)
    if sql.endswith(";"):
        sql = sql[:-1].rstrip()
        scrubbed = scrubbed[:-1].rstrip()
    if ";" in scrubbed:
        return None, "multiple statements are forbidden"
    if not SELECT_RE.match(scrubbed):
        return None, "only SELECT statements are permitted"
    if FORBIDDEN_RE.search(scrubbed):
        return None, "write, DDL, and maintenance keywords are forbidden"
    if re.search(r"\bfor\s+(?:no\s+key\s+)?(?:update|share)\b", scrubbed, re.I):
        return None, "locking SELECT statements are forbidden"
    if UNSAFE_FUNCTION_RE.search(scrubbed):
        return None, "unsafe PostgreSQL functions are forbidden"
    # Parse every relation, including comma joins and nested subqueries.
    # Convert only real psycopg placeholders, never text inside SQL literals.
    parser_sql = sql
    placeholders = list(re.finditer(r"%s", scrubbed))
    for index, match in reversed(list(enumerate(placeholders, 1))):
        parser_sql = parser_sql[:match.start()] + f"${index}" + parser_sql[match.end():]
    try:
        statements = parse_sql(parser_sql)
        if len(statements) != 1 or not isinstance(statements[0].stmt, ast.SelectStmt):
            return None, "only one SELECT statement is permitted"
        _ReadQueryVisitor()(statements)
    except ValueError as exc:
        return None, str(exc)
    except Exception:
        return None, "SQL could not be parsed as a supported PostgreSQL SELECT"
    return sql, "ok"


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def tool_list_tables(_args: dict) -> dict:
    sql = """
SELECT table_name,
       (SELECT reltuples::bigint FROM pg_class WHERE relname = table_name) AS est_rows
  FROM information_schema.tables
 WHERE table_schema = 'public'
   AND table_name IN (""" + ", ".join(["%s"] * len(ALLOWED_TABLES)) + ") ORDER BY table_name;"
    result = _execute_select(sql, sorted(ALLOWED_TABLES))
    rows = result["rows"]
    return {"tables": [{"name": r[0], "est_rows": int(r[1] or 0)} for r in rows]}


def tool_describe(args: dict) -> dict:
    table = args.get("table", "")
    if table not in ALLOWED_TABLES:
        return {"error": f"table {table!r} not in allowlist"}
    column_result = _execute_select(
        """SELECT column_name, data_type, is_nullable
             FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position""",
        [table],
    )
    index_result = _execute_select(
        """SELECT indexname, indexdef
             FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = %s
            ORDER BY indexname""",
        [table],
    )
    cols = [
        {"name": r[0], "type": r[1], "nullable": r[2] == "YES"}
        for r in column_result["rows"]
    ]
    idx = [
        {"name": r[0], "definition": r[1]}
        for r in index_result["rows"]
    ]
    return {"table": table, "columns": cols, "indexes": idx}


def tool_run_query(args: dict) -> dict:
    sql = args.get("sql", "")
    params = args.get("params") or []
    if not isinstance(params, list):
        return {"error": "params must be an array"}
    normalized, reason = _normalized_select(sql)
    if normalized is None:
        return {"error": reason}
    bounded_sql = f"SELECT * FROM ({normalized}) AS mcp_query LIMIT {MAX_ROWS + 1}"
    result = _execute_select(bounded_sql, params)
    rows = result["rows"]
    truncated = len(rows) > MAX_ROWS
    return {
        "columns": result["columns"],
        "rows": [
            [_jsonable(value) for value in row]
            for row in rows[:MAX_ROWS]
        ],
        "truncated": truncated,
    }


# ---------------------------------------------------------------------------
# Query execution: direct PostgreSQL locally, RDS Data API on Aurora
# ---------------------------------------------------------------------------
def _execute_select(sql: str, params: list[Any]) -> dict:
    if use_data_api():
        return _run_query_data_api(sql, params)
    with conn() as c, c.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(
            "SELECT set_config('statement_timeout', %s, true)",
            (f"{STATEMENT_TIMEOUT_MS}ms",),
        )
        cur.execute(sql, params)
        columns = [d[0] for d in (cur.description or [])]
        rows = cur.fetchall()
    return {"columns": columns, "rows": rows}


def _data_api_client():
    import boto3

    return boto3.client("rds-data", region_name=os.getenv("AWS_REGION", "us-east-1"))


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required when DEMO_MODE=aurora")
    return value


def _to_data_api_param(name: str, value: Any) -> dict:
    if isinstance(value, (list, tuple, dict)):
        raise ValueError(
            "Aurora Data API mode does not support array or object parameters"
        )
    if value is None:
        return {"name": name, "value": {"isNull": True}}
    if isinstance(value, bool):
        return {"name": name, "value": {"booleanValue": value}}
    if isinstance(value, int):
        return {"name": name, "value": {"longValue": value}}
    if isinstance(value, float):
        return {"name": name, "value": {"doubleValue": value}}
    return {"name": name, "value": {"stringValue": str(value)}}


def _rewrite_positional_params(sql: str, params: list[Any]) -> tuple[str, list[dict]]:
    out: list[str] = []
    i = 0
    param_index = 0
    in_string = False
    while i < len(sql):
        if sql[i] == "'":
            out.append(sql[i])
            if in_string and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append(sql[i + 1])
                i += 2
                continue
            in_string = not in_string
            i += 1
            continue
        if not in_string and sql.startswith("%s", i):
            out.append(f":p{param_index}")
            param_index += 1
            i += 2
            continue
        out.append(sql[i])
        i += 1
    if in_string:
        raise ValueError("unterminated SQL string literal")
    if param_index != len(params):
        raise ValueError(
            f"expected {param_index} SQL parameters, received {len(params)}"
        )
    return (
        "".join(out),
        [_to_data_api_param(f"p{i}", value) for i, value in enumerate(params)],
    )


def _from_data_api_array(value: dict) -> list[Any]:
    for key in ("stringValues", "longValues", "doubleValues", "booleanValues"):
        if key in value:
            return list(value[key])
    if "arrayValues" in value:
        return [_from_data_api_array(item) for item in value["arrayValues"]]
    return []


def _from_data_api_field(field: dict) -> Any:
    if field.get("isNull"):
        return None
    for k in ("stringValue", "longValue", "doubleValue", "booleanValue"):
        if k in field:
            return field[k]
    if "blobValue" in field:
        return base64.b64encode(field["blobValue"]).decode("ascii")
    if "arrayValue" in field:
        return _from_data_api_array(field["arrayValue"])
    return None


def _run_query_data_api(sql: str, params: list[Any]) -> dict:
    cluster_arn = _required_env("AURORA_CLUSTER_ARN")
    secret_arn = _required_env("AURORA_SECRET_ARN")
    database = os.getenv("AURORA_DATABASE", "coffee")
    named_sql, named_params = _rewrite_positional_params(sql, params)
    client = _data_api_client()
    transaction_id = client.begin_transaction(
        resourceArn=cluster_arn,
        secretArn=secret_arn,
        database=database,
    )["transactionId"]
    try:
        client.execute_statement(
            resourceArn=cluster_arn,
            secretArn=secret_arn,
            database=database,
            transactionId=transaction_id,
            sql="SET TRANSACTION READ ONLY",
        )
        response = client.execute_statement(
            resourceArn=cluster_arn,
            secretArn=secret_arn,
            database=database,
            transactionId=transaction_id,
            sql=named_sql,
            parameters=named_params,
            includeResultMetadata=True,
        )
    finally:
        client.rollback_transaction(
            resourceArn=cluster_arn,
            secretArn=secret_arn,
            transactionId=transaction_id,
        )
    columns = [
        column.get("label") or column.get("name") or f"column_{index + 1}"
        for index, column in enumerate(response.get("columnMetadata", []))
    ]
    rows = [
        [_from_data_api_field(field) for field in row]
        for row in response.get("records", [])
    ]
    return {"columns": columns, "rows": rows}


def _jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, bytes):
        return base64.b64encode(v).decode("ascii")
    if isinstance(v, (list, tuple)):
        return [_jsonable(item) for item in v]
    if isinstance(v, dict):
        return {str(key): _jsonable(value) for key, value in v.items()}
    return str(v)


TOOLS = {
    "list_tables": {
        "description": "List allowlisted public tables with approximate row counts.",
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
