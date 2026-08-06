from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="replace",
    )


INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "bronze"
    / "khpropertyhub_com"
    / "raw_listings.json"
)


SALE_PRICE_MIN = 20_000
SALE_PRICE_MAX = 2_000_000
SIZE_MIN = 20
SIZE_MAX = 500
PPM2_MIN = 300
PPM2_MAX = 10_000
BEDROOM_MAX = 10
BATHROOM_MAX = 10
UNIT_FLOOR_MAX = 100


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def clean_text(value: Any) -> str | None:
    if is_missing(value):
        return None

    text = str(value)
    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\ufeff", "")
    text = re.sub(r"\s+", " ", text).strip()

    return text or None


def normalize_url(value: Any) -> str | None:
    text = clean_text(value)

    if text is None:
        return None

    try:
        parts = urlsplit(text)
    except ValueError:
        return text

    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            "",
            "",
        )
    )


def as_float(value: Any) -> float | None:
    if isinstance(value, bool) or is_missing(value):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).replace(",", "").replace("$", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)

    if not match:
        return None

    try:
        return float(match.group())
    except ValueError:
        return None


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Input file not found:\n{path}"
        )

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        raise TypeError(
            "Expected raw_listings.json to contain a JSON list."
        )

    return [
        row
        for row in data
        if isinstance(row, dict)
    ]


def price_per_m2(row: dict[str, Any]) -> float | None:
    price = as_float(row.get("price_usd"))
    size = as_float(row.get("size_m2"))

    if price is None or size is None:
        return None

    if price <= 0 or size <= 0:
        return None

    return round(price / size, 2)


def is_sale_like_profile(row: dict[str, Any]) -> bool:
    price = as_float(row.get("price_usd"))
    size = as_float(row.get("size_m2"))
    ppm2 = price_per_m2(row)

    return (
        price is not None
        and size is not None
        and ppm2 is not None
        and SALE_PRICE_MIN <= price <= SALE_PRICE_MAX
        and SIZE_MIN <= size <= SIZE_MAX
        and PPM2_MIN <= ppm2 <= PPM2_MAX
    )


def print_record(row: dict[str, Any]) -> None:
    print("\n" + "-" * 105)
    print("ID             :", row.get("listing_id"))
    print("Property code  :", row.get("property_code"))
    print("Title          :", row.get("title"))
    print("Listing type   :", row.get("listing_type"))
    print("Property type  :", row.get("property_type"))
    print("Price          :", row.get("price_usd"))
    print("Size           :", row.get("size_m2"))
    print("Price/m²       :", price_per_m2(row))
    print("Bedrooms       :", row.get("bedrooms"))
    print("Bedroom options:", row.get("bedroom_options"))
    print("Bathrooms      :", row.get("bathrooms"))
    print("Unit floor     :", row.get("unit_floor"))
    print("Building floors:", row.get("building_total_floors"))
    print("District       :", row.get("district"))
    print("Review flag    :", row.get("needs_manual_review"))
    print("Out of scope   :", row.get("out_of_scope_reason"))

    for key, value in row.items():
        if (
            key.endswith("_conflict")
            or key.endswith("_reference_mismatch")
            or key.endswith("_search_mismatch")
        ) and value:
            print(f"{key:<30}: {value}")

    print("URL            :", row.get("url"))


def print_group(
    title: str,
    rows: list[dict[str, Any]],
    limit: int = 10,
) -> None:
    print("\n" + "=" * 105)
    print(f"{title}: {len(rows)} records")
    print("=" * 105)

    for row in rows[:limit]:
        print_record(row)


def main() -> None:
    records = load_records(INPUT_PATH)

    rent_only = [
        row for row in records
        if row.get("listing_type") == "rent"
    ]

    sale_rent = [
        row for row in records
        if row.get("listing_type") == "sale/rent"
    ]

    sale_rent_sale_like = [
        row for row in sale_rent
        if is_sale_like_profile(row)
    ]

    sale_rent_ambiguous = [
        row for row in sale_rent
        if not is_sale_like_profile(row)
    ]

    non_condo = [
        row for row in records
        if row.get("property_type")
        not in {"Condo", "Penthouse"}
    ]

    multi_unit = [
        row for row in records
        if row.get("multi_unit_options")
        or row.get("bedroom_options")
    ]

    missing_size = [
        row for row in records
        if is_missing(row.get("size_m2"))
    ]

    low_price = [
        row for row in records
        if (
            as_float(row.get("price_usd")) is not None
            and as_float(row.get("price_usd")) < SALE_PRICE_MIN
        )
    ]

    high_price = [
        row for row in records
        if (
            as_float(row.get("price_usd")) is not None
            and as_float(row.get("price_usd")) > SALE_PRICE_MAX
        )
    ]

    small_size = [
        row for row in records
        if (
            as_float(row.get("size_m2")) is not None
            and as_float(row.get("size_m2")) < SIZE_MIN
        )
    ]

    large_size = [
        row for row in records
        if (
            as_float(row.get("size_m2")) is not None
            and as_float(row.get("size_m2")) > SIZE_MAX
        )
    ]

    low_ppm2 = [
        row for row in records
        if (
            price_per_m2(row) is not None
            and price_per_m2(row) < PPM2_MIN
        )
    ]

    high_ppm2 = [
        row for row in records
        if (
            price_per_m2(row) is not None
            and price_per_m2(row) > PPM2_MAX
        )
    ]

    high_bedrooms = [
        row for row in records
        if (
            as_float(row.get("bedrooms")) is not None
            and as_float(row.get("bedrooms")) > BEDROOM_MAX
        )
    ]

    high_bathrooms = [
        row for row in records
        if (
            as_float(row.get("bathrooms")) is not None
            and as_float(row.get("bathrooms")) > BATHROOM_MAX
        )
    ]

    high_floor = [
        row for row in records
        if (
            as_float(row.get("unit_floor")) is not None
            and as_float(row.get("unit_floor")) > UNIT_FLOOR_MAX
        )
    ]

    floor_above_building = []

    for row in records:
        unit_floor = as_float(row.get("unit_floor"))
        total_floors = as_float(
            row.get("building_total_floors")
        )

        if (
            unit_floor is not None
            and total_floors is not None
            and unit_floor > total_floors
        ):
            floor_above_building.append(row)

    review_true = [
        row for row in records
        if row.get("needs_manual_review") is True
    ]

    floor_conflicts = [
        row for row in records
        if row.get("unit_floor_conflict")
    ]

    bedroom_conflicts = [
        row for row in records
        if row.get("bedrooms_conflict")
    ]

    property_conflicts = [
        row for row in records
        if row.get("property_type_conflict")
    ]

    search_mismatches = [
        row for row in records
        if row.get("listing_type_search_mismatch")
    ]

    out_of_scope_counts = Counter(
        clean_text(row.get("out_of_scope_reason"))
        for row in records
        if clean_text(row.get("out_of_scope_reason"))
    )

    property_codes = defaultdict(list)

    for row in records:
        code = clean_text(row.get("property_code"))

        if code:
            property_codes[code].append(row)

    duplicate_code_groups = {
        code: rows
        for code, rows in property_codes.items()
        if len(rows) > 1
    }

    duplicate_code_records = sum(
        len(rows)
        for rows in duplicate_code_groups.values()
    )

    urls = Counter(
        normalize_url(row.get("url"))
        for row in records
        if normalize_url(row.get("url"))
    )

    duplicate_urls = {
        url: count
        for url, count in urls.items()
        if count > 1
    }

    print("\nKHPROPERTYHUB CLEANING DECISION AUDIT")
    print("=" * 105)
    print(f"Total Bronze records                : {len(records):,}")
    print(f"True manual-review flags            : {len(review_true):,}")
    print(f"Rent-only records                   : {len(rent_only):,}")
    print(f"Sale/rent records                   : {len(sale_rent):,}")
    print(f"  Sale-like numeric profile         : {len(sale_rent_sale_like):,}")
    print(f"  Ambiguous numeric profile         : {len(sale_rent_ambiguous):,}")
    print(f"Non-condo property types            : {len(non_condo):,}")
    print(f"Multi-unit advertisements           : {len(multi_unit):,}")
    print(f"Missing size                        : {len(missing_size):,}")
    print(f"Price below ${SALE_PRICE_MIN:,}             : {len(low_price):,}")
    print(f"Price above ${SALE_PRICE_MAX:,}          : {len(high_price):,}")
    print(f"Size below {SIZE_MIN}m²                    : {len(small_size):,}")
    print(f"Size above {SIZE_MAX}m²                   : {len(large_size):,}")
    print(f"Price/m² below ${PPM2_MIN:,}              : {len(low_ppm2):,}")
    print(f"Price/m² above ${PPM2_MAX:,}           : {len(high_ppm2):,}")
    print(f"Bedrooms above {BEDROOM_MAX}               : {len(high_bedrooms):,}")
    print(f"Bathrooms above {BATHROOM_MAX}              : {len(high_bathrooms):,}")
    print(f"Unit floor above {UNIT_FLOOR_MAX}             : {len(high_floor):,}")
    print(f"Unit floor > building floors        : {len(floor_above_building):,}")
    print(f"Property-type conflicts             : {len(property_conflicts):,}")
    print(f"Bedroom conflicts                   : {len(bedroom_conflicts):,}")
    print(f"Unit-floor conflicts                : {len(floor_conflicts):,}")
    print(f"Listing/search mismatches           : {len(search_mismatches):,}")
    print(f"Duplicate URL groups                : {len(duplicate_urls):,}")
    print(f"Duplicate property-code groups      : {len(duplicate_code_groups):,}")
    print(f"Records in duplicate-code groups    : {duplicate_code_records:,}")

    print("\nOUT-OF-SCOPE REASONS")
    print("-" * 105)

    if out_of_scope_counts:
        for reason, count in out_of_scope_counts.most_common():
            print(f"{reason:<75}: {count}")
    else:
        print("No out-of-scope reasons found.")

    print("\nDUPLICATE PROPERTY-CODE GROUPS")
    print("-" * 105)

    if duplicate_code_groups:
        for code, rows in list(
            sorted(
                duplicate_code_groups.items(),
                key=lambda item: len(item[1]),
                reverse=True,
            )
        )[:20]:
            print(f"\nProperty code: {code} | records: {len(rows)}")

            for row in rows:
                print(
                    "  -",
                    row.get("listing_id"),
                    "|",
                    row.get("title"),
                    "|",
                    row.get("price_usd"),
                    "|",
                    row.get("size_m2"),
                )
    else:
        print("No duplicate property-code groups found.")

    print_group(
        "SALE/RENT — SALE-LIKE",
        sale_rent_sale_like,
        limit=10,
    )

    print_group(
        "SALE/RENT — AMBIGUOUS",
        sale_rent_ambiguous,
        limit=10,
    )

    print_group(
        "NON-CONDO PROPERTY",
        non_condo,
        limit=15,
    )

    print_group(
        "MULTI-UNIT ADVERTISEMENT",
        multi_unit,
        limit=10,
    )

    print_group(
        "LOW-PRICE",
        low_price,
        limit=15,
    )

    print_group(
        "HIGH-PRICE",
        high_price,
        limit=10,
    )

    print_group(
        "SMALL-SIZE",
        small_size,
        limit=10,
    )

    print_group(
        "LARGE-SIZE",
        large_size,
        limit=10,
    )

    print_group(
        "LOW PRICE/M²",
        low_ppm2,
        limit=15,
    )

    print_group(
        "HIGH PRICE/M²",
        high_ppm2,
        limit=10,
    )

    print_group(
        "BEDROOMS ABOVE LIMIT",
        high_bedrooms,
        limit=10,
    )

    print_group(
        "BATHROOMS ABOVE LIMIT",
        high_bathrooms,
        limit=10,
    )

    print_group(
        "UNIT-FLOOR CONFLICT",
        floor_conflicts,
        limit=10,
    )

    print_group(
        "LISTING/SEARCH MISMATCH",
        search_mismatches,
        limit=15,
    )

    print("\n" + "=" * 105)
    print("KHPropertyHub decision audit completed.")
    print("=" * 105)


if __name__ == "__main__":
    main()
