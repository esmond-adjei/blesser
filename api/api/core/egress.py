"""Outbound-request guard for URLs a user or a model chose.

http(s) only, no userinfo; the host must resolve to public addresses only;
every redirect hop is rechecked; bodies are byte-capped. DNS is checked, not
pinned, so rebinding between check and connect can still slip past: that
needs a resolver-level fix.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket

import httpx

MAX_REDIRECTS = 5


class EgressBlocked(Exception):
    """The URL points somewhere this process must not reach."""


def ip_is_public(raw: str) -> bool:
    ip = ipaddress.ip_address(raw.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


async def _resolve(host: str, port: int) -> list[str]:
    """Every address the host resolves to (seam for tests)."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def _literal_ip(host: str) -> str | None:
    try:
        ipaddress.ip_address(host.strip("[]").split("%", 1)[0])
    except ValueError:
        return None
    return host.strip("[]")


async def check_url(url: str | httpx.URL) -> httpx.URL:
    """Raise EgressBlocked unless `url` is http(s) to public addresses only.
    DNS failures surface as httpx.ConnectError."""
    parsed = httpx.URL(str(url))
    if parsed.scheme not in ("http", "https"):
        raise EgressBlocked(f"scheme {parsed.scheme or '(none)'!r} is not allowed")
    if parsed.userinfo:
        raise EgressBlocked("credentials in the URL are not allowed")
    host = parsed.host
    if not host:
        raise EgressBlocked("the URL has no host")
    literal = _literal_ip(host)
    if literal is not None:
        addresses = [literal]
    else:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            addresses = await _resolve(host, port)
        except (OSError, UnicodeError) as exc:
            raise httpx.ConnectError(f"could not resolve {host}") from exc
    if not addresses or not all(ip_is_public(a) for a in addresses):
        raise EgressBlocked(f"{host} is not a public address")
    return parsed


async def safe_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int,
    max_redirects: int = MAX_REDIRECTS,
) -> tuple[httpx.Response, str]:
    """Checked GET on every hop; returns the response and its text cut at `max_bytes`."""
    current = httpx.URL(url)
    for _ in range(max_redirects + 1):
        await check_url(current)
        async with client.stream("GET", current, follow_redirects=False) as resp:
            location = resp.headers.get("location")
            if resp.is_redirect and location:
                current = current.join(location)
                continue
            body = bytearray()
            async for chunk in resp.aiter_bytes():
                body.extend(chunk)
                if len(body) >= max_bytes:
                    break
            encoding = resp.encoding or "utf-8"
            return resp, bytes(body[:max_bytes]).decode(encoding, errors="replace")
    raise EgressBlocked(f"more than {max_redirects} redirects")


class GuardedTransport(httpx.AsyncHTTPTransport):
    """Transport for SDK clients on a user-chosen base URL; checks every request."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await check_url(request.url)
        return await super().handle_async_request(request)


def allowed_provider_hosts() -> set[str]:
    """Operator allowlist (ALLOWED_PROVIDER_HOSTS) of host or host:port entries."""
    from api.core.config import settings

    raw = settings.allowed_provider_hosts or ""
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def provider_host_allowlisted(url: str) -> bool:
    parsed = httpx.URL(url)
    host = (parsed.host or "").lower()
    allowed = allowed_provider_hosts()
    if host in allowed:
        return True
    return parsed.port is not None and f"{host}:{parsed.port}" in allowed


def validate_provider_base_url(url: str, default: str = "") -> str:
    """Syntax checks for a user's provider base URL; raises ValueError.

    Blank and the provider default always pass. Otherwise https or an allowlisted
    host; no userinfo, query or fragment; IP literals public unless allowlisted.
    Hostnames are checked again at request time.
    """
    value = url.strip()
    if not value or value.rstrip("/") == default.rstrip("/"):
        return value
    if "?" in value or "#" in value:
        raise ValueError("Base URL must not contain '?' or '#'.")
    try:
        parsed = httpx.URL(value)
    except httpx.InvalidURL as exc:
        raise ValueError("Base URL is not a valid URL.") from exc
    if parsed.userinfo:
        raise ValueError("Base URL must not contain credentials.")
    if not parsed.host:
        raise ValueError("Base URL needs a host.")
    if provider_host_allowlisted(value):
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Base URL must use http or https.")
        return value
    if parsed.scheme != "https":
        raise ValueError(
            "Base URL must use https (ask the operator to add the host to "
            "ALLOWED_PROVIDER_HOSTS for a local model server)."
        )
    literal = _literal_ip(parsed.host)
    if literal is not None and not ip_is_public(literal):
        raise ValueError("Base URL must point at a public address.")
    return value


def needs_guard(base_url: str, default: str = "") -> bool:
    """True for a user-chosen URL that is neither the provider default nor allowlisted."""
    value = (base_url or "").strip()
    if not value or value.rstrip("/") == default.rstrip("/"):
        return False
    return not provider_host_allowlisted(value)


# Fixed advice for common provider failures; the body is only matched, never shown.
_OUT_OF_CREDIT_PHRASES = ("credit balance is too low", "insufficient_quota", "exceeded your current quota")
_OUT_OF_CREDIT = "The provider account is out of credit or quota: top it up in the provider's billing settings."
_STATUS_HINTS = {
    401: "The provider rejected the API key: check it in your model settings.",
    403: "The API key has no access to this model.",
    404: "The provider doesn't recognise this model: check its name in your model settings.",
    429: "The provider is rate-limiting this key: wait a moment and try again.",
    # Gemini answers 503 UNAVAILABLE when the model is under high demand.
    503: "The provider is overloaded right now: try again shortly.",
    529: "The provider is overloaded right now: try again shortly.",
}


def _upstream_hint(exc: BaseException, status: int, response) -> str | None:
    detail = str(exc)
    if isinstance(response, httpx.Response):
        try:
            detail += response.text
        except httpx.ResponseNotRead:
            pass
    if any(phrase in detail.lower() for phrase in _OUT_OF_CREDIT_PHRASES):
        return _OUT_OF_CREDIT
    return _STATUS_HINTS.get(status)


def public_error(exc: BaseException) -> str:
    """Client-safe text for an exception. Upstream HTTP errors report only type and
    status, never the body (a user-chosen server controls it)."""
    status = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status is None and isinstance(response, httpx.Response):
        status = response.status_code
    if status is not None:
        hint = _upstream_hint(exc, status, response)
        return f"{type(exc).__name__}: the upstream service answered HTTP {status}." + (f" {hint}" if hint else "")
    if isinstance(exc, httpx.HTTPError) or type(exc).__module__.split(".")[0] in (
        "openai",
        "anthropic",
    ):
        return f"{type(exc).__name__}: the upstream service could not be reached."
    # Some exceptions (a bare TimeoutError) have no message at all.
    return str(exc) or type(exc).__name__
