"""Minimal, credential-free-on-disk access to TAHMO precipitation data."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import requests


API_ROOT = "https://datahub.tahmo.org"
COUNTRY_CODES = {"Kenya": "KE", "Zimbabwe": "ZW", "Ghana": "GH"}


def credentials() -> tuple[str, str]:
    """Read TAHMO credentials from environment variables, never from Git."""
    key = os.environ.get("TAHMO_API_KEY")
    secret = os.environ.get("TAHMO_API_SECRET")
    if not key or not secret:
        raise RuntimeError(
            "Set TAHMO_API_KEY and TAHMO_API_SECRET in the notebook environment before fetching live station data."
        )
    return key, secret


def _get(endpoint: str, params: dict | None = None) -> dict:
    key, secret = credentials()
    response = requests.get(
        f"{API_ROOT}/{endpoint}", params=params, auth=(key, secret), timeout=60
    )
    response.raise_for_status()
    return response.json()


def stations(country: str) -> pd.DataFrame:
    """Fetch station metadata for a workshop country."""
    if country not in COUNTRY_CODES:
        raise ValueError(f"Unsupported country: {country}")
    payload = _get("services/assets/v2/stations", {"sort": "code"})
    frame = pd.json_normalize(payload["data"])
    return frame.loc[
        frame["location.countrycode"].eq(COUNTRY_CODES[country])
        & ~frame["code"].astype(str).str.contains("TH", na=False)
    ].copy()


def station_precipitation(station_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch controlled precipitation observations for one station as long data.

    Quality flags are retained; filtering happens explicitly in the QC step.
    """
    payload = _get(
        f"services/measurements/v2/stations/{station_code}/measurements/controlled",
        {"start": f"{start_date}T00:00:00Z", "end": f"{end_date}T23:59:59Z", "variable": "pr"},
    )
    rows = []
    for result in payload.get("results", []):
        for series in result.get("series", []):
            columns = series.get("columns", [])
            for values in series.get("values", []):
                row = dict(zip(columns, values))
                if row.get("variable") == "pr":
                    row["station"] = station_code
                    rows.append(row)
    return pd.DataFrame(rows)


def save_station_metadata(path: Path, country: str) -> None:
    stations(country).to_csv(path, index=False)
