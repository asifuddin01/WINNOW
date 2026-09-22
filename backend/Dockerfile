# syntax=docker/dockerfile:1
# Winnow API and worker image. Targets: `dev` (tools, reload) and `prod` (runtime only).

FROM python:3.12-slim-bookworm AS base
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH
RUN groupadd --system --gid 1000 winnow \
    && useradd --system --uid 1000 --gid winnow --home-dir /app --shell /usr/sbin/nologin winnow \
    # Uploaded files live here; a fresh volume inherits this ownership when it is mounted.
    && mkdir -p /data/uploads \
    && chown -R winnow:winnow /data
WORKDIR /app

FROM base AS dev
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project
COPY --chown=winnow:winnow . .
USER winnow
EXPOSE 8000
# Behind Caddy on the internal network: take the client address from X-Forwarded-For,
# which Caddy sets itself (it ignores the header from untrusted clients).
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--reload", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "*"]

FROM base AS prod
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project --no-dev
COPY --chown=root:root app ./app
COPY --chown=root:root alembic ./alembic
COPY --chown=root:root alembic.ini ./
USER winnow
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/healthz', timeout=2).status != 200)"]
# The API is reachable only through Caddy on the internal network, so trust its X-Forwarded-For.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "*"]
