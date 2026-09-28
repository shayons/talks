#!/usr/bin/env bash
# The morning of the talk: start what the demo needs and check all of it, in one command.
#
#   ./scripts/preflight.sh          start the database and the UI if needed, then check
#   ./scripts/preflight.sh --open   ...and open the deck and the Vitamin D question in Chrome
#
# Checks: PostgreSQL 18 with pgvector and pg_textsearch; every dataset embedded and scored;
# every stage question answered by the UI; the rainy-day question active for VS Code;
# Bedrock reachable (a warning only: stage questions don't need it).
set -euo pipefail
cd "$(dirname "$0")/.."
unset PGUSER PGHOST PGDATABASE PGPASSWORD PGPORT PGSERVICE
UI_URL="http://127.0.0.1:8018"

step() { printf '\n==> %s\n' "$*"; }

step "Database"
mkdir -p data
if ./scripts/setup.sh >data/preflight-setup.log 2>&1; then
  echo "  ✓ $(grep -E '^pg_textsearch|^vector' data/preflight-setup.log | tr '\n' ' ')on 127.0.0.1:5433"
else
  echo "  ✗ scripts/setup.sh failed; the end of data/preflight-setup.log:"
  tail -n 15 data/preflight-setup.log
  exit 1
fi

step "UI"
if curl -sf "$UI_URL/api/datasets" >/dev/null; then
  echo "  ✓ already running at $UI_URL"
else
  nohup uv run --extra local hybrid-lab >data/ui.log 2>&1 &
  for _ in $(seq 60); do
    curl -sf "$UI_URL/api/datasets" >/dev/null && break
    sleep 0.5
  done
  if curl -sf "$UI_URL/api/datasets" >/dev/null; then
    echo "  ✓ started at $UI_URL (log: data/ui.log)"
  else
    echo "  ✗ the UI did not start; the end of data/ui.log:"
    tail -n 15 data/ui.log
    exit 1
  fi
fi

step "Checks"
uv run --extra local python -m hybrid_lab.preflight

if [ "${1:-}" = "--open" ]; then
  open -a "Google Chrome" "$(cd ../deck && pwd)/deck.html" "$UI_URL/#d=nfcorpus&q=PLAIN-307"
fi

cat <<EOF

Ready. Next:
  - Deck: open ../deck/deck.html in Chrome (f fullscreen, p presenter view)
  - VS Code: open this folder, SQLTools -> "hybrid-lab · fiqa", Cmd+E Cmd+E runs a file
  - Stage links: $UI_URL/#d=nfcorpus&q=PLAIN-307  and  $UI_URL/#d=fiqa&q=9961
EOF
