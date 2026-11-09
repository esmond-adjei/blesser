import asyncio
import base64
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from api.applications.models import Application
from api.core.config import settings
from api.core.db import SessionLocal
from api.main import app
from api.opportunities import service as opp_service
from api.opportunities import share
from api.opportunities.models import Opportunity
from api.todos.models import Todo
from tests.conftest import TEST_USER_ID

SITE = "https://blesser.example"


def _wipe():
    async def go():
        async with SessionLocal() as session:
            await session.execute(delete(Todo))
            await session.execute(delete(Application))
            await session.execute(delete(Opportunity))
            await session.commit()

    asyncio.run(go())


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(settings, "site_url", SITE + "/")
    _wipe()
    yield
    _wipe()


def _add(**fields) -> Opportunity:
    async def go():
        async with SessionLocal() as session:
            title = fields.pop("title", "Seed Fund")
            org = fields.pop("organization", "Accra Ventures")
            row = Opportunity(
                title=title,
                organization=org,
                category=fields.pop("category", "startup"),
                kind=fields.pop("kind", "grant"),
                summary="",
                eligibility=fields.pop("eligibility", ""),
                benefits=fields.pop("benefits", "Up to USD 50,000"),
                location="Ghana",
                countries=[],
                requirements=[],
                tags=[],
                deadline=fields.pop("deadline", ""),
                deadline_date=fields.pop("deadline_date", date(2027, 11, 21)),
                rolling=fields.pop("rolling", False),
                link="https://example.org/apply",
                source_url="https://example.org/apply",
                status=fields.pop("status", "published"),
                audience=fields.pop("audience", "public"),
                source="agent",
                dedupe_key=opp_service.dedupe_key(org, title),
                **fields,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            session.expunge(row)
            return row

    return asyncio.run(go())


def _client():
    return TestClient(app)


# --- tokens -----------------------------------------------------------------


def test_token_round_trips_uuids_and_other_ids():
    opp, sharer = str(uuid.uuid4()), str(uuid.uuid4())
    assert share.read_token(share.make_token(opp, sharer)) == (opp, sharer)
    assert share.read_token(share.make_token(opp)) == (opp, None)
    assert share.read_token(share.make_token(opp, TEST_USER_ID)) == (opp, TEST_USER_ID)
    assert share.read_token(share.make_token("not-a-uuid")) == ("not-a-uuid", None)
    assert len(share.make_token(opp, sharer)) <= 60


def test_tampered_or_foreign_tokens_are_rejected(monkeypatch):
    opp, sharer = str(uuid.uuid4()), str(uuid.uuid4())
    token = share.make_token(opp, sharer)
    raw = bytearray(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    raw[3] ^= 1
    forged = base64.urlsafe_b64encode(bytes(raw)).rstrip(b"=").decode()
    assert share.read_token(forged) is None
    assert share.read_token(token[:-2]) is None
    assert share.read_token(token + "A") is None
    assert share.read_token("x" * 30) is None
    assert share.read_token(token.replace(token[5], "!")) is None
    monkeypatch.setattr(share.security, "_SIGNING_KEY", "another-key")
    assert share.read_token(token) is None


# --- captions ---------------------------------------------------------------


def test_short_caption_always_fits_280_trimming_benefit_then_title():
    url = f"{SITE}/s/{'x' * 60}"
    opp = Opportunity(
        title="The " + "Very Long Fellowship Name " * 12,
        organization="Center for Effective Global Action (CEGA)",
        benefits="Fully funded, " * 40,
        kind="fellowship",
        category="research",
        deadline="",
        deadline_date=date(2027, 1, 17),
        rolling=False,
        status="published",
    )
    text = share.short_caption(opp, url)
    assert len(text) <= 280
    assert text.endswith(f"{url} via Blesser")
    assert "Deadline 17 Jan 2027." in text
    assert "(Center for Effective Global Action (CEGA))" in text

    opp.title = "Seed Grant"
    text = share.short_caption(opp, url)
    assert len(text) <= 280 and text.startswith("Seed Grant (Center")
    assert "…" in text

    opp.organization = "O" * 300
    assert len(share.short_caption(opp, url)) <= 280


def test_short_caption_reads_naturally_when_it_fits():
    opp = Opportunity(
        title="Seed Fund",
        organization="Accra Ventures",
        benefits="Up to USD 50,000.",
        deadline="",
        deadline_date=None,
        rolling=True,
        status="published",
        kind="grant",
        category="startup",
    )
    assert (
        share.short_caption(opp, "https://b.example/s/t")
        == "Seed Fund (Accra Ventures). Up to USD 50,000. Apply any time. https://b.example/s/t via Blesser"
    )


def test_member_share_kit_for_public_opportunity():
    opp = _add(
        eligibility="Ghanaian founders under 35. Must be registered.",
        benefits="Up to USD 50,000\nplus mentoring",
    )
    resp = _client().post(f"/api/app/opportunities/{opp.id}/share")
    assert resp.status_code == 200
    kit = resp.json()
    token = kit["share_url"].removeprefix(f"{SITE}/s/")
    assert share.read_token(token) == (opp.id, TEST_USER_ID)
    assert set(kit["images"]) == {"square", "wide", "story"}
    assert kit["images"]["wide"].startswith(f"{SITE}/share/{token}/wide.png?v=")
    assert kit["disclaimer"] == "Blesser is not affiliated with Accra Ventures."

    standard = kit["captions"]["standard"]
    assert standard.splitlines()[:4] == [
        "Seed Fund",
        "Offered by Accra Ventures",
        "",
        "Up to USD 50,000 plus mentoring",
    ]
    assert "Ghanaian founders under 35." in standard
    assert "Deadline: 21 Nov 2027" in standard
    assert f"Details and the official link: {kit['share_url']}" in standard
    assert (
        "Blesser is not affiliated with Accra Ventures; always apply on the official page."
        in standard
    )
    for wording in ("presents", "partnership", "partner", "endorse"):
        assert wording not in standard.lower()

    tagged = kit["captions"]["hashtags"]
    assert tagged.splitlines()[-1] == "#Grants #Startups #Ghana"
    assert "Blesser is not affiliated with Accra Ventures." in tagged
    assert len(kit["captions"]["short"]) <= 280


def test_rolling_and_missing_organization_wording():
    opp = _add(
        organization="",
        rolling=True,
        deadline_date=None,
        kind="fellowship",
        category="research",
    )
    kit = _client().post(f"/api/app/opportunities/{opp.slug}/share").json()
    assert "Deadline: Rolling, apply any time" in kit["captions"]["standard"]
    assert "Offered by" not in kit["captions"]["standard"]
    assert (
        kit["disclaimer"]
        == "Blesser is not affiliated with the organization offering it."
    )
    assert kit["captions"]["hashtags"].endswith("#Fellowships #Research #Ghana")


# --- visibility -------------------------------------------------------------


def test_members_only_share_shows_a_teaser_without_the_official_link():
    opp = _add(audience="members")
    kit = _client().post(f"/api/app/opportunities/{opp.id}/share").json()
    token = kit["share_url"].rsplit("/", 1)[1]

    teaser = _client().get(f"/api/public/shared/{token}")
    assert teaser.status_code == 200
    body = teaser.json()
    assert body["audience"] == "members" and body["status"] == "published"
    assert body["slug"] == opp.slug and body["seed"] == opp.slug
    assert body["deadline"] == "21 Nov 2027" and body["deadline_date"] == "2027-11-21"
    assert "link" not in body and "source_url" not in body
    assert "example.org" not in teaser.text

    assert (
        _client().get(f"/api/public/opportunities/{opp.slug}/share").status_code == 404
    )
    assert _client().get(f"/api/public/opportunities/{opp.slug}").status_code == 404


def test_hidden_and_draft_opportunities_cannot_be_shared():
    for status in ("hidden", "draft", "in_review"):
        opp = _add(title=f"{status} grant", status=status)
        assert (
            _client().post(f"/api/app/opportunities/{opp.id}/share").status_code == 404
        )
        token = share.make_token(opp.id, TEST_USER_ID)
        assert _client().get(f"/api/public/shared/{token}").status_code == 404
    assert _client().get(f"/api/public/shared/{'A' * 40}").status_code == 404
    assert _client().get("/api/public/shared/not-a-token").status_code == 404


def test_archived_opportunity_shares_as_closed():
    opp = _add(status="archived", audience="members")
    kit = _client().post(f"/api/app/opportunities/{opp.id}/share").json()
    assert "Deadline: Closed" in kit["captions"]["standard"]
    assert "Now closed." in kit["captions"]["short"]
    token = kit["share_url"].rsplit("/", 1)[1]
    body = _client().get(f"/api/public/shared/{token}").json()
    assert body["status"] == "archived" and body["deadline"] == "Closed"


def test_public_share_kit_has_no_sharer_and_links_the_page():
    opp = _add()
    resp = _client().get(f"/api/public/opportunities/{opp.slug}/share")
    assert resp.status_code == 200
    kit = resp.json()
    assert kit["share_url"] == f"{SITE}/opportunities/{opp.slug}"
    token = kit["images"]["square"].split("/share/")[1].split("/")[0]
    assert share.read_token(token) == (opp.id, None)
    assert kit["share_url"] in kit["captions"]["short"]

    archived = _add(title="Old Grant", status="archived")
    assert (
        _client().get(f"/api/public/opportunities/{archived.slug}/share").status_code
        == 404
    )
