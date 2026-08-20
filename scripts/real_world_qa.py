from pathlib import Path

import pandas as pd

from src.prediction.predict import (
    explain_prediction,
    VALID_DISTRICTS,
    VALID_PROPERTY_TYPES,
)


# =========================================================
# PATHS
# =========================================================

INPUT_PATH = Path(
    "data/qa/real_world_validation.csv"
)

OUTPUT_PATH = Path(
    "data/qa/real_world_validation_results.csv"
)

OUTPUT_PATH.parent.mkdir(
    parents=True,
    exist_ok=True,
)


# =========================================================
# LOAD DATA
# =========================================================

df = pd.read_csv(
    INPUT_PATH
)


# =========================================================
# CLEAN COLUMN NAMES
# =========================================================

df.columns = (
    df.columns
    .str.strip()
    .str.lower()
)


# =========================================================
# REQUIRED COLUMNS
# =========================================================

required_columns = [
    "listing_name",
    "property_type",
    "district",
    "size_m2",
    "bedrooms",
    "bathrooms",
    "unit_floor",
    "advertised_price_usd",
]


missing_columns = [
    column
    for column in required_columns
    if column not in df.columns
]


if missing_columns:

    raise ValueError(
        f"Missing CSV columns: "
        f"{missing_columns}"
    )


# =========================================================
# CLEAN TEXT VALUES
# =========================================================

text_columns = [
    "listing_name",
    "property_type",
    "district",
]

if "source_url" in df.columns:
    text_columns.append(
        "source_url"
    )


for column in text_columns:

    df[column] = (
        df[column]
        .astype("string")
        .str.strip()
    )

# =========================================================
# NORMALIZE MODEL CATEGORIES
# =========================================================

# Build case-insensitive lookup from the exact categories
# learned by the trained model.

property_type_lookup = {
    str(value).strip().casefold(): value
    for value in VALID_PROPERTY_TYPES
}

district_lookup = {
    str(value).strip().casefold(): value
    for value in VALID_DISTRICTS
}


def normalize_category(value, lookup):

    if pd.isna(value):
        return None

    cleaned = str(value).strip()

    return lookup.get(
        cleaned.casefold(),
        cleaned,
    )


df["property_type"] = df[
    "property_type"
].apply(
    lambda value: normalize_category(
        value,
        property_type_lookup,
    )
)


df["district"] = df[
    "district"
].apply(
    lambda value: normalize_category(
        value,
        district_lookup,
    )
)


# =========================================================
# CLEAN NUMERIC VALUES
# =========================================================

numeric_columns = [
    "size_m2",
    "bedrooms",
    "bathrooms",
    "unit_floor",
    "advertised_price_usd",
]


for column in numeric_columns:

    df[column] = pd.to_numeric(
        df[column],
        errors="coerce",
    )


# =========================================================
# CHECK VALID DISTRICTS
# =========================================================

invalid_districts = (
    df.loc[
        df["district"].notna()
        &
        ~df["district"].isin(
            VALID_DISTRICTS
        ),
        "district",
    ]
    .unique()
)


if len(invalid_districts) > 0:

    print(
        "\nDistricts not recognized "
        "by the model:"
    )

    for district in invalid_districts:

        print(
            f"- {repr(district)}"
        )

    raise ValueError(
        "Please correct the district names "
        "before running QA."
    )


# =========================================================
# CHECK VALID PROPERTY TYPES
# =========================================================

invalid_property_types = (
    df.loc[
        ~df["property_type"].isin(
            VALID_PROPERTY_TYPES
        ),
        "property_type",
    ]
    .dropna()
    .unique()
)


if len(invalid_property_types) > 0:

    print(
        "\nProperty types not recognized "
        "by the model:"
    )

    for property_type in invalid_property_types:

        print(
            f"- {repr(property_type)}"
        )

    raise ValueError(
        "Please correct the property types "
        "before running QA."
    )


# =========================================================
# QA PREDICTIONS
# =========================================================

results = []


for index, row in df.iterrows():

    try:

        # ---------------------------------------------
        # REQUIRED VALUES
        # ---------------------------------------------

        if pd.isna(
            row["size_m2"]
        ):
            raise ValueError(
                "size_m2 is missing."
            )

        if pd.isna(
            row["advertised_price_usd"]
        ):
            raise ValueError(
                "advertised_price_usd is missing."
            )

        if row["advertised_price_usd"] <= 0:
            raise ValueError(
                "advertised_price_usd must be greater than 0."
            )


        # ---------------------------------------------
        # HANDLE OPTIONAL VALUES
        # ---------------------------------------------

        bedrooms = (
            None
            if pd.isna(
                row["bedrooms"]
            )
            else int(
                row["bedrooms"]
            )
        )


        bathrooms = (
            None
            if pd.isna(
                row["bathrooms"]
            )
            else int(
                row["bathrooms"]
            )
        )


        unit_floor = (
            None
            if pd.isna(
                row["unit_floor"]
            )
            else int(
                row["unit_floor"]
            )
        )


        district = (
            None
            if pd.isna(
                row["district"]
            )
            else str(
                row["district"]
            )
        )


        # ---------------------------------------------
        # PREDICTION
        # ---------------------------------------------

        prediction = explain_prediction(
            size_m2=float(
                row["size_m2"]
            ),
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            unit_floor=unit_floor,
            district=district,
            property_type=str(
                row["property_type"]
            ),
        )


        # ---------------------------------------------
        # ACTUAL VS PREDICTED
        # ---------------------------------------------

        actual = float(
            row[
                "advertised_price_usd"
            ]
        )

        predicted = float(
            prediction[
                "estimated_price_usd"
            ]
        )

        lower = float(
            prediction[
                "lower_price_usd"
            ]
        )

        upper = float(
            prediction[
                "upper_price_usd"
            ]
        )


        absolute_error = abs(
            actual - predicted
        )


        percentage_error = (
            absolute_error
            / actual
            * 100
        )


        inside_range = (
            lower
            <= actual
            <= upper
        )


        # ---------------------------------------------
        # SAVE RESULT
        # ---------------------------------------------

        results.append({
            "listing_name":
                row["listing_name"],

            "property_type":
                row["property_type"],

            "district":
                district,

            "size_m2":
                row["size_m2"],

            "bedrooms":
                bedrooms,

            "bathrooms":
                bathrooms,

            "unit_floor":
                unit_floor,

            "advertised_price_usd":
                actual,

            "estimated_price_usd":
                predicted,

            "lower_price_usd":
                lower,

            "upper_price_usd":
                upper,

            "absolute_error_usd":
                absolute_error,

            "percentage_error":
                percentage_error,

            "inside_range":
                inside_range,

            "source_url":
                (
                    row["source_url"]
                    if "source_url" in df.columns
                    else None
                ),

            "status":
                "success",

            "error":
                None,
        })


    except Exception as error:

        print(
            f"Row {index + 1} failed: "
            f"{error}"
        )

        results.append({
            "listing_name":
                row.get(
                    "listing_name",
                    f"Row {index + 1}",
                ),

            "property_type":
                row.get(
                    "property_type"
                ),

            "district":
                row.get(
                    "district"
                ),

            "size_m2":
                row.get(
                    "size_m2"
                ),

            "bedrooms":
                row.get(
                    "bedrooms"
                ),

            "bathrooms":
                row.get(
                    "bathrooms"
                ),

            "unit_floor":
                row.get(
                    "unit_floor"
                ),

            "advertised_price_usd":
                row.get(
                    "advertised_price_usd"
                ),

            "estimated_price_usd":
                None,

            "lower_price_usd":
                None,

            "upper_price_usd":
                None,

            "absolute_error_usd":
                None,

            "percentage_error":
                None,

            "inside_range":
                None,

            "source_url":
                (
                    row.get(
                        "source_url"
                    )
                    if "source_url" in df.columns
                    else None
                ),

            "status":
                "failed",

            "error":
                str(error),
        })


# =========================================================
# CREATE RESULT DATAFRAME
# =========================================================

results_df = pd.DataFrame(
    results
)


# =========================================================
# SAVE
# =========================================================

results_df.to_csv(
    OUTPUT_PATH,
    index=False,
)


# =========================================================
# SUCCESSFUL ROWS ONLY
# =========================================================

successful_df = results_df[
    results_df["status"]
    == "success"
].copy()


# =========================================================
# DISPLAY RESULTS
# =========================================================

print(
    "\nReal-World QA Results"
)

print(
    "=" * 80
)


if not successful_df.empty:

    print(
        successful_df[
            [
                "listing_name",
                "advertised_price_usd",
                "estimated_price_usd",
                "percentage_error",
                "inside_range",
            ]
        ]
    )


# =========================================================
# SUMMARY
# =========================================================

print(
    "\nReal-World QA Summary"
)

print(
    "=" * 60
)


print(
    f"Total listings: "
    f"{len(results_df)}"
)

print(
    f"Successful predictions: "
    f"{len(successful_df)}"
)

print(
    f"Failed predictions: "
    f"{(
        results_df['status']
        == 'failed'
    ).sum()}"
)


if not successful_df.empty:

    print(
        f"Mean percentage error: "
        f"{successful_df['percentage_error'].mean():.2f}%"
    )

    print(
        f"Median percentage error: "
        f"{successful_df['percentage_error'].median():.2f}%"
    )

    print(
        f"Inside estimated range: "
        f"{successful_df['inside_range'].mean() * 100:.2f}%"
    )


print(
    f"\nResults saved to: "
    f"{OUTPUT_PATH}"
)

print(
    results_df[
        [
            "listing_name",
            "advertised_price_usd",
            "estimated_price_usd",
            "lower_price_usd",
            "upper_price_usd",
            "percentage_error",
            "inside_range",
        ]
    ]
    .sort_values(
        "percentage_error",
        ascending=False,
    )
    .to_string(index=False)
)