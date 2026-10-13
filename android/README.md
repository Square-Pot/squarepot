# Android app

The phone client. In live mode, the camera reads the nearest Data Matrix
label and shows that plant's name next to it. In photo mode, it captions a
full-resolution photo, for the largest label or for every label in the shot. It
keeps a local copy of the collection so it works offline, in a greenhouse or on
a balcony.

Planned stack: Kotlin, Jetpack Compose, CameraX, ML Kit Barcode Scanning, Room.

## Local copy and sync

Following [ADR 0005](../docs/adr/0005-offline-first-phone.md), the app keeps a
copy of every collection on the server in Room and looks label numbers up only
in that copy, never over the network.

- **Server settings.** The collector enters the server address and the
  operator's API token on the main screen. They are kept in the app's private
  storage, never in the code. **Check** lists the server's collections without
  saving anything.
- **Sync.** `GET /api/v1/sync` with the stored cursor returns a full copy or the
  changes since the cursor (see [`server/openapi.json`](../server/openapi.json)).
  When `schema_version` differs from the stored schema, the app also fetches
  `GET /api/v1/schema`. Each response and its cursor are written in one
  transaction, so a sync that fails or is interrupted leaves the previous copy
  in place.
- **When.** At app start and on **Refresh**. The sync runs in WorkManager and
  waits for a network, so a sync asked for offline happens once the phone is
  back in coverage. Network and server errors are retried with backoff.
- **Freshness.** The screen shows when the copy was last refreshed and when the
  server last read each sheet, with the sheet's error if its last read failed.
- **Changing server.** A new server address drops the cursor, so the next sync
  replaces the whole copy.

Release builds talk to the server over HTTPS only. Debug builds also allow
plain HTTP, for a demo server on the local network or on the emulator's host
(`http://10.0.2.2:<port>`).

Sync is unit-tested against a fake server (OkHttp MockWebServer) with Room
under Robolectric. The tests cover full and delta responses, schema changes,
old cursors and failures.
