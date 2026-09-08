#!/usr/bin/env bash
# Launch the AWS Labs PostgreSQL MCP server from project-local Aurora settings.

set -euo pipefail

cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . .env
  set +a
fi

command -v uvx >/dev/null 2>&1 || {
  echo "error: uvx is required (install uv first)" >&2
  exit 1
}

: "${AURORA_CLUSTER_ARN:?AURORA_CLUSTER_ARN must be set in .env}"
: "${AURORA_SECRET_ARN:?AURORA_SECRET_ARN must be set in .env}"

# postgres-mcp-server 1.0.2 still uses the MCP Python SDK 1.x FastMCP API.
# Without this constraint uvx can resolve MCP 2.x, which renamed that API and
# makes the server fail during import before it can negotiate stdio.
export FASTMCP_LOG_LEVEL="${FASTMCP_LOG_LEVEL:-ERROR}"

exec uvx \
  --from awslabs.postgres-mcp-server==1.0.2 \
  --with 'mcp<2' \
  awslabs.postgres-mcp-server \
  --resource_arn "$AURORA_CLUSTER_ARN" \
  --secret_arn "$AURORA_SECRET_ARN" \
  --database "${AURORA_DATABASE:-coffee}" \
  --region "${AWS_REGION:-us-east-1}" \
  --readonly true
