#!/usr/bin/env bash
# A project-owned PostgreSQL 18 cluster; never starts/stops a global service.
set -euo pipefail

DEMO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEMO_PGDATA="$DEMO_ROOT/.local/postgres18"
DEMO_PGPORT="${COFFEE_PG18_PORT:-5433}"
DEMO_PGLOCALE="${COFFEE_PG18_LOCALE:-en_US.UTF-8}"
DEMO_PGLOG="$DEMO_ROOT/.local/postgres18.log"
DEMO_ACTION="${1:-start}"

case "$DEMO_ACTION" in
  start|stop|status) ;;
  *) echo "Usage: $0 {start|stop|status}" >&2; exit 2 ;;
esac
case "$DEMO_PGPORT" in
  ''|*[!0-9]*) echo "COFFEE_PG18_PORT must be a port number." >&2; exit 2 ;;
esac

if [ -z "${PG18_BIN:-}" ]; then
  if command -v brew >/dev/null 2>&1; then
    PG18_BIN="$(brew --prefix postgresql@18)/bin"
  elif command -v pg_config >/dev/null 2>&1; then
    PG18_BIN="$(pg_config --bindir)"
  else
    echo "Install PostgreSQL 18 and set PG18_BIN to its bin directory." >&2
    exit 1
  fi
fi
case "$("$PG18_BIN/postgres" --version)" in
  *" 18."*) ;;
  *) echo "PG18_BIN must point to PostgreSQL 18." >&2; exit 1 ;;
esac

if [ -f "$DEMO_PGDATA/PG_VERSION" ] && [ "$(cat "$DEMO_PGDATA/PG_VERSION")" != "18" ]; then
  echo "Refusing to use a data directory from a different PostgreSQL major." >&2
  exit 1
fi

case "$DEMO_ACTION" in
  stop)
    "$PG18_BIN/pg_ctl" -D "$DEMO_PGDATA" -m fast -w stop
    exit
    ;;
  status)
    "$PG18_BIN/pg_ctl" -D "$DEMO_PGDATA" status
    exit
    ;;
esac

umask 077
mkdir -p "$DEMO_ROOT/.local"
if [ ! -f "$DEMO_PGDATA/PG_VERSION" ]; then
  DEMO_PASSWORD_FILE="$(mktemp "$DEMO_ROOT/.local/initdb-password.XXXXXX")"
  trap 'rm -f "$DEMO_PASSWORD_FILE"' EXIT
  # Public local-demo credentials, confined to loopback.
  printf '%s\n' coffee > "$DEMO_PASSWORD_FILE"
  "$PG18_BIN/initdb" -D "$DEMO_PGDATA" --username=coffee \
    --encoding=UTF8 --locale="$DEMO_PGLOCALE" --auth-local=trust --auth-host=scram-sha-256 \
    --pwfile="$DEMO_PASSWORD_FILE"
  rm -f "$DEMO_PASSWORD_FILE"
  trap - EXIT
fi

if ! "$PG18_BIN/pg_ctl" -D "$DEMO_PGDATA" status >/dev/null 2>&1; then
  # TCP only: no shared socket path or socket-path length limit.
  "$PG18_BIN/pg_ctl" -D "$DEMO_PGDATA" -l "$DEMO_PGLOG" \
    -o "-h 127.0.0.1 -p $DEMO_PGPORT -k ''" -w start
fi
if [ "$(sed -n '4p' "$DEMO_PGDATA/postmaster.pid")" != "$DEMO_PGPORT" ]; then
  echo "This cluster is already running on a different port; inspect status." >&2
  exit 1
fi

export PGPASSWORD=coffee
DEMO_DATABASE_EXISTS="$("$PG18_BIN/psql" -X -h 127.0.0.1 -p "$DEMO_PGPORT" \
  -U coffee -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname = 'coffee'")"
if [ "$DEMO_DATABASE_EXISTS" != "1" ]; then
  "$PG18_BIN/createdb" -h 127.0.0.1 -p "$DEMO_PGPORT" -U coffee \
    --template=template0 --encoding=UTF8 --locale="$DEMO_PGLOCALE" coffee
fi
"$PG18_BIN/psql" -X -h 127.0.0.1 -p "$DEMO_PGPORT" -U coffee -d coffee \
  -Atc "SELECT 'PostgreSQL ' || current_setting('server_version') || ' · coffee database ready'"
echo "Database: 127.0.0.1:$DEMO_PGPORT/coffee"
echo "Initialize an empty catalog with scripts/initialize_demo.py; existing data is preserved."
