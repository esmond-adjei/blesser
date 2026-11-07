from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api import __version__
from api.account.routes import router as account_router
from api.agents.routes import router as agents_router
from api.applications.routes import router as applications_router
from api.assistant.routes import router as assistant_router
from api.auth import schemas as auth_schemas
from api.auth.profile import MAX_AVATAR_BYTES
from api.auth.routes import get_current_user
from api.auth.routes import router as auth_router
from api.billing.routes import router as billing_router
from api.candidates.routes import router as candidates_router
from api.core.body_limit import MULTIPART_OVERHEAD, BodySizeLimitMiddleware
from api.core.config import log_config_warnings, settings
from api.core.db import init_db
from api.core.exceptions import AuthError, DomainError, RateLimitError
from api.cv.routes import router as cv_router
from api.exports.routes import router as exports_router
from api.flows.routes import router as flows_router
from api.metering.routes import router as metering_router
from api.notifications.routes import router as notifications_router
from api.opportunities.routes import router as opportunities_router
from api.outreach.routes import router as outreach_router
from api.prospects.routes_professors import router as professors_router
from api.prospects.routes_programs import router as programs_router
from api.prospects.routes_schools import router as schools_router
from api.providers.routes import router as providers_router
from api.runs.routes_runs import router as runs_router
from api.runs.routes_tasks import router as tasks_router
from api.runs.routes_tasks import workers_router
from api.todos.routes import router as todos_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print(f"==== [api] version {__version__} ====", flush=True)
    log_config_warnings()
    # Log the isolation mode so a deployment without network namespaces is visible.
    from api.cv.sandbox import sandbox_status

    status = sandbox_status()
    print(
        f"==== [cv-sandbox] status ====\n"
        f"[cv-sandbox] mode={status['mode']} network_isolated={status['network_isolated']} "
        f"unprivileged={status['unprivileged']}",
        flush=True,
    )
    yield


app = FastAPI(
    title="Graduator",
    lifespan=lifespan,
    version=__version__,
    description="Agentic research and outreach for graduate programs",
)

# Before CORS, so CORS stays outermost and a 413 still carries its headers.
app.add_middleware(
    BodySizeLimitMiddleware,
    default_limit=settings.max_request_bytes,
    route_limits={
        ("POST", "/api/assistant/attachments"): 2 * 1024 * 1024 + MULTIPART_OVERHEAD,
        ("POST", "/api/assistant/conversations/{conversation_id}/chat"): 9 * 1024 * 1024,
        ("POST", "/api/assistant/conversations/{conversation_id}/confirm"): 9 * 1024 * 1024,
        ("POST", "/api/cv/documents"): settings.cv_max_upload_bytes
        + MULTIPART_OVERHEAD,
        ("PUT", "/api/auth/me/avatar"): MAX_AVATAR_BYTES + MULTIPART_OVERHEAD,
    },
)
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


@app.get("/health", tags=["ops"])
async def health(current: auth_schemas.UserOut = Depends(get_current_user)):
    """Queue depth and worker liveness for the caller's own work."""
    from api.agent.llm.factory import get_provider_info
    from api.candidates.scoring import get_embedding_info
    from api.runs.health import get_health

    info = await get_health(current.id)
    info["version"] = __version__
    info.update(get_provider_info())
    info.update(get_embedding_info())
    info["search_configured"] = bool(settings.search_api_key)
    info["typesafe_enabled"] = bool(
        settings.typesafe_rationale_check and settings.typesafe_api_key
    )
    return info


@app.get("/ready", tags=["ops"])
async def ready():
    """Public readiness probe: 200 when the database answers, else 503."""
    from api.runs.health import check_database

    database = await check_database()
    if database.get("reachable"):
        return {"ready": True}
    return JSONResponse(status_code=503, content={"ready": False})


app.include_router(runs_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(workers_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(assistant_router, prefix="/api")
app.include_router(applications_router, prefix="/api")
app.include_router(schools_router, prefix="/api")
app.include_router(programs_router, prefix="/api")
app.include_router(providers_router, prefix="/api")
app.include_router(professors_router, prefix="/api")
app.include_router(candidates_router, prefix="/api")
app.include_router(cv_router, prefix="/api")
app.include_router(outreach_router, prefix="/api")
app.include_router(account_router, prefix="/api")
app.include_router(metering_router, prefix="/api")
app.include_router(billing_router, prefix="/api")
app.include_router(exports_router, prefix="/api")
app.include_router(flows_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(opportunities_router, prefix="/api")
app.include_router(todos_router, prefix="/api")


def main() -> None:
    """Start the API: `uv run api` (dev: `uv run api --reload`)."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Graduator API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run(
        "api.main:app", host=args.host, port=args.port, reload=args.reload
    )


if __name__ == "__main__":
    main()
