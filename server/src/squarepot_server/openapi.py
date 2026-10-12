# SPDX-License-Identifier: AGPL-3.0-or-later
"""Print the OpenAPI document of the API.

Usage:
    uv run python -m squarepot_server.openapi > openapi.json
"""

from __future__ import annotations

import json
from typing import Any

from squarepot_server.app import create_app


def document() -> dict[str, Any]:
    return create_app().openapi()


def render() -> str:
    return json.dumps(document(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    print(render(), end="")
