"""Account data export: one ZIP with everything an account owns.

Owned tables are discovered from the schema (every table with user_id), so
new features export automatically; secrets and derived blobs are excluded
explicitly (EXCLUDED_*). Archives are kept for EXPORT_TTL and served only via
short-lived signed links scoped to the owner.
"""

import json
import logging
import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select

from api.auth import models as auth_models
from api.core.db import Base, SessionLocal
from api.core.time import utcnow_naive

log = logging.getLogger(__name__)

FORMAT_VERSION = 1
EXPORT_TTL = timedelta(days=7)

# Credentials (push subscriptions are per-device keys) and export bookkeeping
# never leave the server.
EXCLUDED_TABLES = {
    "auth_refresh_tokens",
    "auth_email_tokens",
    "account_exports",
    "push_subscriptions",
}
# Secrets, server paths, and large derived/internal blobs.
EXCLUDED_COLUMNS = {
    "provider_configs": {"api_key"},
    "runs": {"interest_embedding"},
    "research_tasks": {"messages_json"},
    "cv_documents": {"source_path"},
}

README = """Graduator account export (format version {version})
Generated {generated} for {email}.

manifest.json      what's inside and row counts per table
account.json       your profile
data/*.json        every record you own, one JSON array per table
                   (column names as keys; timestamps are UTC ISO-8601)
files/             your profile picture and every stored CV file

Not included: your password hash, session tokens, and model-provider API
keys (re-enter keys after importing elsewhere).
"""


def storage_root() -> Path:
    from api.cv.service import storage_root as cv_root

    return cv_root()


def archive_path(user_id: str, export_id: str) -> Path:
    return storage_root() / "exports" / user_id / f"{export_id}.zip"


def owned_tables():
    return [
        t
        for t in sorted(Base.metadata.tables.values(), key=lambda t: t.name)
        if "user_id" in t.c and t.name not in EXCLUDED_TABLES
    ]


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return None
    return str(value)


async def build_archive(user_id: str, export_id: str) -> None:
    """Background job: write the ZIP and flip the row to ready/failed."""
    async with SessionLocal() as session:
        export = await session.get(_export_model(), export_id)
        try:
            user = await session.get(auth_models.User, user_id)
            path = archive_path(user_id, export_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            counts: dict[str, int] = {}
            cv_doc_ids: list[str] = []
            tmp = path.with_suffix(".part")
            with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for table in owned_tables():
                    skip = EXCLUDED_COLUMNS.get(table.name, set())
                    cols = [c for c in table.c if c.name not in skip]
                    rows = (
                        (
                            await session.execute(
                                select(*cols).where(table.c.user_id == user_id)
                            )
                        )
                        .mappings()
                        .all()
                    )
                    counts[table.name] = len(rows)
                    if table.name == "cv_documents":
                        cv_doc_ids = [r["id"] for r in rows]
                    zf.writestr(
                        f"data/{table.name}.json",
                        json.dumps(
                            [dict(r) for r in rows], default=_json_default, indent=1
                        ),
                    )
                profile = {
                    "id": user.id,
                    "email": user.email,
                    "display_name": user.display_name,
                    "email_verified_at": user.email_verified_at,
                    "created_at": user.created_at,
                }
                zf.writestr(
                    "account.json", json.dumps(profile, default=_json_default, indent=1)
                )
                avatar = (
                    await session.execute(
                        select(auth_models.User.avatar).where(
                            auth_models.User.id == user_id
                        )
                    )
                ).scalar_one_or_none()
                if avatar:
                    zf.writestr("files/avatar.webp", avatar)
                file_count = 0
                for doc_id in cv_doc_ids:
                    folder = storage_root() / "cv" / doc_id
                    for f in sorted(folder.rglob("*")) if folder.exists() else []:
                        if f.is_file():
                            zf.write(f, f"files/cv/{doc_id}/{f.relative_to(folder)}")
                            file_count += 1
                generated = utcnow_naive().isoformat()
                zf.writestr(
                    "manifest.json",
                    json.dumps(
                        {
                            "format_version": FORMAT_VERSION,
                            "generated_at": generated,
                            "account_email": user.email,
                            "tables": counts,
                            "cv_files": file_count,
                        },
                        indent=1,
                    ),
                )
                zf.writestr(
                    "README.txt",
                    README.format(
                        version=FORMAT_VERSION, generated=generated, email=user.email
                    ),
                )
            tmp.replace(path)
            export.status = "ready"
            export.size_bytes = path.stat().st_size
        except Exception as exc:
            log.exception("account export %s failed", export_id)
            export.status = "failed"
            export.error = str(exc)[:500]
        await session.commit()


def _export_model():
    from api.account.models import AccountExport

    return AccountExport


def purge_expired_files(rows) -> None:
    for row in rows:
        archive_path(row.user_id, row.id).unlink(missing_ok=True)


def exports_root() -> Path:
    return storage_root() / "exports"


def purge_user_exports(user_id: str) -> None:
    """Remove every archive (and .part file) of an account; they hold all its data."""
    if not user_id or "/" in user_id or user_id in (".", ".."):
        return
    shutil.rmtree(exports_root() / user_id, ignore_errors=True)


async def sweep_expired_exports(session, user_id: str | None = None) -> int:
    """Drop expired archives (rows + files) for one account or all. The global pass
    also removes directories whose account is gone, in case a delete raced a build.
    Returns how many were removed."""
    from api.account import models as account_models

    model = account_models.AccountExport
    query = select(model).where(model.expires_at <= utcnow_naive())
    if user_id is not None:
        query = query.where(model.user_id == user_id)
    expired = (await session.execute(query)).scalars().all()
    if expired:
        purge_expired_files(expired)
        await session.execute(delete(model).where(model.id.in_([e.id for e in expired])))
        await session.commit()
    if user_id is None:
        root = exports_root()
        owners = [p.name for p in root.iterdir() if p.is_dir()] if root.is_dir() else []
        if owners:
            alive = set(
                (
                    await session.execute(
                        select(auth_models.User.id).where(auth_models.User.id.in_(owners))
                    )
                )
                .scalars()
                .all()
            )
            for owner in owners:
                if owner not in alive:
                    purge_user_exports(owner)
    return len(expired)
