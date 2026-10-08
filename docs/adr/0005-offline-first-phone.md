# 0005. The phone works offline from a local copy

- **Status:** Proposed
- **Date:** 2026-10-08

## Context

Plants live in greenhouses, on balconies and in sheds, where mobile coverage is
often poor or absent. The live overlay looks up every recognised code many
times a second. Even a fast network round trip is too slow for that, and any
dependency on the network makes the feature fail exactly where it is used.

## Decision

- **The phone keeps a local copy** (Room) of every collection on the
  instance: plant fields, presets and the schema version.
- **The camera path never touches the network.** Recognition, lookup, captions
  in the live view and captioned photos all work from the local copy.
- **The copy syncs whenever the phone is online.** The server exposes changes
  since a cursor the phone keeps, so a sync moves only what changed. A full
  refresh is the fallback when the cursor is too old or the schema has changed.
- **Staleness is visible.** The app shows when the copy was last refreshed.
  The server's copy itself may lag the sheet
  ([ADR 0003](0003-spreadsheet-as-source-of-truth.md)), and the app does not
  hide that either.
- **The phone is read-only for plant data in the first release.** Edits happen
  in the sheet. This avoids offline write conflicts entirely.

## Consequences

- Identification is instant and works with no network at all.
- The phone stores the collector's collections. For hobby collections this is
  a few megabytes. Photos are not part of the copy.
- The sync API (changes since a cursor) is part of the server's OpenAPI contract
  from the start.
- Offline edits, if added later, will need their own conflict design, still
  with the sheet winning.

## Alternatives considered

- **Online lookups with a cache.** Less storage, but the first scan of each
  plant would need the network, and the feature would fail in the greenhouse.
- **Only selected collections offline.** Less data, but the collector would
  have to remember to select a collection before walking into the greenhouse.
- **Offline edits from the start.** Useful, but it brings conflict resolution
  on three sides (phone, server, sheet) into the first release for little gain,
  while the sheet remains the place where data is edited.
