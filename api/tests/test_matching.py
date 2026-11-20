"""Full-text search, match profiles, "For you" order, saved searches and new-match alerts."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from api.applicant_kit.models import Profile
from api.applications.models import Application
from api.auth import models as auth_models
from api.core import mailer
from api.core.db import SessionLocal
from api.main import app
from api.matching import alerts, geo
from api.matching import service as matching
from api.matching.models import MatchProfile, SavedSearch
from api.notifications import delivery
from api.notifications.models import Notification, NotificationPreference
from api.opportunities import service as opp_service
from api.opportunities.models import Opportunity
from tests.conftest import TEST_USER_ID


def _run(coro):
    return asyncio.run(coro)


def _wipe():
    async def go():
        async with SessionLocal() as session:
            for model in (Application, Notification, SavedSearch, MatchProfile, Opportunity):
                await session.execute(delete(model))
            await session.execute(delete(Profile).where(Profile.user_id == TEST_USER_ID))
            await session.execute(delete(NotificationPreference).where(NotificationPreference.user_id == TEST_USER_ID))
            await session.commit()

    _run(go())


@pytest.fixture(autouse=True)
def _clean():
    _wipe()
    yield
    _wipe()


def _client():
    return TestClient(app)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _add(title: str, **fields) -> str:
    async def go():
        async with SessionLocal() as session:
            org = fields.pop("organization", "Funder")
            row = Opportunity(
                title=title,
                organization=org,
                category=fields.pop("category", "student"),
                kind=fields.pop("kind", "scholarship"),
                summary=fields.pop("summary", ""),
                eligibility=fields.pop("eligibility", ""),
                benefits="",
                location=fields.pop("location", ""),
                countries=fields.pop("countries", []),
                requirements=[],
                tags=fields.pop("tags", []),
                deadline="",
                rolling=fields.pop("rolling", False),
                link=f"https://example.org/{uuid.uuid4().hex[:6]}",
                source_url="https://example.org/",
                status=fields.pop("status", "published"),
                published_at=fields.pop("published_at", _now() - timedelta(days=30)),
                source="agent",
                dedupe_key=opp_service.dedupe_key(org, title),
                **fields,
            )
            session.add(row)
            await session.commit()
            return row.id

    return _run(go())


def _ids(page: dict) -> list[str]:
    return [item["id"] for item in page["items"]]


# --- Full-text search -------------------------------------------------------------


def test_search_stems_prefixes_and_ranks_title_first():
    in_title = _add("Mastercard Scholarships for Engineering", summary="Fully funded.")
    in_summary = _add("Graduate Award", summary="A scholarship for engineers.", deadline_date=opp_service.today() + timedelta(days=3))
    _add("Seed Grant", category="startup", kind="grant", summary="For founders.")
    client = _client()

    plural = client.get("/api/opportunities", params={"q": "scholarships"}).json()
    assert set(_ids(plural)) == {in_title, in_summary}
    # A word still being typed matches as a prefix.
    assert set(_ids(client.get("/api/opportunities", params={"q": "schol"}).json())) == {in_title, in_summary}
    # Every word must match.
    assert _ids(client.get("/api/opportunities", params={"q": "scholarship engineering"}).json()) != []
    assert _ids(client.get("/api/opportunities", params={"q": "scholarship founders"}).json()) == []
    # Best match puts the title hit first; deadline order puts the sooner one first.
    best = client.get("/api/opportunities", params={"q": "scholarship", "sort": "relevance"}).json()
    assert _ids(best) == [in_title, in_summary]
    soonest = client.get("/api/opportunities", params={"q": "scholarship"}).json()
    assert _ids(soonest) == [in_summary, in_title]


def test_search_reads_tags_kind_and_location_and_ignores_punctuation():
    tagged = _add("Climate Award", tags=["agritech"], location="Kumasi")
    client = _client()
    for q in ("agritech", "kumasi", "scholarship", "climate & (agri", "  "):
        assert tagged in _ids(client.get("/api/opportunities", params={"q": q}).json()), q
    # Only stop words: nothing to filter on, so everything matches.
    assert _ids(client.get("/api/opportunities", params={"q": "the for"}).json()) == [tagged]


def test_public_search_uses_full_text_too():
    public = _add("Public Health Fellowship", kind="fellowship", category="research", audience="public")
    _add("Members Health Fellowship", kind="fellowship", category="research", audience="members")
    page = _client().get("/api/public/opportunities", params={"q": "fellowships health", "sort": "relevance"}).json()
    assert _ids(page) == [public]


def test_tsquery_text_strips_operators():
    assert matching.tsquery_text("AI & (data) | 'x'!") == "ai:* & data:* & x:*"
    assert matching.tsquery_text("___") == ""


# --- Match profile ----------------------------------------------------------------


def _kit(data: dict):
    async def go():
        async with SessionLocal() as session:
            session.add(Profile(user_id=TEST_USER_ID, data=data, sensitive={}))
            await session.commit()

    _run(go())


def test_profile_is_suggested_from_the_applicant_kit_until_saved():
    _kit(
        {
            "nationality": "Ghanaian",
            "country_of_residence": "United Kingdom",
            "education": [
                {"institution": "KNUST", "qualification": "BSc", "field": "Computer Science", "end": "2024-07-01"},
            ],
            "skills": ["Python", "Data analysis", "python"],
        }
    )
    client = _client()
    body = client.get("/api/match-profile").json()
    assert body["saved"] is False
    assert body["countries"] == ["Ghana", "United Kingdom"]
    assert body["levels"] == ["masters"]
    assert body["categories"] == ["student"]
    assert body["fields"] == ["Computer Science", "Python", "Data analysis"]

    saved = client.put(
        "/api/match-profile",
        json={**{k: body[k] for k in ("categories", "fields", "levels", "countries")}, "kinds": ["scholarship"], "alerts": "weekly"},
    ).json()
    assert saved["saved"] is True and saved["alerts"] == "weekly" and saved["kinds"] == ["scholarship"]
    assert client.get("/api/match-profile").json()["saved"] is True

    assert client.delete("/api/match-profile").status_code == 204
    assert client.get("/api/match-profile").json()["saved"] is False


def test_profile_validation_and_cleanup():
    client = _client()
    assert client.put("/api/match-profile", json={"categories": ["astronaut"]}).status_code == 422
    assert client.put("/api/match-profile", json={"alerts": "hourly"}).status_code == 422
    assert client.put("/api/match-profile", json={"surprise": 1}).status_code == 422
    body = client.put(
        "/api/match-profile",
        json={"countries": ["ghana", "Narnia", "Ivory Coast", "Ghana"], "fields": ["AI", "ai", " health "]},
    ).json()
    assert body["countries"] == ["Ghana", "Côte d'Ivoire"]
    assert body["fields"] == ["AI", "health"]


def test_geo_names_and_aliases():
    assert geo.country("U.S.A") is None  # dots become spaces: "u s a" is not an alias
    assert geo.country("USA") == "United States"
    assert geo.country("Côte d’Ivoire") == "Côte d'Ivoire"
    assert geo.country("Nigerian") == "Nigeria"
    assert "ghana" in geo.keys_for("Ghana")


# --- For you ----------------------------------------------------------------------


def _profile(**fields):
    _client().put("/api/match-profile", json={"alerts": "daily", **fields}).raise_for_status()


def test_for_you_ranks_by_profile_and_leaves_out_closed_countries():
    _profile(categories=["student"], kinds=["scholarship"], fields=["public health"], countries=["Ghana"])
    best = _add("Public Health Masters Scholarship", countries=["Ghana", "Kenya"])
    kind_only = _add("General Scholarship", countries=["Africa"])
    other = _add("Startup Grant", category="startup", kind="grant", countries=[])
    _add("Kenya-only Scholarship", countries=["Kenya", "Uganda"])
    global_one = _add("Health Award", category="research", kind="grant", summary="Public health research.", countries=["Global"])

    page = _client().get("/api/opportunities", params={"sort": "for_you"}).json()
    assert _ids(page) == [best, kind_only, global_one, other]
    assert page["total"] == 4
    top = page["items"][0]
    assert top["match_terms"] == ["public health"] and top["match_score"] >= 6.5
    assert page["items"][-1]["match_terms"] == []


def test_for_you_without_a_profile_still_lists_everything():
    a = _add("A Scholarship", countries=["Kenya"])
    page = _client().get("/api/opportunities", params={"sort": "for_you"}).json()
    assert _ids(page) == [a]


def test_for_you_boosts_closing_soon_and_fresh_checks():
    _profile(categories=["student"])
    later = _add("Later", deadline_date=opp_service.today() + timedelta(days=90))
    soon = _add("Soon", deadline_date=opp_service.today() + timedelta(days=10), verified_at=_now())
    assert _ids(_client().get("/api/opportunities", params={"sort": "for_you"}).json()) == [soon, later]


# --- Saved searches ---------------------------------------------------------------


def test_saved_search_crud_and_limit():
    client = _client()
    created = client.post(
        "/api/saved-searches",
        json={"name": "AI grants", "filters": {"q": "ai", "kind": "grant", "country": ""}, "alerts": "weekly"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["filters"] == {"q": "ai", "kind": "grant", "category": None, "country": None, "closing_within": None}
    sid = body["id"]
    assert client.patch(f"/api/saved-searches/{sid}", json={"alerts": "off", "name": "AI"}).json()["name"] == "AI"
    assert [s["id"] for s in client.get("/api/saved-searches").json()] == [sid]
    assert client.post("/api/saved-searches", json={"name": "x", "filters": {"kind": "rocket"}}).status_code == 422
    for i in range(19):
        assert client.post("/api/saved-searches", json={"name": f"s{i}", "filters": {}}).status_code == 201
    assert client.post("/api/saved-searches", json={"name": "one too many", "filters": {}}).status_code == 409
    assert client.delete(f"/api/saved-searches/{sid}").status_code == 204
    assert client.delete(f"/api/saved-searches/{sid}").status_code == 404


def test_saved_searches_are_private():
    other = _other_user()

    async def go():
        async with SessionLocal() as session:
            row = SavedSearch(user_id=other, name="Theirs", filters={}, alerts="daily")
            session.add(row)
            await session.commit()
            return row.id

    theirs = _run(go())
    client = _client()
    assert client.get("/api/saved-searches").json() == []
    assert client.patch(f"/api/saved-searches/{theirs}", json={"name": "Mine"}).status_code == 404
    assert client.delete(f"/api/saved-searches/{theirs}").status_code == 404


# --- Alerts -----------------------------------------------------------------------


def _other_user(tz: str | None = None) -> str:
    user_id = f"match-{uuid.uuid4().hex[:10]}"

    async def go():
        async with SessionLocal() as session:
            session.add(
                auth_models.User(
                    id=user_id, email=f"{user_id}@example.com", password_hash="x", email_verified_at=_now()
                )
            )
            await session.flush()
            if tz:
                session.add(NotificationPreference(user_id=user_id, channels={}, timezone=tz))
            await session.commit()

    _run(go())
    return user_id


def _set_profile(user_id: str, **fields):
    async def go():
        async with SessionLocal() as session:
            row = MatchProfile(
                user_id=user_id,
                categories=fields.pop("categories", []),
                kinds=fields.pop("kinds", []),
                fields=fields.pop("fields", []),
                levels=fields.pop("levels", []),
                countries=fields.pop("countries", []),
                alerts=fields.pop("alerts", "daily"),
                closing_soon=fields.pop("closing_soon", False),
                **fields,
            )
            session.add(row)
            await session.commit()

    _run(go())


def _alerts(now: datetime) -> int:
    async def go():
        async with SessionLocal() as session:
            return await alerts.run(session, now)

    return _run(go())


def _notes(user_id: str, kind: str | None = None) -> list[Notification]:
    async def go():
        async with SessionLocal() as session:
            stmt = select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at)
            if kind:
                stmt = stmt.where(Notification.kind == kind)
            return list((await session.execute(stmt)).scalars())

    return _run(go())


def _at(hour: int, days: int = 0) -> datetime:
    """Naive UTC on a fixed day, so local hours are predictable."""
    return datetime(2026, 11, 20, hour, 0, tzinfo=UTC).replace(tzinfo=None) + timedelta(days=days)


def test_new_match_alert_lists_fitting_new_listings_once_a_day():
    user = _other_user()
    _set_profile(user, categories=["student"], fields=["engineering"], countries=["Ghana"], last_alert_at=_at(20, days=-1))
    fits = _add("Engineering Scholarship", published_at=_at(7), deadline_date=_at(0, 20).date())
    _add("Old Engineering Scholarship", published_at=_at(19, days=-1))  # before the last alert
    _add("History Scholarship", published_at=_at(7))  # no field match
    _add("Engineering Grant", category="startup", kind="grant", published_at=_at(7))  # wrong category
    _add("Kenya Engineering Scholarship", countries=["Kenya"], published_at=_at(7))  # not open to Ghana

    assert _alerts(_at(7)) == 0  # before 08:00 local
    assert _alerts(_at(9)) == 1
    [note] = _notes(user, "new_match")
    assert note.title == "1 new opportunity fits you"
    assert note.link == "/opportunities?sort=for_you"
    assert note.items == [{"title": "Engineering Scholarship", "body": "Funder, Closes in 20 days", "link": f"/opportunities/{fits}"}]

    # Same day: nothing more, even with a new fit.
    _add("Engineering Masters Scholarship", published_at=_at(10))
    assert _alerts(_at(11)) == 0
    # Next day: only what is new since the last run.
    assert _alerts(_at(9, days=1)) == 1
    latest = _notes(user, "new_match")[-1]
    assert [i["title"] for i in latest.items] == ["Engineering Masters Scholarship"]


def test_alerts_follow_local_time_weekly_cadence_and_skip_tracked():
    user = _other_user(tz="Pacific/Auckland")  # UTC+13 in November
    _set_profile(user, kinds=["fellowship"], alerts="weekly", last_alert_at=_at(0, days=-7))
    tracked = _add("Tracked Fellowship", kind="fellowship", published_at=_at(1, days=-1))
    _add("New Fellowship", kind="fellowship", published_at=_at(1, days=-1))

    async def track():
        async with SessionLocal() as session:
            session.add(Application(user_id=user, title="Tracked Fellowship", opportunity_id=tracked))
            await session.commit()

    _run(track())
    # 18:00 UTC on the 19th is 07:00 on the 20th in Auckland: too early.
    assert _alerts(_at(18, days=-1)) == 0
    assert _alerts(_at(20, days=-1)) == 1
    [note] = _notes(user, "new_match")
    assert [i["title"] for i in note.items] == ["New Fellowship"]
    # Weekly: nothing for six days.
    _add("Another Fellowship", kind="fellowship", published_at=_at(0, days=2))
    assert _alerts(_at(20, days=5)) == 0
    assert _alerts(_at(20, days=6)) == 1


def test_profile_without_preferences_or_with_alerts_off_gets_no_new_match():
    only_country = _other_user()
    _set_profile(only_country, countries=["Ghana"], last_alert_at=_at(0, days=-1))
    off = _other_user()
    _set_profile(off, categories=["student"], alerts="off", last_alert_at=_at(0, days=-1))
    _add("Any Scholarship", published_at=_at(1))
    assert _alerts(_at(9)) == 0
    assert _notes(only_country) == [] and _notes(off) == []


def test_weekly_closing_soon_lists_fits_closing_within_two_weeks():
    user = _other_user()
    _set_profile(user, categories=["research"], alerts="off", closing_soon=True)
    today = _at(9).date()
    _add("Soon Grant", category="research", kind="grant", deadline_date=today + timedelta(days=5))
    _add("Later Grant", category="research", kind="grant", deadline_date=today + timedelta(days=40))
    _add("Soon Student", category="student", deadline_date=today + timedelta(days=5))
    assert _alerts(_at(9)) == 1
    [note] = _notes(user, "closing_match")
    assert note.title == "1 opportunity that fits you closes soon"
    assert [i["title"] for i in note.items] == ["Soon Grant"]
    assert _alerts(_at(9, days=3)) == 0
    _add("Next Grant", category="research", kind="grant", deadline_date=today + timedelta(days=10))
    assert _alerts(_at(9, days=7)) == 1
    assert [i["title"] for i in _notes(user, "closing_match")[-1].items] == ["Next Grant"]


def test_saved_search_alerts_on_new_results():
    user = _other_user()

    async def go():
        async with SessionLocal() as session:
            row = SavedSearch(
                user_id=user,
                name="Climate grants",
                filters={"q": "climate", "kind": "grant"},
                alerts="daily",
                last_alert_at=_at(0, days=-1),
            )
            session.add(row)
            await session.commit()
            return row.id

    sid = _run(go())
    _add("Climate Grant", kind="grant", category="research", published_at=_at(3))
    _add("Climate Scholarship", published_at=_at(3))
    _add("Water Grant", kind="grant", category="research", published_at=_at(3))
    assert _alerts(_at(9)) == 1
    [note] = _notes(user, "saved_search")
    assert note.title == "1 new result for “Climate grants”"
    assert note.link == f"/opportunities?saved={sid}" and note.entity_id == sid
    assert _alerts(_at(9, days=1)) == 0


def test_alert_email_lists_the_matched_listings():
    user = _other_user()
    _set_profile(user, kinds=["grant"], last_alert_at=_at(0, days=-1))
    _add("Seed Grant", kind="grant", category="startup", organization="Accra Fund", published_at=_at(2), rolling=True)
    assert _alerts(_at(9)) == 1
    mailer.outbox.clear()

    async def deliver():
        async with SessionLocal() as session:
            return await delivery.deliver_pending(session, now=_at(9))

    _run(deliver())
    [mail] = [m for m in mailer.outbox if m.to == f"{user}@example.com"]
    assert mail.subject == "1 new opportunity fits you"
    assert "Seed Grant" in mail.html and "Accra Fund, Rolling" in mail.text
    assert "/opportunities/" in mail.text


def test_for_you_and_alerts_agree_on_the_country_gate():
    prefs = matching.Prefs(categories=("student",), countries=("Ghana",))
    assert prefs.can_alert and not matching.Prefs(countries=("Ghana",)).can_alert
    # Members typed "Ghanaian" in the kit; it maps to the same gate.
    assert matching.clean_countries(["Ghanaian"]) == ["Ghana"]
