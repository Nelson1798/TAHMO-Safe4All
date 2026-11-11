"""Find workshop files (keys, credentials) in the shared SAFE4ALL-workshop Drive folder.

Secrets live only in that Google Drive folder, never in this repository.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

DEFAULT_FOLDER = "SAFE4ALL-workshop"


def _candidate_folders() -> list[Path]:
    """Places the shared folder can appear, most specific first.

    ``SAFE4ALL_SA_KEY_DIR`` points straight at the folder (tests or an unusual
    Drive mount). Otherwise the folder (``SAFE4ALL_SHARED_DRIVE``, default
    ``SAFE4ALL-workshop``) is looked up as a Shared Drive or as a My Drive
    folder/shortcut, both in Colab and in Google Drive for Desktop.
    """
    override = os.environ.get("SAFE4ALL_SA_KEY_DIR")
    if override:
        return [Path(override)]

    folder = os.environ.get("SAFE4ALL_SHARED_DRIVE", DEFAULT_FOLDER)
    drive_roots = [
        "/content/drive/Shareddrives",                # Colab, Shared Drive
        "/content/drive/MyDrive",                     # Colab, My Drive folder or shortcut
        "/content/drive/.shortcut-targets-by-id/*",   # Colab, "Shared with me" shortcut
    ]
    home = Path.home()
    for desktop_root in sorted(glob.glob(str(home / "Library" / "CloudStorage" / "GoogleDrive-*"))) + [
        str(home / "Google Drive"), "G:", "H:",
    ]:
        drive_roots += [f"{desktop_root}/Shared drives", f"{desktop_root}/My Drive"]

    folders = []
    for root in drive_roots:
        for match in sorted(glob.glob(root)) if "*" in root else [root]:
            folders.append(Path(match) / folder)
    return folders


def _mount_colab_drive() -> None:
    """Mount Google Drive in Colab (no-op elsewhere or if already mounted)."""
    try:
        from google.colab import drive
    except ImportError:
        return
    if not Path("/content/drive/MyDrive").exists():
        drive.mount("/content/drive", force_remount=False)


def find_shared_drive_file(filename: str) -> Path | None:
    """Return ``<shared folder>/<filename>`` if it exists and is not empty, else ``None``."""
    if not os.environ.get("SAFE4ALL_SA_KEY_DIR"):
        _mount_colab_drive()
    for folder in _candidate_folders():
        candidate = folder / filename
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None
