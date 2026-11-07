#!/usr/bin/env bash
# Logical Postgres backup: one compressed custom-format dump per run,
# local retention, optional off-site copy. Schedule daily (cron/systemd).
#
#   ops/backup.sh                      # uses the compose `db` service
#   BACKUP_DIR=/srv/backups KEEP_DAYS=14 OFFSITE="rclone copy {} remote:graduator" ops/backup.sh
#
# CV files live on disk (CV_STORAGE_DIR); back that directory up with
# the same schedule (rsync/rclone) so restores are consistent.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
DB_SERVICE="${DB_SERVICE:-db}"
PGUSER="${POSTGRES_USER:-graduator}"
PGDB="${POSTGRES_DB:-graduator}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/graduator-$STAMP.dump"

mkdir -p "$BACKUP_DIR"
docker compose exec -T "$DB_SERVICE" pg_dump -U "$PGUSER" -d "$PGDB" -Fc --no-owner > "$OUT.part"
mv "$OUT.part" "$OUT"
echo "backup: wrote $OUT ($(du -h "$OUT" | cut -f1))"

if [[ -n "${OFFSITE:-}" ]]; then
  # OFFSITE is a command template; {} is replaced with the dump path.
  eval "${OFFSITE//\{\}/\"$OUT\"}"
  echo "backup: copied off-site"
fi

find "$BACKUP_DIR" -name 'graduator-*.dump' -mtime +"$KEEP_DAYS" -print -delete | sed 's/^/backup: pruned /'
