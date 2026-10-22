# The API server. Build from the repository root, which holds schema/:
#   docker build -f server/Dockerfile .
FROM ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv

FROM python:3.14.7-slim-trixie@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d

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
