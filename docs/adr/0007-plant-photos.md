# 0007. Plant photos live in object storage, indexed by the server

- **Status:** Proposed
- **Date:** 2026-10-26

## Context

The owner wants photos on the plant card: several per plant, shown as a
timeline, one of them marked as the main photo. Photos are taken on the phone,
often in a greenhouse without signal, and sometimes uploaded from a computer.

Photos do not fit in the sheet, and the server is a cache whose loss must not
lose the owner's data ([ADR 0003](0003-spreadsheet-as-source-of-truth.md)).
The server runs on a small host with little disk space. The owner already
keeps the photos of another project in Yandex Object Storage, an
S3-compatible service.

A collection is private: the instance holds one owner's plants, behind a
token. Photos from a phone can carry the place they were taken in their
EXIF data.

## Decision

- **Photos are files in an S3-compatible bucket that the owner owns.** The
  owner's instance uses Yandex Object Storage, in the account the owner
  already has, with a new bucket used only by Square-Pot and a key of its own
  that reaches only that bucket. Any S3-compatible service works, including
  a self-hosted MinIO. A storage adapter hides the service, as the
  collection store does for sheets, and a local-disk adapter serves an
  install without a cloud account.
- **A photo belongs to a plant through its number.** Numbers are never reused
  ([ADR 0002](0002-plant-number-allocation.md)), while a plant id can change
  when its row is edited. A plant without a number gets one before it can
  have photos (see [ADR 0006](0006-editing-plants-from-the-apps.md)).
- **The server keeps the index; the bucket can rebuild it.** The server's
  database holds each photo's id, number, when it was taken, when it was
  uploaded, its size, and which photo is the plant's main one. This gives
  fast timelines and the same change cursor the phone already syncs with
  ([ADR 0005](0005-offline-first-phone.md)). Each object's key and metadata
  repeat what matters, as in `photos/004217/2026-10-26T14-03-11Z_<id>.jpg`, so
  the bucket alone is readable by a person, and a server command rebuilds the
  index from it. Only the choice of main photo is lost in a rebuild, and it
  falls back to the newest photo.
- **Uploads go through the server.** The phone and the web app send a photo to
  the server, which:
  - turns it the right way up and removes its EXIF data, including the place
    it was taken, keeping only the time it was taken, which goes into the
    index;
  - stores two sizes as JPEG: a large one at most 2560 px on its longest
    side, about 1 MB, and a thumbnail at most 480 px, about 40 KB;
  - writes both to the bucket, and then records the photo.

  A client generates the photo's id, so sending it again after a lost
  connection does not make a copy.
- **The phone uploads from a queue.** A photo taken offline is kept on the
  phone and uploaded when there is a connection. Adding photos cannot
  conflict, so offline is safe here, unlike edits.
- **Downloads come straight from the bucket.** The bucket is private. For each
  photo, the API hands out a signed address that expires after a few hours,
  so an app shows it without the server passing the bytes on. The phone keeps
  thumbnails in its local copy and fetches a large photo when it is opened.
- **The timeline is ordered by when the photo was taken.** That is the time
  from the camera, else the time the phone gives, else the upload time. The
  owner can change it, and the app shows the plant's age at each photo when
  the sheet has a seeding date.
- **Deleting is reversible for 30 days.** A deleted photo leaves the timeline
  at once, and its files are removed after 30 days.
- **Backups belong to the bucket.** The owner turns on the bucket's
  versioning, with a lifecycle rule that removes old versions after 30 days.
  The index is part of the server's data volume and can be rebuilt.

## Consequences

- Losing the server loses no photos, and at most the choice of main photos.
- The owner needs a new bucket and a service account key limited to it: the
  key goes in the server's environment, never in git. A leaked key exposes
  only Square-Pot's photos, not the owner's other buckets.
- The server does the image work for each upload: one photo at a time, about
  120 MB of memory at the peak for a phone photo, and up to about 250 MB for
  the largest PNG it accepts, which fits the 1 GB limit. CI measures it, as it
  does for labels.
- Formats: JPEG, PNG and WebP come in at first. HEIC from iPhones needs an
  extra library and comes later; Android phones send JPEG.
- Cost, at Yandex Object Storage's standard class: 10 photos for each of
  about 530 plants is about 6 GB, roughly $0.10 a month for storage after the
  first free GB. Outgoing traffic within the first 100 GB a month and a
  person's number of requests cost about nothing.
- The API gains photo endpoints, and the sync gains photo changes. Both are
  additive.

## Alternatives considered

- **All metadata in the bucket, no index in the server's database.** Nothing
  to rebuild, but each timeline would need bucket listings, moving the main
  photo would rewrite objects, and the phone's sync could not use the
  existing cursor. The index costs little, and it can be rebuilt.
- **The owner's existing bucket, or a public bucket with unguessable keys**,
  as in the owner's other project.
  One bucket less to set up, and addresses that never expire, but the two
  projects would share a key, and anyone who sees one address can share it
  for good. A private collection is better served by its own bucket and
  signed addresses.
- **Photos in the sheet, or in Google Drive.** It keeps everything in one
  place, but Drive is slow to serve images, and its quota is shared with the
  owner's other files. The sheet would only hold links.
- **Photos on the server's disk.** No cloud account, but the host is small and
  the files would be lost with it. It stays possible through the local-disk
  adapter.
- **Uploading straight from the phone to the bucket with a signed upload
  address.** Less traffic through the server, but the EXIF location would
  reach the bucket, and each client would have to make thumbnails.
