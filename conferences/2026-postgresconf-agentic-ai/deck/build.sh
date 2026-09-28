#!/usr/bin/env bash
# Build deck.pdf from deck.md with the black hybrid-search theme.
# Requires: Node.js 18+ and Chrome/Chromium. Uses a pinned Marp CLI.
# Render on macOS: the theme uses the system font (SF Pro), which the PDF then embeds.
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

echo "→ rendering deck.pdf"
npx --yes @marp-team/marp-cli@4.5.1 \
  --theme theme.css \
  --html \
  --pdf \
  --pdf-outlines \
  --allow-local-files \
  --no-stdin \
  deck.md

echo "✓ deck.pdf written"
ls -lh deck.pdf
