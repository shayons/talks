#!/usr/bin/env bash
# Start, stop, or check the lab's own PostgreSQL 18 cluster. Never touches a global service.
# The data directory is the talk folder's ignored .local/postgres18; it listens on
# 127.0.0.1 only. scripts/setup.sh calls this, then configures extensions and databases.
#
#   ./scripts/postgres18.sh start|stop|status
set -euo pipefail

TALK_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PGDATA_DIR="$TALK_ROOT/.local/postgres18"
PGLOG="$TALK_ROOT/.local/postgres18.log"
PORT="${LAB_PGPORT:-5433}"
LOCALE="${LAB_PGLOCALE:-en_US.UTF-8}"
ACTION="${1:-start}"

case "$ACTION" in
  start|stop|status) ;;
  *) echo "Usage: $0 {start|stop|status}" >&2; exit 2 ;;
esac
case "$PORT" in
  ''|*[!0-9]*) echo "LAB_PGPORT must be a port number." >&2; exit 2 ;;
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

if [ -f "$PGDATA_DIR/PG_VERSION" ] && [ "$(cat "$PGDATA_DIR/PG_VERSION")" != "18" ]; then
  echo "Refusing to use a data directory from a different PostgreSQL major." >&2
  exit 1
fi

case "$ACTION" in
  stop) exec "$PG18_BIN/pg_ctl" -D "$PGDATA_DIR" -m fast -w stop ;;
  status) exec "$PG18_BIN/pg_ctl" -D "$PGDATA_DIR" status ;;
esac

umask 077
mkdir -p "$TALK_ROOT/.local"
if [ ! -f "$PGDATA_DIR/PG_VERSION" ]; then
  PASSWORD_FILE="$(mktemp "$TALK_ROOT/.local/initdb-password.XXXXXX")"
  trap 'rm -f "$PASSWORD_FILE"' EXIT
  # Public lab credentials (coffee/coffee), reachable from loopback only.
  printf '%s\n' coffee > "$PASSWORD_FILE"
  "$PG18_BIN/initdb" -D "$PGDATA_DIR" --username=coffee \
    --encoding=UTF8 --locale="$LOCALE" --auth-local=trust --auth-host=scram-sha-256 \
    --pwfile="$PASSWORD_FILE"
  rm -f "$PASSWORD_FILE"
  trap - EXIT
fi

if ! "$PG18_BIN/pg_ctl" -D "$PGDATA_DIR" status >/dev/null 2>&1; then
  # TCP only: no shared socket path or socket-path length limit.
  "$PG18_BIN/pg_ctl" -D "$PGDATA_DIR" -l "$PGLOG" -o "-h 127.0.0.1 -p $PORT -k ''" -w start
fi
if [ "$(sed -n '4p' "$PGDATA_DIR/postmaster.pid")" != "$PORT" ]; then
  echo "This cluster is already running on a different port; check '$0 status'." >&2
  exit 1
fi
echo "PostgreSQL 18 running on 127.0.0.1:$PORT (data: $PGDATA_DIR)"
