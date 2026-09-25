# GeoStat User Guide

GeoStat is a spatial statistics desktop app for macOS and Windows. It covers what GeoDa does — exploratory spatial data
analysis (ESDA), spatial regression and spatial clustering — and adds GWR/MGWR, Korean coordinate systems and
encodings, raster zonal statistics, point aggregation, rate smoothing (EB) and space-time analysis. This guide describes version 0.10. A more detailed Korean guide is in
[manual.md](manual.md).

> Error messages and text reports produced by the analysis engine are currently in Korean only.

## 1. Install

**macOS** — macOS 14 (Sonoma) or later on Apple Silicon (M1 or newer):

1. Download `GeoStat_<version>_aarch64.dmg` from [Releases](https://github.com/SeaViewer91/GeoStat/releases).
2. Open the dmg and drag `GeoStat.app` into Applications.
3. The app is not notarized by Apple, so the first launch shows an "unidentified developer" warning. Allow it once:
   - **System Settings → Privacy & Security → Open Anyway**, or
   - Terminal: `xattr -dr com.apple.quarantine /Applications/GeoStat.app`

**Windows** — Windows 10 or 11, 64-bit: download and run `GeoStat_<version>_x64-setup.exe`. It installs for the
current user without admin rights. The installer is not code-signed, so SmartScreen may show "Windows protected
your PC" — click **More info → Run anyway**. On Windows, read ⌘ in this guide as **Ctrl** (⇧⌘S → Ctrl+Shift+S).

The first launch can take 10–20 seconds while the analysis engine starts. When the status bar shows
`Engine <version> · GDAL …`, it is ready. New versions are announced in the top-right corner; **Install and restart**
downloads, verifies the signature and installs them. Switch the interface language under **Help → 한국어 / English**.

## 2. Window layout

| Area | Contents |
|---|---|
| Toolbar | File · Spatial analysis · Help menus, chart panel, selection tools (pan, box, lasso), invert/clear selection, basemap |
| Left panel | Layers, rasters and their display settings, map classification and legend, spatial weights |
| Center | Map, with the attribute table below (drag the divider; ⌘T toggles it) |
| Right panel | Charts and analysis reports (⌘J) |
| Status bar | Feature and selection counts, progress and **Cancel** for running jobs, engine version |

Drag the borders between the side panels and the map to resize the panels; double-click a border to reset it. Widths are remembered.

The layer you click in the layer list is the *active layer*; classification, the attribute table and analysis
menus apply to it.

## 3. Opening data

**File → Open data…** (⌘O)

- Vector: Shapefile, GeoPackage (a layer picker appears if there are several), GeoJSON, FlatGeobuf, KML, GML
- Tables: CSV/TSV/TXT and Excel — choose the X/Y columns and the coordinate system to create points
- Raster: GeoTIFF/COG, IMG, VRT, ASCII Grid, JPEG2000

Shapefile attribute encoding (cp949/EUC-KR or UTF-8) is detected automatically, with or without a `.cpg` file.
Layers without a coordinate system cannot be drawn, so a CRS dialog appears with Korean presets (EPSG:5186,
5179, 5174, …); only the CRS definition is attached, coordinates are not changed.

## 4. Choropleth maps

Pick a variable and a method under **Thematic map** and click **Apply**: quantile, equal interval, natural breaks (Jenks),
standard deviation, percentile, box map (1.5 IQR), zero-centered diverging (for GWR coefficients and residuals),
unique values, and cluster/significance maps for local statistics. Click a legend entry to select its features
(⌘-click adds). For GWR coefficient columns, **Hide non-significant areas** greys out locations that are not
significant after multiple-testing correction.

For a column in a time variable group (or a LISA-per-period result), a **Period** row appears: step with ◀ ▶ or press
**Play**. **Same class breaks for all periods** pools all periods so colors can be compared between periods.

## 5. Attribute table and selection

- Click a column header to sort; click a row to select it. Map, table, legend and charts share one selection.
- Selection tools: pan/click, **box** (B or Shift-drag), **lasso** (L; selects features whose centroid is inside). Hold ⌘ to add.
- **Select by attribute…** uses pandas expressions; wrap non-ASCII or spaced column names in backticks:
  `` `population` > 5000 and `type` == 'urban' ``
- **Add calculated field…** creates a variable from an expression; it is recomputed when a project is reopened.
- **Export…** writes GeoPackage, Shapefile (choose cp949 or UTF-8), GeoJSON, FlatGeobuf or CSV, optionally reprojected.

## 6. Spatial weights

**Spatial analysis → Create spatial weights…**: queen/rook contiguity (higher orders), distance band (suggests
the minimum distance that gives every feature a neighbor; inverse distance optional), k-nearest neighbors, kernel
weights, and GeoDa `.gal`/`.gwt` files (load and save). Geographic coordinates are projected to UTM for
distances. The panel shows a connectivity histogram and the number of isolates.

## 7. ESDA

- **Moran's I · Moran scatter plot** with permutation inference: univariate, bivariate, **differential** (variable −
  base variable, change between two periods) and **EB rate** (numerator ÷ denominator standardized with the
  Assunção–Reis method, like GeoDa's EB Moran). Brushing the scatter plot selects on the map.
- **Local statistics**: LISA, Getis-Ord Gi*, Local Geary, with FDR or Bonferroni correction and a fixed random
  seed. Results are saved as columns (statistic, `_CL` cluster code, `_P` p-value) and a cluster map is drawn.
- **EB rate LISA**: LISA on an EB-standardized rate (numerator and denominator).
- **Join count** for binary variables.
- **Charts**: histogram, scatter plot, box plot, Moran scatter plot — all linked to the map.

## 8. Regression

**Spatial analysis → Regression (…)…** runs as a background job with progress and cancel.

| Model | Notes |
|---|---|
| OLS | With weights: residual Moran's I and LM diagnostics (LM/robust LM lag and error, SARMA) plus a model-choice hint. Optional White robust standard errors |
| Spatial lag (ML, GM) | Includes a direct / indirect / total effects table |
| Spatial error (ML, GM) | GM estimation is heteroskedasticity-robust |
| GWR | Bisquare/Gaussian/exponential kernels, fixed or adaptive bandwidth chosen by AICc/AIC/BIC/CV |
| MGWR | One bandwidth per variable; slow — about 5,000 observations or fewer recommended |

Predictions (`_PRED`) and residuals (`_RESID`) are saved as columns; GWR/MGWR also save local coefficients
(`_B_`), t-values (`_T_`), significance flags (`_SIG_`) and local R². When two or more models have been fitted, a
**Model comparison** table lists R², log likelihood, AICc (computed like mgwr, counting σ²; MGWR on the original
scale) and residual Moran's I, and marks the lowest AICc among models with the same dependent variable.

## 9. Clustering

**Spatial analysis → Clustering (…)…**: SKATER, Max-p (minimum total per region, e.g. population), AZP, Region
K-Means and spatially constrained Ward, plus non-spatial K-means and hierarchical clustering for comparison. The
result is a `<prefix>_GRP` column (1 = largest cluster), a cluster map, and a report with the between/total sum
of squares ratio, per-cluster means (shaded red above / blue below the overall mean) and the number of spatial
fragments per cluster. AZP, Max-p and Region K-Means need a connected neighbor graph — use KNN weights if there are islands.

## 10. Point aggregation and rate maps

**Spatial analysis → Aggregate points…** collects a point layer (survey sites, detections) into each polygon of the
active polygon layer (grid or administrative areas): count (`<prefix>_CNT`), density per km² (`_DENS`) and sum,
mean, min, max, median or standard deviation of point attributes (`_SUM_<column>` …). Coordinate systems are matched
automatically, non-point layers are counted by representative point, and points on a shared boundary are counted
once. Polygons without points get 0 for count and sum.

**Spatial analysis → Rate maps · EB smoothing…** builds rates from a numerator (events, catch) and a denominator
(population, effort), as in GeoDa's Rates menu: raw rate, excess risk (observed ÷ expected, drawn as a box map),
empirical Bayes smoothing, spatial rate and spatial EB smoothing (the last two need spatial weights). A multiplier
(per 1,000 …) can be applied. Use **EB rate** in the Moran scatter plot or local statistics for the spatial
autocorrelation of a rate.

## 11. Space-time analysis

Everything works on **time variable groups** — the per-period columns of one variable.

| Data layout | Example | How |
|---|---|---|
| Wide | `catch_2022`, `catch_2023` … columns | **Space-time → Time variable groups… → Detect from column names** (or add manually) |
| Long | (site, year, catch) rows repeated every year | **Space-time → Create per-period data… → Long format**: pick ID, period and value columns |
| Per-period files | `2022.shp`, `2023.shp` … | Open them all, then **Create per-period data… → Join per-period files**: ID column and period name per file |

Converted data is saved as a GeoPackage, opened as a new layer and gets a time variable group per value. Groups are
saved with the project.

**Space-time → Space-time analysis…** offers:

1. **Global Moran's I over time** — line chart and table per period (filled dots: p ≤ 0.05).
2. **LISA per period and cluster transitions** — saves `TLISA_<period>_CL` and the number of changes (`TLISA_CHG`);
   the results panel shows cluster counts per period and a transition table (earlier → next period). Click a period
   to map it.
3. **Differential LISA** — LISA of the change between two periods (later − earlier), like GeoDa's differential Moran.

## 12. Rasters

- Display settings in the **Raster** panel: band, colormap, value range (2–98 %, min–max, manual), opacity, RGB composite.
- **Build overviews** creates an external `.ovr` next to large rasters so zoomed-out views are fast (the original file is untouched).
- **Zonal statistics**: mean, min, max, standard deviation, sum, median, quartiles, count, majority and variety per polygon, weighted by cell coverage.
- **Create grid (square/hexagon)**: square or hexagonal grid over a raster or layer extent, saved as GeoPackage; optionally run zonal statistics right away and continue with LISA on the grid.

## 13. Projects and export

**File → Save project** (⌘S) writes a `.gstproj` file with source paths (relative and absolute) and every step
(CRS assignment, computed fields, weights, analyses, map styles, charts, raster settings). Regression, clustering,
zonal and point-aggregation results are cached in a `.gstcache` folder next to the project so they are not recomputed.
**File → Save map image (PNG)…** saves the current map with legend and attribution.

**File → Export analysis report (Word · HTML)…** collects data information, calculated fields, spatial weights, time
variable groups, the result tables of the analyses you ran and the current map into one .docx or .html document.
Tables and text generated by the engine are in Korean.

## 14. Try it with the sample data

**Help → Sample: …** copies a sample into `Documents/GeoStat/샘플 데이터` and opens it.

- **Georgia education (GWR)**: OLS and then GWR of `PctBach ~ PctRural + PctFB + PctBlack`. The adaptive
  bisquare bandwidth is 117 neighbors, matching the mgwr documentation.
- **North Carolina SIDS (ESDA)**: queen weights, Moran's I and LISA of `SIDR79`.
- **Seoul synthetic terrain (raster)**: create a 500 m grid over the raster with zonal statistics, then run LISA on `ZS_MEAN`.

## 15. Shortcuts

| Action | Keys |
|---|---|
| Open data / open project | ⌘O / ⇧⌘O |
| Save project / save as | ⌘S / ⇧⌘S |
| Toggle attribute table / chart panel | ⌘T / ⌘J |
| Box select / lasso select / pan tool | B / L / Esc |
| Add to selection | ⌘ + click or drag |

## 16. Troubleshooting

| Problem | Fix |
|---|---|
| "unidentified developer" / "damaged" | See section 1 (`xattr -dr com.apple.quarantine /Applications/GeoStat.app`) |
| Garbled attribute text | The file uses an encoding other than cp949/UTF-8; resave as UTF-8 |
| Layer not visible | Missing or wrong CRS — check it in the layer info and use **Set…** |
| "Analysis engine stopped" | Click **Restart engine**; open data is closed, so reopen your project |
| MGWR / Max-p takes too long | Cancel from the status bar; reduce observations or try GWR / SKATER first |

Please report problems at [GitHub Issues](https://github.com/SeaViewer91/GeoStat/issues).
