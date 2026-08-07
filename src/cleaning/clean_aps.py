from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


# Supports:
#   python -m src.cleaning.clean_aps
#   python src/cleaning/clean_aps.py
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
    STANDARD_COLUMNS,
    add_reason,
    calculate_price_per_m2,
    clean_text,
    ensure_standard_columns,
    join_reasons,
    load_json_records,
    normalize_district,
    normalize_listing_type,
    normalize_property_type_label,
    normalize_url,
    safe_float,
    safe_int,
    save_csv_records,
    save_json_records,
)


POSSIBLE_INPUT_PATHS = [
    PROJECT_ROOT
    / "data"
    / "bronze"
    / "aps_com_kh"
    / "raw_listings.json",

    PROJECT_ROOT
    / "data"
    / "bronze"
    / "aps_com"
    / "raw_listings.json",

    PROJECT_ROOT
    / "data"
    / "bronze"
    / "aps"
    / "raw_listings.json",
]

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "silver"
    / "by_source"
    / "aps"
)

SOURCE_NAME = "aps.com.kh"
TARGET_CITY = "Phnom Penh"
TARGET_PROPERTY_TYPES = {"Condo", "Penthouse"}

REVIEW_LIMITS = {
    "price_min": 20_000,
    "price_max": 2_000_000,
    "size_min": 20,
    "size_max": 500,
    "price_per_m2_min": 300,
    "price_per_m2_max": 10_000,
    "bedrooms_max": 10,
    "bathrooms_max": 10,
    "unit_floor_max": 100,
    "building_total_floors_max": 120,
}

APS_TITLE_SUFFIX_RE = re.compile(
    r"\s*-\s*APS\s+Cambodia\s+\d+\s*$",
    re.I,
)

PROJECT_TITLE_RE = re.compile(
    r"""
    \b\d{2,4}\s+units?\b
    |
    \b\d{2,3}\s+(?:stories|floors)\s+high\b
    """,
    re.I | re.X,
)


def find_input_path() -> Path:
    for path in POSSIBLE_INPUT_PATHS:
        if path.exists():
            return path

    checked = "\n".join(
        str(path)
        for path in POSSIBLE_INPUT_PATHS
    )

    raise FileNotFoundError(
        "APS Bronze file was not found.\n"
        f"Checked:\n{checked}"
    )


def clean_aps_title(value: Any) -> str | None:
    title = clean_text(value)

    if title is None:
        return None

    title = APS_TITLE_SUFFIX_RE.sub("", title)
    title = re.sub(r"\s+", " ", title).strip(" -|")

    return title or None


def normalize_aps_code(value: Any) -> str | None:
    code = clean_text(value)

    if not code:
        return None

    digits = re.sub(r"\D", "", code)

    if not digits:
        return None

    return digits


def build_global_listing_id(
    source_listing_id: Any,
) -> str:
    value = clean_text(source_listing_id) or "unknown"

    if value.lower().startswith("aps.com.kh_"):
        return value

    return f"{SOURCE_NAME}_{value}"


def duplicate_group_id(
    aps_code: str,
) -> str:
    digest = hashlib.sha1(
        aps_code.encode("utf-8")
    ).hexdigest()[:12]

    return f"aps_listing_code_{digest}"


def is_project_level(
    raw: dict[str, Any],
) -> bool:
    property_code = (
        clean_text(raw.get("property_code"))
        or ""
    ).upper()

    title = clean_text(raw.get("title")) or ""

    return (
        property_code.startswith("B-")
        or bool(PROJECT_TITLE_RE.search(title))
        or bool(raw.get("display_as_project"))
    )


def resolve_bedrooms(
    raw: dict[str, Any],
) -> tuple[int | None, str | None, list[str]]:
    current = safe_int(raw.get("bedrooms"))
    current_source = clean_text(
        raw.get("bedrooms_source")
    )

    title_value = safe_int(
        raw.get("bedrooms_title_value")
    )
    title_source = clean_text(
        raw.get("bedrooms_title_source")
    )

    mismatch = clean_text(
        raw.get("bedrooms_url_mismatch")
    )

    notes: list[str] = []

    if mismatch and title_value is not None:
        if current != title_value:
            add_reason(
                notes,
                "bedrooms corrected from title: "
                f"{current} -> {title_value}",
            )

        add_reason(
            notes,
            f"resolved bedrooms_url_mismatch: {mismatch}",
        )

        return (
            title_value,
            title_source or "aps_com_kh_title",
            notes,
        )

    return current, current_source, notes


def resolve_unit_floor(
    raw: dict[str, Any],
) -> tuple[int | None, str | None, list[str]]:
    current = safe_int(raw.get("unit_floor"))
    current_source = clean_text(
        raw.get("unit_floor_source")
    )

    previous = safe_int(
        raw.get("unit_floor_previous_value")
    )
    mismatch = clean_text(
        raw.get("unit_floor_reference_mismatch")
    )

    notes: list[str] = []

    # Audited mismatch:
    # title/URL say 28th floor; canonical level was 39.
    # Prefer the explicit listing title/URL value.
    if mismatch and previous is not None:
        if current != previous:
            add_reason(
                notes,
                "unit floor corrected from explicit title/URL: "
                f"{current} -> {previous}",
            )

        add_reason(
            notes,
            f"resolved unit_floor_reference_mismatch: {mismatch}",
        )

        return (
            previous,
            "aps_com_kh_title_or_url",
            notes,
        )

    return current, current_source, notes


def normalize_record(
    raw: dict[str, Any],
) -> dict[str, Any]:
    source_listing_id = clean_text(
        raw.get("listing_id")
    )

    aps_listing_code = normalize_aps_code(
        raw.get("aps_listing_code")
    )

    property_code = clean_text(
        raw.get("property_code")
    )

    title = clean_aps_title(
        raw.get("title")
    )

    price_usd = safe_float(
        raw.get("price_usd")
    )
    size_m2 = safe_float(
        raw.get("size_m2")
    )

    bedrooms, bedrooms_source, bed_notes = (
        resolve_bedrooms(raw)
    )

    unit_floor, unit_floor_source, floor_notes = (
        resolve_unit_floor(raw)
    )

    notes: list[str] = []
    notes.extend(bed_notes)
    notes.extend(floor_notes)

    if property_code:
        add_reason(
            notes,
            f"APS property_code={property_code}",
        )

    size_mismatch = clean_text(
        raw.get("size_m2_reference_mismatch")
    )

    if size_mismatch:
        add_reason(
            notes,
            "kept APS canonical structured size; "
            f"reference mismatch: {size_mismatch}",
        )

    listing_type_mismatch = clean_text(
        raw.get("listing_type_url_mismatch")
    )

    if listing_type_mismatch:
        add_reason(
            notes,
            "kept current title-derived listing type; "
            f"URL mismatch: {listing_type_mismatch}",
        )

    district = normalize_district(
        raw.get("district")
    )

    if not district:
        add_reason(
            notes,
            "district missing in Bronze",
        )

    source_out_of_scope = clean_text(
        raw.get("out_of_scope_reason")
    )

    if source_out_of_scope:
        add_reason(
            notes,
            f"Bronze out_of_scope_reason: {source_out_of_scope}",
        )

    property_type = normalize_property_type_label(
        raw.get("property_type")
    )

    record: dict[str, Any] = {
        # Identity
        "listing_id": build_global_listing_id(
            source_listing_id
        ),
        "source": SOURCE_NAME,
        "source_listing_id": source_listing_id,
        "source_listing_code": aps_listing_code,
        "url": clean_text(raw.get("url")),
        "canonical_url": normalize_url(
            raw.get("url")
        ),

        # Listing
        "title": title,
        "description": clean_text(
            raw.get("description")
        ),
        "listing_type": normalize_listing_type(
            raw.get("listing_type")
        ),
        "property_type": property_type,
        "property_type_original": property_type,
        "project_name": clean_text(
            raw.get("project_name")
        ),

        # Price and size
        "price_usd": price_usd,
        "size_m2": size_m2,
        "price_per_m2": calculate_price_per_m2(
            price_usd,
            size_m2,
        ),
        "price_original": safe_float(
            raw.get("price_original_usd")
        ),

        # Features
        "bedrooms": bedrooms,
        "bathrooms": safe_int(
            raw.get("bathrooms")
        ),
        "unit_floor": unit_floor,
        "building_total_floors": safe_int(
            raw.get("building_total_floors")
        ),
        "bedroom_options": None,
        "multi_unit_options": False,

        # Location
        "city": (
            clean_text(raw.get("province"))
            or TARGET_CITY
        ),
        "district": district,
        "commune": clean_text(
            raw.get("commune")
        ),
        "address": clean_text(
            raw.get("address")
        ),
        "location_text": (
            clean_text(raw.get("location_text"))
            or district
        ),
        "latitude": safe_float(
            raw.get("latitude")
        ),
        "longitude": safe_float(
            raw.get("longitude")
        ),

        # Dates
        "listing_created_at": clean_text(
            raw.get("created_at")
        ),
        "listing_updated_at": clean_text(
            raw.get("updated_at")
        ),
        "scraped_at": clean_text(
            raw.get("scraped_at")
        ),

        # Status
        "record_status": None,
        "needs_manual_review": False,
        "review_reason": None,
        "reject_reason": None,
        "duplicate_group_id": None,
        "duplicate_reason": None,
        "cleaning_notes": join_reasons(notes),

        # Sources
        "price_usd_source": clean_text(
            raw.get("price_usd_source")
        ),
        "size_m2_source": clean_text(
            raw.get("size_m2_source")
        ),
        "bedrooms_source": bedrooms_source,
        "bathrooms_source": clean_text(
            raw.get("bathrooms_source")
        ),
        "unit_floor_source": unit_floor_source,
        "building_total_floors_source": clean_text(
            raw.get(
                "building_total_floors_source"
            )
        ),
        "district_source": clean_text(
            raw.get("district_source")
        ),
        "listing_type_source": clean_text(
            raw.get("listing_type_source")
        ),
        "property_type_source": clean_text(
            raw.get("property_type_source")
        ),

        # Internal fields removed by ensure_standard_columns().
        "_is_project_level": is_project_level(raw),
        "_size_reference_mismatch": bool(
            size_mismatch
        ),
    }

    return record


def classify_record(
    record: dict[str, Any],
) -> dict[str, Any]:
    reject_reasons: list[str] = []
    review_reasons: list[str] = []

    listing_type = record.get("listing_type")
    property_type = record.get("property_type")

    price = safe_float(
        record.get("price_usd")
    )
    size = safe_float(
        record.get("size_m2")
    )
    ppm2 = safe_float(
        record.get("price_per_m2")
    )

    bedrooms = safe_int(
        record.get("bedrooms")
    )
    bathrooms = safe_int(
        record.get("bathrooms")
    )
    unit_floor = safe_int(
        record.get("unit_floor")
    )
    total_floors = safe_int(
        record.get("building_total_floors")
    )

    # Hard rejection rules.
    if listing_type == "rent":
        add_reason(
            reject_reasons,
            "rent_listing",
        )
    elif listing_type not in {
        "sale",
        "sale/rent",
    }:
        add_reason(
            reject_reasons,
            "unknown_listing_type",
        )

    if property_type not in TARGET_PROPERTY_TYPES:
        add_reason(
            reject_reasons,
            "not_condo_or_penthouse",
        )

    if record.get("_is_project_level"):
        add_reason(
            reject_reasons,
            "project_level_listing",
        )

    if (
        bedrooms is not None
        and bedrooms > REVIEW_LIMITS["bedrooms_max"]
    ):
        add_reason(
            reject_reasons,
            "multi_unit_listing",
        )

    if price is None:
        add_reason(
            reject_reasons,
            "missing_price",
        )
    elif price <= 0:
        add_reason(
            reject_reasons,
            "invalid_price",
        )

    if size is None:
        add_reason(
            reject_reasons,
            "missing_size",
        )
    elif size <= 0:
        add_reason(
            reject_reasons,
            "invalid_size",
        )

    # Review rules.
    if (
        price is not None
        and price < REVIEW_LIMITS["price_min"]
    ):
        add_reason(
            review_reasons,
            "price_below_review_limit",
        )
    elif (
        price is not None
        and price > REVIEW_LIMITS["price_max"]
    ):
        add_reason(
            review_reasons,
            "price_above_review_limit",
        )

    if (
        size is not None
        and size < REVIEW_LIMITS["size_min"]
    ):
        add_reason(
            review_reasons,
            "size_below_review_limit",
        )
    elif (
        size is not None
        and size > REVIEW_LIMITS["size_max"]
    ):
        add_reason(
            review_reasons,
            "size_above_review_limit",
        )

    if (
        ppm2 is not None
        and ppm2 < REVIEW_LIMITS["price_per_m2_min"]
    ):
        add_reason(
            review_reasons,
            "price_per_m2_below_review_limit",
        )
    elif (
        ppm2 is not None
        and ppm2 > REVIEW_LIMITS["price_per_m2_max"]
    ):
        add_reason(
            review_reasons,
            "price_per_m2_above_review_limit",
        )

    if record.get("_size_reference_mismatch"):
        add_reason(
            review_reasons,
            "size_reference_mismatch",
        )

    if (
        bathrooms is not None
        and bathrooms > REVIEW_LIMITS["bathrooms_max"]
    ):
        add_reason(
            review_reasons,
            "bathrooms_above_review_limit",
        )

    if (
        unit_floor is not None
        and unit_floor > REVIEW_LIMITS["unit_floor_max"]
    ):
        add_reason(
            review_reasons,
            "unit_floor_above_review_limit",
        )

    if (
        total_floors is not None
        and total_floors
        > REVIEW_LIMITS["building_total_floors_max"]
    ):
        add_reason(
            review_reasons,
            "building_floors_above_review_limit",
        )

    if (
        unit_floor is not None
        and total_floors is not None
        and unit_floor > total_floors
    ):
        add_reason(
            review_reasons,
            "unit_floor_exceeds_building_floors",
        )

    if reject_reasons:
        record["record_status"] = "rejected"
        record["needs_manual_review"] = False
        record["reject_reason"] = join_reasons(
            reject_reasons
        )
        record["review_reason"] = join_reasons(
            review_reasons
        )
        return record

    if review_reasons:
        record["record_status"] = "review"
        record["needs_manual_review"] = True
        record["review_reason"] = join_reasons(
            review_reasons
        )
        record["reject_reason"] = None
        return record

    record["record_status"] = "accepted"
    record["needs_manual_review"] = False
    record["review_reason"] = None
    record["reject_reason"] = None

    return record


def mark_duplicate(
    record: dict[str, Any],
    aps_code: str,
) -> dict[str, Any]:
    record["record_status"] = "duplicate"
    record["needs_manual_review"] = False
    record["duplicate_reason"] = (
        "duplicate_aps_listing_code"
    )
    record["duplicate_group_id"] = (
        duplicate_group_id(aps_code)
    )
    record["review_reason"] = None
    record["reject_reason"] = None

    return record


def clean_records(
    raw_records: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    outputs: dict[str, list[dict[str, Any]]] = {
        "accepted": [],
        "review": [],
        "rejected": [],
        "duplicates": [],
    }

    seen_aps_codes: set[str] = set()
    seen_listing_ids: set[str] = set()
    seen_urls: set[str] = set()

    for raw in raw_records:
        record = normalize_record(raw)

        aps_code = clean_text(
            record.get("source_listing_code")
        )
        source_listing_id = clean_text(
            record.get("source_listing_id")
        )
        canonical_url = clean_text(
            record.get("canonical_url")
        )

        if aps_code and aps_code in seen_aps_codes:
            duplicate = mark_duplicate(
                record,
                aps_code,
            )

            outputs["duplicates"].append(
                ensure_standard_columns(duplicate)
            )
            continue

        if (
            source_listing_id
            and source_listing_id in seen_listing_ids
        ):
            duplicate = mark_duplicate(
                record,
                source_listing_id,
            )
            duplicate["duplicate_reason"] = (
                "duplicate_source_listing_id"
            )

            outputs["duplicates"].append(
                ensure_standard_columns(duplicate)
            )
            continue

        if canonical_url and canonical_url in seen_urls:
            duplicate = mark_duplicate(
                record,
                canonical_url,
            )
            duplicate["duplicate_reason"] = (
                "duplicate_canonical_url"
            )

            outputs["duplicates"].append(
                ensure_standard_columns(duplicate)
            )
            continue

        if aps_code:
            seen_aps_codes.add(aps_code)

        if source_listing_id:
            seen_listing_ids.add(source_listing_id)

        if canonical_url:
            seen_urls.add(canonical_url)

        classified = classify_record(record)
        status = str(classified["record_status"])

        outputs[status].append(
            ensure_standard_columns(classified)
        )

    return outputs


def build_summary(
    raw_records: list[dict[str, Any]],
    outputs: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    accepted = outputs["accepted"]
    review = outputs["review"]
    rejected = outputs["rejected"]
    duplicates = outputs["duplicates"]

    review_counts: Counter[str] = Counter()
    reject_counts: Counter[str] = Counter()
    duplicate_counts: Counter[str] = Counter()

    for row in review:
        text = clean_text(
            row.get("review_reason")
        )

        if text:
            for reason in text.split("; "):
                review_counts[reason] += 1

    for row in rejected:
        text = clean_text(
            row.get("reject_reason")
        )

        if text:
            for reason in text.split("; "):
                reject_counts[reason] += 1

    for row in duplicates:
        reason = clean_text(
            row.get("duplicate_reason")
        )

        if reason:
            duplicate_counts[reason] += 1

    all_rows = [
        row
        for group in outputs.values()
        for row in group
    ]

    corrected_floor_records = sum(
        "unit floor corrected from explicit title/URL"
        in str(row.get("cleaning_notes") or "")
        for row in all_rows
    )

    bedroom_mismatch_records = sum(
        "resolved bedrooms_url_mismatch"
        in str(row.get("cleaning_notes") or "")
        for row in all_rows
    )

    listing_type_mismatch_records = sum(
        "title-derived listing type"
        in str(row.get("cleaning_notes") or "")
        for row in all_rows
    )

    missing_district_kept = sum(
        row.get("district") in (None, "")
        for row in all_rows
        if row.get("record_status")
        in {"accepted", "review"}
    )

    return {
        "source": SOURCE_NAME,
        "input_path": str(find_input_path()),
        "output_directory": str(OUTPUT_DIR),
        "total_raw_records": len(raw_records),
        "accepted_records": len(accepted),
        "review_records": len(review),
        "rejected_records": len(rejected),
        "duplicate_records": len(duplicates),
        "output_total": (
            len(accepted)
            + len(review)
            + len(rejected)
            + len(duplicates)
        ),
        "unit_floor_mismatches_corrected": (
            corrected_floor_records
        ),
        "bedroom_url_mismatches_resolved": (
            bedroom_mismatch_records
        ),
        "listing_type_url_mismatches_preserved": (
            listing_type_mismatch_records
        ),
        "accepted_or_review_missing_district": (
            missing_district_kept
        ),
        "review_reason_counts": dict(
            review_counts.most_common()
        ),
        "reject_reason_counts": dict(
            reject_counts.most_common()
        ),
        "duplicate_reason_counts": dict(
            duplicate_counts.most_common()
        ),
        "review_limits": REVIEW_LIMITS,
        "standard_columns": STANDARD_COLUMNS,
        "deduplication_policy": (
            "APS listing code is the primary source-level duplicate "
            "identifier. One record is kept per APS listing code."
        ),
    }


def save_outputs(
    outputs: dict[str, list[dict[str, Any]]],
    summary: dict[str, Any],
) -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for name, records in outputs.items():
        save_json_records(
            records,
            OUTPUT_DIR / f"{name}.json",
        )

        save_csv_records(
            records,
            OUTPUT_DIR / f"{name}.csv",
            columns=STANDARD_COLUMNS,
        )

    (
        OUTPUT_DIR
        / "cleaning_summary.json"
    ).write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def print_summary(
    summary: dict[str, Any],
) -> None:
    print("\nAPS CLEANING SUMMARY — V1")
    print("=" * 78)
    print(
        f"Input records : "
        f"{summary['total_raw_records']:,}"
    )
    print(
        f"Accepted      : "
        f"{summary['accepted_records']:,}"
    )
    print(
        f"Review        : "
        f"{summary['review_records']:,}"
    )
    print(
        f"Rejected      : "
        f"{summary['rejected_records']:,}"
    )
    print(
        f"Duplicates    : "
        f"{summary['duplicate_records']:,}"
    )
    print(
        f"Output total  : "
        f"{summary['output_total']:,}"
    )

    print("\nKEY RESOLUTIONS")
    print(
        "APS-code duplicate records removed       : "
        f"{summary['duplicate_records']:,}"
    )
    print(
        "Unit-floor mismatches corrected          : "
        f"{summary['unit_floor_mismatches_corrected']:,}"
    )
    print(
        "Bedroom URL mismatches resolved          : "
        f"{summary['bedroom_url_mismatches_resolved']:,}"
    )
    print(
        "Listing-type URL mismatches preserved    : "
        f"{summary['listing_type_url_mismatches_preserved']:,}"
    )
    print(
        "Missing districts retained               : "
        f"{summary['accepted_or_review_missing_district']:,}"
    )

    print("\nTOP REVIEW REASONS")
    review_counts = summary["review_reason_counts"]

    if review_counts:
        for reason, count in list(
            review_counts.items()
        )[:15]:
            print(
                f"{reason:<48}: {count}"
            )
    else:
        print("No review records.")

    print("\nTOP REJECTION REASONS")
    reject_counts = summary["reject_reason_counts"]

    if reject_counts:
        for reason, count in list(
            reject_counts.items()
        )[:15]:
            print(
                f"{reason:<48}: {count}"
            )
    else:
        print("No rejected records.")

    print("\nDUPLICATE REASONS")
    duplicate_counts = summary["duplicate_reason_counts"]

    if duplicate_counts:
        for reason, count in duplicate_counts.items():
            print(
                f"{reason:<48}: {count}"
            )
    else:
        print("No duplicate records.")

    print(f"\nSaved to: {OUTPUT_DIR}")
    print("=" * 78)


def main() -> None:
    input_path = find_input_path()

    raw_records = load_json_records(
        input_path
    )

    outputs = clean_records(
        raw_records
    )

    summary = build_summary(
        raw_records,
        outputs,
    )

    if (
        summary["output_total"]
        != summary["total_raw_records"]
    ):
        raise RuntimeError(
            "Cleaning output count does not match input count."
        )

    save_outputs(
        outputs,
        summary,
    )

    print_summary(summary)


if __name__ == "__main__":
    main()
