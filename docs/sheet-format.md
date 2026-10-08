# Spreadsheet format

> **Status: draft**, pending approval by the product owner.

Each Square-Pot collection is backed by a Google Sheet that its owner keeps in
their own Google Drive. The sheet is the source of truth
([ADR 0003](adr/0003-spreadsheet-as-source-of-truth.md)): the server reads it,
caches it and writes plant numbers into it, but the owner can always open,
edit and export the sheet without Square-Pot.

This document is the contract between the sheet and the software. The fields
themselves are defined in [`schema/fields.yaml`](../schema/fields.yaml); this
page says how they are laid out in a sheet.

## Layout

- **One collection is one tab.** When a collection is connected, the owner
  chooses the spreadsheet and the tab. Other tabs are ignored and never
  modified.
- **Row 1 is the header.** Each header cell holds a field `key` from the schema,
  such as `genus` or `seeding_date`. Matching ignores case and surrounding
  whitespace.
- **Each row below the header is one plant.** Fully empty rows are skipped.
- **Column order is free.** Columns are found by header, not by position, so the
  owner may reorder them, hide them or insert their own.

An example with a few columns:

| tag | field_number | genus | species | subspecies | ex | seeding_date |
| --- | --- | --- | --- | --- | --- | --- |
| 004217 | SB 1234 | Lithops | lesliei | | Mesa Garden | 2024-03-15 |
| 004218 | | Conophytum | bilobum | gracile | | |

## Columns

- **Known columns** are those whose header matches a field `key` or one of its
  `aliases`. Aliases exist so that sheets made before this format still work:
  `uid` is read as `tag`, `cultivated_variety` as `cultivar`, `information`
  as `notes`. Square-Pot never renames the owner's headers.
- **Unknown columns** are kept as they are. They are not imported, shown or
  written, and they never cause an error.
- **Missing columns** are treated as empty fields, except for required fields
  (`required: true` in the schema; today only `genus`). Without a `genus`
  column the tab is rejected with an explanation.
- **Duplicate headers** (two columns mapping to the same field) make the tab
  invalid until the owner removes one.

## Values

Values are read with the Sheets API's unformatted values and serial-number
dates, so they do not depend on the sheet's locale or display format.

| Type | In the sheet | Notes |
| --- | --- | --- |
| `text` | Any text | Trimmed. An empty cell means "no value". |
| `date` | A date cell, or text in ISO 8601 form `YYYY-MM-DD` | Text in the legacy form `DD.MM.YYYY` is also accepted on read. Anything else is reported as invalid for that cell only. |
| `decimal` | A number cell | A price's currency is in its own `currency` column, so each row can have its own. `currency` is read case-insensitively and stored in upper case (`eur` → `EUR`). |

Display rules such as italics or the `subsp.` prefix are applied by Square-Pot
when it renders a name, following botanical conventions (ICN, and ICNCP for
cultivars). The sheet holds plain values: `subspecies` contains `gracile`, not
`subsp. gracile`, and `cultivar` contains `Hana`, without quotes.

## The plant number

- The `tag` column holds the plant number: the six digits encoded on the
  plant's label, including leading zeros: `004217`. When Square-Pot writes a
  number, it sets that one cell's format to plain text, so the sheet does not
  drop the zeros. It does not change the format of any other cell. A number
  cell such as `4217` is read as `004217`.
- An empty `tag` means the plant has no label yet. Such rows are imported and
  searchable, but cannot be scanned.
- A value that is not six digits after padding, or is `000000` (reserved), is
  reported as invalid, and the row is imported without a number.
- Numbers are unique within a Square-Pot instance. How they are assigned, and
  what happens when imported collections collide, is decided in
  [ADR 0002](adr/0002-plant-number-allocation.md).
- A number is never reused, even after its row is deleted, because a printed
  label may still exist.

## How Square-Pot writes

Square-Pot writes to the sheet only when a user acts, never on its own.

In the first release there is exactly one write: **assigning numbers**. In the
web app's label designer, the owner selects plants that have no number and
asks for numbers before printing their labels. Square-Pot writes each new
number into the empty `tag` cell of that plant's row, and sets that cell's
format to plain text. Plant data is otherwise edited in the sheet itself.

Before writing, Square-Pot re-reads the target rows. A row has no number yet,
so it is identified by its position together with the values of its known
cells as of the last sync. If any of them has changed, or the `tag` cell is
no longer empty, nothing is written for that row, the collection is synced
again, and the owner is asked to retry. Edits made directly in the sheet always
win ([ADR 0003](adr/0003-spreadsheet-as-source-of-truth.md)).

Square-Pot never deletes rows, reorders rows, changes headers, or touches cells
outside the known columns. The only formatting it changes is that of the
`tag` cells it writes.

Adding plants and editing fields from Square-Pot's own clients may come later.
They will follow the same rule: re-check the row (then identified by its
`tag`) before writing, and let the sheet win.

## Validation and errors

Problems are reported per cell and never block the rest of the collection.
Invalid cells are shown to the owner with their row and column:

- An invalid cell in an optional field is treated as empty, and the row is
  imported with its remaining valid fields.
- A row whose required field (`genus`) is empty or invalid is reported and
  skipped, because Square-Pot cannot name the plant. If the row has a number,
  the number stays registered, so it is not issued to another plant.

Only tab-level problems (no `genus` column, duplicate headers) stop the
import.

## Versioning

The schema has a `version`. Adding an optional field is not breaking: old
sheets simply lack the column. Renaming or removing a field, or changing its
type, is breaking; it raises `version` and keeps the old header as an
alias for at least one release.
