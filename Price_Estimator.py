import streamlit as st

from components.styles import inject_global_css
from components.ui import (
    hero_banner,
    section_header,
    price_display,
    price_range_display,
    impact_badge,
    detail_item,
    disclaimer,
)

from src.prediction.predict import (
    explain_prediction,
    VALID_DISTRICTS,
    VALID_PROPERTY_TYPES,
)


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="PP PropertyLens",
    page_icon="🏠",
    layout="wide",
)

inject_global_css()


# =========================================================
# CONSTANTS
# =========================================================

FACTOR_ICONS = {
    "district": "📍",
    "bedrooms": "🛏",
    "bathrooms": "🚿",
    "size_m2": "📐",
    "unit_floor": "🏗",
    "property_type": "🏠",
}


# =========================================================
# SESSION STATE
# =========================================================

if "prediction_result" not in st.session_state:
    st.session_state.prediction_result = None

if "prediction_inputs" not in st.session_state:
    st.session_state.prediction_inputs = None


# =========================================================
# PAGE HEADER
# =========================================================

hero_banner(
    title="PP PropertyLens",
    description=(
        "Find out the estimated asking price of a <strong>Condo or Penthouse</strong> "
        "in Phnom Penh. Just fill in what you know about the property "
        "and get an estimate in seconds."
    ),
    caption=(
        "You'll get an estimated price, a price range, "
        "and a simple explanation of what affected the estimate."
    ),
)


# =========================================================
# INPUT SECTION
# =========================================================

section_header(
    "Property Details",
    subtitle=(
        "Fill in what you know. Not sure about a detail? "
        "Just tick the box next to it and the model will handle it."
    ),
)


with st.container(border=True):

    col1, col2 = st.columns(2, gap="large")

    # =====================================================
    # LEFT COLUMN
    # =====================================================

    with col1:

        property_type = st.selectbox(
            "Property Type",
            options=VALID_PROPERTY_TYPES,
            help="Select the actual type of the property.",
            key="property_type",
        )

        district_unknown = st.checkbox(
            "District not known",
            key="district_unknown",
        )

        district = None if district_unknown else st.selectbox(
            "District",
            options=VALID_DISTRICTS,
            key="district",
        )

        size_m2 = st.number_input(
            "Property Size (m\u00b2)",
            min_value=1.0,
            value=70.0,
            step=1.0,
            key="size_m2",
        )

    # =====================================================
    # RIGHT COLUMN
    # =====================================================

    with col2:

        bedrooms_unknown = st.checkbox(
            "Bedrooms not known",
            key="bedrooms_unknown",
        )

        bedrooms = None if bedrooms_unknown else st.number_input(
            "Bedrooms",
            min_value=0,
            value=2,
            step=1,
            key="bedrooms",
        )

        bathrooms_unknown = st.checkbox(
            "Bathrooms not known",
            key="bathrooms_unknown",
        )

        bathrooms = None if bathrooms_unknown else st.number_input(
            "Bathrooms",
            min_value=0,
            value=2,
            step=1,
            key="bathrooms",
        )

        floor_unknown = st.checkbox(
            "Floor level not known",
            key="floor_unknown",
        )

        unit_floor = None if floor_unknown else st.number_input(
            "Floor Level",
            min_value=0,
            value=10,
            step=1,
            key="unit_floor",
        )

    # =====================================================
    # ESTIMATE BUTTON
    # =====================================================

    submitted = st.button(
        "Estimate property price",
        icon="🧮",
        width="stretch",
        type="primary",
    )


# =========================================================
# CURRENT FORM VALUES
# =========================================================

current_inputs = {
    "property_type": property_type,
    "district": district,
    "size_m2": size_m2,
    "bedrooms": bedrooms,
    "bathrooms": bathrooms,
    "unit_floor": unit_floor,
}


# =========================================================
# GENERATE PREDICTION
# =========================================================

if submitted:

    with st.spinner("Getting your estimate..."):
        try:

            result = explain_prediction(
                size_m2=size_m2,
                bedrooms=bedrooms,
                bathrooms=bathrooms,
                unit_floor=unit_floor,
                district=district,
                property_type=property_type,
            )

            st.session_state.prediction_result = result
            st.session_state.prediction_inputs = current_inputs.copy()

        except ValueError as error:

            st.error(str(error))

        except Exception as error:

            st.error("Something went wrong. Please try again.")
            st.exception(error)


# =========================================================
# DISPLAY SAVED PREDICTION
# =========================================================

if st.session_state.prediction_result is not None:

    result = st.session_state.prediction_result
    saved_inputs = st.session_state.prediction_inputs

    inputs_changed = current_inputs != saved_inputs

    if inputs_changed:
        st.info(
            "You changed the property details. "
            "Click **Estimate property price** again to get a new estimate."
        )


    # =====================================================
    # RESULT HEADER
    # =====================================================

    section_header(
        "Property Price Estimate",
        subtitle="Based on advertised property listings in Phnom Penh.",
        icon="🏠",
    )


    # =====================================================
    # MAIN PRICE + RANGE
    # =====================================================

    with st.container(border=True):
        price_display(
            result["estimated_price_usd"],
            label="ESTIMATED ASKING PRICE",
            subtitle="This is the system's best estimate based on the details you provided.",
        )

    st.markdown("")

    price_range_display(
        result["lower_price_usd"],
        result["upper_price_usd"],
    )

    st.caption(
        "The price range shows how much the estimate might vary. "
        "A range is more useful than a single number."
    )


    # =====================================================
    # SEPARATE PROVIDED / MISSING FACTORS
    # =====================================================

    provided_factors = [
        item
        for item in result["explanations"]
        if item["value"] != "Not provided"
    ]

    missing_factors = [
        item
        for item in result["explanations"]
        if item["value"] == "Not provided"
    ]


    # =====================================================
    # MAIN FACTORS
    # =====================================================

    section_header(
        "What affected this estimate?",
        subtitle="These are the main things that influenced the price.",
    )

    top_factors = provided_factors[:4]

    if top_factors:

        factor_columns = st.columns(
            len(top_factors), gap="medium"
        )

        for column, item in zip(factor_columns, top_factors):

            icon = FACTOR_ICONS.get(item["feature"], "ℹ️")

            with column:
                st.markdown(
                    f'<div class="pp-factor-card">'
                    f'<div class="pp-factor-icon">'
                    f"{icon}"
                    f"</div>"
                    f'<div class="pp-factor-name">'
                    f"{item['display_feature']}"
                    f"</div>"
                    f'<div class="pp-factor-value">'
                    f"{item['value']}"
                    f"</div>"
                    f'<div class="pp-factor-impact">'
                    f"{impact_badge(item['impact_level'])}"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


    # =====================================================
    # MISSING INFORMATION
    # =====================================================

    if missing_factors:

        section_header(
            "Missing Information",
            icon="⚠️",
        )

        missing_names = ", ".join(
            item["display_feature"] for item in missing_factors
        )

        st.warning(
            f"{missing_names} were not provided. "
            "The system handled this automatically, but "
            "providing these details may give a better estimate."
        )


    # =====================================================
    # PROPERTY DETAILS USED
    # =====================================================

    section_header("Property Details Used")

    with st.container(border=True):

        detail_col1, detail_col2, detail_col3 = st.columns(
            3, gap="large"
        )

        with detail_col1:
            st.markdown(
                detail_item(
                    "🏠",
                    "Property Type",
                    saved_inputs["property_type"],
                ),
                unsafe_allow_html=True,
            )
            st.markdown(
                detail_item(
                    "📍",
                    "District",
                    saved_inputs["district"]
                    if saved_inputs["district"] is not None
                    else "Not provided",
                ),
                unsafe_allow_html=True,
            )

        with detail_col2:
            st.markdown(
                detail_item(
                    "📐",
                    "Property Size",
                    f"{saved_inputs['size_m2']:g} m\u00b2",
                ),
                unsafe_allow_html=True,
            )
            st.markdown(
                detail_item(
                    "🛏",
                    "Bedrooms",
                    str(saved_inputs["bedrooms"])
                    if saved_inputs["bedrooms"] is not None
                    else "Not provided",
                ),
                unsafe_allow_html=True,
            )

        with detail_col3:
            st.markdown(
                detail_item(
                    "🚿",
                    "Bathrooms",
                    str(saved_inputs["bathrooms"])
                    if saved_inputs["bathrooms"] is not None
                    else "Not provided",
                ),
                unsafe_allow_html=True,
            )
            st.markdown(
                detail_item(
                    "🏗",
                    "Floor Level",
                    str(saved_inputs["unit_floor"])
                    if saved_inputs["unit_floor"] is not None
                    else "Not provided",
                ),
                unsafe_allow_html=True,
            )


    # =====================================================
    # IMPORTANT WARNINGS
    # =====================================================

    important_warnings = [
        warning
        for warning in result["warnings"]
        if "missing-value" not in warning.lower()
        and "not provided" not in warning.lower()
    ]

    if important_warnings:

        section_header("Important Notes")

        for warning in important_warnings:
            st.warning(warning)


    # =========================================================
    # DISCLAIMER
    # =========================================================

    disclaimer(
        "PropertyLens gives you an estimated asking price based on advertised "
        "property listings. It is not an official property valuation and may "
        "not reflect things like interior condition, furnishing, view, "
        "building quality, or negotiation."
    )
