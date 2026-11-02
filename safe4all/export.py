"""Step 10: exports - GeoTIFF, CSV, Shapefile, interactive HTML maps and district risk statistics."""

from __future__ import annotations

import io
import math
import os
import zipfile
from pathlib import Path

from .config import BASEMAP_ATTRIBUTION, BASEMAP_URL, CLASS_COLORS, CLASS_LABELS
from .model import assign_classes, rank_descending

# Short shapefile field (<= 10 characters) -> descriptive CSV column.
FIELD_DESCRIPTIONS = {
    "ADM0_NAME": "country", "ADM1_NAME": "region", "ADM2_NAME": "district", "ADM2_CODE": "district_code",
    "area_km2": "area_km2", "pop_total": "population",
    "fl_haz": "flood_hazard_mean", "fl_exp": "flood_exposure_mean", "fl_vul": "flood_vulnerability_mean",
    "fl_risk": "flood_risk_index", "fl_class": "flood_risk_class", "fl_rank": "flood_risk_rank",
    "fl_hi_pct": "flood_high_veryhigh_area_pct", "pop_fl_hi": "flood_high_veryhigh_population",
    "dr_haz": "drought_hazard_mean", "dr_exp": "drought_exposure_mean", "dr_vul": "drought_vulnerability_mean",
    "dr_risk": "drought_risk_index", "dr_class": "drought_risk_class", "dr_rank": "drought_risk_rank",
    "dr_hi_pct": "drought_high_veryhigh_area_pct", "pop_dr_hi": "drought_high_veryhigh_population",
    "mh_risk": "multi_hazard_risk_index", "mh_class": "multi_hazard_risk_class", "mh_rank": "multi_hazard_risk_rank",
}


def polygon_parts(geometry):
    """Return only the polygonal parts of a geometry as a MultiPolygon (None if there are none).

    Some GAUL 2015 districts come back from Earth Engine as GeometryCollections
    or with line slivers after simplification; a polygon shapefile rejects them.
    """
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.validation import make_valid

    if geometry is None or geometry.is_empty:
        return None
    geometry = make_valid(geometry)
    if isinstance(geometry, Polygon):
        return MultiPolygon([geometry])
    if isinstance(geometry, MultiPolygon):
        return geometry
    parts = []
    for part in getattr(geometry, "geoms", []):
        cleaned = polygon_parts(part)
        if cleaned is not None:
            parts.extend(cleaned.geoms)
    return MultiPolygon(parts) if parts else None


def finalise_district_table(gdf, method: str = "equal"):
    """Add High/Very High %, district classes and ranks; return (gdf, descriptive table)."""
    import pandas as pd

    gdf = gdf.copy()
    gdf["geometry"] = gdf.geometry.apply(polygon_parts)
    gdf = gdf.set_geometry("geometry")
    missing = gdf.geometry.isna()
    if missing.any():
        print(f"{missing.sum()} district(s) without polygon geometry (kept in the CSV, left out of maps): "
              f"{gdf.loc[missing, 'ADM2_NAME'].tolist()}")
    for column in ["pop_total", "pop_fl_hi", "pop_dr_hi", "fl_hi_frac", "dr_hi_frac"]:
        gdf[column] = gdf[column].fillna(0) if column in gdf else 0.0
    gdf["fl_hi_pct"] = 100 * gdf["fl_hi_frac"]
    gdf["dr_hi_pct"] = 100 * gdf["dr_hi_frac"]
    for prefix in ("fl", "dr", "mh"):
        values = gdf[f"{prefix}_risk"].tolist()
        gdf[f"{prefix}_class"] = assign_classes(values, method)
        gdf[f"{prefix}_rank"] = pd.array(rank_descending(values), dtype="Int64")

    table = pd.DataFrame(gdf.drop(columns="geometry"))[list(FIELD_DESCRIPTIONS)].rename(columns=FIELD_DESCRIPTIONS)
    table = table.sort_values("multi_hazard_risk_rank")
    for column in table.columns:
        if column.endswith(("_mean", "_index")):
            table[column] = table[column].round(3)
        elif column.endswith("_pct") or column == "area_km2":
            table[column] = table[column].round(1)
        elif column == "population" or column.endswith("_population"):
            table[column] = table[column].round(0).astype(int)
    return gdf, table


def save_shapefile(gdf, out_dir: Path, prefix: str) -> Path:
    """Write the district polygons with statistics as a zipped shapefile plus a field dictionary."""
    import pandas as pd

    shp_dir = Path(out_dir) / f"{prefix}_district_risk_shp"
    shp_dir.mkdir(parents=True, exist_ok=True)
    fields = [f for f in FIELD_DESCRIPTIONS if f != "ADM0_NAME"]
    shp = gdf.loc[gdf.geometry.notna(), fields + ["geometry"]].copy()
    for column in ("fl_rank", "dr_rank", "mh_rank"):
        shp[column] = shp[column].astype(float)
    shp.to_file(shp_dir / f"{prefix}_district_risk.shp")
    pd.DataFrame({"field": fields, "description": [FIELD_DESCRIPTIONS[f] for f in fields]}).to_csv(
        shp_dir / "field_dictionary.csv", index=False)
    zip_path = Path(out_dir) / f"{prefix}_district_risk_shapefile.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in shp_dir.iterdir():
            archive.write(file, arcname=file.name)
    return zip_path


def save_district_html(gdf, path: Path) -> Path:
    """Self-contained interactive district map (flood / drought / multi-hazard layers, pop-ups)."""
    import folium

    fields = ["ADM1_NAME", "ADM2_NAME", "pop_total", "fl_risk", "fl_class", "pop_fl_hi",
              "dr_risk", "dr_class", "pop_dr_hi", "mh_risk", "mh_class"]
    aliases = ["Region", "District", "Population", "Flood risk index", "Flood risk class",
               "Pop. in high flood risk", "Drought risk index", "Drought risk class",
               "Pop. in high drought risk", "Multi-hazard index", "Multi-hazard class"]
    data = gdf[gdf.geometry.notna()].copy()
    for column in ("fl_risk", "dr_risk", "mh_risk"):
        data[column] = data[column].round(3)
    for column in ("pop_total", "pop_fl_hi", "pop_dr_hi"):
        data[column] = data[column].round(0).astype(int)
    fmap = None
    for i, (column, name) in enumerate([("fl_class", "Flood risk"), ("dr_class", "Drought risk"),
                                        ("mh_class", "Multi-hazard risk")]):
        fmap = data.explore(m=fmap, column=column, categorical=True, categories=CLASS_LABELS,
                            cmap=["#" + c for c in CLASS_COLORS], name=name, show=(i == 0),
                            legend=(i == 0), legend_kwds={"caption": "Risk class"},
                            tooltip=fields, tooltip_kwds={"aliases": aliases}, popup=fields,
                            style_kwds={"color": "#444444", "weight": 0.6, "fillOpacity": 0.75},
                            tiles=BASEMAP_URL, attr=BASEMAP_ATTRIBUTION)
    folium.LayerControl(collapsed=False).add_to(fmap)
    fmap.save(str(path))
    return Path(path)


def save_ranking_chart(table, path: Path, top_n: int = 15) -> Path:
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    colours = {label: "#" + c for label, c in zip(CLASS_LABELS, CLASS_COLORS)}
    top_n = min(top_n, len(table))
    fig, axes = plt.subplots(1, 2, figsize=(14, 0.42 * top_n + 1.8))
    for ax, (index, cls, title) in zip(axes, [("flood_risk_index", "flood_risk_class", "Flood risk"),
                                             ("drought_risk_index", "drought_risk_class", "Drought risk")]):
        top = table.nlargest(top_n, index).iloc[::-1]
        ax.barh(top["district"], top[index], color=[colours.get(c, "#999999") for c in top[cls]],
                edgecolor="#555555", lw=0.4)
        ax.set_xlim(0, 1)
        ax.set_xlabel("Mean risk index (0-1)")
        ax.set_title(f"Top {top_n} districts - {title}", loc="left", fontweight="bold")
        ax.spines[["top", "right"]].set_visible(False)
    fig.legend(handles=[Patch(color=colours[l], label=l) for l in CLASS_LABELS],
               loc="lower center", ncol=5, frameon=False)
    plt.tight_layout(rect=[0, 0.05, 1, 1])
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.show()
    return Path(path)


def save_static_maps(ee, panels: list, districts, study_fc, study_area, gdf, out_dir: Path,
                     prefix: str, title: str) -> list[Path]:
    """PNG map panel of pixel classes (hazard and risk) and PNG district class maps for reports."""
    import matplotlib.pyplot as plt
    import pandas as pd
    import requests
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    from PIL import Image

    handles = [Patch(facecolor="#" + c, edgecolor="#555555", label=l) for l, c in zip(CLASS_LABELS, CLASS_COLORS)]
    bounds = study_area.bounds(1000)
    corners = bounds.coordinates().getInfo()[0]
    xs, ys = [p[0] for p in corners], [p[1] for p in corners]
    extent = [min(xs), max(xs), min(ys), max(ys)]
    outline = (ee.Image().byte().paint(districts, 1, 1).visualize(palette=["555555"])
               .blend(ee.Image().byte().paint(study_fc, 1, 2).visualize(palette=["000000"])))

    def thumbnail(class_image):
        # A country-wide class map is computed in one synchronous request, which can
        # exceed Earth Engine's time/memory limits; retry smaller and report EE's message.
        vis = class_image.visualize(min=1, max=5, palette=CLASS_COLORS).blend(outline)
        error = ""
        for dimensions in (1200, 800, 512):
            try:
                url = vis.getThumbURL({"region": bounds, "dimensions": dimensions, "format": "png", "crs": "EPSG:4326"})
                response = requests.get(url, timeout=600)
            except Exception as exc:
                error = str(exc)
                continue
            if response.ok and response.headers.get("Content-Type", "").startswith("image"):
                return Image.open(io.BytesIO(response.content))
            error = response.text[:300]
        raise RuntimeError(error or "no image returned")

    aspect = (extent[3] - extent[2]) / (extent[1] - extent[0])
    rows = math.ceil(len(panels) / 2)
    fig, axes = plt.subplots(rows, 2, figsize=(12, 6 * rows * aspect + 1.5), squeeze=False)
    for ax, (image, label) in zip(axes.ravel(), panels):
        try:
            ax.imshow(thumbnail(image), extent=extent)
            ax.tick_params(labelsize=8)
        except Exception as exc:
            print(f"{label}: Earth Engine could not render the static map ({str(exc)[:200]}). "
                  "Use the interactive map or the GeoTIFF export for this layer.")
            ax.text(0.5, 0.5, "Not rendered\n(see GeoTIFF export)", ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
        ax.set_title(label, fontweight="bold")
    for ax in axes.ravel()[len(panels):]:
        ax.set_axis_off()
    fig.legend(handles=handles, loc="lower center", ncol=5, frameon=False)
    fig.suptitle(title, fontsize=14, fontweight="bold")
    plt.tight_layout(rect=[0, 0.04, 1, 0.97])
    panel_path = Path(out_dir) / f"{prefix}_risk_map_panel.png"
    plt.savefig(panel_path, dpi=200, bbox_inches="tight")
    plt.show()

    fig, axes = plt.subplots(1, 3, figsize=(18, 7))
    for ax, (column, label) in zip(axes, [("fl_class", "Flood risk"), ("dr_class", "Drought risk"),
                                          ("mh_class", "Multi-hazard risk")]):
        gdf.assign(_c=pd.Categorical(gdf[column], categories=CLASS_LABELS)).plot(
            column="_c", categorical=True, cmap=ListedColormap(["#" + c for c in CLASS_COLORS]),
            edgecolor="white", linewidth=0.3, ax=ax, missing_kwds={"color": "lightgrey"})
        ax.set_title(f"{label} by district", fontweight="bold")
        ax.set_axis_off()
    fig.legend(handles=handles, loc="lower center", ncol=5, frameon=False)
    plt.tight_layout(rect=[0, 0.06, 1, 1])
    district_path = Path(out_dir) / f"{prefix}_district_risk_maps.png"
    plt.savefig(district_path, dpi=200, bbox_inches="tight")
    plt.show()
    return [panel_path, district_path]


def export_geotiffs(ee, rasters: dict, prefix: str, folder: str, region, scale: int = 1000) -> list:
    """Start Earth Engine GeoTIFF exports to Google Drive (indices Float32, classes Byte)."""
    tasks = []
    for name, image in rasters.items():
        image = image.toByte() if name.endswith("_class") else image.toFloat()
        task = ee.batch.Export.image.toDrive(
            image=image, description=f"{prefix}_{name}"[:100], folder=folder,
            fileNamePrefix=f"{prefix}_{name}", region=region, scale=scale, crs="EPSG:4326",
            maxPixels=1e13, fileFormat="GeoTIFF")
        task.start()
        tasks.append(task)
        print("Started GeoTIFF export:", name)
    return tasks


def export_tables(ee, collection, prefix: str, folder: str, formats=("CSV", "SHP")) -> list:
    tasks = []
    for fmt in formats:
        task = ee.batch.Export.table.toDrive(collection=collection, description=f"{prefix}_district_stats_{fmt}"[:100],
                                             folder=folder, fileNamePrefix=f"{prefix}_district_risk_stats",
                                             fileFormat=fmt)
        task.start()
        tasks.append(task)
        print("Started table export:", fmt)
    return tasks


def zip_outputs(out_dir: Path, zip_path: Path) -> Path:
    out_dir = Path(out_dir)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, _, files in os.walk(out_dir):
            for file in files:
                full = Path(root) / file
                if full.resolve() != Path(zip_path).resolve():
                    archive.write(full, arcname=full.relative_to(out_dir))
    return Path(zip_path)
