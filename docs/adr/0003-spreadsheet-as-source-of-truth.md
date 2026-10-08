# 0003. The spreadsheet is the source of truth, behind a storage adapter

- **Status:** Proposed
- **Date:** 2026-10-08

## Context

Collectors already keep their collections in spreadsheets, and the most
important promise of Square-Pot is that the data outlives the software. If an
instance goes down, or the project is abandoned, the collection must still be
complete and readable by a person, with no Square-Pot software.

At the same time, the app needs fast lookups by number, search and offline
copies on phones, none of which a spreadsheet provides. The
Google Sheets API also has per-minute quotas and latencies of hundreds of
milliseconds, so it cannot sit on the path of every request.

## Decision

- **Each collection's source of truth is a Google Sheet in its owner's Drive.**
  The format is specified in [sheet-format.md](../sheet-format.md).
- **The server is a cache, an index and a sync engine.** It keeps a copy of
  every connected collection in its own database and serves all reads from
  there.
- **Sync is incremental by change detection.** The worker polls each
  spreadsheet's Drive `modifiedTime`, a cheap call. It reads the tab only when
  that has changed, then applies the differences to its copy. Recently used
  collections are polled more often than idle ones.
- **Writes go to the sheet first.** Anything Square-Pot writes goes to the
  sheet through the Sheets API, and the copy is updated from the result.
  Before writing, the server re-reads the target row and checks it still
  holds the expected plant
  ([sheet-format.md](../sheet-format.md#how-square-pot-writes)). In the first
  release the only write is assigning numbers to plants that have
  none. Plant data is edited in the sheet.
- **On conflict, the sheet wins.** An edit made in the sheet is never
  overwritten by the server. A write based on stale data is cancelled and the
  user retries after a fresh sync.
- **Storage sits behind an adapter interface.** The server's core talks to a
  `CollectionStore` interface: read the collection, report whether it changed,
  and update cells (in the first release, only to assign numbers). Google
  Sheets is the first implementation.
- **Access through a service account.** The instance belongs to one collector
  (personal deployment), who shares the sheet with a Google service account.
  This needs no Google OAuth app. If a multi-user service is ever built,
  Google OAuth will be added as a second way to grant access.

## Consequences

- Losing the server loses no plant data. Server-only state (settings,
  presets, the number registry) is what operators back up.
- Reads are fast and do not depend on Google's availability. When Google is
  unreachable the server keeps serving its last copy, and says how old it is.
- Edits made in the sheet appear in the app after the next poll, not at once.
  The polling interval is a trade-off between freshness and API quota.
- A whole tab is read on each change. For collections of a few thousand rows
  this is one API call and well within quotas. Much larger collections would
  need a finer scheme.
- Every feature must work through the adapter interface. Nothing may assume
  Sheets-specific behaviour outside the Sheets adapter.
- Supporting another backend (CSV, Nextcloud) later is a new adapter, not a
  redesign.

## Alternatives considered

- **The server's database as the source of truth, exported to a sheet.** Simpler
  to build, but the data's survival would depend on the instance, which is the
  very thing Square-Pot promises to avoid.
- **Reading the sheet on every request.** No cache to keep consistent, but slow,
  bound by API quotas, and impossible offline.
- **Drive push notifications instead of polling.** Fewer calls, but they need a
  public HTTPS callback and channel renewal, which many self-hosted installs
  behind home routers cannot provide. They can be added later as an
  optimisation.
- **Server wins on conflict.** Would make app edits feel more reliable, but it
  would silently discard changes the owner made by hand in their own sheet.
