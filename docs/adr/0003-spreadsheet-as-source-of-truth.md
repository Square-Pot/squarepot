# 0003. The spreadsheet is the source of truth, behind a storage adapter

- **Status:** Proposed
- **Date:** 2026-10-08, revised 2026-10-20

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
  collection for a sign of change, and applies only the differences to its
  copy. With a service account, the sign is the spreadsheet's Drive
  `modifiedTime`, a cheap call, and the tab is read only when it has changed.
  Through a link, it is a hash of the downloaded tab. Recently used
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
- **Access by link by default, a service account for a private sheet.** The
  instance belongs to one collector (personal deployment). By default the
  owner shares the sheet as "anyone with the link can view", and the server
  downloads the tab as CSV from its export link
  (`https://docs.google.com/spreadsheets/d/<id>/export?format=csv`). This
  needs no Google Cloud project at all. An owner who keeps the sheet private
  shares it with a Google service account instead, and the server reads it
  through the Sheets and Drive APIs. Neither needs a Google OAuth app. If a
  multi-user service is ever built, Google OAuth will be added as a third way
  to grant access.
- **Writing needs the service account.** A link gives read-only access, so
  assigning numbers is available only to a sheet shared with the service
  account. A collection read by link is otherwise complete.

## Consequences

- Losing the server loses no plant data. Server-only state (settings,
  presets, the number registry) is what operators back up.
- Reads are fast and do not depend on Google's availability. When Google is
  unreachable the server keeps serving its last copy, and says how old it is.
- Edits made in the sheet appear in the app after the next poll, not at once.
  The polling interval is a trade-off between freshness and API quota.
- Through a link, every poll downloads the whole tab, about 100 bytes per
  plant. This is outside the Sheets API quotas, but Google may serve an
  export a little behind the latest edit. The export carries values as
  displayed, so dates and numbers depend on the sheet's format
  ([sheet-format.md](../sheet-format.md#values)).
- Anyone who learns a link-shared sheet's id can read the collection. The
  id is kept in the server's configuration like a secret, and an owner who
  does not accept this uses the service account.
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
- **Only the service account.** One way to set up and test, but every owner
  would need a Google Cloud project, the hardest step of self-hosting, even
  for a collection they are happy to share by link.
- **A sheet published to the web** (File, Share, Publish to web). It also
  gives a CSV link, but publishing is a separate, easily forgotten setting,
  and the published copy can lag the sheet by minutes.
- **Server wins on conflict.** Would make app edits feel more reliable, but it
  would silently discard changes the owner made by hand in their own sheet.
