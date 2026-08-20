from pathlib import Path
import json

import altair as alt
import pandas as pd
import streamlit as st


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="About & Methodology | PP PropertyLens",
    page_icon="ℹ️",
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

METADATA_PATH = (
    PROJECT_ROOT
    / "models"
    / "propertylens_xgboost_final_metadata.json"
)


# =========================================================
# LOAD DATA
# =========================================================

@st.cache_data
def load_data():

    return pd.read_csv(
        DATA_PATH
    )


@st.cache_data
def load_metadata():

    if not METADATA_PATH.exists():
        return None

    with open(
        METADATA_PATH,
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(file)


df = load_data()

metadata = load_metadata()


# =========================================================
# HEADER
# =========================================================

st.title(
    "ℹ️ About & Methodology"
)

st.write(
    "Learn how PP PropertyLens was built, "
    "from collecting Phnom Penh property listings "
    "to producing data-based asking-price estimates."
)

st.divider()


# =========================================================
# ABOUT THE PROJECT
# =========================================================

st.subheader(
    "About PP PropertyLens"
)

st.write(
    """
    **PP PropertyLens** is a data science project for exploring
    advertised Condo and Penthouse prices in Phnom Penh and
    estimating an asking price from basic property information.

    The system combines property-listing data, exploratory data
    analysis, machine learning, and model explainability in one
    interactive application.
    """
)


st.info(
    "PropertyLens estimates advertised asking prices from "
    "listing data. It is not an official property valuation "
    "or a substitute for a professional property appraiser."
)


# =========================================================
# PROJECT OBJECTIVES
# =========================================================

st.subheader(
    "Project Objectives"
)

objective_col1, objective_col2, objective_col3 = (
    st.columns(
        3,
        gap="large",
    )
)


with objective_col1:

    with st.container(
        border=True
    ):

        st.markdown(
            "### 📊 Explore the Market"
        )

        st.write(
            "Show asking-price patterns across "
            "Phnom Penh districts and property types."
        )


with objective_col2:

    with st.container(
        border=True
    ):

        st.markdown(
            "### 🏠 Estimate Asking Price"
        )

        st.write(
            "Use property characteristics to generate "
            "a central asking-price estimate and range."
        )


with objective_col3:

    with st.container(
        border=True
    ):

        st.markdown(
            "### 🔍 Explain Predictions"
        )

        st.write(
            "Help users understand which property "
            "characteristics influence model estimates."
        )


st.divider()


# =========================================================
# DATASET OVERVIEW
# =========================================================

st.subheader(
    "Dataset Overview"
)

st.caption(
    "The final dataset contains cleaned and deduplicated "
    "advertised property listings from multiple public "
    "real-estate websites."
)


data_col1, data_col2, data_col3, data_col4 = (
    st.columns(4)
)


with data_col1:

    st.metric(
        "Final Listings",
        f"{len(df):,}",
    )


with data_col2:

    st.metric(
        "Property Types",
        df[
            "property_type"
        ].nunique(),
    )


with data_col3:

    st.metric(
        "Districts",
        df[
            "district"
        ].nunique(),
    )


with data_col4:

    st.metric(
        "Median Asking Price",
        (
            f"${df['price_usd'].median():,.0f}"
        ),
    )


# =========================================================
# DATA SOURCES
# =========================================================

st.subheader(
    "Data Sources"
)

st.caption(
    "Listings were collected from six public Cambodian "
    "property-listing websites and then standardized "
    "into one common dataset."
)


source_counts = (
    df[
        "source"
    ]
    .value_counts()
    .reset_index()
)

source_counts.columns = [
    "Source",
    "Listings",
]


source_counts = (
    source_counts
    .sort_values(
        "Listings",
        ascending=True,
    )
)


source_chart = (
    alt.Chart(
        source_counts
    )
    .mark_bar(
        cornerRadiusEnd=5
    )
    .encode(
        y=alt.Y(
            "Source:N",
            sort=None,
            title=None,
        ),

        x=alt.X(
            "Listings:Q",
            title="Number of Listings",
        ),

        tooltip=[
            alt.Tooltip(
                "Source:N",
                title="Source",
            ),

            alt.Tooltip(
                "Listings:Q",
                title="Listings",
                format=",",
            ),
        ],
    )
    .properties(
        height=330,
    )
)


st.altair_chart(
    source_chart,
    use_container_width=True,
)


with st.expander(
    "See the six data sources"
):

    st.markdown(
        """
        - realestate.com.kh
        - harbor-property.com
        - khpropertyhub.com
        - camrealtyservice.com
        - aps.com.kh
        - khmer24.com
        """
    )


st.caption(
    "Property listings from different websites may use "
    "different formats and may contain missing, duplicated, "
    "or inconsistent information."
)


st.divider()


# =========================================================
# DATA PREPARATION PIPELINE
# =========================================================

st.subheader(
    "Data Preparation"
)

st.caption(
    "Several preparation steps were used before the "
    "data was used for analysis and machine learning."
)


pipeline_col1, pipeline_col2, pipeline_col3 = (
    st.columns(
        3,
        gap="large",
    )
)


with pipeline_col1:

    with st.container(
        border=True
    ):

        st.markdown(
            "### 1️⃣ Collect"
        )

        st.write(
            "Property listings were collected "
            "from multiple public websites."
        )


with pipeline_col2:

    with st.container(
        border=True
    ):

        st.markdown(
            "### 2️⃣ Clean"
        )

        st.write(
            "Prices, sizes, property types, "
            "districts, bedrooms, bathrooms, "
            "and floor information were standardized."
        )


with pipeline_col3:

    with st.container(
        border=True
    ):

        st.markdown(
            "### 3️⃣ Review"
        )

        st.write(
            "Suspicious or conflicting listings "
            "were reviewed before inclusion."
        )


pipeline_col4, pipeline_col5, pipeline_col6 = (
    st.columns(
        3,
        gap="large",
    )
)


with pipeline_col4:

    with st.container(
        border=True
    ):

        st.markdown(
            "### 4️⃣ Deduplicate"
        )

        st.write(
            "Duplicate properties across different "
            "sources were identified and removed."
        )


with pipeline_col5:

    with st.container(
        border=True
    ):

        st.markdown(
            "### 5️⃣ Recover Location"
        )

        st.write(
            "Missing district information was recovered "
            "when reliable location evidence was available."
        )


with pipeline_col6:

    with st.container(
        border=True
    ):

        st.markdown(
            "### 6️⃣ Analyze & Model"
        )

        st.write(
            "The final dataset was used for market "
            "analysis and machine-learning experiments."
        )


# =========================================================
# FINAL DATASET NOTE
# =========================================================

st.info(
    f"After cleaning and cross-source deduplication, "
    f"the final dataset contains {len(df):,} unique "
    f"property listings."
)


st.divider()


# =========================================================
# MODEL FEATURES
# =========================================================

st.subheader(
    "Information Used by the Model"
)

st.caption(
    "The final model uses six property characteristics "
    "to estimate advertised asking price."
)


feature_data = pd.DataFrame(
    [
        {
            "Feature":
                "Property Size",

            "Model Field":
                "size_m2",

            "Description":
                "Property area in square meters",
        },

        {
            "Feature":
                "Bedrooms",

            "Model Field":
                "bedrooms",

            "Description":
                "Number of bedrooms",
        },

        {
            "Feature":
                "Bathrooms",

            "Model Field":
                "bathrooms",

            "Description":
                "Number of bathrooms",
        },

        {
            "Feature":
                "Floor Level",

            "Model Field":
                "unit_floor",

            "Description":
                "Floor where the property unit is located",
        },

        {
            "Feature":
                "Location",

            "Model Field":
                "district",

            "Description":
                "Phnom Penh district",
        },

        {
            "Feature":
                "Property Type",

            "Model Field":
                "property_type",

            "Description":
                "Condo or Penthouse",
        },
    ]
)


st.dataframe(
    feature_data,
    use_container_width=True,
    hide_index=True,
)


# =========================================================
# FEATURES NOT USED
# =========================================================

with st.expander(
    "Why are some dataset columns not used by the model?"
):

    st.markdown(
        """
        **Price per m²**

        This is calculated using the actual asking price.
        Using it to predict asking price would leak information
        about the target into the model.

        **Project name**

        Project names were missing for many listings, so they
        were not reliable enough to use as a main production
        feature.

        **Latitude and longitude**

        Exact coordinates were available for only a small
        percentage of listings. District was therefore used as
        the primary location feature.

        **Building total floors**

        This field had very high missingness and was excluded.

        **Website source**

        The goal is to estimate property asking price rather
        than learn price differences caused by individual
        listing websites.
        """
    )


st.divider()


# =========================================================
# MISSING DATA HANDLING
# =========================================================

st.subheader(
    "Handling Missing Information"
)

st.write(
    """
    Some listings do not provide every property detail.
    Instead of removing all of these listings, the model
    uses preprocessing rules to handle missing values.
    """
)


missing_col1, missing_col2 = (
    st.columns(
        2,
        gap="large",
    )
)


with missing_col1:

    with st.container(
        border=True
    ):

        st.markdown(
            "### 🔢 Numeric Features"
        )

        st.write(
            "Missing numeric values such as bedrooms, "
            "bathrooms, and floor level are filled using "
            "median values learned from the training data."
        )

        st.write(
            "Missing-value indicators are also included "
            "so the model can recognize that the original "
            "information was unavailable."
        )


with missing_col2:

    with st.container(
        border=True
    ):

        st.markdown(
            "### 🏷️ Categorical Features"
        )

        st.write(
            "Missing categorical information such as "
            "district is represented using an "
            "'Unknown' category."
        )


st.divider()


# =========================================================
# TARGET VARIABLE
# =========================================================

st.subheader(
    "Prediction Target"
)

st.write(
    """
    The model predicts the property's **advertised asking price**.

    Property prices are strongly right-skewed because most
    listings are in common market price ranges while a smaller
    number of luxury properties can cost several million dollars.
    """
)


st.info(
    "To make model training more stable across low-, mid-, "
    "and high-priced properties, the asking price was "
    "log-transformed during model training."
)


with st.expander(
    "What does log-transformed price mean?"
):

    st.write(
        """
        Instead of directly learning from raw dollar prices,
        the model learns from a compressed logarithmic version
        of price.

        This reduces the extreme difference between typical
        properties and very expensive luxury properties.

        After prediction, the result is converted back into
        normal US dollars before it is shown to the user.
        """
    )


st.divider()


# =========================================================
# DATA SPLIT
# =========================================================

st.subheader(
    "Model Development Split"
)

st.caption(
    "The final workflow separated the data into training, "
    "validation, calibration, and final test sets."
)


split_df = pd.DataFrame(
    [
        {
            "Dataset":
                "Training",

            "Rows":
                1869,

            "Share":
                70,

            "Purpose":
                "Fit candidate models",
        },

        {
            "Dataset":
                "Validation",

            "Rows":
                268,

            "Share":
                10,

            "Purpose":
                "Compare and select models",
        },

        {
            "Dataset":
                "Calibration",

            "Rows":
                268,

            "Share":
                10,

            "Purpose":
                "Create the estimated price range",
        },

        {
            "Dataset":
                "Final Test",

            "Rows":
                268,

            "Share":
                10,

            "Purpose":
                "Final model evaluation",
        },
    ]
)


split_chart = (
    alt.Chart(
        split_df
    )
    .mark_bar(
        cornerRadiusTopLeft=5,
        cornerRadiusTopRight=5,
    )
    .encode(
        x=alt.X(
            "Dataset:N",
            title=None,
            sort=[
                "Training",
                "Validation",
                "Calibration",
                "Final Test",
            ],
        ),

        y=alt.Y(
            "Rows:Q",
            title="Number of Listings",
        ),

        tooltip=[
            alt.Tooltip(
                "Dataset:N",
                title="Dataset",
            ),

            alt.Tooltip(
                "Rows:Q",
                title="Rows",
                format=",",
            ),

            alt.Tooltip(
                "Share:Q",
                title="Share",
                format=".0f",
            ),

            alt.Tooltip(
                "Purpose:N",
                title="Purpose",
            ),
        ],
    )
    .properties(
        height=350,
    )
)


st.altair_chart(
    split_chart,
    use_container_width=True,
)


st.dataframe(
    split_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Rows":
            st.column_config.NumberColumn(
                format="%d",
            ),

        "Share":
            st.column_config.NumberColumn(
                "Share (%)",
                format="%d%%",
            ),
    },
)


st.caption(
    "The split was stratified by property type so the "
    "proportion of Condos and Penthouses remained similar "
    "across the four datasets."
)


# =========================================================
# FINAL TRAINING NOTE
# =========================================================

if metadata is not None:

    st.info(
        f"After XGBoost was selected, the final model was "
        f"refitted using the Training + Validation data "
        f"({metadata['training_rows']:,} listings). "
        f"The Calibration set remained separate for the "
        f"price range, and the {metadata['final_test_rows']:,} "
        f"Final Test listings were used for final evaluation."
    )


st.divider()


# =========================================================
# MODEL SELECTION
# =========================================================

st.subheader(
    "Model Selection"
)

st.caption(
    "Three regression approaches were compared before "
    "choosing the final production model."
)


model_col1, model_col2, model_col3 = (
    st.columns(
        3,
        gap="large",
    )
)


with model_col1:

    with st.container(
        border=True
    ):

        st.markdown(
            "### Linear Regression"
        )

        st.write(
            "Used as a simple baseline model."
        )


with model_col2:

    with st.container(
        border=True
    ):

        st.markdown(
            "### Random Forest"
        )

        st.write(
            "Used to capture nonlinear relationships "
            "between property characteristics and price."
        )


with model_col3:

    with st.container(
        border=True
    ):

        st.markdown(
            "### ✅ XGBoost"
        )

        st.write(
            "Selected as the final model based mainly "
            "on validation performance in log-price space."
        )


st.info(
    "Random Forest and XGBoost produced similar results. "
    "XGBoost was selected because it achieved the best "
    "validation Log RMSE and Log R², while maintaining "
    "strong overall performance."
)


st.divider()


# =========================================================
# ESTIMATED PRICE RANGE
# =========================================================

st.subheader(
    "Estimated Price Range"
)

st.write(
    """
    PropertyLens does not show only one estimated price.
    It also provides a lower and upper estimated range to
    communicate uncertainty.
    """
)


range_col1, range_col2, range_col3 = (
    st.columns(
        3,
        gap="large",
    )
)


with range_col1:

    with st.container(
        border=True
    ):

        st.markdown(
            "### 1️⃣ Central Estimate"
        )

        st.write(
            "XGBoost predicts the central "
            "advertised asking-price estimate."
        )


with range_col2:

    with st.container(
        border=True
    ):

        st.markdown(
            "### 2️⃣ Calibration"
        )

        st.write(
            "Prediction errors from a separate calibration "
            "dataset are used to measure uncertainty."
        )


with range_col3:

    with st.container(
        border=True
    ):

        st.markdown(
            "### 3️⃣ Price Range"
        )

        st.write(
            "A lower and upper price are created around "
            "the central estimate."
        )


if metadata is not None:

    interval_level = metadata.get(
        "interval_level",
        0.80,
    )

    st.info(
        f"The estimated range was designed for approximately "
        f"{interval_level:.0%} coverage. On the final test "
        f"set, observed coverage was about 78%."
    )


with st.expander(
    "Technical note about the estimated range"
):

    st.write(
        """
        The project uses a split-conformal approach based on
        prediction errors from the calibration dataset.

        This provides a practical way to communicate model
        uncertainty.

        The range should not be interpreted as a guaranteed
        probability interval for every individual property.
        """
    )


st.divider()


# =========================================================
# MODEL EXPLAINABILITY
# =========================================================

st.subheader(
    "Model Explainability"
)

st.write(
    """
    SHAP is used to help explain how property characteristics
    influence the XGBoost model.
    """
)


explain_col1, explain_col2 = (
    st.columns(
        2,
        gap="large",
    )
)


with explain_col1:

    with st.container(
        border=True
    ):

        st.markdown(
            "### 🌍 Global Explanation"
        )

        st.write(
            "Shows which features generally have the "
            "strongest influence across many listings."
        )


with explain_col2:

    with st.container(
        border=True
    ):

        st.markdown(
            "### 🏠 Individual Explanation"
        )

        st.write(
            "Shows which property characteristics were "
            "most influential for one specific estimate."
        )


st.info(
    "Global SHAP analysis found that property size had "
    "the strongest overall influence, followed by location, "
    "bedrooms, and floor level."
)


st.divider()


# =========================================================
# LIMITATIONS
# =========================================================

st.subheader(
    "Limitations"
)

st.caption(
    "The system has several important limitations that "
    "should be considered when interpreting its results."
)


with st.container(
    border=True
):

    st.markdown(
        """
        **📋 Advertised prices, not transaction prices**

        The dataset contains sellers' advertised asking prices.
        It does not show the final negotiated sale price.

        **🏠 Limited property characteristics**

        The model uses six main features. It does not directly
        know the property's interior condition, renovation
        quality, furnishings, view, facilities, parking,
        exact building reputation, seller urgency, or
        negotiation circumstances.

        **📍 Limited exact-location coverage**

        District is the primary location feature because exact
        coordinates were unavailable for most listings.

        **🌆 Luxury properties are less common**

        There are fewer very high-value properties in the
        dataset, so estimates for unusual luxury properties
        may be less stable.

        **🏢 Property mix**

        The dataset contains many more Condos than Penthouses.
        The split preserved this distribution, but Penthouse
        predictions are supported by fewer examples.

        **🔗 Similar buildings may appear across splits**

        The final split was performed at the listing level.
        Because reliable project names were unavailable for
        many records, completely grouping every building or
        project across splits was not possible.
        """
    )


st.divider()


# =========================================================
# RESPONSIBLE USE
# =========================================================

st.subheader(
    "How to Use PropertyLens"
)


use_col1, use_col2 = (
    st.columns(
        2,
        gap="large",
    )
)


with use_col1:

    with st.container(
        border=True
    ):

        st.markdown(
            "### ✅ Appropriate Uses"
        )

        st.markdown(
            """
            - Explore advertised market patterns
            - Compare districts
            - Understand typical listing prices
            - Generate a data-based asking-price estimate
            - Support early property research
            """
        )


with use_col2:

    with st.container(
        border=True
    ):

        st.markdown(
            "### ⚠️ Do Not Treat It As"
        )

        st.markdown(
            """
            - An official property valuation
            - A guaranteed selling price
            - A replacement for physical inspection
            - A replacement for professional appraisal
            - A guarantee of future market value
            """
        )


# =========================================================
# FINAL DISCLAIMER
# =========================================================

st.warning(
    "PP PropertyLens provides data-based estimates derived "
    "from advertised property listings. Results should be "
    "used as supporting market information only and should "
    "not be interpreted as an official property valuation."
)


# =========================================================
# FOOTER
# =========================================================

st.divider()

st.caption(
    "PP PropertyLens — Phnom Penh Condo & Penthouse "
    "Market Analytics and Asking-Price Estimation."
)