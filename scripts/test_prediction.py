from src.prediction.predict import (
    explain_prediction,
)


# =========================================================
# HELPER
# =========================================================

def format_usd_effect(value):
    sign = "+" if value >= 0 else "-"

    value = abs(value)

    if value >= 1_000:
        return f"{sign}${value / 1000:.1f}K"

    return f"{sign}${value:,.0f}"


# =========================================================
# TEST PROPERTY
# =========================================================

result = explain_prediction(
    size_m2=70,
    bedrooms=2,
    bathrooms=None,
    unit_floor=None,
    district="Boeung Keng Kang",
    property_type="Condo",
)


# =========================================================
# ESTIMATED PRICE
# =========================================================

print("\nEstimated Asking Price")
print("=" * 60)

print(
    f"${result['estimated_price_usd']:,.0f}"
)


print("\nEstimated Price Range")
print("=" * 60)

print(
    f"${result['lower_price_usd']:,.0f}"
    f" – "
    f"${result['upper_price_usd']:,.0f}"
)


print(
    f"\nRange level: "
    f"{result['interval_level']:.0%}"
)

print("\nMain Factors")
print("=" * 60)

provided_factors = [
    item
    for item in result["explanations"]
    if item["value"] != "Not provided"
]


for item in provided_factors[:4]:

    print(
        f"\n{item['display_feature']}"
    )

    print(
        f"  Value        : "
        f"{item['value']}"
    )

    print(
        f"  Influence    : "
        f"{item['impact_level']}"
    )


# =========================================================
# ABOUT PRICE RANGE
# =========================================================

print("\nAbout the Price Range")
print("=" * 60)

print(
    "This range reflects uncertainty in the "
    "model's prediction."
)

print(
    "On the final test data, about 78% of actual asking prices" \
    " fell within these ranges."
)

# =========================================================
# SEPARATE PROVIDED AND MISSING FACTORS
# =========================================================

provided_factors = []
missing_factors = []

for item in result["explanations"]:

    if item["value"] == "Not provided":
        missing_factors.append(item)

    else:
        provided_factors.append(item)



# =========================================================
# MISSING INFORMATION
# =========================================================

if missing_factors:

    print("\nMissing Information")
    print("=" * 60)

    for item in missing_factors:

        print(
            f"- {item['display_feature']}: "
            f"Not provided"
        )

    print(
        "\nThe model handled these missing "
        "values automatically."
    )

    print(
        "Providing this information may "
        "improve the estimate."
    )



# =========================================================
# DISCLAIMER
# =========================================================

print("\nDisclaimer")
print("=" * 60)

print(
    "This is a data-based estimate from "
    "advertised property listings and is "
    "not an official property valuation."
)

