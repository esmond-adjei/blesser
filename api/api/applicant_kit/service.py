from pathlib import PurePosixPath

from sqlalchemy import delete, func, or_, select, update

from api.applicant_kit import models, schemas
from api.applicant_kit.storage import MEMBER_LIMIT_BYTES, get_storage
from api.auth.models import User
from api.autofill.normalization import normalize_question
from api.core.db import like_pattern
from api.core.exceptions import NotFoundError
from api.core.ids import new_id
from api.core.time import utcnow_naive

PROFILE_COMPLETENESS = (
    "given_name",
    "family_name",
    "email",
    "phone",
    "country_of_residence",
    "city",
    "headline",
    "short_bio",
    "education",
    "experience",
    "skills",
    "languages",
)
PROJECT_COMPLETENESS = (
    "name",
    "tagline",
    "website_url",
    "sector",
    "country",
    "problem",
    "solution",
    "target_customers",
    "business_model",
    "traction",
    "team",
    "use_of_funds",
)


def populated(value):
    if isinstance(value, dict):
        return any(
            populated(v)
            for k, v in value.items()
            if k not in {"level", "current", "is_founder"}
        )
    if isinstance(value, list):
        return any(populated(v) for v in value)
    return bool(value)


def completeness(data: dict, fields: tuple[str, ...]) -> int:
    return round(
        100 * sum(populated(data.get(field)) for field in fields) / len(fields)
    )


async def lock_member(session, user_id):
    user = await session.scalar(
        select(User).where(User.id == user_id).with_for_update()
    )
    if user is None:
        raise NotFoundError("Account not found")
    return user


async def owned(session, model, user_id, item_id):
    item = await session.scalar(
        select(model).where(model.id == item_id, model.user_id == user_id)
    )
    if item is None:
        raise NotFoundError("Not found")
    return item


def profile_out(row, reveal=False):
    sensitive = dict(row.sensitive)
    if not reveal:
        sensitive = {
            key: "*" * max(0, len(value) - 4) + value[-4:] if value else value
            for key, value in sensitive.items()
        }
    return {
        **row.data,
        "sensitive": sensitive,
        "completeness": completeness(row.data, PROFILE_COMPLETENESS),
        "updated_at": row.updated_at,
    }


async def profile(session, user_id, req=None, reveal=False):
    user = await lock_member(session, user_id)
    row = await session.get(models.Profile, user_id)
    if row is None:
        defaults = schemas.ProfileIn(email=user.email).model_dump(mode="json")
        row = models.Profile(
            user_id=user_id,
            data={k: v for k, v in defaults.items() if k != "sensitive"},
            sensitive=defaults["sensitive"],
        )
        session.add(row)
    if req is not None:
        data = req.model_dump(mode="json")
        row.sensitive = data.pop("sensitive")
        row.data = data
        row.updated_at = utcnow_naive()
    await session.commit()
    await session.refresh(row)
    return profile_out(row, reveal)


async def validate_ids(session, model, user_id, ids):
    ids = set(ids)
    if ids:
        found = set(
            await session.scalars(
                select(model.id).where(model.user_id == user_id, model.id.in_(ids))
            )
        )
        if found != ids:
            raise NotFoundError("Not found")


async def project_out(session, row):
    document_ids = list(
        await session.scalars(
            select(models.DocumentProject.document_id)
            .where(models.DocumentProject.project_id == row.id)
            .order_by(models.DocumentProject.document_id)
        )
    )
    data = {
        **row.data,
        "logo_document_id": row.logo_document_id,
        "document_ids": document_ids,
    }
    return {
        **data,
        "id": row.id,
        "completeness": completeness(data, PROJECT_COMPLETENESS),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def projects(session, user_id):
    rows = await session.scalars(
        select(models.Project)
        .where(models.Project.user_id == user_id)
        .order_by(models.Project.created_at, models.Project.id)
    )
    return [await project_out(session, row) for row in rows]


async def save_project(session, user_id, req, project_id=None):
    await lock_member(session, user_id)
    row = (
        await owned(session, models.Project, user_id, project_id)
        if project_id
        else models.Project(id=new_id(), user_id=user_id)
    )
    ids = list(req.document_ids)
    await validate_ids(
        session,
        models.Document,
        user_id,
        ids + ([req.logo_document_id] if req.logo_document_id else []),
    )
    data = req.model_dump(mode="json")
    row.logo_document_id = data.pop("logo_document_id")
    data.pop("document_ids")
    row.data = data
    row.updated_at = utcnow_naive()
    session.add(row)
    await session.flush()
    await session.execute(
        delete(models.DocumentProject).where(
            models.DocumentProject.project_id == row.id
        )
    )
    session.add_all(
        models.DocumentProject(project_id=row.id, document_id=doc_id)
        for doc_id in sorted(set(ids))
    )
    await session.commit()
    await session.refresh(row)
    return await project_out(session, row)


async def delete_project(session, user_id, project_id):
    await lock_member(session, user_id)
    row = await owned(session, models.Project, user_id, project_id)
    await session.delete(row)
    await session.commit()


async def document_out(session, row):
    project_ids = list(
        await session.scalars(
            select(models.DocumentProject.project_id)
            .where(models.DocumentProject.document_id == row.id)
            .order_by(models.DocumentProject.project_id)
        )
    )
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "kind",
            "title",
            "filename",
            "content_type",
            "size_bytes",
            "is_default",
            "created_at",
        )
    } | {"project_ids": project_ids}


async def documents(session, user_id, kind=None, project_id=None):
    query = select(models.Document).where(models.Document.user_id == user_id)
    if kind:
        query = query.where(models.Document.kind == kind)
    if project_id:
        await owned(session, models.Project, user_id, project_id)
        query = query.join(models.DocumentProject).where(
            models.DocumentProject.project_id == project_id
        )
    rows = await session.scalars(
        query.order_by(models.Document.created_at, models.Document.id)
    )
    return [await document_out(session, row) for row in rows]


async def usage(session, user_id):
    used = await session.scalar(
        select(func.coalesce(func.sum(models.Document.size_bytes), 0)).where(
            models.Document.user_id == user_id
        )
    )
    return {"used_bytes": used, "limit_bytes": MEMBER_LIMIT_BYTES}


async def clear_default(session, user_id, kind, excluding):
    await session.execute(
        update(models.Document)
        .where(
            models.Document.user_id == user_id,
            models.Document.kind == kind,
            models.Document.id != excluding,
            models.Document.is_default.is_(True),
        )
        .values(is_default=False)
    )


async def link_document(session, document_id, project_ids):
    await session.execute(
        delete(models.DocumentProject).where(
            models.DocumentProject.document_id == document_id
        )
    )
    session.add_all(
        models.DocumentProject(document_id=document_id, project_id=project_id)
        for project_id in sorted(set(project_ids))
    )


async def upload_document(session, user_id, upload, req):
    await lock_member(session, user_id)
    await validate_ids(session, models.Project, user_id, req.project_ids or [])
    budget = MEMBER_LIMIT_BYTES - (await usage(session, user_id))["used_bytes"]
    storage = get_storage()
    saved = await storage.save(user_id, upload, budget)
    try:
        row = models.Document(
            id=new_id(),
            user_id=user_id,
            kind=req.kind,
            title=req.title,
            filename=PurePosixPath(
                (upload.filename or "document").replace("\\", "/")
            ).name[:255]
            or "document",
            content_type=saved.content_type,
            size_bytes=saved.size,
            storage_key=saved.key,
            is_default=req.is_default or False,
        )
        if row.is_default:
            await clear_default(session, user_id, row.kind, row.id)
        session.add(row)
        await session.flush()
        await link_document(session, row.id, req.project_ids or [])
        await session.commit()
    except BaseException:
        await session.rollback()
        await storage.delete(saved.key)
        raise
    await session.refresh(row)
    return await document_out(session, row)


async def patch_document(session, user_id, document_id, req):
    await lock_member(session, user_id)
    row = await owned(session, models.Document, user_id, document_id)
    if req.project_ids is not None:
        await validate_ids(session, models.Project, user_id, req.project_ids)
    kind = req.kind if req.kind is not None else row.kind
    is_default = req.is_default if req.is_default is not None else row.is_default
    if is_default:
        await clear_default(session, user_id, kind, row.id)
    for key in ("title", "kind", "is_default"):
        if key in req.model_fields_set:
            setattr(row, key, getattr(req, key))
    if req.project_ids is not None:
        await link_document(session, row.id, req.project_ids)
        await session.execute(
            update(models.Project)
            .where(
                models.Project.user_id == user_id,
                models.Project.id.in_(req.project_ids),
            )
            .values(updated_at=utcnow_naive())
        )
    await session.commit()
    await session.refresh(row)
    return await document_out(session, row)


async def delete_document(session, user_id, document_id):
    await lock_member(session, user_id)
    row = await owned(session, models.Document, user_id, document_id)
    await get_storage().delete(row.storage_key)
    await session.delete(row)
    await session.commit()


def answer_out(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "question",
            "answer",
            "tags",
            "project_id",
            "word_count",
            "updated_at",
        )
    }


async def answers(session, user_id, q=None, project_id=None):
    query = select(models.Answer).where(models.Answer.user_id == user_id)
    if project_id:
        await owned(session, models.Project, user_id, project_id)
        query = query.where(models.Answer.project_id == project_id)
    if q:
        pattern = like_pattern(q)
        query = query.where(
            or_(
                models.Answer.question.ilike(pattern),
                models.Answer.answer.ilike(pattern),
            )
        )
    rows = await session.scalars(
        query.order_by(models.Answer.updated_at.desc(), models.Answer.id)
    )
    return [answer_out(row) for row in rows]


async def save_answer(session, user_id, req, answer_id=None):
    await lock_member(session, user_id)
    row = (
        await owned(session, models.Answer, user_id, answer_id)
        if answer_id
        else models.Answer(user_id=user_id)
    )
    if req.project_id:
        await owned(session, models.Project, user_id, req.project_id)
    for key, value in req.model_dump().items():
        setattr(row, key, value)
    row.word_count = len(req.answer.split())
    row.normalized_question = normalize_question(req.question)
    row.updated_at = utcnow_naive()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return answer_out(row)


async def delete_answer(session, user_id, answer_id):
    await lock_member(session, user_id)
    row = await owned(session, models.Answer, user_id, answer_id)
    await session.delete(row)
    await session.commit()
