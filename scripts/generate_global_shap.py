from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap


# =========================================================
# PATHS
# =========================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "propertylens_xgboost_final.joblib"
)

DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "gold"
    / "property_listings_geocoded.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "model"
)

OUTPUT_PATH = (
    OUTPUT_DIR
    / "global_shap_importance.csv"
)


# =========================================================
# MODEL FEATURES
# =========================================================

FEATURES = [
    "size_m2",
    "bedrooms",
    "bathrooms",
    "unit_floor",
    "district",
    "property_type",
]


# =========================================================
# DISPLAY LABELS
# =========================================================

DISPLAY_NAMES = {
    "size_m2": "Property Size",
    "bedrooms": "Bedrooms",
    "bathrooms": "Bathrooms",
    "unit_floor": "Floor Level",
    "district": "Location (District)",
    "property_type": "Property Type",
}


# =========================================================
# LOAD MODEL
# =========================================================

print("Loading model...")

pipeline = joblib.load(
    MODEL_PATH
)


# =========================================================
# LOAD DATA
# =========================================================

print("Loading property data...")

df = pd.read_csv(
    DATA_PATH
)


X = df[
    FEATURES
].copy()


# =========================================================
# OPTIONAL SAMPLE
# =========================================================
#
# 500 rows is enough for a stable global explanation
# while keeping SHAP computation reasonably fast.
#

if len(X) > 500:

    X_shap = X.sample(
        n=500,
        random_state=42,
    )

else:

    X_shap = X.copy()


print(
    f"Calculating SHAP using "
    f"{len(X_shap):,} listings..."
)


# =========================================================
# ACCESS PIPELINE COMPONENTS
# =========================================================

preprocessor = pipeline.named_steps[
    "preprocessor"
]

model = pipeline.named_steps[
    "model"
]


# =========================================================
# TRANSFORM INPUT
# =========================================================

X_transformed = (
    preprocessor.transform(
        X_shap
    )
)


# Some sklearn transformations may return sparse matrices.
if hasattr(
    X_transformed,
    "toarray",
):

    X_transformed = (
        X_transformed.toarray()
    )


# =========================================================
# TRANSFORMED FEATURE NAMES
# =========================================================

transformed_names = (
    preprocessor
    .get_feature_names_out()
)


# =========================================================
# SHAP EXPLAINER
# =========================================================

explainer = shap.TreeExplainer(
    model
)

shap_values = explainer.shap_values(
    X_transformed
)


shap_values = np.asarray(
    shap_values
)


# =========================================================
# GROUP TRANSFORMED FEATURES
# BACK TO ORIGINAL FEATURES
# =========================================================

grouped_shap = {
    feature: np.zeros(
        len(X_shap)
    )
    for feature in FEATURES
}


for index, feature_name in enumerate(
    transformed_names
):

    name = str(
        feature_name
    ).lower()


    # -----------------------------------------------------
    # SIZE
    # -----------------------------------------------------

    if "size_m2" in name:

        grouped_shap[
            "size_m2"
        ] += shap_values[
            :,
            index
        ]


    # -----------------------------------------------------
    # BEDROOMS
    # -----------------------------------------------------

    elif "bedrooms" in name:

        grouped_shap[
            "bedrooms"
        ] += shap_values[
            :,
            index
        ]


    # -----------------------------------------------------
    # BATHROOMS
    # -----------------------------------------------------

    elif "bathrooms" in name:

        grouped_shap[
            "bathrooms"
        ] += shap_values[
            :,
            index
        ]


    # -----------------------------------------------------
    # FLOOR
    # -----------------------------------------------------

    elif "unit_floor" in name:

        grouped_shap[
            "unit_floor"
        ] += shap_values[
            :,
            index
        ]


    # -----------------------------------------------------
    # DISTRICT
    # -----------------------------------------------------

    elif "district" in name:

        grouped_shap[
            "district"
        ] += shap_values[
            :,
            index
        ]


    # -----------------------------------------------------
    # PROPERTY TYPE
    # -----------------------------------------------------

    elif "property_type" in name:

        grouped_shap[
            "property_type"
        ] += shap_values[
            :,
            index
        ]


# =========================================================
# GLOBAL IMPORTANCE
# =========================================================
#
# Global SHAP importance =
# average absolute SHAP value for each original feature.
#

results = []


for feature in FEATURES:

    values = grouped_shap[
        feature
    ]

    mean_abs_shap = float(
        np.mean(
            np.abs(
                values
            )
        )
    )

    mean_shap = float(
        np.mean(
            values
        )
    )


    results.append(
        {
            "feature":
                feature,

            "display_name":
                DISPLAY_NAMES[
                    feature
                ],

            "mean_abs_shap":
                mean_abs_shap,

            "mean_shap":
                mean_shap,
        }
    )


importance_df = (
    pd.DataFrame(
        results
    )
    .sort_values(
        "mean_abs_shap",
        ascending=False,
    )
    .reset_index(
        drop=True
    )
)


# =========================================================
# ADD RELATIVE IMPORTANCE
# =========================================================

total_importance = (
    importance_df[
        "mean_abs_shap"
    ].sum()
)


importance_df[
    "relative_importance"
] = (
    importance_df[
        "mean_abs_shap"
    ]
    / total_importance
    * 100
)


# =========================================================
# SAVE
# =========================================================

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


importance_df.to_csv(
    OUTPUT_PATH,
    index=False,
)


# =========================================================
# PRINT RESULTS
# =========================================================

print(
    "\nGlobal SHAP importance:\n"
)

print(
    importance_df.to_string(
        index=False
    )
)

print(
    f"\nSaved to:\n{OUTPUT_PATH}"
)