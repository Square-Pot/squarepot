# Android app

The phone client: a camera view that reads Data Matrix labels and draws each
plant's name next to its label, in single-plant and group modes. It keeps a
local copy of the collection so it works offline, in a greenhouse or on a
balcony.

Stack: Kotlin, Jetpack Compose, CameraX, ML Kit Barcode Scanning (zxing-cpp as
the fallback decoder), Room.

## Status: recognition spike

The app currently holds only the recognition spike, which measures how
reliably labels are read in real conditions before the rest of the app is
built:

- **Live camera.** 720p analysis frames are decoded by ML Kit, zxing-cpp, or
  both on alternate frames. In single-plant mode the app picks the label you
  are aiming at, locks it after a few stable frames (with a haptic tick) and
  copies its number when you tap. The bottom panel shows each decoder's
  decode rate and latency over the last 120 frames.
- **Bench.** Pick a folder of label photos. Each photo is made upright (EXIF
  orientation), scaled to the live analysis resolution and decoded by both
  decoders. The results are written as `squarepot-bench-<time>.json` in the
  same folder.

### Bench ground truth

To score decodes, put a `bench.csv` next to the photos:

```csv
file,codes,conditions
IMG_0001.jpg,004217,glare
IMG_0002.jpg,004218 004219,tilt;lowlight
IMG_0003.jpg,,lowlight
```

- `codes`: the label numbers visible in the photo, separated by spaces. Leave it
  empty for a photo with no readable label; then any decode counts as wrong.
- `conditions`: tags separated by `;`, such as `glare`, `tilt`, `dirt`,
  `lowlight` or `far`.

For each decoder the report counts correct, missed and wrong codes, overall
and per condition. Photos missing from `bench.csv` are decoded but not scored.

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
