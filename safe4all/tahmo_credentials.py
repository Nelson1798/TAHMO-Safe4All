"""Load TAHMO API credentials from the shared SAFE4ALL-workshop Drive folder.

Kept free of pandas/requests so it can be imported and tested anywhere.
"""

from __future__ import annotations

import os
from pathlib import Path

from .shared_drive import find_shared_drive_file

SHARED_CREDENTIALS_FILENAME = "tahmo-credentials.txt"
_KEY_NAMES = {"tahmo_api_key", "api_key", "key", "username", "user"}
_SECRET_NAMES = {"tahmo_api_secret", "api_secret", "secret", "password"}


def parse_credentials_file(path: Path) -> tuple[str, str]:
    """Read ``TAHMO_API_KEY=...`` and ``TAHMO_API_SECRET=...`` lines from a text file.

    Blank lines and ``#`` comments are ignored; ``key``/``username`` and
    ``secret``/``password`` are accepted as alternative names.
    """
    key = secret = None
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = (part.strip() for part in line.split("=", 1))
        value = value.strip("'\"")
        if name.lower() in _KEY_NAMES:
            key = value
        elif name.lower() in _SECRET_NAMES:
            secret = value
    if not key or not secret:
        raise ValueError(f"{path} must contain TAHMO_API_KEY=... and TAHMO_API_SECRET=... lines")
    return key, secret


def load_shared_credentials() -> bool:
    """Put TAHMO credentials in the environment, from the shared Drive file if needed.

    Credentials already set in ``TAHMO_API_KEY`` / ``TAHMO_API_SECRET`` win.
    Returns ``True`` when both are available.
    """
    if os.environ.get("TAHMO_API_KEY") and os.environ.get("TAHMO_API_SECRET"):
        return True
    path = find_shared_drive_file(SHARED_CREDENTIALS_FILENAME)
    if path is None:
        return False
    key, secret = parse_credentials_file(path)
    os.environ["TAHMO_API_KEY"], os.environ["TAHMO_API_SECRET"] = key, secret
    return True
