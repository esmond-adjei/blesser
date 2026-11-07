import io

from fastapi.testclient import TestClient
from PIL import Image

from api.main import app


def _image(fmt: str = "PNG", size=(640, 480), exif: bool = False) -> bytes:
    img = Image.new("RGB", size, (30, 60, 120))
    out = io.BytesIO()
    kwargs = {}
    if exif:
        ex = Image.Exif()
        ex[0x010F] = "SecretCam"  # Make
        kwargs["exif"] = ex
    img.save(out, format=fmt, **kwargs)
    return out.getvalue()


def _put(client, data: bytes, name="me.png", ctype="image/png"):
    return client.put("/api/auth/me/avatar", files={"file": (name, data, ctype)})


def test_display_name_normalizes_and_clears(monkeypatch):
    # Real Bearer auth (not the conftest stub) so /auth/me reads the row.
    import uuid

    from api.auth.routes import get_current_user

    saved = app.dependency_overrides.pop(get_current_user, None)
    try:
        with TestClient(app) as client:
            email = f"profile-{uuid.uuid4().hex[:8]}@example.com"
            reg = client.post(
                "/api/auth/register",
                json={"accept_terms": True, "email": email, "password": "long-enough-pw-1"},
            )
            headers = {
                "Authorization": f"Bearer {reg.json()['tokens']['access_token']}"
            }
            r = client.patch(
                "/api/auth/me",
                json={"display_name": "  Ada \t Lovelace\u0007 "},
                headers=headers,
            )
            assert r.status_code == 200, r.text
            assert r.json()["display_name"] == "Ada Lovelace"
            assert (
                client.get("/api/auth/me", headers=headers).json()["display_name"]
                == "Ada Lovelace"
            )
            too_long = client.patch(
                "/api/auth/me", json={"display_name": "x" * 81}, headers=headers
            )
            assert too_long.status_code == 400
            cleared = client.patch(
                "/api/auth/me", json={"display_name": "   "}, headers=headers
            )
            assert cleared.json()["display_name"] is None
    finally:
        if saved is not None:
            app.dependency_overrides[get_current_user] = saved


def test_avatar_is_reencoded_square_webp_and_served_by_key():
    with TestClient(app) as client:
        r = _put(client, _image("JPEG", (800, 400), exif=True), "me.jpg", "image/jpeg")
        assert r.status_code == 200, r.text
        url = r.json()["avatar_url"]
        assert url and url.startswith("/api/avatars/")
        served = client.get(url)
        assert served.status_code == 200
        assert served.headers["content-type"] == "image/webp"
        assert "immutable" in served.headers["cache-control"]
        img = Image.open(io.BytesIO(served.content))
        assert img.format == "WEBP" and img.size == (256, 256)
        assert not img.getexif()

        new_url = _put(client, _image()).json()["avatar_url"]
        assert new_url != url
        assert client.get(url).status_code == 404

        cleared = client.delete("/api/auth/me/avatar")
        assert cleared.json()["avatar_url"] is None
        assert client.get(new_url).status_code == 404


def test_avatar_rejects_non_images_and_oversize():
    with TestClient(app) as client:
        assert _put(client, b"%PDF-1.4 not an image", "x.png").status_code == 400
        # Right magic bytes, garbage after them.
        assert _put(client, b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).status_code == 400
        assert (
            _put(
                client, b"\xff\xd8\xff" + b"a" * (5 * 1024 * 1024 + 10), "x.jpg"
            ).status_code
            == 400
        )
        assert _put(client, b"").status_code == 400
