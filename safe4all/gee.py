"""Small, explicit Google Earth Engine helpers for workshop notebooks.

By default Earth Engine signs in with the workshop service-account key
``service-key.json``, downloaded by its Google Drive file ID or read from the
shared ``SAFE4ALL-workshop`` Drive folder, so participants do not each need an
OAuth login. The key is never stored in this
repository.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .config import country_settings
from .shared_drive import DEFAULT_FOLDER, get_workshop_file

SHARED_KEY_FILENAME = "service-key.json"
SERVICE_KEY_FILE_ID_ENV = "SAFE4ALL_SERVICE_KEY_FILE_ID"


def initialise_earth_engine(project: str | None = None):
    """Authenticate and return the Earth Engine module.

    Since November 2024, Earth Engine requires every request to be attached
    to a Google Cloud project. Pass ``project`` explicitly or set the
    ``EE_PROJECT`` environment variable (the notebook's Section 1 does this).

    Authentication order:

    1. **Explicit key file:** ``EE_SERVICE_ACCOUNT_KEY`` (or the standard
       ``GOOGLE_APPLICATION_CREDENTIALS``) pointing to a service-account JSON
       key. It must exist.
    2. **Workshop key (default):** ``service-key.json`` downloaded by its
       Google Drive file ID (``SAFE4ALL_SERVICE_KEY_FILE_ID``, set from
       ``SERVICE_KEY_FILE_ID`` in the notebook), or else found in the shared
       ``SAFE4ALL-workshop`` Drive folder (Drive is mounted in Colab).
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
        key_path = get_workshop_file(SHARED_KEY_FILENAME, SERVICE_KEY_FILE_ID_ENV)
        if key_path is None:
            folder = os.environ.get("SAFE4ALL_SHARED_DRIVE", DEFAULT_FOLDER)
            print(
                f"No workshop key: SERVICE_KEY_FILE_ID is not set and {SHARED_KEY_FILENAME} "
                f"was not found in the shared '{folder}' Drive folder; falling back to "
                "interactive Earth Engine sign-in."
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
