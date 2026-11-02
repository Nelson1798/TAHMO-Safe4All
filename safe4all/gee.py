"""Small, explicit Google Earth Engine helpers for workshop notebooks."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .config import country_settings


def initialise_earth_engine(project: str | None = None):
    """Authenticate when required and return the Earth Engine module.

    Since November 2024, Earth Engine requires every request to be attached
    to a Google Cloud project. Pass ``project`` explicitly or set the
    ``EE_PROJECT`` environment variable (the notebook's Section 1 does this).

    Two authentication modes are supported:

    - **Service account (headless, good for a shared workshop project):** set
      ``EE_SERVICE_ACCOUNT_KEY`` (or the standard
      ``GOOGLE_APPLICATION_CREDENTIALS``) to the local path of a service
      account JSON key. The key file itself must never be committed to the
      repository — keep it outside the project folder, or inside
      ``.safe4all-cache/`` (already git-ignored).
    - **Interactive OAuth (default, good for individual accounts):** if no
      key file is configured, the usual ``ee.Authenticate()`` browser prompt
      is used.
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
        key_info = json.loads(key_path.read_text())
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
