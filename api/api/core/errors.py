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
