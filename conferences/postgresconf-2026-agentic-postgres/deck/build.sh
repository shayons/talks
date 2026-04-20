#!/usr/bin/env bash
# Build the slide deck PDF from deck.md.
# Requires: Node.js 18+ (for npx). Uses @marp-team/marp-cli on demand.
set -euo pipefail

cd "$(dirname "$0")"

# Source nvm if present so node is on PATH
if [ -s "$HOME/.nvm/nvm.sh" ]; then
  export NVM_DIR="$HOME/.nvm"
  # shellcheck disable=SC1091
  . "$NVM_DIR/nvm.sh"
fi

if ! command -v npx >/dev/null 2>&1; then
  echo "error: npx not found — install Node.js 18+ first" >&2
  exit 1
fi

echo "→ rendering deck.md → deck.pdf"
npx --yes @marp-team/marp-cli@latest \
  --theme theme.css \
  --pdf \
  --allow-local-files \
  deck.md

echo "✓ deck.pdf written"
ls -lh deck.pdf
