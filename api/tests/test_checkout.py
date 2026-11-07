import uuid

import pytest
from fastapi.testclient import TestClient

from api.core.config import settings
from api.main import app

pytestmark = pytest.mark.real_auth

OK = "4242 4242 4242 4242"
DECLINED = "4000 0000 0000 0002"


@pytest.fixture(autouse=True)
def _plans_apply(monkeypatch):
    monkeypatch.setattr(settings, "billing_enforced", True)
    monkeypatch.setattr(settings, "billing_plan_switch", True)
    monkeypatch.setattr(settings, "billing_provider", "simulated")


def _account(client):
    email = f"checkout-{uuid.uuid4().hex[:8]}@example.com"
    reg = client.post(
        "/api/auth/register",
        json={"accept_terms": True, "email": email, "password": "long-enough-1"},
    ).json()
    return reg["user"], {"Authorization": f"Bearer {reg['tokens']['access_token']}"}


def _me(client, h):
    return client.get("/api/auth/me", headers=h).json()


def test_a_new_account_is_asked_to_pick_a_plan():
    with TestClient(app) as client:
        user, h = _account(client)
        assert user["needs_plan"] is True and user["plan"] == "free"
        catalog = client.get("/api/billing/plan", headers=h).json()["catalog"]
        assert [p["id"] for p in catalog] == ["free", "pro"]  # Beta isn't sold
        assert catalog[1]["monthly_price_usd"] > 0


def test_free_applies_at_once():
    with TestClient(app) as client:
        _, h = _account(client)
        out = client.post("/api/billing/checkout", json={"plan": "free"}, headers=h).json()
        assert out == {"status": "applied", "plan": "free"}
        me = _me(client, h)
        assert me["needs_plan"] is False and me["plan"] == "free"


def test_pro_goes_through_checkout_with_test_cards():
    with TestClient(app) as client:
        _, h = _account(client)
        start = client.post("/api/billing/checkout", json={"plan": "pro"}, headers=h).json()
        assert start["status"] == "checkout"
        token = start["session"]
        page = client.get("/api/billing/checkout", params={"session": token}, headers=h).json()
        assert page["plan"]["id"] == "pro" and page["provider"] == "simulated"

        def pay(card):
            return client.post(
                "/api/billing/checkout/complete",
                json={"session": token, "card_number": card},
                headers=h,
            )

        declined = pay(DECLINED)
        assert declined.status_code == 400 and "declined" in declined.text
        assert pay("1234 5678").status_code == 400  # not a test card
        assert _me(client, h)["needs_plan"] is True

        assert pay(OK).json() == {"status": "paid", "plan": "pro"}
        me = _me(client, h)
        assert me["plan"] == "pro" and me["needs_plan"] is False
        assert client.get("/api/billing/plan", headers=h).json()["plan"]["id"] == "pro"


def test_a_checkout_belongs_to_its_account_and_beta_is_not_sold():
    with TestClient(app) as client:
        _, h = _account(client)
        _, other = _account(client)
        token = client.post("/api/billing/checkout", json={"plan": "pro"}, headers=h).json()["session"]
        stolen = client.post(
            "/api/billing/checkout/complete",
            json={"session": token, "card_number": OK},
            headers=other,
        )
        assert stolen.status_code == 400
        assert client.post("/api/billing/checkout", json={"plan": "beta"}, headers=h).status_code == 400


def test_no_plan_step_while_plans_do_not_apply(monkeypatch):
    monkeypatch.setattr(settings, "billing_enforced", False)
    monkeypatch.setattr(settings, "billing_plan_switch", False)
    with TestClient(app) as client:
        user, _ = _account(client)
        assert user["needs_plan"] is False and user["plan"] == "beta"


def test_paid_checkout_is_refused_without_the_dev_switch(monkeypatch):
    monkeypatch.setattr(settings, "billing_plan_switch", False)
    with TestClient(app) as client:
        _, h = _account(client)
        refused = client.post("/api/billing/checkout", json={"plan": "pro"}, headers=h)
        assert refused.status_code == 400
        assert "development-only" in refused.text
        out = client.post("/api/billing/checkout", json={"plan": "free"}, headers=h).json()
        assert out == {"status": "applied", "plan": "free"}


def test_paid_checkout_needs_a_configured_provider(monkeypatch):
    monkeypatch.setattr(settings, "billing_provider", "")
    with TestClient(app) as client:
        _, h = _account(client)
        refused = client.post("/api/billing/checkout", json={"plan": "pro"}, headers=h)
        assert refused.status_code == 400
        assert "provider" in refused.text
