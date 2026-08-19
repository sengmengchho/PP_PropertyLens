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
    page_icon="🏠",
    layout="wide",
)


# =========================================================
# PAGE HEADER
# =========================================================

st.title("🏠 PP PropertyLens")

st.write(
    "Estimate the advertised asking price of a Condo "
    "or Penthouse in Phnom Penh."
)

st.caption(
    "Enter the property details below to receive an "
    "estimated asking price and price range."
)


# =========================================================
# INPUT FORM
# =========================================================

st.subheader("Property Details")

with st.form("property_form"):

    col1, col2 = st.columns(2)

    # -----------------------------------------------------
    # LEFT
    # -----------------------------------------------------

    with col1:

        property_type = st.selectbox(
            "Property Type",
            options=VALID_PROPERTY_TYPES,
            help="Select the actual type of the property.",
        )

        district_unknown = st.checkbox(
            "District not known"
        )

        if district_unknown:
            district = None

        else:
            district = st.selectbox(
                "District",
                options=VALID_DISTRICTS,
            )

        size_m2 = st.number_input(
            "Property Size (m²)",
            min_value=1.0,
            value=70.0,
            step=1.0,
        )


    # -----------------------------------------------------
    # RIGHT
    # -----------------------------------------------------

    with col2:

        bedrooms_unknown = st.checkbox(
            "Bedrooms not known"
        )

        if bedrooms_unknown:
            bedrooms = None

        else:
            bedrooms = st.number_input(
                "Bedrooms",
                min_value=0,
                value=2,
                step=1,
            )


        bathrooms_unknown = st.checkbox(
            "Bathrooms not known"
        )

        if bathrooms_unknown:
            bathrooms = None

        else:
            bathrooms = st.number_input(
                "Bathrooms",
                min_value=0,
                value=2,
                step=1,
            )


        floor_unknown = st.checkbox(
            "Floor level not known"
        )

        if floor_unknown:
            unit_floor = None

        else:
            unit_floor = st.number_input(
                "Floor Level",
                min_value=0,
                value=10,
                step=1,
            )


    submitted = st.form_submit_button(
        "Estimate Price",
        use_container_width=True,
    )


# =========================================================
# PREDICTION
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


        # =================================================
        # PRICE
        # =================================================

        st.divider()

        st.header(
            "Property Price Estimate"
        )


        st.metric(
            label="Estimated Asking Price",
            value=(
                f"${result['estimated_price_usd']:,.0f}"
            ),
        )


        # =================================================
        # PRICE RANGE
        # =================================================

        st.subheader(
            "Estimated Price Range"
        )

        lower_col, upper_col = st.columns(2)

        with lower_col:

            st.metric(
                label="Lower Estimate",
                value=(
                    f"${result['lower_price_usd']:,.0f}"
                ),
            )

        with upper_col:

            st.metric(
                label="Upper Estimate",
                value=(
                    f"${result['upper_price_usd']:,.0f}"
                ),
            )


        


        st.info(
            "The price range reflects uncertainty in the estimate and is intended to give a more realistic view than a single price alone."
            
        )


        # =================================================
        # PROVIDED / MISSING FACTORS
        # =================================================

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


        # =================================================
        # MAIN FACTORS
        # =================================================

        st.subheader(
            "Main Factors"
        )

        st.caption(
            "These are the property characteristics that "
            "had the strongest influence on this estimate."
        )


        factor_icons = {
            "district": "📍",
            "bedrooms": "🛏️",
            "bathrooms": "🚿",
            "size_m2": "📐",
            "unit_floor": "🏢",
            "property_type": "🏠",
        }


        top_factors = provided_factors[:4]


        if top_factors:

            factor_columns = st.columns(
                len(top_factors)
            )

            for column, item in zip(
                factor_columns,
                top_factors,
            ):

                with column:

                    icon = factor_icons.get(
                        item["feature"],
                        "🔹",
                    )

                    with st.container(
                        border=True
                    ):

                        st.markdown(
                            f"### {icon} "
                            f"{item['display_feature']}"
                        )

                        st.markdown(
                            f"**{item['value']}**"
                        )

                        st.caption(
                            f"{item['impact_level']} influence"
                        )


        # =================================================
        # MISSING INFORMATION
        # =================================================

        if missing_factors:

            st.subheader(
                "Missing Information"
            )

            missing_names = ", ".join(
                item["display_feature"]
                for item in missing_factors
            )

            st.warning(
                f"{missing_names} were not provided. "
                "The model handled these values automatically, "
                "but providing them may improve the estimate."
            )


        # =================================================
        # PROPERTY DETAILS USED
        # =================================================

        st.subheader(
            "Property Details Used"
        )

        detail1, detail2, detail3 = (
            st.columns(3)
        )


        with detail1:

            st.write(
                f"**Property Type:** "
                f"{property_type}"
            )

            st.write(
                f"**District:** "
                f"{district if district is not None else 'Not provided'}"
            )


        with detail2:

            st.write(
                f"**Size:** "
                f"{size_m2:g} m²"
            )

            st.write(
                f"**Bedrooms:** "
                f"{bedrooms if bedrooms is not None else 'Not provided'}"
            )


        with detail3:

            st.write(
                f"**Bathrooms:** "
                f"{bathrooms if bathrooms is not None else 'Not provided'}"
            )

            st.write(
                f"**Floor Level:** "
                f"{unit_floor if unit_floor is not None else 'Not provided'}"
            )


        # =================================================
        # WARNINGS
        # =================================================

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


        # =================================================
        # DISCLAIMER
        # =================================================

        st.divider()

        st.caption(
            "⚠️ This is a data-based estimate from advertised "
            "property listings and is not an official property valuation."
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