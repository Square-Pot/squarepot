# Web app

The browser client. It shows the collections read-only: the list with search,
sorting and filters (custom sheet columns too, and the inventory filters: no
photo or an old one, not seen since a day, former plants), a plant card with its
label preview and its photos, and the print editor (`/c/<collection>/print`): pick plants, one label
type a sheet, what the labels show, the server's own A4 preview, and the PDF. Plant data is edited in the spreadsheet, not here. Later: the label
designer, onboarding and the spreadsheet connection.

Stack: TypeScript (strict), React, Vite. The API client is generated from
[`server/openapi.json`](../server/openapi.json) by `npm run gen` into
`src/api/schema.ts`, which is not committed.

## How it runs

The server image builds this app and serves it at `/`, next to the API at
`/api/` (see [`server/Dockerfile`](../server/Dockerfile)). On the first visit
the owner pastes the API token (`SQUAREPOT_API_TOKEN`); it is kept in that
browser's local storage and sent only as `Authorization: Bearer`, never in a
URL. A rejected token is forgotten and asked for again.

The app loads every plant once with `GET /api/v1/sync`, then fetches changes
every minute. Search, filters and sorting run in the browser, and their state
is in the address, so a filtered list can be bookmarked or sent.

The sheet's data stays read-only here; photos are the exception, because they
live on the server, not in the sheet ([ADR 0007](../docs/adr/0007-plant-photos.md)).
On a numbered plant's card the owner adds photos (JPEG, PNG or WebP, one upload
at a time, each with an id chosen in the browser so a retry makes no copy),
picks the main one, edits a photo's comment or date, and deletes or restores
one. The card loads the plant's photos with their signed addresses, which it
fetches again before they expire.

## Develop

```sh
npm ci
npm run dev        # proxies /api to a server on 127.0.0.1:8000
npm run typecheck
npm run lint
npm test
npm run build      # into dist/
```

CI runs the same checks in the `Web` job. The `Web lockfile` workflow resolves
`package-lock.json` on a runner after a change of `package.json`.
