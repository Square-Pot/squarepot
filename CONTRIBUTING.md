# Contributing to Square-Pot

Thank you for your interest in Square-Pot. The project is in early design, so
the most useful contributions right now are comments on the design documents
in [`docs/`](docs/) and issues that describe real collection workflows.

By taking part you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ground rules

- **Discuss first.** For anything beyond a small fix, open an issue before
  writing code, so we can agree on the approach.
- **Design before code.** Changes to the field schema, the API contract or the
  label format start as a document or an ADR in `docs/`.
- **The label format is fixed.** A label encodes only a six-digit number in a
  10×10 Data Matrix. Proposals to add URLs, prefixes or other data to it will
  be declined: they make labels bigger.
- **The schema is the contract.** Fields are defined once in `schema/`. The
  API, labels, captions, the app and the web follow it; they never define
  fields of their own.
- **English everywhere** in code, comments, documentation, commits and pull
  requests. The user interface ships in English and Russian.

## Development setup

You need Git and [pre-commit](https://pre-commit.com/). Install the hooks once
after cloning:

```sh
pre-commit install
```

The hooks check for leaked secrets ([gitleaks](https://github.com/gitleaks/gitleaks)),
whitespace and line endings, Markdown style and GitHub workflow files. Run them
on the whole tree with:

```sh
pre-commit run --all-files
```

Each component adds its own linters, type checks and tests as it gets code;
its README explains how to run them locally.

## Licensing

The server, bot and web app are licensed under `AGPL-3.0-or-later`; the
Android app and `schema/` under `Apache-2.0` (see the README). Start every
new source file with an [SPDX](https://spdx.dev/) identifier of the license
of its directory, in the file's comment syntax:

```python
# SPDX-License-Identifier: AGPL-3.0-or-later
```

By contributing, you agree that your contribution is licensed under the
license of the directory it goes into.

## Configuration and secrets

- All configuration comes from environment variables.
- Every variable a component reads is listed, with a comment and a safe
  placeholder, in [`deploy/.env.example`](deploy/.env.example). Add it in the
  same pull request that starts reading it.
- Never commit secrets: no `.env` files, API keys, OAuth client secrets,
  service-account JSON or signing keys. gitleaks runs in pre-commit and in CI.
  If you commit a secret by accident, treat it as leaked: revoke it first, then
  remove it.

## Commits

Commits follow [Conventional Commits](https://www.conventionalcommits.org/):

```text
<type>(<scope>): <summary>

<body: what changed and why>
```

- **type**: `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`, `ci`,
  `chore`, `revert`.
- **scope** (optional): the component, such as `server`, `android`, `web`,
  `bot`, `schema`, `deploy`.
- **summary**: imperative mood, lower case, no trailing period, about 72
  characters at most.
- Breaking changes: add `!` after the type or scope and a `BREAKING CHANGE:`
  footer.

Keep commits atomic: one logical change per commit, with the tree building and
the tests passing at every commit. Rebase and squash fixups before review.

## Pull requests

1. Branch from `main` with a descriptive name, for example
   `feat/server-sheets-sync` or `fix/android-overlay-jitter`.
2. Keep the pull request focused on one change. Fill in the template: what,
   why, how it was tested.
3. CI must be green: secret scan, linters, type checks and tests.
4. At least one maintainer approval is required. Nobody merges their own pull
   request.
5. Pull requests are merged into `main` once approved; `main` stays releasable.

## Reporting bugs and requesting features

Use the issue templates. For security problems, do **not** open a public
issue: follow [SECURITY.md](SECURITY.md).
