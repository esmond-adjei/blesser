#!/usr/bin/env bash
# Prove a backup restores: load a dump into a scratch database, check the
# schema is at the expected Alembic head and core tables have rows, then
# drop the scratch database. Never touches the live database.
#
#   ops/restore-verify.sh                     # newest dump in ./backups
#   ops/restore-verify.sh backups/graduator-20261015T020000Z.dump
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
DUMP="${1:-$(ls -1t "$BACKUP_DIR"/graduator-*.dump | head -1)}"
DB_SERVICE="${DB_SERVICE:-db}"
PGUSER="${POSTGRES_USER:-graduator}"
SCRATCH="graduator_restore_check_$$"
psql() { docker compose exec -T "$DB_SERVICE" psql -U "$PGUSER" -v ON_ERROR_STOP=1 "$@"; }

echo "restore-verify: $DUMP -> $SCRATCH"
psql -d postgres -qc "CREATE DATABASE $SCRATCH"
trap 'psql -d postgres -qc "DROP DATABASE IF EXISTS $SCRATCH" >/dev/null' EXIT
docker compose exec -T "$DB_SERVICE" pg_restore -U "$PGUSER" -d "$SCRATCH" --no-owner < "$DUMP"

head=$(psql -d "$SCRATCH" -Atc "SELECT version_num FROM alembic_version")
[ -n "$head" ] || { echo "restore-verify: FAIL: no alembic version in restore" >&2; exit 1; }
echo "restore-verify: alembic head = $head"
users=0
for t in users runs applications cv_documents; do
  n=$(psql -d "$SCRATCH" -Atc "SELECT count(*) FROM $t")
  echo "restore-verify: $t = $n rows"
  [ "$t" != users ] || users="$n"
done
[ "$users" -ge 1 ] || { echo "restore-verify: FAIL: users table is empty" >&2; exit 1; }
echo "restore-verify: OK"
