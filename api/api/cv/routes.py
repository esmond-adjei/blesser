"""Document routes. They keep their /cv paths: a CV was the first kind
of document, and existing clients use them."""

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.billing import service as billing
from api.core.config import settings
from api.core.db import get_session
from api.core.exceptions import BadRequestError
from api.core.ratelimit import rate_limit
from api.cv import schemas as cv_schemas
from api.cv import service as cv_service
from api.cv import suggest as cv_suggest

router = APIRouter(tags=["cv"])


def _file(data: bytes, name: str, media: str) -> Response:
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post(
    "/cv/documents",
    response_model=cv_schemas.DocumentOut,
    dependencies=[Depends(rate_limit("upload"))],
)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    kind: cv_schemas.DocumentKind = Form(default="cv"),
    folder_id: str | None = Form(default=None),
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Upload a document (.docx, .pdf, .md or .txt); a CV unless `kind` says otherwise."""
    # Bounded read: never hold more than the limit plus one byte.
    data = await file.read(settings.cv_max_upload_bytes + 1)
    if len(data) > settings.cv_max_upload_bytes:
        raise BadRequestError("File too large.")
    return await cv_service.create_from_upload(
        session, current.id, file.filename or "cv.docx", data, title, kind, folder_id or None
    )


@router.post("/cv/documents/text", response_model=cv_schemas.DocumentOut)
async def create_document_from_text(
    req: cv_schemas.DocumentCreate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Start a base document from pasted or typed Markdown, with no file."""
    return await cv_service.create_from_text(session, current.id, req)


@router.get("/cv/documents", response_model=list[cv_schemas.DocumentSummary])
async def list_documents(
    kind: cv_schemas.DocumentKind | None = Query(default=None),
    folder_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Every base document, or those of one kind or in one folder."""
    return await cv_service.list_documents(session, current.id, kind, folder_id)


@router.get("/cv/documents/{document_id}", response_model=cv_schemas.DocumentOut)
async def get_document(
    document_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await cv_service.get_document(session, current.id, document_id)


@router.put("/cv/documents/{document_id}", response_model=cv_schemas.DocumentOut)
async def update_document(
    document_id: str,
    req: cv_schemas.TextUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Save the base text or title; 409 if it changed since `base_revision`."""
    return await cv_service.update_document(session, current.id, document_id, req)


@router.patch("/cv/documents/{document_id}", response_model=cv_schemas.DocumentOut)
async def update_document_meta(
    document_id: str,
    req: cv_schemas.DocumentMeta,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Move a document to a folder (or out of one), or set its word and page limits."""
    return await cv_service.update_document_meta(session, current.id, document_id, req)


@router.get("/cv/documents/{document_id}/checks", response_model=cv_schemas.ChecksOut)
async def document_checks(
    document_id: str,
    version_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Read-only consistency checks on the base or one version."""
    return await cv_service.document_checks(session, current.id, document_id, version_id)


@router.get("/cv/folders", response_model=list[cv_schemas.FolderOut])
async def list_folders(
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await cv_service.list_folders(session, current.id)


@router.post("/cv/folders", response_model=cv_schemas.FolderOut)
async def create_folder(
    req: cv_schemas.FolderCreate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await cv_service.create_folder(session, current.id, req)


@router.put("/cv/folders/order", response_model=list[cv_schemas.FolderOut])
async def reorder_folders(
    req: cv_schemas.FolderOrder,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Reorder the folders: every folder id, in the new order."""
    return await cv_service.reorder_folders(session, current.id, req)


@router.patch("/cv/folders/{folder_id}", response_model=cv_schemas.FolderOut)
async def update_folder(
    folder_id: str,
    req: cv_schemas.FolderUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await cv_service.update_folder(session, current.id, folder_id, req)


@router.delete("/cv/folders/{folder_id}")
async def delete_folder(
    folder_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Remove a folder; its documents move to the top level."""
    return await cv_service.delete_folder(session, current.id, folder_id)


@router.delete("/cv/documents/{document_id}")
async def delete_document(
    document_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await cv_service.delete_document(session, current.id, document_id)


@router.get("/cv/documents/{document_id}/original")
async def download_original(
    document_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """The file that was uploaded, unchanged."""
    return _file(*await cv_service.original_file(session, current.id, document_id))


@router.get("/cv/documents/{document_id}/export")
async def export_document(
    document_id: str,
    format: Literal["md", "txt", "pdf", "docx"] = Query(default="pdf"),
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return _file(*await cv_service.export(session, current.id, format, document_id=document_id))


@router.post("/cv/documents/{document_id}/versions", response_model=cv_schemas.VersionOut)
async def create_version(
    document_id: str,
    req: cv_schemas.VersionCreate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """A tailored copy of the base CV; for a candidate, the existing copy unless `new` is set."""
    return await cv_service.create_version(session, current.id, document_id, req)


@router.get("/cv/versions/{version_id}", response_model=cv_schemas.VersionOut)
async def get_version(
    version_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await cv_service.get_version(session, current.id, version_id)


@router.put("/cv/versions/{version_id}", response_model=cv_schemas.VersionOut)
async def update_version(
    version_id: str,
    req: cv_schemas.TextUpdate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Save a version's text or title; 409 if it changed since `base_revision`."""
    return await cv_service.update_version(session, current.id, version_id, req)


@router.patch("/cv/versions/{version_id}", response_model=cv_schemas.VersionOut)
async def update_version_meta(
    version_id: str,
    req: cv_schemas.VersionMeta,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Set a version's own word and page limits. The text is untouched."""
    return await cv_service.update_version_meta(session, current.id, version_id, req)


@router.delete("/cv/versions/{version_id}")
async def delete_version(
    version_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await cv_service.delete_version(session, current.id, version_id)


@router.get("/cv/versions/{version_id}/base-changes", response_model=cv_schemas.BaseChanges)
async def base_changes(
    version_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """What changed in the base since this version was forked, read-only."""
    return await cv_service.get_base_changes(session, current.id, version_id)


@router.post(
    "/cv/versions/{version_id}/sync",
    response_model=cv_schemas.SyncOut,
    dependencies=[Depends(rate_limit("proposal"))],
)
async def sync_from_base(
    version_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Offer the base's changes since the fork as suggestions on this version."""
    return await cv_service.sync_from_base(session, current.id, version_id)


@router.post("/cv/versions/{version_id}/keep", response_model=cv_schemas.VersionOut)
async def keep_version(
    version_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Keep this version as it is; the base's changes so far aren't offered again."""
    return await cv_service.keep_version_as_is(session, current.id, version_id)


@router.get("/cv/versions/{version_id}/export")
async def export_version(
    version_id: str,
    format: Literal["md", "txt", "pdf", "docx"] = Query(default="pdf"),
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return _file(*await cv_service.export(session, current.id, format, version_id=version_id))


@router.post("/cv/layout", response_model=cv_schemas.LayoutOut)
async def layout(
    req: cv_schemas.LayoutIn,
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Where each page of the CV's PDF starts, as source lines; takes unsaved text."""
    return await cv_service.layout(req.markdown)


@router.get("/cv/suggestions", response_model=list[cv_schemas.SuggestionOut])
async def list_suggestions(
    document_id: str | None = Query(default=None),
    version_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    base_only: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Suggestions for one CV or version; `base_only` keeps only the base CV's own."""
    return await cv_service.list_suggestions(
        session, current.id, document_id, version_id, status, base_only
    )


@router.post(
    "/cv/documents/{document_id}/suggestions",
    response_model=list[cv_schemas.SuggestionOut],
    dependencies=[Depends(rate_limit("proposal"))],
)
async def create_suggestions(
    document_id: str,
    req: cv_schemas.SuggestionsCreate,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Store suggested changes for review; nothing in the CV changes."""
    return await cv_service.create_suggestions(session, current.id, document_id, req, "user")


@router.post(
    "/cv/documents/{document_id}/suggest",
    response_model=list[cv_schemas.SuggestionOut],
    dependencies=[Depends(rate_limit("proposal"))],
)
async def suggest_for_selection(
    document_id: str,
    req: cv_schemas.SelectionSuggest,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Suggest a rewrite of the selected passage; 409 if the saved text changed."""
    await billing.require_feature(session, current.id, "cv_editor")
    return await cv_suggest.suggest_for_selection(session, current.id, document_id, req)


@router.post(
    "/cv/suggestions/{suggestion_id}/refresh",
    response_model=list[cv_schemas.SuggestionOut],
    dependencies=[Depends(rate_limit("proposal"))],
)
async def refresh_suggestion(
    suggestion_id: str,
    req: cv_schemas.SuggestionRefresh,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """A fresh suggestion in place of a stale one; 409 when its passage is gone."""
    await billing.require_feature(session, current.id, "cv_editor")
    return await cv_suggest.refresh_suggestion(session, current.id, suggestion_id, req)


@router.post("/cv/suggestions/{suggestion_id}/accept")
async def accept_suggestion(
    suggestion_id: str,
    req: cv_schemas.SuggestionAccept,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """Apply a suggestion, optionally edited; 409 when stale or unconfirmed new terms."""
    return await cv_service.accept_suggestion(session, current.id, suggestion_id, req)


@router.post("/cv/suggestions/{suggestion_id}/reject", response_model=cv_schemas.SuggestionOut)
async def reject_suggestion(
    suggestion_id: str,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    return await cv_service.reject_suggestion(session, current.id, suggestion_id)
