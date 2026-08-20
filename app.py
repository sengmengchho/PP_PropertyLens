import streamlit as st

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
    page_icon=":material/real_estate_agent:",
    layout="wide",
)


# =========================================================
# CONSTANTS
# =========================================================

FACTOR_ICONS = {
    "district": ":material/place:",
    "bedrooms": ":material/bed:",
    "bathrooms": ":material/shower:",
    "size_m2": ":material/square_foot:",
    "unit_floor": ":material/stairs:",
    "property_type": ":material/home:",
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

st.title("PP PropertyLens")

st.markdown(
    """
    Estimate the asking price of a **Condo or Penthouse**
    in Phnom Penh. Enter what you know and get a
    data-based estimate in seconds.
    """
)

st.caption(
    "You'll get a central estimate, a realistic price range, "
    "and a plain-English breakdown of what drove the price."
)


# =========================================================
# INPUT SECTION
# =========================================================

st.subheader("Property Details")

st.caption(
    "Fill in what you know. Not sure about a detail? "
    "Tick the box next to it and the model will take "
    "it from there."
)


with st.container(border=True):

    col1, col2 = st.columns(
        2,
        gap="large",
    )


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


        # -------------------------------------------------
        # DISTRICT
        # -------------------------------------------------

        district_unknown = st.checkbox(
            "District not known",
            key="district_unknown",
        )

        if district_unknown:

            district = None

        else:

            district = st.selectbox(
                "District",
                options=VALID_DISTRICTS,
                key="district",
            )


        # -------------------------------------------------
        # PROPERTY SIZE
        # -------------------------------------------------

        size_m2 = st.number_input(
            "Property Size (m²)",
            min_value=1.0,
            value=70.0,
            step=1.0,
            key="size_m2",
        )


    # =====================================================
    # RIGHT COLUMN
    # =====================================================

    with col2:

        # -------------------------------------------------
        # BEDROOMS
        # -------------------------------------------------

        bedrooms_unknown = st.checkbox(
            "Bedrooms not known",
            key="bedrooms_unknown",
        )

        if bedrooms_unknown:

            bedrooms = None

        else:

            bedrooms = st.number_input(
                "Bedrooms",
                min_value=0,
                value=2,
                step=1,
                key="bedrooms",
            )


        # -------------------------------------------------
        # BATHROOMS
        # -------------------------------------------------

        bathrooms_unknown = st.checkbox(
            "Bathrooms not known",
            key="bathrooms_unknown",
        )

        if bathrooms_unknown:

            bathrooms = None

        else:

            bathrooms = st.number_input(
                "Bathrooms",
                min_value=0,
                value=2,
                step=1,
                key="bathrooms",
            )


        # -------------------------------------------------
        # FLOOR
        # -------------------------------------------------

        floor_unknown = st.checkbox(
            "Floor level not known",
            key="floor_unknown",
        )

        if floor_unknown:

            unit_floor = None

        else:

            unit_floor = st.number_input(
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
        icon=":material/calculate:",
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

    try:

        result = explain_prediction(
            size_m2=size_m2,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            unit_floor=unit_floor,
            district=district,
            property_type=property_type,
        )


        # Save result
        st.session_state.prediction_result = result


        # Save the exact values used to create this prediction
        st.session_state.prediction_inputs = (
            current_inputs.copy()
        )


    except ValueError as error:

        st.error(
            str(error)
        )


    except Exception as error:

        st.error(
            "The prediction could not be completed."
        )

        st.exception(
            error
        )


# =========================================================
# DISPLAY SAVED PREDICTION
# =========================================================

if st.session_state.prediction_result is not None:

    result = (
        st.session_state.prediction_result
    )

    saved_inputs = (
        st.session_state.prediction_inputs
    )


    # =====================================================
    # CHECK WHETHER CURRENT INPUTS HAVE CHANGED
    # =====================================================

    inputs_changed = (
        current_inputs
        != saved_inputs
    )


    if inputs_changed:

        st.info(
            "You changed the property details after the last "
            "estimate. Click **Estimate property price** again "
            "to update the result."
        )


# =====================================================
    # RESULT HEADER
    # =====================================================

    st.header(
        ":material/home: Property Price Estimate"
    )

    st.caption(
        "Estimated from advertised Phnom Penh "
        "property listing data."
    )


    # =====================================================
    # MAIN ESTIMATED PRICE
    # =====================================================

    with st.container(
        border=True,
        horizontal_alignment="center",
    ):

        st.caption(
            "ESTIMATED ASKING PRICE"
        )

        st.markdown(
            f"# ${result['estimated_price_usd']:,.0f}"
        )


        st.caption(
            "The system's estimate based on "
            "the property details provided."
        )


    # =====================================================
    # PRICE RANGE
    # =====================================================

    st.subheader(
        "Estimated Price Range"
    )


    lower_col, upper_col = st.columns(
        2,
        gap="medium",
    )


    # -----------------------------------------------------
    # LOWER RANGE
    # -----------------------------------------------------

    with lower_col:

        with st.container(
            border=True,
            horizontal_alignment="center",
        ):

            st.caption(
                "LOWER ESTIMATE"
            )

            st.markdown(
                f"## ${result['lower_price_usd']:,.0f}"
            )

            


    # -----------------------------------------------------
    # UPPER RANGE
    # -----------------------------------------------------

    with upper_col:

        with st.container(
            border=True,
            horizontal_alignment="center",
        ):

            st.caption(
                "UPPER ESTIMATE"
            )

            st.markdown(
                f"## ${result['upper_price_usd']:,.0f}"
            )

        


    st.caption(
        "The price range reflects uncertainty in the estimate "
        "and gives a more realistic view than a single predicted "
        "price alone."
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

    st.subheader(
        "Why this estimate?"
    )

    st.caption(
        "These factors had the most influence "
        "on this estimate."
    )


    top_factors = (
        provided_factors[:4]
    )


    if top_factors:

        factor_columns = st.columns(
            len(top_factors),
            gap="medium",
        )


        for column, item in zip(
            factor_columns,
            top_factors,
        ):

            icon = FACTOR_ICONS.get(
                item["feature"],
                "🔹",
            )


            with column:

                with st.container(
                    border=True
                ):

                    st.markdown(
                        f"### {icon}"
                    )

                    st.markdown(
                        f"**{item['display_feature']}**"
                    )

                    st.markdown(
                        f"### {item['value']}"
                    )

                    st.caption(
                        f"{item['impact_level']} influence"
                    )


    # =====================================================
    # MISSING INFORMATION
    # =====================================================

    if missing_factors:

        st.subheader(
            ":material/error: Missing Information"
        )


        missing_names = ", ".join(
            item["display_feature"]
            for item in missing_factors
        )


        st.warning(
            f"{missing_names} were not provided. "
            "The model handled the missing information "
            "automatically, but providing these details "
            "may improve the estimate."
        )


    # =====================================================
    # PROPERTY DETAILS USED
    # =====================================================

    st.subheader(
        "Property Details Used"
    )


    with st.container(
        border=True
    ):

        detail1, detail2, detail3 = (
            st.columns(
                3,
                gap="large",
            )
        )


        # =================================================
        # COLUMN 1
        # =================================================

        with detail1:

            st.markdown(
                f"""
                :material/home: **Property Type**  
                {saved_inputs["property_type"]}
                """
            )


            district_display = (
                saved_inputs["district"]
                if saved_inputs["district"] is not None
                else "Not provided"
            )


            st.markdown(
                f"""
                :material/place: **District**  
                {district_display}
                """
            )


        # =================================================
        # COLUMN 2
        # =================================================

        with detail2:

            st.markdown(
                f"""
                :material/square_foot: **Property Size**  
                {saved_inputs["size_m2"]:g} m²
                """
            )


            bedrooms_display = (
                saved_inputs["bedrooms"]
                if saved_inputs["bedrooms"] is not None
                else "Not provided"
            )


            st.markdown(
                f"""
                :material/bed: **Bedrooms**  
                {bedrooms_display}
                """
            )


        # =================================================
        # COLUMN 3
        # =================================================

        with detail3:

            bathrooms_display = (
                saved_inputs["bathrooms"]
                if saved_inputs["bathrooms"] is not None
                else "Not provided"
            )


            st.markdown(
                f"""
                :material/shower: **Bathrooms**  
                {bathrooms_display}
                """
            )


            floor_display = (
                saved_inputs["unit_floor"]
                if saved_inputs["unit_floor"] is not None
                else "Not provided"
            )


            st.markdown(
                f"""
                :material/stairs: **Floor Level**  
                {floor_display}
                """
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

        st.subheader(
            "Important Notes"
        )


        for warning in important_warnings:

            st.warning(
                warning
            )


    # =====================================================
    # DISCLAIMER
    # =====================================================

    st.space("medium")


    st.caption(
        ":material/info: PropertyLens provides a data-based asking-price "
        "estimate using advertised property listing data. "
        "It is not an official property valuation and may "
        "not capture factors such as interior condition, "
        "furnishing, view, facilities, building reputation, "
        "seller urgency, or negotiation."
    )
