#!/usr/bin/env bash
# Measure every dataset from a clean state: rebuild tables and indexes, tune fusion weights
# on dev questions, evaluate every arm on test questions, then write results/.
# Run after loading and embedding (py/1_load.py, py/2_embed.py, py/2b_embed_local.py).
set -euo pipefail
cd "$(dirname "$0")/.."
unset PGUSER PGHOST PGDATABASE PGPASSWORD PGPORT PGSERVICE

for dataset in ${LAB_DATASETS:-fiqa scifact nfcorpus scidocs}; do
  echo "=== $dataset $(date +%H:%M:%S)"
  export LAB_DATASET="$dataset"
  uv run python -c "
from hybrid_lab.db import connect
with connect(autocommit=True) as conn:
    conn.execute('VACUUM (FULL, ANALYZE) docs')
    conn.execute('VACUUM (FULL, ANALYZE) queries')
print('rebuilt tables and indexes')"
  uv run --extra local python py/5_tune_fusion.py || echo "no dev split: blends use 0.5"
  uv run python -c "
from hybrid_lab.arms import BY_STAGE
from hybrid_lab.db import connect, dataset, run_script
from hybrid_lab.evaluate import run_all, scoreboard, write_scoreboard_markdown
conn = connect()
run_all(conn)
write_scoreboard_markdown(scoreboard(conn), {s: a.label for s, a in BY_STAGE.items()}, dataset())
with connect(autocommit=True) as setup:
    run_script(setup, 'demo_questions.sql')"
done
uv run python py/6_summary.py
uv run python py/7_k_sweep.py
echo "=== done $(date +%H:%M:%S)"
