from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api import __version__
from api.applications.routes import router as applications_router
from api.auth.routes import router as auth_router
from api.core.body_limit import BodySizeLimitMiddleware
from api.core.config import log_config_warnings, settings
from api.core.db import init_db
from api.core.exceptions import AuthError, DomainError, RateLimitError
from api.notifications.routes import router as notifications_router
from api.opportunities.routes import router as opportunities_router
from api.scans.routes import router as scans_router
from api.todos.routes import router as todos_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print(f"==== [api] version {__version__} ====", flush=True)
    log_config_warnings()
    yield


app = FastAPI(
    title="Blesser",
    lifespan=lifespan,
    version=__version__,
    description="Opportunities for startups, researchers and students, found and checked by agents",
)

# Before CORS, so CORS stays outermost and a 413 still carries its headers.
app.add_middleware(BodySizeLimitMiddleware, default_limit=settings.max_request_bytes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.resolve_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def _domain_error(request: Request, exc: DomainError):
    details = getattr(exc, "details", None)
    detail = {"message": exc.message, **details} if details is not None else exc.message
    headers = None
    if isinstance(exc, AuthError):
        headers = {"WWW-Authenticate": "Bearer"}
    elif isinstance(exc, RateLimitError) and exc.retry_after:
        headers = {"Retry-After": str(exc.retry_after)}
    return JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers=headers)


@app.get("/ready", tags=["ops"])
async def ready():
    """Public readiness probe: 200 when the database answers, else 503."""
    from sqlalchemy import text

    from api.core.db import SessionLocal

    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"ready": False})
    return {"ready": True}


for router in (
    auth_router,
    opportunities_router,
    applications_router,
    todos_router,
    scans_router,
    notifications_router,
):
    app.include_router(router, prefix="/api")


def main() -> None:
    """Start the API: `uv run api` (dev: `uv run api --reload`)."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Blesser API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("api.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
