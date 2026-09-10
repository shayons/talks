#!/usr/bin/env bash
# Reset conversation state between rehearsals.
#
# Truncates the four tables that accumulate during a demo run:
#
#   - approvals       — pending/approved order rows
#   - tool_audit      — every SQL tool call + every LLM call
#   - agent_messages  — per-turn user/agent messages
#   - agent_sessions  — one row per chat session
#
# Does NOT touch:
#
#   - beans           — knowledge base + embeddings
#   - customers       — Leo / Maya / Yuki profiles
#   - orders          — historical order rows that drive episodic memory
#   - tools           — tool registry with description_emb
#
# Safe to run as often as you want. Use this between rehearsals; reach for
# `python seed.py` only if you edited seed data or changed EMBED_MODEL.
#
# Usage:
#   ./reset.sh
#   DATABASE_URL=postgresql://... ./reset.sh

set -euo pipefail

cd "$(dirname "$0")"

# Read .env while preserving explicit command-line/shell overrides.
_override_names=(
  DEMO_MODE DATABASE_URL AWS_PROFILE AWS_REGION
  AURORA_CLUSTER_ARN AURORA_SECRET_ARN AURORA_DATABASE
  PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE
)
for _override_name in "${_override_names[@]}"; do
  if declare -p "$_override_name" >/dev/null 2>&1; then
    printf -v "_had_${_override_name}" '%s' "1"
    printf -v "_value_${_override_name}" '%s' "${!_override_name}"
  fi
done

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . .env
  set +a
fi

for _override_name in "${_override_names[@]}"; do
  _had_name="_had_${_override_name}"
  _value_name="_value_${_override_name}"
  if [ "${!_had_name:-}" = "1" ]; then
    printf -v "$_override_name" '%s' "${!_value_name}"
    export "${_override_name?}"
  fi
done

DEMO_MODE="${DEMO_MODE:-local}"
if [ "$DEMO_MODE" != "local" ] && [ "$DEMO_MODE" != "aurora" ]; then
  echo "error: DEMO_MODE must be local or aurora" >&2
  exit 2
fi

SQL="TRUNCATE approvals, tool_audit, agent_messages, agent_sessions RESTART IDENTITY;"

if [ "$DEMO_MODE" = "aurora" ]; then
  command -v aws >/dev/null 2>&1 || {
    echo "error: aws CLI is required for aurora mode" >&2
    exit 1
  }
  : "${AURORA_CLUSTER_ARN:?AURORA_CLUSTER_ARN must be set in .env for aurora mode}"
  : "${AURORA_SECRET_ARN:?AURORA_SECRET_ARN must be set in .env for aurora mode}"
  aws rds-data execute-statement \
    --resource-arn "$AURORA_CLUSTER_ARN" \
    --secret-arn "$AURORA_SECRET_ARN" \
    --database "${AURORA_DATABASE:-coffee}" \
    --region "${AWS_REGION:-us-east-1}" \
    --sql "$SQL" \
    --output text >/dev/null
elif [ -n "${DATABASE_URL:-}" ]; then
  command -v psql >/dev/null 2>&1 || {
    echo "error: psql is required for local mode" >&2
    exit 1
  }
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "$SQL"
else
  command -v psql >/dev/null 2>&1 || {
    echo "error: psql is required for local mode" >&2
    exit 1
  }
  PGPASSWORD="${PGPASSWORD:-coffee}" \
    psql -h "${PGHOST:-127.0.0.1}" \
         -p "${PGPORT:-5433}" \
         -U "${PGUSER:-coffee}" \
         -d "${PGDATABASE:-coffee}" \
         -v ON_ERROR_STOP=1 \
         -c "$SQL"
fi

echo "✓ demo reset (${DEMO_MODE}) — approvals, tool_audit, agent_messages, agent_sessions cleared"
