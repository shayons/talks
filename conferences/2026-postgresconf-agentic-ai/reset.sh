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
#   - customers       — Marco / Ana / Yuki profiles
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

# Read .env if present so DATABASE_URL / PGHOST / etc. pick up automatically.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . .env
  set +a
fi

SQL="TRUNCATE approvals, tool_audit, agent_messages, agent_sessions RESTART IDENTITY;"

if [ -n "${DATABASE_URL:-}" ]; then
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "$SQL"
else
  PGPASSWORD="${PGPASSWORD:-coffee}" \
    psql -h "${PGHOST:-127.0.0.1}" \
         -U "${PGUSER:-coffee}" \
         -d "${PGDATABASE:-coffee}" \
         -v ON_ERROR_STOP=1 \
         -c "$SQL"
fi

echo "✓ demo reset — approvals, tool_audit, agent_messages, agent_sessions cleared"
