import streamlit as st
import pandas as pd
import altair as alt
from pathlib import Path

from components.styles import inject_global_css
from components.ui import (
    hero_banner,
    section_header,
    metric_cards,
    disclaimer,
)


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Market Insights | PP PropertyLens",
    page_icon="💡",
    layout="wide",
)

inject_global_css()


# =========================================================
# PATHS
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_PATH = (
    PROJECT_ROOT / "data" / "gold" / "property_listings_geocoded.csv"
)


# =========================================================
# LOAD DATA
# =========================================================

@st.cache_data
def load_data():
    return pd.read_csv(DATA_PATH)


df = load_data()


# =========================================================
# HEADER
# =========================================================

hero_banner(
    title="Phnom Penh Market Insights",
    description=(
        "Explore advertised Condo and Penthouse "
        "asking-price patterns across Phnom Penh."
    ),
)


# =========================================================
# MARKET FILTERS
# =========================================================

section_header(
    "Market Filters",
    subtitle="Use the filters below to explore specific parts of the Phnom Penh property market.",
)

with st.container(border=True):

    filter_col1, filter_col2 = st.columns([1, 2], gap="large")

    with filter_col1:

        property_type_filter = st.segmented_control(
            "Property Type",
            options=["All", "Condo", "Penthouse"],
            default="All",
            selection_mode="single",
            key="market_property_type",
            width="stretch",
        )

    with filter_col2:

        district_options = sorted(
            df["district"].dropna().unique()
        )

        district_filter = st.multiselect(
            "District",
            options=district_options,
            default=[],
            placeholder="All districts",
            key="market_districts",
        )

    max_price = int(df["price_usd"].max())

    price_range = st.slider(
        "Asking Price Range",
        min_value=0,
        max_value=max_price,
        value=(0, max_price),
        step=10_000,
        format="$%d",
        key="market_price_range",
    )


# =========================================================
# APPLY FILTERS
# =========================================================

filtered_df = df.copy()

if property_type_filter != "All":
    filtered_df = filtered_df[
        filtered_df["property_type"] == property_type_filter
    ].copy()

if district_filter:
    filtered_df = filtered_df[
        filtered_df["district"].isin(district_filter)
    ].copy()

filtered_df = filtered_df[
    filtered_df["price_usd"].between(price_range[0], price_range[1])
].copy()


if filtered_df.empty:
    st.warning(
        "No listings match the selected filters. "
        "Try expanding the district or asking-price range."
    )
    st.stop()

st.caption(
    f"Showing **{len(filtered_df):,} listings** "
    "for the selected market filters."
)


# =========================================================
# MARKET OVERVIEW
# =========================================================

section_header("Market Overview")

lowest_price = filtered_df["price_usd"].min()
median_price = filtered_df["price_usd"].median()
highest_price = filtered_df["price_usd"].max()
median_size = filtered_df["size_m2"].median()
district_count = filtered_df["district"].nunique()

metric_cards([
    {"label": "Listings", "value": f"{len(filtered_df):,}", "icon": "🏠"},
    {"label": "Lowest Asking Price", "value": f"${lowest_price:,.0f}", "icon": "📉"},
    {"label": "Median Asking Price", "value": f"${median_price:,.0f}", "icon": "💵"},
], columns=st.columns(3, gap="medium"))

st.markdown("")

metric_cards([
    {"label": "Highest Asking Price", "value": f"${highest_price:,.0f}", "icon": "📈"},
    {"label": "Median Size", "value": f"{median_size:,.0f} m\u00b2", "icon": "📐"},
    {"label": "Districts Covered", "value": str(district_count), "icon": "📍"},
], columns=st.columns(3, gap="medium"))

st.caption(
    "Lowest and highest values show the advertised asking-price range "
    "among listings matching the current filters."
)


# =========================================================
# MOST COMMON PRICE RANGE
# =========================================================

section_header(
    "Most Common Price Range",
    subtitle=(
        "Shows the asking-price range with the most listings "
        "for each selected property type."
    ),
)


if property_type_filter == "All":
    types_to_show = ["Condo", "Penthouse"]
else:
    types_to_show = [property_type_filter]


def _fmt_short_price(val):
    if val >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    if val >= 1_000:
        return f"${val / 1_000:.0f}K"
    return f"${val:,.0f}"


def get_common_price_range(data, property_type_name):
    type_df = data[
        data["property_type"] == property_type_name
    ].dropna(subset=["price_usd"]).copy()

    if type_df.empty:
        return None, None

    price_band_size = 25_000 if property_type_name == "Condo" else 50_000

    type_df["price_band_start"] = (
        type_df["price_usd"] // price_band_size * price_band_size
    )
    type_df["price_band_end"] = (
        type_df["price_band_start"] + price_band_size
    )

    band_summary = (
        type_df
        .groupby(["price_band_start", "price_band_end"])
        .size()
        .reset_index(name="listings")
    )

    band_summary["price_band_label"] = band_summary.apply(
        lambda row: (
            f"${row['price_band_start']:,.0f} \u2013 "
            f"${row['price_band_end']:,.0f}"
        ),
        axis=1,
    )

    band_summary["short_label"] = band_summary.apply(
        lambda row: (
            f"{_fmt_short_price(row['price_band_start'])}\u2013"
            f"{_fmt_short_price(row['price_band_end'])}"
        ),
        axis=1,
    )

    most_common_band = (
        band_summary
        .sort_values("listings", ascending=False)
        .iloc[0]
    )

    result = {
        "property_type": property_type_name,
        "total_listings": len(type_df),
        "band_start": most_common_band["price_band_start"],
        "band_end": most_common_band["price_band_end"],
        "band_count": int(most_common_band["listings"]),
        "band_share": most_common_band["listings"] / len(type_df) * 100,
    }

    return result, band_summary


common_range_results = []

for property_type_name in types_to_show:
    result, band_summary = get_common_price_range(filtered_df, property_type_name)
    if result is not None:
        common_range_results.append((result, band_summary))


if not common_range_results:
    st.info("No listings are available for this section with the current filters.")
else:

    range_columns = st.columns(len(common_range_results), gap="large")

    for column, (result, band_summary) in zip(range_columns, common_range_results):

        ptype = result["property_type"]
        icon = "🏢" if ptype == "Condo" else "🏡"

        with column:
            with st.container(border=True):
                st.markdown(f"### {icon} {ptype}")

                st.caption("MOST COMMON ASKING-PRICE RANGE")

                st.markdown(
                    f"## ${result['band_start']:,.0f} \u2013 ${result['band_end']:,.0f}"
                )

                range_metric1, range_metric2 = st.columns(2)

                with range_metric1:
                    st.metric("Listings in Range", f"{result['band_count']:,}")

                with range_metric2:
                    st.metric("Share", f"{result['band_share']:.1f}%")

                st.caption(
                    f"{result['band_count']:,} of {result['total_listings']:,} "
                    f"{ptype} listings fall within this price range."
                )

                if result["total_listings"] < 5:
                    st.warning(
                        "Very few listings match the current filters. "
                        "This range is descriptive only and should not "
                        "be treated as a market trend."
                    )
                elif result["total_listings"] < 20:
                    st.warning(
                        "This result is based on a small number of listings, "
                        "so interpret the price concentration carefully."
                    )


# =========================================================
# COMMON PRICE RANGE CHARTS
# =========================================================

for result, band_summary in common_range_results:

    if result["total_listings"] < 5:
        continue

    ptype = result["property_type"]

    st.markdown(f"#### {ptype} Price Distribution")

    top_price_bands = (
        band_summary
        .sort_values("listings", ascending=False)
        .head(8)
        .sort_values("price_band_start", ascending=True)
        .copy()
    )

    short_label_order = top_price_bands["short_label"].tolist()

    common_price_chart = (
        alt.Chart(top_price_bands)
        .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
        .encode(
            x=alt.X(
                "short_label:N",
                title=f"{ptype} Asking-Price Range",
                sort=short_label_order,
                axis=alt.Axis(
                    labelAngle=0,
                    labelFontSize=12,
                    titleFontSize=13,
                    titlePadding=12,
                ),
            ),
            y=alt.Y(
                "listings:Q",
                title="Number of Listings",
                axis=alt.Axis(tickMinStep=1),
            ),
            tooltip=[
                alt.Tooltip("price_band_label:N", title="Price Range"),
                alt.Tooltip("listings:Q", title="Listings", format=","),
            ],
        )
        .properties(height=380)
    )

    bar_text = (
        alt.Chart(top_price_bands)
        .mark_text(
            dy=-8,
            fontSize=12,
            fontWeight=600,
            color="#1E293B",
        )
        .encode(
            x=alt.X("short_label:N", sort=short_label_order),
            y=alt.Y("listings:Q"),
            text=alt.Text("listings:Q", format=","),
        )
    )

    combined = (common_price_chart + bar_text).configure_view(strokeWidth=0)

    st.altair_chart(combined, width="stretch")


st.info(
    "The most common price range shows where advertised listings are most "
    "concentrated. It does not represent an official property valuation."
)


# =========================================================
# DISTRICT ANALYSIS
# =========================================================

district_summary = (
    filtered_df
    .dropna(subset=["district", "price_usd"])
    .groupby("district")
    .agg(
        listings=("price_usd", "size"),
        median_price=("price_usd", "median"),
        median_price_per_m2=("price_per_m2", "median"),
    )
    .reset_index()
    .sort_values("median_price", ascending=False)
)


# =========================================================
# MEDIAN ASKING PRICE BY DISTRICT
# =========================================================

section_header(
    "Median Asking Price by District",
    subtitle="Typical advertised asking price by district. Only districts with at least 20 matching listings are shown.",
)

district_price_chart_df = (
    district_summary[district_summary["listings"] >= 20]
    .copy()
    .sort_values("median_price", ascending=True)
)

if district_price_chart_df.empty:
    st.info(
        "There are not enough listings for a reliable district "
        "asking-price comparison with the current filters."
    )
else:
    district_price_chart = (
        alt.Chart(district_price_chart_df)
        .mark_bar(cornerRadiusEnd=5)
        .encode(
            y=alt.Y("district:N", sort=None, title=None),
            x=alt.X(
                "median_price:Q",
                title="Median Asking Price (USD)",
                axis=alt.Axis(format="$,.0f"),
            ),
            tooltip=[
                alt.Tooltip("district:N", title="District"),
                alt.Tooltip("listings:Q", title="Listings", format=","),
                alt.Tooltip("median_price:Q", title="Median Price", format="$,.0f"),
                alt.Tooltip("median_price_per_m2:Q", title="Median Price / m\u00b2", format="$,.0f"),
            ],
        )
        .properties(height=400)
    )

    st.altair_chart(district_price_chart, width="stretch")


# =========================================================
# MEDIAN PRICE PER M2 BY DISTRICT
# =========================================================

section_header(
    "Median Price per m\u00b2 by District",
    subtitle="Compares the typical advertised price per square meter across districts.",
)

district_m2_chart_df = (
    district_summary[district_summary["listings"] >= 20]
    .copy()
    .sort_values("median_price_per_m2", ascending=True)
)

if district_m2_chart_df.empty:
    st.info(
        "There are not enough listings for a reliable district "
        "price-per-m\u00b2 comparison with the current filters."
    )
else:
    district_m2_chart = (
        alt.Chart(district_m2_chart_df)
        .mark_bar(cornerRadiusEnd=5)
        .encode(
            y=alt.Y("district:N", sort=None, title=None),
            x=alt.X(
                "median_price_per_m2:Q",
                title="Median Price per m\u00b2 (USD)",
                axis=alt.Axis(format="$,.0f"),
            ),
            tooltip=[
                alt.Tooltip("district:N", title="District"),
                alt.Tooltip("listings:Q", title="Listings", format=","),
                alt.Tooltip("median_price_per_m2:Q", title="Median Price / m\u00b2", format="$,.0f"),
                alt.Tooltip("median_price:Q", title="Median Asking Price", format="$,.0f"),
            ],
        )
        .properties(height=400)
    )

    st.altair_chart(district_m2_chart, width="stretch")


# =========================================================
# DISTRICT DETAILS TABLE
# =========================================================

section_header(
    "District Details",
    subtitle="Detailed statistics for districts matching the current filters.",
)

display_district_summary = district_summary.rename(columns={
    "district": "District",
    "listings": "Listings",
    "median_price": "Median Asking Price",
    "median_price_per_m2": "Median Price / m\u00b2",
})

st.dataframe(
    display_district_summary,
    hide_index=True,
    column_config={
        "Listings": st.column_config.NumberColumn(format="%d"),
        "Median Asking Price": st.column_config.NumberColumn(format="$%.0f"),
        "Median Price / m\u00b2": st.column_config.NumberColumn(format="$%.0f"),
    },
)


# =========================================================
# ASKING PRICE DISTRIBUTION
# =========================================================

section_header(
    "Asking Price Distribution",
    subtitle="Shows how advertised prices are spread out for the selected market.",
)

if len(filtered_df) < 5:

    st.info(
        "Only a few listings match the current filters. "
        "A price-distribution chart is not shown."
    )

else:

    price_99 = filtered_df["price_usd"].quantile(0.99)

    price_distribution_df = (
        filtered_df[filtered_df["price_usd"] <= price_99]
        .dropna(subset=["price_usd"])
        .copy()
    )

    distribution_median_price = filtered_df["price_usd"].median()

    histogram = (
        alt.Chart(price_distribution_df)
        .mark_bar(opacity=0.8)
        .encode(
            x=alt.X(
                "price_usd:Q",
                bin=alt.Bin(maxbins=40),
                title="Advertised Asking Price (USD)",
                axis=alt.Axis(format="$,.0f"),
            ),
            y=alt.Y("count():Q", title="Number of Listings"),
            tooltip=[
                alt.Tooltip("count():Q", title="Listings"),
            ],
        )
    )

    median_data = pd.DataFrame({"median_price": [distribution_median_price]})

    median_rule = (
        alt.Chart(median_data)
        .mark_rule(strokeWidth=2)
        .encode(x=alt.X("median_price:Q"))
    )

    median_label_data = pd.DataFrame({
        "median_price": [distribution_median_price],
        "label": [f"Median: ${distribution_median_price:,.0f}"],
    })

    median_label = (
        alt.Chart(median_label_data)
        .mark_text(align="left", dx=6, dy=-8, fontSize=12)
        .encode(
            x=alt.X("median_price:Q"),
            y=alt.value(10),
            text=alt.Text("label:N"),
        )
    )

    price_distribution_chart = (
        histogram + median_rule + median_label
    ).properties(height=400)

    st.altair_chart(price_distribution_chart, width="stretch")

    st.info(
        "Most advertised properties are concentrated in the lower and middle "
        "price ranges, while a smaller number of luxury properties extend above "
        "the typical market price."
    )


# =========================================================
# PROPERTY TYPE ANALYSIS
# =========================================================

if property_type_filter == "All":
    section_header(
        "Condo vs Penthouse",
        subtitle="Compare typical advertised prices, property sizes, and price per square meter.",
    )
else:
    section_header(
        f"{property_type_filter} Market Summary",
        subtitle=f"Typical advertised pricing and characteristics for {property_type_filter} listings.",
    )


property_type_summary = (
    filtered_df
    .dropna(subset=["property_type"])
    .groupby("property_type")
    .agg(
        listings=("price_usd", "size"),
        median_price=("price_usd", "median"),
        median_size=("size_m2", "median"),
        median_price_per_m2=("price_per_m2", "median"),
    )
    .reset_index()
)


if not property_type_summary.empty:

    type_columns = st.columns(len(property_type_summary), gap="large")

    for column, (_, row) in zip(type_columns, property_type_summary.iterrows()):

        ptype_name = row["property_type"]
        icon = "🏢" if ptype_name == "Condo" else "🏡"
        badge_color = "blue" if ptype_name == "Condo" else "violet"

        with column:
            with st.container(border=True, horizontal_alignment="center"):

                st.badge(
                    ptype_name,
                    icon=icon,
                    color=badge_color,
                )

                st.space("small")

                st.caption("MEDIAN ASKING PRICE")
                st.markdown(f"# ${row['median_price']:,.0f}")

                st.caption(
                    f"Based on {int(row['listings']):,} matching {ptype_name} listings."
                )

                st.space("medium")

                measure_col1, measure_col2 = st.columns(2, gap="medium")

                with measure_col1:
                    with st.container(border=True, horizontal_alignment="center"):
                        st.caption("Median size")
                        st.markdown(f"**{row['median_size']:,.0f} m\u00b2**")

                with measure_col2:
                    with st.container(border=True, horizontal_alignment="center"):
                        st.caption("Price per m\u00b2")
                        st.markdown(f"**${row['median_price_per_m2']:,.0f}**")


if len(filtered_df) >= 5:

    property_type_price_chart = (
        alt.Chart(property_type_summary)
        .mark_bar(cornerRadiusEnd=6, size=70)
        .encode(
            x=alt.X("property_type:N", title=None),
            y=alt.Y(
                "median_price:Q",
                title="Median Asking Price (USD)",
                axis=alt.Axis(format="$,.0f"),
            ),
            tooltip=[
                alt.Tooltip("property_type:N", title="Property Type"),
                alt.Tooltip("listings:Q", title="Listings", format=","),
                alt.Tooltip("median_price:Q", title="Median Asking Price", format="$,.0f"),
                alt.Tooltip("median_size:Q", title="Median Size", format=".0f"),
                alt.Tooltip("median_price_per_m2:Q", title="Median Price / m\u00b2", format="$,.0f"),
            ],
        )
        .properties(height=350)
    )

    st.altair_chart(property_type_price_chart, width="stretch")


if property_type_filter == "All" and len(filtered_df) >= 20:
    st.info(
        "Penthouses typically have higher asking prices and larger property "
        "sizes than Condos. They also tend to have a higher advertised price "
        "per square meter."
    )


# =========================================================
# BEDROOM & BATHROOM ANALYSIS
# =========================================================

section_header(
    "Bedroom & Bathroom Analysis",
    subtitle="Explore how advertised asking prices vary with the number of bedrooms and bathrooms.",
)


total_filtered_listings = len(filtered_df)


if total_filtered_listings < 5:

    st.warning(
        f"Only {total_filtered_listings} listing"
        f"{'s' if total_filtered_listings != 1 else ''} "
        "match the current filters."
    )

    typical_bedrooms = filtered_df["bedrooms"].median()
    typical_bathrooms = filtered_df["bathrooms"].median()
    typical_size = filtered_df["size_m2"].median()
    typical_floor = filtered_df["unit_floor"].median()

    def fmt(val, suffix=""):
        if pd.isna(val):
            return "Unknown"
        return f"{val:,.0f}{suffix}"

    def fmt_bed(val):
        if pd.isna(val):
            return "Unknown"
        if val == 0:
            return "Studio"
        return f"{val:.0f}"

    profile_col1, profile_col2, profile_col3, profile_col4 = st.columns(
        4, gap="large"
    )

    with profile_col1:
        st.metric("Bedrooms", fmt_bed(typical_bedrooms))
    with profile_col2:
        st.metric("Bathrooms", fmt(typical_bathrooms))
    with profile_col3:
        st.metric("Size", fmt(typical_size, " m\u00b2"))
    with profile_col4:
        st.metric("Floor Level", fmt(typical_floor))

    st.info(
        "These characteristics describe only the small number of listings "
        "matching the filters and should not be interpreted as a wider market trend."
    )

else:

    if total_filtered_listings >= 100:
        minimum_group_size = 20
    elif total_filtered_listings >= 20:
        minimum_group_size = 5
    else:
        minimum_group_size = 1

    if total_filtered_listings < 20:
        st.warning(
            f"Only {total_filtered_listings} listings match the current filters. "
            "Results are descriptive and may not represent the wider market."
        )

    bedroom_summary = (
        filtered_df
        .dropna(subset=["bedrooms", "price_usd"])
        .groupby("bedrooms")
        .agg(
            listings=("price_usd", "size"),
            median_price=("price_usd", "median"),
        )
        .reset_index()
    )

    bedroom_summary = bedroom_summary[
        bedroom_summary["listings"] >= minimum_group_size
    ].copy()

    if not bedroom_summary.empty:
        bedroom_summary["bedroom_label"] = (
            bedroom_summary["bedrooms"]
            .astype(int)
            .apply(lambda v: "Studio" if v == 0 else str(v))
        )
        bedroom_order = (
            bedroom_summary
            .sort_values("bedrooms")["bedroom_label"]
            .tolist()
        )

    bathroom_summary = (
        filtered_df
        .dropna(subset=["bathrooms", "price_usd"])
        .groupby("bathrooms")
        .agg(
            listings=("price_usd", "size"),
            median_price=("price_usd", "median"),
        )
        .reset_index()
    )

    bathroom_summary = bathroom_summary[
        bathroom_summary["listings"] >= minimum_group_size
    ].copy()

    if not bathroom_summary.empty:
        bathroom_summary["bathroom_label"] = (
            bathroom_summary["bathrooms"].astype(int).astype(str)
        )
        bathroom_order = (
            bathroom_summary
            .sort_values("bathrooms")["bathroom_label"]
            .tolist()
        )

    bed_col, bath_col = st.columns(2, gap="large")

    with bed_col:
        st.markdown("#### 🛏 Median Price by Bedrooms")

        if bedroom_summary.empty:
            st.info("Bedroom information is not available for enough of the matching listings.")
        else:
            bedroom_chart = (
                alt.Chart(bedroom_summary)
                .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
                .encode(
                    x=alt.X("bedroom_label:N", title="Bedrooms", sort=bedroom_order),
                    y=alt.Y(
                        "median_price:Q",
                        title="Median Asking Price (USD)",
                        axis=alt.Axis(format="$,.0f"),
                    ),
                    tooltip=[
                        alt.Tooltip("bedroom_label:N", title="Bedrooms"),
                        alt.Tooltip("listings:Q", title="Listings", format=","),
                        alt.Tooltip("median_price:Q", title="Median Asking Price", format="$,.0f"),
                    ],
                )
                .properties(height=350)
            )

            st.altair_chart(bedroom_chart, width="stretch")

    with bath_col:
        st.markdown("#### 🚿 Median Price by Bathrooms")

        if bathroom_summary.empty:
            st.info("Bathroom information is not available for enough of the matching listings.")
        else:
            bathroom_chart = (
                alt.Chart(bathroom_summary)
                .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
                .encode(
                    x=alt.X("bathroom_label:N", title="Bathrooms", sort=bathroom_order),
                    y=alt.Y(
                        "median_price:Q",
                        title="Median Asking Price (USD)",
                        axis=alt.Axis(format="$,.0f"),
                    ),
                    tooltip=[
                        alt.Tooltip("bathroom_label:N", title="Bathrooms"),
                        alt.Tooltip("listings:Q", title="Listings", format=","),
                        alt.Tooltip("median_price:Q", title="Median Asking Price", format="$,.0f"),
                    ],
                )
                .properties(height=350)
            )

            st.altair_chart(bathroom_chart, width="stretch")

    st.info(
        "Properties with more bedrooms and bathrooms generally have higher asking prices. "
        "However, room count is only one factor \u2014 property size, location, floor level, "
        "and property type also affect price."
    )


# =========================================================
# FOOTER
# =========================================================

disclaimer(
    "Market Insights are based on advertised property listing data collected "
    "for the PP PropertyLens project. They describe listing patterns and should "
    "not be interpreted as official transaction-price statistics."
)
