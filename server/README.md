# Server

The HTTP API and the background worker. The server keeps a cache and index of
each collection, syncs it with the owner's Google Sheet, generates printable
labels and draws captions on photos. The spreadsheet stays the source of truth.

Planned stack: Python, FastAPI, Pydantic, SQLAlchemy with Alembic migrations,
PostgreSQL (SQLite for a minimal install).

## Status

A working prototype for one owner. It reads collections from Google Sheets
through a service account, keeps a copy in its database, checks the sheets for
changes in the background, and serves lookups by tag and the phone's sync.
Labels, photo captions and assigning numbers come later.

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

## Running it

You need Docker with Compose, and a Google Cloud project.

1. **Create a service account.** In the
   [Google Cloud console](https://console.cloud.google.com/), enable the
   **Google Sheets API** and the **Google Drive API** for your project. Create
   a service account and a JSON key for it. Save the key as
   `deploy/service-account.json`, which git ignores. Never commit it.
2. **Share the sheet.** In Google Sheets, share each collection's spreadsheet
   with the service account's email (`…@….iam.gserviceaccount.com`) as
   **Viewer**. The tab's layout is described in
   [docs/sheet-format.md](../docs/sheet-format.md).
3. **Configure.** In `deploy/`, copy `.env.example` to `.env`. Set
   `SQUAREPOT_API_TOKEN` (for example, `openssl rand -hex 32`) and list your
   collections in `SQUAREPOT_COLLECTIONS`, with the spreadsheet id from the
   sheet's URL and the tab's name.
4. **Start.** From `deploy/`:

   ```sh
   docker compose up -d --build
   ```

The API listens on `http://127.0.0.1:8000`. Check it:

```sh
curl http://127.0.0.1:8000/api/v1/health
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/collections
```

Each collection's `error` explains a failed sync, such as a sheet that is not
shared with the service account or a tab without a `genus` column. Problems
with single cells do not stop the import.

The database lives in the `data` volume. With the default SQLite, back it up
with `docker compose cp server:/data/squarepot.db .`: it holds the registry of
issued numbers, which the sheets cannot fully restore
([ADR 0002](../docs/adr/0002-plant-number-allocation.md)).

The prototype speaks plain HTTP. To reach it from a phone on your network, set
`SQUAREPOT_LISTEN=0.0.0.0:8000`, but do not expose it to the internet until
HTTPS is in place.

## How it works

- **Sync.** Every `SQUAREPOT_SYNC_INTERVAL_SECONDS` (60 by default), the
  server asks Drive for each spreadsheet's `modifiedTime`, a cheap call. Only
  when that has changed does it read the tab, in one Sheets call, and apply the
  differences to its copy. That stays well within the default quotas. When
  Google cannot be reached, the server keeps serving its last copy and reports
  the error.
- **Storage adapter.** The sync talks to a `CollectionStore` interface
  ([ADR 0003](../docs/adr/0003-spreadsheet-as-source-of-truth.md)). Google
  Sheets is its only implementation, and the tests use an in-memory one.
- **Change sequence.** Every change to a collection or plant takes the next
  number of one sequence, and removed rows are kept as tombstones. A sync
  cursor is a position in that sequence, so a delta is everything after it.
- **Plant ids.** A plant with a tag is identified by its collection and tag,
  wherever it moves in the sheet. A plant without one is identified by its
  contents.
- **Migrations.** The server applies its Alembic migrations at startup.

## Development

The server uses [uv](https://docs.astral.sh/uv/). From this directory:

```sh
uv sync                     # create .venv with the server and its dev tools
uv run pytest               # run the tests
uv run mypy                 # type-check
uv run python -m squarepot_server.openapi > openapi.json  # after an API change
SQUAREPOT_DATABASE_URL=sqlite:///dev.db uv run alembic revision --autogenerate -m "…"
```

To run it outside Docker, export the variables from
[`deploy/.env.example`](../deploy/.env.example) and start
`uv run uvicorn squarepot_server.app:create_app --factory --reload`.

Lint and formatting run with the repository's pre-commit hooks.
