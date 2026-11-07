"""Candidate dossiers as branded PDFs."""

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import schemas as auth_schemas
from api.auth.routes import get_current_user
from api.core.db import get_session
from api.core.ratelimit import rate_limit
from api.exports import service as export_service

router = APIRouter(tags=["candidates"])


class CandidateExportRequest(BaseModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=export_service.MAX_CANDIDATES)


@router.post(
    "/candidates/export.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    dependencies=[Depends(rate_limit("export"))],
)
async def export_candidates_pdf(
    req: CandidateExportRequest,
    session: AsyncSession = Depends(get_session),
    current: auth_schemas.UserOut = Depends(get_current_user),
):
    """One candidate's dossier, or several with a cover and contents, strongest first."""
    body, name = await export_service.export_candidates(session, current.id, req.candidate_ids)
    return Response(
        content=body,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )
