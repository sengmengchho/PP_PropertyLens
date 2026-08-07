from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


# Supports:
#   python -m src.cleaning.prepare_manual_review
#   python src/cleaning/prepare_manual_review.py
PROJECT_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="replace",
    )


from src.cleaning.common import (
    PROJECT_ROOT,
    clean_text,
    load_json_records,
)


INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "silver"
    / "combined"
    / "review.json"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "silver"
    / "manual_review"
)

OUTPUT_CSV = (
    OUTPUT_DIR
    / "manual_review_queue.csv"
)

OUTPUT_SUMMARY = (
    OUTPUT_DIR
    / "manual_review_queue_summary.json"
)


REVIEW_COLUMNS = [
    # Editable decision fields.
    "manual_decision",
    "manual_note",

    # Optional corrections. Leave blank when no correction is needed.
    "corrected_price_usd",
    "corrected_size_m2",
    "corrected_bedrooms",
    "corrected_bathrooms",
    "corrected_unit_floor",
    "corrected_building_total_floors",
    "corrected_district",
    "corrected_property_type",
    "corrected_listing_type",

    # Read-only evidence fields.
    "listing_id",
    "source",
    "source_listing_id",
    "source_listing_code",
    "title",
    "description_excerpt",
    "listing_type",
    "property_type",
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
    "project_name",
    "review_reason",
    "cleaning_notes",
    "price_usd_source",
    "size_m2_source",
    "bedrooms_source",
    "bathrooms_source",
    "unit_floor_source",
    "district_source",
    "url",
]


def description_excerpt(
    value: Any,
    limit: int = 1500,
) -> str | None:
    text = clean_text(value)

    if not text:
        return None

    if len(text) <= limit:
        return text

    return text[:limit].rstrip() + "..."


def prepare_rows(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for record in records:
        status = clean_text(
            record.get("record_status")
        )

        if status != "review":
            raise ValueError(
                "Expected only review records, but "
                f"{record.get('listing_id')} has "
                f"record_status={status!r}."
            )

        row = {
            "manual_decision": "",
            "manual_note": "",
            "corrected_price_usd": "",
            "corrected_size_m2": "",
            "corrected_bedrooms": "",
            "corrected_bathrooms": "",
            "corrected_unit_floor": "",
            "corrected_building_total_floors": "",
            "corrected_district": "",
            "corrected_property_type": "",
            "corrected_listing_type": "",
            "listing_id": record.get("listing_id"),
            "source": record.get("source"),
            "source_listing_id": record.get(
                "source_listing_id"
            ),
            "source_listing_code": record.get(
                "source_listing_code"
            ),
            "title": record.get("title"),
            "description_excerpt": description_excerpt(
                record.get("description")
            ),
            "listing_type": record.get("listing_type"),
            "property_type": record.get("property_type"),
            "price_usd": record.get("price_usd"),
            "size_m2": record.get("size_m2"),
            "price_per_m2": record.get("price_per_m2"),
            "bedrooms": record.get("bedrooms"),
            "bathrooms": record.get("bathrooms"),
            "unit_floor": record.get("unit_floor"),
            "building_total_floors": record.get(
                "building_total_floors"
            ),
            "city": record.get("city"),
            "district": record.get("district"),
            "commune": record.get("commune"),
            "project_name": record.get("project_name"),
            "review_reason": record.get("review_reason"),
            "cleaning_notes": record.get(
                "cleaning_notes"
            ),
            "price_usd_source": record.get(
                "price_usd_source"
            ),
            "size_m2_source": record.get(
                "size_m2_source"
            ),
            "bedrooms_source": record.get(
                "bedrooms_source"
            ),
            "bathrooms_source": record.get(
                "bathrooms_source"
            ),
            "unit_floor_source": record.get(
                "unit_floor_source"
            ),
            "district_source": record.get(
                "district_source"
            ),
            "url": record.get("url"),
        }

        rows.append(row)

    rows.sort(
        key=lambda row: (
            str(row.get("source") or ""),
            str(row.get("review_reason") or ""),
            float(row.get("price_usd") or 0),
            str(row.get("listing_id") or ""),
        )
    )

    return rows


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
            fieldnames=REVIEW_COLUMNS,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


def build_summary(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    source_counts = Counter(
        str(row.get("source"))
        for row in rows
    )

    reason_counts: Counter[str] = Counter()

    for row in rows:
        text = clean_text(
            row.get("review_reason")
        )

        if not text:
            reason_counts["missing_review_reason"] += 1
            continue

        for reason in text.split("; "):
            reason_counts[reason] += 1

    return {
        "input_path": str(INPUT_PATH),
        "output_csv": str(OUTPUT_CSV),
        "total_review_records": len(rows),
        "source_counts": dict(
            source_counts.most_common()
        ),
        "review_reason_counts": dict(
            reason_counts.most_common()
        ),
        "allowed_manual_decisions": [
            "approve",
            "reject",
            "keep_review",
        ],
        "instructions": {
            "approve": (
                "The record is plausible and may enter the "
                "cross-source deduplication candidate pool."
            ),
            "reject": (
                "The record is invalid, out of scope, or has "
                "an unresolved extraction error."
            ),
            "keep_review": (
                "Evidence is not strong enough. Exclude it "
                "from the first modeling dataset."
            ),
        },
    }


def print_summary(
    summary: dict[str, Any],
) -> None:
    print("\nMANUAL REVIEW QUEUE CREATED")
    print("=" * 78)
    print(
        "Review records : "
        f"{summary['total_review_records']:,}"
    )
    print(f"Saved CSV      : {OUTPUT_CSV}")

    print("\nSOURCE COUNTS")
    print("-" * 78)

    for source, count in (
        summary["source_counts"].items()
    ):
        print(f"{source:<35}: {count}")

    print("\nTOP REVIEW REASONS")
    print("-" * 78)

    for reason, count in list(
        summary["review_reason_counts"].items()
    )[:20]:
        print(f"{reason:<52}: {count}")

    print("\nAllowed decisions:")
    print("  approve")
    print("  reject")
    print("  keep_review")
    print("=" * 78)


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Combined review file was not found: "
            f"{INPUT_PATH}"
        )

    records = load_json_records(
        INPUT_PATH
    )

    rows = prepare_rows(records)
    save_csv(rows)

    summary = build_summary(rows)

    OUTPUT_SUMMARY.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print_summary(summary)


if __name__ == "__main__":
    main()
