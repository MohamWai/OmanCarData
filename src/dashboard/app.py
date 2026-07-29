import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.geo import OMAN_CITY_COORDS, OMAN_NEIGHBORHOOD_COORDS
from src.dashboard.market_position import enrich_market_position
from src.dashboard.stats_analysis import (
    bootstrap_median_by_make_model,
    depreciation_regression,
    group_price_comparison,
    interpret_p_value,
    numeric_correlation_matrix,
)
from src.models.price_predictor import PricePredictorNotReady, predict_price
from src.storage import load_processed

PROCESSED_DIR = ROOT / "data" / "processed"
CHART_TEMPLATE = "plotly_dark"
CHART_COLORS = px.colors.qualitative.Set2

PAGES = [
    "Market Overview",
    "Explore Listings",
    "Price Landscape",
    "Geography",
    "Specs & Segments",
    "Data Quality",
    "Statistical Analysis",
    "Price Prediction",
]

MARKET_POSITIONS = ["All", "Below Market", "Fair Price", "Above Market", "Unknown"]
# Bump when market position schema changes (invalidates Streamlit cache).
MARKET_POSITION_VERSION = 2


@st.cache_data(ttl=300)
def load_data(_market_position_version: int = MARKET_POSITION_VERSION) -> tuple[pd.DataFrame, dict]:
    df, metadata = load_processed(PROCESSED_DIR)
    return enrich_market_position(df), metadata


def style_fig(fig: go.Figure, title: str | None = None) -> go.Figure:
    if title:
        fig.update_layout(title=title)
    fig.update_layout(
        template=CHART_TEMPLATE,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=24, r=24, t=56, b=24),
        font=dict(size=13),
        title_x=0.02,
        colorway=CHART_COLORS,
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)", zeroline=False)
    return fig


def show_chart(fig: go.Figure, title: str | None = None) -> None:
    st.plotly_chart(style_fig(fig, title=title), use_container_width=True)


def bar_chart(
    frame: pd.DataFrame,
    category: str,
    value: str,
    title: str,
    horizontal: bool = False,
    sort_desc: bool = True,
) -> None:
    data = frame.copy()
    if sort_desc:
        data = data.sort_values(value, ascending=horizontal)
    else:
        data = data.sort_values(category)

    if horizontal:
        fig = px.bar(
            data,
            x=value,
            y=category,
            orientation="h",
            text=value,
            color_discrete_sequence=[CHART_COLORS[0]],
        )
        fig.update_layout(
            yaxis={"categoryorder": "total ascending"},
            margin=dict(l=24, r=48, t=56, b=24),
        )
        fig.update_traces(texttemplate="%{text:,}", textposition="outside", cliponaxis=False)
    else:
        fig = px.bar(
            data,
            x=category,
            y=value,
            text=value,
            color_discrete_sequence=[CHART_COLORS[0]],
        )
        fig.update_layout(xaxis_tickangle=-35, margin=dict(l=24, r=24, t=56, b=96))
        fig.update_traces(texttemplate="%{text:,}", textposition="outside", cliponaxis=False)

    show_chart(fig, title=title)


def _price_chart_cap(prices: pd.Series) -> float:
    if prices.empty:
        return 50_000.0
    cap = float(prices.quantile(0.99))
    return min(max(cap * 1.05, 15_000), 60_000)


def init_session_filters(df: pd.DataFrame) -> None:
    if "filters_initialized" not in st.session_state:
        st.session_state.filters_initialized = True
        st.session_state.selected_makes = sorted(df["make"].dropna().unique().tolist())
        st.session_state.selected_cities = sorted(df["city"].dropna().unique().tolist())
        st.session_state.condition = "All"
        st.session_state.market_position = "All"
        st.session_state.year_range = (
            int(df["year"].min()) if df["year"].notna().any() else 1990,
            int(df["year"].max()) if df["year"].notna().any() else 2026,
        )
        st.session_state.price_range = (
            float(df["price_omr"].min()) if df["price_omr"].notna().any() else 0.0,
            _price_chart_cap(df["price_omr"].dropna()) if df["price_omr"].notna().any() else 60_000.0,
        )
        st.session_state.price_page_top_n = 10
        st.session_state.price_page_max_price = (
            _price_chart_cap(df["price_omr"].dropna()) if df["price_omr"].notna().any() else 50_000.0
        )
        st.session_state.price_page_hist_bins = 40
        st.session_state.price_page_scatter_makes = sorted(df["make"].dropna().unique().tolist())[:12]

    defaults = {
        "selected_makes": sorted(df["make"].dropna().unique().tolist()),
        "selected_cities": sorted(df["city"].dropna().unique().tolist()),
        "condition": "All",
        "market_position": "All",
        "year_range": (
            int(df["year"].min()) if df["year"].notna().any() else 1990,
            int(df["year"].max()) if df["year"].notna().any() else 2026,
        ),
        "price_range": (
            float(df["price_omr"].min()) if df["price_omr"].notna().any() else 0.0,
            _price_chart_cap(df["price_omr"].dropna()) if df["price_omr"].notna().any() else 60_000.0,
        ),
        "price_page_top_n": 10,
        "price_page_max_price": (
            _price_chart_cap(df["price_omr"].dropna()) if df["price_omr"].notna().any() else 50_000.0
        ),
        "price_page_hist_bins": 40,
        "price_page_scatter_makes": sorted(df["make"].dropna().unique().tolist())[:12],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_header(metadata: dict, total_listings: int) -> None:
    left, right = st.columns([3, 1])
    updated = metadata.get("last_updated", "unknown")
    updated_display = updated[:10] if isinstance(updated, str) and len(updated) >= 10 else "unknown"
    with left:
        st.title("Oman Car Market Dashboard")
        st.caption(
            f"OpenSooq Oman snapshot — refreshed {updated_display} via scheduled pipeline "
            f"(not scraped on each page load)."
        )
    with right:
        st.metric("Dataset size", f"{total_listings:,}")
        st.caption(f"Last processed {updated_display}")


def render_data_status(metadata: dict, total_listings: int) -> None:
    with st.sidebar.expander("Data status", expanded=False):
        st.write(f"**Listings:** {metadata.get('row_count', total_listings):,}")
        median = metadata.get("price_median_omr")
        if median is not None:
            st.write(f"**Median price:** {median:,.0f} OMR")
        sources = metadata.get("source_files") or []
        if sources:
            st.write("**Raw sources:**")
            for source in sources:
                st.caption(f"- {source}")
        anomaly = metadata.get("anomaly_summary") or {}
        if anomaly:
            flagged = sum(anomaly.values())
            st.write(f"**Flagged listings:** {flagged:,}")
        st.caption("Refresh locally: `python scripts/refresh_data.py --max-pages 5`")


def render_sidebar(df: pd.DataFrame, metadata: dict) -> pd.DataFrame:
    st.sidebar.header("Filters")
    makes = sorted(df["make"].dropna().unique().tolist())
    cities = sorted(df["city"].dropna().unique().tolist())

    selected_makes = st.sidebar.multiselect("Make", makes, default=st.session_state.selected_makes)
    selected_cities = st.sidebar.multiselect("City", cities, default=st.session_state.selected_cities)
    condition = st.sidebar.selectbox(
        "Condition",
        ["All", "New", "Used"],
        index=["All", "New", "Used"].index(st.session_state.condition),
    )
    market_position = st.sidebar.selectbox(
        "Market position",
        MARKET_POSITIONS,
        index=MARKET_POSITIONS.index(st.session_state.get("market_position", "All")),
    )

    year_min = int(df["year"].min()) if df["year"].notna().any() else 1990
    year_max = int(df["year"].max()) if df["year"].notna().any() else 2026
    year_range = st.sidebar.slider("Year", year_min, year_max, st.session_state.year_range)

    price_min = float(df["price_omr"].min()) if df["price_omr"].notna().any() else 0.0
    price_cap = _price_chart_cap(df["price_omr"].dropna()) if df["price_omr"].notna().any() else 60_000.0
    price_range = st.sidebar.slider(
        "Price (OMR)",
        price_min,
        price_cap,
        (
            min(st.session_state.price_range[0], price_cap),
            min(st.session_state.price_range[1], price_cap),
        ),
        step=100.0,
    )

    st.session_state.selected_makes = selected_makes
    st.session_state.selected_cities = selected_cities
    st.session_state.condition = condition
    st.session_state.market_position = market_position
    st.session_state.year_range = year_range
    st.session_state.price_range = price_range

    filtered = df.copy()
    if selected_makes:
        filtered = filtered[filtered["make"].isin(selected_makes)]
    if selected_cities:
        filtered = filtered[filtered["city"].isin(selected_cities)]
    if condition != "All":
        filtered = filtered[filtered["condition"] == condition]
    if market_position != "All":
        filtered = filtered[filtered["market_position"] == market_position]
    filtered = filtered[filtered["year"].between(year_range[0], year_range[1], inclusive="both") | filtered["year"].isna()]
    filtered = filtered[filtered["price_omr"].between(price_range[0], price_range[1], inclusive="both") | filtered["price_omr"].isna()]

    below_market = (filtered["market_position"] == "Below Market").sum()
    st.sidebar.caption(f"Showing {len(filtered):,} of {len(df):,} listings")
    if below_market:
        st.sidebar.success(f"{below_market:,} below-market deals in view")
    render_data_status(metadata, len(df))
    return filtered


def page_overview(df: pd.DataFrame, metadata: dict) -> None:
    st.subheader("Market Overview")
    st.caption(
        "Market position uses make/model quantile bands (Q1–Q3) or hedonic residuals "
        "(log price ~ year + km when n≥20), not fixed ±15% thresholds."
    )
    below_market = (df["market_position"] == "Below Market").sum()
    above_market = (df["market_position"] == "Above Market").sum()
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Listings", f"{len(df):,}")
    col2.metric("Median Price", f"{df['price_omr'].median():,.0f} OMR" if df["price_omr"].notna().any() else "N/A")
    col3.metric("Below Market", f"{below_market:,}")
    col4.metric("Above Market", f"{above_market:,}")
    used_pct = (df["condition"] == "Used").mean() * 100 if df["condition"].notna().any() else 0
    col5.metric("Used Share", f"{used_pct:.1f}%")

    left, right = st.columns(2)
    with left:
        make_counts = df["make"].value_counts().head(12).reset_index()
        make_counts.columns = ["make", "count"]
        bar_chart(make_counts, category="make", value="count", title="Top Makes", horizontal=True)
    with right:
        city_counts = df["city"].value_counts().reset_index()
        city_counts.columns = ["city", "count"]
        bar_chart(city_counts, category="city", value="count", title="Listings by City", horizontal=True)

    market_counts = df["market_position"].value_counts().reset_index()
    market_counts.columns = ["market_position", "count"]
    fig = px.pie(
        market_counts,
        names="market_position",
        values="count",
        title="Market Position Mix",
        color="market_position",
        color_discrete_map={
            "Below Market": "#2ECC71",
            "Fair Price": "#3498DB",
            "Above Market": "#E74C3C",
            "Unknown": "#95A5A6",
        },
    )
    show_chart(fig)

    scrape_dates = df["scraped_at"].dt.normalize().dropna().unique()
    if len(scrape_dates) >= 2:
        trend = df.groupby(df["scraped_at"].dt.date).size().reset_index(name="count")
        trend.columns = ["date", "count"]
        bar_chart(trend, category="date", value="count", title="Listings by Scrape Date", sort_desc=False)


def page_explore(df: pd.DataFrame) -> None:
    st.subheader("Explore Listings")
    sort_by = st.selectbox(
        "Sort by",
        ["Price (low to high)", "Price (high to low)", "Best deals", "Year (newest)"],
    )

    table = df.copy()
    if "market_confidence" not in table.columns:
        table = enrich_market_position(table)

    if sort_by == "Price (low to high)":
        table = table.sort_values("price_omr", na_position="last")
    elif sort_by == "Price (high to low)":
        table = table.sort_values("price_omr", ascending=False, na_position="last")
    elif sort_by == "Best deals":
        table = table.sort_values("price_vs_market_pct", na_position="last")
    elif sort_by == "Year (newest)":
        table = table.sort_values("year", ascending=False, na_position="last")

    display_cols = [
        "name",
        "make",
        "model",
        "year",
        "price_omr",
        "market_position",
        "market_confidence",
        "group_size",
        "price_vs_market_pct",
        "km_mid",
        "city",
        "condition",
        "url",
    ]
    table = table[display_cols].rename(
        columns={
            "name": "Name",
            "make": "Make",
            "model": "Model",
            "year": "Year",
            "price_omr": "Price (OMR)",
            "market_position": "Market",
            "market_confidence": "Confidence",
            "group_size": "Comparables",
            "price_vs_market_pct": "vs Median %",
            "km_mid": "Kilometers (mid)",
            "city": "City",
            "condition": "Condition",
            "url": "URL",
        }
    )
    table["Price (OMR)"] = table["Price (OMR)"].map(lambda value: f"{value:,.0f}" if pd.notna(value) else "")
    table["vs Median %"] = table["vs Median %"].map(
        lambda value: f"{value:+.0f}%" if pd.notna(value) else ""
    )
    table["Comparables"] = table["Comparables"].map(
        lambda value: f"{int(value):,}" if pd.notna(value) else ""
    )
    table["Kilometers (mid)"] = table["Kilometers (mid)"].map(
        lambda value: f"{value:,.0f}" if pd.notna(value) else ""
    )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "URL": st.column_config.LinkColumn("Listing"),
            "Market": st.column_config.TextColumn(
                "Market",
                help=(
                    "Below Q1 or above Q3 vs make/model peers (or hedonic residual bands when n≥20). "
                    "Requires at least 5 comparables with price variation."
                ),
            ),
            "Confidence": st.column_config.TextColumn(
                "Confidence",
                help="High/Moderate/Low based on peer group size; Unreliable when n<5 or IQR=0.",
            ),
        },
    )


def page_price(df: pd.DataFrame) -> None:
    st.subheader("Price Landscape")

    priced = df.dropna(subset=["price_omr", "make"])
    if priced.empty:
        st.warning("No listings match the current filters.")
        return

    default_cap = _price_chart_cap(priced["price_omr"])
    all_makes = sorted(priced["make"].unique().tolist())

    with st.expander("Chart options", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        top_n = c1.slider(
            "Top makes (box plot)",
            min_value=5,
            max_value=min(20, len(all_makes)),
            value=min(st.session_state.price_page_top_n, len(all_makes)),
        )
        hist_bins = c2.slider("Histogram bins", min_value=10, max_value=80, value=st.session_state.price_page_hist_bins)
        max_price = c3.slider(
            "Max price on charts (OMR)",
            min_value=5_000,
            max_value=60_000,
            value=int(min(st.session_state.price_page_max_price, default_cap)),
            step=1_000,
        )
        color_by = c4.selectbox("Scatter color by", ["make", "condition", "city", "body_type", "market_position"])

        scatter_default = [make for make in st.session_state.price_page_scatter_makes if make in all_makes]
        if not scatter_default:
            scatter_default = all_makes[:12]
        scatter_makes = st.multiselect("Makes in scatter plot", all_makes, default=scatter_default)

        year_min = int(priced["year"].min()) if priced["year"].notna().any() else 1990
        year_max = int(priced["year"].max()) if priced["year"].notna().any() else 2026
        scatter_years = st.slider("Scatter year range", year_min, year_max, (year_min, year_max))

    st.session_state.price_page_top_n = top_n
    st.session_state.price_page_hist_bins = hist_bins
    st.session_state.price_page_max_price = max_price
    st.session_state.price_page_scatter_makes = scatter_makes

    chart_df = priced[priced["price_omr"] <= max_price]
    excluded = len(priced) - len(chart_df)
    if excluded:
        st.caption(f"Showing listings up to {max_price:,.0f} OMR ({excluded:,} hidden above cap).")

    top_makes = chart_df["make"].value_counts().head(top_n).index.tolist()
    subset = chart_df[chart_df["make"].isin(top_makes)]

    left, right = st.columns(2)
    box_fig = px.box(
        subset,
        x="make",
        y="price_omr",
        color="make",
        color_discrete_sequence=CHART_COLORS,
        title=f"Price Distribution by Make (Top {top_n})",
    )
    box_fig.update_layout(yaxis_range=[0, max_price], xaxis_tickangle=-45, showlegend=False)
    left.plotly_chart(style_fig(box_fig), use_container_width=True)

    hist_fig = px.histogram(
        chart_df,
        x="price_omr",
        nbins=hist_bins,
        title="Price Histogram",
        color_discrete_sequence=[CHART_COLORS[1]],
    )
    hist_fig.update_layout(xaxis_range=[0, max_price])
    right.plotly_chart(style_fig(hist_fig), use_container_width=True)

    scatter_df = chart_df[chart_df["make"].isin(scatter_makes)].dropna(subset=["year"])
    scatter_df = scatter_df[scatter_df["year"].between(scatter_years[0], scatter_years[1])]
    if scatter_df.empty:
        st.info("No listings match the scatter plot filters.")
        return

    color_field = color_by if color_by in scatter_df.columns else "make"
    scatter_fig = px.scatter(
        scatter_df,
        x="year",
        y="price_omr",
        color=color_field,
        hover_data=["make", "model", "city", "market_position"],
        title="Year vs Price",
        color_discrete_map={
            "Below Market": "#2ECC71",
            "Fair Price": "#3498DB",
            "Above Market": "#E74C3C",
            "Unknown": "#95A5A6",
        }
        if color_field == "market_position"
        else None,
    )
    scatter_fig.update_layout(
        yaxis_range=[0, max_price],
        legend_title_text=color_field.replace("_", " ").title(),
    )
    show_chart(scatter_fig)


def _attach_coords(frame: pd.DataFrame, place_col: str, coord_map: dict[str, tuple[float, float]]) -> pd.DataFrame:
    result = frame.copy()
    result["lat"] = result[place_col].map(lambda name: coord_map.get(name, (None, None))[0])
    result["lon"] = result[place_col].map(lambda name: coord_map.get(name, (None, None))[1])
    return result.dropna(subset=["lat", "lon"])


def page_geography(df: pd.DataFrame) -> None:
    st.subheader("Geography")
    city_df = df.dropna(subset=["city"])
    if city_df.empty:
        st.warning("No city data for the current filters.")
        return

    map_level = st.radio("Map view", ["By city", "By neighborhood"], horizontal=True)
    color_by = st.selectbox("Map color", ["median_price", "count", "below_market"])

    if map_level == "By city":
        map_df = (
            city_df.groupby("city", as_index=False)
            .agg(
                count=("city", "size"),
                median_price=("price_omr", "median"),
                below_market=("market_position", lambda s: (s == "Below Market").sum()),
            )
        )
        map_df = _attach_coords(map_df, "city", OMAN_CITY_COORDS)
        place_col = "city"
        map_title = "Oman Listings Map by City"
    else:
        nb_df = city_df.dropna(subset=["neighborhood"])
        if nb_df.empty:
            st.info("No neighborhood data available.")
            return
        top_neighborhoods = nb_df["neighborhood"].value_counts().head(25).index.tolist()
        nb_df = nb_df[nb_df["neighborhood"].isin(top_neighborhoods)]
        map_df = (
            nb_df.groupby("neighborhood", as_index=False)
            .agg(
                count=("neighborhood", "size"),
                median_price=("price_omr", "median"),
                below_market=("market_position", lambda s: (s == "Below Market").sum()),
            )
        )
        map_df = _attach_coords(map_df, "neighborhood", OMAN_NEIGHBORHOOD_COORDS)
        place_col = "neighborhood"
        map_title = "Top Neighborhoods Map (Muscat & major areas)"
        mapped_names = set(map_df["neighborhood"])
        missing = [name for name in top_neighborhoods if name not in mapped_names]
        if missing:
            st.caption(f"Showing {len(map_df)} mapped neighborhoods ({len(missing)} without coordinates omitted).")

    if map_df.empty:
        st.warning("No locations could be mapped.")
        return

    size_metric = "count"
    zoom = 5.8 if map_level == "By neighborhood" else 5.3
    center = {"lat": 23.58, "lon": 58.35} if map_level == "By neighborhood" else {"lat": 21.4, "lon": 57.2}
    color_scale = "Greens" if color_by == "below_market" else "Redor"

    map_fig = px.scatter_map(
        map_df,
        lat="lat",
        lon="lon",
        size=size_metric,
        color=color_by,
        hover_name=place_col,
        hover_data={size_metric: ":,", color_by: ":,.0f", "lat": False, "lon": False},
        zoom=zoom,
        center=center,
        map_style="carto-darkmatter",
        title=map_title,
        color_continuous_scale=color_scale,
    )
    map_fig.update_traces(marker=dict(sizemin=12, opacity=0.85))
    st.plotly_chart(style_fig(map_fig, title=map_title), use_container_width=True)

    st.caption("Bubble size = listing count. Pan and zoom to explore.")

    left, right = st.columns(2)

    with left:
        city_counts = city_df["city"].value_counts().reset_index()
        city_counts.columns = ["city", "count"]
        bar_chart(city_counts, category="city", value="count", title="Listings by City", horizontal=True)

    with right:
        city_price = city_df.groupby("city", as_index=False)["price_omr"].median().sort_values("price_omr")
        bar_chart(city_price, category="city", value="price_omr", title="Median Price by City", horizontal=True)

    neighborhood = city_df.dropna(subset=["neighborhood"])
    if not neighborhood.empty:
        nb_counts = neighborhood["neighborhood"].value_counts().head(20).reset_index()
        nb_counts.columns = ["neighborhood", "count"]
        bar_chart(nb_counts, category="neighborhood", value="count", title="Top Neighborhoods", horizontal=True)


def page_specs(df: pd.DataFrame) -> None:
    st.subheader("Specs & Segments")
    left, right = st.columns(2)

    fuel_counts = df["fuel"].value_counts().reset_index()
    fuel_counts.columns = ["fuel", "count"]
    fig = px.pie(fuel_counts, names="fuel", values="count", title="Fuel Type", color_discrete_sequence=CHART_COLORS)
    left.plotly_chart(style_fig(fig), use_container_width=True)

    transmission_counts = df["transmission"].value_counts().reset_index()
    transmission_counts.columns = ["transmission", "count"]
    fig = px.pie(
        transmission_counts,
        names="transmission",
        values="count",
        title="Transmission",
        color_discrete_sequence=CHART_COLORS,
    )
    right.plotly_chart(style_fig(fig), use_container_width=True)

    specs_counts = df["regional_specs"].value_counts().reset_index()
    specs_counts.columns = ["regional_specs", "count"]
    bar_chart(specs_counts, category="regional_specs", value="count", title="Regional Specs")

    body_counts = df["body_type"].value_counts().reset_index()
    body_counts.columns = ["body_type", "count"]
    bar_chart(body_counts, category="body_type", value="count", title="Body Type")

    km_df = df.dropna(subset=["km_mid"])
    if not km_df.empty:
        hist_fig = px.histogram(
            km_df,
            x="km_mid",
            nbins=30,
            title="Kilometer Distribution",
            color_discrete_sequence=[CHART_COLORS[2]],
        )
        show_chart(hist_fig)


def page_data_quality(df: pd.DataFrame, metadata: dict) -> None:
    st.subheader("Data Quality")
    summary = metadata.get("anomaly_summary", {})
    if summary:
        summary_df = pd.DataFrame({"flag": list(summary.keys()), "count": list(summary.values())})
        summary_df = summary_df.sort_values("count", ascending=False)
        bar_chart(summary_df, category="flag", value="count", title="Anomaly Flags", sort_desc=False)

    col1, col2 = st.columns(2)
    with col1:
        st.write("Dataset metadata")
        st.json(metadata)
    with col2:
        clean_pct = (1 - df["has_anomaly"].mean()) * 100 if "has_anomaly" in df.columns else 0
        st.metric("Data health score", f"{clean_pct:.1f}%")
        st.caption("Share of listings without any anomaly flag.")

    flagged = df[df["has_anomaly"]].head(100)
    if not flagged.empty:
        st.write("Sample flagged listings")
        st.dataframe(
            flagged[
                [
                    "name",
                    "make",
                    "model",
                    "year",
                    "price_omr",
                    "market_position",
                    "flag_missing_core",
                    "flag_year_invalid",
                    "flag_km_suspicious",
                    "flag_price_outlier",
                    "flag_duplicate",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )


def page_statistics(df: pd.DataFrame) -> None:
    st.subheader("Statistical Analysis")
    st.caption(
        "Inferential methods on filtered listings. Prices are skewed, so Kruskal-Wallis and "
        "Spearman correlations are preferred over ANOVA and Pearson where noted."
    )

    priced = df.dropna(subset=["price_omr"])
    if len(priced) < 30:
        st.warning("Need at least 30 priced listings for statistical analysis.")
        return

    st.markdown("### Depreciation curve")
    st.write(
        "Fits **log(price) ~ year** for a selected make. The slope approximates how listed prices "
        "change with model year (holding other factors constant). A positive slope means newer model "
        "years tend to list at higher prices in this sample."
    )
    make_counts = priced["make"].value_counts()
    eligible_makes = make_counts[make_counts >= 30].index.tolist()
    if not eligible_makes:
        st.info("No make has at least 30 listings in the current filter.")
    else:
        selected_make = st.selectbox("Make for depreciation model", eligible_makes, key="stats_dep_make")
        dep = depreciation_regression(priced, selected_make)
        if dep:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Listings (n)", f"{dep['n']:,}")
            c2.metric("R²", f"{dep['r_squared']:.3f}")
            c3.metric("Annual price change", f"{dep['annual_pct_change']:+.1f}%")
            c4.metric("p-value (slope)", f"{dep['p_value']:.4g}")

            direction = "increase" if dep["annual_pct_change"] >= 0 else "decrease"
            st.write(
                f"Each additional model year is associated with a **{abs(dep['annual_pct_change']):.1f}%** "
                f"{direction} in listed price for **{selected_make}** "
                f"({interpret_p_value(dep['p_value'])})."
            )

            scatter = dep["scatter"]
            line = dep["line"]
            fig = px.scatter(
                scatter,
                x="year",
                y="log_price",
                hover_data=["price_omr"],
                opacity=0.35,
                title=f"log(Price) vs Year — {selected_make}",
                color_discrete_sequence=[CHART_COLORS[0]],
            )
            fig.add_trace(
                go.Scatter(
                    x=line["year"],
                    y=line["log_price_fitted"],
                    mode="lines",
                    name="OLS fit",
                    line=dict(color=CHART_COLORS[1], width=3),
                )
            )
            show_chart(fig)

    st.divider()

    st.markdown("### Price differences across groups")
    group_col = st.selectbox(
        "Compare prices across",
        ["city", "fuel", "transmission"],
        key="stats_group_col",
    )
    comparison = group_price_comparison(priced, group_col)
    if comparison is None:
        st.info("Not enough groups with sufficient listings for this comparison.")
    else:
        st.write(
            "Prices are typically right-skewed, so **Kruskal-Wallis** (non-parametric) is the "
            "primary test. **One-way ANOVA** is shown for reference but assumes approximate normality."
        )
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Kruskal-Wallis p-value", f"{comparison['kruskal_p']:.4g}")
            st.caption(interpret_p_value(comparison["kruskal_p"]))
        with c2:
            st.metric("ANOVA p-value", f"{comparison['anova_p']:.4g}")
            st.caption(interpret_p_value(comparison["anova_p"]))

        box_fig = px.box(
            priced[priced[group_col].isin(comparison["groups"])],
            x=group_col,
            y="price_omr",
            color=group_col,
            color_discrete_sequence=CHART_COLORS,
            title=f"Price by {group_col.replace('_', ' ').title()}",
        )
        box_fig.update_layout(showlegend=False, xaxis_tickangle=-35)
        show_chart(box_fig)

        summary = comparison["summary"].rename(
            columns={
                group_col: group_col.replace("_", " ").title(),
                "n": "n",
                "median": "Median (OMR)",
                "mean": "Mean (OMR)",
            }
        )
        st.dataframe(summary, use_container_width=True, hide_index=True)

    st.divider()

    st.markdown("### Bootstrap confidence intervals for median price")
    st.write(
        "Non-parametric **95% percentile bootstrap CIs** for the median listing price by make/model. "
        "Only pairs with at least 25 listings in the current filter are shown."
    )
    ci_df = bootstrap_median_by_make_model(priced, min_n=25, top_n=15)
    if ci_df.empty:
        st.info("No make/model pair has at least 25 listings.")
    else:
        ci_df["label"] = ci_df["make"] + " " + ci_df["model"]
        ci_df = ci_df.sort_values("median_omr", ascending=True)
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=ci_df["median_omr"],
                y=ci_df["label"],
                mode="markers",
                marker=dict(size=10, color=CHART_COLORS[2]),
                error_x=dict(
                    type="data",
                    symmetric=False,
                    array=ci_df["ci_high_omr"] - ci_df["median_omr"],
                    arrayminus=ci_df["median_omr"] - ci_df["ci_low_omr"],
                ),
                name="Median ± 95% CI",
            )
        )
        fig.update_layout(
            title="Median Price with 95% Bootstrap CI (top make/model pairs)",
            xaxis_title="Price (OMR)",
            yaxis_title="Make / Model",
            template=CHART_TEMPLATE,
        )
        show_chart(fig)

        display = ci_df[["make", "model", "n", "median_omr", "ci_low_omr", "ci_high_omr"]].copy()
        display["median_omr"] = display["median_omr"].map(lambda v: f"{v:,.0f}")
        display["ci_low_omr"] = display["ci_low_omr"].map(lambda v: f"{v:,.0f}")
        display["ci_high_omr"] = display["ci_high_omr"].map(lambda v: f"{v:,.0f}")
        st.dataframe(display, use_container_width=True, hide_index=True)

    st.divider()

    st.markdown("### Correlation heatmap")
    pearson, spearman = numeric_correlation_matrix(priced)
    if pearson.empty:
        st.info("Not enough complete numeric records for correlation analysis.")
    else:
        st.write(
            "Associations among numeric fields. **Spearman** (rank-based) is more robust to skew and "
            "nonlinearity than **Pearson**. Correlation does not imply causation."
        )
        corr_method = st.radio("Coefficient", ["Spearman", "Pearson"], horizontal=True, key="stats_corr")
        matrix = spearman if corr_method == "Spearman" else pearson
        labels = [col.replace("_", " ").title() for col in matrix.columns]
        fig = px.imshow(
            matrix.values,
            x=labels,
            y=labels,
            zmin=-1,
            zmax=1,
            color_continuous_scale="RdBu_r",
            title=f"{corr_method} Correlation Matrix",
            text_auto=".2f",
            aspect="auto",
        )
        show_chart(fig)


def page_prediction() -> None:
    st.subheader("Price Prediction")
    st.info("Coming soon. This project prioritizes market exploration and data quality before predictive modeling.")
    if st.button("Try placeholder predictor"):
        try:
            predict_price({})
        except PricePredictorNotReady as exc:
            st.warning(str(exc))


def main() -> None:
    st.set_page_config(page_title="Oman Car Market Dashboard", layout="wide", page_icon="🚗")

    try:
        df, metadata = load_data()
    except FileNotFoundError:
        st.error("Processed data not found. Ensure `data/processed/listings.parquet` exists.")
        st.stop()

    if "market_confidence" not in df.columns:
        df = enrich_market_position(df)

    render_header(metadata, len(df))
    init_session_filters(df)

    page = st.radio(
        "Pages",
        PAGES,
        horizontal=True,
        label_visibility="collapsed",
        key="active_page",
    )
    st.divider()

    filtered = render_sidebar(df, metadata)

    if page == "Market Overview":
        page_overview(filtered, metadata)
    elif page == "Explore Listings":
        page_explore(filtered)
    elif page == "Price Landscape":
        page_price(filtered)
    elif page == "Geography":
        page_geography(filtered)
    elif page == "Specs & Segments":
        page_specs(filtered)
    elif page == "Data Quality":
        page_data_quality(filtered, metadata)
    elif page == "Statistical Analysis":
        page_statistics(filtered)
    elif page == "Price Prediction":
        page_prediction()


if __name__ == "__main__":
    main()
