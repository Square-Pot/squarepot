# Server

The HTTP API and the background worker. The server keeps a cache and index of
each collection, syncs it with the owner's Google Sheet, generates printable
labels and draws captions on photos. The spreadsheet stays the source of truth.

Planned stack: Python, FastAPI, Pydantic, SQLAlchemy with Alembic migrations,
PostgreSQL (SQLite for a minimal install).

## Status

A working prototype for one owner. It reads collections from Google Sheets,
shared by link or through a service account, keeps a copy in its database,
checks the sheets for changes in the background, serves lookups by tag and the
phone's sync, and prints label sheets. Photo captions and assigning numbers
come later. A demo mode reads fictional plants from a CSV file instead,
without a Google account.

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
| `GET /api/v1/labels/templates` | Lists the built-in label sizes and sheet layouts. |
| `POST /api/v1/labels` | Prints labels for plants, as a PDF or one SVG page. |
| `POST /api/v1/collections/{collection_id}/plants` | Adds a plant as a new row of the sheet, with the next free number ([ADR 0006](../docs/adr/0006-editing-plants-from-the-apps.md)). |
| `PATCH /api/v1/plants/{plant_id}` | Changes cells of a plant's row, unless the sheet changed them first, or gives it a number. |
| `PUT /api/v1/photos/{photo_id}?tag=…` | Uploads a photo of a numbered plant; the body is the image ([ADR 0007](../docs/adr/0007-plant-photos.md)). |
| `GET /api/v1/plants/by-tag/{tag}/photos` | Lists a plant's photos in the order taken, with addresses that expire. |
| `PATCH`, `DELETE /api/v1/photos/{photo_id}`, `POST …/restore` | Changes a photo's comment or time taken, deletes it, or restores it within 30 days. |
| `PUT /api/v1/plants/by-tag/{tag}/main-photo` | Chooses the plant's main photo; else the newest is shown. |

Every route except `health` needs the operator's API token as
`Authorization: Bearer <token>`. A client address that sends 10 wrong or
missing tokens must then wait: it gets one more try a minute, and `429` with
`Retry-After` until then, even with the right token. Behind a reverse proxy,
the address is the one the proxy forwards (`SQUAREPOT_TRUSTED_PROXIES` in
[deploy](../deploy/.env.example)). Every error has the same body:
`{"code": "not_found", "message": "…"}`. Large responses are gzip-compressed
when the client accepts it.

## Running it

You need Docker with Compose.

1. **Share the sheet.** In Google Sheets, choose **Share**, then under
   **General access** choose **Anyone with the link**, as **Viewer**. The
   tab's layout is described in [docs/sheet-format.md](../docs/sheet-format.md).
   Anyone who learns the sheet's id can then read it; for a private sheet, see
   [A private sheet](#a-private-sheet) below.
2. **Configure.** In `deploy/`, copy `.env.example` to `.env`. Set
   `SQUAREPOT_API_TOKEN` (for example, `openssl rand -hex 32`) and list your
   collections in `SQUAREPOT_COLLECTIONS`, with the spreadsheet id from the
   sheet's URL (`docs.google.com/spreadsheets/d/<id>/edit`). The first tab is
   read; to read another, add its `gid`, the number after `#gid=` in the URL
   when that tab is open.
3. **Start.** From `deploy/`:

   ```sh
   docker compose up -d --build
   ```

The API listens on `http://127.0.0.1:8000`. Check it:

```sh
curl http://127.0.0.1:8000/api/v1/health
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/collections
```

Each collection's `error` explains a failed sync, such as a sheet that is not
shared by link or a tab without a `genus` column. Problems with single cells
do not stop the import. A sheet read by link is downloaded with its values as
displayed, so a date must display as `YYYY-MM-DD` or `DD.MM.YYYY` and a
decimal with a dot ([docs/sheet-format.md](../docs/sheet-format.md#values)).

The database lives in the `data` volume. With the default SQLite, back it up
with `docker compose cp server:/data/squarepot.db .`: it holds the registry of
issued numbers, which the sheets cannot fully restore
([ADR 0002](../docs/adr/0002-plant-number-allocation.md)).

The prototype speaks plain HTTP. To reach it from a phone on your network, set
`SQUAREPOT_LISTEN=0.0.0.0:8000`, but do not expose it to the internet until
HTTPS is in place.

### A private sheet

A sheet that is not shared by link is read with a Google service account
instead, through the Sheets and Drive APIs.

1. **Create a service account.** In the
   [Google Cloud console](https://console.cloud.google.com/), enable the
   **Google Sheets API** and the **Google Drive API** for your project. Create
   a service account and a JSON key for it. Save the key as
   `deploy/service-account.json`, which git ignores. Never commit it.
2. **Share the sheet** with the service account's email
   (`…@….iam.gserviceaccount.com`): as **Editor** to add and edit plants from
   the apps, or as **Viewer** to only read it.
3. **Configure.** In `.env`, set `SQUAREPOT_STORE=google` and
   `COMPOSE_FILE=compose.yaml:compose.google.yaml`, which passes the key to the
   server. Each collection in `SQUAREPOT_COLLECTIONS` names its tab with
   `sheet` instead of `gid`.

Adding and editing plants writes to the sheet, and so needs the service
account: a link gives read-only access
([sheet-format.md](../docs/sheet-format.md#how-square-pot-writes)).

### Photos

Photos are off until `SQUAREPOT_PHOTOS` is set
([ADR 0007](../docs/adr/0007-plant-photos.md)):

- `disk` keeps them in the data volume. Simple, but they are lost with the
  host, so back the volume up.
- `s3` keeps them in a private bucket of an S3-compatible service, such as
  Yandex Object Storage. Create a bucket used only by Square-Pot, with
  versioning on and a lifecycle rule that removes old versions after 30 days,
  and a key that can reach only that bucket. Save the key as `deploy/photos-key`,
  the key id on its first line and the secret on its second, which git
  ignores. In `.env`, set `SQUAREPOT_PHOTOS=s3`, `SQUAREPOT_S3_BUCKET`, and
  add `compose.photos.yaml` to `COMPOSE_FILE`.

The server turns each photo upright, drops its EXIF data, including where it
was taken, and keeps a large JPEG and a thumbnail, one photo at a time.

Each photo and each sighting also has a small JSON file in the storage. If the
database is lost, rebuild the photo index and the sightings from them, while
the server runs:

```sh
docker compose exec server python -m squarepot_server.rebuild
```

It adds only what the database lacks, and prints how many of each it added.
Only the choice of each plant's main photo is lost: the newest photo is shown
again. With `s3`, the key must be allowed to list the bucket.

### Demo mode

To try the server, or to test a client end to end, without a Google account:
the server reads [`demo/plants.csv`](demo/plants.csv), 80 fictional plants
laid out like a sheet's tab. 77 of them have the numbers `000001` to `000077`,
so labels printed for them scan to real plants. The other three have no
number yet. From `deploy/`:

```sh
export SQUAREPOT_API_TOKEN=$(openssl rand -hex 32)
docker compose -f compose.demo.yaml up -d --build
curl -H "Authorization: Bearer $SQUAREPOT_API_TOKEN" http://127.0.0.1:8000/api/v1/plants/by-tag/000042
```

Compose needs `SQUAREPOT_API_TOKEN` for every command on this file, so stop the
demo from the same shell with `docker compose -f compose.demo.yaml down`.

The file is mounted read-only, and the server checks it every 5 seconds: edit
it, and the change reaches `/api/v1/sync` as a delta, as an edit of the sheet
would. To reach the demo from a phone, set `SQUAREPOT_LISTEN=0.0.0.0:8000` as
well. Outside Docker, set `SQUAREPOT_STORE=file` and give each collection in
`SQUAREPOT_COLLECTIONS` a `file` instead of a `spreadsheet_id` and `sheet`;
keys meant for the other store are ignored. The file is UTF-8 with commas
between fields, as most spreadsheets export CSV; a file saved with semicolons
reads as one column and is reported as missing its `genus` column.

## How it works

- **Sync.** Every `SQUAREPOT_SYNC_INTERVAL_SECONDS` (60 by default), the
  server checks each collection for changes and applies only the differences
  to its copy. A sheet shared by link is downloaded as CSV, and its version is
  a hash of the download. With a service account, the server asks Drive for
  the spreadsheet's `modifiedTime`, a cheap call, and reads the tab, in one
  Sheets call, only when that has changed; that stays well within the default
  quotas. When Google cannot be reached, the server keeps serving its last
  copy and reports the error. A change to the field schema makes it read
  every sheet again.
- **Storage adapter.** The sync talks to a `CollectionStore` interface
  ([ADR 0003](../docs/adr/0003-spreadsheet-as-source-of-truth.md)). It has
  three implementations, chosen with `SQUAREPOT_STORE`: a Google Sheet by
  link (`link`, the default), a Google Sheet through a service account
  (`google`), and CSV files for the demo (`file`), whose version is a hash of
  the file's content. The tests also use an in-memory one.
- **Change sequence.** Every change to a collection or plant takes the next
  number of one sequence, and removed rows are kept as tombstones. A sync
  cursor is a position in that sequence, so a delta is everything after it.
- **Plant ids.** A plant with a tag is identified by its collection and tag,
  wherever it moves in the sheet. A plant without one is identified by its
  contents.
- **Migrations.** The server applies its Alembic migrations at startup.
- **Web app.** With `SQUAREPOT_WEB_DIR` set, as the image does, the server
  also serves the [web app](../web/)'s build at `/`: any path no route
  matches gets a file of the build, or `index.html` for the app's own
  addresses. Unknown paths under `/api/` stay API errors.
- **Labels.** Each label holds the plant's number in a 10×10 Data Matrix
  ([ADR 0001](../docs/adr/0001-label-code-format.md)) and a caption from the
  `label` preset. The `vertical` template has the code on top and the caption
  under it, the `horizontal` one the caption beside the code; both end in a
  white burial zone that goes into the substrate, under a dashed soil line.
  The horizontal one prints the `burial` preset there, each field with its
  label in bold (`language`: English by default, or Russian); the vertical
  one leaves it blank.
  A print request may choose instead what a label shows, in order:
  `caption_fields` for the caption, and `extra_fields` for more about the
  plant, printed in the burial zone of the horizontal label and after the
  caption of the vertical one. Both take schema fields and custom columns
  (`Name: value`). The plant's name is always included.
  By default (`auto`), each plant gets the template its `label_type` names,
  and each template's labels start on a page of their own.
  The code is always printed whole, with a white quiet zone of at least one
  module on the label: a layout too small for that is refused, never cropped,
  and only the caption shrinks or is cut short. Text is
  converted to outlines with the bundled [fonts](src/squarepot_server/labels/fonts/),
  so printing needs no fonts installed. A test renders every template as SVG
  and PDF and decodes every symbol with zxing-cpp.

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
`uv run uvicorn squarepot_server.app:create_app --factory --reload`. Set
`SQUAREPOT_API_DOCS=true` to browse the API at `/docs`; it is off by default.

Lint and formatting run with the repository's pre-commit hooks.
