# Backups and restores

## What gets backed up

| Data | How | Schedule |
|---|---|---|
| Postgres (every account, run, CV version metadata, chat) | `ops/backup.sh`: `pg_dump -Fc` via the compose `db` service | daily |
| CV files on disk (`CV_STORAGE_DIR`; the `graduator_cv_storage` volume in compose) | `rsync`/`rclone` of the directory | daily, same window |

Dumps are compressed custom-format files named
`graduator-<UTC timestamp>.dump`, kept for `KEEP_DAYS` (default 14)
locally. Set `OFFSITE` to copy each dump elsewhere, for example:

```
OFFSITE="rclone copy {} b2:graduator-backups" make backup
OFFSITE="aws s3 cp {} s3://graduator-backups/" make backup
```

Copy the CV volume out of compose in the same window, for example:

```
docker run --rm -v graduator_cv_storage:/src:ro -v /srv/backups/cv_storage:/dest \
  alpine sh -c "cp -a /src/. /dest/"
```

Example cron (02:00 UTC):

```
0 2 * * * cd /srv/graduator && BACKUP_DIR=/srv/backups OFFSITE="rclone copy {} b2:graduator-backups" make backup >> /var/log/graduator-backup.log 2>&1
```

## Objectives

* **RPO 24 h:** at most one day of data is lost (daily dumps). Tighten
  later with WAL archiving if beta usage demands it.
* **RTO 1 h:** restore = provision Postgres, `pg_restore` the newest
  dump, restore the CV directory, start the API (migrations run on boot).

## Verify by restoring

`make backup-verify` loads the newest dump into a throwaway database,
checks the Alembic head and core table counts, and drops it. Run it
after every schema change and at least weekly (add it to the same cron
after `make backup`).

Last verified: 2026-10-15 against a dev database (head
`022_account_exports`; users, runs, applications, CV documents restored).

## Full restore (disaster)

```
docker compose up -d db
docker compose exec -T db psql -U graduator -c "DROP DATABASE IF EXISTS graduator"
docker compose exec -T db psql -U graduator -c "CREATE DATABASE graduator"
docker compose exec -T db pg_restore -U graduator -d graduator --no-owner < backups/graduator-<stamp>.dump
docker run --rm -v graduator_cv_storage:/dest -v /srv/backups/cv_storage:/src:ro \
  alpine sh -c "cp -a /src/. /dest/"
docker compose up -d api worker webapp
```

## User exports (not backups)

Users can download their own archive from Settings → Profile → *Export
your data* (verified email required; see `api/account/export.py`). That
is portability for the person, not a recovery mechanism for ops.
