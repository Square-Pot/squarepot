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
  chooses the spreadsheet and the tab: by its name with a service account, or
  by its `gid` (the number after `#gid=` in the tab's URL) when the sheet is
  read by link; without a `gid`, the first tab is read. Other tabs are
  ignored and never modified.
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
- **Custom columns** are all the others: a column whose header is not a field
  `key` or alias is read as it is, under its header's name (see
  [Custom columns](#custom-columns)). A column with an empty header is ignored.
- **Missing columns** are treated as empty fields, except for required fields
  (`required: true` in the schema; today only `genus`). Without a `genus`
  column the tab is rejected with an explanation.
- **Duplicate headers** (two columns mapping to the same field) make the tab
  invalid until the owner removes one. Two custom columns with the same name
  only leave those two columns out.

## Custom columns

A custom column holds whatever the owner wants to keep next to a plant that
the schema has no field for, such as a mark for a marathon. Square-Pot imports
it without knowing what it means, and serves it with the plant's other
values. The owner chooses where custom columns show. When preparing labels,
each print request picks which ones a printed label shows, as `Name: value`.
Choosing which ones the phone shows, in its settings, is planned and not built
yet; until then, they are in the API and the phone's copy.

- **Name.** The header, with spaces trimmed and runs of spaces made single;
  its case is kept for display: `Marathon`. Two custom columns whose names are
  equal ignoring case are both left out, and reported.
- **Value.** Text, as the sheet shows it, trimmed: a number cell reads as
  `12.5`, a checkbox as `TRUE` or `FALSE`. An empty cell means no value. With
  a service account, values are read unformatted, so a date in a custom
  column arrives as the sheet's day number; read by link, it arrives as the
  sheet shows it.
- **Limits.** At most 50 custom columns per tab, names of at most 64
  characters, and values of at most 1000 characters. Columns beyond the first
  50, and columns with longer names, are left out; a longer value is cut short
  with `…`. Each case is reported.
- **Never written.** Like every other column, Square-Pot only reads custom
  columns.
- **Never interpreted.** A custom column is opaque passthrough text: neither
  typed nor validated, and shown on labels and on the phone only where the
  owner picks it. Anything that needs meaning becomes a field in the
  [schema](../schema/fields.yaml).

## Values

With a service account, values are read with the Sheets API's unformatted
values and serial-number dates, so they do not depend on the sheet's locale or
display format. A sheet read by link
([ADR 0003](adr/0003-spreadsheet-as-source-of-truth.md)) is downloaded as CSV,
which holds every value as the sheet displays it: a date cell must then
display as `YYYY-MM-DD` or `DD.MM.YYYY`, and a decimal with a dot (`12.50`),
or the cell is reported as invalid. A sheet whose locale writes decimals with
a comma, such as Russian (`12,50`), must keep its decimal columns, such as
`price`, as plain text written with a dot (Format, Number, Plain text).

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

## The label type

The optional `label_type` column chooses the label template a plant is
printed with: `h` for the horizontal label, empty or `v` for the vertical
one, the default. It is read case-insensitively, and any other value is
reported as invalid, so the plant gets the default. Choosing a template when
printing overrides it.

## How Square-Pot writes

Square-Pot writes to the sheet only when a user acts, never on its own.

In the first release there is exactly one write: **assigning numbers**. It
needs a sheet shared with the service account; a sheet read by link is
read-only. In the
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

Only tab-level problems (no `genus` column, two columns for the same field)
stop the import.

## Versioning

The schema has a `version`. Adding an optional field is not breaking: old
sheets simply lack the column. A sheet that already has a custom column of
that name then reads it as the new field. Renaming or removing a field, or
changing its type, is breaking; it raises `version` and keeps the old header
as an alias for at least one release.
