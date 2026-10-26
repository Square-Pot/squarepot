# Deployment

Docker Compose setup for self-hosting: API, worker, bot, web app, database and
Caddy with automatic HTTPS.
The server image, which also serves the web app, is built; the rest of the
stack (worker, bot, database, Caddy) is not built yet.

Configuration comes only from environment variables. [`.env.example`](.env.example)
lists every variable the stack reads; copy it to `.env` and fill it in. Never
commit `.env`.

## Pull instead of building

Building the server image takes more memory and time than a small host can
spare. CI builds it on every push to `main`, tests it, and publishes it as
`ghcr.io/square-pot/squarepot-server`, tagged with the commit's full hash and
with `main`. The package is private, so the host logs in once with a GitHub
token that can only read packages:

1. On GitHub, create a personal access token (classic) with the single scope
   `read:packages`, and give it an expiry date.
2. On the host:

   ```sh
   docker login ghcr.io --username <github-user>
   # paste the token as the password
   ```

3. In `.env`, choose the image. A commit's tag never changes; `main` follows
   the latest build.

   ```sh
   SQUAREPOT_IMAGE=ghcr.io/square-pot/squarepot-server:main
   ```

4. Start it, without `--build`:

   ```sh
   docker compose pull
   docker compose up -d
   ```

To update, run the same two commands again.

## Memory

`compose.yaml` caps the server at `SQUAREPOT_MEMORY_LIMIT`, 1 GB unless `.env`
says otherwise. Above it the kernel stops the server and Docker starts it
again. CI measures the server's memory on every build, idle and at its peak
while printing the largest label request (2000 labels), and shows it in the
summary of the *Server image* job. Keep the cap well above that peak.

## Behind another reverse proxy

A label request answers with an `X-Cut-Captions` header that names every
label whose text was cut short: about 12 bytes per label with a short
collection id, so up to about 24 KB for 2000 labels, more with long
collection ids. Caddy passes headers of that size. nginx with its default
buffers answers `502` ("upstream sent too big header") instead, so raise
them in the server's `location` block:

```nginx
proxy_buffer_size 64k;
proxy_buffers 8 64k;
proxy_busy_buffers_size 128k;
```
