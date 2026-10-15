# The API server. Build from the repository root, which holds schema/:
#   docker build -f server/Dockerfile .
FROM ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 AS uv

FROM python:3.14.8-slim-trixie@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170

COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app/server
# Dependencies first, so that code changes do not reinstall them.
COPY server/pyproject.toml server/uv.lock server/README.md server/LICENSE ./
RUN uv sync --locked --no-dev --no-install-project

COPY schema/fields.yaml /app/schema/fields.yaml
COPY server/alembic.ini ./
COPY server/src ./src
RUN uv sync --locked --no-dev

RUN useradd --system --uid 10001 squarepot && mkdir /data && chown squarepot /data
USER squarepot
ENV PATH=/app/server/.venv/bin:$PATH \
    SQUAREPOT_DATABASE_URL=sqlite:////data/squarepot.db
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"]

CMD ["uvicorn", "squarepot_server.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
