from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="replace",
    )

from src.cleaning.common import (
    is_missing,
    load_json_records,
    normalize_url,
)


INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "bronze"
    / "khpropertyhub_com"
    / "raw_listings.json"
)


IMPORTANT_COLUMNS = [
    "listing_id",
    "source",
    "url",
    "title",
    "description",

    "listing_type",
    "property_type",

    "price_usd",
    "size_m2",
    "bedrooms",
    "bathrooms",
    "unit_floor",
    "building_total_floors",

    "bedroom_options",
    "multi_unit_options",

    "district",
    "commune",
    "address",
    "location_text",
    "project_name",

    "created_at",
    "scraped_at",

    "needs_manual_review",
]


NUMERIC_COLUMNS = [
    "price_usd",
    "size_m2",
    "bedrooms",
    "bathrooms",
    "unit_floor",
    "building_total_floors",
]


def collect_columns(
    records: list[dict[str, Any]],
) -> list[str]:
    return sorted(
        {
            column
            for record in records
            for column in record.keys()
        }
    )


def show_column_profile(
    records: list[dict[str, Any]],
) -> None:
    total = len(records)
    columns = collect_columns(records)

    non_missing_counts: Counter[str] = Counter()
    type_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for record in records:
        for column in columns:
            value = record.get(column)

            if not is_missing(value):
                non_missing_counts[column] += 1
                type_counts[column][
                    type(value).__name__
                ] += 1

    print("\nALL RAW COLUMNS")
    print("=" * 110)
    print(
        f"{'Column':<47}"
        f"{'Non-missing':>14}"
        f"{'Missing':>12}"
        f"{'Coverage':>12}"
        f"  Types"
    )
    print("-" * 110)

    for column in columns:
        non_missing = non_missing_counts[column]
        missing = total - non_missing

        coverage = (
            non_missing / total * 100
            if total
            else 0
        )

        types = ", ".join(
            f"{name}:{count}"
            for name, count
            in type_counts[column].most_common()
        )

        print(
            f"{column:<47}"
            f"{non_missing:>14}"
            f"{missing:>12}"
            f"{coverage:>11.1f}%"
            f"  {types}"
        )


def show_important_coverage(
    records: list[dict[str, Any]],
) -> None:
    total = len(records)

    print("\nIMPORTANT COLUMN COVERAGE")
    print("=" * 88)
    print(
        f"{'Column':<37}"
        f"{'Non-missing':>14}"
        f"{'Missing':>12}"
        f"{'Coverage':>12}"
    )
    print("-" * 88)

    for column in IMPORTANT_COLUMNS:
        non_missing = sum(
            not is_missing(record.get(column))
            for record in records
        )

        missing = total - non_missing

        coverage = (
            non_missing / total * 100
            if total
            else 0
        )

        print(
            f"{column:<37}"
            f"{non_missing:>14}"
            f"{missing:>12}"
            f"{coverage:>11.1f}%"
        )


def show_value_counts(
    records: list[dict[str, Any]],
    column: str,
    limit: int = 30,
) -> None:
    counts = Counter(
        str(record.get(column)).strip()
        for record in records
        if not is_missing(record.get(column))
    )

    print(f"\n{column.upper()} VALUES")
    print("=" * 78)

    if not counts:
        print("No values found.")
        return

    for value, count in counts.most_common(limit):
        print(f"{value:<58}: {count}")


def show_numeric_ranges(
    records: list[dict[str, Any]],
) -> None:
    print("\nNUMERIC RANGES")
    print("=" * 88)
    print(
        f"{'Column':<35}"
        f"{'Count':>10}"
        f"{'Minimum':>17}"
        f"{'Maximum':>17}"
    )
    print("-" * 88)

    for column in NUMERIC_COLUMNS:
        values: list[float] = []

        for record in records:
            value = record.get(column)

            if isinstance(value, bool):
                continue

            if isinstance(value, (int, float)):
                values.append(float(value))

        if values:
            print(
                f"{column:<35}"
                f"{len(values):>10}"
                f"{min(values):>17,.2f}"
                f"{max(values):>17,.2f}"
            )
        else:
            print(
                f"{column:<35}"
                f"{0:>10}"
                f"{'N/A':>17}"
                f"{'N/A':>17}"
            )


def show_conflict_counts(
    records: list[dict[str, Any]],
) -> None:
    counts: Counter[str] = Counter()

    for record in records:
        for key, value in record.items():
            if key.endswith("_conflict") and value:
                counts[key] += 1

    print("\nCONFLICT COUNTS")
    print("=" * 80)

    if not counts:
        print("No conflict fields found.")
        return

    for key, count in counts.most_common():
        print(f"{key:<55}: {count}")


def show_field_source_counts(
    records: list[dict[str, Any]],
) -> None:
    fields = [
        "price_usd_source",
        "size_m2_source",
        "bedrooms_source",
        "bathrooms_source",
        "unit_floor_source",
        "property_type_source",
        "listing_type_source",
    ]

    for field in fields:
        counts = Counter(
            str(record.get(field))
            for record in records
            if not is_missing(record.get(field))
        )

        print(f"\n{field.upper()}")
        print("=" * 85)

        if not counts:
            print("No values found.")
            continue

        for value, count in counts.most_common(20):
            print(f"{value:<68}: {count}")


def show_duplicate_check(
    records: list[dict[str, Any]],
) -> None:
    listing_ids = Counter(
        str(record.get("listing_id")).strip()
        for record in records
        if not is_missing(record.get("listing_id"))
    )

    urls = Counter(
        normalize_url(record.get("url"))
        for record in records
        if normalize_url(record.get("url"))
    )

    duplicate_ids = {
        value: count
        for value, count in listing_ids.items()
        if count > 1
    }

    duplicate_urls = {
        value: count
        for value, count in urls.items()
        if count > 1
    }

    print("\nIDENTITY DUPLICATE CHECK")
    print("=" * 78)
    print(
        f"Duplicate listing IDs : {len(duplicate_ids)}"
    )
    print(
        f"Duplicate URLs        : {len(duplicate_urls)}"
    )

    if duplicate_ids:
        print("\nDUPLICATE ID EXAMPLES")

        for value, count in list(
            duplicate_ids.items()
        )[:10]:
            print(f"{value}: {count}")

    if duplicate_urls:
        print("\nDUPLICATE URL EXAMPLES")

        for value, count in list(
            duplicate_urls.items()
        )[:10]:
            print(f"{value}: {count}")


def show_review_records(
    records: list[dict[str, Any]],
) -> None:
    reviews = [
        record
        for record in records
        if record.get("needs_manual_review")
    ]

    print("\nBRONZE REVIEW RECORDS")
    print("=" * 100)
    print(f"Review records: {len(reviews)}")

    for record in reviews[:30]:
        print("\n" + "-" * 100)
        print("ID          :", record.get("listing_id"))
        print("Title       :", record.get("title"))
        print("Listing type:", record.get("listing_type"))
        print("Property    :", record.get("property_type"))
        print("Price       :", record.get("price_usd"))
        print("Size        :", record.get("size_m2"))
        print("Bedrooms    :", record.get("bedrooms"))
        print("Bed options :", record.get("bedroom_options"))
        print("Multi-unit  :", record.get("multi_unit_options"))
        print("Bathrooms   :", record.get("bathrooms"))
        print("Unit floor  :", record.get("unit_floor"))
        print("District    :", record.get("district"))

        for key, value in record.items():
            if key.endswith("_conflict") and value:
                print(f"{key:<34}: {value}")

        print("URL         :", record.get("url"))


def show_special_groups(
    records: list[dict[str, Any]],
) -> None:
    rent = [
        row
        for row in records
        if row.get("listing_type") == "rent"
    ]

    sale_rent = [
        row
        for row in records
        if row.get("listing_type") == "sale/rent"
    ]

    multi_unit = [
        row
        for row in records
        if row.get("multi_unit_options")
    ]

    missing_price = [
        row
        for row in records
        if is_missing(row.get("price_usd"))
    ]

    missing_size = [
        row
        for row in records
        if is_missing(row.get("size_m2"))
    ]

    print("\nSPECIAL GROUP COUNTS")
    print("=" * 80)
    print(f"Rent-only records       : {len(rent)}")
    print(f"Sale/rent records       : {len(sale_rent)}")
    print(f"Multi-unit records      : {len(multi_unit)}")
    print(f"Missing price           : {len(missing_price)}")
    print(f"Missing size            : {len(missing_size)}")


def show_samples(
    records: list[dict[str, Any]],
    limit: int = 5,
) -> None:
    columns = [
        "listing_id",
        "title",
        "listing_type",
        "property_type",
        "price_usd",
        "size_m2",
        "bedrooms",
        "bathrooms",
        "unit_floor",
        "building_total_floors",
        "district",
        "bedroom_options",
        "multi_unit_options",
        "needs_manual_review",
        "url",
    ]

    print("\nSAMPLE RECORDS")
    print("=" * 100)

    for index, record in enumerate(
        records[:limit],
        start=1,
    ):
        print(f"\nRECORD {index}")
        print("-" * 100)

        for column in columns:
            print(
                f"{column:<30}: "
                f"{record.get(column)}"
            )


def main() -> None:
    records = load_json_records(INPUT_PATH)

    print("\nKHPROPERTYHUB RAW DATA INSPECTION")
    print("=" * 110)
    print(f"Input file : {INPUT_PATH}")
    print(f"Total rows : {len(records):,}")

    show_column_profile(records)
    show_important_coverage(records)

    for column in [
        "listing_type",
        "property_type",
        "district",
    ]:
        show_value_counts(records, column)

    show_numeric_ranges(records)
    show_special_groups(records)
    show_conflict_counts(records)
    show_field_source_counts(records)
    show_duplicate_check(records)
    show_review_records(records)
    show_samples(records)

    print("\n" + "=" * 110)
    print("KHPropertyHub inspection completed.")
    print("=" * 110)


if __name__ == "__main__":
    main()