"""Documents: base documents, tailored versions, suggestions, folders, exports.

- Every write bumps the text's revision; a write based on an older revision
  answers 409 instead of overwriting newer edits.
- A suggestion applies only where its `find` occurs exactly once in the
  current text, checked right before applying; otherwise it goes stale and
  is never applied loosely. Applying one stales the pending ones it overlaps.
- Base changes reach a forked version only as suggestions the student asks for.
"""

import asyncio
import contextlib
import difflib
import hashlib
import re
import shutil
from pathlib import Path

from sqlalchemy import delete, func, select, update

from api.core.config import settings
from api.core.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    UnprocessableError,
)
from api.core.time import utcnow_naive
from api.cv import checks as cv_checks
from api.cv import claims as cv_claims
from api.cv import engine as docx_engine
from api.cv import kinds as cv_kinds
from api.cv import markdown as cv_markdown
from api.cv import models as cv_models
from api.cv import sandbox as cv_sandbox
from api.cv import schemas as cv_schemas
from api.cv import storage as cv_storage

#: Upload formats and how they become Markdown.
FORMATS = {".docx": "docx", ".pdf": "pdf", ".md": "md", ".markdown": "md", ".txt": "txt"}

_MEDIA_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "md": "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
}


def storage_root() -> Path:
    return Path(settings.cv_storage_dir)


def _base_updated(v: cv_models.CvTailoredVersion, base_text: str | None) -> bool:
    """Whether the base's text changed since `v` was forked from it."""
    return (
        base_text is not None
        and v.forked_from_markdown is not None
        and v.forked_from_markdown != base_text
    )


def _version_summary(v: cv_models.CvTailoredVersion, base_text: str | None = None) -> dict:
    return {
        "id": v.id,
        "document_id": v.document_id,
        "name": v.name,
        "candidate_id": v.candidate_id,
        "professor_id": v.professor_id,
        "application_id": v.application_id,
        "target_label": v.target_label,
        "revision": v.revision,
        "forked_from_revision": v.forked_from_revision,
        "base_updated": _base_updated(v, base_text),
        "word_limit": v.word_limit,
        "page_limit": v.page_limit,
        "created_at": v.created_at,
        "updated_at": v.updated_at,
    }


def _document_summary(doc: cv_models.CvDocument, version_count: int = 0) -> dict:
    return {
        "id": doc.id,
        "title": doc.title,
        "kind": doc.kind or "cv",
        "folder_id": doc.folder_id,
        "word_limit": doc.word_limit,
        "page_limit": doc.page_limit,
        "format": doc.format,
        "size_bytes": doc.size_bytes or 0,
        "has_original": bool(doc.source_path),
        "revision": doc.revision,
        "version_count": version_count,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


def locate(text: str, find: str) -> tuple[int, int] | None:
    """Where `find` occurs exactly once in `text`, as (start, end); None
    for no match or several. Exact: this decides whether a suggestion can
    be applied, and a suggestion is never applied loosely."""
    if not find or text.count(find) != 1:
        return None
    start = text.index(find)
    return start, start + len(find)


def anchor(text: str, find: str) -> str | None:
    """The exact text a new suggestion's quote stands for: `find` itself
    when it occurs once, else the one passage that matches it up to
    whitespace (a quoted line is often reflowed). None when the quote
    isn't in the text once. Only used when a suggestion is stored: from
    then on its `find` is exact."""
    if not find:
        return None
    count = text.count(find)
    if count == 1:
        return find
    if count > 1:
        return None
    words = find.split()
    if not words:
        return None
    pattern = re.compile(r"\s+".join(re.escape(w) for w in words))
    matches = list(pattern.finditer(text))
    if len(matches) == 1:
        return matches[0].group(0)
    return None


def _suggestion_out(s: cv_models.CvSuggestion, current_text: str | None) -> dict:
    return {
        "id": s.id,
        "document_id": s.document_id,
        "version_id": s.version_id,
        "find": s.find,
        "replace": s.replace,
        "rationale": s.rationale,
        "claim_check": s.claim_check or {},
        "limit_check": s.limit_check,
        "status": s.status,
        "applicable": s.status == "pending"
        and current_text is not None
        and locate(current_text, s.find) is not None,
        "superseded_by": s.superseded_by,
        "created_by": s.created_by,
        "created_at": s.created_at,
        "resolved_at": s.resolved_at,
    }


async def _owned(session, model, row_id: str, user_id: str, what: str):
    row = (
        await session.execute(select(model).where(model.id == row_id, model.user_id == user_id))
    ).scalars().first()
    if row is None:
        raise NotFoundError(f"{what} not found")
    return row


async def get_document_or_404(session, document_id: str, user_id: str) -> cv_models.CvDocument:
    return await _owned(session, cv_models.CvDocument, document_id, user_id, "Document")


async def get_version_or_404(session, version_id: str, user_id: str) -> cv_models.CvTailoredVersion:
    return await _owned(session, cv_models.CvTailoredVersion, version_id, user_id, "Version")


async def get_folder_or_404(session, folder_id: str, user_id: str) -> cv_models.DocumentFolder:
    return await _owned(session, cv_models.DocumentFolder, folder_id, user_id, "Folder")


async def get_suggestion_or_404(session, suggestion_id: str, user_id: str) -> cv_models.CvSuggestion:
    return await _owned(session, cv_models.CvSuggestion, suggestion_id, user_id, "Suggestion")


async def _versions_of(session, document_id: str, user_id: str) -> list[cv_models.CvTailoredVersion]:
    rows = await session.execute(
        select(cv_models.CvTailoredVersion)
        .where(
            cv_models.CvTailoredVersion.document_id == document_id,
            cv_models.CvTailoredVersion.user_id == user_id,
        )
        .order_by(cv_models.CvTailoredVersion.updated_at.desc())
    )
    return list(rows.scalars().all())


async def list_documents(
    session, user_id: str, kind: str | None = None, folder_id: str | None = None
) -> list[dict]:
    """The student's base documents, newest edit first, each with its
    tailored versions; optionally of one kind or in one folder."""
    query = select(cv_models.CvDocument).where(cv_models.CvDocument.user_id == user_id)
    if kind:
        query = query.where(cv_models.CvDocument.kind == kind)
    if folder_id:
        query = query.where(cv_models.CvDocument.folder_id == folder_id)
    docs = (
        await session.execute(query.order_by(cv_models.CvDocument.updated_at.desc()))
    ).scalars().all()
    versions: dict[str, list[dict]] = {}
    texts = {d.id: d.markdown or "" for d in docs}
    rows = await session.execute(
        select(cv_models.CvTailoredVersion)
        .where(cv_models.CvTailoredVersion.user_id == user_id)
        .order_by(cv_models.CvTailoredVersion.updated_at.desc())
    )
    for v in rows.scalars().all():
        versions.setdefault(v.document_id, []).append(_version_summary(v, texts.get(v.document_id)))
    return [
        {**_document_summary(d, len(versions.get(d.id, []))), "versions": versions.get(d.id, [])}
        for d in docs
    ]


async def get_document(session, user_id: str, document_id: str) -> dict:
    doc = await get_document_or_404(session, document_id, user_id)
    versions = await _versions_of(session, doc.id, user_id)
    return {
        **_document_summary(doc, len(versions)),
        "markdown": doc.markdown or "",
        "versions": [_version_summary(v, doc.markdown or "") for v in versions],
    }


@contextlib.asynccontextmanager
async def _engine_errors():
    """Sandbox outcomes as API errors: bad input -> 400 with the reader's
    reason; a limit or timeout -> 422."""
    try:
        yield
    except docx_engine.CvEngineError as exc:
        raise BadRequestError(exc.message) from exc
    except cv_sandbox.SandboxLimitError as exc:
        raise UnprocessableError(exc.message) from exc


def upload_format(filename: str) -> str:
    """"docx", "pdf", "md" or "txt" from a file name, else 400."""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in FORMATS:
        raise BadRequestError("Upload a .docx, .pdf, .md or .txt file.")
    return FORMATS[suffix]


async def markdown_from_upload(fmt: str, filename: str, data: bytes) -> str:
    """The base CV text for one upload. DOCX and PDF are parsed in the
    sandbox; Markdown and plain text are read as UTF-8."""
    if not data:
        raise BadRequestError("Empty file.")
    async with _engine_errors():
        if fmt == "docx":
            ir = await cv_sandbox.extract_docx(data, filename)
            text = cv_markdown.units_to_markdown(ir.units)
        elif fmt == "pdf":
            text = cv_markdown.pdf_text_to_markdown(await cv_sandbox.extract_pdf(data))
        else:
            text = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
    if not text.strip():
        raise BadRequestError("No text could be read from this file.")
    if len(text) > cv_schemas.MAX_MARKDOWN_CHARS:
        raise BadRequestError(
            f"This CV is longer than {cv_schemas.MAX_MARKDOWN_CHARS} characters once read."
        )
    return text


async def _check_folder(session, user_id: str, folder_id: str | None) -> None:
    if folder_id:
        await get_folder_or_404(session, folder_id, user_id)


async def create_from_upload(
    session,
    user_id: str,
    filename: str,
    data: bytes,
    title: str | None,
    kind: str = "cv",
    folder_id: str | None = None,
) -> dict:
    fmt = upload_format(filename)
    await _check_folder(session, user_id, folder_id)
    text = await markdown_from_upload(fmt, filename, data)
    doc = cv_models.CvDocument(
        user_id=user_id,
        title=(title or Path(filename).stem or cv_kinds.DEFAULT_TITLES[kind])[:200],
        kind=kind,
        folder_id=folder_id,
        format=fmt,
        status="ready",
        original_sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        markdown=text,
        revision=1,
    )
    session.add(doc)
    await session.flush()  # assign doc.id for the storage path
    ext = Path(filename).suffix.lower().lstrip(".")
    path = cv_storage.original_path(storage_root(), doc.id, ext)
    cv_storage.write_bytes(path, data)
    doc.source_path = str(path.relative_to(storage_root()))
    await session.commit()
    return await get_document(session, user_id, doc.id)


async def create_from_text(session, user_id: str, body: cv_schemas.DocumentCreate) -> dict:
    await _check_folder(session, user_id, body.folder_id)
    doc = cv_models.CvDocument(
        user_id=user_id,
        title=body.title,
        kind=body.kind,
        folder_id=body.folder_id,
        format="md",
        status="ready",
        markdown=body.markdown,
        revision=1,
    )
    session.add(doc)
    await session.commit()
    return await get_document(session, user_id, doc.id)


async def _save_text(session, model, row, base_revision: int, values: dict) -> None:
    """Compare-and-set on the revision: write only when nobody saved since
    the text was loaded, else 409 with the current revision."""
    if not values:
        return
    result = await session.execute(
        update(model)
        .where(model.id == row.id, model.revision == base_revision)
        .values(**values, revision=base_revision + 1, updated_at=utcnow_naive())
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        await session.rollback()
        await session.refresh(row)
        raise ConflictError(
            "This was changed since you opened it. Reload to see the latest text.",
            {"reason": "revision", "revision": row.revision},
        )
    await session.commit()
    await session.refresh(row)


def _text_values(body: cv_schemas.TextUpdate, title_field: str, title_max: int) -> dict:
    values: dict = {}
    if body.markdown is not None:
        values["markdown"] = body.markdown
    if body.title:
        values[title_field] = body.title[:title_max]
    return values


async def update_document(
    session, user_id: str, document_id: str, body: cv_schemas.TextUpdate
) -> dict:
    doc = await get_document_or_404(session, document_id, user_id)
    await _save_text(
        session, cv_models.CvDocument, doc, body.base_revision, _text_values(body, "title", 200)
    )
    return await get_document(session, user_id, doc.id)


async def update_document_meta(
    session, user_id: str, document_id: str, body: cv_schemas.DocumentMeta
) -> dict:
    """Move a document in or out of a folder, or set its limits. Its text
    and revision stay as they are, so an open editor isn't interrupted."""
    doc = await get_document_or_404(session, document_id, user_id)
    sent = body.model_fields_set
    if "folder_id" in sent:
        await _check_folder(session, user_id, body.folder_id)
    values = {k: getattr(body, k) for k in ("folder_id", "word_limit", "page_limit") if k in sent}
    await _set_meta(session, cv_models.CvDocument, doc, values)
    return await get_document(session, user_id, doc.id)


async def update_version_meta(
    session, user_id: str, version_id: str, body: cv_schemas.VersionMeta
) -> dict:
    """Set a version's own limits; its text and revision stay as they are."""
    v = await get_version_or_404(session, version_id, user_id)
    sent = body.model_fields_set
    values = {k: getattr(body, k) for k in ("word_limit", "page_limit") if k in sent}
    await _set_meta(session, cv_models.CvTailoredVersion, v, values)
    return await get_version(session, user_id, v.id)


async def _set_meta(session, model, row, values: dict) -> None:
    if not values:
        return
    # Not through the ORM: updated_at is when the text last changed.
    await session.execute(
        update(model)
        .where(model.id == row.id)
        .values(**values, updated_at=model.updated_at)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    await session.refresh(row)


def _folder_out(f: cv_models.DocumentFolder, count: int = 0) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "sort_order": f.sort_order,
        "document_count": count,
        "created_at": f.created_at,
        "updated_at": f.updated_at,
    }


async def list_folders(session, user_id: str) -> list[dict]:
    folders = (
        await session.execute(
            select(cv_models.DocumentFolder)
            .where(cv_models.DocumentFolder.user_id == user_id)
            .order_by(cv_models.DocumentFolder.sort_order, cv_models.DocumentFolder.created_at)
        )
    ).scalars().all()
    counts = dict(
        (
            await session.execute(
                select(cv_models.CvDocument.folder_id, func.count())
                .where(
                    cv_models.CvDocument.user_id == user_id,
                    cv_models.CvDocument.folder_id.is_not(None),
                )
                .group_by(cv_models.CvDocument.folder_id)
            )
        ).all()
    )
    return [_folder_out(f, counts.get(f.id, 0)) for f in folders]


async def create_folder(session, user_id: str, body: cv_schemas.FolderCreate) -> dict:
    last = (
        await session.execute(
            select(func.max(cv_models.DocumentFolder.sort_order)).where(
                cv_models.DocumentFolder.user_id == user_id
            )
        )
    ).scalar()
    folder = cv_models.DocumentFolder(
        user_id=user_id, name=body.name.strip()[:120], sort_order=(last or 0) + 1
    )
    session.add(folder)
    await session.commit()
    await session.refresh(folder)
    return _folder_out(folder)


async def update_folder(
    session, user_id: str, folder_id: str, body: cv_schemas.FolderUpdate
) -> dict:
    folder = await get_folder_or_404(session, folder_id, user_id)
    if body.name and body.name.strip():
        folder.name = body.name.strip()[:120]
    await session.commit()
    await session.refresh(folder)
    return (await _folders_by_id(session, user_id))[folder.id]


async def _folders_by_id(session, user_id: str) -> dict[str, dict]:
    return {f["id"]: f for f in await list_folders(session, user_id)}


async def reorder_folders(session, user_id: str, body: cv_schemas.FolderOrder) -> list[dict]:
    """Put the folders in the order given. Every folder must be named
    once, so a stale list from another tab can't drop one."""
    folders = (
        await session.execute(
            select(cv_models.DocumentFolder).where(cv_models.DocumentFolder.user_id == user_id)
        )
    ).scalars().all()
    by_id = {f.id: f for f in folders}
    if sorted(body.ids) != sorted(by_id) or len(set(body.ids)) != len(body.ids):
        raise ConflictError(
            "The folders changed since this list was loaded. Reload and try again.",
            {"reason": "folders"},
        )
    for i, fid in enumerate(body.ids):
        by_id[fid].sort_order = i + 1
    await session.commit()
    return await list_folders(session, user_id)


async def delete_folder(session, user_id: str, folder_id: str) -> dict:
    """Remove a folder. Its documents move to the top level; none is
    deleted."""
    folder = await get_folder_or_404(session, folder_id, user_id)
    await session.execute(
        update(cv_models.CvDocument)
        .where(
            cv_models.CvDocument.folder_id == folder.id,
            cv_models.CvDocument.user_id == user_id,
        )
        .values(folder_id=None, updated_at=cv_models.CvDocument.updated_at)
        .execution_options(synchronize_session=False)
    )
    await session.delete(folder)
    await session.commit()
    return {"status": "deleted"}


def purge_document_files(document_id: str) -> None:
    """Remove every stored file of one CV document."""
    shutil.rmtree(storage_root() / "cv" / document_id, ignore_errors=True)


async def delete_document(session, user_id: str, document_id: str) -> dict:
    doc = await get_document_or_404(session, document_id, user_id)
    await session.execute(
        delete(cv_models.CvSuggestion).where(
            cv_models.CvSuggestion.document_id == doc.id,
            cv_models.CvSuggestion.user_id == user_id,
        )
    )
    await session.execute(
        delete(cv_models.CvTailoredVersion).where(
            cv_models.CvTailoredVersion.document_id == doc.id,
            cv_models.CvTailoredVersion.user_id == user_id,
        )
    )
    await session.delete(doc)
    await session.commit()
    purge_document_files(doc.id)
    return {"status": "deleted"}


def _safe_name(title: str) -> str:
    name = re.sub(r"[^A-Za-z0-9 ._-]+", "", title or "").strip(" .") or "CV"
    return name[:80]


async def original_file(session, user_id: str, document_id: str) -> tuple[bytes, str, str]:
    """(bytes, file name, media type) of the uploaded file."""
    doc = await get_document_or_404(session, document_id, user_id)
    if not doc.source_path:
        raise NotFoundError("This document has no uploaded file.")
    path = storage_root() / doc.source_path
    try:
        data = cv_storage.read_bytes(path)
    except FileNotFoundError as exc:
        raise NotFoundError(
            "The uploaded file is missing from storage. The storage directory "
            "was cleaned or moved after upload."
        ) from exc
    ext = path.suffix.lstrip(".") or doc.format
    fmt = FORMATS.get(f".{ext}", ext)
    return data, f"{_safe_name(doc.title)}.{ext}", _MEDIA_TYPES.get(fmt, "application/octet-stream")


async def _professor_and_school(session, professor_id: str | None) -> tuple[str | None, str | None]:
    if not professor_id:
        return None, None
    from api.prospects import models as prospect_models

    row = (
        await session.execute(
            select(prospect_models.Professor.name, prospect_models.School.name)
            .join(
                prospect_models.Program,
                prospect_models.Program.id == prospect_models.Professor.program_id,
            )
            .join(
                prospect_models.School,
                prospect_models.School.id == prospect_models.Program.school_id,
            )
            .where(prospect_models.Professor.id == professor_id)
        )
    ).first()
    return (row[0], row[1]) if row else (None, None)


async def get_version(session, user_id: str, version_id: str) -> dict:
    v = await get_version_or_404(session, version_id, user_id)
    professor, school = await _professor_and_school(session, v.professor_id)
    base = await session.get(cv_models.CvDocument, v.document_id)
    return {
        **_version_summary(v, (base.markdown or "") if base is not None else None),
        "markdown": v.markdown or "",
        "professor_name": professor,
        "school_name": school,
        "base_word_limit": base.word_limit if base is not None else None,
        "base_page_limit": base.page_limit if base is not None else None,
    }


async def create_version(
    session, user_id: str, document_id: str, body: cv_schemas.VersionCreate
) -> dict:
    """A tailored copy of the base CV, or of `markdown` when the student
    saves a variant they edited before saving. For a candidate, the copy
    already tailored for them is returned instead, unless `new` asks for
    another."""
    doc = await get_document_or_404(session, document_id, user_id)
    noun = cv_kinds.noun(doc.kind)
    what = noun[:1].upper() + noun[1:]
    professor_id = None
    label = None
    name = body.name
    if body.candidate_id:
        from api.candidates import service as candidate_service

        candidate = await candidate_service.get_candidate_or_404(
            session, body.candidate_id, user_id
        )
        if not body.new:
            existing = (
                await session.execute(
                    select(cv_models.CvTailoredVersion)
                    .where(
                        cv_models.CvTailoredVersion.document_id == doc.id,
                        cv_models.CvTailoredVersion.user_id == user_id,
                        cv_models.CvTailoredVersion.candidate_id == body.candidate_id,
                    )
                    .order_by(cv_models.CvTailoredVersion.created_at.desc())
                )
            ).scalars().first()
            if existing is not None:
                return await get_version(session, user_id, existing.id)
        professor_id = candidate.professor_id
        professor, school = await _professor_and_school(session, professor_id)
        label = ", ".join(p for p in (professor, school) if p) or None
        name = name or (f"{what} for {professor}" if professor else None)
    if body.application_id:
        from api.applications import service as application_service

        app = await application_service.get_application_or_404(
            session, body.application_id, user_id
        )
        app_label = " ".join(p for p in (app.school, app.program) if p)
        label = label or app_label or None
        name = name or (f"{what} for {app_label}" if app_label else None)
    version = cv_models.CvTailoredVersion(
        user_id=user_id,
        document_id=doc.id,
        name=(name or f"Tailored {noun}")[:160],
        markdown=(doc.markdown or "") if body.markdown is None else body.markdown,
        revision=1,
        candidate_id=body.candidate_id,
        professor_id=professor_id,
        application_id=body.application_id,
        target_label=label,
        forked_from_revision=doc.revision,
        forked_from_markdown=doc.markdown or "",
    )
    session.add(version)
    await session.commit()
    return await get_version(session, user_id, version.id)


async def update_version(
    session, user_id: str, version_id: str, body: cv_schemas.TextUpdate
) -> dict:
    v = await get_version_or_404(session, version_id, user_id)
    await _save_text(
        session, cv_models.CvTailoredVersion, v, body.base_revision, _text_values(body, "name", 160)
    )
    return await get_version(session, user_id, v.id)


async def delete_version(session, user_id: str, version_id: str) -> dict:
    v = await get_version_or_404(session, version_id, user_id)
    await session.execute(
        delete(cv_models.CvSuggestion).where(
            cv_models.CvSuggestion.version_id == v.id,
            cv_models.CvSuggestion.user_id == user_id,
        )
    )
    await session.delete(v)
    await session.commit()
    return {"status": "deleted"}


async def _target_text(session, s: cv_models.CvSuggestion, user_id: str) -> str | None:
    model = cv_models.CvTailoredVersion if s.version_id else cv_models.CvDocument
    row = await session.get(model, s.version_id or s.document_id)
    return row.markdown if row is not None and row.user_id == user_id else None


async def claims_corpus(session, user_id: str, doc: cv_models.CvDocument) -> str:
    """The text a suggestion's words are checked against: the base CV for
    a CV; for any other kind, its own base text plus the student's CVs,
    where the facts a statement draws on are written down."""
    if (doc.kind or "cv") == "cv":
        return doc.markdown or ""
    cvs = (
        await session.execute(
            select(cv_models.CvDocument.markdown).where(
                cv_models.CvDocument.user_id == user_id,
                cv_models.CvDocument.kind == "cv",
            )
        )
    ).scalars().all()
    return "\n\n".join([doc.markdown or "", *(t or "" for t in cvs)])


async def _target_of(session, doc: cv_models.CvDocument, version_id: str | None, user_id: str):
    """(row, model) whose text a suggestion for `version_id` changes."""
    if version_id:
        version = await get_version_or_404(session, version_id, user_id)
        if version.document_id != doc.id:
            raise BadRequestError("That version belongs to another document.")
        return version, cv_models.CvTailoredVersion
    return doc, cv_models.CvDocument


async def create_suggestions(
    session,
    user_id: str,
    document_id: str,
    body: cv_schemas.SuggestionsCreate,
    created_by: str = "assistant",
) -> list[dict]:
    """Store suggested changes as pending; nothing in the text changes.
    Each `find` must quote the current text once (up to whitespace) and is
    stored as the exact text it stands for, else 400. Each is checked for
    words the student's documents never mention."""
    doc = await get_document_or_404(session, document_id, user_id)
    target, _ = await _target_of(session, doc, body.version_id, user_id)
    current = target.markdown or ""
    finds = [anchor(current, item.find) for item in body.suggestions]
    missing = [i for i, f in enumerate(finds) if f is None]
    if missing:
        raise BadRequestError(
            "Each suggestion must quote the current text exactly once.", "suggestions", missing
        )
    corpus = await claims_corpus(session, user_id, doc)
    limits = await _limit_checks(
        current, [(f, i.replace) for f, i in zip(finds, body.suggestions, strict=True)],
        *effective_limits(doc, target),
    )
    rows = []
    for item, find, limit in zip(body.suggestions, finds, limits, strict=True):
        row = cv_models.CvSuggestion(
            user_id=user_id,
            document_id=doc.id,
            version_id=body.version_id,
            find=find,
            replace=item.replace,
            rationale=item.rationale,
            claim_check=cv_claims.check_new_terms(corpus, item.replace),
            limit_check=limit,
            status="pending",
            created_by=created_by,
        )
        session.add(row)
        rows.append(row)
    await session.commit()
    return [_suggestion_out(r, current) for r in rows]


def effective_limits(doc: cv_models.CvDocument, target) -> tuple[int | None, int | None]:
    """(word_limit, page_limit) for the base or a version: a version's own,
    else its base's."""
    if isinstance(target, cv_models.CvTailoredVersion):
        return (
            target.word_limit or doc.word_limit,
            target.page_limit or doc.page_limit,
        )
    return doc.word_limit, doc.page_limit


def _apply_all(text: str, changes: list[tuple[str, str]]) -> str:
    """`text` with every change that still fits applied, in order; one
    whose quote isn't there exactly once (or overlaps an earlier one) is
    left out."""
    for find, replace in changes:
        at = locate(text, find)
        if at is not None:
            text = text[: at[0]] + replace + text[at[1] :]
    return text


async def _limit_checks(
    current: str, changes: list[tuple[str, str]], word_limit: int | None, page_limit: int | None
) -> list[dict | None]:
    """The word-budget rule: on a document with a limit, a change
    that adds words must come with a cut in the same batch that keeps the
    document within the limit, or it is flagged over the limit. Each
    change gets {"delta", "words_after", "over_limit", "offset"}: words
    and pages after the whole batch; `offset` when it would go over on
    its own and the batch's cuts make room. None without a limit."""
    if not word_limit and not page_limit:
        return [None] * len(changes)
    words_before = cv_checks.word_count(current)
    after = _apply_all(current, changes)
    words_after = cv_checks.word_count(after)
    pages_after = (await layout(after))["pages"] if page_limit else None
    over = bool(
        (word_limit and words_after > word_limit) or (page_limit and pages_after > page_limit)
    )
    out = []
    for find, replace in changes:
        delta = cv_checks.word_count(replace) - cv_checks.word_count(find)
        alone = bool(word_limit and words_before + delta > word_limit)
        out.append(
            {
                "word_limit": word_limit,
                "page_limit": page_limit,
                "delta": delta,
                "words_before": words_before,
                "words_after": words_after,
                "pages_after": pages_after,
                "over_limit": delta > 0 and over,
                "offset": delta > 0 and not over and alone,
            }
        )
    return out


async def _target_names(session, user_id: str, version) -> list[str]:
    """The faculty the student is aiming at: professors their runs found,
    the ones linked on their applications, and the version's own."""
    from api.applications.models import Application
    from api.prospects.models import Professor

    names = list(
        (await session.execute(select(Professor.name).where(Professor.user_id == user_id)))
        .scalars()
        .all()
    )
    for links in (
        await session.execute(select(Application.professors).where(Application.user_id == user_id))
    ).scalars():
        names += [p.get("name") or "" for p in links or [] if isinstance(p, dict)]
    if version is not None and version.professor_id:
        professor, _ = await _professor_and_school(session, version.professor_id)
        names.append(professor or "")
    return [n for n in names if n]


async def document_checks(
    session, user_id: str, document_id: str, version_id: str | None = None
) -> dict:
    """Read-only findings on the base or one version (api/cv/checks.py)."""
    doc = await get_document_or_404(session, document_id, user_id)
    target, model = await _target_of(session, doc, version_id, user_id)
    kind = doc.kind or "cv"
    cv_texts: list[str] = []
    targets: list[str] = []
    if kind in cv_checks.STATEMENT_KINDS:
        cv_texts = list(
            (
                await session.execute(
                    select(cv_models.CvDocument.markdown).where(
                        cv_models.CvDocument.user_id == user_id,
                        cv_models.CvDocument.kind == "cv",
                    )
                )
            )
            .scalars()
            .all()
        )
        version = target if model is cv_models.CvTailoredVersion else None
        targets = await _target_names(session, user_id, version)
    findings = cv_checks.run_checks(target.markdown or "", kind, cv_texts, targets)
    return {"findings": findings}


async def list_suggestions(
    session,
    user_id: str,
    document_id: str | None = None,
    version_id: str | None = None,
    status: str | None = None,
    base_only: bool = False,
) -> list[dict]:
    query = select(cv_models.CvSuggestion).where(cv_models.CvSuggestion.user_id == user_id)
    if document_id:
        query = query.where(cv_models.CvSuggestion.document_id == document_id)
    if version_id:
        query = query.where(cv_models.CvSuggestion.version_id == version_id)
    elif base_only:
        query = query.where(cv_models.CvSuggestion.version_id.is_(None))
    if status:
        query = query.where(cv_models.CvSuggestion.status == status)
    rows = (
        await session.execute(query.order_by(cv_models.CvSuggestion.created_at))
    ).scalars().all()
    texts: dict[tuple, str | None] = {}
    out = []
    for r in rows:
        key = (r.document_id, r.version_id)
        if key not in texts:
            texts[key] = await _target_text(session, r, user_id)
        out.append(_suggestion_out(r, texts[key]))
    return out


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Whether two spans share a character, or touch (an insertion right at
    the edge of a change moves with it)."""
    return a[0] <= b[1] and b[0] <= a[1]


async def _stale_after(
    session,
    s: cv_models.CvSuggestion,
    old_text: str,
    span: tuple[int, int],
    new_text: str,
) -> None:
    """After `s` was applied at `span`: every other pending suggestion on
    the same text that overlaps the change, or no longer quotes the new
    text exactly once, goes stale. Never re-anchored behind the student's
    back: a fresh suggestion is theirs to ask for."""
    others = (
        await session.execute(
            select(cv_models.CvSuggestion).where(
                cv_models.CvSuggestion.user_id == s.user_id,
                cv_models.CvSuggestion.document_id == s.document_id,
                cv_models.CvSuggestion.version_id.is_(None)
                if s.version_id is None
                else cv_models.CvSuggestion.version_id == s.version_id,
                cv_models.CvSuggestion.status == "pending",
                cv_models.CvSuggestion.id != s.id,
            )
        )
    ).scalars().all()
    for o in others:
        before = locate(old_text, o.find)
        if before is None:
            # It couldn't be applied before either; it goes stale when
            # someone tries, as any other.
            continue
        if _overlaps(before, span) or locate(new_text, o.find) is None:
            o.status = "stale"
            o.resolved_at = utcnow_naive()


async def accept_suggestion(
    session, user_id: str, suggestion_id: str, body: cv_schemas.SuggestionAccept
) -> dict:
    """Apply one suggestion (or the student's edit of it) to the text it
    targets. Its `find` is checked again against the current text first:
    unless it occurs there exactly once, the suggestion turns stale and
    nothing changes (409). Also 409 when it adds new terms the student
    hasn't confirmed. Pending suggestions it overlaps turn stale."""
    s = await get_suggestion_or_404(session, suggestion_id, user_id)
    if s.status != "pending":
        raise ConflictError(f"This suggestion is already {s.status}.", {"status": s.status})
    doc = await get_document_or_404(session, s.document_id, user_id)
    target, model = await _target_of(session, doc, s.version_id, user_id)
    replace = s.replace if body.replace is None else body.replace
    check = (
        s.claim_check
        if body.replace is None
        else cv_claims.check_new_terms(await claims_corpus(session, user_id, doc), replace)
    ) or {}
    text = target.markdown or ""
    span = locate(text, s.find)
    if span is None:
        s.status = "stale"
        s.resolved_at = utcnow_naive()
        await session.commit()
        raise ConflictError(
            "The text this suggestion changes has been edited, or appears more "
            "than once. Ask for a fresh suggestion.",
            {"reason": "stale"},
        )
    if not check.get("passed", True) and not body.confirm_new_terms:
        raise ConflictError(
            "This change adds words your documents don't mention. Check they're true, then confirm.",
            {"reason": "new_terms", "new_terms": check.get("new_terms", [])},
        )
    new_text = text[: span[0]] + replace + text[span[1]:]
    await _save_text(session, model, target, target.revision, {"markdown": new_text})
    s.status = "accepted"
    s.replace = replace
    s.claim_check = check
    s.resolved_at = utcnow_naive()
    await _stale_after(session, s, text, span, new_text)
    await session.commit()
    return {
        "suggestion": _suggestion_out(s, None),
        "markdown": new_text,
        "revision": target.revision,
    }


async def reject_suggestion(session, user_id: str, suggestion_id: str) -> dict:
    """Dismiss a waiting suggestion, or a stale one; the outcome is kept."""
    s = await get_suggestion_or_404(session, suggestion_id, user_id)
    if s.status not in ("pending", "stale"):
        raise ConflictError(f"This suggestion is already {s.status}.", {"status": s.status})
    s.status = "rejected"
    s.resolved_at = utcnow_naive()
    await session.commit()
    return _suggestion_out(s, None)


#: Lines of context a base change may take on to quote the version once.
_CONTEXT_LINES = 3


def _unique_change(
    old_lines: list[str], i1: int, i2: int, after: str, variant: str
) -> tuple[str, str] | None:
    """The base lines old_lines[i1:i2] becoming `after`, as a (find,
    replace) pair that quotes the variant exactly once: widened by up to
    _CONTEXT_LINES unchanged lines on each side when it needs them."""
    for extra in range(_CONTEXT_LINES + 1):
        lo, hi = max(i1 - extra, 0), min(i2 + extra, len(old_lines))
        head = "".join(old_lines[lo:i1])
        tail = "".join(old_lines[i2:hi])
        find = head + "".join(old_lines[i1:i2]) + tail
        if find.strip() and variant.count(find) == 1:
            return find, head + after + tail
        if lo == 0 and hi == len(old_lines):
            break
    return None


def base_changes(forked: str, base: str, variant: str) -> list[dict]:
    """What changed in the base between the fork (`forked`) and now
    (`base`), hunk by hunk, each as the change to make in the variant:
    {before, after, applicable, find, replace}. Not applicable when the
    variant no longer has the base's old text there (it was tailored)."""
    old = forked.splitlines(keepends=True)
    new = base.splitlines(keepends=True)
    out = []
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        before, after = "".join(old[i1:i2]), "".join(new[j1:j2])
        pair = _unique_change(old, i1, i2, after, variant)
        out.append(
            {
                "before": before,
                "after": after,
                "applicable": pair is not None,
                "find": pair[0] if pair else None,
                "replace": pair[1] if pair else None,
            }
        )
    return out


async def get_base_changes(session, user_id: str, version_id: str) -> dict:
    """The base's changes since `version_id` was forked, read-only."""
    v = await get_version_or_404(session, version_id, user_id)
    base = await get_document_or_404(session, v.document_id, user_id)
    changes = (
        base_changes(v.forked_from_markdown, base.markdown or "", v.markdown or "")
        if _base_updated(v, base.markdown or "")
        else []
    )
    return {
        "base_updated": bool(changes),
        "forked_from_revision": v.forked_from_revision,
        "base_revision": base.revision,
        "changes": [
            {"before": c["before"], "after": c["after"], "applicable": c["applicable"]}
            for c in changes
        ],
    }


async def _mark_synced(session, v: cv_models.CvTailoredVersion, base: cv_models.CvDocument) -> None:
    """Move the fork point to the base as it is now; the version's own
    text is not touched."""
    await session.execute(
        update(cv_models.CvTailoredVersion)
        .where(cv_models.CvTailoredVersion.id == v.id)
        .values(
            forked_from_revision=base.revision,
            forked_from_markdown=base.markdown or "",
            updated_at=cv_models.CvTailoredVersion.updated_at,
        )
        .execution_options(synchronize_session=False)
    )


async def sync_from_base(session, user_id: str, version_id: str) -> dict:
    """Offer the base's changes since the fork as suggestions on the
    version, for the student to apply one by one; the version's text is
    untouched. The fork point moves to the base as it is now."""
    v = await get_version_or_404(session, version_id, user_id)
    base = await get_document_or_404(session, v.document_id, user_id)
    if not _base_updated(v, base.markdown or ""):
        return {"suggestions": [], "skipped": 0}
    changes = base_changes(v.forked_from_markdown, base.markdown or "", v.markdown or "")
    ready = [c for c in changes if c["applicable"]]
    rows = []
    if ready:
        rows = await create_suggestions(
            session,
            user_id,
            base.id,
            cv_schemas.SuggestionsCreate(
                version_id=v.id,
                suggestions=[
                    cv_schemas.SuggestionIn(
                        find=c["find"], replace=c["replace"], rationale="Updated in the base"
                    )
                    for c in ready[:20]
                ],
            ),
            created_by="sync",
        )
    await _mark_synced(session, v, base)
    await session.commit()
    return {"suggestions": rows, "skipped": len(changes) - len(rows)}


async def keep_version_as_is(session, user_id: str, version_id: str) -> dict:
    """The student saw the base's changes and keeps the version as it is."""
    v = await get_version_or_404(session, version_id, user_id)
    base = await get_document_or_404(session, v.document_id, user_id)
    await _mark_synced(session, v, base)
    await session.commit()
    await session.refresh(v)
    return await get_version(session, user_id, v.id)


async def export(
    session,
    user_id: str,
    fmt: str,
    document_id: str | None = None,
    version_id: str | None = None,
) -> tuple[bytes, str, str]:
    """(bytes, file name, media type) of a CV as Markdown, plain text, PDF or Word."""
    if version_id:
        v = await get_version_or_404(session, version_id, user_id)
        text, title = v.markdown or "", v.name
    else:
        doc = await get_document_or_404(session, document_id, user_id)
        text, title = doc.markdown or "", doc.title
    name = _safe_name(title)
    if fmt == "md":
        return text.encode(), f"{name}.md", _MEDIA_TYPES["md"]
    if fmt == "txt":
        return cv_markdown.to_plain_text(text).encode(), f"{name}.txt", _MEDIA_TYPES["txt"]
    if fmt == "pdf":
        from api.cv import pdf_export

        return pdf_export.build_pdf(text, title), f"{name}.pdf", _MEDIA_TYPES["pdf"]
    if fmt == "docx":
        from api.cv import docx_export

        return docx_export.build_docx(text, title), f"{name}.docx", _MEDIA_TYPES["docx"]
    raise BadRequestError("Export as md, txt, pdf or docx.")


async def layout(markdown: str) -> dict:
    """The PDF's page starts for this text (pdf_export.layout), off the
    event loop: ReportLab lays the whole CV out."""
    from api.cv import pdf_export

    return await asyncio.to_thread(pdf_export.layout, markdown)
