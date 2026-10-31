# syntax=docker/dockerfile:1
# ScholarSync: the Vite bundle is built in the first stage, so the host needs no Node.

FROM node:22.23.4-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# vite.config.ts writes to ../static/dist, which is /build/static/dist here.
RUN npm run build

FROM python:3.13.18-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .
COPY --from=frontend /build/static/dist ./static/dist

# collectstatic needs settings to import; these values exist only for this build step.
RUN DJANGO_SECRET_KEY=build-only-not-a-secret \
    DATABASE_URL=postgres://build:build@localhost:5432/build \
    DJANGO_ENV_FILE=/nonexistent \
    python manage.py collectstatic --noinput

RUN useradd --system --no-create-home --uid 10001 scholarsync \
    && chown -R scholarsync /app
USER scholarsync

EXPOSE 8000
ENTRYPOINT ["sh", "/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
