# Agent guide: Hybrid Search in PostgreSQL (Postgres Summit US 2026)

Talk material for a 50-minute session. `CLAUDE.md` imports this file; edit this one.

## Layout

| Path | What it is |
| --- | --- |
| `hybrid-lab/` | **The live demo.** SQL-first hybrid search on BEIR FiQA-2018, graded with NDCG@10. |
| `hybrid-lab/sql/` | Numbered SQL files shown on stage. The single source of truth for retrieval. |
| `hybrid-lab/py/` | `# %%` cells: load, embed, choose a question, evaluate. |
| `hybrid-lab/src/hybrid_lab/` | Python package: DB access, Bedrock calls, evaluation, FastAPI UI. |
| `hybrid-search-plugin/` | Claude Code plugin; the skill is in `skills/postgres-hybrid-search/`. Downloadable agent skill that applies the pattern to any table. |
| `deck/` | Marp deck (`deck.md`), both PDF themes, talking points, SQL patterns. |
| root `*.py`, `static/` | The earlier "Coffee & queries" app. Kept as a fallback; do not extend it. |

## Commands

```bash
cd hybrid-lab
./scripts/setup.sh                    # PG 18 cluster on :5433, pg_textsearch, fiqa database
uv sync                               # Python 3.12+ environment
uv run python py/1_load.py            # FiQA into PostgreSQL
uv run python py/2_embed.py           # Cohere Embed v4 on Bedrock, then indexes
uv run python py/4_evaluate.py        # every arm on 648 questions -> results/scoreboard.md
                                      # (SQL arms ~25 min; rerank arms call Bedrock 648× each)
uv run hybrid-lab                     # UI on http://127.0.0.1:8018
uv run pytest -q                      # fixture DB fiqa_test; Bedrock mocked
uv run ruff check src py tests        # zero warnings
./deck/build.sh                       # from the talk folder: both PDFs (set CHROME_PATH if
                                      # the system Chrome hangs; Playwright's Chromium works)
./hybrid-search-plugin/build-zip.sh   # rebuild the skill zip after editing the skill
```

The user's shell exports `PGUSER`, `PGPASSWORD`, `PGHOST`, `PGDATABASE`. Unset them
(`env -u PGUSER -u PGPASSWORD -u PGHOST -u PGDATABASE ...`) for `psql` or tests against
the lab cluster; the Python code always passes an explicit DSN.

## Invariants

- Arm files have a `-- == ARM QUERY ==` line. Everything below it runs byte-for-byte in
  the evaluator and the UI; keep exactly one query there (a test enforces it).
- Numbers on slides and in the README come from `runs` via `sql/10_scoreboard.sql`, never
  from estimates. Re-run `py/4_evaluate.py` after changing any arm file. On FiQA, vector
  search (54.0 NDCG@10) beats every hybrid and reranked arm; do not write copy that claims
  otherwise without a new measurement.
- Documents use Embed v4 `input_type='search_document'`; questions use `'search_query'`.
  Never mix embedding models or versions between `docs` and `queries`.
- Vector candidate lists keep `ORDER BY <distance>` ascending with a literal `LIMIT` and
  set `hnsw.ef_search` at least as large as the LIMIT.
- Functions with optional filters (`p IS NULL OR ...`) need `SET plan_cache_mode =
  force_custom_plan`, or the planner drops both indexes (measured 335 ms vs 86 ms).
- pg_textsearch lives in the ignored `.local/extensions/`, loaded through
  `extension_control_path` and `dynamic_library_path`; do not install into Homebrew.
- Never commit `.env`, `hybrid-lab/data/`, or anything under `.local/`.
- Never run the coffee app's `schema.sql` against data you want to keep: it drops tables.
