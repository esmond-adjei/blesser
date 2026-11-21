import logging

from starlette.responses import JSONResponse

log = logging.getLogger("api.errors")


class UnhandledErrorMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            log.exception(
                "Unhandled error on %s %s", scope.get("method"), scope.get("path")
            )
            if started:
                raise
            await JSONResponse(
                {"detail": "Something went wrong on our side. Try again."},
                status_code=500,
            )(scope, receive, send)


_PLAIN = (
    ("value is not a valid email address", "enter a valid email address like name@example.com"),
    ("Input should be a valid URL", "enter a full web address starting with https://"),
    ("Field required", "this is required"),
    ("Input should be a valid integer", "enter a whole number"),
    ("Input should be a valid number", "enter a number"),
    ("Input should be a valid date", "enter a valid date"),
    ("Input should be a valid boolean", "choose yes or no"),
)


def _label(loc) -> str:
    names = [p for p in loc if isinstance(p, str) and p not in {"body", "query", "path"}]
    return names[-1].replace("_", " ").capitalize() if names else "Input"


def _plain(error: dict) -> str:
    msg = str(error.get("msg", "")).removeprefix("Value error, ")
    for needle, replacement in _PLAIN:
        if needle in msg:
            return replacement
    ctx = error.get("ctx") or {}
    if error.get("type") == "string_too_long" and "max_length" in ctx:
        return f"keep it to {ctx['max_length']} characters or fewer"
    if error.get("type") == "string_too_short" and "min_length" in ctx:
        return f"use at least {ctx['min_length']} characters"
    return msg[:1].lower() + msg[1:]


def describe_validation_errors(errors: list[dict], limit: int = 3) -> str:
    """One readable sentence per invalid field, instead of pydantic's raw list."""
    seen: list[str] = []
    for error in errors:
        text = _plain(error)
        line = f"{_label(error.get('loc', ()))}: {text[:1].upper() + text[1:]}."
        if line not in seen:
            seen.append(line)
    return " ".join(seen[:limit])
