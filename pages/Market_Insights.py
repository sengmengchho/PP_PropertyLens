import streamlit as st
import pandas as pd
import altair as alt
from pathlib import Path


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Market Insights | PP PropertyLens",
    page_icon=":material/insights:",
    layout="wide",
)


# =========================================================
# PATHS
# =========================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)


# =========================================================
# LOAD DATA
# =========================================================

DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "gold"
    / "property_listings_geocoded.csv"
)


@st.cache_data
def load_data():

    return pd.read_csv(
        DATA_PATH
    )


df = load_data()


# =========================================================
# HEADER
# =========================================================

st.title(
    ":material/insights: Phnom Penh Market Insights"
)

st.write(
    "Explore advertised Condo and Penthouse "
    "asking-price patterns across Phnom Penh."
)

st.divider()


# =========================================================
# MARKET FILTERS
# =========================================================

st.subheader(
    "Market Filters"
)

st.caption(
    "Use the filters below to explore specific parts "
    "of the Phnom Penh property market."
)


with st.container(
    border=True
):

    # =====================================================
    # ROW 1
    # =====================================================

    filter_col1, filter_col2 = st.columns(
        [1, 2],
        gap="large",
    )


    # -----------------------------------------------------
    # PROPERTY TYPE
    # -----------------------------------------------------

    with filter_col1:

        property_type_filter = (
            st.segmented_control(
                "Property Type",
                options=[
                    "All",
                    "Condo",
                    "Penthouse",
                ],
                default="All",
                selection_mode="single",
                key="market_property_type",
                width="stretch",
            )
        )


    # -----------------------------------------------------
    # DISTRICT
    # -----------------------------------------------------

    with filter_col2:

        district_options = sorted(
            df[
                "district"
            ]
            .dropna()
            .unique()
        )


        district_filter = (
            st.multiselect(
                "District",
                options=district_options,
                default=[],
                placeholder="All districts",
                key="market_districts",
            )
        )


    # =====================================================
    # PRICE RANGE
    # =====================================================

    st.markdown("")


    max_price = int(
        df[
            "price_usd"
        ].max()
    )


    price_range = st.slider(
        "Asking Price Range",
        min_value=0,
        max_value=max_price,
        value=(
            0,
            max_price,
        ),
        step=10_000,
        format="$%d",
        key="market_price_range",
    )


# =========================================================
# APPLY FILTERS
# =========================================================

filtered_df = df.copy()


# ---------------------------------------------------------
# PROPERTY TYPE FILTER
# ---------------------------------------------------------

if (
    property_type_filter
    != "All"
):

    filtered_df = (
        filtered_df[
            filtered_df[
                "property_type"
            ]
            == property_type_filter
        ]
        .copy()
    )


# ---------------------------------------------------------
# DISTRICT FILTER
# ---------------------------------------------------------

if district_filter:

    filtered_df = (
        filtered_df[
            filtered_df[
                "district"
            ].isin(
                district_filter
            )
        ]
        .copy()
    )


# ---------------------------------------------------------
# PRICE FILTER
# ---------------------------------------------------------

filtered_df = (
    filtered_df[
        filtered_df[
            "price_usd"
        ].between(
            price_range[0],
            price_range[1],
        )
    ]
    .copy()
)


# =========================================================
# EMPTY RESULT CHECK
# =========================================================

if filtered_df.empty:

    st.warning(
        "No listings match the selected filters. "
        "Try expanding the district or price range."
    )

    st.stop()


# =========================================================
# FILTER RESULT COUNT
# =========================================================

st.caption(
    f"Showing **{len(filtered_df):,} listings** "
    "for the selected market filters."
)


# =========================================================
# MARKET OVERVIEW
# =========================================================

st.subheader(
    "Market Overview"
)


overview_col1, overview_col2, (
    overview_col3
), overview_col4 = st.columns(
    4
)


# ---------------------------------------------------------
# LISTINGS
# ---------------------------------------------------------

with overview_col1:

    st.metric(
        "Listings",
        f"{len(filtered_df):,}",
    )


# ---------------------------------------------------------
# MEDIAN PRICE
# ---------------------------------------------------------

with overview_col2:

    st.metric(
        "Median Asking Price",
        (
            f"${filtered_df['price_usd'].median():,.0f}"
        ),
    )


# ---------------------------------------------------------
# MEDIAN SIZE
# ---------------------------------------------------------

with overview_col3:

    st.metric(
        "Median Size",
        (
            f"{filtered_df['size_m2'].median():,.0f} m²"
        ),
    )


# ---------------------------------------------------------
# DISTRICTS
# ---------------------------------------------------------

with overview_col4:

    st.metric(
        "Districts Covered",
        (
            filtered_df[
                "district"
            ].nunique()
        ),
    )


st.divider()


# =========================================================
# DISTRICT ANALYSIS
# =========================================================

district_summary = (
    filtered_df
    .dropna(
        subset=[
            "district",
            "price_usd",
        ]
    )
    .groupby(
        "district"
    )
    .agg(
        listings=(
            "price_usd",
            "size",
        ),

        median_price=(
            "price_usd",
            "median",
        ),

        median_price_per_m2=(
            "price_per_m2",
            "median",
        ),
    )
    .reset_index()
    .sort_values(
        "median_price",
        ascending=False,
    )
)


# =========================================================
# MEDIAN ASKING PRICE BY DISTRICT
# =========================================================

st.subheader(
    "Median Asking Price by District"
)

st.caption(
    "Typical advertised asking price by district. "
    "Only districts with at least 20 matching listings "
    "are shown to make the comparison more reliable."
)


district_price_chart_df = (
    district_summary[
        district_summary[
            "listings"
        ] >= 20
    ]
    .copy()
    .sort_values(
        "median_price",
        ascending=True,
    )
)


if district_price_chart_df.empty:

    st.info(
        "There are not enough listings for a reliable "
        "district asking-price comparison with the "
        "current filters."
    )

else:

    district_price_chart = (
        alt.Chart(
            district_price_chart_df
        )
        .mark_bar(
            cornerRadiusEnd=5
        )
        .encode(
            y=alt.Y(
                "district:N",
                sort=None,
                title=None,
            ),

            x=alt.X(
                "median_price:Q",
                title=(
                    "Median Asking Price (USD)"
                ),
                axis=alt.Axis(
                    format="$,.0f",
                ),
            ),

            tooltip=[
                alt.Tooltip(
                    "district:N",
                    title="District",
                ),

                alt.Tooltip(
                    "listings:Q",
                    title="Listings",
                    format=",",
                ),

                alt.Tooltip(
                    "median_price:Q",
                    title="Median Price",
                    format="$,.0f",
                ),

                alt.Tooltip(
                    "median_price_per_m2:Q",
                    title="Median Price / m²",
                    format="$,.0f",
                ),
            ],
        )
        .properties(
            height=420,
        )
    )


    st.altair_chart(
        district_price_chart,
    )


# =========================================================
# MEDIAN PRICE PER M² BY DISTRICT
# =========================================================

st.subheader(
    "Median Price per m² by District"
)

st.caption(
    "Compares the typical advertised price per square "
    "meter across districts. Only districts with at "
    "least 20 matching listings are shown."
)


district_m2_chart_df = (
    district_summary[
        district_summary[
            "listings"
        ] >= 20
    ]
    .copy()
    .sort_values(
        "median_price_per_m2",
        ascending=True,
    )
)


if district_m2_chart_df.empty:

    st.info(
        "There are not enough listings for a reliable "
        "district price-per-m² comparison with the "
        "current filters."
    )

else:

    district_m2_chart = (
        alt.Chart(
            district_m2_chart_df
        )
        .mark_bar(
            cornerRadiusEnd=5
        )
        .encode(
            y=alt.Y(
                "district:N",
                sort=None,
                title=None,
            ),

            x=alt.X(
                "median_price_per_m2:Q",
                title=(
                    "Median Price per m² (USD)"
                ),
                axis=alt.Axis(
                    format="$,.0f",
                ),
            ),

            tooltip=[
                alt.Tooltip(
                    "district:N",
                    title="District",
                ),

                alt.Tooltip(
                    "listings:Q",
                    title="Listings",
                    format=",",
                ),

                alt.Tooltip(
                    "median_price_per_m2:Q",
                    title="Median Price / m²",
                    format="$,.0f",
                ),

                alt.Tooltip(
                    "median_price:Q",
                    title="Median Asking Price",
                    format="$,.0f",
                ),
            ],
        )
        .properties(
            height=420,
        )
    )


    st.altair_chart(
        district_m2_chart,
    )


# =========================================================
# DISTRICT DETAILS TABLE
# =========================================================

st.subheader(
    "District Details"
)

st.caption(
    "Detailed market statistics for all districts "
    "matching the selected filters, including districts "
    "with smaller sample sizes."
)


display_district_summary = (
    district_summary.rename(
        columns={
            "district":
                "District",

            "listings":
                "Listings",

            "median_price":
                "Median Asking Price",

            "median_price_per_m2":
                "Median Price / m²",
        }
    )
)


st.dataframe(
    display_district_summary,
    hide_index=True,
    column_config={
        "Listings":
            st.column_config.NumberColumn(
                format="%d",
            ),

        "Median Asking Price":
            st.column_config.NumberColumn(
                format="$%.0f",
            ),

        "Median Price / m²":
            st.column_config.NumberColumn(
                format="$%.0f",
            ),
    },
)


st.divider()


# =========================================================
# ASKING PRICE DISTRIBUTION
# =========================================================

st.subheader(
    "Asking Price Distribution"
)

st.caption(
    "Shows how advertised property prices are distributed "
    "for the selected market. The chart displays up to "
    "the 99th percentile so a small number of luxury "
    "listings do not compress the main distribution."
)


# =========================================================
# 99TH PERCENTILE — DISPLAY ONLY
# =========================================================

price_99 = (
    filtered_df[
        "price_usd"
    ]
    .quantile(
        0.99
    )
)


price_distribution_df = (
    filtered_df[
        filtered_df[
            "price_usd"
        ] <= price_99
    ]
    .dropna(
        subset=[
            "price_usd"
        ]
    )
    .copy()
)


median_price = (
    filtered_df[
        "price_usd"
    ]
    .median()
)


# =========================================================
# HISTOGRAM
# =========================================================

histogram = (
    alt.Chart(
        price_distribution_df
    )
    .mark_bar(
        opacity=0.8
    )
    .encode(
        x=alt.X(
            "price_usd:Q",
            bin=alt.Bin(
                maxbins=40
            ),
            title=(
                "Advertised Asking Price (USD)"
            ),
            axis=alt.Axis(
                format="$,.0f",
            ),
        ),

        y=alt.Y(
            "count():Q",
            title=(
                "Number of Listings"
            ),
        ),

        tooltip=[
            alt.Tooltip(
                "count():Q",
                title="Listings",
            ),
        ],
    )
)


# =========================================================
# MEDIAN LINE
# =========================================================

median_data = pd.DataFrame({
    "median_price": [
        median_price
    ]
})


median_rule = (
    alt.Chart(
        median_data
    )
    .mark_rule(
        strokeWidth=2
    )
    .encode(
        x=alt.X(
            "median_price:Q"
        )
    )
)


median_label_data = pd.DataFrame({
    "median_price": [
        median_price
    ],

    "label": [
        f"Median: ${median_price:,.0f}"
    ],
})


median_label = (
    alt.Chart(
        median_label_data
    )
    .mark_text(
        align="left",
        dx=6,
        dy=-8,
        fontSize=12,
    )
    .encode(
        x=alt.X(
            "median_price:Q"
        ),

        y=alt.value(
            10
        ),

        text=alt.Text(
            "label:N"
        ),
    )
)


price_distribution_chart = (
    histogram
    + median_rule
    + median_label
).properties(
    height=400,
)


st.altair_chart(
    price_distribution_chart,
)


st.info(
    "Most advertised properties are concentrated in "
    "the lower and middle price ranges, while a smaller "
    "number of luxury properties extend far above the "
    "typical market price."
)


st.divider()


# =========================================================
# PROPERTY TYPE ANALYSIS
# =========================================================

if (
    property_type_filter
    == "All"
):

    st.subheader(
        "Condo vs Penthouse"
    )

    st.caption(
        "Compare typical advertised prices, property sizes, "
        "and price per square meter between Condos and "
        "Penthouses."
    )

else:

    st.subheader(
        f"{property_type_filter} Market Summary"
    )

    st.caption(
        f"Typical advertised pricing and property "
        f"characteristics for {property_type_filter} "
        f"listings matching the selected filters."
    )


# =========================================================
# PROPERTY TYPE SUMMARY
# =========================================================

property_type_summary = (
    filtered_df
    .dropna(
        subset=[
            "property_type"
        ]
    )
    .groupby(
        "property_type"
    )
    .agg(
        listings=(
            "price_usd",
            "size",
        ),

        median_price=(
            "price_usd",
            "median",
        ),

        median_size=(
            "size_m2",
            "median",
        ),

        median_price_per_m2=(
            "price_per_m2",
            "median",
        ),
    )
    .reset_index()
)


# =========================================================
# PROPERTY TYPE CARDS
# =========================================================

if not property_type_summary.empty:

    type_columns = st.columns(
        len(
            property_type_summary
        ),
        gap="large",
    )


    for column, (_, row) in zip(
        type_columns,
        property_type_summary.iterrows(),
    ):

        property_type_name = (
            row[
                "property_type"
            ]
        )


        if (
            property_type_name
            == "Condo"
        ):

            icon = ":material/apartment:"

        else:

            icon = ":material/villa:"


        with column:

            with st.container(
                border=True,
                horizontal_alignment="center",
            ):

                st.badge(
                    property_type_name,
                    icon=icon,
                    color=(
                        "blue"
                        if property_type_name == "Condo"
                        else "violet"
                    ),
                )

                st.space("small")

                st.caption(
                    "MEDIAN ASKING PRICE"
                )

                st.markdown(
                    f"# ${row['median_price']:,.0f}"
                )

                st.caption(
                    f"Half the {int(row['listings']):,} "
                    "listings are priced above this line, "
                    "half below."
                )

                st.space("medium")

                measure_col1, measure_col2 = (
                    st.columns(
                        2,
                        gap="medium",
                    )
                )


                with measure_col1:

                    # -----------------------------------------
                    # MEDIAN SIZE
                    # -----------------------------------------

                    with st.container(
                        border=True,
                        horizontal_alignment="center",
                    ):

                        st.caption(
                            "Median size"
                        )

                        st.markdown(
                            f"**{row['median_size']:,.0f} m²**"
                        )


                with measure_col2:

                    # -----------------------------------------
                    # MEDIAN PRICE PER M2
                    # -----------------------------------------

                    with st.container(
                        border=True,
                        horizontal_alignment="center",
                    ):

                        st.caption(
                            "Price per m²"
                        )

                        st.markdown(
                            f"**${row['median_price_per_m2']:,.0f}**"
                        )


# =========================================================
# PROPERTY TYPE PRICE CHART
# =========================================================

if not property_type_summary.empty:

    property_type_price_chart = (
        alt.Chart(
            property_type_summary
        )
        .mark_bar(
            cornerRadiusEnd=6,
            size=70,
        )
        .encode(
            x=alt.X(
                "property_type:N",
                title=None,
            ),

            y=alt.Y(
                "median_price:Q",
                title=(
                    "Median Asking Price (USD)"
                ),
                axis=alt.Axis(
                    format="$,.0f",
                ),
            ),

            tooltip=[
                alt.Tooltip(
                    "property_type:N",
                    title=(
                        "Property Type"
                    ),
                ),

                alt.Tooltip(
                    "listings:Q",
                    title="Listings",
                    format=",",
                ),

                alt.Tooltip(
                    "median_price:Q",
                    title=(
                        "Median Asking Price"
                    ),
                    format="$,.0f",
                ),

                alt.Tooltip(
                    "median_size:Q",
                    title="Median Size",
                    format=".0f",
                ),

                alt.Tooltip(
                    "median_price_per_m2:Q",
                    title=(
                        "Median Price / m²"
                    ),
                    format="$,.0f",
                ),
            ],
        )
        .properties(
            height=350,
        )
    )


    st.altair_chart(
        property_type_price_chart,
    )


# =========================================================
# PROPERTY TYPE EXPLANATION
# =========================================================

if (
    property_type_filter
    == "All"
):

    st.info(
        "Penthouses typically have higher asking prices "
        "and larger property sizes than Condos. They also "
        "tend to have a higher advertised price per "
        "square meter."
    )


st.divider()


# =========================================================
# BEDROOM & BATHROOM ANALYSIS
# =========================================================

st.subheader(
    "Bedroom & Bathroom Analysis"
)

st.caption(
    "Explore how advertised asking prices vary with "
    "the number of bedrooms and bathrooms."
)


# =========================================================
# BEDROOM SUMMARY
# =========================================================

bedroom_summary = (
    filtered_df
    .dropna(
        subset=[
            "bedrooms",
            "price_usd",
        ]
    )
    .groupby(
        "bedrooms"
    )
    .agg(
        listings=(
            "price_usd",
            "size",
        ),

        median_price=(
            "price_usd",
            "median",
        ),
    )
    .reset_index()
)


# ---------------------------------------------------------
# REQUIRE AT LEAST 20 LISTINGS
# ---------------------------------------------------------

bedroom_summary = (
    bedroom_summary[
        bedroom_summary[
            "listings"
        ] >= 20
    ]
    .copy()
)


# ---------------------------------------------------------
# LABEL 0 BEDROOM AS STUDIO
# ---------------------------------------------------------

if not bedroom_summary.empty:

    bedroom_summary[
        "bedroom_label"
    ] = (
        bedroom_summary[
            "bedrooms"
        ]
        .astype(int)
        .astype(str)
    )


    bedroom_order = (
        bedroom_summary
        .sort_values(
            "bedrooms"
        )[
            "bedroom_label"
        ]
        .tolist()
    )


# =========================================================
# BATHROOM SUMMARY
# =========================================================

bathroom_summary = (
    filtered_df
    .dropna(
        subset=[
            "bathrooms",
            "price_usd",
        ]
    )
    .groupby(
        "bathrooms"
    )
    .agg(
        listings=(
            "price_usd",
            "size",
        ),

        median_price=(
            "price_usd",
            "median",
        ),
    )
    .reset_index()
)


bathroom_summary = (
    bathroom_summary[
        bathroom_summary[
            "listings"
        ] >= 20
    ]
    .copy()
)


if not bathroom_summary.empty:

    bathroom_summary[
        "bathroom_label"
    ] = (
        bathroom_summary[
            "bathrooms"
        ]
        .astype(int)
        .astype(str)
    )


    bathroom_order = (
        bathroom_summary
        .sort_values(
            "bathrooms"
        )[
            "bathroom_label"
        ]
        .tolist()
    )


# =========================================================
# CHART LAYOUT
# =========================================================

bed_col, bath_col = st.columns(
    2,
    gap="large",
)


# =========================================================
# BEDROOM CHART
# =========================================================

with bed_col:

    st.markdown(
        "#### :material/bed: Median Price by Bedrooms"
    )


    if bedroom_summary.empty:

        st.info(
            "Not enough listings are available "
            "for bedroom analysis with the "
            "selected filters."
        )

    else:

        bedroom_chart = (
            alt.Chart(
                bedroom_summary
            )
            .mark_bar(
                cornerRadiusTopLeft=5,
                cornerRadiusTopRight=5,
            )
            .encode(
                x=alt.X(
                    "bedroom_label:N",
                    title="Bedrooms",
                    sort=bedroom_order,
                ),

                y=alt.Y(
                    "median_price:Q",
                    title=(
                        "Median Asking Price (USD)"
                    ),
                    axis=alt.Axis(
                        format="$,.0f",
                    ),
                ),

                tooltip=[
                    alt.Tooltip(
                        "bedroom_label:N",
                        title="Bedrooms",
                    ),

                    alt.Tooltip(
                        "listings:Q",
                        title="Listings",
                        format=",",
                    ),

                    alt.Tooltip(
                        "median_price:Q",
                        title=(
                            "Median Asking Price"
                        ),
                        format="$,.0f",
                    ),
                ],
            )
            .properties(
                height=350,
            )
        )


        st.altair_chart(
            bedroom_chart,
        )


# =========================================================
# BATHROOM CHART
# =========================================================

with bath_col:

    st.markdown(
        "#### :material/shower: Median Price by Bathrooms"
    )


    if bathroom_summary.empty:

        st.info(
            "Not enough listings are available "
            "for bathroom analysis with the "
            "selected filters."
        )

    else:

        bathroom_chart = (
            alt.Chart(
                bathroom_summary
            )
            .mark_bar(
                cornerRadiusTopLeft=5,
                cornerRadiusTopRight=5,
            )
            .encode(
                x=alt.X(
                    "bathroom_label:N",
                    title="Bathrooms",
                    sort=bathroom_order,
                ),

                y=alt.Y(
                    "median_price:Q",
                    title=(
                        "Median Asking Price (USD)"
                    ),
                    axis=alt.Axis(
                        format="$,.0f",
                    ),
                ),

                tooltip=[
                    alt.Tooltip(
                        "bathroom_label:N",
                        title="Bathrooms",
                    ),

                    alt.Tooltip(
                        "listings:Q",
                        title="Listings",
                        format=",",
                    ),

                    alt.Tooltip(
                        "median_price:Q",
                        title=(
                            "Median Asking Price"
                        ),
                        format="$,.0f",
                    ),
                ],
            )
            .properties(
                height=350,
            )
        )


        st.altair_chart(
            bathroom_chart,
        )


# =========================================================
# ROOM ANALYSIS NOTE
# =========================================================

st.info(
    "Properties with more bedrooms and bathrooms generally "
    "have higher asking prices. However, room count is only "
    "one factor — property size, location, floor level, and "
    "property type also affect price."
)


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "Market Insights are based on advertised property "
    "listing data collected for the PP PropertyLens project. "
    "They describe listing patterns and should not be "
    "interpreted as official transaction-price statistics."
)