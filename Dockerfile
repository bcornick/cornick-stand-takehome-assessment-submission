# ABOUTME: Image for the app: Python 3.12 slim with the locked dependencies and src/ without any cases/ folder.
# ABOUTME: GIT_COMMIT is a build argument because .git is outside the build context.

# Copy src/ and delete every cases/ folder so no layer of the app image holds one.
FROM python:3.12-slim AS source
COPY src /src
RUN find /src -type d -name cases -prune -exec rm -rf {} +

FROM python:3.12-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /uvx /bin/
RUN apt-get update \
    && apt-get install -y --no-install-recommends sqlite3 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=0 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH=/app/.venv/bin:$PATH

# Dependencies first, so this layer caches until the lockfile changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

COPY pyproject.toml uv.lock ./
COPY --from=source /src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY docs/brief/field_registry.json /app/registry/field_registry.json

ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=$GIT_COMMIT

EXPOSE 8000
CMD ["uvicorn", "--factory", "uwh.api.app:create_app", "--host", "0.0.0.0", "--port", "8000"]
