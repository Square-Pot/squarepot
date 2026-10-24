# Android app

The phone client. In live mode, the camera reads the nearest Data Matrix
label and shows that plant's name next to it. In photo mode, it captions a
full-resolution photo, for the largest label or for every label in the shot. It
keeps a local copy of the collection so it works offline, in a greenhouse or on
a balcony.

Stack: Kotlin, Jetpack Compose, CameraX, ML Kit Barcode Scanning (zxing-cpp as
the fallback decoder), Room.

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

## Status: recognition spike

The app opens on the recognition spike, which measures how reliably labels
are read in real conditions. **Bench** and **Local copy** on the camera screen
open the photo bench and the local copy described above; Back returns to the
camera.

- **Live camera.** Analysis frames (720p by default; 1080p or the largest
  16:9 size can be picked) are decoded by ML Kit, zxing-cpp, or both on
  alternate frames. In single-plant mode the app picks one label:
  1. **a tapped label**, whatever its size. It stays picked until you tap
     another label, tap where there is no label, or it is out of sight for
     more than 0.3 s. Tapping the picked label copies its number;
  2. otherwise **the clearly largest label** (the nearest pot's; labels more
     than 1.5 times smaller are background);
  3. among labels of about equal size, **the one nearest the aim mark**, a
     small cross centred a bit above the middle of the frame. Vertical distance
     counts half, since the label usually sits on the far rim, above the plant.

  It locks the label after a few stable frames (with a haptic tick). The
  bottom panel shows each decoder's decode rate and latency over the last 120
  frames.
- **Bench.** Pick a folder of label photos. Each photo is made upright (EXIF
  orientation), scaled to a long side of 1280, 1920 and 2560 px in turn (the
  720p, 1080p and a larger analysis frame, for the live mode), then taken at
  full resolution (for the photo mode), and decoded by both decoders at each
  size. The results are written as `squarepot-bench-<time>.json` in the
  same folder.

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
| `decoder` | ML Kit and zxing-cpp behind one `TagDecoder` interface. |
| `camera` | CameraX analysis, the live screen and the overlay. |
| `bench` | The photo bench and its JSON report. |
