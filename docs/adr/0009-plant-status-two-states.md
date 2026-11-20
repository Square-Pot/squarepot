# 0009. Plant status: two states, written through to the sheet

- **Status:** Accepted (the owner, 2026-11-19: «по статусам да, делайте так»)
- **Date:** 2026-11-19, accepted 2026-11-19

## Context

The owner decided on 2026-11-15 that a plant has **two states**: it is in the
collection, or it is gone — dead, withered, sold or given away. Why it is gone
matters as a note, not as a category. In the apps the living state is not
shown at all; a departed plant shows its status, and the web list gains
"Status" and "Status date" columns for the departed ones.

This replaces the four status values (`dead`, `gifted`, `sold`, `lost`) of
[ADR 0008](0008-inventory-sightings-and-photo-import.md). They were never
released: the format is pre-release, and the owner's sheet has no `status`
column yet, so nothing to migrate in any live sheet.

The sheet stays the source of truth ([ADR 0003](0003-spreadsheet-as-source-of-truth.md)):
a status change made in the web app is written **to the sheet first**, through
the write path of [ADR 0006](0006-editing-plants-from-the-apps.md), and the
cache is updated from the result. On conflict the sheet wins. This is the
first write the owner will make from the web app.

The bulk status endpoint of ADR 0008 already writes cells this way; this ADR
changes what a status **is**, and adds the comment.

## Decision

### Two states

- **A plant is in the collection, or it is gone.** Gone covers dead, withered,
  sold, gifted, lost — the reason belongs in the comment, not in the value.
- **A gone plant is a former plant**, as before: left out of the collection's
  plant count and of default lists, still served, found by its number,
  recognised by the camera, and its number is never issued again.

### The sheet columns

- **`status`: `0` or `1`.** `0` means gone, `1` means in the collection. An
  **empty cell reads as in the collection**, so a sheet needs no column of
  ones: rows are simply left empty until a plant departs. Square-Pot writes
  the literal `0` or `1` when it changes the cell. Booleans (`TRUE`/`FALSE`)
  are read as `1`/`0`. Any other value is reported as invalid and the plant
  counts as being in the collection — nothing leaves the collection
  unnoticed, as before. The four words of ADR 0008 are no longer read.
- **`status_date`: the date of the last status change**, in either direction.
  Square-Pot writes it with every change it writes: the date given in the
  request when one is (an inventory walk may backdate), else the server's
  day. A hand edit in the sheet that changes `status` and `status_date`
  together keeps the sheet's date. A hand edit that changes `status` alone
  gets the day the server first saw the new value, as now — and nothing is
  written back: Square-Pot writes only when a user acts through it
  (ADR 0006).
- **`status_comment`: free text, the comment to the last status change** —
  "sold at the fair", "dried out in July". Each change overwrites it; a
  comeback with no comment clears it. It is one note about the latest change,
  not a journal: the owner who wants history adds their own column, which
  Square-Pot then reads as a custom column.

All three columns are optional, as `status` and `status_date` are today. The
write path requires them to exist, as it does now (ADR 0008): a status change
on a tab without the columns is refused, telling the owner to add them.

### What the API serves

- **Status leaves `fields` and becomes a field of its own**, as `tag` already
  is. A plant carries:
  - `status`: `"gone"` or `null` — a plant in the collection carries `null`;
    the living state is not output, per the owner's decision;
  - `status_since`: the date of the last status change, `null` while the
    plant is in the collection (a comeback date lives in the sheet but is not
    served);
  - `status_comment`: the comment, `null` while there is none.
- `fields.status` and `fields.status_date` disappear from the `fields` dict.
  This is a breaking change to the OpenAPI contract; the clients (web,
  Android, bot) regenerate, as they do for any contract change.
- The collection keeps `plant_count` (plants in the collection) and
  `former_count` (gone plants), with the binary meaning.

### Changing a status

- **One endpoint, as in ADR 0008**: up to 500 plants, the status to set, an
  optional comment, an optional date, and for each plant the status the
  client last saw. The web app's plant card uses it with one plant.
- The values become `"gone"` (write `0`) and `null` (write `1`): the same
  request both departs and returns a plant.
- The write is unchanged mechanically: one read of the tab, each row written
  only if its status cell still holds what the client saw, one batched Sheets
  call writing only the cells that change (`status`, `status_date`,
  `status_comment`), then a forced re-sync updates the cache. Per-plant
  answers: `written`, `changed_in_sheet` (not written; the sheet wins, the
  client retries after a fresh sync), `not_found`.
- Service-account collections only, as every write (ADR 0006): a collection
  read by link answers `409 not_editable`.
- Setting a status is still a sighting of kind `status` (ADR 0008); the
  client records it, as it does for photos and marks.

### The cache

One migration adds the comment column to the cached plants and resets
`store_version`, so every tab is re-read under the new rules. The cached
status keeps the raw cell as last seen (`status_seen`), the resolved date
(`status_since`) and now the comment; the former count counts cells that
read as `0`.

## Consequences

- The owner's sheet gains three columns when the feature is wanted, and stays
  readable by a person with no software: `0`, a date, a note.
- The web list can show "Status" and "Status date" for departed plants only,
  straight from the plant's `status` and `status_since`.
- A wrong change is undone by the same request in the other direction; the
  old date and comment are overwritten, not kept.
- The reason a plant is gone is one free-text note, not structured data: no
  filters by reason. The owner's words live in the sheet, where the owner can
  always read and edit them.
- Clients see one breaking change (`fields.status`, `fields.status_date` out;
  `status`, `status_comment` in) and regenerate from the OpenAPI contract.
- `schema/fields.yaml` and `docs/sheet-format.md` change with this ADR: the
  `status` field takes the values `0`/`1` with labels, `status_comment` is a
  new text field, and the write rules above replace the ADR 0008 wording.

## Alternatives considered

- **Keep the four values and only display them as two.** No sheet change for
  the format, but the owner asked for two states, and the reason fits a note
  better than a category the apps must then translate.
- **Carry `1`/`0` for every plant in the API.** A uniform shape, but the
  owner asked for the living state not to be output, and `status: null` says
  exactly that; a client branches on one nullable field.
- **Keep reading the old words (`dead`, `погиб`, …) as `0`.** Kind to a
  hypothetical pre-release sheet, but the format never shipped, and two ways
  to say the same thing is a bug farm; the comment is the place for words.
- **A journal of status changes** (append a row per change, in the sheet or
  the server). Real history, but the events and watered-down genealogy are
  declared out of scope for the first release, and the sheet stays the
  single source: one status, one date, one note.
- **The date only in the server's cache**, written nowhere. Would spare a
  column, but then the sheet — the thing that must survive the software —
  does not tell when a plant left, and hand edits could not backdate.
