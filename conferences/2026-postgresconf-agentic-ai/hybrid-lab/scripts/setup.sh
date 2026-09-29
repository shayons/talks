#!/usr/bin/env bash
# Prepare the project's local PostgreSQL 18 cluster for the hybrid search lab.
# Safe to re-run: every step checks before it changes anything.
#
#   1. Check PostgreSQL 18 and pgvector 0.8+.
#   2. Build pg_textsearch into the ignored .local/ directory (not into Homebrew).
#   3. Point the cluster at it with PostgreSQL 18's extension_control_path and
#      dynamic_library_path, preload it, and size memory for a 57k-row lab.
#   4. Create the fiqa database with the vector and pg_textsearch extensions.
set -euo pipefail

LAB_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TALK_ROOT="$(cd "$LAB_ROOT/.." && pwd)"
LAB_PORT="${LAB_PGPORT:-5433}"
PGTS_VERSION="${PGTS_VERSION:-1.4.0}"
LAB_DB="${LAB_DB:-fiqa}"
# Ignore libpq variables from the caller's shell; every command below is explicit.
unset PGUSER PGHOST PGDATABASE PGPORT PGSERVICE
export PGPASSWORD="${LAB_PGPASSWORD:-postgres}"

if [ -z "${PG18_BIN:-}" ]; then
  PG18_BIN="$(brew --prefix postgresql@18)/bin"
fi
PG_CONFIG="$PG18_BIN/pg_config"
PSQL=("$PG18_BIN/psql" -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -p "$LAB_PORT" -U postgres)

step() { printf '\n==> %s\n' "$*"; }
fail() { printf 'error: %s\n' "$*" >&2; exit 1; }

step "Checking PostgreSQL and pgvector"
case "$("$PG18_BIN/postgres" --version)" in
  *" 18."*) "$PG18_BIN/postgres" --version ;;
  *) fail "PG18_BIN must point to PostgreSQL 18 (got: $PG18_BIN)." ;;
esac
SHAREDIR="$("$PG_CONFIG" --sharedir)"
PKGLIBDIR="$("$PG_CONFIG" --pkglibdir)"
VECTOR_VERSION="$(awk -F"'" '/default_version/ {print $2}' "$SHAREDIR/extension/vector.control" 2>/dev/null || true)"
case "$VECTOR_VERSION" in
  0.8.*) echo "pgvector $VECTOR_VERSION" ;;
  *) fail "pgvector 0.8+ is required for iterative index scans (found '${VECTOR_VERSION:-none}'). Run: brew install pgvector" ;;
esac

step "Building pg_textsearch $PGTS_VERSION into .local/extensions"
EXT_ROOT="$TALK_ROOT/.local/extensions"
PGTS_DEST="$EXT_ROOT/pg_textsearch-$PGTS_VERSION"
PGTS_SHARE="$PGTS_DEST$SHAREDIR"
PGTS_LIB="$PGTS_DEST$PKGLIBDIR"
if [ -f "$PGTS_SHARE/extension/pg_textsearch.control" ] && [ -f "$PGTS_LIB/pg_textsearch.dylib" -o -f "$PGTS_LIB/pg_textsearch.so" ]; then
  echo "Already built: $PGTS_DEST"
else
  SRC="$EXT_ROOT/src/pg_textsearch-$PGTS_VERSION"
  if [ ! -d "$SRC" ]; then
    mkdir -p "$EXT_ROOT/src"
    git clone --quiet --depth 1 --branch "v$PGTS_VERSION" \
      https://github.com/timescale/pg_textsearch.git "$SRC"
  fi
  make -C "$SRC" PG_CONFIG="$PG_CONFIG" -j"$(sysctl -n hw.ncpu 2>/dev/null || nproc)" >"$EXT_ROOT/pg_textsearch-build.log" 2>&1 \
    || fail "pg_textsearch build failed; see $EXT_ROOT/pg_textsearch-build.log"
  make -C "$SRC" PG_CONFIG="$PG_CONFIG" install DESTDIR="$PGTS_DEST" >>"$EXT_ROOT/pg_textsearch-build.log" 2>&1 \
    || fail "pg_textsearch install failed; see $EXT_ROOT/pg_textsearch-build.log"
  echo "Installed under $PGTS_DEST"
fi

step "Starting the project cluster on port $LAB_PORT"
PG18_BIN="$PG18_BIN" LAB_PGPORT="$LAB_PORT" "$LAB_ROOT/scripts/postgres18.sh" start >/dev/null
"${PSQL[@]}" -d postgres -Atc "SELECT 'running ' || current_setting('server_version')"

step "Configuring extension paths, preload, and memory"
setting() { "${PSQL[@]}" -d postgres -Atc "SELECT current_setting('$1')"; }
set_if_different() {
  local name="$1" want="$2"
  if [ "$(setting "$name")" != "$want" ]; then
    "${PSQL[@]}" -d postgres -qc "ALTER SYSTEM SET $name = '$want'"
    echo "set $name = '$want'"
    RESTART=1
  fi
}
RESTART=0
set_if_different extension_control_path "\$system:$PGTS_SHARE"
set_if_different dynamic_library_path "\$libdir:$PGTS_LIB"
PRELOAD="$(setting shared_preload_libraries)"
case ",${PRELOAD// /}," in
  *,pg_textsearch,*) ;;
  ,,) set_if_different shared_preload_libraries "pg_textsearch" ;;
  *) set_if_different shared_preload_libraries "$PRELOAD, pg_textsearch" ;;
esac
set_if_different shared_buffers "1GB"
set_if_different maintenance_work_mem "1GB"
if [ "$RESTART" = 1 ]; then
  "$PG18_BIN/pg_ctl" -D "$TALK_ROOT/.local/postgres18" -l "$TALK_ROOT/.local/postgres18.log" \
    -m fast -w restart -o "-h 127.0.0.1 -p $LAB_PORT -k ''" >/dev/null
  echo "restarted"
fi
[ "$(setting shared_preload_libraries)" != "" ] || fail "shared_preload_libraries is empty after restart."

step "Creating database $LAB_DB"
if [ "$("${PSQL[@]}" -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname = '$LAB_DB'")" != "1" ]; then
  "$PG18_BIN/createdb" -h 127.0.0.1 -p "$LAB_PORT" -U postgres --template=template0 --encoding=UTF8 "$LAB_DB"
fi
"${PSQL[@]}" -d "$LAB_DB" -qc "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_textsearch;"
"${PSQL[@]}" -d "$LAB_DB" -Atc "SELECT extname || ' ' || extversion FROM pg_extension WHERE extname IN ('vector','pg_textsearch') ORDER BY 1"
echo
echo "Ready: postgresql://postgres:postgres@127.0.0.1:$LAB_PORT/$LAB_DB"
