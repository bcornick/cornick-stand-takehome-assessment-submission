# ABOUTME: Images for the app (Python 3.12 slim with the locked dependencies, src/ without any cases/ folder, and the frontend built in a Node stage) and for the eval runner (the app image plus evals/, the skills' cases and Stand's generator).
# ABOUTME: GIT_COMMIT is a build argument because .git is outside the build context.

# Copy src/ and delete every cases/ folder so no layer of the app image holds one.
FROM python:3.12-slim AS source
COPY src /src
RUN find /src -type d -name cases -prune -exec rm -rf {} +

# Node 22.23.3 bundles corepack 0.36.0, which can launch the pnpm 12 pinned in web/package.json.
FROM node:22.23.3-slim AS frontend
RUN corepack enable
WORKDIR /app/web
COPY web/package.json web/pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
COPY web ./
RUN pnpm build

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

# The reply bodies of the fixture-reply control; the default of UWH_FIXTURE_REPLIES.
COPY fixtures/replies /app/fixtures/replies

# The built frontend; the default of UWH_STATIC_DIR.
COPY --from=frontend /app/web/dist /app/static

ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=$GIT_COMMIT

EXPOSE 8000
CMD ["uvicorn", "--factory", "uwh.api.app:create_app", "--host", "0.0.0.0", "--port", "8000"]

# The eval runner: the app image with the skills' cases back in src/, the labels and graders in evals/,
# and Stand's generator, which the answer-key grader runs in process. Results append to evals/results.jsonl,
# which the eval service bind-mounts from the host.
FROM app AS eval
COPY src/uwh/skills ./src/uwh/skills
COPY sim-harness/shared ./sim-harness/shared
COPY sim-harness/leadgen ./sim-harness/leadgen
COPY evals ./evals
ENTRYPOINT ["python", "-m", "evals.run"]
