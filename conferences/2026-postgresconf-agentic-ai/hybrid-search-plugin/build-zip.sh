#!/usr/bin/env bash
# Package the skill folder for claude.ai upload or any tool that reads SKILL.md folders.
# The zip contains one top-level folder, postgres-hybrid-search/, with SKILL.md inside.
set -euo pipefail
cd "$(dirname "$0")/skills"
out="../postgres-hybrid-search.zip"
rm -f "$out"
zip -qrX "$out" postgres-hybrid-search -x '*/__pycache__/*' '*.pyc' '*/.DS_Store'
unzip -l "$out"
