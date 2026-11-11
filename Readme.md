# Climate Risk Assessment (Floods and Drought)

**SAFE4ALL Climate Risk Assessment Workshop notebook**

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/TAHMO/Safe4All/blob/main/SAFE4ALL_Climate_Risk_Assessment_Workshop.ipynb)

Hands-on Jupyter notebook for **flood and drought risk mapping** in **Kenya**,
**Zimbabwe**, and **Ghana** (default: Ghana, whole country). It follows a
hazard x exposure x vulnerability workflow in Google Earth Engine and produces
classified risk maps and district risk statistics, with TAHMO station
observations for ground validation and TAMSAT for drought context.

## Run it — pick one

**Google Colab (default, no local setup):** click the badge above, or open
<https://colab.research.google.com/github/TAHMO/Safe4All/blob/main/SAFE4ALL_Climate_Risk_Assessment_Workshop.ipynb>,
then **Runtime -> Run all**. Section 0 of the notebook clones this repo into
the Colab runtime and installs anything missing — nothing else to configure.

**Local Jupyter or Anaconda:** clone this repo and run the notebook from its
root folder with **Run -> Run All Cells**. Section 0 detects that the
`safe4all` package is already available locally and skips the Colab-only
steps; any missing Python packages are installed automatically. A conda
environment file is provided if you prefer to pre-install everything instead:

```bash
git clone https://github.com/TAHMO/Safe4All.git
cd Safe4All
conda env create -f environment.yml
conda activate safe4all-climate-risk
python -m ipykernel install --user --name safe4all-climate-risk --display-name "Python (SAFE4ALL)"
jupyter lab
```

Open `SAFE4ALL_Climate_Risk_Assessment_Workshop.ipynb` and select the
**Python (SAFE4ALL)** kernel. All three environments (Colab, Jupyter,
Anaconda) run the same notebook and produce the same screening outputs.

To verify a local installation outside the notebook, run:

```bash
python -m unittest tests/test_project.py
```

## Workshop flow

Run `SAFE4ALL_Climate_Risk_Assessment_Workshop.ipynb` from top to bottom. It
follows ten steps, and each one has its own module in the `safe4all` package:

| Step | What it does | Module |
|---|---|---|
| 1-2 | Select country / region / district / river basin; load GAUL boundaries | `aoi.py` |
| 3 | Climate: CHIRPS, ERA5-Land, TAHMO QC and validation (optional), TAMSAT (optional) | `drought.py`, `tahmo.py`, `qc.py`, `validation.py` |
| 4 | Drought hazard: SPI-1/3/6, rainfall anomaly, NDVI anomaly, VCI, soil-moisture anomaly | `drought.py` |
| 5 | Flood hazard: extreme rainfall, Sentinel-1 flood frequency, DEM, slope, HAND, flow accumulation, distance from river | `flood.py` |
| 6 | Exposure: WorldPop, cropland, settlements, infrastructure | `exposure.py` |
| 7 | Vulnerability: socioeconomic indicators, land use, agricultural dependence | `vulnerability.py` |
| 8 | Risk = Hazard x Exposure x Vulnerability (flood, drought, multi-hazard) | `model.py` |
| 9 | Classify: Very Low, Low, Moderate, High, Very High | `model.py` |
| 10 | Export: GeoTIFF, CSV, Shapefile, interactive HTML maps, district statistics, PNG figures | `export.py` |

Study area, periods, weights, and classification method are set in Section 1
of the notebook. Per-country flood/dry/rainy-season months, default weights,
and land-use susceptibility scores are in `safe4all/config.py`.

## Outputs

- **Google Drive** (`SAFE4ALL_Flood_Drought_Risk`): GeoTIFFs of hazard,
  exposure, vulnerability, risk index and risk class for flood, drought and
  multi-hazard, plus the district statistics as CSV and Shapefile.
- **Workshop cache** (`outputs/<study area>/`): district risk statistics CSV,
  zipped shapefile, interactive district map (self-contained HTML), interactive
  raster map (HTML), area and population per risk class, district ranking
  chart and static risk maps (PNG), and one zip of everything.

## Data strategy

- **TAHMO stations:** local observations, station QC, and product validation.
- **TAMSAT:** primary Africa-focused rainfall and soil-moisture source for
  drought monitoring and long-term risk context.
- **CHIRPS:** independent long-term rainfall comparator available in Earth
  Engine.
- **IMERG:** half-hourly event-rainfall context for flood case studies.

The project caches every approved live extract. In Colab, set
`SAFE4ALL_SHARED_DRIVE` in the notebook to the exact Shared Drive name before
starting; the default is `SAFE4ALL-workshop`. If it cannot be found, the
notebook falls back to a workshop folder in the participant's MyDrive. Local
Jupyter/Anaconda use `.safe4all-cache/` inside the project folder.

## Google Earth Engine access

Earth Engine requires every request to be attached to a Google Cloud project.
You do **not** need your own project for the workshop: by default the notebook
signs in with the shared SAFE4ALL / TAHMO workshop **service account**, the same
account the other TAHMO/NOAA workshop notebooks use. This avoids the
`PERMISSION_DENIED` / "Caller does not have required permission to use project"
error that appears when each participant authenticates with a personal Google
account that has no access to the workshop project.

`EE_AUTH` in Section 1 selects the mode:

- **`'shared'` (default):** the shared workshop service account is used. Its key
  is downloaded at run time from Google Drive (via `gdown`), so **no credential
  is stored in this repository**. Nothing else to configure — just Run all.
- **`'personal'`:** sign in with your own Google account. Set `EE_PROJECT` to a
  Cloud project where you have enabled the Earth Engine API (free to create at
  <https://console.cloud.google.com/>); the notebook then uses the normal
  `ee.Authenticate()` prompt.

Advanced override: set `EE_SERVICE_ACCOUNT_KEY` (or the standard
`GOOGLE_APPLICATION_CREDENTIALS`) to the local path of your own service-account
JSON key. **Never commit a key file to this repository** — keep it outside the
project folder, or inside `.safe4all-cache/` (already git-ignored). If the shared
key is ever misused, rotate it in
[IAM & Admin -> Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
and update the Drive key file; only `safe4all/gee.py` references it.

TAHMO API credentials are still requested privately at run time with `getpass`
and kept only in the current session's memory.

## Interpretation note

The flood and drought maps are **screening-level risk products**, not
operational forecasts or disaster warnings. Indices are relative to the
selected study area. Calibrate weights and thresholds with local experts and
validate the classes against observed flood extents, disaster records, and
drought impacts before using them for decisions.
