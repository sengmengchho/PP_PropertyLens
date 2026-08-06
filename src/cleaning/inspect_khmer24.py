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


POSSIBLE_INPUT_PATHS = [
    PROJECT_ROOT
    / "data"
    / "bronze"
    / "khmer24"
    / "raw_listings.json",

    PROJECT_ROOT
    / "data"
    / "bronze"
    / "khmer24_com"
    / "raw_listings.json",
]


IMPORTANT_COLUMNS = [
    "listing_id",
    "source",
    "url",
    "title",
    "description",

    "listing_type",
    "property_type",
    "category",

    "price_usd",
    "size_m2",
    "bedrooms",
    "bathrooms",
    "unit_floor",
    "building_total_floors",

    "province",
    "district",
    "commune",
    "location_text",
    "address",

    "seller_name",
    "seller_type",

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


def find_input_path() -> Path:
    for path in POSSIBLE_INPUT_PATHS:
        if path.exists():
            return path

    checked = "\n".join(
        str(path)
        for path in POSSIBLE_INPUT_PATHS
    )

    raise FileNotFoundError(
        "Khmer24 Bronze file was not found.\n"
        f"Checked:\n{checked}"
    )


def collect_all_columns(
    records: list[dict[str, Any]],
) -> list[str]:
    return sorted(
        {
            key
            for record in records
            for key in record.keys()
        }
    )


def show_column_profile(
    records: list[dict[str, Any]],
) -> None:
    total = len(records)
    columns = collect_all_columns(records)

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
    print("=" * 105)
    print(
        f"{'Column':<44}"
        f"{'Non-missing':>14}"
        f"{'Missing':>12}"
        f"{'Coverage':>12}"
        f"  Types"
    )
    print("-" * 105)

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
            f"{column:<44}"
            f"{non_missing:>14}"
            f"{missing:>12}"
            f"{coverage:>11.1f}%"
            f"  {types}"
        )


def show_important_columns(
    records: list[dict[str, Any]],
) -> None:
    total = len(records)

    print("\nIMPORTANT COLUMN COVERAGE")
    print("=" * 85)
    print(
        f"{'Column':<34}"
        f"{'Non-missing':>14}"
        f"{'Missing':>12}"
        f"{'Coverage':>12}"
    )
    print("-" * 85)

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
            f"{column:<34}"
            f"{non_missing:>14}"
            f"{missing:>12}"
            f"{coverage:>11.1f}%"
        )


def show_value_counts(
    records: list[dict[str, Any]],
    column: str,
    limit: int = 25,
) -> None:
    values = Counter(
        str(record.get(column)).strip()
        for record in records
        if not is_missing(record.get(column))
    )

    print(f"\n{column.upper()} VALUES")
    print("=" * 75)

    if not values:
        print("No values found.")
        return

    for value, count in values.most_common(limit):
        print(f"{value:<55}: {count}")


def show_numeric_ranges(
    records: list[dict[str, Any]],
) -> None:
    print("\nNUMERIC RANGES")
    print("=" * 85)
    print(
        f"{'Column':<32}"
        f"{'Count':>10}"
        f"{'Minimum':>16}"
        f"{'Maximum':>16}"
    )
    print("-" * 85)

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
                f"{column:<32}"
                f"{len(values):>10}"
                f"{min(values):>16,.2f}"
                f"{max(values):>16,.2f}"
            )
        else:
            print(
                f"{column:<32}"
                f"{0:>10}"
                f"{'N/A':>16}"
                f"{'N/A':>16}"
            )


def show_duplicate_check(
    records: list[dict[str, Any]],
) -> None:
    ids = Counter(
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
        for value, count in ids.items()
        if count > 1
    }

    duplicate_urls = {
        value: count
        for value, count in urls.items()
        if count > 1
    }

    print("\nIDENTITY DUPLICATE CHECK")
    print("=" * 75)
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


def show_review_examples(
    records: list[dict[str, Any]],
) -> None:
    review_records = [
        record
        for record in records
        if record.get("needs_manual_review")
    ]

    print("\nBRONZE REVIEW RECORDS")
    print("=" * 95)
    print(f"Review records: {len(review_records)}")

    for record in review_records[:15]:
        print("\n" + "-" * 95)
        print("ID          :", record.get("listing_id"))
        print("Title       :", record.get("title"))
        print("Listing type:", record.get("listing_type"))
        print("Property    :", record.get("property_type"))
        print("Price       :", record.get("price_usd"))
        print("Size        :", record.get("size_m2"))
        print("Bedrooms    :", record.get("bedrooms"))
        print("Bathrooms   :", record.get("bathrooms"))
        print("Unit floor  :", record.get("unit_floor"))

        for key, value in record.items():
            if key.endswith("_conflict") and value:
                print(f"{key:<28}: {value}")

        print("URL         :", record.get("url"))


def show_sample_records(
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
        "district",
        "commune",
        "needs_manual_review",
        "url",
    ]

    print("\nSAMPLE RECORDS")
    print("=" * 95)

    for index, record in enumerate(
        records[:limit],
        start=1,
    ):
        print(f"\nRECORD {index}")
        print("-" * 95)

        for column in columns:
            print(
                f"{column:<27}: "
                f"{record.get(column)}"
            )


def main() -> None:
    input_path = find_input_path()
    records = load_json_records(input_path)

    print("\nKHMER24 RAW DATA INSPECTION")
    print("=" * 105)
    print(f"Input file : {input_path}")
    print(f"Total rows : {len(records):,}")

    show_column_profile(records)
    show_important_columns(records)

    for column in [
        "listing_type",
        "property_type",
        "category",
        "province",
        "district",
        "commune",
        "seller_type",
    ]:
        show_value_counts(records, column)

    show_numeric_ranges(records)
    show_duplicate_check(records)
    show_review_examples(records)
    show_sample_records(records)

    print("\n" + "=" * 105)
    print("Khmer24 inspection completed.")
    print("=" * 105)


if __name__ == "__main__":
    main()