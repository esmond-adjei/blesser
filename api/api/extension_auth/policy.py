from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.routing import compile_path

from api.auth.security import parse_access_claims
from api.core.exceptions import AuthError

EXTENSION_ROUTES = frozenset(
    {
        ("POST", "/api/app/autofill/fill"),
        ("GET", "/api/app/autofill/match"),
        ("POST", "/api/app/autofill/feedback"),
        ("POST", "/api/app/autofill/reports"),
        ("GET", "/api/app/profile"),
        ("GET", "/api/app/projects"),
        ("GET", "/api/app/projects/{project_id}"),
        ("GET", "/api/app/documents"),
        ("GET", "/api/app/documents/usage"),
        ("GET", "/api/app/documents/{document_id}/download"),
        ("GET", "/api/app/applications"),
        ("POST", "/api/app/applications"),
        ("GET", "/api/app/applications/{application_id}"),
        ("PATCH", "/api/app/applications/{application_id}"),
        ("GET", "/api/app/extension/me"),
        ("POST", "/api/app/extension/logout"),
    }
)
_bearer = HTTPBearer(auto_error=False)
_ALLOWED_PATHS = [(method, compile_path(path)[0]) for method, path in EXTENSION_ROUTES]


def extension_allowed(request: Request) -> bool:
    return any(
        method == request.method and pattern.fullmatch(request.scope["path"])
        for method, pattern in _ALLOWED_PATHS
    )


async def enforce_extension_boundary(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    if (
        credentials
        and parse_access_claims(credentials.credentials, "ext")
        and not extension_allowed(request)
    ):
        raise AuthError("Extension tokens cannot access this route.")
