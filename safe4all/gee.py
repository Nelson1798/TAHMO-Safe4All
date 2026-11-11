"""Small, explicit Google Earth Engine helpers for workshop notebooks.

By default Earth Engine signs in with the workshop service-account key stored as
``service-key.json`` in the shared ``SAFE4ALL-workshop`` Google Drive folder, so
participants do not each need an OAuth login. The key is never stored in this
repository.
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path

from .config import country_settings

SHARED_KEY_FOLDER = "SAFE4ALL-workshop"
SHARED_KEY_FILENAME = "service-key.json"


def _shared_key_candidates() -> list[Path]:
    """Places ``SAFE4ALL-workshop/service-key.json`` can appear, most specific first.

    ``SAFE4ALL_SA_KEY_DIR`` points straight at the folder (tests or an unusual
    Drive mount). Otherwise the folder is looked up as a Shared Drive or as a My
    Drive folder/shortcut, both in Colab and in Google Drive for Desktop.
    """
    override = os.environ.get("SAFE4ALL_SA_KEY_DIR")
    if override:
        return [Path(override) / SHARED_KEY_FILENAME]

    folder = os.environ.get("SAFE4ALL_SHARED_DRIVE", SHARED_KEY_FOLDER)
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

    candidates = []
    for root in drive_roots:
        for match in sorted(glob.glob(root)) if "*" in root else [root]:
            candidates.append(Path(match) / folder / SHARED_KEY_FILENAME)
    return candidates


def _mount_colab_drive() -> None:
    """Mount Google Drive in Colab (no-op elsewhere or if already mounted)."""
    try:
        from google.colab import drive
    except ImportError:
        return
    if not Path("/content/drive/MyDrive").exists():
        drive.mount("/content/drive", force_remount=False)


def shared_drive_key_path() -> Path | None:
    """Return ``SAFE4ALL-workshop/service-key.json`` if it can be found, else ``None``."""
    if not os.environ.get("SAFE4ALL_SA_KEY_DIR"):
        _mount_colab_drive()
    for candidate in _shared_key_candidates():
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


def initialise_earth_engine(project: str | None = None):
    """Authenticate and return the Earth Engine module.

    Since November 2024, Earth Engine requires every request to be attached
    to a Google Cloud project. Pass ``project`` explicitly or set the
    ``EE_PROJECT`` environment variable (the notebook's Section 1 does this).

    Authentication order:

    1. **Explicit key file:** ``EE_SERVICE_ACCOUNT_KEY`` (or the standard
       ``GOOGLE_APPLICATION_CREDENTIALS``) pointing to a service-account JSON
       key. It must exist.
    2. **Shared Drive key (default):** ``service-key.json`` in the shared
       ``SAFE4ALL-workshop`` Google Drive folder. In Colab, Drive is mounted
       automatically.
    3. **Interactive OAuth:** if no key is found, the usual
       ``ee.Authenticate()`` browser prompt is used.

    Key files must never be committed to the repository.
    """
    project = project or os.environ.get("EE_PROJECT")
    if not project:
        raise RuntimeError(
            "Earth Engine needs a Cloud project. Set EE_PROJECT in Section 1 "
            "of the notebook to a project where you have enabled the Earth "
            "Engine API (see https://console.cloud.google.com/)."
        )
    import ee

    key_path = os.environ.get("EE_SERVICE_ACCOUNT_KEY") or os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS"
    )
    if key_path:
        key_path = Path(key_path)
        if not key_path.is_file():
            raise FileNotFoundError(f"Service account key not found: {key_path}")
    else:
        key_path = shared_drive_key_path()
        if key_path is None:
            folder = os.environ.get("SAFE4ALL_SHARED_DRIVE", SHARED_KEY_FOLDER)
            print(
                f"{SHARED_KEY_FILENAME} was not found in the shared '{folder}' Drive folder; "
                "falling back to interactive Earth Engine sign-in. If the folder was shared "
                "with you, add it to your Drive (Shared with me -> right-click it -> "
                "Organize -> Add shortcut -> My Drive) and re-run."
            )

    if key_path:
        key_info = json.loads(Path(key_path).read_text())
        credentials = ee.ServiceAccountCredentials(key_info["client_email"], str(key_path))
        ee.Initialize(credentials, project=project)
        return ee

    try:
        ee.Initialize(project=project)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=project)
    return ee


def country_boundary(ee, country: str):
    """Return the GAUL level-0 boundary for a selected workshop country."""
    country_settings(country)  # Validate before making a remote request.
    return ee.FeatureCollection("FAO/GAUL/2015/level0").filter(
        ee.Filter.eq("ADM0_NAME", country)
    )
