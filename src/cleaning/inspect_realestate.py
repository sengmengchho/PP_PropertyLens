from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "bronze"
    / "realestate"
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
    "district",
    "commune",
    "address",
    "project_name",
    "latitude",
    "longitude",
    "created_at",
    "scraped_at",
]


def is_missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Input file was not found:\n{path}"
        )

    try:
        data = json.loads(
            path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            f"The JSON file is invalid:\n{error}"
        ) from error

    if not isinstance(data, list):
        raise TypeError(
            "Expected raw_listings.json to contain a JSON list."
        )

    records = [
        row for row in data
        if isinstance(row, dict)
    ]

    return records


def display_all_columns(
    records: list[dict[str, Any]],
) -> None:
    non_missing_counts: Counter[str] = Counter()
    type_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for row in records:
        for key, value in row.items():
            if not is_missing(value):
                non_missing_counts[key] += 1
                type_counts[key][type(value).__name__] += 1

    all_columns = sorted(
        {
            key
            for row in records
            for key in row.keys()
        }
    )

    print("\nALL RAW COLUMNS")
    print("=" * 100)
    print(
        f"{'Column':<42}"
        f"{'Non-missing':>14}"
        f"{'Missing':>12}"
        f"  Data types"
    )
    print("-" * 100)

    total = len(records)

    for column in all_columns:
        non_missing = non_missing_counts[column]
        missing = total - non_missing

        types = ", ".join(
            f"{name}:{count}"
            for name, count
            in type_counts[column].most_common()
        )

        print(
            f"{column:<42}"
            f"{non_missing:>14}"
            f"{missing:>12}"
            f"  {types}"
        )


def display_important_columns(
    records: list[dict[str, Any]],
) -> None:
    print("\nIMPORTANT COLUMN MISSING VALUES")
    print("=" * 80)
    print(
        f"{'Column':<32}"
        f"{'Non-missing':>14}"
        f"{'Missing':>12}"
        f"{'Coverage':>12}"
    )
    print("-" * 80)

    total = len(records)

    for column in IMPORTANT_COLUMNS:
        non_missing = sum(
            not is_missing(row.get(column))
            for row in records
        )

        missing = total - non_missing

        coverage = (
            non_missing / total * 100
            if total
            else 0
        )

        print(
            f"{column:<32}"
            f"{non_missing:>14}"
            f"{missing:>12}"
            f"{coverage:>11.1f}%"
        )


def display_unique_values(
    records: list[dict[str, Any]],
    column: str,
    limit: int = 20,
) -> None:
    values = Counter(
        str(row.get(column)).strip()
        for row in records
        if not is_missing(row.get(column))
    )

    print(f"\n{column.upper()} VALUES")
    print("=" * 70)

    if not values:
        print("No values found.")
        return

    for value, count in values.most_common(limit):
        print(f"{value:<45} {count:>8}")


def display_numeric_ranges(
    records: list[dict[str, Any]],
) -> None:
    numeric_columns = [
        "price_usd",
        "size_m2",
        "bedrooms",
        "bathrooms",
        "unit_floor",
        "building_total_floors",
    ]

    print("\nNUMERIC RANGES")
    print("=" * 80)
    print(
        f"{'Column':<30}"
        f"{'Count':>10}"
        f"{'Minimum':>15}"
        f"{'Maximum':>15}"
    )
    print("-" * 80)

    for column in numeric_columns:
        values: list[float] = []

        for row in records:
            value = row.get(column)

            if isinstance(value, bool):
                continue

            if isinstance(value, (int, float)):
                values.append(float(value))

        if values:
            print(
                f"{column:<30}"
                f"{len(values):>10}"
                f"{min(values):>15,.2f}"
                f"{max(values):>15,.2f}"
            )
        else:
            print(
                f"{column:<30}"
                f"{0:>10}"
                f"{'N/A':>15}"
                f"{'N/A':>15}"
            )


def display_duplicate_identity_counts(
    records: list[dict[str, Any]],
) -> None:
    listing_ids = Counter(
        str(row.get("listing_id")).strip()
        for row in records
        if not is_missing(row.get("listing_id"))
    )

    urls = Counter(
        str(row.get("url")).strip().lower().rstrip("/")
        for row in records
        if not is_missing(row.get("url"))
    )

    duplicate_ids = {
        key: count
        for key, count in listing_ids.items()
        if count > 1
    }

    duplicate_urls = {
        key: count
        for key, count in urls.items()
        if count > 1
    }

    print("\nIDENTITY DUPLICATE CHECK")
    print("=" * 70)
    print(
        f"Duplicate listing IDs : {len(duplicate_ids)}"
    )
    print(
        f"Duplicate URLs        : {len(duplicate_urls)}"
    )


def display_samples(
    records: list[dict[str, Any]],
    number: int = 3,
) -> None:
    print("\nSAMPLE RECORDS")
    print("=" * 100)

    sample_columns = [
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
        "commune",
        "project_name",
        "needs_manual_review",
        "url",
    ]

    for index, row in enumerate(
        records[:number],
        start=1,
    ):
        print(f"\nRECORD {index}")
        print("-" * 100)

        for column in sample_columns:
            print(
                f"{column:<28}: "
                f"{row.get(column)}"
            )


def main() -> None:
    records = load_records(INPUT_PATH)

    print("\nREALESTATE.COM.KH RAW DATA INSPECTION")
    print("=" * 100)
    print(f"Input file : {INPUT_PATH}")
    print(f"Total rows : {len(records):,}")

    display_all_columns(records)
    display_important_columns(records)
    display_unique_values(records, "listing_type")
    display_unique_values(records, "property_type")
    display_unique_values(records, "district")
    display_numeric_ranges(records)
    display_duplicate_identity_counts(records)
    display_samples(records)

    print("\n" + "=" * 100)
    print("Inspection completed.")
    print("=" * 100)


if __name__ == "__main__":
    main()