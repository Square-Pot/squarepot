# SPDX-License-Identifier: AGPL-3.0-or-later
"""The built web app, served at `/` beside the API.

It answers only what no route matches, as the router's default: any path that
is not a file of the build and has no file extension gets `index.html`, so that
the app's own addresses (`/c/main?genus=Lithops`) open directly. Paths under
`/api/` never do: there an unknown path stays a `404`.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from fastapi import HTTPException, Request, status
from fastapi.responses import FileResponse
from starlette.types import Receive, Scope, Send
from starlette.websockets import WebSocketClose

from squarepot_server.runtime import Runtime

# Vite names every file in assets/ by a hash of its content.
IMMUTABLE = "public, max-age=31536000, immutable"
# The page holds the API token: it runs only its own scripts and talks only to this server.
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' blob: data:; object-src 'none'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


def web_file(request: Request) -> FileResponse:
    runtime: Runtime = request.app.state.runtime
    root = runtime.settings.web_dir
    path = request.url.path.lstrip("/")
    if root is None or path == "api" or path.startswith("api/"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    if request.method not in ("GET", "HEAD"):
        raise HTTPException(status.HTTP_405_METHOD_NOT_ALLOWED, "Method Not Allowed")
    root = root.resolve()
    try:
        file = (root / path).resolve()
        found = bool(path) and file.is_relative_to(root) and file.is_file()
    except (OSError, ValueError) as error:  # such as a NUL byte in the path
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found") from error
    if found:
        cache = IMMUTABLE if file.parent == root / "assets" else "no-cache"
        return FileResponse(file, headers={"Cache-Control": cache, **SECURITY_HEADERS})
    if PurePosixPath(path).suffix:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    return FileResponse(
        root / "index.html", headers={"Cache-Control": "no-cache", **SECURITY_HEADERS}
    )


async def serve(scope: Scope, receive: Receive, send: Send) -> None:
    """The router's default: what it runs when no route matches."""
    if scope["type"] == "websocket":
        # As Starlette's own default does.
        await WebSocketClose()(scope, receive, send)
        return
    response = web_file(Request(scope, receive))
    await response(scope, receive, send)
