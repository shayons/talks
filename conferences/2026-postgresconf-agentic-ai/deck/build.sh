#!/usr/bin/env bash
# Build paper and black-background PDFs from the same deck.md.
# Requires: Node.js 18+ and Chrome/Chromium. Uses a pinned Marp CLI.
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

node build-assets.mjs

echo "→ rendering paper deck → deck.pdf"
npx --yes @marp-team/marp-cli@4.5.1 \
  --theme theme.css \
  --html \
  --pdf \
  --pdf-outlines \
  --allow-local-files \
  --no-stdin \
  deck.md

echo "✓ deck.pdf written"

echo "→ rendering black deck → deck-dark.pdf"
npx --yes @marp-team/marp-cli@4.5.1 \
  --theme-set theme.css \
  --theme theme-dark.css \
  --html \
  --pdf \
  --pdf-outlines \
  --allow-local-files \
  --no-stdin \
  --output deck-dark.pdf \
  deck.md

echo "✓ deck-dark.pdf written"
ls -lh deck.pdf deck-dark.pdf
