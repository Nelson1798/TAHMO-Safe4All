"""Steps 3-4: climate inputs (CHIRPS, ERA5-Land, MODIS) and drought-hazard indicators.

Every drought indicator is expressed as how often drought conditions occur over
the analysis period (fraction of months or seasons in drought), which is the
long-term propensity a risk map needs. Indicators are then rescaled to 0-1.
"""

from __future__ import annotations

import math

from .config import DEFAULT_WEIGHTS
from .ee_tools import (TIME_PROPS, add_time_props, frequency_below, minmax, month_filter,
                       monthly_composites, standardized_anomalies, vci_collection, weighted_overlay)

CHIRPS_DAILY = "UCSB-CHG/CHIRPS/DAILY"
CHIRPS_PENTAD = "UCSB-CHG/CHIRPS/PENTAD"
ERA5_LAND_MONTHLY = "ECMWF/ERA5_LAND/MONTHLY_AGGR"
MODIS_NDVI = "MODIS/061/MOD13A2"

_GAMMAINC_SHAPE_FIRST = None


def chirps_projection(ee):
    return ee.ImageCollection(CHIRPS_DAILY).first().projection()


def chirps_accumulation(ee, start_year: int, end_year: int, months: int = 1):
    """``months``-long accumulated CHIRPS rainfall ending in each month (mm)."""
    pentads = ee.ImageCollection(CHIRPS_PENTAD).select("precipitation")
    start = ee.Date.fromYMD(start_year, 1, 1)

    def make(offset):
        date = start.advance(offset, "month")
        total = pentads.filterDate(date.advance(-(months - 1), "month"), date.advance(1, "month")).sum()
        return total.rename("precip").set({"system:time_start": date.millis(),
                                           "year": date.get("year"), "month": date.get("month")})

    count = (end_year - start_year + 1) * 12
    return ee.ImageCollection(ee.List.sequence(0, count - 1).map(make))


def _gamma_cdf(ee, x_over_beta, alpha):
    # Earth Engine's gammainc argument order is checked once against a known
    # value (P(a=1, x=2) = 1 - e^-2), so the gamma CDF is always the right way round.
    global _GAMMAINC_SHAPE_FIRST
    if _GAMMAINC_SHAPE_FIRST is None:
        probe = ee.Number(1).gammainc(2).getInfo()
        _GAMMAINC_SHAPE_FIRST = abs(probe - (1 - math.exp(-2))) < 1e-3
    return alpha.gammainc(x_over_beta) if _GAMMAINC_SHAPE_FIRST else x_over_beta.gammainc(alpha)


def spi(ee, accumulation, months: int, baseline_filter, min_years: int = 10, min_mean_mm: float = 5):
    """Standardized Precipitation Index (McKee et al. 1993; WMO 2012).

    For each pixel and calendar month a two-parameter gamma distribution is fitted
    to the baseline totals (Thom's maximum-likelihood approximation), zero-rainfall
    probability q is included, H = q + (1 - q) G(x), and SPI = sqrt(2) erfinv(2H - 1).
    Calendar months with negligible rain (mean < ``min_mean_mm`` x months) or fewer
    than ``min_years`` wet years are masked because SPI is not meaningful there.
    """
    merged = None
    for month in range(1, 13):
        monthly = accumulation.filter(ee.Filter.eq("month", month))
        base = monthly.filter(baseline_filter)
        wet = base.map(lambda img: img.updateMask(img.gt(0)))
        n_all, n_wet = base.count(), wet.count()
        q = ee.Image(1).subtract(n_wet.divide(n_all))
        mean_wet = wet.mean()
        mean_log = wet.map(lambda img: img.log()).mean()
        a = mean_wet.log().subtract(mean_log).max(1e-6)
        alpha = ee.Image(1).add(ee.Image(1).add(a.multiply(4.0 / 3.0)).sqrt()).divide(a.multiply(4))
        beta = mean_wet.divide(alpha)
        valid = n_wet.gte(min_years).And(base.mean().gte(min_mean_mm * months))

        def to_spi(img):
            g = _gamma_cdf(ee, img.divide(beta), alpha)
            h = q.add(ee.Image(1).subtract(q).multiply(g)).clamp(0.00135, 0.99865)  # SPI within +/-3
            z = h.multiply(2).subtract(1).erfInv().multiply(math.sqrt(2))
            return ee.Image(z.updateMask(valid).rename("spi").copyProperties(img, TIME_PROPS))

        result = monthly.map(to_spi)
        merged = result if merged is None else merged.merge(result)
    return merged


def era5_root_zone_soil_moisture(ee, start_year: int, end_year: int):
    """ERA5-Land depth-weighted soil moisture for 0-28 cm (layers 1-2), m3/m3."""
    era5 = (ee.ImageCollection(ERA5_LAND_MONTHLY)
            .filterDate(f"{start_year}-01-01", f"{end_year + 1}-01-01").map(add_time_props))
    soil = era5.map(lambda img: ee.Image(
        img.select("volumetric_soil_water_layer_1").multiply(7)
        .add(img.select("volumetric_soil_water_layer_2").multiply(21)).divide(28)
        .rename("soil_moisture").copyProperties(img, TIME_PROPS)))
    return era5, soil


def modis_ndvi_monthly(ee, start_year: int, end_year: int):
    raw = ee.ImageCollection(MODIS_NDVI).filterDate(f"{start_year}-01-01", f"{end_year + 1}-01-01")
    ndvi = raw.map(lambda img: ee.Image(
        img.select("NDVI").multiply(0.0001).updateMask(img.select("SummaryQA").lte(1))
        .copyProperties(img, ["system:time_start"])))
    return monthly_composites(ee, ndvi, start_year, end_year, "mean"), raw.first().select("NDVI").projection()


def seasonal_rainfall(ee, monthly_precip, rainy_months, season_year_start: int, first_year: int, last_year: int):
    """Rainy-season totals per agricultural year (handles seasons that cross 31 December)."""
    season = monthly_precip.filter(month_filter(ee, rainy_months))
    if season_year_start > 1:
        season = season.map(lambda img: img.set("season_year", ee.Number(img.get("year")).add(
            ee.Number(img.get("month")).gte(season_year_start))))
        first_year += 1
    else:
        season = season.map(lambda img: img.set("season_year", img.get("year")))

    def total(year):
        year = ee.Number(year).int()
        return season.filter(ee.Filter.eq("season_year", year)).sum().rename("season_precip").set("year", year)

    return ee.ImageCollection(ee.List.sequence(first_year, last_year).map(total))


def drought_indicators(ee, region, settings: dict, start_year: int, end_year: int,
                       baseline=(1991, 2020), spi_scales=(1, 3, 6), weights=None,
                       spi_threshold: float = -1.0, spi_min_years: int = 10, spi_min_mean_mm: float = 5,
                       rain_deficit_ratio: float = 0.8, anomaly_z: float = -1.0, vci_threshold: float = 35,
                       snapshot=None):
    """Compute all Step 4 drought indicators and the composite drought hazard.

    Returns a dict with ``frequency`` (raw drought frequencies), ``index`` (0-1
    indicators), ``snapshot`` (current-conditions maps for ``snapshot`` = (year, month)),
    ``hazard`` and the context layers ``annual_rainfall`` and ``soil_moisture_mean``.
    """
    weights = weights or DEFAULT_WEIGHTS["drought_hazard"]
    for k in spi_scales:
        if f"spi{k}" not in weights:
            raise ValueError(f"Add a weight for 'spi{k}' to the drought weights.")
    base_filter = ee.Filter.rangeContains("year", baseline[0], baseline[1])
    chirps_proj = chirps_projection(ee)
    freq, index, snap = {}, {}, {}
    snapshot_date = ee.Date.fromYMD(*(snapshot or (end_year, 9)), 1)

    # Climate context: CHIRPS mean annual rainfall
    monthly = chirps_accumulation(ee, start_year, end_year, 1)
    annual_rainfall = (monthly.filter(base_filter).sum().divide(baseline[1] - baseline[0] + 1)
                       .rename("annual_rainfall").reproject(chirps_proj).clip(region))

    # SPI-1 / SPI-3 / SPI-6
    for k in spi_scales:
        series = spi(ee, chirps_accumulation(ee, start_year, end_year, k), k, base_filter,
                     spi_min_years, spi_min_mean_mm)
        freq[f"spi{k}"] = frequency_below(ee, series, spi_threshold, f"spi{k}_freq", chirps_proj, region)
        index[f"spi{k}"] = minmax(ee, freq[f"spi{k}"], region, 5000, f"spi{k}")
        snap[f"spi{k}"] = ee.Image(series.filterDate(snapshot_date, snapshot_date.advance(1, "month")).first()
                                   ).reproject(chirps_proj).clip(region)

    # Rainfall anomaly: frequency of rainy seasons below x % of normal
    seasons = seasonal_rainfall(ee, monthly, settings["rainy_months"], settings["season_year_start"],
                                start_year, end_year)
    normal = seasons.filter(base_filter).mean()
    freq["rainfall_anomaly"] = (seasons.map(lambda img: img.lt(normal.multiply(rain_deficit_ratio))).mean()
                                .rename("rain_deficit_freq").reproject(chirps_proj).clip(region))
    index["rainfall_anomaly"] = minmax(ee, freq["rainfall_anomaly"], region, 5000, "rainfall_anomaly")
    snap["rainfall_pct_normal"] = (ee.Image(seasons.filter(ee.Filter.eq("year", end_year)).first())
                                   .divide(normal).multiply(100).reproject(chirps_proj).clip(region))

    # NDVI anomaly and VCI (MODIS starts in 2000; baseline starts in 2001 at the earliest)
    ndvi_start = max(start_year, 2001)
    ndvi_monthly, modis_proj = modis_ndvi_monthly(ee, ndvi_start, end_year)
    ndvi_base = ee.Filter.rangeContains("year", max(baseline[0], 2001), baseline[1])
    freq["ndvi_anomaly"] = frequency_below(ee, standardized_anomalies(ee, ndvi_monthly, ndvi_base),
                                           anomaly_z, "ndvi_anom_freq", modis_proj, region)
    index["ndvi_anomaly"] = minmax(ee, freq["ndvi_anomaly"], region, 1000, "ndvi_anomaly")
    vci = vci_collection(ee, ndvi_monthly, ndvi_base)
    freq["vci"] = (vci.map(lambda img: img.lt(vci_threshold)).mean()
                   .rename("vci_freq").reproject(modis_proj).clip(region))
    index["vci"] = minmax(ee, freq["vci"], region, 1000, "vci")
    snap["vci"] = ee.Image(vci.filterDate(snapshot_date, snapshot_date.advance(1, "month")).first()
                           ).reproject(modis_proj).clip(region)

    # Soil-moisture anomaly (ERA5-Land root zone)
    era5, soil = era5_root_zone_soil_moisture(ee, start_year, end_year)
    era5_proj = era5.first().projection()
    freq["soil_moisture"] = frequency_below(ee, standardized_anomalies(ee, soil, base_filter),
                                            anomaly_z, "sm_anom_freq", era5_proj, region)
    index["soil_moisture"] = minmax(ee, freq["soil_moisture"], region, 10000, "soil_moisture")
    soil_mean = soil.filter(base_filter).mean().reproject(era5_proj).clip(region)

    hazard = weighted_overlay(ee, index, weights, "drought_hazard", region)
    return {"frequency": freq, "index": index, "snapshot": snap, "hazard": hazard,
            "annual_rainfall": annual_rainfall, "soil_moisture_mean": soil_mean}
