import streamlit as st
import pandas as pd
import altair as alt
from pathlib import Path

from components.styles import inject_global_css
from components.ui import (
    hero_banner,
    section_header,
    metric_cards,
    recommendation_card,
    disclaimer,
)


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Budget Advisor | PP PropertyLens",
    page_icon="💰",
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
    title="Budget Advisor",
    description=(
        "Enter your property budget and explore the types of "
        "Condo and Penthouse listings, districts, and typical "
        "property characteristics available within that budget."
    ),
    caption=(
        "Recommendations are based on advertised listings in "
        "the PP PropertyLens dataset and are provided for "
        "market comparison, not financial or investment advice."
    ),
)


# =========================================================
# YOUR BUDGET
# =========================================================

section_header(
    "Your Budget",
    subtitle=(
        "Tell PropertyLens how much you plan to spend and "
        "optionally narrow the search by property type or district."
    ),
)


with st.container(border=True):

    input_col1, input_col2 = st.columns(2, gap="large")

    with input_col1:

        budget = st.number_input(
            "Maximum Budget (USD)",
            min_value=int(df["price_usd"].min()),
            max_value=int(df["price_usd"].max()),
            value=100_000,
            step=10_000,
            format="%d",
            key="advisor_budget",
        )

    with input_col2:

        property_type_filter = st.segmented_control(
            "Property Type",
            options=["All", "Condo", "Penthouse"],
            default="All",
            selection_mode="single",
            key="advisor_property_type",
            width="stretch",
        )

    district_options = sorted(
        df["district"].dropna().unique()
    )

    district_filter = st.multiselect(
        "Preferred Districts (Optional)",
        options=district_options,
        default=[],
        placeholder="All districts",
        key="advisor_districts",
    )


# =========================================================
# SELECTED MARKET
# =========================================================

selected_market_df = df.copy()

if property_type_filter != "All":
    selected_market_df = selected_market_df[
        selected_market_df["property_type"] == property_type_filter
    ].copy()

if district_filter:
    selected_market_df = selected_market_df[
        selected_market_df["district"].isin(district_filter)
    ].copy()


if selected_market_df.empty:
    st.warning(
        "No listings are available for the selected "
        "property type and district preferences."
    )
    st.stop()


# =========================================================
# AFFORDABLE LISTINGS
# =========================================================

affordable_df = selected_market_df[
    selected_market_df["price_usd"] <= budget
].copy()


if affordable_df.empty:

    st.warning(
        "No listings in the current dataset match this "
        "budget and the selected preferences."
    )

    closest_above = selected_market_df[
        selected_market_df["price_usd"] > budget
    ].copy()

    if not closest_above.empty:

        closest_above["amount_above_budget"] = (
            closest_above["price_usd"] - budget
        )

        closest_above = (
            closest_above
            .sort_values("amount_above_budget", ascending=True)
            .head(10)
        )

        section_header("Closest Options Above Your Budget")

        st.caption(
            "These are the nearest advertised listings "
            "above your selected maximum budget."
        )

        above_columns = [
            col
            for col in [
                "title", "property_type", "district",
                "size_m2", "bedrooms", "bathrooms",
                "unit_floor", "price_usd", "source",
                "amount_above_budget",
            ]
            if col in closest_above.columns
        ]

        display_above = closest_above[above_columns].copy()

        display_above = display_above.rename(columns={
            "title": "Listing",
            "property_type": "Property Type",
            "district": "District",
            "size_m2": "Size (m\u00b2)",
            "bedrooms": "Bedrooms",
            "bathrooms": "Bathrooms",
            "unit_floor": "Floor",
            "price_usd": "Asking Price",
            "source": "Source",
            "amount_above_budget": "Above Budget",
        })

        st.dataframe(
            display_above,
            hide_index=True,
            column_config={
                "Asking Price": st.column_config.NumberColumn(format="$%.0f"),
                "Above Budget": st.column_config.NumberColumn(format="$%.0f"),
                "Size (m\u00b2)": st.column_config.NumberColumn(format="%.0f"),
                "Bedrooms": st.column_config.NumberColumn(format="%.0f"),
                "Bathrooms": st.column_config.NumberColumn(format="%.0f"),
                "Floor": st.column_config.NumberColumn(format="%.0f"),
            },
        )

    st.stop()


# =========================================================
# BUDGET SUMMARY
# =========================================================

section_header("Budget Summary")

market_coverage = (
    len(affordable_df) / len(selected_market_df) * 100
)

median_matching_price = affordable_df["price_usd"].median()
highest_affordable_price = affordable_df["price_usd"].max()

budget_percentile = (
    (df["price_usd"] <= budget).mean() * 100
)

if budget_percentile < 25:
    budget_position = "Entry Market"
elif budget_percentile < 75:
    budget_position = "Mid Market"
elif budget_percentile < 95:
    budget_position = "Upper Market"
else:
    budget_position = "Luxury / High-End Market"


metric_cards([
    {"label": "Matching Listings", "value": f"{len(affordable_df):,}", "icon": "🏠"},
    {"label": "Your Budget", "value": f"${budget:,.0f}", "icon": "💰"},
    {"label": "Median Matching Price", "value": f"${median_matching_price:,.0f}", "icon": "💵"},
], columns=st.columns(3, gap="medium"))

st.markdown("")

metric_cards([
    {"label": "Highest Matching", "value": f"${highest_affordable_price:,.0f}", "icon": "📈"},
    {"label": "Market Coverage", "value": f"{market_coverage:.1f}%", "icon": "📊"},
    {"label": "Budget Position", "value": budget_position, "icon": "📶"},
], columns=st.columns(3, gap="medium"))


if budget_percentile >= 99:
    st.caption(
        "Your budget reaches the very top end of "
        "advertised prices in the PropertyLens dataset."
    )
else:
    st.caption(
        f"Your budget is higher than about "
        f"**{budget_percentile:.0f}%** of advertised "
        f"prices in the PropertyLens dataset."
    )

st.caption(
    f"**{market_coverage:.1f}%** of listings in your "
    "selected market are at or below your maximum budget."
)


# =========================================================
# RELEVANT BUDGET WINDOW
# =========================================================

target_lower_price = budget * 0.70

budget_window_df = affordable_df[
    affordable_df["price_usd"].between(target_lower_price, budget)
].copy()

if len(budget_window_df) >= 10:
    target_df = budget_window_df.copy()
    target_window_label = (
        f"listings between ${target_lower_price:,.0f} and ${budget:,.0f}"
    )
else:
    number_to_compare = min(30, len(affordable_df))
    target_df = (
        affordable_df
        .sort_values("price_usd", ascending=False)
        .head(number_to_compare)
        .copy()
    )
    comparison_low = target_df["price_usd"].min()
    target_window_label = (
        f"the {len(target_df):,} listings closest to your budget, "
        f"ranging from ${comparison_low:,.0f} to ${budget:,.0f}"
    )


if len(target_df) < 10:
    st.warning(
        "Only a few listings are available near this budget. "
        "The suggestions below are examples, not broad market trends."
    )


# =========================================================
# WHAT YOUR BUDGET TYPICALLY GETS
# =========================================================

section_header(
    "What Your Budget Typically Gets",
    subtitle=f"Typical property details based on {target_window_label}.",
)

typical_size = target_df["size_m2"].median()
typical_bedrooms = target_df["bedrooms"].median()
typical_bathrooms = target_df["bathrooms"].median()
typical_floor = target_df["unit_floor"].median()


def format_bedroom(val):
    if pd.isna(val):
        return "Unknown"
    if val == 0:
        return "Studio"
    return f"{val:.0f}"


def format_or_unknown(val, suffix=""):
    if pd.isna(val):
        return "Unknown"
    return f"{val:,.0f}{suffix}"


metric_cards([
    {"label": "Typical Size", "value": format_or_unknown(typical_size, " m\u00b2"), "icon": "📐"},
    {"label": "Typical Bedrooms", "value": format_bedroom(typical_bedrooms), "icon": "🛏"},
    {"label": "Typical Bathrooms", "value": format_or_unknown(typical_bathrooms), "icon": "🚿"},
    {"label": "Typical Floor", "value": format_or_unknown(typical_floor), "icon": "🏗"},
], columns=st.columns(4, gap="large"))


# =========================================================
# AVAILABLE MARKET WITHIN BUDGET
# =========================================================

if property_type_filter == "All":

    section_header(
        "Available Market Within Your Budget",
        subtitle=(
            "This section summarizes all listings at or below your budget. "
            "The section above focuses on properties closer to your budget."
        ),
    )

    type_summary = (
        affordable_df
        .dropna(subset=["property_type"])
        .groupby("property_type")
        .agg(
            listings=("price_usd", "size"),
            median_price=("price_usd", "median"),
            median_size=("size_m2", "median"),
            median_bedrooms=("bedrooms", "median"),
            median_bathrooms=("bathrooms", "median"),
        )
        .reset_index()
    )

    if not type_summary.empty:

        type_columns = st.columns(len(type_summary), gap="large")

        for column, (_, row) in zip(type_columns, type_summary.iterrows()):

            property_type_name = row["property_type"]
            icon = "🏢" if property_type_name == "Condo" else "🏡"

            with column:
                with st.container(border=True):
                    st.markdown(
                        f"### {icon} {property_type_name}"
                    )

                    st.metric(
                        "Available Listings",
                        f"{int(row['listings']):,}",
                    )

                    st.metric(
                        "Median Asking Price",
                        f"${row['median_price']:,.0f}",
                    )

                    type_detail_col1, type_detail_col2 = st.columns(2, gap="medium")

                    with type_detail_col1:
                        st.caption("Typical size")
                        if pd.notna(row["median_size"]):
                            st.markdown(f"**{row['median_size']:,.0f} m\u00b2**")
                        else:
                            st.markdown("**Unknown**")

                    with type_detail_col2:
                        st.caption("Typical bedrooms")
                        st.markdown(f"**{format_bedroom(row['median_bedrooms'])}**")


# =========================================================
# DISTRICT RECOMMENDATIONS
# =========================================================

section_header(
    "Areas to Compare",
    subtitle=(
        "These areas are selected from properties near your budget and show "
        "different options for availability, space, and price."
    ),
)


district_profiles = (
    target_df
    .dropna(subset=["district"])
    .groupby("district")
    .agg(
        available_listings=("price_usd", "size"),
        typical_price=("price_usd", "median"),
        typical_size=("size_m2", "median"),
        typical_bedrooms=("bedrooms", "median"),
        typical_bathrooms=("bathrooms", "median"),
        typical_floor=("unit_floor", "median"),
    )
    .reset_index()
)


if len(target_df) >= 100:
    minimum_district_listings = 10
elif len(target_df) >= 30:
    minimum_district_listings = 5
else:
    minimum_district_listings = 1

district_profiles = district_profiles[
    district_profiles["available_listings"] >= minimum_district_listings
].copy()


recommendations = []

if not district_profiles.empty:

    most_options = (
        district_profiles
        .sort_values(["available_listings", "typical_price"], ascending=[False, False])
        .iloc[0]
    )
    recommendations.append(("Most Options", "🔍", most_options, "pp-rec-blue"))

    used_districts = {most_options["district"]}

    remaining_space_options = district_profiles[
        ~district_profiles["district"].isin(used_districts)
    ].copy()

    if not remaining_space_options.empty:
        more_space = (
            remaining_space_options
            .sort_values("typical_size", ascending=False)
            .iloc[0]
        )
        recommendations.append(("More Space", "📐", more_space, "pp-rec-green"))
        used_districts.add(more_space["district"])

    remaining_budget_options = district_profiles[
        ~district_profiles["district"].isin(used_districts)
    ].copy()

    if not remaining_budget_options.empty:
        remaining_budget_options["distance_to_budget"] = (
            budget - remaining_budget_options["typical_price"]
        ).abs()
        closest_budget = (
            remaining_budget_options
            .sort_values("distance_to_budget", ascending=True)
            .iloc[0]
        )
        recommendations.append(
            ("Closer to Your Budget", "🎯", closest_budget, "pp-rec-violet")
        )


if recommendations:

    rec_cols = st.columns(len(recommendations), gap="large")

    for col_idx, (label, icon, row, accent) in enumerate(recommendations):

        bedroom_text = format_bedroom(row["typical_bedrooms"])

        metrics = [
            ("Typical Price", f"${row['typical_price']:,.0f}"),
            ("Listings", f"{int(row['available_listings']):,}"),
        ]

        if pd.notna(row["typical_size"]):
            metrics.append(("Typical Size", f"{row['typical_size']:,.0f} m\u00b2"))

        if pd.notna(row["typical_bedrooms"]):
            metrics.append(("Bedrooms", bedroom_text))

        if pd.notna(row["typical_bathrooms"]):
            metrics.append(("Bathrooms", f"{row['typical_bathrooms']:.0f}"))

        if pd.notna(row["typical_floor"]):
            metrics.append(("Floor", f"{row['typical_floor']:.0f}"))

        with rec_cols[col_idx]:
            st.markdown(
                recommendation_card(
                    accent_class=accent,
                    title=label,
                    district=row["district"],
                    metrics=metrics,
                ),
                unsafe_allow_html=True,
            )

else:
    st.info(
        "There are not enough district-level listings near this budget "
        "to create useful area comparisons."
    )


# =========================================================
# DISTRICT COMPARISON CHART
# =========================================================

if not district_profiles.empty:

    section_header(
        "Budget Options by District",
        subtitle="Number of properties near your budget in each area that has enough listings.",
    )

    district_chart_df = (
        district_profiles
        .sort_values("available_listings", ascending=True)
        .copy()
    )

    district_chart = (
        alt.Chart(district_chart_df)
        .mark_bar(cornerRadiusEnd=5)
        .encode(
            y=alt.Y("district:N", sort=None, title=None),
            x=alt.X(
                "available_listings:Q",
                title="Listings Near Your Budget",
                axis=alt.Axis(format="d", tickMinStep=1),
            ),
            tooltip=[
                alt.Tooltip("district:N", title="District"),
                alt.Tooltip("available_listings:Q", title="Listings", format=","),
                alt.Tooltip("typical_price:Q", title="Typical Price", format="$,.0f"),
                alt.Tooltip("typical_size:Q", title="Typical Size", format=".0f"),
            ],
        )
        .properties(height=380)
    )

    st.altair_chart(district_chart, use_container_width=True)


# =========================================================
# LISTINGS TO COMPARE
# =========================================================

section_header(
    "Listings to Compare",
    subtitle="These are the closest listings to your budget that are still within it.",
)

comparables = affordable_df.copy()
comparables["budget_remaining"] = budget - comparables["price_usd"]

comparables = (
    comparables
    .sort_values(["budget_remaining", "price_usd"], ascending=[True, False])
    .head(10)
)

available_columns = [
    col
    for col in [
        "title", "property_type", "district", "size_m2",
        "bedrooms", "bathrooms", "unit_floor", "price_usd",
        "source", "budget_remaining",
    ]
    if col in comparables.columns
]

comparables_display = comparables[available_columns].copy()

comparables_display = comparables_display.rename(columns={
    "title": "Listing",
    "property_type": "Property Type",
    "district": "District",
    "size_m2": "Size (m\u00b2)",
    "bedrooms": "Bedrooms",
    "bathrooms": "Bathrooms",
    "unit_floor": "Floor",
    "price_usd": "Asking Price",
    "source": "Source",
    "budget_remaining": "Budget Remaining",
})

st.dataframe(
    comparables_display,
    hide_index=True,
    column_config={
        "Asking Price": st.column_config.NumberColumn(format="$%.0f"),
        "Budget Remaining": st.column_config.NumberColumn(format="$%.0f"),
        "Size (m\u00b2)": st.column_config.NumberColumn(format="%.0f"),
        "Bedrooms": st.column_config.NumberColumn(format="%.0f"),
        "Bathrooms": st.column_config.NumberColumn(format="%.0f"),
        "Floor": st.column_config.NumberColumn(format="%.0f"),
    },
)


# =========================================================
# DISCLAIMER
# =========================================================

disclaimer(
    "Budget Advisor results are based on advertised property listings "
    "collected for PP PropertyLens. They are intended for market comparison "
    "and decision support only and are not financial advice, purchase "
    "recommendations, or official property valuations."
)
