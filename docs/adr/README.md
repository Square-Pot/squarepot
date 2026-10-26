# Architecture decision records

Each record explains one significant decision: the context, what was decided,
what it costs and what else was considered. Records are numbered and never
rewritten once accepted. A later decision supersedes an earlier one in a new
record, and the old one links to it.

To propose a decision, copy [`template.md`](template.md) to the next number,
fill it in with status **Proposed**, and open a pull request.

| ADR | Title | Status |
| --- | --- | --- |
| [0001](0001-label-code-format.md) | Label code: a six-digit number in a 10×10 Data Matrix | Proposed |
| [0002](0002-plant-number-allocation.md) | Plant numbers are unique within an instance | Proposed |
| [0003](0003-spreadsheet-as-source-of-truth.md) | The spreadsheet is the source of truth, behind a storage adapter | Proposed |
| [0004](0004-technology-stack.md) | Technology stack | Proposed |
| [0005](0005-offline-first-phone.md) | The phone works offline from a local copy | Proposed |
| [0006](0006-editing-plants-from-the-apps.md) | Editing plants from the apps writes cells to the sheet | Proposed |
