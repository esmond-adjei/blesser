# Backups and restores

Everything Blesser stores is in Postgres: accounts, the opportunity catalogue, applications, to-dos, scans and notifications.

`ops/backup.sh` (`make backup`) dumps it with `pg_dump -Fc` through the compose `db` service into `BACKUP_DIR` (default `./backups`), as `blesser-<UTC timestamp>.dump`, keeping `KEEP_DAYS` (default 14). Set `OFFSITE` to copy each dump elsewhere:

```
OFFSITE="rclone copy {} b2:blesser-backups" make backup
```

Example cron (02:00 UTC):

```
0 2 * * * cd /srv/blesser && BACKUP_DIR=/srv/backups make backup && make backup-verify >> /var/log/blesser-backup.log 2>&1
```

## Verify by restoring

`make backup-verify` loads the newest dump into a throwaway database, checks the Alembic head and that the core tables have rows, then drops it. Run it after every schema change and at least weekly.

## Full restore

```
docker compose up -d db
docker compose exec -T db psql -U blesser -c "DROP DATABASE IF EXISTS blesser"
docker compose exec -T db psql -U blesser -c "CREATE DATABASE blesser"
docker compose exec -T db pg_restore -U blesser -d blesser --no-owner < backups/blesser-<stamp>.dump
docker compose up -d api worker webapp
```

Calendar links are encrypted with a key derived from `AUTH_SECRET`: restore with the same secret, or everyone will need a new calendar link.
