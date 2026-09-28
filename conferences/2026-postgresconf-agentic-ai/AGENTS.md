# Agent guide: Hybrid Search in PostgreSQL (Postgres Summit US 2026)

Talk material for a 50-minute session. `CLAUDE.md` imports this file; edit this one.

## Layout

| Path | What it is |
| --- | --- |
| `hybrid-lab/` | **The live demo.** SQL-first hybrid search on four BEIR datasets (FiQA main; SciFact, NFCorpus, SCIDOCS), graded with NDCG@10; one database per dataset. |
| `hybrid-lab/sql/` | Numbered SQL files shown on stage. The single source of truth for retrieval. |
| `hybrid-lab/py/` | `# %%` cells: load, embed, choose a question, evaluate. |
| `hybrid-lab/src/hybrid_lab/` | Python package: DB access, Bedrock calls, evaluation, FastAPI UI. |
| `hybrid-search-plugin/` | Claude Code plugin; the skill is in `skills/postgres-hybrid-search/`. Downloadable agent skill that applies the pattern to any table. |
| `deck/` | Marp deck (`deck.md`, black `theme.css`), `deck.html` to present, `deck.pdf`, talking points, SQL patterns. |
| `.local/` (ignored) | The PostgreSQL 18 cluster, the pg_textsearch build, backups, planning notes. |

## Commands

```bash
cd hybrid-lab
./scripts/setup.sh                    # PG 18 cluster on :5433, pg_textsearch, fiqa database
./scripts/postgres18.sh stop          # stop the cluster (start | stop | status)
uv sync --extra local                 # Python 3.12+ environment (+ fastembed)
uv run python py/1_load.py            # LAB_DATASET (default fiqa) into its database
uv run python py/2_embed.py           # Cohere Embed v4 on Bedrock, then indexes
uv run --extra local python py/2b_embed_local.py   # bge-small into embedding_local
uv run --extra local python py/5_tune_fusion.py   # blend weights, dev questions only
./scripts/evaluate_all.sh             # clean rebuild, tune, evaluate all datasets, summary, k sweep
uv run python py/7_k_sweep.py         # RRF k sensitivity from stored runs -> results/k_sweep.md
uv run python py/4_evaluate.py        # every arm on the test questions -> results/scoreboard-<dataset>.md,
                                      # then sql/demo_questions.sql (FiQA: SQL arms ~25 min;
                                      # each rerank arm calls Bedrock once per question)
uv run hybrid-lab                     # UI on http://127.0.0.1:8018
uv run pytest -q                      # fixture DB fiqa_test; Bedrock mocked
uv run ruff check src py tests        # zero warnings
./deck/build.sh                       # from the talk folder: deck.html + deck.pdf (set CHROME_PATH if
                                      # the system Chrome hangs; Playwright's Chromium works)
./hybrid-search-plugin/build-zip.sh   # rebuild the skill zip after editing the skill
```

The user's shell exports `PGUSER`, `PGPASSWORD`, `PGHOST`, `PGDATABASE`. Unset them
(`env -u PGUSER -u PGPASSWORD -u PGHOST -u PGDATABASE ...`) for `psql` or tests against
the lab cluster; the Python code always passes an explicit DSN.

## Invariants

- Arm files have a `-- == ARM QUERY ==` line. Everything below it runs byte-for-byte in
  the evaluator and the UI; keep exactly one query there (a test enforces it).
- Numbers on slides and in the README come from `runs` via `sql/10_scoreboard.sql` and
  `results/summary.md`, never from estimates. Re-run `./scripts/evaluate_all.sh` after
  changing any arm file. Only claim a hybrid win where the summary's 95% interval excludes 0.
- Fusion weights are tuned on each dataset's dev questions (`queries.split = 'dev'`) and
  stored in `fusion_settings`. Never tune on test questions.
- One column per embedding model: `embedding` (Cohere Embed v4, 1536) and `embedding_local`
  (bge-small-en-v1.5, 384). Never mix them.
- Documents use Embed v4 `input_type='search_document'`; questions use `'search_query'`.
  Never mix embedding models or versions between `docs` and `queries`.
- Vector candidate lists keep `ORDER BY <distance>` ascending with a literal `LIMIT` and
  set `hnsw.ef_search` at least as large as the LIMIT.
- Functions with optional filters (`p IS NULL OR ...`) need `SET plan_cache_mode =
  force_custom_plan`, or a generic plan replaces the HNSW scan with a sequential scan
  (measured 197 ms vs 73 ms).
- pg_textsearch lives in the ignored `.local/extensions/`, loaded through
  `extension_control_path` and `dynamic_library_path`; do not install into Homebrew.
- The deck renders with `deck/.marprc.yml`, which turns off Marp's newline-to-line-break:
  source lines reflow on the slide. Use `<br>` for a hard break. Build on macOS so the
  system font (SF Pro) renders; elsewhere it falls back to Helvetica Neue or Arial.
- Click steps are elements with `data-marpit-fragment` (Marp's HTML player reveals them in
  document order). Style them so the default state is the final one: the PDF has no player.
- Never commit `.env`, `hybrid-lab/data/`, or anything under `.local/`.
