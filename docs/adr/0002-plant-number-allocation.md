# 0002. Plant numbers are unique within an instance

- **Status:** Proposed
- **Date:** 2026-10-08

## Context

The label holds only a six-digit number ([ADR 0001](0001-label-code-format.md)).
A phone that scans `004217` must know which plant that is, even when the
collector keeps several collections on the instance. With no prefix on the
label, the number alone has to identify the plant.

Collectors also arrive with existing collections that already have numbered
labels. The product owner's own collection already has strictly unique
numbers, so a collision on import is an error, not a normal case.

## Decision

- **Numbers are unique within an instance.** The server keeps one number space,
  `000001` to `999999`, shared by every collection on the instance. `000000` is
  reserved and never issued.
- **The server issues numbers.** When a collector assigns numbers (for
  example before printing labels), the server hands out the next free numbers,
  in ascending order, and writes them into the sheet's `tag` column
  ([sheet-format.md](../sheet-format.md)).
- **A number is never reused.** The server records every number it has issued
  or seen in a sheet, with its collection. A number stays taken after its row is
  deleted, because a printed label may still exist.
- **Imported numbers are kept.** When a collection is connected, its existing
  numbers are registered as they are.
- **A collision on import is reported, not hidden.** If an imported number is
  already taken, the web app reports the collision with both rows so that the
  collector can fix the sheet. Until it is fixed, both plants keep the number
  and a scan of it shows both, so nothing silently points to the wrong plant.

## Consequences

- Scanning a label never needs the user to pick a collection first.
- New labels can never collide. Only numbers that predate the instance can.
- Clients must handle the rare lookup that returns more than one plant.
- The registry of issued numbers is server state that cannot be rebuilt
  completely from the sheets (deleted rows are gone from them). It is part of
  what operators back up. If it is lost, it can be rebuilt from the sheets for
  every number still in use. The numbers of deleted rows cannot be recovered,
  though, and the server could issue them again. An old label still on a pot
  would then point to a new plant. That is why the registry must be backed up.
- Two instances may issue the same numbers. Moving a collection between
  instances is treated as an import.

## Alternatives considered

- **Numbers unique per collection.** Simpler, but the scanner would need to
  know the collection, either from a prefix on the label (rejected in ADR 0001)
  or from the user picking it before every scan.
- **Random numbers.** Avoid guessable sequences, but sequential numbers are
  easier to read, sort and print in runs, and nothing secret depends on them.
- **Rejecting a collection with a collision outright.** Cleaner, but one typo in
  a sheet would block the whole collection. Reporting the collision and
  showing both plants keeps the app usable while the collector fixes it.
- **Treating collisions as a normal case**, with a picker on every ambiguous
  scan. Not needed: numbers in practice are unique, and new numbers can never
  collide.
