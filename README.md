# Square-Pot

Square-Pot is an open, self-hosted system for managing a plant collection.
Every pot carries a small label with a Data Matrix code that holds the plant's
six-digit number. Point a phone camera at the pots and each plant's name
appears next to its label in the live video, for a single plant or a whole
tray at once. From there you can copy the details, share them to a chat, or
take a photo with every plant already captioned.

The collection itself lives in a Google Sheet owned by the user. The server
only caches, indexes and syncs it. If the server goes away, the data stays
complete and readable in the spreadsheet, with no software needed.

> **Status: early design.** There is no working code yet. The repository holds
> the project skeleton, tooling and design documents. Expect breaking changes
> until the first release.

## Components

| Directory | Component | What it does |
| --- | --- | --- |
| [`android/`](android/) | Android app | Camera with labels drawn over the live video, single-plant and group modes, copy and share, captioned photos, offline cache |
| [`server/`](server/) | Server | HTTP API, Google Sheets sync, label generation, photo captions, multi-user mode |
| [`web/`](web/) | Web app | Label designer, onboarding and spreadsheet connection, collections and sharing, field presets |
| [`bot/`](bot/) | Telegram bot | Thin client to the API: look up a plant by number, inline mode, captions on photos you send |
| [`schema/`](schema/) | Field schema | The single machine-readable definition of plant fields, plus the OpenAPI contract |
| [`deploy/`](deploy/) | Deployment | Docker Compose setup for self-hosting |
| [`docs/`](docs/) | Documentation | Requirements, data model, architecture decision records, self-hosting guide |

## Design principles

- **The spreadsheet is the source of truth.** The server is a cache and a sync
  engine. On conflict, the spreadsheet wins.
- **One field schema.** Fields are defined once in [`schema/`](schema/). The API,
  labels, captions, the app and the web all follow it.
- **A fixed label format.** A label encodes only a six-digit number in a 10×10
  Data Matrix, the smallest square symbol that holds six digits. This keeps
  labels as small as possible.
- **Easy to self-host.** One `docker compose` command on a clean machine.

## Documentation

Design documents are in [`docs/`](docs/). They come before the code: requirements,
the spreadsheet format and decision records will land there first.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, commit
convention and pull request flow. Please follow the
[Code of Conduct](CODE_OF_CONDUCT.md). To report a vulnerability, see
[SECURITY.md](SECURITY.md).

## License

Not chosen yet. Until a license is added, all rights are reserved.
