"""Compose and nginx keep the API private behind the web app's proxy."""

from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text())


def test_api_port_is_loopback_and_nginx_proxies_api():
    ports = [str(p) for p in _compose()["services"]["api"]["ports"]]
    assert all(p.startswith("${API_BIND:-127.0.0.1}:") for p in ports)
    nginx = (COMPOSE.parent / "webapp" / "nginx.conf").read_text()
    assert "location /api/ {" in nginx and "proxy_pass http://api:8000;" in nginx


def test_api_and_worker_share_one_image():
    services = _compose()["services"]
    assert services["api"]["build"] == services["worker"]["build"]
    assert services["worker"]["command"][:3] == ["python", "-m", "api.worker"]
