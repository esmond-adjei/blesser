"""What the member is looking for, saved searches, notifications and their name."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from api.auth import profile as auth_profile
from api.auth import service as auth_service
from api.core.exceptions import BadRequestError
from api.matching import saved
from api.matching import service as matching
from api.matching.schemas import (
    Alerts,
    Level,
    MatchProfileIn,
    SavedSearchIn,
    SearchFilters,
    Term,
)
from api.notifications import service as notifications
from api.notifications.schemas import PreferencesIn
from api.opportunities.models import OpportunityCategory, OpportunityKind

from .base import (
    Applied,
    Proposal,
    RecordId,
    Tool,
    ToolInput,
    field_lines,
    preview,
    quoted,
    record,
)

ALERT_LABELS = {"off": "Off", "daily": "Daily", "weekly": "Weekly"}
NotificationKind = Literal[
    tuple(k for k, v in notifications.KINDS.items() if v.configurable)
]  # type: ignore[valid-type]
Channel = Literal["inbox", "push", "email"]


class MatchChanges(ToolInput):
    categories: list[OpportunityCategory] | None = Field(default=None, max_length=3)
    kinds: list[OpportunityKind] | None = Field(default=None, max_length=12)
    fields: list[Term] | None = Field(default=None, max_length=12)
    levels: list[Level] | None = Field(default=None, max_length=5)
    countries: list[Term] | None = Field(default=None, max_length=10)
    alerts: Alerts | None = None
    closing_soon: bool | None = None


class UpdateMatch(ToolInput):
    changes: MatchChanges


class SearchId(ToolInput):
    search_id: RecordId


class AddSearch(ToolInput):
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
    ]
    filters: SearchFilters
    alerts: Alerts = "daily"


class SearchChanges(ToolInput):
    name: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
        ]
        | None
    ) = None
    alerts: Alerts | None = None


class UpdateSearch(SearchId):
    changes: SearchChanges


class Notifications(ToolInput):
    unread_only: bool = False


class MarkRead(ToolInput):
    notification_id: RecordId | None = Field(
        default=None, description="Leave out to mark every notification read."
    )


class ChannelChange(ToolInput):
    kind: NotificationKind
    channel: Channel
    on: bool


class NotificationChanges(ToolInput):
    channels: list[ChannelChange] | None = Field(default=None, max_length=30)
    quiet_start: Annotated[str, StringConstraints(max_length=5)] | None = Field(
        default=None,
        description="24-hour HH:MM. An empty string turns quiet hours off.",
    )
    quiet_end: Annotated[str, StringConstraints(max_length=5)] | None = None
    timezone: Annotated[str, StringConstraints(max_length=64)] | None = None
    email_digest: bool | None = None


class UpdateNotifications(ToolInput):
    changes: NotificationChanges


class DisplayName(ToolInput):
    display_name: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=80)
    ] = Field(
        description="An empty string clears the name, so Blesser uses the email instead."
    )


def _filters_text(filters: dict) -> str:
    parts = []
    if filters.get("q"):
        parts.append(quoted(filters["q"], 60))
    for key in ("category", "kind", "country"):
        if filters.get(key):
            parts.append(str(filters[key]).replace("_", " ").capitalize())
    if filters.get("closing_within") is not None:
        parts.append(f"Closing within {filters['closing_within']} days")
    return ", ".join(parts) or "All open listings"


async def get_match_profile(session, user_id, args, registry):
    out = await matching.read(session, user_id)
    out.pop("updated_at", None)
    out["scope"] = (
        "saved is false while the values are only a suggestion from the Apply kit."
    )
    return out, None


async def propose_match(session, user_id, args):
    changes = args.changes.model_dump(
        mode="json", exclude_unset=True, exclude_none=True
    )
    if not changes:
        raise BadRequestError("Supply at least one change.")
    current = await matching.read(session, user_id)
    MatchProfileIn.model_validate(
        {k: current[k] for k in MatchProfileIn.model_fields} | changes
    )
    shown = dict(changes)
    if "alerts" in shown:
        shown["alerts"] = ALERT_LABELS[shown["alerts"]]
    return Proposal(
        "Update your feed settings?",
        {"changes": changes},
        field_lines(shown, {"closing_soon": "Closing soon email"}),
    )


async def apply_match(session, user_id, arguments):
    current = await matching.read(session, user_id)
    req = MatchProfileIn.model_validate(
        {k: current[k] for k in MatchProfileIn.model_fields} | arguments["changes"]
    )
    await matching.save(session, user_id, req.model_dump(mode="json"))
    return Applied(
        {"updated": sorted(arguments["changes"])},
        "Updated your feed settings.",
        preview("settings", "matching", "Your feed", "Settings"),
    )


async def list_saved_searches(session, user_id, args, registry):
    rows = await saved.list_for(session, user_id)
    return {
        "items": [{**record(row, ("id", "name", "filters", "alerts"))} for row in rows],
        "total": len(rows),
        "max": saved.MAX_PER_MEMBER,
    }, len(rows)


async def propose_add_search(session, user_id, args):
    filters = args.filters.model_dump(mode="json")
    SavedSearchIn.model_validate(
        {"name": args.name, "filters": filters, "alerts": args.alerts}
    )
    return Proposal(
        f"Save the search {quoted(args.name)}?",
        {"name": args.name, "filters": filters, "alerts": args.alerts},
        field_lines(
            {"filters": _filters_text(filters), "alerts": ALERT_LABELS[args.alerts]},
            {"filters": "Finds", "alerts": "Alerts"},
        ),
        "Save search",
    )


async def apply_add_search(session, user_id, arguments):
    row = await saved.create(
        session,
        user_id,
        name=arguments["name"],
        filters=arguments["filters"],
        alerts=arguments["alerts"],
    )
    return Applied(
        {"search_id": row["id"], "name": row["name"]},
        "Saved the search.",
        preview(
            "saved_search",
            row["id"],
            row["name"],
            f"Alerts {ALERT_LABELS[row['alerts']].lower()}",
        ),
    )


async def propose_update_search(session, user_id, args):
    row = await saved._own(session, user_id, args.search_id)
    changes = args.changes.model_dump(
        mode="json", exclude_unset=True, exclude_none=True
    )
    if not changes:
        raise BadRequestError("Supply at least one change.")
    shown = dict(changes)
    if "alerts" in shown:
        shown["alerts"] = ALERT_LABELS[shown["alerts"]]
    return Proposal(
        f"Update the saved search {quoted(row.name)}?",
        {"search_id": row.id, "changes": changes},
        field_lines(shown),
    )


async def apply_update_search(session, user_id, arguments):
    row = await saved.update(
        session, user_id, arguments["search_id"], arguments["changes"]
    )
    return Applied(
        {"search_id": row["id"], "name": row["name"], "alerts": row["alerts"]},
        "Updated the saved search.",
        preview(
            "saved_search",
            row["id"],
            row["name"],
            f"Alerts {ALERT_LABELS[row['alerts']].lower()}",
        ),
    )


async def propose_delete_search(session, user_id, args):
    row = await saved._own(session, user_id, args.search_id)
    return Proposal(
        f"Delete the saved search {quoted(row.name)}?",
        {"search_id": row.id},
        "Its alerts stop.",
        "Delete",
    )


async def apply_delete_search(session, user_id, arguments):
    await saved.delete(session, user_id, arguments["search_id"])
    return Applied({"deleted": True}, "Deleted the saved search.")


async def list_notifications(session, user_id, args, registry):
    inbox = await notifications.list_inbox(session, user_id)
    items = [
        {
            **record(row, ("id", "kind", "title", "body")),
            "read": row["read_at"] is not None,
            "received": row["created_at"].date().isoformat(),
        }
        for row in inbox["items"]
        if not (args.unread_only and row["read_at"])
    ]
    return {"items": items, "unread": inbox["unread"]}, len(items)


async def propose_mark_read(session, user_id, args):
    if args.notification_id:
        from sqlalchemy import select

        from api.notifications.models import Notification

        title = await session.scalar(
            select(Notification.title).where(
                Notification.id == args.notification_id,
                Notification.user_id == user_id,
            )
        )
        if title is None:
            from api.core.exceptions import NotFoundError

            raise NotFoundError("Notification not found")
        return Proposal(
            f"Mark {quoted(title)} as read?",
            {"notification_id": args.notification_id},
            action="Mark read",
        )
    unread = (await notifications.list_inbox(session, user_id))["unread"]
    if not unread:
        raise BadRequestError("There are no unread notifications.")
    return Proposal(
        f"Mark all {unread} unread notifications as read?"
        if unread > 1
        else "Mark your unread notification as read?",
        {"notification_id": None},
        action="Mark read",
    )


async def apply_mark_read(session, user_id, arguments):
    marked = await notifications.mark_read(
        session, user_id, arguments["notification_id"]
    )
    return Applied(
        {"marked": marked},
        "Marked as read." if marked else "Nothing was left unread.",
    )


async def get_notification_settings(session, user_id, args, registry):
    prefs = notifications.prefs_out(await notifications.get_prefs(session, user_id))
    return {
        "kinds": [
            {"kind": k["kind"], "label": k["label"], "channels": k["channels"]}
            for k in prefs["kinds"]
        ],
        "quiet_start": prefs["quiet_start"],
        "quiet_end": prefs["quiet_end"],
        "timezone": prefs["timezone"],
        "email_digest": prefs["email_digest"],
        "scope": "Push only reaches devices where the member turned it on in the app.",
    }, None


def _notification_patch(changes):
    patch = {k: v for k, v in changes.items() if k != "channels"}
    for key in ("quiet_start", "quiet_end", "timezone"):
        if patch.get(key) == "":
            patch[key] = None
    if changes.get("channels"):
        channels: dict[str, dict[str, bool]] = {}
        for item in changes["channels"]:
            channels.setdefault(item["kind"], {})[item["channel"]] = item["on"]
        patch["channels"] = channels
    return PreferencesIn.model_validate(patch).model_dump(exclude_unset=True)


async def propose_notifications(session, user_id, args):
    changes = args.changes.model_dump(
        mode="json", exclude_unset=True, exclude_none=True
    )
    if not changes:
        raise BadRequestError("Supply at least one change.")
    _notification_patch(changes)
    lines = []
    for item in changes.get("channels") or []:
        label = notifications.KINDS[item["kind"]].label
        channel = {"inbox": "Inbox", "push": "Push", "email": "Email"}[item["channel"]]
        lines.append(f"{label}, {channel}: {'On' if item['on'] else 'Off'}")
    rest = {k: v for k, v in changes.items() if k != "channels"}
    if rest:
        lines.append(
            field_lines(
                {k: (v or "Off") for k, v in rest.items()},
                {
                    "quiet_start": "Quiet hours start",
                    "quiet_end": "Quiet hours end",
                    "timezone": "Time zone",
                    "email_digest": "Daily email digest",
                },
            )
        )
    return Proposal(
        "Change your notification settings?", {"changes": changes}, "\n".join(lines)
    )


async def apply_notifications(session, user_id, arguments):
    await notifications.update_prefs(
        session, user_id, _notification_patch(arguments["changes"])
    )
    return Applied(
        {"updated": True},
        "Updated your notification settings.",
        preview("settings", "notifications", "Notifications", "Settings"),
    )


async def propose_name(session, user_id, args):
    name = auth_profile.normalize_name(args.display_name)
    user = await auth_service.get_user_or_401(session, user_id)
    if name == user.display_name:
        raise BadRequestError("That is already the member's name.")
    return Proposal(
        f"Change your name to {quoted(name)}?" if name else "Clear your display name?",
        {"display_name": name or ""},
        "" if name else "Blesser uses your email address instead.",
    )


async def apply_name(session, user_id, arguments):
    user = await auth_service.get_user_or_401(session, user_id)
    await auth_profile.update_profile(session, user, arguments["display_name"])
    return Applied(
        {"display_name": user.display_name},
        "Updated your name.",
        preview("settings", "profile", "Your profile", "Settings"),
    )


TOOLS = [
    Tool(
        "get_match_profile",
        ToolInput,
        "Read the member's feed settings (Your feed): categories are the audiences their feed shows (none means all), plus kinds, fields, levels, countries and match alert frequency.",
        "Checked your feed settings",
        "read",
        read=get_match_profile,
    ),
    Tool(
        "update_match_profile",
        UpdateMatch,
        "Propose changing the member's feed settings. Categories limit which audiences the feed shows. Only supplied fields change; lists replace the whole list.",
        "Update your feed settings",
        "change",
        propose=propose_match,
        apply=apply_match,
    ),
    Tool(
        "list_saved_searches",
        ToolInput,
        "Read the member's saved searches with their filters and alert frequency.",
        "Checked your saved searches",
        "read",
        read=list_saved_searches,
    ),
    Tool(
        "add_saved_search",
        AddSearch,
        "Propose saving a catalog search with alerts for new listings.",
        "Save a search",
        "change",
        propose=propose_add_search,
        apply=apply_add_search,
    ),
    Tool(
        "update_saved_search",
        UpdateSearch,
        "Propose renaming a saved search or changing its alerts.",
        "Update a saved search",
        "change",
        propose=propose_update_search,
        apply=apply_update_search,
    ),
    Tool(
        "delete_saved_search",
        SearchId,
        "Propose deleting a saved search and its alerts.",
        "Delete a saved search",
        "delete",
        propose=propose_delete_search,
        apply=apply_delete_search,
    ),
    Tool(
        "list_notifications",
        Notifications,
        "Read the member's notification inbox, newest first.",
        "Checked your notifications",
        "read",
        read=list_notifications,
    ),
    Tool(
        "mark_notifications_read",
        MarkRead,
        "Propose marking one notification, or all of them, as read.",
        "Mark notifications read",
        "change",
        propose=propose_mark_read,
        apply=apply_mark_read,
    ),
    Tool(
        "get_notification_settings",
        ToolInput,
        "Read the member's notification settings: channels per kind, quiet hours, time zone and the daily email digest.",
        "Checked your notification settings",
        "read",
        read=get_notification_settings,
    ),
    Tool(
        "update_notification_settings",
        UpdateNotifications,
        "Propose changing notification channels, quiet hours, time zone or the daily email digest. Only supplied fields change.",
        "Update notification settings",
        "change",
        propose=propose_notifications,
        apply=apply_notifications,
    ),
    Tool(
        "update_display_name",
        DisplayName,
        "Propose changing the name Blesser shows for the member and uses in emails.",
        "Change your name",
        "change",
        propose=propose_name,
        apply=apply_name,
    ),
]
