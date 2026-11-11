"""Small, explicit Google Earth Engine helpers for workshop notebooks.

Authentication is **zero-friction by default**: the notebook signs in with the
shared SAFE4ALL / TAHMO workshop *service account*, exactly like the TAHMO/NOAA
workshop notebooks. Participants therefore do not need their own Google Cloud
project, which is what caused the ``PERMISSION_DENIED`` / "Caller does not have
required permission to use project" errors when each person authenticated with a
personal account that had no access to the workshop project.

The service-account key is **not stored in this repository**. It is read at run
time from ``service-key.json`` in the shared ``SAFE4ALL-workshop`` Google Drive
folder; if that folder is not shared with the user, the key is downloaded from
its shared Drive file link instead (the same mechanism the TAHMO/NOAA notebooks
use). Either way, no credential is committed here.
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path

from .config import country_settings

# Shared workshop identifiers (not secrets: a project id and an email). The
# private key itself lives only in the shared Drive folder below.
SHARED_EE_PROJECT = "natural-notch-435413-j3"
SHARED_SA_EMAIL = "gee-notebook-user@natural-notch-435413-j3.iam.gserviceaccount.com"
SHARED_KEY_FOLDER = "SAFE4ALL-workshop"
SHARED_KEY_FILENAME = "service-key.json"
# Fallback: the same shared key file the TAHMO/NOAA workshop notebooks download
# (a public "anyone with the link" Drive file). Used when the Shared Drive folder
# above is not shared with the person running the notebook.
SHARED_SA_KEY_DRIVE_ID = "181IKB3sJ3iUn6ZOZbg50htgH2JKcxFkT"


def _shared_key_candidates() -> list[Path]:
    """Places ``SAFE4ALL-workshop/service-key.json`` can appear, most specific first.

    ``SAFE4ALL_SA_KEY_DIR`` points straight at the folder (useful for tests or an
    unusual Drive mount). Otherwise the folder is looked up as a Shared Drive or
    as a MyDrive folder/shortcut, both in Colab and in Google Drive for Desktop.
    """
    override = os.environ.get("SAFE4ALL_SA_KEY_DIR")
    if override:
        return [Path(override) / SHARED_KEY_FILENAME]

    folder = os.environ.get("SAFE4ALL_SHARED_DRIVE", SHARED_KEY_FOLDER)
    drive_roots = [
        "/content/drive/Shareddrives",       # Colab, Shared Drive
        "/content/drive/MyDrive",            # Colab, MyDrive folder or shortcut
        "/content/drive/.shortcut-targets-by-id/*",  # Colab, "Shared with me" shortcut
    ]
    home = Path.home()
    for desktop_root in glob.glob(str(home / "Library" / "CloudStorage" / "GoogleDrive-*")) + [
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


def _locate_shared_key() -> Path | None:
    """Return the shared key in the SAFE4ALL-workshop Drive folder, or None if absent."""
    if not os.environ.get("SAFE4ALL_SA_KEY_DIR"):
        _mount_colab_drive()
    for candidate in _shared_key_candidates():
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


def _download_shared_key() -> Path | None:
    """Fallback: download the shared key from its Drive file link (gdown), like TAHMO/NOAA.

    Cached locally so it is fetched only once. Returns the path, or None if the
    download is not possible (gdown missing or the file unreachable).
    """
    import tempfile

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


def _shared_service_account_credentials(ee):
    """Return ``(credentials, project_id)`` for the shared workshop service account.

    The key is taken from the shared ``SAFE4ALL-workshop`` Drive folder when it is
    available, otherwise downloaded from its shared Drive file link.
    """
    key_path = _locate_shared_key() or _download_shared_key()
    if key_path is None:
        folder = os.environ.get("SAFE4ALL_SHARED_DRIVE", SHARED_KEY_FOLDER)
        raise FileNotFoundError(
            f"Could not read {SHARED_KEY_FILENAME} from the shared '{folder}' Google Drive "
            "folder, and could not download the shared key from its Drive link. Share the "
            "folder with yourself (in 'Shared with me', right-click it -> Organize -> Add "
            "shortcut -> My Drive), or set EE_SERVICE_ACCOUNT_KEY to a key file path, or set "
            "EE_AUTH = 'personal' to sign in with your own account."
        )
    info = json.loads(key_path.read_text())
    credentials = ee.ServiceAccountCredentials(info["client_email"], str(key_path))
    return credentials, info.get("project_id", SHARED_EE_PROJECT)


def initialise_earth_engine(project: str | None = None):
    """Authenticate with Earth Engine and return the ``ee`` module.

    Authentication order:

    1. **Explicit key file** — if ``EE_SERVICE_ACCOUNT_KEY`` (or the standard
       ``GOOGLE_APPLICATION_CREDENTIALS``) points to a service-account JSON key,
       that key is used. Never commit such a file to the repository.
    2. **Shared workshop service account (default)** — otherwise the shared
       SAFE4ALL/TAHMO service-account key is read from ``service-key.json`` in
       the shared ``SAFE4ALL-workshop`` Drive folder, so no personal project is
       required.
    3. **Personal OAuth** — set ``SAFE4ALL_EE_AUTH=personal`` (and ``EE_PROJECT``
       to a project where you have enabled the Earth Engine API) to sign in with
       your own Google account instead. This path is also used automatically if
       the shared service account cannot be reached.
    """
    project = project or os.environ.get("EE_PROJECT")
    key_path = os.environ.get("EE_SERVICE_ACCOUNT_KEY") or os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS"
    )
    auth_mode = os.environ.get("SAFE4ALL_EE_AUTH", "").strip().lower()

    # Personal OAuth needs a project; fail fast with a clear message before the
    # (possibly slow) Earth Engine import.
    if auth_mode == "personal" and not key_path and not project:
        raise RuntimeError(
            "Personal Earth Engine auth needs a Cloud project. Set EE_PROJECT in "
            "Section 1 to a project where you have enabled the Earth Engine API "
            "(https://console.cloud.google.com/), or unset SAFE4ALL_EE_AUTH to use "
            "the shared workshop service account."
        )

    import ee

    # 1) Explicit, admin-provided key file.
    if key_path:
        key_path = Path(key_path)
        if not key_path.is_file():
            raise FileNotFoundError(f"Service account key not found: {key_path}")
        key_info = json.loads(key_path.read_text())
        credentials = ee.ServiceAccountCredentials(key_info["client_email"], str(key_path))
        ee.Initialize(credentials, project=project or key_info.get("project_id"))
        return ee

    # 2) Shared workshop service account (default, zero-friction).
    if auth_mode != "personal":
        try:
            credentials, sa_project = _shared_service_account_credentials(ee)
            # Use the key's own project: a service account only has access to its
            # own project, so an EE_PROJECT override here would reintroduce the
            # permission error when the two differ.
            ee.Initialize(credentials, project=sa_project or project)
            return ee
        except Exception as error:  # pragma: no cover - network/credential issues
            print(
                f"Shared workshop service account unavailable ({error}); "
                "falling back to personal Earth Engine sign-in."
            )

    # 3) Personal interactive OAuth.
    if not project:
        raise RuntimeError(
            "Earth Engine needs a Cloud project for personal sign-in. Set EE_PROJECT "
            "in Section 1 to a project where you have enabled the Earth Engine API "
            "(https://console.cloud.google.com/)."
        )
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
