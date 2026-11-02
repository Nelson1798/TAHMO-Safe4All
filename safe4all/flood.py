"""Step 5: flood-hazard indicators.

extreme rainfall (CHIRPS Rx1day) - Sentinel-1 observed flooding - DEM - slope -
HAND - flow accumulation - distance from river (MERIT Hydro 90 m).
"""

from __future__ import annotations

from .config import DEFAULT_WEIGHTS
from .drought import CHIRPS_DAILY, chirps_projection
from .ee_tools import inverse, linear_decay, minmax, month_filter, weighted_overlay

MERIT_HYDRO = "MERIT/Hydro/v1_0_1"
JRC_SURFACE_WATER = "JRC/GSW1_4/GlobalSurfaceWater"
SENTINEL1 = "COPERNICUS/S1_GRD"


def permanent_water(ee, occurrence_pct: float = 80):
    """JRC Global Surface Water pixels that are water at least ``occurrence_pct`` % of the time."""
    return (ee.Image(JRC_SURFACE_WATER).select("occurrence").unmask(0)
            .gte(occurrence_pct).rename("permanent_water"))


def extreme_rainfall(ee, region, start_year: int, end_year: int):
    """Mean annual maximum 1-day rainfall (Rx1day, ETCCDI) from CHIRPS daily, mm."""
    daily = ee.ImageCollection(CHIRPS_DAILY).select("precipitation")

    def annual_max(year):
        start = ee.Date.fromYMD(ee.Number(year).int(), 1, 1)
        return daily.filterDate(start, start.advance(1, "year")).max().rename("rx1day")

    years = ee.List.sequence(start_year, end_year)
    return ee.ImageCollection(years.map(annual_max)).mean().reproject(chirps_projection(ee)).clip(region)


def terrain(ee, region, river_upa_km2: float = 100):
    """DEM, slope, HAND, upstream area and distance from river (m) from MERIT Hydro."""
    merit = ee.Image(MERIT_HYDRO)
    rivers = merit.select("upa").gte(river_upa_km2).unmask(0)
    # fastDistanceTransform returns squared pixel distance; multiplying by the
    # pixel size of the output projection keeps metres correct at any scale.
    distance = (rivers.fastDistanceTransform(512, "pixels").sqrt()
                .multiply(ee.Image.pixelArea().sqrt()).rename("distance_to_river").clip(region))
    return {
        "dem": merit.select("elv").rename("elevation").clip(region),
        "slope": ee.Terrain.slope(merit.select("elv")).rename("slope").clip(region),
        "hand": merit.select("hnd").rename("hand").clip(region),
        "upa": merit.select("upa").rename("upa").clip(region),
        "rivers": rivers.selfMask().clip(region),
        "distance_to_river": distance,
    }


def sentinel1_flood_frequency(ee, region, flood_months, dry_months, start_year: int, end_year: int,
                              hand, slope, perm_water, water_db: float = -18, change_db: float = 3,
                              hand_max_m: float = 20):
    """Fraction of flood seasons in which each pixel was observed flooded by Sentinel-1.

    Per year: the 10th-percentile VV backscatter of the flood season (speckle
    filtered) is compared with a multi-year dry-season median. A pixel is flooded
    when it is water-like (VV < ``water_db``), dropped by more than ``change_db``
    from the dry reference, is not permanent water, and lies in flood-prone
    terrain (HAND < ``hand_max_m`` and slope < 5 degrees).
    """
    s1 = (ee.ImageCollection(SENTINEL1).filterBounds(region)
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
          .filterDate(f"{start_year}-01-01", f"{end_year + 1}-01-01").select("VV"))
    dry_reference = s1.filter(month_filter(ee, dry_months)).median().focal_median(50, "circle", "meters")
    flood_filter = month_filter(ee, flood_months)
    prone = hand.lt(hand_max_m).And(slope.lt(5))

    def flood_map(year):
        year = ee.Number(year).int()
        wet = s1.filter(ee.Filter.calendarRange(year, year, "year")).filter(flood_filter)
        low = wet.reduce(ee.Reducer.percentile([10])).rename("VV").focal_median(50, "circle", "meters")
        flooded = (low.lt(water_db).And(low.subtract(dry_reference).lt(-change_db))
                   .And(perm_water.Not()).And(prone)).rename("flood")
        empty = ee.Image.constant(0).rename("flood").updateMask(ee.Image.constant(0))
        return ee.Image(ee.Algorithms.If(wet.size().gt(0), flooded, empty)).set("year", year)

    yearly = ee.ImageCollection(ee.List.sequence(start_year, end_year).map(flood_map))
    frequency = yearly.mean().unmask(0).rename("s1_flood_freq").clip(region)
    latest = ee.Image(yearly.filter(ee.Filter.eq("year", end_year)).first()).clip(region)
    return frequency, latest


def flood_indicators(ee, region, settings: dict, start_year: int, end_year: int,
                     s1_years=(2017, 2025), weights=None, river_upa_km2: float = 100,
                     river_buffer_m: float = 5000, hand_max_m: float = 20, slope_max_deg: float = 10,
                     s1_water_db: float = -18, s1_change_db: float = 3, s1_freq_saturation: float = 0.5,
                     permanent_water_pct: float = 80):
    """Compute all Step 5 flood indicators and the composite flood hazard."""
    weights = weights or DEFAULT_WEIGHTS["flood_hazard"]
    perm = permanent_water(ee, permanent_water_pct)
    rx1day = extreme_rainfall(ee, region, start_year, end_year)
    topo = terrain(ee, region, river_upa_km2)
    s1_freq, s1_latest = sentinel1_flood_frequency(
        ee, region, settings["flood_months"], settings["dry_months"], s1_years[0], s1_years[1],
        topo["hand"], topo["slope"], perm, s1_water_db, s1_change_db, hand_max_m)

    index = {
        "extreme_rainfall": minmax(ee, rx1day, region, 5000, "extreme_rainfall"),
        "observed_flood": s1_freq.divide(s1_freq_saturation).clamp(0, 1).rename("observed_flood"),
        "hand": linear_decay(ee, topo["hand"], hand_max_m, "hand"),
        "slope": linear_decay(ee, topo["slope"], slope_max_deg, "slope"),
        "flow_accumulation": minmax(ee, topo["upa"].max(0.01).log10(), region, 1000, "flow_accumulation"),
        "river_proximity": linear_decay(ee, topo["distance_to_river"], river_buffer_m, "river_proximity"),
        "low_elevation": inverse(ee, minmax(ee, topo["dem"], region, 1000, "x"), "low_elevation"),
    }
    hazard = weighted_overlay(ee, index, weights, "flood_hazard", region)
    return {"index": index, "hazard": hazard, "rx1day": rx1day, "terrain": topo,
            "s1_flood_frequency": s1_freq, "s1_latest": s1_latest, "permanent_water": perm}
