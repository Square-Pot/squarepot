# 0008. Inventory: sightings, inventory filters and batch photo import

- **Status:** Proposed
- **Date:** 2026-10-26

## Context

The owner wants to walk the whole collection and confirm that each plant is
still there, by photographing it or just by scanning its label. Many rows are
thought to belong to plants that are gone. The apps should then show the
plants with no photo, with no recent photo, or not seen since a date, and the
owner should be able to give many of them a status at once
([sheet-format.md, "The status"](../sheet-format.md#the-status)).

The owner also has years of plant photos with labels in the frame. Filing them
by hand is out of the question, so they should be filed by the Data Matrix
code they show ([ADR 0001](0001-label-code-format.md)).

This builds on photos in object storage indexed by the server
([ADR 0007](0007-plant-photos.md)), on cell edits written to the sheet
([ADR 0006](0006-editing-plants-from-the-apps.md)), and on the phone's local
copy ([ADR 0005](0005-offline-first-phone.md)). The server runs on a host with
two cores and 4 GB of memory, shared with other services, and its database is
a cache whose loss must not lose the owner's data
([ADR 0003](0003-spreadsheet-as-source-of-truth.md)).

zxing-cpp is the decoder of the phone and of the server
([ADR 0004](0004-technology-stack.md)). On the owner's photos of real labels
it read 24 of 32, so a batch of older photos will leave a share unread.

## Decision

### Sightings

- **A sighting records that a plant was seen at a time.** It has an id the
  client generates, the plant's number, the time it was seen, and how: a
  scan, a photo, or a batch import. Like photos, sightings belong to numbered
  plants only, and a plant without a label cannot be scanned anyway.
- **The phone records a sighting on each scan in inventory mode.** Opening a
  plant's card from a scanned label is the proof. Live captions do not record
  sightings: they read many labels a second without the owner looking at
  them. A repeat scan of the same plant within ten minutes is not recorded
  again.
- **Sightings are queued on the phone and sent when online.** Adding
  sightings cannot conflict, so offline is safe here, as for photos. The
  client's id makes a resend harmless.
- **A photo is a sighting at the time it was taken.** No separate record is
  kept for it; a plant's last sighting is the later of its last scan and its
  last photo. An old photo from a batch import therefore never makes a plant
  look recently seen.
- **Sightings live in the server's database, and copies go to the bucket.**
  Each sighting is also written as a small object, as in
  `sightings/004217/2026-10-26T14-03-11Z_<id>.json`, so a server command
  rebuilds them, as it does the photo index. They are not written to the
  sheet. A "last seen" column can be added later if the owner wants it in the
  sheet.
- **A time in the future is clamped** to the time the server received the
  sighting, in case the phone's clock is wrong.

### What the apps receive

- **Each plant carries `last_seen`, `last_photo` and `photo_count`.**
  A sighting or a photo changes the plant in the sync, so the phone and the
  web app filter their local copies, as they already do for other filters.
- **The plant list also takes inventory filters**, for the bot and for
  scripts: `seen_before`, `photo_before` (both dates, matching plants never
  seen or never photographed too) and `has_photo`. Former plants, those with
  a status, are left out unless asked for.

### Status for many plants at once

- **One request sets the status of up to 500 plants.** It names the plants,
  the status, an optional date, and for each plant the status the client saw.
  The server reads the tab once, writes every cell that still matches in one
  Sheets call, and answers per plant: written, changed in the sheet (not
  written), or not found. The rules of ADR 0006 apply: service account
  collections only, a `status` column must exist, and the request needs the
  server.
- **Clearing a status is the same request with an empty status**, so a wrong
  bulk change can be undone the same way.

### Batch photo import

- **The web app uploads a batch of photos; the server decodes them.** Each
  file goes to a staging area in the bucket with the client's id and the
  file's own date, and a queue entry is recorded. Nothing is filed until it is
  decoded.
- **A worker, apart from the API, works through the queue one photo at a
  time.** It reads the Data Matrix codes with zxing-cpp: first on a copy at
  most 2000 px on its longest side, then on the full image if nothing was
  read. One known number files the photo into that plant, through the same
  steps as an upload (ADR 0007), with a sighting at the time it was taken.
- **Everything else waits for the owner** in a review queue: no code read, a
  number that no plant has, or two or more different numbers. The owner picks
  the plant, or discards the photo. Staged files are removed once filed or
  discarded, and after 30 days in any case.
- **The time taken comes from the photo's EXIF data**, with its time zone
  offset when present, else from the file's own date as the browser gives
  it, else from the upload time. The location is never kept (ADR 0007).
- **The phone imports from its gallery by decoding on the phone.** It already
  has the decoder. Photos it reads go to its normal upload queue as photos of
  that plant; the others go to the same review queue.

### Event tags

- **A photo can carry event tags:** seedling, transplant, bloom, disease. A
  photo may have several, and a whole batch can be given one. They are kept
  in the photo index and in the object's metadata, so a rebuild keeps them.
  The list is fixed in the schema, like status values, so a new tag is a
  schema change.

## Consequences

- An inventory walk leaves a dated proof per plant, even with no network in
  the greenhouse, and the filters show what was not found. Former plants do
  not clutter the result.
- Losing the server loses neither photos nor sightings, only the review queue
  of a batch in progress.
- The cost on this host is the worker's. Decoding and resizing one phone
  photo takes about one to three seconds of one core and up to about 150 MB
  of memory. The worker gets half a core and 512 MB, so the API and the other
  services stay responsive: 1000 photos take about one to two hours. Staging
  keeps the files in the bucket, not on the host's disk. CI measures time and
  memory on sample photos, as it does for labels.
- The bucket holds the staged originals while a batch is processed: about
  4 GB for 1000 phone photos, a few cents for those days.
- The API gains endpoints for sightings, bulk status, imports and the review
  queue, and the plant gains three fields. All are additive. The phone's
  first release of inventory mode needs only sightings and photos; bulk
  status needs the service account (ADR 0006).
- The schema gains the list of event tags.

## Alternatives considered

- **"Last seen" as a column in the sheet.** Visible without the apps, but
  each scan would be a write to the sheet, a walk through the collection
  would be hundreds of writes, and the phone would need the network. It can
  be added later as a copy of what the server records.
- **Sightings only in the server's database.** Simpler, but the server would
  hold data that exists nowhere else, which ADR 0003 rules out.
- **Every scan is a sighting, in any mode.** No mode to switch to, but live
  captions would record plants the owner never looked at.
- **Decoding batches in the browser** with zxing-cpp built for WebAssembly.
  It would spare the host, but a browser tab would have to stay open for the
  whole batch, and the review queue would still need the server.
- **Decoding in the API process.** No new container, but a batch would hold a
  core for hours next to the requests of the apps.
- **Free event tags.** More flexible, but the timeline and filters need a
  known list, and Russian and English names for each tag.
