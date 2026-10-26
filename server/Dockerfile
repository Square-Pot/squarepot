# The API server, with the web app it serves at /. Build from the repository
# root, which holds schema/ and web/:
#   docker build -f server/Dockerfile .
FROM node:24.22.1-trixie-slim@sha256:43b9ba1142b8dcf33fa8f922ca1be85714adc444e0586c7cf7726daaeabc1bea AS web

WORKDIR /app/web
# Dependencies first, so that code changes do not reinstall them.
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
# The API client is generated from the contract during the build.
COPY server/openapi.json /app/server/openapi.json
COPY web ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv

FROM python:3.12.15-slim-trixie@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

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
COPY --from=web /app/web/dist /app/web

RUN useradd --system --uid 10001 squarepot && mkdir /data && chown squarepot /data
USER squarepot
ENV PATH=/app/server/.venv/bin:$PATH \
    SQUAREPOT_DATABASE_URL=sqlite:////data/squarepot.db \
    SQUAREPOT_PHOTOS_DIR=/data/photos \
    SQUAREPOT_WEB_DIR=/app/web
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"]

CMD ["uvicorn", "squarepot_server.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
