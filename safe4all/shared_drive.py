"""Get workshop secret files (Earth Engine key, TAHMO credentials).

Each file is fetched, in order of preference:

1. **By Google Drive file ID** (``<FILE>_FILE_ID`` setting): the file is shared
   as "Anyone with the link" and downloaded with ``gdown``, so participants
   need only the workshop notebook link, with no Drive access or mounting.
2. **From the shared ``SAFE4ALL-workshop`` Drive folder**, for people who have
   that folder in their Drive.

Secrets and their file IDs are never stored in this repository.
"""

from __future__ import annotations

import glob
import os
import tempfile
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


def download_drive_file(file_id: str, filename: str) -> Path:
    """Download a link-shared Google Drive file to a private temp folder and return its path."""
    import gdown

    target_dir = Path(tempfile.gettempdir()) / "safe4all-secrets"
    target_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = target_dir / filename
    target.unlink(missing_ok=True)
    try:
        gdown.download(f"https://drive.google.com/uc?id={file_id}", str(target), quiet=True)
    except Exception as error:
        raise RuntimeError(f"Could not download {filename} from Google Drive: {error}") from error
    if not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError(
            f"Could not download {filename} from Google Drive (file ID {file_id}). "
            "Check the ID and that the file is shared as 'Anyone with the link'."
        )
    target.chmod(0o600)
    return target


def get_workshop_file(filename: str, file_id_env: str) -> Path | None:
    """Return a workshop secret file: by Drive file ID if ``file_id_env`` is set, else from the shared folder."""
    file_id = os.environ.get(file_id_env, "").strip()
    if file_id:
        return download_drive_file(file_id, filename)
    return find_shared_drive_file(filename)
