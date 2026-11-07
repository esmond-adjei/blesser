import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from api.notifications.service import valid_zone

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class NotificationOut(BaseModel):
    id: str
    kind: str
    title: str
    body: str
    link: str
    entity_id: str | None
    created_at: datetime
    read_at: datetime | None


class InboxOut(BaseModel):
    items: list[NotificationOut]
    unread: int
    # The stored timezone; NULL tells the web app to report the browser's.
    timezone: str | None


class KindPrefsOut(BaseModel):
    kind: str
    label: str
    description: str
    channels: dict[str, bool]
    defaults: dict[str, bool]


class PreferencesOut(BaseModel):
    kinds: list[KindPrefsOut]
    quiet_start: str | None
    quiet_end: str | None
    timezone: str | None
    email_digest: bool


class PreferencesIn(BaseModel):
    """PATCH semantics: only provided fields are written."""

    channels: dict[str, dict[str, bool]] | None = None
    quiet_start: str | None = None
    quiet_end: str | None = None
    timezone: str | None = None
    email_digest: bool | None = None

    @field_validator("quiet_start", "quiet_end")
    @classmethod
    def _hhmm(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        if not _HHMM.match(value):
            raise ValueError("Use 24-hour HH:MM, e.g. 22:00")
        return value

    @field_validator("timezone")
    @classmethod
    def _zone(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        if len(value) > 64 or not valid_zone(value):
            raise ValueError("Unknown timezone")
        return value


class PushConfigOut(BaseModel):
    enabled: bool
    public_key: str | None


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class PushSubscriptionIn(BaseModel):
    """The browser's PushSubscription.toJSON(), plus its timezone."""

    endpoint: str = Field(min_length=1, max_length=2000)
    keys: PushKeys
    timezone: str | None = None

    @field_validator("endpoint")
    @classmethod
    def _https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("Push endpoints are https URLs")
        return value


class PushEndpointIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2000)


class PushSubscriptionOut(BaseModel):
    id: str
    endpoint: str
    user_agent: str | None
    created_at: datetime
    last_ok_at: datetime | None


class TestResultOut(BaseModel):
    push_enabled: bool
    devices: int
    pushed: int


class TestEmailOut(BaseModel):
    to: str
    sent: bool
    #: "console" prints mail to the server log instead of sending it.
    backend: str


class UnsubscribeIn(BaseModel):
    token: str = Field(min_length=1, max_length=2000)
