# syntax=docker/dockerfile:1.7

# One image, three process types: the API, the Celery worker, and Celery beat.
# The start command picks the role; the roles are listed at the bottom.

FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /bin/uv

# Builder-only: nothing in the runtime stage needs a compiler.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies come from the lockfile alone, so this layer stays cached until
# pyproject.toml or uv.lock changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


FROM python:3.14-slim AS runtime

# No libpq: asyncpg speaks the Postgres wire protocol directly.
RUN useradd --create-home --uid 10001 app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv

# `backend` is installed into the venv, so src/ is not copied. alembic.ini and
# migrations/ are, because the migration job runs from this same image.
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations ./migrations

USER app

EXPOSE 8000

# Role: API. One uvicorn worker per container, scaled by replica count, so the
# connection ceiling stays replicas x (DB_POOL_SIZE + DB_MAX_OVERFLOW) rather
# than multiplying by an in-process worker count as well.
# Behind a load balancer, add --proxy-headers and set --forwarded-allow-ips to
# the proxy's address; audit events read the client address from the ASGI scope.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

# Role: Celery worker, scales freely
#   celery -A backend.mail.celery_app worker --loglevel INFO --concurrency 4
#
# Role: Celery beat, exactly one replica, ever
#   celery -A backend.mail.celery_app beat --loglevel INFO \
#     --schedule /tmp/celerybeat-schedule
#
# Role: migrations, once per deploy, before the rollout
#   alembic upgrade head
