"""Request-size ceiling enforced before anything reads the body.

FastAPI parses multipart forms before dependencies run, so route-level checks
come too late. Over-limit Content-Length gets 413 unread; a chunked or lying
body is cut off with 413 once it crosses the limit.
"""

from __future__ import annotations

import json

from starlette.routing import compile_path
from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: Room for multipart boundaries and the other form fields.
MULTIPART_OVERHEAD = 64 * 1024


class _TooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        default_limit: int,
        route_limits: dict[tuple[str, str], int] | None = None,
    ) -> None:
        self.app = app
        self.default_limit = default_limit
        self.route_limits = route_limits or {}
        self.pattern_limits = [
            (method, compile_path(path)[0], limit)
            for (method, path), limit in self.route_limits.items() if "{" in path
        ]

    def limit_for(self, method: str, path: str) -> int:
        method, path = method.upper(), path.rstrip("/")
        for route_method, pattern, limit in self.pattern_limits:
            if method == route_method and pattern.fullmatch(path):
                return limit
        return self.route_limits.get(
            (method, path), self.default_limit
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.limit_for(scope.get("method", "GET"), scope.get("path", ""))
        declared = _content_length(scope)
        if declared is not None and declared > limit:
            await _reject(send, limit)
            return

        seen = 0
        started = False

        async def limited_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    raise _TooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _TooLarge:
            if not started:
                await _reject(send, limit)


def _content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _reject(send: Send, limit: int) -> None:
    body = json.dumps(
        {"detail": f"Request body too large (limit {limit // 1024 // 1024 or 1} MB)."}
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"connection", b"close"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
