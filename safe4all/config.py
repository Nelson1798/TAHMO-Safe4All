"""Country settings and risk-model defaults shared by the SAFE4ALL workshop notebooks."""

from __future__ import annotations

# Season months drive the Sentinel-1 flood mapping (flood vs dry reference)
# and the rainfall-anomaly indicator. ``season_year_start`` is the first month
# of the agricultural year, so seasons that cross 31 December (Zimbabwe) are
# summed as one season instead of being split across two calendar years.
COUNTRIES = {
    "Kenya": {
        "iso3": "KEN", "center": (0.2, 37.9), "zoom": 6, "bbox": (33.5, -4.8, 42.1, 5.5),
        "flood_months": [3, 4, 5, 10, 11, 12],   # long rains (MAM) and short rains (OND)
        "dry_months": [1, 2, 7, 8, 9],
        "rainy_months": [3, 4, 5, 10, 11, 12],
        "season_year_start": 1,
    },
    "Zimbabwe": {
        "iso3": "ZWE", "center": (-19.0, 29.2), "zoom": 6, "bbox": (25.0, -22.5, 33.0, -15.0),
        "flood_months": [12, 1, 2, 3],
        "dry_months": [6, 7, 8, 9],
        "rainy_months": [11, 12, 1, 2, 3],
        "season_year_start": 7,                  # July-June agricultural year
    },
    "Ghana": {
        "iso3": "GHA", "center": (7.9, -1.0), "zoom": 6, "bbox": (-3.5, 4.5, 1.5, 11.5),
        "flood_months": [6, 7, 8, 9, 10],
        "dry_months": [12, 1, 2, 3],
        "rainy_months": [4, 5, 6, 7, 8, 9, 10],
        "season_year_start": 1,
    },
}

AOI_MODES = ("country", "admin1", "district", "basin")

# Indicator weights for the multi-criteria model. Each group is normalised to
# sum to 1 at run time, so an unavailable optional layer simply drops out.
DEFAULT_WEIGHTS = {
    "drought_hazard": {
        "spi1": 0.10, "spi3": 0.15, "spi6": 0.15,
        "rainfall_anomaly": 0.10, "ndvi_anomaly": 0.15, "vci": 0.15, "soil_moisture": 0.20,
    },
    "flood_hazard": {
        "extreme_rainfall": 0.20, "observed_flood": 0.25, "hand": 0.20, "slope": 0.10,
        "flow_accumulation": 0.10, "river_proximity": 0.10, "low_elevation": 0.05,
    },
    "flood_exposure": {"population": 0.40, "settlements": 0.20, "cropland": 0.20, "infrastructure": 0.20},
    "drought_exposure": {"population": 0.40, "cropland": 0.45, "settlements": 0.05, "infrastructure": 0.10},
    "flood_vulnerability": {"socioeconomic": 0.50, "land_use": 0.30, "agricultural_dependence": 0.20},
    "drought_vulnerability": {"socioeconomic": 0.40, "land_use": 0.20, "agricultural_dependence": 0.40},
}

# Land-cover susceptibility scores (0-1) applied to Copernicus cover fractions.
FLOOD_LAND_USE_SCORES = {
    "urban": 1.0, "crops": 0.8, "water-seasonal": 0.6, "grass": 0.5, "shrub": 0.4,
    "bare": 0.4, "tree": 0.2, "moss": 0.2, "snow": 0.0, "water-permanent": 0.0,
}
DROUGHT_LAND_USE_SCORES = {
    "crops": 1.0, "grass": 0.8, "shrub": 0.7, "bare": 0.6, "urban": 0.3,
    "tree": 0.3, "moss": 0.3, "water-seasonal": 0.2, "snow": 0.0, "water-permanent": 0.0,
}

# Basemap for every map. OpenStreetMap's tile servers return "403 Access blocked"
# and CARTO now requires an API key; Esri World Street Map needs no key.
BASEMAP_NAME = "Esri World Street Map"
BASEMAP_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"
BASEMAP_ATTRIBUTION = "Tiles &copy; Esri &mdash; Source: Esri, HERE, Garmin, USGS, NGA, EPA, USDA, NPS"

CLASS_LABELS = ["Very Low", "Low", "Moderate", "High", "Very High"]
CLASS_COLORS = ["1a9850", "91cf60", "ffffbf", "fc8d59", "d73027"]
EQUAL_BREAKS = [0.2, 0.4, 0.6, 0.8]


def country_settings(country: str) -> dict:
    """Return workshop settings for a supported country."""
    try:
        settings = COUNTRIES[country]
    except KeyError as error:
        supported = ", ".join(COUNTRIES)
        raise ValueError(f"Unsupported country: {country}. Choose one of: {supported}.") from error
    return {key: list(value) if isinstance(value, list) else value for key, value in settings.items()}


def normalise_weights(weights: dict, available=None) -> dict:
    """Return positive weights rescaled to sum to 1, keeping only available layers.

    ``available`` is an optional iterable of layer names that exist for this
    run; weights for missing layers are dropped and the rest re-scaled.
    """
    if any(w < 0 for w in weights.values()):
        raise ValueError("Weights must not be negative.")
    keep = set(weights) if available is None else set(available)
    used = {name: w for name, w in weights.items() if w > 0 and name in keep}
    total = sum(used.values())
    if total <= 0:
        raise ValueError("No positive weights remain for the available layers.")
    return {name: w / total for name, w in used.items()}


def class_index(value: float, breaks=EQUAL_BREAKS) -> int:
    """Return the 1-5 risk class for a 0-1 index value (upper break inclusive)."""
    for position, upper in enumerate(breaks, start=1):
        if value <= upper:
            return position
    return len(breaks) + 1


def class_label(value: float, breaks=EQUAL_BREAKS) -> str:
    return CLASS_LABELS[class_index(value, breaks) - 1]
