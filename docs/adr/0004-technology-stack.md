# 0004. Technology stack

- **Status:** Proposed
- **Date:** 2026-10-08

## Context

Square-Pot has five parts: an Android app with a demanding camera feature, a
server with a sync worker, a web app, a Telegram bot, and the deployment that
ties them together. It is an open-source project that should attract
contributors, and self-hosters must be able to run it on modest hardware.

The camera feature sets the hardest constraint: in live mode, the caption must
follow the nearest label with no visible lag as the phone moves, which needs
direct control of the camera pipeline and an efficient barcode decoder.

## Decision

| Part | Stack |
| --- | --- |
| Android app | Kotlin, Jetpack Compose, CameraX, zxing-cpp as the barcode decoder, Room for the local copy |
| Server | Python, FastAPI, Pydantic, SQLAlchemy with Alembic migrations; PostgreSQL by default, SQLite for a minimal install |
| Labels and photo captions | zxing-cpp to find codes in photos, Pillow, SVG generation converted to PDF |
| Web app | TypeScript in strict mode, React, Vite |
| Telegram bot | Python, aiogram 3 |
| Deployment | Docker Compose (API, worker, bot, web, database, Caddy with automatic HTTPS); images on GHCR; APKs on GitHub Releases, later F-Droid |

The parts share a contract, not code:

- the field schema in [`schema/`](../../schema/) defines fields once for every
  part;
- the server publishes an OpenAPI description, and the web and Android API
  clients are generated from it;
- shared golden tests check that every part renders names, captions and labels
  the same way.

## Consequences

- Native Android gives full control of CameraX and the decoder, which the live
  mode needs. The product owner has decided on Android only for now; an
  iOS app would be a separate project.
- The app decodes with zxing-cpp alone. The first draft of this decision had
  ML Kit Barcode Scanning as the decoder and zxing-cpp as a fallback; the
  recognition spike (#58, PR #4) measured both on a real phone (Samsung
  SM-S918B) with the owner's photos of real labels. zxing-cpp read 24 of 32
  labels at the live analysis size (25 at full resolution) with no misreads,
  in 8 ms median per frame; ML Kit read none of the 32 and was slow or silent
  live. zxing-cpp also needs no Google Play services, so the app can be
  published on F-Droid.
- Python has the widest pool of contributors for the server and bot, and mature
  libraries for Google APIs, images and PDFs.
- The domain model exists in more than one language (Python, Kotlin,
  TypeScript). The schema, generated clients and golden tests keep them in step.
- SQLite support constrains the server to portable SQL. Migrations are tested
  against both databases.
- Each part has its own linters and tests in CI: ruff and mypy (strict) for
  Python, detekt and ktlint for Kotlin, eslint and tsc for the web.

## Alternatives considered

- **Kotlin everywhere** (Ktor on the server, Kotlin Multiplatform for shared
  code). One domain model with no duplication, but a smaller pool of
  contributors, and a weaker fit for the bot and the image tooling.
- **A cross-platform app** (Flutter or React Native). iOS for free, but less
  direct control of the camera pipeline, where latency matters most, and iOS is
  not needed.
- **Server-side ML to find codes in photos** (as in an earlier prototype that
  used Detectron2). Far heavier than needed: zxing-cpp finds Data Matrix codes
  in photos quickly on a CPU.
- **A web scanner instead of a native app.** Browser camera access and decoding
  are not fast or controllable enough for a caption that follows a label
  smoothly in live mode.
