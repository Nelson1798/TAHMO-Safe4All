"""Small, explicit Google Earth Engine helpers for workshop notebooks.

Authentication is **zero-friction by default**: the notebook signs in with the
shared SAFE4ALL / TAHMO workshop *service account*, exactly like the TAHMO/NOAA
workshop notebooks. Participants therefore do not need their own Google Cloud
project, which is what caused the ``PERMISSION_DENIED`` / "Caller does not have
required permission to use project" errors when each person authenticated with a
personal account that had no access to the workshop project.

The service-account key is **not stored in this repository**. It is downloaded
at run time from the shared Google Drive file that TAHMO already uses for the
other workshop notebooks, so no credential is committed here.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .config import country_settings

# Shared workshop identifiers (not secrets: a project id, an email and a Drive
# file id). The private key itself lives only in the Drive file below.
SHARED_EE_PROJECT = "natural-notch-435413-j3"
SHARED_SA_EMAIL = "gee-notebook-user@natural-notch-435413-j3.iam.gserviceaccount.com"
SHARED_SA_KEY_DRIVE_ID = "181IKB3sJ3iUn6ZOZbg50htgH2JKcxFkT"


def _shared_key_path() -> Path:
    """Local path the shared service-account key is cached at (overridable in tests)."""
    override = os.environ.get("SAFE4ALL_SA_KEY_CACHE")
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "safe4all_ee_service_account.json"


def _shared_service_account_credentials(ee):
    """Download (once) and return the shared workshop service-account credentials.

    Returns ``(credentials, project_id)``. Raises if the key cannot be obtained.
    """
    key_path = _shared_key_path()
    if not key_path.is_file() or key_path.stat().st_size == 0:
        import gdown

        key_path.parent.mkdir(parents=True, exist_ok=True)
        gdown.download(
            f"https://drive.google.com/uc?id={SHARED_SA_KEY_DRIVE_ID}",
            str(key_path),
            quiet=True,
        )
    if not key_path.is_file() or key_path.stat().st_size == 0:
        raise RuntimeError(
            "Could not download the shared service-account key from Google Drive. "
            "Check your connection, or set EE_SERVICE_ACCOUNT_KEY to a local key "
            "file, or set SAFE4ALL_EE_AUTH=personal to sign in with your own account."
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
       SAFE4ALL/TAHMO service account is downloaded from Google Drive and used,
       so no personal project is required.
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
            ee.Initialize(credentials, project=project or sa_project)
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
