# Android app

The phone client. In live mode, the camera reads the nearest Data Matrix
label and shows that plant's name next to it. In photo mode, it captions a
full-resolution photo, for the largest label or for every label in the shot. It
keeps a local copy of the collection so it works offline, in a greenhouse or on
a balcony.

Stack: Kotlin, Jetpack Compose, CameraX, zxing-cpp, Room. The recognition spike
compared zxing-cpp with ML Kit on real labels; ML Kit read none of them and
needs Google Play services, so the app decodes with zxing-cpp only.

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
  back in coverage. Network and server errors, and a server that asks the
  app to slow down (HTTP 429), are retried with backoff.
- **Freshness.** The screen shows when the copy was last refreshed and when the
  server last read each sheet, with the sheet's error if its last read failed.
- **Changing server.** A new server address drops the cursor, so the next sync
  replaces the whole copy.
- **Inventory.** Each plant also carries when it was last seen (its newest
  sighting or photo), its photo count, its newest and main photo, and since
  when it has its status; each collection, whether its plants can be edited.
- **Custom columns.** The copy also keeps each collection's own sheet columns
  (`custom_columns`) and every plant's values for them, so captions can show
  them offline.
- **App updates.** When an update changes the copy's tables, the copy and its
  cursor are dropped, and the next sync downloads a full copy. There are no
  migrations to maintain: the server holds the data.

## Queue

What the owner records on a plant's card in inventory mode (ADR 0007, 0008)
waits on the phone until the server has it, so a walk through a greenhouse
without signal loses nothing.

- **What.** Sightings ("seen, no photo", or a status set) and photos, each with
  an id the phone chooses, so sending one again after a lost answer is
  harmless. A photo's comment goes with it.
- **When.** As soon as something is added, at app start and after the server
  settings change. Sending runs in WorkManager and waits for a network.
  Sightings go out in batches of up to 500, then photos one at a time; then
  the copy is synced, so it shows the plants' new `last_seen` and photo count.
- **Refusals.** A number no plant has, a photo that is too large or that the
  server cannot read, and a photo whose file is gone stay in the queue for the
  owner to retry or discard; the rest of the queue goes on. Network and server
  errors, and a busy server, stop sending and are retried with backoff.
- **Kept apart from the copy.** The queue is its own database. It holds data
  that exists nowhere else yet, so an app update never drops it: every change
  to its tables comes with a migration. Sent items are kept for 90 days, so a
  long walk still counts them as seen.

Release builds talk to the server over HTTPS only. Debug builds also allow
plain HTTP, for a demo server on the local network or on the emulator's host
(`http://10.0.2.2:<port>`).

Sync is unit-tested against a fake server (OkHttp MockWebServer) with Room
under Robolectric. The tests cover full and delta responses, schema changes,
old cursors and failures.

## Camera

The app opens on the live camera. The chip at the top left shows when the
local copy was refreshed and opens it; ⚙ opens the caption settings, which
also hold the tools (analysis resolution and the photo bench); Back returns
to the camera.

- **Live camera.** Analysis frames (720p by default; 1080p or the largest
  16:9 size can be picked) are decoded by zxing-cpp. In single-plant mode the
  app picks one label:
  1. **a tapped label**, whatever its size. It stays picked until you tap
     another label, tap where there is no label, or it is out of sight for
     more than 0.3 s. A tapped label is drawn in blue instead of green, and
     tapping it again copies its caption. The tap also focuses the camera there;
  2. otherwise **the clearly largest label** (the nearest pot's; labels more
     than 1.5 times smaller are background);
  3. among labels of about equal size, **the one nearest the aim mark**, a
     small cross centred a bit above the middle of the frame. Vertical distance
     counts half, since the label usually sits on the far rim, above the plant.

  It locks the label after a few stable frames (with a haptic tick). A label
  the decoder misses for a frame or two stays on screen for 0.3 s, so frames
  and numbers do not blink, and each label's corners go through a 1€ filter
  (smoothed hard while the phone is still, followed closely while it moves),
  so they do not tremble. Lookups read only the local copy, never the network.
- **Captions.** Every decoded label has a frame and its number on a tab. The
  selected label's caption shows the chosen fields from the local copy
  (field number, name, ex and the first custom column until the owner picks
  others), or that the copy has no plant or several plants with that number.
  By default it hangs off the number tab: to the right of the label when it
  fits, else above it, never below, since the plant is usually under its
  label. It can be a paper card or bare text, or go in a dark panel at the
  bottom instead, which folds to the name alone. Long names can be shown in
  full, on two lines or with the genus as its initial; neighbouring labels
  can show a short name. All of this is in the caption settings and kept on
  the phone.
- **Inventory mode.** The clipboard button at the top turns it on (ADR 0008,
  variant A). A tap on any label then opens the plant's card instead of
  copying: its caption, when it was last seen, its photos and its status,
  **Take photo** and **Seen, no photo**. Only these buttons count: a label
  the camera merely reads records nothing. **Take photo** takes a
  full-resolution photo (inventory mode binds photo capture next to
  analysis) and shows it with an optional comment, then **Save** queues it
  for upload, or **Retake** drops it. The photo is decoded first: when it
  shows a second plant of the copy, the app asks whose photo it is, and can
  mark the other one as seen. Numbers seen in the walk
  carry a ✓ on their tab. The bar at the bottom shows how many plants of the
  walk were seen since it began and opens the walk: a collection, optionally
  narrowed to one value of the genus or of one of its own columns (such as a
  shelf), and the time from which sightings count, which **Start over**
  resets. The queue chip next to it shows what waits to be sent, and turns
  red when the server refused something; the queue screen says why and
  offers retry or discard.
- **Smoothing panel.** A long press on the version line (in the caption
  settings, or in the bottom panel) opens a hidden panel over the camera with
  the 1€ filter's two settings, the decode rate and latency over the last 120
  frames, and a button that copies the values for a report.
- **Bench.** Pick a folder of label photos. Each photo is made upright (EXIF
  orientation), scaled to a long side of 1280, 1920 and 2560 px in turn (the
  720p, 1080p and a larger analysis frame, for the live mode), then taken at
  full resolution (for the photo mode), and decoded at each size. The results
  are written as `squarepot-bench-<time>.json` in the same folder.

### Bench ground truth

To score decodes, put a `bench.csv` next to the photos:

```csv
file,codes,conditions,primary
IMG_0001.jpg,004217,glare,004217
IMG_0002.jpg,004218 004219,tilt;lowlight,004219
IMG_0003.jpg,,lowlight,
```

- `codes`: the label numbers visible in the photo, separated by spaces. Leave it
  empty for a photo with no readable label; then any decode counts as wrong.
- `conditions`: tags separated by `;`, such as `glare`, `tilt`, `dirt`,
  `lowlight` or `far`.
- `primary` (optional column): the largest label in the photo, the one a
  single-plant mode must pick. It must be one of `codes`.

For each decoder the report counts correct, missed and wrong codes, overall
and per condition. Where `primary` is given, it also counts how often the
decoder's largest detection is that label (`primary`, `primaryByCondition`).
Photos missing from `bench.csv` are decoded but not scored.
Rows of `bench.csv` whose photo is not in the folder are listed under
`missingPhotos` in the report.

## Build

CI builds a debug APK on every pull request that touches `android/`. Download
the `squarepot-debug-apk` artifact from the workflow run and install it with
`adb install`, or open it on the phone.

Locally you need JDK 17 and the Android SDK (`ANDROID_HOME` or
`local.properties`):

```sh
cd android
./gradlew detekt ktlintCheck lintDebug   # linters
./gradlew testDebugUnitTest              # unit tests
./gradlew assembleDebug                  # app/build/outputs/apk/debug/
```

`./gradlew ktlintFormat` fixes formatting. Code style: Kotlin coding
conventions, 120 columns (`.editorconfig`).

## Layout

| Package | What it holds |
| --- | --- |
| `recognition` | Pure Kotlin: label codes, detections, single-target selection, statistics. Unit tested on the JVM. |
| `decoder` | zxing-cpp behind the `TagDecoder` interface. |
| `camera` | CameraX analysis, the live screen and the overlay. |
| `bench` | The photo bench and its JSON report. |
