"""Domain errors; api/main.py maps `status_code` to HTTP so services never import FastAPI."""


class DomainError(Exception):
    status_code: int = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code = 404


class BadRequestError(DomainError):
    status_code = 400

    def __init__(self, message: str, field: str | None = None, value: object = None):
        super().__init__(message)
        self.field = field
        self.value = value


class ConflictError(DomainError):
    """409 with a structured payload, e.g. {"message": ..., "candidates": N}."""

    status_code = 409

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = dict(details or {})


class AuthError(DomainError):
    """401: missing, expired, or forged credentials."""

    status_code = 401


class UpgradeRequiredError(DomainError):
    """402: the account's plan doesn't include this; `details` feeds the upgrade prompt."""

    status_code = 402

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = dict(details or {})


class ForbiddenError(DomainError):
    """403: signed in, but this action needs more (e.g. a verified email)."""

    status_code = 403


class UnprocessableError(DomainError):
    """422: valid request, but the input can't be processed safely."""

    status_code = 422


class RateLimitError(DomainError):
    """429: throttle tripped (login lockout, per-account rate limits)."""

    status_code = 429

    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after
