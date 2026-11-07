# Single image for both processes; the command decides the role:
#   api:    uvicorn api.main:app
#   worker: python -m api.worker
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# curl powers the compose HEALTHCHECK against /ready.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Deps first for layer caching (README is package metadata).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY api/ ./api/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
