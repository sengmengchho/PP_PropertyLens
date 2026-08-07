from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any


# Supports:
#   python -m src.cleaning.build_gold_dataset
#   python src/cleaning/build_gold_dataset.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="replace",
    )


from src.cleaning.common import (
    clean_text,
    load_json_records,
    safe_float,
    safe_int,
)


INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "silver"
    / "deduplicated"
    / "accepted_after_cross_source_dedupe.json"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "gold"
)

OUTPUT_JSON = (
    OUTPUT_DIR
    / "property_listings.json"
)

OUTPUT_CSV = (
    OUTPUT_DIR
    / "property_listings.csv"
)

SUMMARY_JSON = (
    OUTPUT_DIR
    / "gold_summary.json"
)


GOLD_COLUMNS = [
    "listing_id",
    "source",
    "source_listing_id",
    "source_listing_code",
    "url",
    "title",
    "description",
    "listing_type",
    "property_type",
    "project_name",
    "price_usd",
    "size_m2",
    "price_per_m2",
    "bedrooms",
    "bathrooms",
    "unit_floor",
    "building_total_floors",
    "city",
    "district",
    "commune",
    "address",
    "location_text",
    "latitude",
    "longitude",
    "listing_created_at",
    "listing_updated_at",
    "scraped_at",
]


REQUIRED_FOR_GOLD = [
    "listing_id",
    "source",
    "price_usd",
    "size_m2",
    "listing_type",
    "property_type",
]


QUALITY_COLUMNS = [
    "price_usd",
    "size_m2",
    "price_per_m2",
    "bedrooms",
    "bathrooms",
    "unit_floor",
    "building_total_floors",
    "district",
    "commune",
    "project_name",
    "latitude",
    "longitude",
]


def normalize_gold_row(
    record: dict[str, Any],
) -> dict[str, Any]:
    price = safe_float(
        record.get("price_usd")
    )

    size = safe_float(
        record.get("size_m2")
    )

    if (
        price is not None
        and size is not None
        and size > 0
    ):
        ppm2 = round(
            price / size,
            2,
        )
    else:
        ppm2 = None

    return {
        "listing_id": clean_text(
            record.get("listing_id")
        ),
        "source": clean_text(
            record.get("source")
        ),
        "source_listing_id": clean_text(
            record.get("source_listing_id")
        ),
        "source_listing_code": clean_text(
            record.get("source_listing_code")
        ),
        "url": clean_text(
            record.get("url")
        ),
        "title": clean_text(
            record.get("title")
        ),
        "description": clean_text(
            record.get("description")
        ),
        "listing_type": clean_text(
            record.get("listing_type")
        ),
        "property_type": clean_text(
            record.get("property_type")
        ),
        "project_name": clean_text(
            record.get("project_name")
        ),
        "price_usd": price,
        "size_m2": size,
        "price_per_m2": ppm2,
        "bedrooms": safe_int(
            record.get("bedrooms")
        ),
        "bathrooms": safe_int(
            record.get("bathrooms")
        ),
        "unit_floor": safe_int(
            record.get("unit_floor")
        ),
        "building_total_floors": safe_int(
            record.get("building_total_floors")
        ),
        "city": clean_text(
            record.get("city")
        ),
        "district": clean_text(
            record.get("district")
        ),
        "commune": clean_text(
            record.get("commune")
        ),
        "address": clean_text(
            record.get("address")
        ),
        "location_text": clean_text(
            record.get("location_text")
        ),
        "latitude": safe_float(
            record.get("latitude")
        ),
        "longitude": safe_float(
            record.get("longitude")
        ),
        "listing_created_at": clean_text(
            record.get("listing_created_at")
        ),
        "listing_updated_at": clean_text(
            record.get("listing_updated_at")
        ),
        "scraped_at": clean_text(
            record.get("scraped_at")
        ),
    }


def validate_gold_rows(
    rows: list[dict[str, Any]],
) -> None:
    seen_ids: set[str] = set()

    for index, row in enumerate(
        rows,
        start=1,
    ):
        listing_id = clean_text(
            row.get("listing_id")
        )

        if not listing_id:
            raise ValueError(
                f"Gold row {index} has blank listing_id."
            )

        if listing_id in seen_ids:
            raise ValueError(
                f"Duplicate listing_id in Gold dataset: "
                f"{listing_id}"
            )

        seen_ids.add(listing_id)

        for field in REQUIRED_FOR_GOLD:
            value = row.get(field)

            if value is None or (
                isinstance(value, str)
                and not value.strip()
            ):
                raise ValueError(
                    f"Gold row {listing_id} is missing "
                    f"required field {field}."
                )

        price = safe_float(
            row.get("price_usd")
        )

        size = safe_float(
            row.get("size_m2")
        )

        if price is None or price <= 0:
            raise ValueError(
                f"Gold row {listing_id} has invalid price."
            )

        if size is None or size <= 0:
            raise ValueError(
                f"Gold row {listing_id} has invalid size."
            )

        listing_type = clean_text(
            row.get("listing_type")
        )

        if listing_type not in {
            "sale",
            "sale/rent",
        }:
            raise ValueError(
                f"Gold row {listing_id} has invalid "
                f"listing_type={listing_type!r}."
            )

        property_type = clean_text(
            row.get("property_type")
        )

        if property_type not in {
            "Condo",
            "Penthouse",
        }:
            raise ValueError(
                f"Gold row {listing_id} has invalid "
                f"property_type={property_type!r}."
            )


def save_csv(
    rows: list[dict[str, Any]],
) -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=GOLD_COLUMNS,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


def missing_count(
    rows: list[dict[str, Any]],
    field: str,
) -> int:
    count = 0

    for row in rows:
        value = row.get(field)

        if value is None:
            count += 1
        elif (
            isinstance(value, str)
            and not value.strip()
        ):
            count += 1

    return count


def numeric_summary(
    rows: list[dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    values: list[float] = []

    for row in rows:
        value = safe_float(
            row.get(field)
        )

        if value is not None:
            values.append(value)

    if not values:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
        }

    return {
        "count": len(values),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "mean": round(
            sum(values) / len(values),
            2,
        ),
    }


def build_summary(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    total = len(rows)

    missingness: dict[str, Any] = {}

    for field in QUALITY_COLUMNS:
        missing = missing_count(
            rows,
            field,
        )

        missingness[field] = {
            "missing": missing,
            "non_missing": total - missing,
            "coverage_pct": round(
                ((total - missing) / total) * 100,
                1,
            ) if total else 0.0,
        }

    source_counts = Counter(
        clean_text(row.get("source"))
        or "missing"
        for row in rows
    )

    district_counts = Counter(
        clean_text(row.get("district"))
        or "missing"
        for row in rows
    )

    property_counts = Counter(
        clean_text(row.get("property_type"))
        or "missing"
        for row in rows
    )

    listing_type_counts = Counter(
        clean_text(row.get("listing_type"))
        or "missing"
        for row in rows
    )

    return {
        "input_path": str(
            INPUT_PATH
        ),
        "gold_json": str(
            OUTPUT_JSON
        ),
        "gold_csv": str(
            OUTPUT_CSV
        ),
        "total_records": total,
        "gold_columns": GOLD_COLUMNS,
        "column_count": len(
            GOLD_COLUMNS
        ),
        "source_counts": dict(
            source_counts.most_common()
        ),
        "listing_type_counts": dict(
            listing_type_counts.most_common()
        ),
        "property_type_counts": dict(
            property_counts.most_common()
        ),
        "district_counts": dict(
            district_counts.most_common()
        ),
        "missingness": missingness,
        "numeric_summary": {
            "price_usd": numeric_summary(
                rows,
                "price_usd",
            ),
            "size_m2": numeric_summary(
                rows,
                "size_m2",
            ),
            "price_per_m2": numeric_summary(
                rows,
                "price_per_m2",
            ),
            "bedrooms": numeric_summary(
                rows,
                "bedrooms",
            ),
            "bathrooms": numeric_summary(
                rows,
                "bathrooms",
            ),
            "unit_floor": numeric_summary(
                rows,
                "unit_floor",
            ),
        },
        "modeling_note": (
            "No imputation, encoding, scaling, log transformation, "
            "train/test split, or location-distance engineering has "
            "been applied yet. This Gold file is the clean analytical "
            "base dataset for EDA and later feature engineering."
        ),
    }


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            "Deduplicated Silver dataset was not found:\n"
            f"{INPUT_PATH}"
        )

    records = load_json_records(
        INPUT_PATH
    )

    rows: list[dict[str, Any]] = []

    for record in records:
        status = clean_text(
            record.get("record_status")
        )

        if status != "accepted":
            raise ValueError(
                "Gold builder expects only accepted records, "
                f"but {record.get('listing_id')} has "
                f"record_status={status!r}."
            )

        rows.append(
            normalize_gold_row(
                record
            )
        )

    validate_gold_rows(
        rows
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_JSON.write_text(
        json.dumps(
            rows,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    save_csv(
        rows
    )

    summary = build_summary(
        rows
    )

    SUMMARY_JSON.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nGOLD DATASET CREATED")
    print("=" * 86)
    print(
        "Input accepted records : "
        f"{len(records):,}"
    )
    print(
        "Gold records           : "
        f"{len(rows):,}"
    )
    print(
        "Gold columns           : "
        f"{len(GOLD_COLUMNS):,}"
    )
    print(
        "Unique listing IDs     : "
        f"{len({row['listing_id'] for row in rows}):,}"
    )

    print("\nSOURCE COUNTS")
    print("-" * 86)

    for source, count in (
        summary["source_counts"].items()
    ):
        print(
            f"{source:<35}: {count:,}"
        )

    print("\nKEY COVERAGE")
    print("-" * 86)

    for field in [
        "bedrooms",
        "bathrooms",
        "unit_floor",
        "district",
        "project_name",
        "latitude",
        "longitude",
    ]:
        info = summary[
            "missingness"
        ][field]

        print(
            f"{field:<28}: "
            f"{info['coverage_pct']:>6.1f}% "
            f"({info['non_missing']:,}/{len(rows):,})"
        )

    print(f"\nSaved JSON : {OUTPUT_JSON}")
    print(f"Saved CSV  : {OUTPUT_CSV}")
    print(f"Summary    : {SUMMARY_JSON}")
    print("=" * 86)


if __name__ == "__main__":
    main()
