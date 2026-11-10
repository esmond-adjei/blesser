from hashlib import sha256
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from api.applicant_kit.service import owned
from api.autofill import models, schemas
from api.autofill.matcher import (
    blocked,
    contains_sensitive,
    match_options,
    sensitive_field,
    within_limits,
)
from api.autofill.normalization import normalize
from api.core.exceptions import UnprocessableError


def url_host(url):
    return urlsplit(url).hostname.lower().rstrip(".")


def page_host(page):
    parsed = urlsplit(page.url)
    host = url_host(page.url)
    if page.host and page.host.lower().rstrip(".") not in {
        host,
        parsed.netloc.lower().rstrip("."),
    }:
        raise UnprocessableError("Page host must match the URL host")
    return host


def correction_key(field):
    label = normalize(field.label or field.placeholder or field.name or field.id)
    label_key = sha256(label.encode()).hexdigest() if label else ""
    return label_key, field.type.lower() or "text"


async def remember(session, user_id, req):
    label, field_type = correction_key(req.field)
    if not label:
        raise UnprocessableError("A correction needs a field label")
    wrong_field = isinstance(req.corrected, schemas.WrongField)
    data = {
        "user_id": user_id,
        "host": page_host(req.page),
        "label": req.field.label
        or req.field.placeholder
        or req.field.name
        or req.field.id,
        "label_key": label,
        "field_type": field_type,
        "descriptor": req.field.model_dump(mode="json"),
        "filled": req.filled.model_dump(mode="json"),
        "value": None if wrong_field else req.corrected.value,
        "wrong_field": wrong_field,
        "updated_at": func.clock_timestamp(),
    }
    await session.execute(
        insert(models.Correction)
        .values(**data)
        .on_conflict_do_update(
            constraint="uq_autofill_correction",
            set_={
                key: value
                for key, value in data.items()
                if key not in {"user_id", "host", "label_key", "field_type"}
            },
        )
    )
    await session.commit()


async def corrections(session, user_id, host=None):
    query = select(models.Correction).where(models.Correction.user_id == user_id)
    if host is not None:
        query = query.where(models.Correction.host == host)
    return list(
        await session.scalars(
            query.order_by(models.Correction.updated_at.desc(), models.Correction.id)
        )
    )


async def forget(session, user_id, correction_id):
    row = await owned(session, models.Correction, user_id, correction_id)
    await session.delete(row)
    await session.commit()


def apply_correction(row, field, sensitive):
    if (
        row.wrong_field
        or row.value in (None, "", [])
        or blocked(field)
        or field.type.lower() == "file"
    ):
        return None
    value = row.value
    if field.options:
        value = match_options(value, field)
        if value is None:
            return None
    elif field.type.lower() in {"checkbox", "radio"}:
        return None
    if not within_limits(value, field):
        return None
    if not sensitive_field(field) and contains_sensitive(value, sensitive):
        return None
    source = row.filled.get("source")
    return schemas.Fill(
        key=field.key,
        value=value,
        source=source
        if source in {"profile", "project", "answer", "drafted"}
        else "profile",
        rule="correction",
        note="Your correction for this site and field",
    )


async def report(session, user_id, req):
    page = req.page.model_dump(mode="json")
    page["host"] = page_host(req.page)
    session.add(
        models.FormReport(
            user_id=user_id,
            page=page,
            fields=[field.model_dump(mode="json") for field in req.fields],
            note=req.note,
        )
    )
    await session.commit()


async def reports(session, limit, offset):
    return list(
        await session.scalars(
            select(models.FormReport)
            .order_by(models.FormReport.created_at.desc(), models.FormReport.id)
            .limit(limit)
            .offset(offset)
        )
    )
