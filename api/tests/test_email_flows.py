import re
import uuid

import pytest
from fastapi.testclient import TestClient

from api.core import mailer
from api.core.config import settings
from api.main import app

pytestmark = pytest.mark.real_auth
PW = "first-password-1"


def _token(mail: mailer.Mail) -> str:
    return re.search(r"token=([\w\-%]+)", mail.text).group(1)


def _register(client):
    email = f"flow-{uuid.uuid4().hex[:8]}@example.com"
    mailer.outbox.clear()
    reg = client.post(
        "/api/auth/register", json={"accept_terms": True, "email": email, "password": PW}
    ).json()
    return email, reg


def test_register_sends_single_use_verification_link():
    with TestClient(app) as client:
        email, reg = _register(client)
        headers = {"Authorization": f"Bearer {reg['tokens']['access_token']}"}
        assert reg["user"]["email_verified"] is False
        sent = [m for m in mailer.outbox if m.to == email]
        assert sent and "/verify-email?token=" in sent[-1].text
        token = _token(sent[-1])
        ok = client.post("/api/auth/verify", json={"token": token})
        assert ok.status_code == 200 and ok.json()["email_verified"] is True
        assert (
            client.get("/api/auth/me", headers=headers).json()["email_verified"] is True
        )
        again = client.post("/api/auth/verify", json={"token": token})
        assert (
            again.status_code == 400
            and "invalid or has expired" in again.json()["detail"]
        )


def test_reset_flow_is_enumeration_safe_single_use_and_revokes_sessions():
    with TestClient(app) as client:
        email, reg = _register(client)
        mailer.outbox.clear()
        unknown = client.post(
            "/api/auth/password/forgot", json={"email": "nobody-x@example.com"}
        )
        known = client.post("/api/auth/password/forgot", json={"email": email.upper()})
        assert unknown.status_code == known.status_code == 200
        assert unknown.json() == known.json()  # same answer either way
        assert [m.to for m in mailer.outbox] == [email]

        token = _token(mailer.outbox[-1])
        done = client.post(
            "/api/auth/password/reset",
            json={"token": token, "new_password": "brand-new-pw-2"},
        )
        assert done.status_code == 200, done.text
        assert (
            client.post(
                "/api/auth/refresh",
                json={"refresh_token": reg["tokens"]["refresh_token"]},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/auth/login", json={"email": email, "password": PW}
            ).status_code
            == 401
        )
        login = client.post(
            "/api/auth/login", json={"email": email, "password": "brand-new-pw-2"}
        )
        assert login.status_code == 200
        assert login.json()["user"]["email_verified"] is True  # mailbox proven
        reuse = client.post(
            "/api/auth/password/reset",
            json={"token": token, "new_password": "another-pw-3"},
        )
        assert reuse.status_code == 400


def test_expired_reset_link_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "password_reset_minutes", 0)
    with TestClient(app) as client:
        email, _ = _register(client)
        mailer.outbox.clear()
        client.post("/api/auth/password/forgot", json={"email": email})
        token = _token(mailer.outbox[-1])
        r = client.post(
            "/api/auth/password/reset",
            json={"token": token, "new_password": "brand-new-pw-2"},
        )
        assert r.status_code == 400


@pytest.mark.rate_limits
def test_forgot_is_throttled_per_email_and_resend_has_a_cooldown():
    with TestClient(app) as client:
        email, reg = _register(client)
        codes = [
            client.post("/api/auth/password/forgot", json={"email": email}).status_code
            for _ in range(4)
        ]
        assert codes == [200, 200, 200, 429]
        headers = {"Authorization": f"Bearer {reg['tokens']['access_token']}"}
        # Registration just sent one, so an immediate resend waits.
        r = client.post("/api/auth/verify/send", headers=headers)
        assert r.status_code == 429 and "Try again in" in r.json()["detail"]
