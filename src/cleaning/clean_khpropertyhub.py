from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Allow both:
#   python -m src.cleaning.clean_khpropertyhub
#   python src/cleaning/clean_khpropertyhub.py
PROJECT_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.cleaning.common import (
    PROJECT_ROOT,
    STANDARD_COLUMNS,
    add_reason,
    calculate_price_per_m2,
    clean_text,
    ensure_standard_columns,
    is_missing,
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


INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "bronze"
    / "khpropertyhub_com"
    / "raw_listings.json"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "silver"
    / "by_source"
    / "khpropertyhub"
)

SOURCE_NAME = "khpropertyhub.com"
TARGET_CITY = "Phnom Penh"
TARGET_PROPERTY_TYPES = {"Condo", "Penthouse"}

# These values create review flags. They are not automatic rejection limits.
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

EXPLICIT_MULTI_UNIT_PATTERN = re.compile(
    r"\b(?:entire|whole)\s+floor\b.*\b\d{2,3}\s*units?\b"
    r"|\b\d{2,3}\s*units?\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------


def build_global_listing_id(source_listing_id: Any) -> str:
    text = clean_text(source_listing_id) or "unknown"

    if text.lower().startswith("khpropertyhub.com_"):
        return text

    return f"{SOURCE_NAME}_{text}"


def duplicate_group_id(kind: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return f"khpropertyhub_{kind}_{digest}"


def normalize_option_list(value: Any) -> list[int] | None:
    if not isinstance(value, list):
        return None

    options: list[int] = []

    for item in value:
        number = safe_int(item)

        if number is not None and number >= 0:
            options.append(number)

    unique = sorted(set(options))
    return unique or None


def has_explicit_multi_unit_title(value: Any) -> bool:
    text = clean_text(value)
    return bool(text and EXPLICIT_MULTI_UNIT_PATTERN.search(text))


def is_sale_like_numeric_profile(record: dict[str, Any]) -> bool:
    price = safe_float(record.get("price_usd"))
    size = safe_float(record.get("size_m2"))
    ppm2 = safe_float(record.get("price_per_m2"))

    return (
        price is not None
        and size is not None
        and ppm2 is not None
        and REVIEW_LIMITS["price_min"]
        <= price
        <= REVIEW_LIMITS["price_max"]
        and REVIEW_LIMITS["size_min"]
        <= size
        <= REVIEW_LIMITS["size_max"]
        and REVIEW_LIMITS["price_per_m2_min"]
        <= ppm2
        <= REVIEW_LIMITS["price_per_m2_max"]
    )


# ---------------------------------------------------------------------------
# Source-specific field resolution
# ---------------------------------------------------------------------------


def resolve_unit_floor(
    raw: dict[str, Any],
) -> tuple[int | None, str | None, list[str], set[str]]:
    """
    Prefer an explicit floor in the current title when Bronze reports a
    title-versus-description conflict.

    In the audited records, titles explicitly said floors 9, 3, 6 and 21,
    while generic description parsing produced 6, 17, 11 and 1.
    """

    current = safe_int(raw.get("unit_floor"))
    current_source = clean_text(raw.get("unit_floor_source"))
    title_value = safe_int(raw.get("unit_floor_title_value"))
    title_source = clean_text(raw.get("unit_floor_title_source"))
    conflict = clean_text(raw.get("unit_floor_conflict"))

    notes: list[str] = []
    resolved: set[str] = set()

    if conflict and title_value is not None and 1 <= title_value <= 100:
        add_reason(
            notes,
            "unit floor corrected from explicit title: "
            f"{current} -> {title_value}",
        )
        add_reason(notes, f"original unit_floor_conflict: {conflict}")
        resolved.add("unit_floor_conflict")

        return (
            title_value,
            title_source or "khpropertyhub_com_title",
            notes,
            resolved,
        )

    return current, current_source, notes, resolved


def resolve_bedrooms(
    raw: dict[str, Any],
) -> tuple[
    int | None,
    str | None,
    list[int] | None,
    bool,
    list[str],
]:
    bedrooms = safe_int(raw.get("bedrooms"))
    source = clean_text(raw.get("bedrooms_source"))
    options = normalize_option_list(raw.get("bedroom_options"))

    multi_unit_options = bool(
        raw.get("multi_unit_options")
        or (options is not None and len(options) > 1)
    )

    notes: list[str] = []

    if multi_unit_options:
        bedrooms = None
        source = None
        add_reason(
            notes,
            "multiple bedroom configurations preserved in bedroom_options",
        )

    return bedrooms, source, options, multi_unit_options, notes


def collect_unresolved_conflicts(
    raw: dict[str, Any],
    resolved_conflicts: set[str],
) -> list[tuple[str, str]]:
    conflicts: list[tuple[str, str]] = []

    for key, value in raw.items():
        if not key.endswith("_conflict"):
            continue

        text = clean_text(value)

        if not text or key in resolved_conflicts:
            continue

        conflicts.append((key, text))

    return conflicts


# ---------------------------------------------------------------------------
# Record normalization
# ---------------------------------------------------------------------------


def normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    source_listing_id = clean_text(raw.get("listing_id"))
    source_listing_code = clean_text(raw.get("property_code"))

    title = clean_text(raw.get("title"))
    description = clean_text(raw.get("description"))
    url = clean_text(raw.get("url"))

    listing_type = normalize_listing_type(raw.get("listing_type"))
    property_type = normalize_property_type_label(
        raw.get("property_type")
    )

    price_usd = safe_float(raw.get("price_usd"))
    size_m2 = safe_float(raw.get("size_m2"))

    (
        bedrooms,
        bedrooms_source,
        bedroom_options,
        multi_unit_options,
        bedroom_notes,
    ) = resolve_bedrooms(raw)

    bathrooms = safe_int(raw.get("bathrooms"))

    (
        unit_floor,
        unit_floor_source,
        floor_notes,
        resolved_conflicts,
    ) = resolve_unit_floor(raw)

    building_total_floors = safe_int(
        raw.get("building_total_floors")
    )

    province = clean_text(raw.get("province")) or TARGET_CITY
    district = normalize_district(raw.get("district"))

    notes: list[str] = []
    notes.extend(bedroom_notes)
    notes.extend(floor_notes)

    source_out_of_scope = clean_text(
        raw.get("out_of_scope_reason")
    )
    if source_out_of_scope:
        add_reason(
            notes,
            f"Bronze out_of_scope_reason: {source_out_of_scope}",
        )

    # Preserve useful source-reference diagnostics without automatically
    # treating every expected search-scope mismatch as a review reason.
    for key in [
        "listing_type_search_mismatch",
        "property_type_reference_mismatch",
        "bedrooms_reference_mismatch",
        "unit_floor_reference_mismatch",
    ]:
        value = clean_text(raw.get(key))
        if value:
            add_reason(notes, f"{key}: {value}")

    unresolved_conflicts = collect_unresolved_conflicts(
        raw,
        resolved_conflicts,
    )

    for key, value in unresolved_conflicts:
        add_reason(notes, f"{key}: {value}")

    explicit_multi_unit = has_explicit_multi_unit_title(title)

    record: dict[str, Any] = {
        # Identity
        "listing_id": build_global_listing_id(source_listing_id),
        "source": SOURCE_NAME,
        "source_listing_id": source_listing_id,
        "source_listing_code": source_listing_code,
        "url": url,
        "canonical_url": normalize_url(url),

        # Listing information
        "title": title,
        "description": description,
        "listing_type": listing_type,
        "property_type": property_type,
        "property_type_original": normalize_property_type_label(
            raw.get("property_type")
        ),
        "project_name": clean_text(raw.get("project_name")),

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
        "bathrooms": bathrooms,
        "unit_floor": unit_floor,
        "building_total_floors": building_total_floors,
        "bedroom_options": bedroom_options,
        "multi_unit_options": multi_unit_options,

        # Location
        "city": province,
        "district": district,
        "commune": clean_text(raw.get("commune")),
        "address": clean_text(raw.get("address")),
        "location_text": (
            clean_text(raw.get("location_text"))
            or district
        ),
        "latitude": safe_float(raw.get("latitude")),
        "longitude": safe_float(raw.get("longitude")),

        # Dates
        "listing_created_at": clean_text(raw.get("created_at")),
        "listing_updated_at": None,
        "scraped_at": clean_text(raw.get("scraped_at")),

        # Cleaning status
        "record_status": None,
        "needs_manual_review": False,
        "review_reason": None,
        "reject_reason": None,
        "duplicate_group_id": None,
        "duplicate_reason": None,
        "cleaning_notes": join_reasons(notes),

        # Field sources
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
            raw.get("building_total_floors_source")
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
        "_display_as_project": bool(
            raw.get("display_as_project")
        ),
        "_explicit_multi_unit": explicit_multi_unit,
        "_raw_manual_review": bool(
            raw.get("needs_manual_review")
        ),
        "_resolved_conflicts": sorted(resolved_conflicts),
        "_unresolved_conflicts": [
            key for key, _ in unresolved_conflicts
        ],
    }

    return record


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_record(
    record: dict[str, Any],
    raw: dict[str, Any],
) -> dict[str, Any]:
    reject_reasons: list[str] = []
    review_reasons: list[str] = []

    listing_type = record.get("listing_type")
    property_type = record.get("property_type")

    price = safe_float(record.get("price_usd"))
    size = safe_float(record.get("size_m2"))
    ppm2 = safe_float(record.get("price_per_m2"))
    bedrooms = safe_int(record.get("bedrooms"))
    bathrooms = safe_int(record.get("bathrooms"))
    unit_floor = safe_int(record.get("unit_floor"))
    total_floors = safe_int(
        record.get("building_total_floors")
    )

    unresolved_conflicts = set(
        record.get("_unresolved_conflicts") or []
    )

    # Hard rejection rules.
    if listing_type == "rent":
        add_reason(reject_reasons, "rent_listing")
    elif listing_type not in {"sale", "sale/rent"}:
        add_reason(reject_reasons, "unknown_listing_type")

    if property_type not in TARGET_PROPERTY_TYPES:
        add_reason(
            reject_reasons,
            "not_condo_or_penthouse",
        )

    if record.get("_display_as_project"):
        add_reason(
            reject_reasons,
            "project_level_listing",
        )

    if (
        record.get("_explicit_multi_unit")
        or record.get("multi_unit_options")
    ):
        add_reason(
            reject_reasons,
            "multi_unit_listing",
        )

    if price is None:
        add_reason(reject_reasons, "missing_price")
    elif price <= 0:
        add_reason(reject_reasons, "invalid_price")

    if size is None:
        add_reason(reject_reasons, "missing_size")
    elif size <= 0:
        add_reason(reject_reasons, "invalid_size")

    # Review rules.
    if (
        listing_type == "sale/rent"
        and not is_sale_like_numeric_profile(record)
    ):
        add_reason(
            review_reasons,
            "sale_rent_ambiguous_price_profile",
        )


    for conflict_key in sorted(unresolved_conflicts):
        # Property-type conflicts are already handled by the normalized
        # property type and hard target-scope rule.
        if conflict_key == "property_type_conflict":
            continue

        add_reason(review_reasons, conflict_key)

    if not clean_text(record.get("district")):
        add_reason(review_reasons, "missing_district")

    if price is not None:
        if price < REVIEW_LIMITS["price_min"]:
            add_reason(
                review_reasons,
                "price_below_review_limit",
            )
        elif price > REVIEW_LIMITS["price_max"]:
            add_reason(
                review_reasons,
                "price_above_review_limit",
            )

    if size is not None:
        if size < REVIEW_LIMITS["size_min"]:
            add_reason(
                review_reasons,
                "size_below_review_limit",
            )
        elif size > REVIEW_LIMITS["size_max"]:
            add_reason(
                review_reasons,
                "size_above_review_limit",
            )

    if ppm2 is not None:
        if ppm2 < REVIEW_LIMITS["price_per_m2_min"]:
            add_reason(
                review_reasons,
                "price_per_m2_below_review_limit",
            )
        elif ppm2 > REVIEW_LIMITS["price_per_m2_max"]:
            add_reason(
                review_reasons,
                "price_per_m2_above_review_limit",
            )

    if (
        bedrooms is not None
        and bedrooms > REVIEW_LIMITS["bedrooms_max"]
    ):
        add_reason(
            review_reasons,
            "bedrooms_above_review_limit",
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
    reason: str,
    group_id: str,
) -> dict[str, Any]:
    record["record_status"] = "duplicate"
    record["needs_manual_review"] = False
    record["duplicate_reason"] = reason
    record["duplicate_group_id"] = group_id
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

    seen_listing_ids: set[str] = set()
    seen_urls: set[str] = set()
    seen_property_codes: set[str] = set()

    for raw in raw_records:
        record = normalize_record(raw)

        source_listing_id = clean_text(
            record.get("source_listing_id")
        )
        canonical_url = clean_text(
            record.get("canonical_url")
        )
        property_code = clean_text(
            record.get("source_listing_code")
        )

        duplicate_reason: str | None = None
        group_id: str | None = None

        if (
            source_listing_id
            and source_listing_id in seen_listing_ids
        ):
            duplicate_reason = (
                "duplicate_source_listing_id"
            )
            group_id = duplicate_group_id(
                "listing_id",
                source_listing_id,
            )
        elif canonical_url and canonical_url in seen_urls:
            duplicate_reason = "duplicate_canonical_url"
            group_id = duplicate_group_id(
                "url",
                canonical_url,
            )
        elif (
            property_code
            and property_code in seen_property_codes
        ):
            duplicate_reason = (
                "duplicate_source_listing_code"
            )
            group_id = duplicate_group_id(
                "property_code",
                property_code,
            )

        if duplicate_reason and group_id:
            duplicate = mark_duplicate(
                record,
                duplicate_reason,
                group_id,
            )
            outputs["duplicates"].append(
                ensure_standard_columns(duplicate)
            )
            continue

        if source_listing_id:
            seen_listing_ids.add(source_listing_id)

        if canonical_url:
            seen_urls.add(canonical_url)

        if property_code:
            seen_property_codes.add(property_code)

        classified = classify_record(record, raw)
        status = str(classified["record_status"])

        outputs[status].append(
            ensure_standard_columns(classified)
        )

    return outputs


# ---------------------------------------------------------------------------
# Reporting and output
# ---------------------------------------------------------------------------


def build_summary(
    raw_records: list[dict[str, Any]],
    outputs: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    accepted = outputs["accepted"]
    review = outputs["review"]
    rejected = outputs["rejected"]
    duplicates = outputs["duplicates"]

    review_reason_counts: Counter[str] = Counter()
    reject_reason_counts: Counter[str] = Counter()

    for row in review:
        text = clean_text(row.get("review_reason"))

        if text:
            for reason in text.split("; "):
                review_reason_counts[reason] += 1

    for row in rejected:
        text = clean_text(row.get("reject_reason"))

        if text:
            for reason in text.split("; "):
                reject_reason_counts[reason] += 1

    all_outputs = [
        row
        for group in outputs.values()
        for row in group
    ]

    accepted_sale_rent = sum(
        row.get("listing_type") == "sale/rent"
        for row in accepted
    )

    floor_corrections = sum(
        "unit floor corrected from explicit title:"
        in str(row.get("cleaning_notes") or "")
        for row in all_outputs
    )

    rejected_multi_unit_records = sum(
        "multi_unit_listing"
        in str(row.get("reject_reason") or "")
        for row in rejected
    )

    rejected_non_condo = sum(
        "not_condo_or_penthouse"
        in str(row.get("reject_reason") or "")
        for row in rejected
    )

    raw_listing_types = Counter(
        normalize_listing_type(
            row.get("listing_type")
        )
        or "Missing"
        for row in raw_records
    )

    raw_property_types = Counter(
        normalize_property_type_label(
            row.get("property_type")
        )
        or "Missing"
        for row in raw_records
    )

    return {
        "source": SOURCE_NAME,
        "input_path": str(INPUT_PATH),
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
        "accepted_sale_rent_records": accepted_sale_rent,
        "resolved_unit_floor_conflicts": floor_corrections,
        "rejected_multi_unit_records": (
            rejected_multi_unit_records
        ),
        "rejected_non_condo_records": rejected_non_condo,
        "raw_listing_types": dict(raw_listing_types),
        "raw_property_types": dict(raw_property_types),
        "review_reason_counts": dict(
            review_reason_counts.most_common()
        ),
        "reject_reason_counts": dict(
            reject_reason_counts.most_common()
        ),
        "review_limits": REVIEW_LIMITS,
        "standard_columns": STANDARD_COLUMNS,
    }


def save_outputs(
    outputs: dict[str, list[dict[str, Any]]],
    summary: dict[str, Any],
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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
        OUTPUT_DIR / "cleaning_summary.json"
    ).write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def print_summary(summary: dict[str, Any]) -> None:
    print(
        "\nKHPROPERTYHUB CLEANING SUMMARY — V1"
    )
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
        "Accepted sale/rent with sale-like price : "
        f"{summary['accepted_sale_rent_records']:,}"
    )
    print(
        "Unit-floor conflicts corrected by title : "
        f"{summary['resolved_unit_floor_conflicts']:,}"
    )
    print(
        "Multi-unit/configuration records rejected: "
        f"{summary['rejected_multi_unit_records']:,}"
    )
    print(
        "Non-condo records rejected              : "
        f"{summary['rejected_non_condo_records']:,}"
    )

    print("\nTOP REVIEW REASONS")
    review_counts = summary["review_reason_counts"]

    if review_counts:
        for reason, count in list(
            review_counts.items()
        )[:15]:
            print(f"{reason:<48}: {count}")
    else:
        print("No review records.")

    print("\nTOP REJECTION REASONS")
    reject_counts = summary["reject_reason_counts"]

    if reject_counts:
        for reason, count in list(
            reject_counts.items()
        )[:15]:
            print(f"{reason:<48}: {count}")
    else:
        print("No rejected records.")

    print(f"\nSaved to: {OUTPUT_DIR}")
    print("=" * 78)


def main() -> None:
    raw_records = load_json_records(INPUT_PATH)
    outputs = clean_records(raw_records)
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

    save_outputs(outputs, summary)
    print_summary(summary)


if __name__ == "__main__":
    main()