import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from api.applicant_kit import cv_import, models, schemas, service
from api.applicant_kit.storage import get_storage
from api.auth.routes import get_current_user
from api.auth.schemas import UserOut
from api.core.db import get_session
from api.core.ratelimit import rate_limit


def private_response(response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"


router = APIRouter(tags=["applicant kit"], dependencies=[Depends(private_response)])
Session = Annotated[AsyncSession, Depends(get_session)]
Member = Annotated[UserOut, Depends(get_current_user)]


@router.get("/profile", response_model=schemas.ProfileOut)
async def get_profile(
    request: Request, session: Session, current: Member, reveal: bool = False
):
    extension = bool(getattr(request.state, "extension_session_id", None))
    result = await service.profile(session, current.id, reveal=reveal and not extension)
    if extension:
        result["sensitive"] = {
            "national_id": "",
            "passport_number": "",
            "passport_expiry": None,
        }
    return result


@router.put("/profile", response_model=schemas.ProfileOut)
async def put_profile(
    req: schemas.ProfileIn, session: Session, current: Member, reveal: bool = False
):
    return await service.profile(session, current.id, req, reveal)


@router.post(
    "/profile/from-cv",
    response_model=schemas.CvImportOut,
    dependencies=[Depends(rate_limit("kit_cv"))],
)
async def profile_from_cv(req: schemas.CvImportIn, session: Session, current: Member):
    """Profile fields read from one of the member's documents. Saves nothing."""
    row = await service.owned(session, models.Document, current.id, req.document_id)
    key, content_type = row.storage_key, row.content_type
    # Reading the file and asking the model take seconds; free the connection.
    await session.close()
    cv = await get_storage().read_text(key, content_type)
    fields = await cv_import.ask_model(cv)
    return {"profile": cv_import.to_profile(fields)}


@router.get("/projects", response_model=list[schemas.ProjectOut])
async def list_projects(session: Session, current: Member):
    return await service.projects(session, current.id)


@router.post("/projects", response_model=schemas.ProjectOut, status_code=201)
async def create_project(req: schemas.ProjectIn, session: Session, current: Member):
    return await service.save_project(session, current.id, req)


@router.get("/projects/{project_id}", response_model=schemas.ProjectOut)
async def get_project(project_id: str, session: Session, current: Member):
    return await service.project_out(
        session, await service.owned(session, models.Project, current.id, project_id)
    )


@router.put("/projects/{project_id}", response_model=schemas.ProjectOut)
async def put_project(
    project_id: str, req: schemas.ProjectIn, session: Session, current: Member
):
    return await service.save_project(session, current.id, req, project_id)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: str, session: Session, current: Member):
    await service.delete_project(session, current.id, project_id)


@router.get("/documents", response_model=list[schemas.DocumentOut])
async def list_documents(
    session: Session,
    current: Member,
    kind: schemas.Kind | None = None,
    project_id: str | None = Query(None, max_length=100),
):
    return await service.documents(session, current.id, kind, project_id)


@router.get("/documents/usage")
async def document_usage(session: Session, current: Member):
    return await service.usage(session, current.id)


@router.post(
    "/documents",
    response_model=schemas.DocumentOut,
    status_code=201,
    dependencies=[Depends(rate_limit("kit_upload"))],
)
async def upload_document(request: Request, session: Session, current: Member):
    async with request.form(
        max_files=1, max_fields=105, max_part_size=64 * 1024
    ) as form:
        allowed = {
            "file",
            "kind",
            "title",
            "project_ids",
            "project_ids[]",
            "is_default",
        }
        upload = form.get("file")
        if not isinstance(upload, UploadFile) or set(form) - allowed:
            raise HTTPException(422, "Supply one file and document metadata.")
        for key in ("file", "kind", "title", "is_default"):
            if len(form.getlist(key)) > 1:
                raise HTTPException(422, f"Supply {key} once.")
        metadata = {
            "kind": form.get("kind"),
            "title": form.get("title"),
            "project_ids": form.getlist("project_ids") + form.getlist("project_ids[]"),
            "is_default": form.get("is_default", "false"),
        }
        try:
            req = schemas.DocumentPatch.model_validate(metadata)
        except ValidationError as exc:
            raise HTTPException(422, json.loads(exc.json(include_input=False))) from exc
        return await service.upload_document(session, current.id, upload, req)


@router.patch("/documents/{document_id}", response_model=schemas.DocumentOut)
async def patch_document(
    document_id: str, req: schemas.DocumentPatch, session: Session, current: Member
):
    return await service.patch_document(session, current.id, document_id, req)


@router.get("/documents/{document_id}/download")
async def download_document(document_id: str, session: Session, current: Member):
    row = await service.owned(session, models.Document, current.id, document_id)
    return get_storage().download(row.storage_key, row.filename, row.content_type)


@router.get("/documents/{document_id}/preview")
async def preview_document(document_id: str, session: Session, current: Member):
    """Thumbnail (image/webp), excerpt (application/json) or 204 when none exists."""
    row = await service.owned(session, models.Document, current.id, document_id)
    key, content_type = row.storage_key, row.content_type
    # Building a preview can take seconds; don't hold a pooled connection meanwhile.
    await session.close()
    return await get_storage().preview(key, content_type)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str, session: Session, current: Member):
    await service.delete_document(session, current.id, document_id)


@router.get("/answers", response_model=list[schemas.AnswerOut])
async def list_answers(
    session: Session,
    current: Member,
    q: str | None = Query(None, max_length=500),
    project_id: str | None = Query(None, max_length=100),
):
    return await service.answers(session, current.id, q, project_id)


@router.post("/answers", response_model=schemas.AnswerOut, status_code=201)
async def create_answer(req: schemas.AnswerIn, session: Session, current: Member):
    return await service.save_answer(session, current.id, req)


@router.put("/answers/{answer_id}", response_model=schemas.AnswerOut)
async def put_answer(
    answer_id: str, req: schemas.AnswerIn, session: Session, current: Member
):
    return await service.save_answer(session, current.id, req, answer_id)


@router.delete("/answers/{answer_id}", status_code=204)
async def delete_answer(answer_id: str, session: Session, current: Member):
    await service.delete_answer(session, current.id, answer_id)
