"""Reusable Earth Engine rainfall indicators for SAFE4ALL exercises."""

from __future__ import annotations


def chirps_daily(ee, start_date: str, end_date: str, region):
    """Load and clip daily CHIRPS precipitation (mm/day)."""
    return (
        ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
        .filterDate(start_date, end_date)
        .filterBounds(region)
        .select("precipitation")
    )


def imerg_half_hourly(ee, start_date: str, end_date: str, region):
    """Load IMERG Final half-hourly rainfall and convert rate to mm per step."""
    return (
        ee.ImageCollection("NASA/GPM_L3/IMERG_V07")
        .filterDate(start_date, end_date)
        .filterBounds(region)
        # V07 renamed the calibrated rain-rate band from "precipitationCal"
        # (V06) to "precipitation".
        .select("precipitation")
        .map(lambda image: image.multiply(0.5).copyProperties(image, ["system:time_start"]))
    )


def imerg_event_rainfall(ee, start_date: str, end_date: str, region):
    """Accumulate IMERG half-hourly rainfall for an event period."""
    return imerg_half_hourly(ee, start_date, end_date, region).sum().rename("imerg_event_rainfall_mm")


def extreme_rainfall_days(ee, start_date: str, end_date: str, region, threshold_mm: float = 50):
    """Count days meeting an extreme daily-rainfall threshold."""
    return chirps_daily(ee, start_date, end_date, region).map(
        lambda image: image.gte(threshold_mm)
    ).sum().rename("extreme_rain_days")


def monthly_rainfall(ee, start_date: str, end_date: str, region):
    """Return total rainfall per calendar month for a date range."""
    start = ee.Date(start_date).advance(0, "month")
    months = ee.Date(end_date).difference(start, "month").toInt()

    def make_month(offset):
        month_start = start.advance(offset, "month")
        month_end = month_start.advance(1, "month")
        return chirps_daily(ee, month_start, month_end, region).sum().set(
            {"system:time_start": month_start.millis(), "month": month_start.format("YYYY-MM")}
        )

    return ee.ImageCollection.fromImages(ee.List.sequence(0, months.subtract(1)).map(make_month))
