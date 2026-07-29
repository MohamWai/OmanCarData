# Oman Car Market Dashboard

An interactive dashboard for exploring used car listings from [OpenSooq Oman](https://om.opensooq.com/en/cars/cars-for-sale). A scheduled scraper pulls fresh listings, the cleanse pipeline normalizes them, and the Streamlit dashboard visualizes the latest snapshot.

---

## Project overview

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Scraper         │ ──> │  Data Cleansing   │ ──> │  Dashboard        │
│  (opensooq.py)   │     │  (parser →        │     │  (app.py)         │
│                  │     │   normalizers →    │     │                  │
│  __NEXT_DATA__   │     │   validators)     │     │  reads Parquet    │
│  → raw CSV       │     │  → Parquet        │     │  snapshot         │
└─────────────────┘     └──────────────────┘     └──────────────────┘
         ▲
         │  scheduled (GitHub Actions every 12h, or local cron)
```

The project has three stages:

1. **Scrape** — Pull car listings from OpenSooq SERP pages into `data/raw/`.
2. **Cleanse** — Parse, normalize, and flag anomalies → `data/processed/listings.parquet`.
3. **Explore** — Streamlit dashboard reads the processed snapshot (does **not** scrape on each visit).

---

## Live data pipeline

The dashboard shows a **scheduled snapshot**, not a live scrape per page load (~12k listings / 400+ pages would be too slow and risks rate limits).

### Refresh manually (dev)

```bash
# Quick test: 2 SERP pages (~60 listings) + full re-process of all raw CSVs
python scripts/refresh_data.py --max-pages 2

# Re-process existing raw CSVs only (no scrape)
python scripts/refresh_data.py --skip-scrape
```

### Scheduled refresh (production)

- **GitHub Actions:** [`.github/workflows/refresh_data.yml`](.github/workflows/refresh_data.yml) runs every 12 hours (`--max-pages 50` initially), commits updated `data/processed/*` and new raw CSVs.
- **Local cron:** `0 */12 * * * cd /path/to/newCar && python scripts/refresh_data.py`

### Why the old scraper failed

The original scraper looked for JSON-LD `@type: ItemList`, which OpenSooq no longer exposes. The new scraper reads listing data from the `__NEXT_DATA__` script tag at `serpApiResponse.listings.items`.

### Limitations

- **Asking prices only** — not sold/transaction prices.
- **Partial specs from SERP** — transmission, engine cc, VIN require detail-page scraping (future work).
- **OpenSooq HTML may change** — parsing is isolated in `src/scraper/opensooq.py`.
- **Terms of service** — scraping may violate OpenSooq ToS; use for academic/portfolio context.

---

## Project structure (excerpt)

```
newCar/
├── scripts/
│   └── refresh_data.py         # scrape → cleanse → Parquet (one command)
├── .github/workflows/
│   └── refresh_data.yml        # scheduled data refresh
├── README.md
├── requirements.txt
├── data/
│   ├── raw/                    # scraped + legacy CSV exports
│   └── processed/              # listings.parquet + metadata.json
├── notebooks/
│   └── analysis.ipynb
└── src/
    ├── scraper/
    │   └── opensooq.py         # __NEXT_DATA__ SERP scraper
    ├── cleanse/
    ├── dashboard/
    └── storage.py
```

---

## Full module layout

```
newCar/
├── README.md                   # This file
├── requirements.txt            # Python dependencies
├── .gitignore                  # Git ignore rules
│
├── data/
│   ├── raw/                    # Raw CSV files (input to cleansing)
│   │   ├── car_listings7k.csv
│   │   ├── car_listings7Kcopy.csv
│   │   └── car_listingsOldRaw.csv
│   └── processed/              # Cleaned output (read by the dashboard)
│       ├── listings.parquet    # Cleaned DataFrame in Parquet format
│       └── metadata.json       # Summary statistics (row count, median price, etc.)
│
├── notebooks/
│   └── analysis.ipynb          # Reproducible EDA + inferential analysis write-up
│
└── src/                        # Python source code
    ├── __init__.py
    │
    ├── storage.py              # Save/load processed data (Parquet + JSON metadata)
    │
    ├── cleanse/                # Data cleaning
    │   ├── __init__.py
    │   ├── parser.py
    │   ├── normalizers.py
    │   └── validators.py
    │
    ├── scraper/                # OpenSooq SERP scraper
    │   └── opensooq.py
    │
    ├── dashboard/              # Streamlit dashboard
    │   ├── app.py              # Main dashboard app (8 pages, filters, charts, maps)
    │   ├── geo.py              # GPS coordinates for Oman cities & neighborhoods
    │   ├── market_position.py  # Quantile / hedonic market position labeling
    │   └── stats_analysis.py   # Inferential stats for Statistical Analysis page
    │
    └── models/                 # ML models (placeholder)
        ├── __init__.py
        └── price_predictor.py  # Placeholder — raises PricePredictorNotReady
```

---

## Quick start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the dashboard

The dashboard reads from `data/processed/listings.parquet`. If that file already exists (it's included in the repo), you can launch directly:

```bash
streamlit run src/dashboard/app.py
```

### 3. Refresh live data

```bash
python scripts/refresh_data.py --max-pages 5
```

### 4. Process raw data only (no scrape)

To convert raw CSV files into the cleaned Parquet format that the dashboard reads, use the modules directly:

```python
from src.cleanse import load_raw_listings, normalize_listings, add_anomaly_flags
from src.storage import save_processed

raw_df = load_raw_listings("data/raw")
normalized = normalize_listings(raw_df)
flagged = add_anomaly_flags(normalized)
save_processed(flagged, "data/processed", source_files=["car_listings7k.csv"])
```

Drop new CSV exports into `data/raw/` before running with `--skip-scrape`.

### 5. Run the analysis notebook

Portfolio-style narrative + code walkthrough (data sources, EDA, market position methodology, validation, limitations):

```bash
jupyter notebook notebooks/analysis.ipynb
```

Run from the `notebooks/` directory so imports resolve to the project root.

---

## How each module works

### Scraper (`src/scraper/opensooq.py`)

- Fetches OpenSooq car search pages (`?search=true&page=N`).
- Parses `__NEXT_DATA__` → `serpApiResponse.listings.items` (30 listings/page).
- Maps SERP fields to the legacy CSV schema (price, make, model, year, km, city, etc.).
- Deduplicates by post ID across existing raw CSVs.
- Writes `data/raw/listings_YYYYMMDD.csv`.
- CLI: `python -m src.scraper.opensooq --max-pages 5`

### Parser (`src/cleanse/parser.py`)

- Scans `data/raw/` for all CSV files.
- Handles multiple CSV formats:
  - **Standard CSVs** — parsed with pandas.
  - **Full-copy CSVs** — a specific format where all fields are in a single comma-separated line (used by some exports).
  - **Slim CSVs** — standard format with fewer columns.
- Deduplicates listings by URL (keeps the most recent).
- Tags duplicate rows with `flag_duplicate = True`.
- Adds `source_file` (filename) and `scraped_at` (timestamp) columns.

### Normalizers (`src/cleanse/normalizers.py`)

Converts raw string columns into clean typed columns:

| Raw column | Cleaned column(s) | Transformation |
|---|---|---|
| `Name` | `name` | Stripped, nullified |
| `Price` | `price_omr` | Extracts numeric value (e.g., "5,500 OMR" → 5500.0) |
| `Year` | `year`, `year_valid` | Extracts 4-digit year, validates range 1990–current+1 |
| `Kilometers` | `km_min`, `km_max`, `km_mid` | Parses ranges ("50,000 - 70,000") or single values |
| `Engine Size (cc)` | `engine_cc_min`, `engine_cc_max` | Same range parsing |
| `Condition` | `condition` | Normalized to "New" or "Used" |
| `Number of Seats` | `seats` | Converted to numeric |
| Various text fields | `make`, `model`, `trim`, `fuel`, `transmission`, `body_type`, `color`, `city`, etc. | Stripped, nullified if empty/"none"/"n/a" |

### Validators (`src/cleanse/validators.py`)

Adds anomaly flags to help identify problematic listings:

| Flag | Condition |
|---|---|
| `flag_missing_core` | Missing make, model, or price |
| `flag_year_invalid` | Year outside 1990–current+1 |
| `flag_km_suspicious` | New car with >1,000 km, or any car with >400,000 km |
| `flag_price_outlier` | Price is an outlier within its make/model group (IQR method, min 4 listings) |
| `flag_duplicate` | Duplicate URL detected during parsing |
| `has_anomaly` | Any of the above flags is true |

### Storage (`src/storage.py`)

- `save_processed()` — Writes a cleaned DataFrame to `listings.parquet` + `metadata.json`.
- `load_processed()` — Reads them back.
- `build_metadata()` — Computes: last updated timestamp, row count, source files, anomaly summary, median price, unique makes, unique cities.

### Dashboard (`src/dashboard/app.py`)

A Streamlit app with 8 pages:

| Page | What it shows |
|---|---|
| **Market Overview** | Key metrics (listings count, median price, below/above market), top makes, listings by city, market position pie chart |
| **Explore Listings** | Sortable/filterable table of all listings with links to OpenSooq |
| **Price Landscape** | Box plots by make, price histogram, year vs. price scatter plot |
| **Geography** | Interactive map of Oman with bubble sizes by listing count, colored by median price or below-market deals |
| **Specs & Segments** | Fuel type, transmission, regional specs, body type, kilometer distribution |
| **Data Quality** | Anomaly flag counts, data health score, sample of flagged listings |
| **Statistical Analysis** | Depreciation regression, ANOVA/Kruskal-Wallis, bootstrap CIs, correlation heatmap |
| **Price Prediction** | Placeholder (coming soon) |

The dashboard also computes a **market position** for each listing:
- Compares each listing to peers with the same **make + model**.
- **Primary rule (n ≥ 20 with year & km):** hedonic expected price from `log(price) ~ year + km`; label using residual Q1/Q3 bands.
- **Fallback:** price below Q1 = **Below Market**, above Q3 = **Above Market**, between = **Fair Price**.
- **Unknown / Unreliable** when fewer than 5 comparables, or peer group has **IQR = 0** (no price spread).
- **Confidence** tiers: High (n ≥ 20), Moderate (n ≥ 10), Low (n ≥ 5), Unreliable otherwise.

### Geo coordinates (`src/dashboard/geo.py`)

Hardcoded approximate GPS coordinates for:
- 9 Oman governorates (Muscat, Al Batinah, Dhofar, etc.)
- ~20 major neighborhoods (Seeb, Sohar, Salalah, Nizwa, Al Khuwair, etc.)

Used by the Geography page to render the map.

### Statistical analysis (`src/dashboard/stats_analysis.py`)

Inferential methods used on the **Statistical Analysis** page:

- **Depreciation** — OLS of log(price) on model year by make
- **Group comparisons** — Kruskal-Wallis (primary) and one-way ANOVA on price across city, fuel, or transmission
- **Bootstrap CIs** — 95% percentile bootstrap intervals for median price by make/model
- **Correlation** — Pearson and Spearman heatmaps for year, km, engine size, and price

---

## Dashboard pages in detail

### Market Overview
- 5 key metrics: total listings, median price, below-market count, above-market count, used car share.
- Horizontal bar charts for top makes and cities.
- Pie chart showing market position distribution.
- Listings by scrape date (if multiple scrape batches exist).

### Explore Listings
- Sort by: price (low/high), best deals (most below market), year (newest).
- Columns: name, make, model, year, price, market position, % vs market, kilometers, city, condition, URL.
- URLs are clickable links to the original OpenSooq listing.

### Price Landscape
- Box plot of price distribution for top N makes.
- Histogram of prices with adjustable bins.
- Scatter plot of year vs. price, colorable by make, condition, city, body type, or market position.
- All charts respect a configurable max price cap.

### Geography
- Toggle between city-level and neighborhood-level map.
- Color bubbles by: listing count, median price, or below-market count.
- Pan/zoom interactive map (Carto dark matter style).
- Supporting bar charts for city/neighborhood breakdowns.

### Specs & Segments
- Pie charts for fuel type and transmission.
- Bar charts for regional specs and body type.
- Histogram of kilometer distribution.

### Data Quality
- Bar chart of anomaly flag counts.
- Data health score (% of listings with no anomalies).
- Full metadata JSON display.
- Sample of 100 flagged listings for inspection.

---

## Deploying the dashboard

Deploy `src/dashboard/app.py` to [Streamlit Community Cloud](https://streamlit.io/cloud):

1. Push this repository to GitHub.
2. Log in to Streamlit Community Cloud.
3. Click **New app** → select this repo → set main file to `src/dashboard/app.py`.
4. Deploy.

The app reads `data/processed/listings.parquet`, so make sure the processed data is committed to the repo or generated as part of the deploy process.

---

## Dependencies

| Package | Purpose |
|---|---|
| `requests` | HTTP requests for OpenSooq scraper |
| `beautifulsoup4` | HTML parsing (`__NEXT_DATA__` extraction) |
| `pandas` | Data manipulation and CSV/Parquet I/O |
| `numpy` | Numeric operations for bootstrap resampling |
| `scipy` | Statistical tests (ANOVA, Kruskal-Wallis, regression) |
| `pyarrow` | Parquet file format support |
| `streamlit` | Interactive dashboard framework |
| `plotly` | Interactive charts and maps |
