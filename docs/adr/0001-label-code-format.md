# 0001. Label code: a six-digit number in a 10×10 Data Matrix

- **Status:** Proposed
- **Date:** 2026-10-08

## Context

Every pot carries a label, and the label must be readable by a phone camera.
Labels for small pots are narrow, often under a centimetre of visible height,
so every millimetre spent on the code is a millimetre taken from the text.
The code must also be reliable in poor conditions: glare on plastic, tilt,
dirt, dim greenhouse light.

A 2D code's physical size grows with the data it holds. The smallest square
Data Matrix symbol (ECC200, 10×10 modules) holds exactly six numeric digits.
A QR code holding the same data needs at least a 21×21 grid.

## Decision

A label encodes **only the plant's six-digit number**, with leading zeros, in
a **Data Matrix ECC200 symbol of 10×10 modules**.

Nothing else goes into the code: no URL, no collection or instance prefix, no
checksum beyond the symbol's own error correction. Readers accept only symbols
whose content is exactly six digits and ignore everything else.

This format is fixed. A change to it would need a new ADR that supersedes this
one, and would make every printed label obsolete.

## Consequences

- Labels stay as small as the code allows, at the most reliable module size
  for a given label height.
- The code carries no context. Which collection a number belongs to comes from
  the app and the instance, not from the label. This is why numbers must be
  unique within an instance ([ADR 0002](0002-plant-number-allocation.md)).
- A label scanned by a generic code reader shows only a number. That is
  acceptable: Square-Pot is the intended reader.
- An instance has at most 10⁶ numbers, which is ample for hobby collections and
  small groups.
- Recognition must be tested on real 10×10 labels before anything else is built
  on it. A reference set of photos becomes a regression test.

## Alternatives considered

- **QR code.** More widely recognised, but at least 21×21 modules for the same
  data, so a larger label or smaller modules.
- **A URL in the code** (`https://host/p/004217`). Any phone could open it, but
  the symbol would grow to 22×22 or larger, and the label would be tied to one
  host forever.
- **A collection prefix or longer numbers.** Removes collisions between
  collections, at the cost of a larger symbol. Uniqueness within an instance
  solves the same problem without touching the label.
- **Rectangular Data Matrix** (8×18 and up). Fits some label shapes, but holds
  little more and reads less reliably at an angle; it can be revisited for
  special labels without changing the content format.
