from datetime import UTC, datetime

from fastapi.encoders import jsonable_encoder

from api.editorial.models import AuditLog


def utc_text(value):
    return (
        (value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC))
        .isoformat()
        .replace("+00:00", "Z")
    )


async def audited(
    session, actor, action, entity_type, entity_id, before, after, request
):
    session.add(
        AuditLog(
            actor_id=actor.id,
            actor_email=actor.email,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=jsonable_encoder(before, custom_encoder={datetime: utc_text}),
            after=jsonable_encoder(after, custom_encoder={datetime: utc_text}),
            ip=request.client.host if request.client else None,
        )
    )
    await session.flush()
