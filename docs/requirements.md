# Requirements

> **Status: draft**, pending approval by the product owner.

## The problem

Plant collectors label every pot. A collection of a few hundred succulents
quickly outgrows paper labels: the label holds a number or a short name, and
everything else (field number, origin, locality, age) lives in a notebook or a
spreadsheet. Today, finding out what is in a pot means reading its code with a
phone, typing the number into a lookup tool, and copying the answer into a
chat. It works, but it is slow, and with a table of thirty plants it is
painful.

Existing collection apps are closed services. They keep the data on their own
servers, and when the service ends, so does the collection.

## Goals

1. **Point and know.** Aim a phone at a pot and see the plant's name next to
   its label in the live camera view.
2. **Data that outlives the software.** The collection stays in a spreadsheet
   the collector owns, readable without Square-Pot.
3. **Share without explaining.** A photo of one plant or a whole group can be
   sent with every plant already captioned.
4. **Show only what matters.** The collector chooses which fields appear,
   and saves the choice as a preset.
5. **Open and self-hosted.** A collector runs their own instance with one
   command, on their own machine or server.

## Users

The first release is built for **personal deployment**: one collector runs
their own instance for their own collections. That person is both the user and
the operator.

- **Collector**: owns the collections, prints labels, scans pots, shares
  photos.
- **Operator**: the same person, wearing a different hat: installs, configures,
  updates and backs up the instance.

A hosted, multi-user service, where many collectors share one instance, may
come later but is not planned. The design keeps the door open (collections
belong to an owner, the storage sits behind an adapter) without building for it
now.

## Scope of the first public release

### Labels

- A label carries one Data Matrix symbol encoding only the plant's six-digit
  number ([ADR 0001](adr/0001-label-code-format.md)).
- The web app designs labels and generates print-ready SVG and PDF, laid out on
  pages, for selected plants. The text on the label follows the `label`
  preset.
- Numbers are assigned by the instance and unique within it
  ([ADR 0002](adr/0002-plant-number-allocation.md)).

### Identifying plants (Android)

Recognition looks for Data Matrix symbols only. The app has two ways of
working, for two different jobs.

#### Live mode: look up one plant at a time

The scene: small pots, about 5–6 cm across, stand close together on a table.
The collector moves the phone over them, held at about 45° to the table, and
looks at the plants one after another. Many labels are in the frame at once,
but only one matters at a time. The working distance from the phone to the
labels is not fixed yet; the recognition spike measures it.

- The app picks the **largest label in the frame**, which is the nearest one,
  and ignores all the others. Size is the main criterion.
- Between labels of similar size, the one closer to the vertical middle band of
  the frame wins: only the horizontal position counts. A label above or below
  the middle is not penalised, because the label sits on the rim of the pot,
  above the plant (far rim) or below it (near rim), while the middle of the
  frame usually shows the plant itself. There is no crosshair in the centre of
  the view.
- It shows that plant's caption next to the label: to the right of it, or
  above it when there is no room on the right, never below, where the plant
  usually is. In the settings, the caption can go in a panel at the bottom of
  the screen instead.
- The caption's fields are chosen in the app's settings and kept on the phone.
  Until the collector chooses, they are the field number, the name, ex and
  the first of the sheet's own columns.
- Other labels in the frame show only their number, or, if the collector
  turns it on, their number and a short name such as "M. theresae".
- The selection does not jump back and forth between labels of almost the same
  size.
- One tap copies the plant's details to the clipboard, or opens the full card.
- Optional: a quick screenshot or a short video clip with the recognised
  plant's caption, ready to send to a friend.
- The largest label must be read reliably in that scene, at the working
  distance measured by the spike. Smaller, more distant labels need not be
  read at all.
- The resolution at which frames are analysed is left open. It will be chosen
  from the measurements of the recognition spike.

#### Photo mode: a captioned photo for a chat

The collector takes a full-resolution still photo, not a frame from the video,
to send to a chat or a group. Before the photo is captioned, they choose the
mode explicitly:

- **Single plant** (the common case): caption the largest label only. Smaller
  labels that happen to be in the shot are ignored.
- **Group**: find and caption every label in the photo.

The layout of the captions is the main requirement:

- Every field of the chosen preset fits.
- The captions do not cover the plants.
- It is always clear which caption belongs to which plant.

One way to do it, given as an example rather than a decision: a coloured frame
around each code, and small captions along the bottom of the photo, each with a
marker of the matching colour.

- Captioning happens on the device. The original photo is kept unchanged.
- Nice to have, not required because it is costly: before saving, the
  collector can tap a label to exclude it from the captions.

#### In both modes

- Copy or share the details of the recognised plants as text, using the chosen
  preset.
- Numbers are unique, so a label identifies exactly one plant. If an import
  ever finds the same number twice, the collision is reported, and until it is
  fixed that number shows every match
  ([ADR 0002](adr/0002-plant-number-allocation.md)).

### Offline

The phone keeps a local copy of every collection on the instance. Scanning,
captions and lookups work with no network at all, in a greenhouse or on a
balcony. The copy is refreshed whenever the phone is online
([ADR 0005](adr/0005-offline-first-phone.md)).

### Collections and data

- A collection is backed by one tab of a Google Sheet in its owner's Drive. The
  format is specified in [sheet-format.md](sheet-format.md), and the fields in
  [`schema/fields.yaml`](../schema/fields.yaml).
- The server caches and indexes collections and syncs with the sheet. The sheet
  is the source of truth, and edits made in it win over everything else
  ([ADR 0003](adr/0003-spreadsheet-as-source-of-truth.md)).
- The web app connects a sheet and shows what was imported and which cells are
  invalid. Plant data is edited in the sheet, not in the web app.
- Fields are grouped as **basic** (the core description: tag, field number,
  name, ex) and **extra** (additional detail: locality, source, dates, price,
  notes). Nothing is hidden: presets decide what is shown where.
- Field presets: the built-in `label`, `overlay`, `chat` and `full`, plus the
  collector's own. Any field can go into any preset.
- Plant names are rendered by the accepted botanical conventions: the ICN for
  wild taxa and the ICNCP for cultivars, as used by the RHS and German botanical
  practice. For example: *Lithops lesliei* subsp. *burchellii*,
  *Lithops* aff. *lesliei*, *Echeveria* 'Perle von Nürnberg'.

### Access

- The instance belongs to one collector. They sign in to the web app and the
  phone with credentials set during installation.
- Square-Pot reads the sheet through a Google service account: the collector
  shares the sheet with the service account's email. No Google OAuth app is
  needed.

### Telegram bot

A thin client to the API. It has no data or logic of its own.

- Look up a plant by number.
- Inline mode: `@bot 004217` in any chat inserts the plant's card. Numbers
  typed without leading zeros (`@bot 4217`) are padded to six digits.
- Send it a photo, and it replies with the photo captioned, the same way as
  photo mode in the app: single plant by default, group when asked. Codes are
  found on the server with zxing-cpp.
- Search collections by any text.
- It answers only the Telegram accounts the collector has allowed.

### Self-hosting

- `docker compose up` on a clean machine brings up the whole stack: API, sync
  worker, bot, web app, database and Caddy with automatic HTTPS.
- All configuration comes from environment variables, documented in
  `deploy/.env.example`.
- A deployed instance shows no contacts of the project's maintainers: it
  belongs to the collector who runs it.
- PostgreSQL by default, SQLite for a minimal install.
- A step-by-step self-hosting guide, tested on a clean machine, including the
  Google Cloud service account setup.

### Languages

The Android app, web app and bot ship in English and Russian. Code,
documentation and the project's discussions are in English.

## Quality targets

These are proposed targets, to be confirmed by the recognition spike on real
labels before development builds on them.

| Area | Target |
| --- | --- |
| Recognition, live | In the live scene (pots of about 5–6 cm on a table, phone at about 45°, at the working distance measured by the spike), the largest label in the frame is read in normal indoor light, including with glare. A set of frames taken in that scene is kept as a regression test. |
| Recognition, photo | In a full-resolution photo, single-plant mode reads the largest label, and group mode finds every label in the shot. A reference set of real photos is kept as a regression test. |
| Responsiveness | In live mode, the caption appears next to the largest label within half a second of it coming into view, on a mid-range phone, with no visible lag as the phone moves. |
| Offline | Every identification feature works with no network. |
| Durability | Losing the server loses no plant data. Server-only state (settings, presets and the registry of issued numbers) is covered by the operator's backups, and the guide explains how. |
| Sheets API | Syncing stays within the default Google quotas for a collection of several thousand plants ([ADR 0003](adr/0003-spreadsheet-as-source-of-truth.md)). |

## Out of scope for the first release

- Care log: watering, repotting, treatments.
- Events, plant history, and lineage between parent plants and offspring.
- Certificates or passports for plants sold to buyers.
- Editing plant data in the web app. The sheet is where data is edited.
- Storage backends other than Google Sheets, such as CSV or Nextcloud. The
  storage adapter leaves room for them.
- iOS. The product owner has decided on Android only for now.
- A multi-user service: several collectors on one instance, Google sign-in
  (OAuth), sharing collections with other people.
- Recognising plants from their appearance, and server-side ML models for
  finding codes.
- Reading small or distant codes.
- Any change to the label format: URLs, collection prefixes, longer numbers.

## Decisions by the product owner

Recorded on 2026-10-09:

1. **Platforms.** Android only for now; no iOS app is planned.
2. **Audience.** Personal deployment by one collector. A multi-user service may
   come later but is uncertain, so it is out of scope.
3. **Numbers on import.** The product owner's collection already has strictly
   unique numbers. A collision on import is treated as an error to report,
   not as a normal case.
4. **Licenses.** `AGPL-3.0-or-later` for the server, bot, web app and
   everything else by default; `Apache-2.0` for the Android app and for the
   field schema in `schema/`, which both sides use. See the README.
5. **Field names.** `tag` for the label number (instead of `uid`, which is
   still read), `cultivar` and `notes`. `number` was rejected as too easily
   confused with `field_number`.
6. **Currency.** Plants are bought worldwide, so each row has its own
   `currency` next to `price`.
7. **Field visibility.** No field is secret. Fields are basic or extra, and
   presets decide what is shown.
8. **Botanical notation.** Names follow the accepted standards (ICN, ICNCP);
   `aff.` takes the place of the epithet.
9. **Contact.** The project has no domain or contact address yet. Bugs and
   questions go to GitHub Issues. Security reports go through GitHub's private
   vulnerability reporting, with no address. A deployed instance shows no
   maintainer contacts, because every instance is run by its own collector.

## Open items

- **Code of Conduct contact.** How conduct reports reach the maintainers is not
  decided yet. It must be settled before the repository goes public.
