"""Transparent station rainfall quality checks used before product validation."""

from __future__ import annotations

import pandas as pd


def qc_daily_precipitation(observations: pd.DataFrame, max_daily_mm: float = 500) -> pd.DataFrame:
    """Aggregate controlled TAHMO precipitation and retain clear QC diagnostics.

    The API quality flag is preserved. Values outside a physically plausible
    daily range are flagged rather than silently removed.
    """
    required = {"time", "value", "station"}
    missing = required - set(observations.columns)
    if missing:
        raise ValueError(f"TAHMO observations are missing columns: {sorted(missing)}")
    data = observations.copy()
    data["time"] = pd.to_datetime(data["time"], utc=True)
    data["value"] = pd.to_numeric(data["value"], errors="coerce")
    data["date"] = data["time"].dt.floor("D")
    grouping = ["station", "date"]
    daily = data.groupby(grouping, as_index=False).agg(
        precipitation_mm=("value", "sum"), observations=("value", "count"),
        quality_flag=("quality", "min") if "quality" in data else ("value", "size"),
    )
    daily["negative_flag"] = daily["precipitation_mm"] < 0
    daily["extreme_flag"] = daily["precipitation_mm"] > max_daily_mm
    daily["usable"] = ~daily["negative_flag"] & ~daily["extreme_flag"]
    return daily
