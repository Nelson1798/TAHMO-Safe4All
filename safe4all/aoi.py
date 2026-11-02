"""Steps 1-2: select the study area (country / region / district / basin) and its districts."""

from __future__ import annotations

from .config import AOI_MODES, country_settings

GAUL = "FAO/GAUL/2015/level{}"
DISTRICT_FIELDS = ["ADM0_NAME", "ADM1_NAME", "ADM2_NAME", "ADM2_CODE", "area_km2"]


def aoi_label(country: str, mode: str = "country", admin1: str | None = None,
              admin2: str | None = None, basin_point=None, basin_level: int = 5) -> str:
    """Return a file-name-safe label for the selected study area."""
    if mode not in AOI_MODES:
        raise ValueError(f"AOI mode must be one of {AOI_MODES}, not {mode!r}.")
    if mode == "admin1":
        if not admin1:
            raise ValueError("Set ADMIN1_NAME when AOI_MODE = 'admin1'.")
        raw = f"{country}_{admin1}"
    elif mode == "district":
        if not admin2:
            raise ValueError("Set ADMIN2_NAME when AOI_MODE = 'district'.")
        raw = f"{country}_{admin2}"
    elif mode == "basin":
        if not basin_point:
            raise ValueError("Set BASIN_POINT = (lon, lat) when AOI_MODE = 'basin'.")
        raw = f"{country}_basin_L{basin_level}_{basin_point[0]}_{basin_point[1]}"
    else:
        raw = country
    return "".join(c if c.isalnum() else "_" for c in raw)


def admin_names(ee, country: str, level: int, admin1: str | None = None) -> list[str]:
    """List GAUL names at level 1 (regions) or 2 (districts) for a country."""
    fc = ee.FeatureCollection(GAUL.format(level)).filter(ee.Filter.eq("ADM0_NAME", country))
    if admin1 and level == 2:
        fc = fc.filter(ee.Filter.eq("ADM1_NAME", admin1))
    return fc.aggregate_array(f"ADM{level}_NAME").distinct().sort().getInfo()


def select_aoi(ee, country: str, mode: str = "country", admin1: str | None = None,
               admin2: str | None = None, basin_point=None, basin_level: int = 5) -> dict:
    """Return the study area, its districts and display settings.

    ``mode`` is one of ``country``, ``admin1`` (region/province), ``district``,
    or ``basin`` (the HydroBASINS sub-basin containing ``basin_point``; districts
    of every country the basin crosses are included).
    """
    settings = country_settings(country)
    label = aoi_label(country, mode, admin1, admin2, basin_point, basin_level)
    gaul1 = ee.FeatureCollection(GAUL.format(1)).filter(ee.Filter.eq("ADM0_NAME", country))
    gaul2 = ee.FeatureCollection(GAUL.format(2))
    country_districts = gaul2.filter(ee.Filter.eq("ADM0_NAME", country))

    if mode == "country":
        study_fc = ee.FeatureCollection(GAUL.format(0)).filter(ee.Filter.eq("ADM0_NAME", country))
        districts = country_districts
    elif mode == "admin1":
        study_fc = gaul1.filter(ee.Filter.eq("ADM1_NAME", admin1))
        districts = country_districts.filter(ee.Filter.eq("ADM1_NAME", admin1))
    elif mode == "district":
        study_fc = country_districts.filter(ee.Filter.eq("ADM2_NAME", admin2))
        if admin1:
            study_fc = study_fc.filter(ee.Filter.eq("ADM1_NAME", admin1))
        districts = study_fc
    else:
        study_fc = ee.FeatureCollection(f"WWF/HydroSHEDS/v1/Basins/hybas_{basin_level}").filterBounds(
            ee.Geometry.Point(list(basin_point)))
        basin = study_fc.geometry()
        districts = gaul2.filterBounds(basin).map(lambda f: f.intersection(basin, ee.ErrorMargin(100)))

    if study_fc.size().getInfo() == 0:
        hint = ""
        if mode == "admin1":
            hint = f" Valid regions: {admin_names(ee, country, 1)}"
        elif mode == "district":
            hint = f" Valid districts: {admin_names(ee, country, 2, admin1)}"
        raise ValueError(f"No study area found for mode={mode!r}.{hint}")

    districts = (districts
                 .map(lambda f: f.set("area_km2", f.geometry().area(100).divide(1e6)))
                 .select(DISTRICT_FIELDS))
    zoom = {"country": settings["zoom"], "admin1": 8, "district": 10, "basin": 7}[mode]
    return {"study_fc": study_fc, "study_area": study_fc.geometry(), "districts": districts,
            "label": label, "zoom": zoom}
