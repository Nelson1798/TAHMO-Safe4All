"""Small, explicit Google Earth Engine helpers for workshop notebooks.

By default Earth Engine signs in with the shared SAFE4ALL / TAHMO workshop
*service account*, so participants never need their own Google Cloud project or an
OAuth login. This is the same zero-friction mechanism the TAHMO/NOAA workshop
notebooks use: the service-account key is downloaded at run time from its shared
Google Drive file link. If that download is not possible, the notebook falls back
to ``service-key.json`` in the shared ``SAFE4ALL-workshop`` Drive folder and then
to interactive sign-in. The key is never stored in this repository.
"""

from __future__ import annotations

import glob
import json
import os
import tempfile
from pathlib import Path

from .config import country_settings

SHARED_KEY_FOLDER = "SAFE4ALL-workshop"
SHARED_KEY_FILENAME = "service-key.json"
# Primary shared access: the same service-account key file the TAHMO/NOAA workshop
# notebooks download (a public "anyone with the link" Drive file, project
# natural-notch-435413-j3). Only the file id is public here, never the key itself.
SHARED_SA_KEY_DRIVE_ID = "181IKB3sJ3iUn6ZOZbg50htgH2JKcxFkT"
SHARED_EE_PROJECT = "natural-notch-435413-j3"


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


def download_shared_key() -> Path | None:
    """Download the shared workshop key from its Drive file link (gdown), like TAHMO/NOAA.

    Cached locally so it is fetched only once. Returns the path, or ``None`` if the
    download is not possible (gdown missing or the file unreachable).
    """
    dest = Path(
        os.environ.get("SAFE4ALL_SA_KEY_CACHE")
        or Path(tempfile.gettempdir()) / "safe4all_service_key.json"
    )
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    try:
        import gdown
    except ImportError:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        gdown.download(
            f"https://drive.google.com/uc?id={SHARED_SA_KEY_DRIVE_ID}", str(dest), quiet=True
        )
    except Exception:
        return None
    return dest if dest.is_file() and dest.stat().st_size > 0 else None


def initialise_earth_engine(project: str | None = None):
    """Authenticate and return the Earth Engine module.

    Authentication order:

    1. **Explicit key file:** ``EE_SERVICE_ACCOUNT_KEY`` (or the standard
       ``GOOGLE_APPLICATION_CREDENTIALS``) pointing to a service-account JSON key.
    2. **Shared workshop service account (default):** the key is downloaded from
       its shared Drive file link (as in the TAHMO/NOAA notebooks), or read from
       ``service-key.json`` in the shared ``SAFE4ALL-workshop`` Drive folder.
       Earth Engine is initialised with the key's own project, so no personal
       project is required. Set ``SAFE4ALL_EE_AUTH=personal`` to skip this.
    3. **Interactive OAuth (fallback):** signs in with your own Google account
       against ``EE_PROJECT``. Used when the shared key cannot be obtained, or
       when ``SAFE4ALL_EE_AUTH=personal``.

    Key files must never be committed to the repository.
    """
    project = project or os.environ.get("EE_PROJECT")
    key_path_env = os.environ.get("EE_SERVICE_ACCOUNT_KEY") or os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS"
    )
    auth_mode = os.environ.get("SAFE4ALL_EE_AUTH", "").strip().lower()

    # Resolve a service-account key file *without* importing ee (so a missing
    # project still fails fast with a clear message rather than an ee import error).
    resolved_key: Path | None = None
    use_env_project = False
    if key_path_env:
        resolved_key = Path(key_path_env)
        if not resolved_key.is_file():
            raise FileNotFoundError(f"Service account key not found: {resolved_key}")
        use_env_project = True  # an admin key respects EE_PROJECT
    elif auth_mode != "personal":
        if os.environ.get("SAFE4ALL_SA_KEY_DIR"):
            resolved_key = shared_drive_key_path()          # explicit folder (tests / pinned mount)
        else:
            resolved_key = download_shared_key() or shared_drive_key_path()  # NOAA link, then folder

    # Interactive sign-in needs a project; fail fast before importing ee.
    if resolved_key is None and not project:
        raise RuntimeError(
            "Earth Engine needs a Cloud project. Set EE_PROJECT in Section 1 of the "
            "notebook to a project where you have enabled the Earth Engine API "
            "(see https://console.cloud.google.com/)."
        )

    import ee

    if resolved_key is not None:
        key_info = json.loads(resolved_key.read_text())
        credentials = ee.ServiceAccountCredentials(key_info["client_email"], str(resolved_key))
        # A service account only has access to its own project; use it unless this
        # is an admin-provided key, where the chosen EE_PROJECT is respected.
        init_project = project if use_env_project else (key_info.get("project_id") or project)
        ee.Initialize(credentials, project=init_project)
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
