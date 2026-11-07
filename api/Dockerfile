# Single image for both processes — the command decides the role:
#   api:    uvicorn api.main:app
#   worker: python -m api.worker
# Compose sets the command per service (see root docker-compose.yml).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# curl powers the compose HEALTHCHECK against /ready. fonts-dejavu-core
# gives the PDF exports (dossiers, CVs) glyphs beyond Latin.
RUN apt-get update && apt-get install -y --no-install-recommends curl fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Unprivileged account for the CV sandbox child (api/cv/sandbox.py): every
# uploaded DOCX or PDF is parsed as this user, never as root.
RUN useradd --system --no-create-home --shell /usr/sbin/nologin cvsandbox

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Deps first for layer caching (README is package metadata for hatchling).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY api/ ./api/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini

ENV PATH="/app/.venv/bin:$PATH" \
    CV_STORAGE_DIR=/app/cv_storage

# Mount point for the compose `cv-storage` volume. CV files must live on a
# volume (or another persistent absolute path): anything written inside
# the container layer is lost on the next rebuild.
RUN mkdir -p /app/cv_storage

EXPOSE 8000

# Default = API. Compose overrides this for the worker service.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
