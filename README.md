# Oman Car Market Dashboard

A data pipeline and interactive dashboard for exploring used car listings from [OpenSooq Oman](https://om.opensooq.com/en/cars/cars-for-sale). The project scrapes car listings, cleanses and normalizes the raw data, detects anomalies, and visualizes the market through a Streamlit dashboard.

---

## Project overview

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Scraper         │ ──> │  Data Cleansing   │ ──> │  Dashboard        │
│  (opensooq.py)   │     │  (parser →        │     │  (app.py)         │
│                  │     │   normalizers →    │     │                  │
│  Fetches listings │     │   validators)     │     │  7 interactive   │
│  from OpenSooq   │     │                   │     │  pages with      │
│  → raw CSV files │     │  → cleaned Parquet │     │  charts & maps   │
└─────────────────┘     └──────────────────┘     └──────────────────┘
```

The project is organized into three main stages:

1. **Scrape** — Download car listings from OpenSooq and save as raw CSV files.
2. **Cleanse** — Parse the raw CSVs, normalize fields (prices, years, kilometers, etc.), and flag anomalies (missing data, outliers, duplicates).
3. **Explore** — Launch a Streamlit dashboard to filter, visualize, and analyze the cleaned data.

---

## Project structure

```
newCar/
├── DataScraperOpenSooq.py      # Standalone scraper (original single-file version)
├── README.md                   # This file
├── requirements.txt            # Python dependencies
├── .gitignore                  # Git ignore rules
│
├── data/
│   ├── raw/                    # Raw scraped CSV files (input to cleansing)
│   │   ├── car_listings7k.csv
│   │   ├── car_listings7Kcopy.csv
│   │   └── car_listingsOldRaw.csv
│   └── processed/              # Cleaned output (read by the dashboard)
│       ├── listings.parquet    # Cleaned DataFrame in Parquet format
│       └── metadata.json       # Summary statistics (row count, median price, etc.)
│
├── raw/                        # Duplicate of data/raw/ (leftover from restructuring)
│
└── src/                        # Python source code
    ├── __init__.py
    │
    ├── storage.py              # Save/load processed data (Parquet + JSON metadata)
    │
    ├── cleanse/                # Data cleaning pipeline
    │   ├── __init__.py         # Exports: load_raw_listings, normalize_listings, add_anomaly_flags
    │   ├── parser.py           # Discovers & parses raw CSV files, deduplicates by URL
    │   ├── normalizers.py      # Converts raw columns → typed columns (price, year, km, etc.)
    │   └── validators.py       # Flags anomalies: missing fields, bad years, suspicious km, price outliers
    │
    ├── scraper/                # Web scraping
    │   ├── __init__.py
    │   └── opensooq.py         # Scrapes OpenSooq car listings → CSV files
    │
    ├── dashboard/              # Streamlit dashboard
    │   ├── app.py              # Main dashboard app (7 pages, filters, charts, maps)
    │   └── geo.py              # GPS coordinates for Oman cities & neighborhoods
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

### 3. Scrape fresh data (optional)

To download the latest listings from OpenSooq:

```bash
python src/scraper/opensooq.py
```

This saves a timestamped CSV to `data/raw/` (e.g., `listings_20260727.csv`).

### 4. Process raw data into the dashboard format

To convert raw CSV files into the cleaned Parquet format that the dashboard reads, use the modules directly:

```python
from pathlib import Path
from src.cleanse import load_raw_listings, normalize_listings, add_anomaly_flags
from src.storage import save_processed

raw_df = load_raw_listings("data/raw")
normalized = normalize_listings(raw_df)
flagged = add_anomaly_flags(normalized)
save_processed(flagged, "data/processed", source_files=["car_listings7k.csv"])
```

---

## How each module works

### Scraper (`src/scraper/opensooq.py`)

- Fetches search result pages from OpenSooq (paginated).
- Extracts listing data from JSON-LD embedded in the HTML (name, price, URL, image).
- Visits each listing's detail page to scrape full specs (condition, make, model, year, kilometers, fuel, transmission, color, city, etc.).
- Skips URLs already seen in existing CSV files to avoid duplicates.
- Saves results to `data/raw/listings_YYYYMMDD.csv`.
- Can be run standalone: `python src/scraper/opensooq.py --max-pages 5`

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

A Streamlit app with 7 pages:

| Page | What it shows |
|---|---|
| **Market Overview** | Key metrics (listings count, median price, below/above market), top makes, listings by city, market position pie chart, data source breakdown |
| **Explore Listings** | Sortable/filterable table of all listings with links to OpenSooq |
| **Price Landscape** | Box plots by make, price histogram, year vs. price scatter plot |
| **Geography** | Interactive map of Oman with bubble sizes by listing count, colored by median price or below-market deals |
| **Specs & Segments** | Fuel type, transmission, regional specs, body type, kilometer distribution |
| **Data Quality** | Anomaly flag counts, data health score, sample of flagged listings |
| **Price Prediction** | Placeholder (coming soon) |

The dashboard also computes a **market position** for each listing:
- Compares each listing's price to the median price of the same make + model.
- Labels: **Below Market** (≤ -15%), **Fair Price** (-15% to +15%), **Above Market** (≥ +15%), or **Unknown** (< 3 comparable listings).

### Geo coordinates (`src/dashboard/geo.py`)

Hardcoded approximate GPS coordinates for:
- 9 Oman governorates (Muscat, Al Batinah, Dhofar, etc.)
- ~20 major neighborhoods (Seeb, Sohar, Salalah, Nizwa, Al Khuwair, etc.)

Used by the Geography page to render the map.

---

## Dashboard pages in detail

### Market Overview
- 5 key metrics: total listings, median price, below-market count, above-market count, used car share.
- Horizontal bar charts for top makes and cities.
- Pie chart showing market position distribution.
- Listings by data source and scrape date (if multiple sources exist).

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
| `requests` | HTTP requests for scraping |
| `beautifulsoup4` | HTML parsing for scraping |
| `pandas` | Data manipulation and CSV/Parquet I/O |
| `pyarrow` | Parquet file format support |
| `streamlit` | Interactive dashboard framework |
| `plotly` | Interactive charts and maps |