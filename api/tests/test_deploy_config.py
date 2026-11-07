"""Compose must keep CV files on a persistent volume, or rebuilds delete them while their DB rows survive."""

from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"
CV_MOUNT = "/app/cv_storage"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text())


def test_cv_storage_is_a_named_volume_on_api_and_worker():
    compose = _compose()
    volumes = compose["volumes"]
    for service in ("api", "worker"):
        svc = compose["services"][service]
        mounts = [str(m) for m in svc.get("volumes", [])]
        sources = [m.split(":", 1)[0] for m in mounts if m.endswith(f":{CV_MOUNT}")]
        assert sources, f"{service} has no volume at {CV_MOUNT}"
        assert sources[0] in volumes, f"{service} mounts an undeclared volume"
        assert svc["environment"]["CV_STORAGE_DIR"] == CV_MOUNT
    assert volumes["cv-storage"]["name"] == "graduator_cv_storage"


def test_nginx_admits_cv_uploads_and_api_port_is_loopback():
    nginx = (COMPOSE.parent / "webapp" / "nginx.conf").read_text()
    api_block = nginx.split("location /api/ {", 1)[1].split("}", 1)[0]
    assert "client_max_body_size 12m;" in api_block
    ports = [str(p) for p in _compose()["services"]["api"]["ports"]]
    assert all(p.startswith("${API_BIND:-127.0.0.1}:") for p in ports)
