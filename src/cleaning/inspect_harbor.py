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
    / "harbor-property_com"
    / "raw_listings.json",

    PROJECT_ROOT
    / "data"
    / "bronze"
    / "harbor_property_com"
    / "raw_listings.json",

    PROJECT_ROOT
    / "data"
    / "bronze"
    / "harbor"
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
    "price_usd",
    "size_m2",
    "bedrooms",
    "bathrooms",
    "unit_floor",
    "building_total_floors",
    "bedroom_options",
    "multi_unit_options",
    "province",
    "city",
    "district",
    "commune",
    "address",
    "location_text",
    "project_name",
    "property_code",
    "created_at",
    "updated_at",
    "scraped_at",
    "detail_scraped",
    "display_as_project",
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

    checked = "\n".join(str(path) for path in POSSIBLE_INPUT_PATHS)

    raise FileNotFoundError(
        "Harbor Property Bronze file was not found.\n"
        f"Checked:\n{checked}"
    )


def collect_columns(
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
    print("=" * 112)
    print(
        f"{'Column':<49}"
        f"{'Non-missing':>14}"
        f"{'Missing':>12}"
        f"{'Coverage':>12}"
        f"  Types"
    )
    print("-" * 112)

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
            f"{column:<49}"
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
    print("=" * 90)
    print(
        f"{'Column':<39}"
        f"{'Non-missing':>14}"
        f"{'Missing':>12}"
        f"{'Coverage':>12}"
    )
    print("-" * 90)

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
            f"{column:<39}"
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
    print("=" * 80)

    if not counts:
        print("No values found.")
        return

    for value, count in counts.most_common(limit):
        print(f"{value:<60}: {count}")


def show_numeric_ranges(
    records: list[dict[str, Any]],
) -> None:
    print("\nNUMERIC RANGES")
    print("=" * 90)
    print(
        f"{'Column':<36}"
        f"{'Count':>10}"
        f"{'Minimum':>18}"
        f"{'Maximum':>18}"
    )
    print("-" * 90)

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
                f"{column:<36}"
                f"{len(values):>10}"
                f"{min(values):>18,.2f}"
                f"{max(values):>18,.2f}"
            )
        else:
            print(
                f"{column:<36}"
                f"{0:>10}"
                f"{'N/A':>18}"
                f"{'N/A':>18}"
            )


def show_special_counts(
    records: list[dict[str, Any]],
) -> None:
    rent = sum(
        record.get("listing_type") == "rent"
        for record in records
    )
    sale_rent = sum(
        record.get("listing_type") == "sale/rent"
        for record in records
    )
    missing_price = sum(
        is_missing(record.get("price_usd"))
        for record in records
    )
    missing_size = sum(
        is_missing(record.get("size_m2"))
        for record in records
    )
    projects = sum(
        record.get("display_as_project") is True
        for record in records
    )
    multi_unit = sum(
        bool(record.get("multi_unit_options"))
        or bool(record.get("bedroom_options"))
        for record in records
    )
    review_true = sum(
        record.get("needs_manual_review") is True
        for record in records
    )
    detail_false = sum(
        record.get("detail_scraped") is False
        for record in records
    )

    print("\nSPECIAL GROUP COUNTS")
    print("=" * 82)
    print(f"Rent-only records          : {rent}")
    print(f"Sale/rent records          : {sale_rent}")
    print(f"Missing price              : {missing_price}")
    print(f"Missing size               : {missing_size}")
    print(f"Project-level records      : {projects}")
    print(f"Multi-unit/config records  : {multi_unit}")
    print(f"True manual-review flags   : {review_true}")
    print(f"Detail scrape false        : {detail_false}")


def show_conflict_counts(
    records: list[dict[str, Any]],
) -> None:
    counts: Counter[str] = Counter()

    for record in records:
        for key, value in record.items():
            if (
                key.endswith("_conflict")
                or key.endswith("_reference_mismatch")
                or key.endswith("_search_mismatch")
            ) and value:
                counts[key] += 1

    print("\nCONFLICT AND MISMATCH COUNTS")
    print("=" * 82)

    if not counts:
        print("No conflict or mismatch fields found.")
        return

    for key, count in counts.most_common():
        print(f"{key:<60}: {count}")


def show_source_counts(
    records: list[dict[str, Any]],
) -> None:
    fields = [
        "price_usd_source",
        "size_m2_source",
        "bedrooms_source",
        "bathrooms_source",
        "unit_floor_source",
        "building_total_floors_source",
        "property_type_source",
        "listing_type_source",
        "district_source",
        "description_source",
    ]

    for field in fields:
        counts = Counter(
            str(record.get(field))
            for record in records
            if not is_missing(record.get(field))
        )

        print(f"\n{field.upper()}")
        print("=" * 88)

        if not counts:
            print("No values found.")
            continue

        for value, count in counts.most_common(20):
            print(f"{value:<70}: {count}")


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

    codes = Counter(
        str(record.get("property_code")).strip()
        for record in records
        if not is_missing(record.get("property_code"))
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
    duplicate_codes = {
        value: count
        for value, count in codes.items()
        if count > 1
    }

    print("\nIDENTITY DUPLICATE CHECK")
    print("=" * 82)
    print(f"Duplicate listing-ID groups : {len(duplicate_ids)}")
    print(f"Duplicate URL groups        : {len(duplicate_urls)}")
    print(f"Duplicate property-code groups: {len(duplicate_codes)}")

    if duplicate_ids:
        print("\nDUPLICATE ID EXAMPLES")
        for value, count in list(duplicate_ids.items())[:10]:
            print(f"{value}: {count}")

    if duplicate_urls:
        print("\nDUPLICATE URL EXAMPLES")
        for value, count in list(duplicate_urls.items())[:10]:
            print(f"{value}: {count}")

    if duplicate_codes:
        print("\nDUPLICATE PROPERTY-CODE EXAMPLES")
        for value, count in list(duplicate_codes.items())[:10]:
            print(f"{value}: {count}")


def show_review_records(
    records: list[dict[str, Any]],
    limit: int = 30,
) -> None:
    reviews = [
        record
        for record in records
        if record.get("needs_manual_review") is True
    ]

    print("\nBRONZE REVIEW RECORDS")
    print("=" * 102)
    print(f"Review records: {len(reviews)}")

    for record in reviews[:limit]:
        print("\n" + "-" * 102)
        print("ID          :", record.get("listing_id"))
        print("Code        :", record.get("property_code"))
        print("Title       :", record.get("title"))
        print("Listing type:", record.get("listing_type"))
        print("Property    :", record.get("property_type"))
        print("Price       :", record.get("price_usd"))
        print("Size        :", record.get("size_m2"))
        print("Bedrooms    :", record.get("bedrooms"))
        print("Bed options :", record.get("bedroom_options"))
        print("Bathrooms   :", record.get("bathrooms"))
        print("Unit floor  :", record.get("unit_floor"))
        print("Total floors:", record.get("building_total_floors"))
        print("District    :", record.get("district"))
        print("Project page:", record.get("display_as_project"))

        for key, value in record.items():
            if (
                key.endswith("_conflict")
                or key.endswith("_reference_mismatch")
                or key.endswith("_search_mismatch")
            ) and value:
                print(f"{key:<34}: {value}")

        print("URL         :", record.get("url"))


def show_samples(
    records: list[dict[str, Any]],
    limit: int = 5,
) -> None:
    columns = [
        "listing_id",
        "property_code",
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
        "project_name",
        "display_as_project",
        "needs_manual_review",
        "url",
    ]

    print("\nSAMPLE RECORDS")
    print("=" * 102)

    for index, record in enumerate(records[:limit], start=1):
        print(f"\nRECORD {index}")
        print("-" * 102)

        for column in columns:
            print(f"{column:<31}: {record.get(column)}")


def main() -> None:
    input_path = find_input_path()
    records = load_json_records(input_path)

    print("\nHARBOR PROPERTY RAW DATA INSPECTION")
    print("=" * 112)
    print(f"Input file : {input_path}")
    print(f"Total rows : {len(records):,}")

    show_column_profile(records)
    show_important_coverage(records)

    for column in [
        "listing_type",
        "property_type",
        "province",
        "city",
        "district",
    ]:
        show_value_counts(records, column)

    show_numeric_ranges(records)
    show_special_counts(records)
    show_conflict_counts(records)
    show_source_counts(records)
    show_duplicate_check(records)
    show_review_records(records)
    show_samples(records)

    print("\n" + "=" * 112)
    print("Harbor Property inspection completed.")
    print("=" * 112)


if __name__ == "__main__":
    main()