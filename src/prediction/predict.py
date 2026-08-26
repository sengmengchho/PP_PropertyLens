from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import json


# =========================================================
# PATHS
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "propertylens_xgboost_final.joblib"
)

METADATA_PATH = (
    PROJECT_ROOT
    / "models"
    / "propertylens_xgboost_final_metadata.json"
)


# =========================================================
# LOAD MODEL + CONFORMAL METADATA
# =========================================================

if not MODEL_PATH.exists():
    raise FileNotFoundError(
        f"Model file not found: {MODEL_PATH}"
    )

if not METADATA_PATH.exists():
    raise FileNotFoundError(
        f"Metadata file not found: {METADATA_PATH}"
    )


model = joblib.load(
    MODEL_PATH
)


with open(
    METADATA_PATH,
    "r",
    encoding="utf-8",
) as file:
    model_metadata = json.load(file)


INTERVAL_LEVEL = float(
    model_metadata["interval_level"]
)

Q_HAT = float(
    model_metadata["q_hat"]
)
# =========================================================
# GET PREPROCESSOR + XGBOOST
# =========================================================

preprocessor = model.named_steps["preprocessor"]

xgb_model = model.named_steps["model"]

feature_names = (
    preprocessor.get_feature_names_out()
)


# =========================================================
# SHAP EXPLAINER (lazy-loaded)
# =========================================================

_shap_explainer = None


def _get_shap_explainer():
    global _shap_explainer
    if _shap_explainer is None:
        import shap
        _shap_explainer = shap.TreeExplainer(
            xgb_model
        )
    return _shap_explainer


# =========================================================
# GET VALID CATEGORIES FROM TRAINED MODEL
# =========================================================

cat_pipeline = (
    preprocessor.named_transformers_["cat"]
)

onehot_encoder = (
    cat_pipeline.named_steps["onehot"]
)

category_values = (
    onehot_encoder.categories_
)


VALID_DISTRICTS = [
    value
    for value in category_values[0]
    if str(value) != "Unknown"
]

VALID_PROPERTY_TYPES = list(
    category_values[1]
)


# =========================================================
# DISPLAY NAMES
# =========================================================

FEATURE_LABELS = {
    "size_m2": "Property Size",
    "bedrooms": "Bedrooms",
    "bathrooms": "Bathrooms",
    "unit_floor": "Floor Level",
    "district": "Location (District)",
    "property_type": "Property Type",
}


# =========================================================
# HELPERS
# =========================================================

def impact_level(shap_value):
    value = abs(shap_value)

    if value >= 0.15:
        return "Strong"

    if value >= 0.05:
        return "Moderate"

    if value >= 0.01:
        return "Small"

    return "Very small"


def impact_direction(shap_value):
    if shap_value > 0:
        return "Pushes estimate higher"

    if shap_value < 0:
        return "Pushes estimate lower"

    return "Little effect"


# =========================================================
# INPUT VALIDATION
# =========================================================

def validate_input(
    size_m2,
    bedrooms,
    bathrooms,
    unit_floor,
    district,
    property_type,
):
    warnings = []

    # -------------------------
    # Hard validation
    # -------------------------

    if size_m2 is None:
        raise ValueError(
            "Property size is required."
        )

    if size_m2 <= 0:
        raise ValueError(
            "Property size must be greater than 0."
        )

    if bedrooms is not None and bedrooms < 0:
        raise ValueError(
            "Bedrooms cannot be negative."
        )

    if bathrooms is not None and bathrooms < 0:
        raise ValueError(
            "Bathrooms cannot be negative."
        )

    if unit_floor is not None and unit_floor < 0:
        raise ValueError(
            "Floor level cannot be negative."
        )

    if (
        district is not None
        and district not in VALID_DISTRICTS
    ):
        raise ValueError(
            f"Unknown district: {district}"
        )

    if (
        property_type
        not in VALID_PROPERTY_TYPES
    ):
        raise ValueError(
            f"Invalid property type: "
            f"{property_type}"
        )

    # -------------------------
    # Unusual-value warnings
    # -------------------------

    if size_m2 > 2000:
        warnings.append(
            "Property size is unusually large."
        )

    if bedrooms is not None and bedrooms > 10:
        warnings.append(
            "Bedroom count is unusually high."
        )

    if bathrooms is not None and bathrooms > 10:
        warnings.append(
            "Bathroom count is unusually high."
        )

    if unit_floor is not None and unit_floor > 78:
        warnings.append(
            "Floor level is unusually high."
        )

    # -------------------------
    # Missing-value warnings
    # -------------------------

    if bedrooms is None:
        warnings.append(
            "Bedrooms were not provided; "
            "the model used missing-value handling."
        )

    if bathrooms is None:
        warnings.append(
            "Bathrooms were not provided; "
            "the model used missing-value handling."
        )

    if unit_floor is None:
        warnings.append(
            "Floor level was not provided; "
            "the model used missing-value handling."
        )

    if district is None:
        warnings.append(
            "Location was not provided; "
            "the estimate may be less reliable."
        )

    return warnings

def predict_price(
    size_m2,
    bedrooms,
    bathrooms,
    unit_floor,
    district,
    property_type,
):
    warnings = validate_input(
        size_m2=size_m2,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        unit_floor=unit_floor,
        district=district,
        property_type=property_type,
    )

    property_data = pd.DataFrame([
        {
            "size_m2": size_m2,
            "bedrooms": (
                np.nan
                if bedrooms is None
                else bedrooms
            ),
            "bathrooms": (
                np.nan
                if bathrooms is None
                else bathrooms
            ),
            "unit_floor": (
                np.nan
                if unit_floor is None
                else unit_floor
            ),
            "district": (
                np.nan
                if district is None
                else district
            ),
            "property_type": property_type,
        }
    ])

    predicted_log_price = model.predict(
        property_data
    )[0]

    estimated_price = float(
        np.expm1(
            predicted_log_price
        )
    )

    lower_price = float(
        np.expm1(
            predicted_log_price - Q_HAT
        )
    )

    upper_price = float(
        np.expm1(
            predicted_log_price + Q_HAT
        )
    )

    lower_price = max(
        0.0,
        lower_price,
    )

    if estimated_price > 1_000_000:
        warnings.append(
            "Ultra-luxury estimates above $1M "
            "have higher uncertainty."
        )

    return {
        "estimated_price_usd":
            estimated_price,

        "lower_price_usd":
            lower_price,

        "upper_price_usd":
            upper_price,

        "interval_level":
            INTERVAL_LEVEL,

        "predicted_log_price":
            float(
                predicted_log_price
            ),

        "warnings":
            warnings,

        "input_data":
            property_data,
    }

def explain_prediction(
    size_m2,
    bedrooms,
    bathrooms,
    unit_floor,
    district,
    property_type,
):
    prediction = predict_price(
        size_m2=size_m2,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        unit_floor=unit_floor,
        district=district,
        property_type=property_type,
    )

    property_data = (
        prediction["input_data"]
    )

    # -------------------------------------------------
    # Transform exactly as model sees the data
    # -------------------------------------------------

    transformed = (
        preprocessor.transform(
            property_data
        )
    )

    if hasattr(
        transformed,
        "toarray"
    ):
        transformed = (
            transformed.toarray()
        )

    transformed_df = pd.DataFrame(
        transformed,
        columns=feature_names
    )

    # -------------------------------------------------
    # SHAP
    # -------------------------------------------------

    shap_values = (
        _get_shap_explainer()(
            transformed_df
        )
    )

    row_shap = shap_values[0]

    shap_map = dict(
        zip(
            feature_names,
            row_shap.values
        )
    )

    # -------------------------------------------------
    # GROUP ONE-HOT FEATURES BACK TO ORIGINAL FEATURES
    # -------------------------------------------------

    groups = {
        "size_m2": [
            name
            for name in feature_names
            if (
                name == "num__size_m2"
            )
        ],

        "bedrooms": [
            name
            for name in feature_names
            if (
                name == "num__bedrooms"
                or
                "missingindicator_bedrooms"
                in name
            )
        ],

        "bathrooms": [
            name
            for name in feature_names
            if (
                name == "num__bathrooms"
                or
                "missingindicator_bathrooms"
                in name
            )
        ],

        "unit_floor": [
            name
            for name in feature_names
            if (
                name == "num__unit_floor"
                or
                "missingindicator_unit_floor"
                in name
            )
        ],

        "district": [
            name
            for name in feature_names
            if name.startswith(
                "cat__district_"
            )
        ],

        "property_type": [
            name
            for name in feature_names
            if name.startswith(
                "cat__property_type_"
            )
        ],
    }

    grouped_shap = {}

    for feature, names in groups.items():

        grouped_shap[feature] = sum(
            shap_map.get(
                name,
                0
            )
            for name in names
        )

    # -------------------------------------------------
    # DISPLAY VALUES
    # -------------------------------------------------

    display_values = {
        "size_m2":
            f"{size_m2:g} m²",

        "bedrooms":
            "Not provided"
            if bedrooms is None
            else bedrooms,

        "bathrooms":
            "Not provided"
            if bathrooms is None
            else bathrooms,

        "unit_floor":
            "Not provided"
            if unit_floor is None
            else unit_floor,

        "district":
            "Not provided"
            if district is None
            else district,

        "property_type":
            property_type,
    }


    # -------------------------------------------------
    # BUILD USER-FRIENDLY EXPLANATIONS
    # -------------------------------------------------

    explanations = []

    for feature, shap_value in grouped_shap.items():

        # Approximate USD influence
        price_without_feature = float(
            np.expm1(
                prediction["predicted_log_price"]
                - shap_value
            )
        )

        approx_effect_usd = (
            prediction["estimated_price_usd"]
            - price_without_feature
        )

        explanations.append({
            "feature":
                feature,

            "display_feature":
                FEATURE_LABELS[feature],

            "value":
                display_values[feature],

            "direction":
                impact_direction(
                    shap_value
                ),

            "impact_level":
                impact_level(
                    shap_value
                ),

            # User-friendly
            "approx_effect_usd":
                float(approx_effect_usd),

            # Technical details
            "shap_value":
                float(shap_value),

            "approx_effect_pct":
                float(
                    np.expm1(
                        shap_value
                    ) * 100
                ),
        })


    # Sort by strongest SHAP impact
    explanations = sorted(
        explanations,
        key=lambda item: abs(
            item["shap_value"]
        ),
        reverse=True,
    )

    
    return {
        "estimated_price_usd":
            prediction[
                "estimated_price_usd"
            ],

        "lower_price_usd":
            prediction[
                "lower_price_usd"
            ],

        "upper_price_usd":
            prediction[
                "upper_price_usd"
            ],

        "interval_level":
            prediction[
                "interval_level"
            ],

        "predicted_log_price":
            prediction[
                "predicted_log_price"
            ],

        "warnings":
            prediction[
                "warnings"
            ],

        "input_data":
            prediction[
                "input_data"
            ],

        "explanations":
            explanations,

        "raw_shap":
            row_shap,
    }
