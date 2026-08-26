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


DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "gold"
    / "property_listings_geocoded.csv"
)


# =========================================================
# LOAD DATA
# =========================================================

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


    # -----------------------------------------------------
    # PRICE RANGE
    # -----------------------------------------------------

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
        "Try expanding the district or asking-price range."
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


lowest_price = (
    filtered_df[
        "price_usd"
    ].min()
)

median_price = (
    filtered_df[
        "price_usd"
    ].median()
)

highest_price = (
    filtered_df[
        "price_usd"
    ].max()
)

median_size = (
    filtered_df[
        "size_m2"
    ].median()
)

district_count = (
    filtered_df[
        "district"
    ].nunique()
)


# =========================================================
# OVERVIEW ROW 1
# =========================================================

overview_col1, overview_col2, overview_col3 = (
    st.columns(
        3,
        gap="large",
    )
)


with overview_col1:

    st.metric(
        "Listings",
        f"{len(filtered_df):,}",
    )


with overview_col2:

    st.metric(
        "Lowest Asking Price",
        f"${lowest_price:,.0f}",
    )


with overview_col3:

    st.metric(
        "Median Asking Price",
        f"${median_price:,.0f}",
    )


# =========================================================
# OVERVIEW ROW 2
# =========================================================

overview_col4, overview_col5, overview_col6 = (
    st.columns(
        3,
        gap="large",
    )
)


with overview_col4:

    st.metric(
        "Highest Asking Price",
        f"${highest_price:,.0f}",
    )


with overview_col5:

    st.metric(
        "Median Size",
        f"{median_size:,.0f} m²",
    )


with overview_col6:

    st.metric(
        "Districts Covered",
        district_count,
    )


st.caption(
    "Lowest and highest values represent the advertised "
    "asking-price range among listings matching the "
    "current filters."
)


st.divider()


# =========================================================
# MOST COMMON PRICE RANGE
# =========================================================

st.subheader(
    "Most Common Price Range"
)

st.caption(
    "Shows the asking-price range containing the largest "
    "concentration of listings for each selected property type."
)


# =========================================================
# PROPERTY TYPES TO DISPLAY
# =========================================================

if property_type_filter == "All":

    types_to_show = [
        "Condo",
        "Penthouse",
    ]

else:

    types_to_show = [
        property_type_filter
    ]


# =========================================================
# COMMON PRICE RANGE FUNCTION
# =========================================================

def get_common_price_range(
    data,
    property_type_name,
):

    type_df = (
        data[
            data[
                "property_type"
            ] == property_type_name
        ]
        .dropna(
            subset=[
                "price_usd"
            ]
        )
        .copy()
    )


    if type_df.empty:

        return None, None


    # Condo has more observations, so smaller bands are useful.
    if property_type_name == "Condo":

        price_band_size = 25_000

    else:

        price_band_size = 50_000


    type_df[
        "price_band_start"
    ] = (
        type_df[
            "price_usd"
        ]
        // price_band_size
        * price_band_size
    )


    type_df[
        "price_band_end"
    ] = (
        type_df[
            "price_band_start"
        ]
        + price_band_size
    )


    band_summary = (
        type_df
        .groupby(
            [
                "price_band_start",
                "price_band_end",
            ]
        )
        .size()
        .reset_index(
            name="listings"
        )
    )


    band_summary[
        "price_band_label"
    ] = (
        band_summary
        .apply(
            lambda row:
            (
                f"${row['price_band_start']:,.0f}"
                f" – "
                f"${row['price_band_end']:,.0f}"
            ),
            axis=1,
        )
    )


    most_common_band = (
        band_summary
        .sort_values(
            "listings",
            ascending=False,
        )
        .iloc[0]
    )


    result = {
        "property_type":
            property_type_name,

        "total_listings":
            len(type_df),

        "band_start":
            most_common_band[
                "price_band_start"
            ],

        "band_end":
            most_common_band[
                "price_band_end"
            ],

        "band_count":
            int(
                most_common_band[
                    "listings"
                ]
            ),

        "band_share":
            (
                most_common_band[
                    "listings"
                ]
                / len(type_df)
                * 100
            ),
    }


    return (
        result,
        band_summary,
    )


# =========================================================
# BUILD COMMON RANGE RESULTS
# =========================================================

common_range_results = []


for property_type_name in types_to_show:

    result, band_summary = (
        get_common_price_range(
            filtered_df,
            property_type_name,
        )
    )


    if result is not None:

        common_range_results.append(
            (
                result,
                band_summary,
            )
        )


# =========================================================
# DISPLAY COMMON RANGE
# =========================================================

if not common_range_results:

    st.info(
        "No listings are available for this section "
        "with the current filters."
    )

else:

    range_columns = st.columns(
        len(common_range_results),
        gap="large",
    )


    for column, (
        result,
        band_summary,
    ) in zip(
        range_columns,
        common_range_results,
    ):

        property_type_name = (
            result[
                "property_type"
            ]
        )


        if property_type_name == "Condo":

            icon = ":material/apartment:"

        else:

            icon = ":material/villa:"


        with column:

            with st.container(
                border=True,
            ):

                st.markdown(
                    f"### {icon} "
                    f"{property_type_name}"
                )


                st.caption(
                    "MOST COMMON ASKING-PRICE RANGE"
                )


                st.markdown(
                    (
                        f"## "
                        f"${result['band_start']:,.0f}"
                        f" – "
                        f"${result['band_end']:,.0f}"
                    )
                )


                range_metric1, range_metric2 = (
                    st.columns(
                        2
                    )
                )


                with range_metric1:

                    st.metric(
                        "Listings in Range",
                        f"{result['band_count']:,}",
                    )


                with range_metric2:

                    st.metric(
                        "Share",
                        (
                            f"{result['band_share']:.1f}%"
                        ),
                    )


                st.caption(
                    (
                        f"{result['band_count']:,} of "
                        f"{result['total_listings']:,} "
                        f"{property_type_name} listings "
                        "fall within this price range."
                    )
                )


                # -----------------------------------------
                # SMALL SAMPLE WARNING
                # -----------------------------------------

                if (
                    result[
                        "total_listings"
                    ] < 5
                ):

                    st.warning(
                        "Very few listings match the "
                        "current filters. This range is "
                        "descriptive only and should not "
                        "be treated as a market trend."
                    )

                elif (
                    result[
                        "total_listings"
                    ] < 20
                ):

                    st.warning(
                        "This result is based on a small "
                        "number of listings, so interpret "
                        "the price concentration carefully."
                    )


# =========================================================
# COMMON PRICE RANGE CHARTS
# =========================================================

for (
    result,
    band_summary,
) in common_range_results:

    # Skip distribution chart for extremely small samples
    if (
        result[
            "total_listings"
        ] < 5
    ):

        continue


    property_type_name = (
        result[
            "property_type"
        ]
    )


    st.markdown(
        f"#### {property_type_name} Price Distribution"
    )


    top_price_bands = (
        band_summary
        .sort_values(
            "listings",
            ascending=False,
        )
        .head(8)
        .sort_values(
            "price_band_start",
            ascending=True,
        )
        .copy()
    )


    price_band_order = (
        top_price_bands[
            "price_band_label"
        ]
        .tolist()
    )


    common_price_chart = (
        alt.Chart(
            top_price_bands
        )
        .mark_bar(
            cornerRadiusTopLeft=5,
            cornerRadiusTopRight=5,
        )
        .encode(
            x=alt.X(
                "price_band_label:N",
                title=(
                    f"{property_type_name} "
                    "Asking-Price Range"
                ),
                sort=price_band_order,
                axis=alt.Axis(
                    labelAngle=-35,
                ),
            ),

            y=alt.Y(
                "listings:Q",
                title="Number of Listings",
            ),

            tooltip=[
                alt.Tooltip(
                    "price_band_label:N",
                    title="Price Range",
                ),

                alt.Tooltip(
                    "listings:Q",
                    title="Listings",
                    format=",",
                ),
            ],
        )
        .properties(
            height=340,
        )
    )


    st.altair_chart(
        common_price_chart,
    )


st.info(
    "The most common price range shows where advertised "
    "listings are most concentrated. It does not represent "
    "an official property valuation."
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
    "are shown for stronger comparisons."
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
                title="Median Asking Price (USD)",
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
                title="Median Price per m² (USD)",
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
# DISTRICT DETAILS
# =========================================================

st.subheader(
    "District Details"
)

st.caption(
    "Detailed statistics for districts matching the "
    "current filters."
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
    "Shows how advertised prices are distributed for "
    "the selected market. The chart displays up to the "
    "99th percentile so extreme luxury listings do not "
    "compress the main distribution."
)


# =========================================================
# ONLY DISPLAY DISTRIBUTION WHEN SAMPLE IS LARGE ENOUGH
# =========================================================

if len(filtered_df) < 5:

    st.info(
        "Only a few listings match the current filters. "
        "A price-distribution chart is not shown because "
        "there are too few observations for a useful "
        "distribution."
    )

else:

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


    distribution_median_price = (
        filtered_df[
            "price_usd"
        ]
        .median()
    )


    # =====================================================
    # HISTOGRAM
    # =====================================================

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
                title="Advertised Asking Price (USD)",
                axis=alt.Axis(
                    format="$,.0f",
                ),
            ),

            y=alt.Y(
                "count():Q",
                title="Number of Listings",
            ),

            tooltip=[
                alt.Tooltip(
                    "count():Q",
                    title="Listings",
                ),
            ],
        )
    )


    # =====================================================
    # MEDIAN LINE
    # =====================================================

    median_data = pd.DataFrame(
        {
            "median_price": [
                distribution_median_price
            ]
        }
    )


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


    median_label_data = pd.DataFrame(
        {
            "median_price": [
                distribution_median_price
            ],

            "label": [
                (
                    f"Median: "
                    f"${distribution_median_price:,.0f}"
                )
            ],
        }
    )


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
        "number of luxury properties extend above the "
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

                st.space(
                    "small"
                )

                st.caption(
                    "MEDIAN ASKING PRICE"
                )

                st.markdown(
                    f"# ${row['median_price']:,.0f}"
                )

                st.caption(
                    f"Based on {int(row['listings']):,} "
                    f"matching {property_type_name} listings."
                )

                st.space(
                    "medium"
                )


                measure_col1, measure_col2 = (
                    st.columns(
                        2,
                        gap="medium",
                    )
                )


                with measure_col1:

                    with st.container(
                        border=True,
                        horizontal_alignment="center",
                    ):

                        st.caption(
                            "Median size"
                        )

                        st.markdown(
                            (
                                f"**{row['median_size']:,.0f} "
                                f"m²**"
                            )
                        )


                with measure_col2:

                    with st.container(
                        border=True,
                        horizontal_alignment="center",
                    ):

                        st.caption(
                            "Price per m²"
                        )

                        st.markdown(
                            (
                                f"**${row['median_price_per_m2']:,.0f}**"
                            )
                        )


# =========================================================
# PROPERTY TYPE PRICE CHART
# =========================================================

if len(filtered_df) >= 5:

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
                title="Median Asking Price (USD)",
                axis=alt.Axis(
                    format="$,.0f",
                ),
            ),

            tooltip=[
                alt.Tooltip(
                    "property_type:N",
                    title="Property Type",
                ),

                alt.Tooltip(
                    "listings:Q",
                    title="Listings",
                    format=",",
                ),

                alt.Tooltip(
                    "median_price:Q",
                    title="Median Asking Price",
                    format="$,.0f",
                ),

                alt.Tooltip(
                    "median_size:Q",
                    title="Median Size",
                    format=".0f",
                ),

                alt.Tooltip(
                    "median_price_per_m2:Q",
                    title="Median Price / m²",
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


if (
    property_type_filter
    == "All"
    and len(filtered_df) >= 20
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


total_filtered_listings = (
    len(
        filtered_df
    )
)


# =========================================================
# VERY SMALL SAMPLE
# =========================================================
#
# With fewer than 5 listings, showing a market-level
# bar chart is misleading. Show the characteristics of
# the matching properties instead.
#

if total_filtered_listings < 5:

    st.warning(
        f"Only {total_filtered_listings} listing"
        f"{'s' if total_filtered_listings != 1 else ''} "
        "match the current filters. Individual property "
        "characteristics are shown instead of market-level "
        "bedroom and bathroom comparisons."
    )


    typical_bedrooms = (
        filtered_df[
            "bedrooms"
        ].median()
    )


    typical_bathrooms = (
        filtered_df[
            "bathrooms"
        ].median()
    )


    typical_size = (
        filtered_df[
            "size_m2"
        ].median()
    )


    typical_floor = (
        filtered_df[
            "unit_floor"
        ].median()
    )


    profile_col1, profile_col2, profile_col3, profile_col4 = (
        st.columns(
            4,
            gap="large",
        )
    )


    with profile_col1:

        if pd.notna(
            typical_bedrooms
        ):

            if typical_bedrooms == 0:

                bedroom_display = (
                    "Studio"
                )

            else:

                bedroom_display = (
                    f"{typical_bedrooms:.0f}"
                )

        else:

            bedroom_display = (
                "Unknown"
            )


        st.metric(
            "Bedrooms",
            bedroom_display,
        )


    with profile_col2:

        st.metric(
            "Bathrooms",
            (
                f"{typical_bathrooms:.0f}"
                if pd.notna(
                    typical_bathrooms
                )
                else "Unknown"
            ),
        )


    with profile_col3:

        st.metric(
            "Size",
            (
                f"{typical_size:,.0f} m²"
                if pd.notna(
                    typical_size
                )
                else "Unknown"
            ),
        )


    with profile_col4:

        st.metric(
            "Floor Level",
            (
                f"{typical_floor:.0f}"
                if pd.notna(
                    typical_floor
                )
                else "Unknown"
            ),
        )


    st.info(
        "These characteristics describe only the small "
        "number of listings matching the filters and should "
        "not be interpreted as a wider market trend."
    )


# =========================================================
# NORMAL / SMALL-SAMPLE ANALYSIS
# =========================================================

else:

    # -----------------------------------------------------
    # DYNAMIC MINIMUM GROUP SIZE
    # -----------------------------------------------------

    if total_filtered_listings >= 100:

        minimum_group_size = 20

    elif total_filtered_listings >= 20:

        minimum_group_size = 5

    else:

        minimum_group_size = 1


    # -----------------------------------------------------
    # SMALL SAMPLE WARNING
    # -----------------------------------------------------

    if total_filtered_listings < 20:

        st.warning(
            f"Only {total_filtered_listings} listings match "
            "the current filters. Bedroom and bathroom "
            "results are descriptive and may not represent "
            "the wider market."
        )


    # =====================================================
    # BEDROOM SUMMARY
    # =====================================================

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


    bedroom_summary = (
        bedroom_summary[
            bedroom_summary[
                "listings"
            ] >= minimum_group_size
        ]
        .copy()
    )


    if not bedroom_summary.empty:

        bedroom_summary[
            "bedroom_label"
        ] = (
            bedroom_summary[
                "bedrooms"
            ]
            .astype(int)
            .apply(
                lambda value:
                (
                    "Studio"
                    if value == 0
                    else str(value)
                )
            )
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


    # =====================================================
    # BATHROOM SUMMARY
    # =====================================================

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
            ] >= minimum_group_size
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


    # =====================================================
    # CHART LAYOUT
    # =====================================================

    bed_col, bath_col = (
        st.columns(
            2,
            gap="large",
        )
    )


    # =====================================================
    # BEDROOM CHART
    # =====================================================

    with bed_col:

        st.markdown(
            "#### :material/bed: Median Price by Bedrooms"
        )


        if bedroom_summary.empty:

            st.info(
                "Bedroom information is not available "
                "for enough of the matching listings."
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
                        title="Median Asking Price (USD)",
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
                            title="Median Asking Price",
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


    # =====================================================
    # BATHROOM CHART
    # =====================================================

    with bath_col:

        st.markdown(
            "#### :material/shower: Median Price by Bathrooms"
        )


        if bathroom_summary.empty:

            st.info(
                "Bathroom information is not available "
                "for enough of the matching listings."
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
                        title="Median Asking Price (USD)",
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
                            title="Median Asking Price",
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


    st.info(
        "Properties with more bedrooms and bathrooms "
        "generally have higher asking prices. However, "
        "room count is only one factor — property size, "
        "location, floor level, and property type also "
        "affect price."
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