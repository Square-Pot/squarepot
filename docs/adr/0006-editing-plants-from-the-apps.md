# 0006. Editing plants from the apps writes cells to the sheet

- **Status:** Proposed
- **Date:** 2026-10-26

## Context

Until now, plant data has been edited only in the sheet. The apps read it, and
the one planned write is assigning numbers
([ADR 0003](0003-spreadsheet-as-source-of-truth.md)). The owner now wants to
add a plant and edit its fields from the web app and the phone, with a number
issued for it, and the sheet updated.

The sheet stays the source of truth, and the owner keeps editing it by hand,
sometimes at the same time as an app. A link only gives read access, so
writing needs the service account. The phone works from a local copy
([ADR 0005](0005-offline-first-phone.md)), and the Sheets API allows about 60
writes a minute for each user.

## Decision

- **Edits go to the sheet first, cell by cell.** The server writes only the
  cells an edit changes, never a whole row, so edits made by hand to other
  cells of the same row are kept. The server's copy is then updated by reading
  the tab again at once, and the response carries the plant as read back.
- **Each edit names what it saw, and the sheet wins.** An edit carries, for
  each field it changes, the value the client last saw. Before writing, the
  server reads the target row again: by its number when it has one, otherwise
  by its row together with its known cells as of the last sync
  ([sheet-format.md](../sheet-format.md#how-square-pot-writes)). If a changed
  cell no longer holds the value the client saw, or the row cannot be found,
  nothing is written. The client gets `409` with the plant as it now is, and
  the owner decides again.
- **A new plant is a new row at the end of the tab.** Its values go into the
  columns that exist. Square-Pot still never adds, renames or reorders
  columns: a field with no column in the sheet cannot be set, and the app says
  which column to add.
- **A number is issued on request, when the plant is created or later.** It is
  taken from the instance's registry and recorded before it is written
  ([ADR 0002](0002-plant-number-allocation.md)), so a failed write wastes it
  but never issues it twice. The `tag` cell is written as plain text, like
  every number the server writes.
- **Values are checked against the schema before writing.** An edit is
  written only if every value reads back as itself: a date as `YYYY-MM-DD`, a
  decimal with a dot, a status from its list. Otherwise `422`, naming each
  field. Custom columns take any text.
- **Deleting a plant is not offered.** A plant leaves the collection through
  its `status` (sheet-format, "The status"); its row stays.
- **Only collections read with the service account are editable.** The API
  says per collection whether it can be edited, and refuses an edit of a
  collection read by link with `409`.
- **Edits need the server.** The phone edits only while online in this first
  step. It does not queue edits offline, so there are no offline conflicts to
  merge.

## Consequences

- An owner who wants editing must set up the service account: a Google Cloud
  project, a service account with the Sheets and Drive APIs, its key on the
  server, and the sheet shared with it as editor. For the owner's own
  instance this replaces the link mode.
- The storage adapter gains two operations: append a row, and update cells of
  a row after checking them. The link and file stores do not implement them.
- Hand edits and app edits can meet. The rare loser is told, and nothing is
  overwritten unseen.
- Rows without a number are hard to find again after the owner edits them by
  hand. Issuing a number when a plant is created avoids this, so the apps
  offer it by default.
- Each edit costs a read and a write of the Sheets API, and a read of the tab.
  At a person's pace this is far below the quotas.
- The server logs each write with the plant id and the fields' keys, never
  their values.

## Alternatives considered

- **Write the whole row.** Simpler, but it would overwrite hand edits made to
  other cells of the row since the last sync.
- **The server's database as the source of truth for edits, copied to the
  sheet later.** Edits would work offline and without Google, but the sheet
  would no longer be the truth, which ADR 0003 rules out.
- **Google OAuth for the owner's own account instead of a service account.**
  No sharing step, but it needs an OAuth app with a consent screen and a
  refresh token on the server, which is harder to set up and to keep working.
- **Queue edits on the phone while offline.** More convenient in a
  greenhouse without signal, but it brings offline conflicts back. It can be
  added later on top of the same check.
- **Add missing columns automatically.** Fewer steps for the owner, but
  Square-Pot would start changing the sheet's layout, which it has promised
  not to do.
