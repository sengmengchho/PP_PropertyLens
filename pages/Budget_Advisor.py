import streamlit as st
import pandas as pd
import altair as alt
from pathlib import Path


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Budget Advisor | PP PropertyLens",
    page_icon=":material/account_balance_wallet:",
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
    ":material/account_balance_wallet: Budget Advisor"
)

st.write(
    "Enter your property budget and explore the types of "
    "Condo and Penthouse listings, districts, and typical "
    "property characteristics available within that budget."
)

st.info(
    "Recommendations are based on advertised listings in "
    "the PP PropertyLens dataset and are provided for "
    "market comparison, not financial or investment advice."
)

st.divider()


# =========================================================
# YOUR BUDGET
# =========================================================

st.subheader(
    "Your Budget"
)

st.caption(
    "Tell PropertyLens how much you plan to spend and "
    "optionally narrow the search by property type or district."
)


with st.container(
    border=True
):

    input_col1, input_col2 = st.columns(
        2,
        gap="large",
    )


    # -----------------------------------------------------
    # MAXIMUM BUDGET
    # -----------------------------------------------------

    with input_col1:

        budget = st.number_input(
            "Maximum Budget (USD)",
            min_value=int(
                df["price_usd"].min()
            ),
            max_value=int(
                df["price_usd"].max()
            ),
            value=100_000,
            step=10_000,
            format="%d",
            key="advisor_budget",
        )


    # -----------------------------------------------------
    # PROPERTY TYPE
    # -----------------------------------------------------

    with input_col2:

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
                key="advisor_property_type",
                width="stretch",
            )
        )


    # -----------------------------------------------------
    # DISTRICT
    # -----------------------------------------------------

    district_options = sorted(
        df[
            "district"
        ]
        .dropna()
        .unique()
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

selected_market_df = (
    df.copy()
)


# =========================================================
# PROPERTY TYPE FILTER
# =========================================================

if (
    property_type_filter
    != "All"
):

    selected_market_df = (
        selected_market_df[
            selected_market_df[
                "property_type"
            ]
            == property_type_filter
        ]
        .copy()
    )


# =========================================================
# DISTRICT FILTER
# =========================================================

if district_filter:

    selected_market_df = (
        selected_market_df[
            selected_market_df[
                "district"
            ].isin(
                district_filter
            )
        ]
        .copy()
    )


# =========================================================
# EMPTY SELECTED MARKET
# =========================================================

if selected_market_df.empty:

    st.warning(
        "No listings are available for the selected "
        "property type and district preferences."
    )

    st.stop()


# =========================================================
# AFFORDABLE LISTINGS
# =========================================================

affordable_df = (
    selected_market_df[
        selected_market_df[
            "price_usd"
        ]
        <= budget
    ]
    .copy()
)


# =========================================================
# NO AFFORDABLE LISTINGS
# =========================================================

if affordable_df.empty:

    st.warning(
        "No listings in the current dataset match this "
        "budget and the selected preferences."
    )


    # =====================================================
    # CLOSEST OPTIONS ABOVE BUDGET
    # =====================================================

    closest_above = (
        selected_market_df[
            selected_market_df[
                "price_usd"
            ]
            > budget
        ]
        .copy()
    )


    if not closest_above.empty:

        closest_above[
            "amount_above_budget"
        ] = (
            closest_above[
                "price_usd"
            ]
            - budget
        )


        closest_above = (
            closest_above
            .sort_values(
                "amount_above_budget",
                ascending=True,
            )
            .head(10)
        )


        st.subheader(
            "Closest Options Above Your Budget"
        )

        st.caption(
            "These are the nearest advertised listings "
            "above your selected maximum budget."
        )


        above_columns = [
            column
            for column in [
                "title",
                "property_type",
                "district",
                "size_m2",
                "bedrooms",
                "bathrooms",
                "unit_floor",
                "price_usd",
                "source",
                "amount_above_budget",
            ]
            if column
            in closest_above.columns
        ]


        display_above = (
            closest_above[
                above_columns
            ]
            .copy()
        )


        display_above = (
            display_above.rename(
                columns={
                    "title":
                        "Listing",

                    "property_type":
                        "Property Type",

                    "district":
                        "District",

                    "size_m2":
                        "Size (m²)",

                    "bedrooms":
                        "Bedrooms",

                    "bathrooms":
                        "Bathrooms",

                    "unit_floor":
                        "Floor",

                    "price_usd":
                        "Asking Price",

                    "source":
                        "Source",

                    "amount_above_budget":
                        "Above Budget",
                }
            )
        )


        st.dataframe(
            display_above,
            hide_index=True,
            column_config={
                "Asking Price":
                    st.column_config.NumberColumn(
                        format="$%.0f",
                    ),

                "Above Budget":
                    st.column_config.NumberColumn(
                        format="$%.0f",
                    ),

                "Size (m²)":
                    st.column_config.NumberColumn(
                        format="%.0f",
                    ),

                "Bedrooms":
                    st.column_config.NumberColumn(
                        format="%.0f",
                    ),

                "Bathrooms":
                    st.column_config.NumberColumn(
                        format="%.0f",
                    ),

                "Floor":
                    st.column_config.NumberColumn(
                        format="%.0f",
                    ),
            },
        )


    st.stop()


# =========================================================
# BUDGET SUMMARY
# =========================================================

st.subheader(
    "Budget Summary"
)


market_coverage = (
    len(
        affordable_df
    )
    / len(
        selected_market_df
    )
    * 100
)


median_matching_price = (
    affordable_df[
        "price_usd"
    ]
    .median()
)


highest_affordable_price = (
    affordable_df[
        "price_usd"
    ]
    .max()
)


# =========================================================
# BUDGET POSITION
# =========================================================

budget_percentile = (
    (
        df[
            "price_usd"
        ]
        <= budget
    )
    .mean()
    * 100
)


if budget_percentile < 25:

    budget_position = (
        "Entry Market"
    )

elif budget_percentile < 75:

    budget_position = (
        "Mid Market"
    )

elif budget_percentile < 95:

    budget_position = (
        "Upper Market"
    )

else:

    budget_position = (
        "Luxury / High-End Market"
    )


# =========================================================
# SUMMARY ROW 1
# =========================================================

summary_col1, summary_col2, summary_col3 = (
    st.columns(
        3,
        gap="large",
    )
)


with summary_col1:

    st.metric(
        "Matching Listings",
        f"{len(affordable_df):,}",
    )


with summary_col2:

    st.metric(
        "Your Budget",
        f"${budget:,.0f}",
    )


with summary_col3:

    st.metric(
        "Median Matching Price",
        f"${median_matching_price:,.0f}",
    )


# =========================================================
# SUMMARY ROW 2
# =========================================================

summary_col4, summary_col5, summary_col6 = (
    st.columns(
        3,
        gap="large",
    )
)


with summary_col4:

    st.metric(
        "Highest Matching Listing",
        f"${highest_affordable_price:,.0f}",
    )


with summary_col5:

    st.metric(
        "Selected Market Coverage",
        f"{market_coverage:.1f}%",
    )


with summary_col6:

    st.metric(
        "Budget Position",
        budget_position,
    )


# =========================================================
# BUDGET POSITION EXPLANATION
# =========================================================

if budget_percentile >= 99:

    st.caption(
        "Your budget reaches the very top end of "
        "advertised prices represented in the "
        "PropertyLens dataset."
    )

else:

    st.caption(
        f"Your budget is higher than approximately "
        f"**{budget_percentile:.0f}%** of advertised "
        f"prices represented in the PropertyLens dataset."
    )


st.caption(
    f"**{market_coverage:.1f}%** of listings in your "
    "selected market are advertised at or below your "
    "maximum budget."
)


# =========================================================
# RELEVANT BUDGET WINDOW
# =========================================================
#
# Recommendations should come from properties reasonably
# close to the user's selected budget.
#

target_lower_price = (
    budget
    * 0.70
)


budget_window_df = (
    affordable_df[
        affordable_df[
            "price_usd"
        ].between(
            target_lower_price,
            budget,
        )
    ]
    .copy()
)


# =========================================================
# SELECT RELEVANT COMPARISON SAMPLE
# =========================================================

if len(
    budget_window_df
) >= 10:

    target_df = (
        budget_window_df.copy()
    )


    target_window_label = (
        f"listings between "
        f"${target_lower_price:,.0f} and "
        f"${budget:,.0f}"
    )


else:

    # -----------------------------------------------------
    # If too few listings exist in the 70–100% range,
    # use the properties closest BELOW the maximum budget.
    # -----------------------------------------------------

    number_to_compare = min(
        30,
        len(
            affordable_df
        ),
    )


    target_df = (
        affordable_df
        .sort_values(
            "price_usd",
            ascending=False,
        )
        .head(
            number_to_compare
        )
        .copy()
    )


    comparison_low = (
        target_df[
            "price_usd"
        ]
        .min()
    )


    target_window_label = (
        f"the {len(target_df):,} listings closest "
        f"to your budget, ranging from "
        f"${comparison_low:,.0f} to "
        f"${budget:,.0f}"
    )


# =========================================================
# SMALL SAMPLE WARNING
# =========================================================

if len(
    target_df
) < 10:

    st.warning(
        "Only a small number of listings are available "
        "near this budget. Recommendations should be "
        "treated as examples rather than broad market trends."
    )


# =========================================================
# WHAT YOUR BUDGET TYPICALLY GETS
# =========================================================

st.divider()

st.subheader(
    "What Your Budget Typically Gets"
)

st.caption(
    f"Typical characteristics are based on "
    f"{target_window_label}."
)


typical_size = (
    target_df[
        "size_m2"
    ]
    .median()
)


typical_bedrooms = (
    target_df[
        "bedrooms"
    ]
    .median()
)


typical_bathrooms = (
    target_df[
        "bathrooms"
    ]
    .median()
)


typical_floor = (
    target_df[
        "unit_floor"
    ]
    .median()
)


profile_col1, profile_col2, profile_col3, profile_col4 = (
    st.columns(
        4,
        gap="large",
    )
)


# =========================================================
# TYPICAL SIZE
# =========================================================

with profile_col1:

    st.metric(
        "Typical Size",
        (
            f"{typical_size:,.0f} m²"
            if pd.notna(
                typical_size
            )
            else "Unknown"
        ),
    )


# =========================================================
# TYPICAL BEDROOMS
# =========================================================

with profile_col2:

    if pd.isna(
        typical_bedrooms
    ):

        bedroom_display = (
            "Unknown"
        )

    elif typical_bedrooms == 0:

        bedroom_display = (
            "Studio"
        )

    else:

        bedroom_display = (
            f"{typical_bedrooms:.0f}"
        )


    st.metric(
        "Typical Bedrooms",
        bedroom_display,
    )


# =========================================================
# TYPICAL BATHROOMS
# =========================================================

with profile_col3:

    st.metric(
        "Typical Bathrooms",
        (
            f"{typical_bathrooms:.0f}"
            if pd.notna(
                typical_bathrooms
            )
            else "Unknown"
        ),
    )


# =========================================================
# TYPICAL FLOOR
# =========================================================

with profile_col4:

    st.metric(
        "Typical Floor",
        (
            f"{typical_floor:.0f}"
            if pd.notna(
                typical_floor
            )
            else "Unknown"
        ),
    )


st.info(
    "These characteristics describe properties advertised "
    "near your selected budget. They are intended to help "
    "you compare realistic options rather than define what "
    "every property at this budget should look like."
)


# =========================================================
# AVAILABLE MARKET WITHIN BUDGET
# =========================================================

if (
    property_type_filter
    == "All"
):

    st.divider()

    st.subheader(
        "Available Market Within Your Budget"
    )

    st.caption(
        "This section summarizes all listings at or below "
        "your maximum budget. The section above focuses "
        "specifically on properties closer to your selected "
        "budget."
    )


    type_summary = (
        affordable_df
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

            median_bedrooms=(
                "bedrooms",
                "median",
            ),

            median_bathrooms=(
                "bathrooms",
                "median",
            ),
        )
        .reset_index()
    )


    if not type_summary.empty:

        type_columns = (
            st.columns(
                len(
                    type_summary
                ),
                gap="large",
            )
        )


        for column, (_, row) in zip(
            type_columns,
            type_summary.iterrows(),
        ):

            property_type_name = (
                row[
                    "property_type"
                ]
            )


            icon = (
                ":material/apartment:"
                if property_type_name
                == "Condo"
                else ":material/villa:"
            )


            with column:

                with st.container(
                    border=True,
                ):

                    st.markdown(
                        f"### {icon} "
                        f"{property_type_name}"
                    )


                    st.metric(
                        "Available Listings",
                        (
                            f"{int(row['listings']):,}"
                        ),
                    )


                    st.metric(
                        "Median Asking Price",
                        (
                            f"${row['median_price']:,.0f}"
                        ),
                    )


                    type_detail_col1, type_detail_col2 = (
                        st.columns(
                            2,
                            gap="medium",
                        )
                    )


                    # -------------------------------------
                    # SIZE
                    # -------------------------------------

                    with type_detail_col1:

                        st.caption(
                            "Typical size"
                        )


                        if pd.notna(
                            row[
                                "median_size"
                            ]
                        ):

                            st.markdown(
                                (
                                    f"**{row['median_size']:,.0f} "
                                    f"m²**"
                                )
                            )

                        else:

                            st.markdown(
                                "**Unknown**"
                            )


                    # -------------------------------------
                    # BEDROOMS
                    # -------------------------------------

                    with type_detail_col2:

                        st.caption(
                            "Typical bedrooms"
                        )


                        median_type_bedrooms = (
                            row[
                                "median_bedrooms"
                            ]
                        )


                        if pd.isna(
                            median_type_bedrooms
                        ):

                            type_bedroom_text = (
                                "Unknown"
                            )

                        elif (
                            median_type_bedrooms
                            == 0
                        ):

                            type_bedroom_text = (
                                "Studio"
                            )

                        else:

                            type_bedroom_text = (
                                f"{median_type_bedrooms:.0f}"
                            )


                        st.markdown(
                            f"**{type_bedroom_text}**"
                        )


# =========================================================
# AREAS TO COMPARE
# =========================================================

st.divider()

st.subheader(
    "Areas to Compare"
)

st.caption(
    "These areas are selected from properties near your "
    "budget and provide different options for availability, "
    "space, and how closely typical prices approach your budget."
)


# =========================================================
# DISTRICT PROFILES
# =========================================================

district_profiles = (
    target_df
    .dropna(
        subset=[
            "district"
        ]
    )
    .groupby(
        "district"
    )
    .agg(
        available_listings=(
            "price_usd",
            "size",
        ),

        typical_price=(
            "price_usd",
            "median",
        ),

        typical_size=(
            "size_m2",
            "median",
        ),

        typical_bedrooms=(
            "bedrooms",
            "median",
        ),

        typical_bathrooms=(
            "bathrooms",
            "median",
        ),

        typical_floor=(
            "unit_floor",
            "median",
        ),
    )
    .reset_index()
)


# =========================================================
# SAMPLE SIZE CONTROL
# =========================================================

if len(
    target_df
) >= 100:

    minimum_district_listings = (
        10
    )

elif len(
    target_df
) >= 30:

    minimum_district_listings = (
        5
    )

else:

    minimum_district_listings = (
        1
    )


district_profiles = (
    district_profiles[
        district_profiles[
            "available_listings"
        ]
        >= minimum_district_listings
    ]
    .copy()
)


# =========================================================
# BUILD AREA RECOMMENDATIONS
# =========================================================

recommendations = []


if not district_profiles.empty:

    # -----------------------------------------------------
    # MOST OPTIONS
    # -----------------------------------------------------

    most_options = (
        district_profiles
        .sort_values(
            [
                "available_listings",
                "typical_price",
            ],
            ascending=[
                False,
                False,
            ],
        )
        .iloc[0]
    )


    recommendations.append(
        (
            "Most Options",
            ":material/search:",
            most_options,
        )
    )


    used_districts = {
        most_options[
            "district"
        ]
    }


    # -----------------------------------------------------
    # MORE SPACE
    # -----------------------------------------------------

    remaining_space_options = (
        district_profiles[
            ~district_profiles[
                "district"
            ]
            .isin(
                used_districts
            )
        ]
        .copy()
    )


    if not remaining_space_options.empty:

        more_space = (
            remaining_space_options
            .sort_values(
                "typical_size",
                ascending=False,
            )
            .iloc[0]
        )


        recommendations.append(
            (
                "More Space",
                ":material/square_foot:",
                more_space,
            )
        )


        used_districts.add(
            more_space[
                "district"
            ]
        )


    # -----------------------------------------------------
    # CLOSER TO MAXIMUM BUDGET
    # -----------------------------------------------------

    remaining_budget_options = (
        district_profiles[
            ~district_profiles[
                "district"
            ]
            .isin(
                used_districts
            )
        ]
        .copy()
    )


    if not remaining_budget_options.empty:

        remaining_budget_options[
            "distance_to_budget"
        ] = (
            budget
            - remaining_budget_options[
                "typical_price"
            ]
        ).abs()


        closest_budget = (
            remaining_budget_options
            .sort_values(
                "distance_to_budget",
                ascending=True,
            )
            .iloc[0]
        )


        recommendations.append(
            (
                "Closer to Your Budget",
                ":material/target:",
                closest_budget,
            )
        )


# =========================================================
# DISPLAY AREA RECOMMENDATIONS
# =========================================================

if recommendations:

    recommendation_columns = (
        st.columns(
            len(
                recommendations
            ),
            gap="large",
        )
    )


    for column, (
        label,
        icon,
        row,
    ) in zip(
        recommendation_columns,
        recommendations,
    ):

        with column:

            with st.container(
                border=True,
            ):

                st.caption(
                    label.upper()
                )


                st.markdown(
                    f"### {icon} "
                    f"{row['district']}"
                )


                st.metric(
                    "Typical Asking Price",
                    (
                        f"${row['typical_price']:,.0f}"
                    ),
                )


                st.write(
                    f"**{int(row['available_listings']):,}** "
                    "matching listings near your budget"
                )


                # -----------------------------------------
                # SIZE
                # -----------------------------------------

                if pd.notna(
                    row[
                        "typical_size"
                    ]
                ):

                    st.write(
                        f"Typical size: "
                        f"**{row['typical_size']:,.0f} m²**"
                    )


                # -----------------------------------------
                # BEDROOMS
                # -----------------------------------------

                if pd.notna(
                    row[
                        "typical_bedrooms"
                    ]
                ):

                    if (
                        row[
                            "typical_bedrooms"
                        ]
                        == 0
                    ):

                        bedroom_text = (
                            "Studio"
                        )

                    else:

                        bedroom_text = (
                            f"{row['typical_bedrooms']:.0f}"
                        )


                    st.write(
                        f"Typical bedrooms: "
                        f"**{bedroom_text}**"
                    )


                # -----------------------------------------
                # BATHROOMS
                # -----------------------------------------

                if pd.notna(
                    row[
                        "typical_bathrooms"
                    ]
                ):

                    st.write(
                        f"Typical bathrooms: "
                        f"**{row['typical_bathrooms']:.0f}**"
                    )


                # -----------------------------------------
                # FLOOR
                # -----------------------------------------

                if pd.notna(
                    row[
                        "typical_floor"
                    ]
                ):

                    st.write(
                        f"Typical floor: "
                        f"**{row['typical_floor']:.0f}**"
                    )


else:

    st.info(
        "There are not enough district-level listings "
        "near this budget to create useful area comparisons."
    )


# =========================================================
# DISTRICT COMPARISON CHART
# =========================================================

if not district_profiles.empty:

    st.subheader(
        "Budget Options by District"
    )

    st.caption(
        "Number of properties near your budget in each "
        "district that has enough matching observations."
    )


    district_chart_df = (
        district_profiles
        .sort_values(
            "available_listings",
            ascending=True,
        )
        .copy()
    )


    district_chart = (
        alt.Chart(
            district_chart_df
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
                "available_listings:Q",
                title=(
                    "Matching Listings Near Budget"
                ),
                axis=alt.Axis(
                    format="d",
                    tickMinStep=1,
                ),
            ),

            tooltip=[
                alt.Tooltip(
                    "district:N",
                    title="District",
                ),

                alt.Tooltip(
                    "available_listings:Q",
                    title="Listings",
                    format=",",
                ),

                alt.Tooltip(
                    "typical_price:Q",
                    title="Typical Price",
                    format="$,.0f",
                ),

                alt.Tooltip(
                    "typical_size:Q",
                    title="Typical Size",
                    format=".0f",
                ),

                alt.Tooltip(
                    "typical_bedrooms:Q",
                    title="Typical Bedrooms",
                    format=".0f",
                ),

                alt.Tooltip(
                    "typical_bathrooms:Q",
                    title="Typical Bathrooms",
                    format=".0f",
                ),
            ],
        )
        .properties(
            height=400,
        )
    )


    st.altair_chart(
        district_chart,
    )


# =========================================================
# LISTINGS TO COMPARE
# =========================================================

st.divider()

st.subheader(
    "Listings to Compare"
)

st.caption(
    "These advertised listings are closest to your "
    "maximum budget while remaining within it."
)


comparables = (
    affordable_df.copy()
)


comparables[
    "budget_remaining"
] = (
    budget
    - comparables[
        "price_usd"
    ]
)


comparables = (
    comparables
    .sort_values(
        [
            "budget_remaining",
            "price_usd",
        ],
        ascending=[
            True,
            False,
        ],
    )
    .head(10)
)


# =========================================================
# COMPARABLE TABLE COLUMNS
# =========================================================

available_columns = [
    column
    for column in [
        "title",
        "property_type",
        "district",
        "size_m2",
        "bedrooms",
        "bathrooms",
        "unit_floor",
        "price_usd",
        "source",
        "budget_remaining",
    ]
    if column
    in comparables.columns
]


comparables_display = (
    comparables[
        available_columns
    ]
    .copy()
)


comparables_display = (
    comparables_display.rename(
        columns={
            "title":
                "Listing",

            "property_type":
                "Property Type",

            "district":
                "District",

            "size_m2":
                "Size (m²)",

            "bedrooms":
                "Bedrooms",

            "bathrooms":
                "Bathrooms",

            "unit_floor":
                "Floor",

            "price_usd":
                "Asking Price",

            "source":
                "Source",

            "budget_remaining":
                "Budget Remaining",
        }
    )
)


st.dataframe(
    comparables_display,
    hide_index=True,
    column_config={
        "Asking Price":
            st.column_config.NumberColumn(
                format="$%.0f",
            ),

        "Budget Remaining":
            st.column_config.NumberColumn(
                format="$%.0f",
            ),

        "Size (m²)":
            st.column_config.NumberColumn(
                format="%.0f",
            ),

        "Bedrooms":
            st.column_config.NumberColumn(
                format="%.0f",
            ),

        "Bathrooms":
            st.column_config.NumberColumn(
                format="%.0f",
            ),

        "Floor":
            st.column_config.NumberColumn(
                format="%.0f",
            ),
    },
)


# =========================================================
# DECISION SUPPORT NOTE
# =========================================================

st.info(
    "Use these results to compare what is commonly "
    "advertised within and near your budget. More matching "
    "listings generally means more choices, while property "
    "size, room count, district, floor level, building quality, "
    "condition, facilities, and other characteristics can "
    "all affect asking price."
)


# =========================================================
# DISCLAIMER
# =========================================================

st.divider()

st.caption(
    "Budget Advisor results are based on advertised "
    "property listings collected for PP PropertyLens. "
    "They are intended for market comparison and decision "
    "support only and are not financial advice, purchase "
    "recommendations, or official property valuations."
)