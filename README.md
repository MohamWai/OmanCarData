# Oman Car Market Dashboard

Explore OpenSooq Oman car listings: scrape raw data, cleanse anomalies, and explore the market in a Streamlit dashboard.

## Quick start

```bash
pip install -r requirements.txt
streamlit run src/dashboard/app.py
```

Processed parquet and metadata are written to `data/processed/`.

## Dashboard pages

- Market Overview
- Explore Listings
- Price Landscape
- Geography
- Specs & Segments
- Data Quality
- Price Prediction (coming soon)

## Deploy dashboard

Deploy `src/dashboard/app.py` to [Streamlit Community Cloud](https://streamlit.io/cloud) from this repository. The app reads `data/processed/listings.parquet`.
