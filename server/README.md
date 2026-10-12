# Server

The HTTP API and the background worker. The server keeps a cache and index of
each collection, syncs it with the owner's Google Sheet, generates printable
labels and draws captions on photos. The spreadsheet stays the source of truth.

Planned stack: Python, FastAPI, Pydantic, SQLAlchemy with Alembic migrations,
PostgreSQL (SQLite for a minimal install).

## Status

Only the API contract exists so far. The routes are declared and documented,
but apart from `/api/v1/health` they answer `501 Not Implemented`. That
answer is temporary and is not part of the contract.

## API contract

[`openapi.json`](openapi.json) is the contract that the Android app, the bot
and the web app are built against. It is generated from the code, and a test
fails when the committed file is out of date.

| Route | What it does |
| --- | --- |
| `GET /api/v1/health` | Checks that the server is up. Needs no token. |
| `GET /api/v1/schema` | Returns the field schema (`schema/fields.yaml` as JSON) that clients render names and captions with. |
| `GET /api/v1/collections` | Lists collections and how fresh the server's copy of each is. |
| `GET /api/v1/plants/by-tag/{tag}` | Finds the plant with a label number. Leading zeros may be left out. |
| `GET /api/v1/sync?cursor=…` | Returns the changes to the phone's local copy since a cursor, or a full copy ([ADR 0005](../docs/adr/0005-offline-first-phone.md)). |

Every route except `health` needs the operator's API token as
`Authorization: Bearer <token>`. Every error has the same body:
`{"code": "not_found", "message": "…"}`. Large responses are gzip-compressed
when the client accepts it.

## Development

The server uses [uv](https://docs.astral.sh/uv/). From this directory:

```sh
uv sync                     # create .venv with the server and its dev tools
uv run pytest               # run the tests
uv run mypy                 # type-check
uv run python -m squarepot_server.openapi > openapi.json  # after an API change
```

Lint and formatting run with the repository's pre-commit hooks.
