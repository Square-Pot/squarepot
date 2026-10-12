# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from importlib.metadata import version

import squarepot_server


def test_version_comes_from_the_package_metadata() -> None:
    assert squarepot_server.__version__ == version("squarepot-server")
