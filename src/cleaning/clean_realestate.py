from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Allow both:
#   python -m src.cleaning.clean_realestate
#   python src/cleaning/clean_realestate.py
PROJECT_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORT))

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
    / "realestate"
    / "raw_listings.json"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "silver"
    / "by_source"
    / "realestate"
)

SOURCE_NAME = "realestate.com.kh"
CITY_NAME = "Phnom Penh"

# These limits send a record to review. They do not automatically reject it.
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

TARGET_PROPERTY_TYPES = {"Condo", "Penthouse"}
AMBIGUOUS_PROPERTY_TYPES = {
    "Apartment",
    "Serviced Apartment",
    "Project",
}

NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

NON_TARGET_TITLE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "Commercial",
        re.compile(
            r"\b(?:office(?:\s+space)?|commercial(?:\s+(?:property|building|space))?|warehouse)\b",
            re.I,
        ),
    ),
    ("Hotel", re.compile(r"\bhotel\b", re.I)),
    (
        "Land",
        re.compile(
            r"\b(?:land\s+(?:for\s+sale|sale)|plot\s+of\s+land)\b",
            re.I,
        ),
    ),
    (
        "House",
        re.compile(
            r"\b(?:house\s+(?:for\s+sale|sale)|shophouse|shop\s+house)\b",
            re.I,
        ),
    ),
    ("Villa", re.compile(r"\bvilla\b", re.I)),
]


def build_global_listing_id(source_listing_id: Any) -> str:
    """Create a globally unique listing ID for the merged dataset."""

    text = clean_text(source_listing_id) or "unknown"
    return f"{SOURCE_NAME}_{text}"


def duplicate_group_id(kind: str, value: str) -> str:
    """Create a stable short ID for a duplicate group."""

    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return f"realestate_{kind}_{digest}"


def combined_listing_text(raw: dict[str, Any]) -> str:
    """Combine the most useful visible listing text for conservative rules."""

    return " ".join(
        clean_text(raw.get(field)) or ""
        for field in (
            "title",
            "detail_title",
            "description",
        )
    )


def detect_explicit_non_target_type(
    title: str | None,
    description: str | None,
) -> str | None:
    """
    Detect clear non-condo property types conservatively.

    Marketing phrases such as "Sky Villa" are not treated as a landed villa
    when the same text also clearly says condo or penthouse.
    """

    title_text = clean_text(title) or ""
    lowered = title_text.lower()

    condo_evidence = bool(
        re.search(r"\b(?:condo|condominium|penthouse)\b", lowered)
    )

    if "sky villa" in lowered and condo_evidence:
        return None

    for property_type, pattern in NON_TARGET_TITLE_PATTERNS:
        if pattern.search(title_text):
            # Avoid treating a hotel-residence condo unit as an entire hotel.
            if property_type == "Hotel" and condo_evidence:
                continue

            return property_type

    return None


def resolve_property_type(
    raw_type: Any,
    title: str | None,
    description: str | None,
) -> tuple[str | None, str | None, list[str]]:
    """
    Resolve the merge-ready property type.

    Returns:
        resolved_type, source_label, cleaning_notes
    """

    notes: list[str] = []
    normalized = normalize_property_type_label(raw_type)
    title_text = (clean_text(title) or "").lower()
    description_text = (clean_text(description) or "").lower()
    combined = f"{title_text} {description_text}"

    explicit_non_target = detect_explicit_non_target_type(
        title,
        description,
    )

    if explicit_non_target:
        add_reason(
            notes,
            f"explicit text indicates {explicit_non_target}",
        )
        return explicit_non_target, "title_or_description", notes

    if re.search(r"\bpenthouse\b", combined):
        if normalized != "Penthouse":
            add_reason(notes, f"mapped {normalized} to Penthouse from text")
        return "Penthouse", "title_or_description", notes

    if re.search(r"\b(?:condo|condominium)\b", combined):
        if normalized != "Condo":
            add_reason(notes, f"mapped {normalized} to Condo from text")
        return "Condo", "title_or_description", notes

    if normalized == "Studio":
        add_reason(notes, "mapped Studio to Condo")
        return "Condo", "realestate_property_type", notes

    return normalized, "realestate_property_type", notes


def parse_explicit_title_bedrooms(title: Any) -> tuple[int | None, str | None]:
    """
    Extract an explicit bedroom count from the current title.

    This deliberately uses strong patterns only. It avoids treating project
    numbers, floor numbers, bathroom counts, or other numbers as bedrooms.
    """

    text = clean_text(title)
    if text is None:
        return None, None

    lowered = text.lower()

    if re.search(r"\bstudio\b", lowered):
        return 0, "Studio"

    plus_match = re.search(
        r"\b(\d{1,2})\s*\+\s*(\d{1,2})\s*(?:bedrooms?|beds?|br)\b",
        lowered,
        re.I,
    )
    if plus_match:
        first = int(plus_match.group(1))
        second = int(plus_match.group(2))
        return first + second, plus_match.group(0)

    number_match = re.search(
        r"\b(\d{1,2})\s*[- ]?\s*(?:bedrooms?|beds?|br)\b",
        lowered,
        re.I,
    )
    if number_match:
        return int(number_match.group(1)), number_match.group(0)

    word_pattern = "|".join(NUMBER_WORDS)
    word_match = re.search(
        rf"\b({word_pattern})\s+bedrooms?\b",
        lowered,
        re.I,
    )
    if word_match:
        word = word_match.group(1).lower()
        return NUMBER_WORDS[word], word_match.group(0)

    return None, None


def resolve_bedrooms(
    raw: dict[str, Any],
) -> tuple[int | None, str | None, list[str], set[str]]:
    """
    Resolve bedroom conflicts using the current visible title.

    Studio is standardized to zero bedrooms. Explicit title layouts such as
    "3+1 Bedroom" are interpreted as four rooms for this dataset because the
    Bronze value and URL also represent the total bedroom layout.
    """

    notes: list[str] = []
    resolved_conflicts: set[str] = set()

    raw_value = safe_int(raw.get("bedrooms"))
    raw_source = clean_text(raw.get("bedrooms_source"))

    title_candidates = [
        raw.get("title"),
        raw.get("detail_title"),
    ]

    explicit_value: int | None = None
    explicit_raw: str | None = None

    for candidate in title_candidates:
        explicit_value, explicit_raw = parse_explicit_title_bedrooms(candidate)
        if explicit_value is not None:
            break

    property_type_original = normalize_property_type_label(
        raw.get("property_type")
    )

    if explicit_value is None and property_type_original == "Studio":
        explicit_value = 0
        explicit_raw = "property_type=Studio"

    if explicit_value is not None:
        if raw_value != explicit_value:
            add_reason(
                notes,
                (
                    f"bedrooms reference mismatch: Bronze={raw_value}; "
                    f"explicit title={explicit_value} from {explicit_raw}"
                ),
            )

        if not is_missing(raw.get("bedrooms_conflict")):
            resolved_conflicts.add("bedrooms_conflict")

        source = (
            "realestate_title_studio"
            if explicit_value == 0
            else "realestate_current_title"
        )
        return explicit_value, source, notes, resolved_conflicts

    return raw_value, raw_source, notes, resolved_conflicts


def collect_unresolved_conflicts(
    raw: dict[str, Any],
    resolved_conflicts: set[str],
) -> list[tuple[str, str]]:
    """Collect only conflict fields that were not safely resolved."""

    conflicts: list[tuple[str, str]] = []

    for key, value in raw.items():
        if not key.endswith("_conflict"):
            continue
        if key in resolved_conflicts:
            continue
        if is_missing(value):
            continue

        conflicts.append((key, clean_text(value) or str(value)))

    return conflicts


def is_sale_like_numeric_profile(record: dict[str, Any]) -> bool:
    """Check whether a sale/rent record clearly carries a plausible sale price."""

    price = safe_float(record.get("price_usd"))
    size = safe_float(record.get("size_m2"))
    ppm2 = safe_float(record.get("price_per_m2"))

    return bool(
        price is not None
        and size is not None
        and REVIEW_LIMITS["price_min"] <= price <= REVIEW_LIMITS["price_max"]
        and REVIEW_LIMITS["size_min"] <= size <= REVIEW_LIMITS["size_max"]
        and ppm2 is not None
        and REVIEW_LIMITS["price_per_m2_min"]
        <= ppm2
        <= REVIEW_LIMITS["price_per_m2_max"]
    )


def normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a Realestate Bronze record into the shared schema."""

    source_listing_id = clean_text(raw.get("listing_id"))
    title = clean_text(raw.get("title"))
    description = clean_text(raw.get("description"))

    property_type_original = normalize_property_type_label(
        raw.get("property_type")
    )

    (
        property_type,
        property_type_source,
        type_notes,
    ) = resolve_property_type(
        property_type_original,
        title,
        description,
    )

    (
        bedrooms,
        bedrooms_source,
        bedroom_notes,
        resolved_conflicts,
    ) = resolve_bedrooms(raw)

    price_usd = safe_float(raw.get("price_usd"))
    size_m2 = safe_float(raw.get("size_m2"))
    bathrooms = safe_int(raw.get("bathrooms"))
    unit_floor = safe_int(raw.get("unit_floor"))
    building_total_floors = safe_int(
        raw.get("building_total_floors")
    )

    listing_type = normalize_listing_type(raw.get("listing_type"))
    district = normalize_district(raw.get("district"))
    canonical_url = normalize_url(raw.get("url"))

    notes = list(type_notes)
    notes.extend(bedroom_notes)

    if raw.get("detail_json_exact_match") is False:
        add_reason(notes, "detail JSON was not an exact listing match")

    unresolved_conflicts = collect_unresolved_conflicts(
        raw,
        resolved_conflicts,
    )
    for key, value in unresolved_conflicts:
        add_reason(notes, f"{key}: {value}")

    record: dict[str, Any] = {
        # Identity
        "listing_id": build_global_listing_id(source_listing_id),
        "source": SOURCE_NAME,
        "source_listing_id": source_listing_id,
        "source_listing_code": None,
        "url": clean_text(raw.get("url")),
        "canonical_url": canonical_url,

        # Main information
        "title": title,
        "description": description,
        "listing_type": listing_type,
        "property_type": property_type,
        "property_type_original": property_type_original,
        "project_name": clean_text(raw.get("project_name")),

        # Price and size
        "price_usd": price_usd,
        "size_m2": size_m2,
        "price_per_m2": calculate_price_per_m2(price_usd, size_m2),
        "price_original": clean_text(raw.get("price_display")),

        # Features
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "unit_floor": unit_floor,
        "building_total_floors": building_total_floors,
        "bedroom_options": None,
        "multi_unit_options": False,

        # Location
        "city": CITY_NAME,
        "district": district,
        "commune": clean_text(raw.get("commune")),
        "address": clean_text(raw.get("address")),
        "location_text": clean_text(raw.get("address")),
        "latitude": safe_float(raw.get("latitude")),
        "longitude": safe_float(raw.get("longitude")),

        # Dates
        "listing_created_at": clean_text(raw.get("created_at")),
        "listing_updated_at": None,
        "scraped_at": clean_text(raw.get("scraped_at")),

        # Cleaning status - filled later
        "record_status": None,
        "needs_manual_review": False,
        "review_reason": None,
        "reject_reason": None,
        "duplicate_group_id": None,
        "duplicate_reason": None,
        "cleaning_notes": join_reasons(notes),

        # Field sources
        "price_usd_source": clean_text(raw.get("price_usd_source"))
        or "realestate_detail_json",
        "size_m2_source": clean_text(raw.get("size_m2_source"))
        or "realestate_detail_json",
        "bedrooms_source": bedrooms_source,
        "bathrooms_source": clean_text(raw.get("bathrooms_source")),
        "unit_floor_source": clean_text(raw.get("unit_floor_source")),
        "building_total_floors_source": clean_text(
            raw.get("building_total_floors_source")
        ),
        "district_source": "realestate_location",
        "listing_type_source": clean_text(raw.get("listing_type_source"))
        or "realestate_search_and_detail",
        "property_type_source": property_type_source,

        # Internal fields removed by ensure_standard_columns().
        "_resolved_conflicts": sorted(resolved_conflicts),
        "_unresolved_conflicts": [
            key for key, _ in unresolved_conflicts
        ],
        "_is_project_page": bool(raw.get("display_as_project")),
    }

    return record


def classify_record(
    record: dict[str, Any],
    raw: dict[str, Any],
) -> dict[str, Any]:
    """Assign accepted, review or rejected status."""

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
    total_floors = safe_int(record.get("building_total_floors"))

    unresolved_conflicts = set(record.get("_unresolved_conflicts") or [])
    is_project_page = bool(record.get("_is_project_page"))

    # Hard rejection rules
    if listing_type == "rent":
        add_reason(reject_reasons, "rent_listing")

    if listing_type not in {"sale", "sale/rent", "rent"}:
        add_reason(reject_reasons, "unknown_listing_type")

    # Project overview/development pages are not individual unit records.
    if is_project_page:
        add_reason(reject_reasons, "project_level_listing")

    # Apartment, Serviced Apartment and Project remain non-target when the
    # page has no explicit condo/penthouse evidence.
    if property_type not in TARGET_PROPERTY_TYPES:
        add_reason(reject_reasons, "not_condo_or_penthouse")

    if price is None:
        add_reason(reject_reasons, "missing_price")
    elif price <= 0:
        add_reason(reject_reasons, "invalid_price")

    if size is None:
        add_reason(reject_reasons, "missing_size")
    elif size <= 0:
        add_reason(reject_reasons, "invalid_size")

    # Review rules
    # Sale/rent records are accepted only when price, size and price/m² form a
    # clear sale-like profile. Otherwise they remain review candidates unless
    # a hard rejection rule already applies.
    if listing_type == "sale/rent" and not is_sale_like_numeric_profile(record):
        add_reason(review_reasons, "sale_rent_ambiguous_price_profile")

    # Only unresolved Bronze conflicts create review flags.
    for conflict_key in sorted(unresolved_conflicts):
        add_reason(review_reasons, conflict_key)

    if bool(raw.get("needs_manual_review")) and unresolved_conflicts:
        add_reason(review_reasons, "bronze_manual_review_flag")

    if raw.get("detail_json_exact_match") is False:
        add_reason(review_reasons, "detail_json_not_exact_match")

    # Suspicious numeric values go to review, not rejection.
    if price is not None:
        if price < REVIEW_LIMITS["price_min"]:
            add_reason(review_reasons, "price_below_review_limit")
        elif price > REVIEW_LIMITS["price_max"]:
            add_reason(review_reasons, "price_above_review_limit")

    if size is not None:
        if size < REVIEW_LIMITS["size_min"]:
            add_reason(review_reasons, "size_below_review_limit")
        elif size > REVIEW_LIMITS["size_max"]:
            add_reason(review_reasons, "size_above_review_limit")

    if ppm2 is not None:
        if ppm2 < REVIEW_LIMITS["price_per_m2_min"]:
            add_reason(review_reasons, "price_per_m2_below_review_limit")
        elif ppm2 > REVIEW_LIMITS["price_per_m2_max"]:
            add_reason(review_reasons, "price_per_m2_above_review_limit")

    if bedrooms is not None and bedrooms > REVIEW_LIMITS["bedrooms_max"]:
        add_reason(review_reasons, "bedrooms_above_review_limit")

    if bathrooms is not None and bathrooms > REVIEW_LIMITS["bathrooms_max"]:
        add_reason(review_reasons, "bathrooms_above_review_limit")

    if unit_floor is not None and unit_floor > REVIEW_LIMITS["unit_floor_max"]:
        add_reason(review_reasons, "unit_floor_above_review_limit")

    if (
        total_floors is not None
        and total_floors > REVIEW_LIMITS["building_total_floors_max"]
    ):
        add_reason(review_reasons, "building_floors_above_review_limit")

    if (
        unit_floor is not None
        and total_floors is not None
        and unit_floor > total_floors
    ):
        add_reason(review_reasons, "unit_floor_exceeds_building_floors")

    if reject_reasons:
        record["record_status"] = "rejected"
        record["needs_manual_review"] = False
        record["reject_reason"] = join_reasons(reject_reasons)
        record["review_reason"] = join_reasons(review_reasons)
        return record

    if review_reasons:
        record["record_status"] = "review"
        record["needs_manual_review"] = True
        record["review_reason"] = join_reasons(review_reasons)
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
    """Mark a normalized record as a within-source duplicate."""

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
    """Normalize, deduplicate and classify all records."""

    outputs: dict[str, list[dict[str, Any]]] = {
        "accepted": [],
        "review": [],
        "rejected": [],
        "duplicates": [],
    }

    seen_listing_ids: dict[str, str] = {}
    seen_urls: dict[str, str] = {}

    for raw in raw_records:
        record = normalize_record(raw)

        source_listing_id = clean_text(record.get("source_listing_id"))
        canonical_url = clean_text(record.get("canonical_url"))

        duplicate_reason: str | None = None
        group_id: str | None = None

        if source_listing_id and source_listing_id in seen_listing_ids:
            duplicate_reason = "duplicate_source_listing_id"
            group_id = duplicate_group_id("listing_id", source_listing_id)

        elif canonical_url and canonical_url in seen_urls:
            duplicate_reason = "duplicate_canonical_url"
            group_id = duplicate_group_id("url", canonical_url)

        if duplicate_reason and group_id:
            duplicate = mark_duplicate(record, duplicate_reason, group_id)
            outputs["duplicates"].append(
                ensure_standard_columns(duplicate)
            )
            continue

        if source_listing_id:
            seen_listing_ids[source_listing_id] = record["listing_id"]

        if canonical_url:
            seen_urls[canonical_url] = record["listing_id"]

        classified = classify_record(record, raw)
        status = classified["record_status"]

        outputs[status].append(
            ensure_standard_columns(classified)
        )

    return outputs


def build_summary(
    raw_records: list[dict[str, Any]],
    outputs: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Create a source-level cleaning summary."""

    raw_listing_types = Counter(
        normalize_listing_type(row.get("listing_type")) or "Missing"
        for row in raw_records
    )

    raw_property_types = Counter(
        normalize_property_type_label(row.get("property_type")) or "Missing"
        for row in raw_records
    )

    accepted = outputs["accepted"]
    review = outputs["review"]
    rejected = outputs["rejected"]
    duplicates = outputs["duplicates"]

    review_reason_counts: Counter[str] = Counter()
    reject_reason_counts: Counter[str] = Counter()

    for row in review:
        reason_text = clean_text(row.get("review_reason"))
        if reason_text:
            for reason in reason_text.split("; "):
                review_reason_counts[reason] += 1

    for row in rejected:
        reason_text = clean_text(row.get("reject_reason"))
        if reason_text:
            for reason in reason_text.split("; "):
                reject_reason_counts[reason] += 1

    accepted_sale_rent = sum(
        row.get("listing_type") == "sale/rent"
        for row in accepted
    )
    resolved_studios = sum(
        row.get("bedrooms") == 0
        and row.get("bedrooms_source") == "realestate_title_studio"
        for group in outputs.values()
        for row in group
    )
    rejected_project_pages = sum(
        "project_level_listing" in str(row.get("reject_reason") or "")
        for row in rejected
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
        "resolved_studio_records": resolved_studios,
        "rejected_project_page_records": rejected_project_pages,
        "raw_listing_types": dict(raw_listing_types),
        "raw_property_types": dict(raw_property_types),
        "review_reason_counts": dict(review_reason_counts.most_common()),
        "reject_reason_counts": dict(reject_reason_counts.most_common()),
        "review_limits": REVIEW_LIMITS,
        "standard_columns": STANDARD_COLUMNS,
    }


def save_outputs(
    outputs: dict[str, list[dict[str, Any]]],
    summary: dict[str, Any],
) -> None:
    """Write JSON, CSV and summary files."""

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

    summary_path = OUTPUT_DIR / "cleaning_summary.json"
    summary_path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def print_summary(summary: dict[str, Any]) -> None:
    """Display a concise cleaning report."""

    print("\nREALESTATE.COM.KH CLEANING SUMMARY — V2")
    print("=" * 78)
    print(f"Input records : {summary['total_raw_records']:,}")
    print(f"Accepted      : {summary['accepted_records']:,}")
    print(f"Review        : {summary['review_records']:,}")
    print(f"Rejected      : {summary['rejected_records']:,}")
    print(f"Duplicates    : {summary['duplicate_records']:,}")
    print(f"Output total  : {summary['output_total']:,}")

    print("\nKEY RESOLUTIONS")
    print(
        f"Accepted sale/rent with sale-like price : "
        f"{summary['accepted_sale_rent_records']:,}"
    )
    print(
        f"Studio records standardized to 0 beds   : "
        f"{summary['resolved_studio_records']:,}"
    )
    print(
        f"Project-level pages rejected            : "
        f"{summary['rejected_project_page_records']:,}"
    )

    print("\nTOP REVIEW REASONS")
    review_counts = summary["review_reason_counts"]
    if review_counts:
        for reason, count in list(review_counts.items())[:15]:
            print(f"{reason:<48}: {count}")
    else:
        print("No review records.")

    print("\nTOP REJECTION REASONS")
    reject_counts = summary["reject_reason_counts"]
    if reject_counts:
        for reason, count in list(reject_counts.items())[:15]:
            print(f"{reason:<48}: {count}")
    else:
        print("No rejected records.")

    print(f"\nSaved to: {OUTPUT_DIR}")
    print("=" * 78)


def main() -> None:
    raw_records = load_json_records(INPUT_PATH)
    outputs = clean_records(raw_records)
    summary = build_summary(raw_records, outputs)

    if summary["output_total"] != summary["total_raw_records"]:
        raise RuntimeError(
            "Cleaning output count does not match input count."
        )

    save_outputs(outputs, summary)
    print_summary(summary)


if __name__ == "__main__":
    main()
