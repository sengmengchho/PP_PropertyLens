from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


# Supports:
#   python -m src.cleaning.clean_camrealty
#   python src/cleaning/clean_camrealty.py
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
    / "camrealtyservice_com"
    / "raw_listings.json",

    PROJECT_ROOT
    / "data"
    / "bronze"
    / "camrealtyservice"
    / "raw_listings.json",

    PROJECT_ROOT
    / "data"
    / "bronze"
    / "camrealty"
    / "raw_listings.json",
]

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "silver"
    / "by_source"
    / "camrealty"
)

SOURCE_NAME = "camrealtyservice.com"
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

# CamRealty codes seen in the source include S, N, SL and similar prefixes.
VALID_CODE_RE = re.compile(
    r"^[A-Z]{1,3}\d{5,}$",
    re.I,
)

URL_CODE_RE = re.compile(
    r"(?:-|/)([A-Z]{1,3}\d{5,})(?:-\d+)?/?$",
    re.I,
)

PRICE_WITH_CURRENCY_RE = re.compile(
    r"""
    (?:
        \$\s*
        (?P<prefix_amount>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{5,8}(?:\.\d+)?)
    )
    |
    (?:
        (?P<suffix_amount>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{5,8}(?:\.\d+)?)
        \s*(?:USD|\$)
    )
    """,
    re.I | re.X,
)

EXPLICIT_MULTI_UNIT_RE = re.compile(
    r"""
    \b(?:entire|whole|full)[-\s]+floor\b
    |
    \b\d{2,3}\s*units?\b
    |
    \b(?:hotel|apartment\s+building)\b
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
        "CamRealtyService Bronze file was not found.\n"
        f"Checked:\n{checked}"
    )


def normalize_code(value: Any) -> str | None:
    code = clean_text(value)

    if not code:
        return None

    code = code.upper()

    if not VALID_CODE_RE.fullmatch(code):
        return None

    return code


def parse_url_code(value: Any) -> str | None:
    url = normalize_url(value)

    if not url:
        return None

    path = urlsplit(url).path
    match = URL_CODE_RE.search(path)

    if not match:
        return None

    return match.group(1).upper()


def choose_source_listing_code(
    raw: dict[str, Any],
) -> tuple[str | None, list[str]]:
    raw_text = clean_text(
        raw.get("property_code")
    )
    raw_code = normalize_code(raw_text)
    url_code = parse_url_code(
        raw.get("url")
    )

    notes: list[str] = []

    if raw_text and not raw_code:
        add_reason(
            notes,
            f"ignored invalid raw property_code: {raw_text}",
        )

    if raw_code and url_code and raw_code != url_code:
        add_reason(
            notes,
            "property code mismatch preserved: "
            f"raw={raw_code}; url={url_code}",
        )

        # URL code is directly tied to this page, but code values are not
        # used for automatic deduplication because the audit found collisions.
        return url_code, notes

    if url_code:
        return url_code, notes

    if raw_code:
        return raw_code, notes

    return None, notes


def recover_price_from_title(
    title: Any,
) -> float | None:
    text = clean_text(title)

    if not text:
        return None

    candidates: list[float] = []

    for match in PRICE_WITH_CURRENCY_RE.finditer(text):
        raw_amount = (
            match.group("prefix_amount")
            or match.group("suffix_amount")
        )

        if not raw_amount:
            continue

        try:
            amount = float(
                raw_amount.replace(",", "")
            )
        except ValueError:
            continue

        if 10_000 <= amount <= 20_000_000:
            candidates.append(amount)

    if not candidates:
        return None

    # In the audited missing-price rows, the sale price is the largest
    # currency-marked amount in the title.
    return max(candidates)


def normalize_signature_text(
    value: Any,
) -> str:
    text = clean_text(value) or ""
    text = text.casefold()
    text = re.sub(
        r"[^\w\u1780-\u17ff]+",
        " ",
        text,
    )
    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def build_global_listing_id(
    source_listing_id: Any,
) -> str:
    value = clean_text(
        source_listing_id
    ) or "unknown"

    if value.lower().startswith(
        "camrealtyservice.com_"
    ):
        return value

    return f"{SOURCE_NAME}_{value}"


def duplicate_group_id(
    kind: str,
    value: str,
) -> str:
    digest = hashlib.sha1(
        value.encode("utf-8")
    ).hexdigest()[:12]

    return f"camrealty_{kind}_{digest}"


def title_is_explicit_multi_unit(
    title: Any,
) -> bool:
    text = clean_text(title)

    return bool(
        text
        and EXPLICIT_MULTI_UNIT_RE.search(text)
    )


def resolve_bedrooms(
    raw: dict[str, Any],
) -> tuple[int | None, str | None, list[str]]:
    current = safe_int(
        raw.get("bedrooms")
    )
    current_source = clean_text(
        raw.get("bedrooms_source")
    )

    title_value = safe_int(
        raw.get("bedrooms_title_value")
    )
    title_source = clean_text(
        raw.get("bedrooms_title_source")
    )

    conflict = clean_text(
        raw.get("bedrooms_conflict")
    )
    mismatch = clean_text(
        raw.get("bedrooms_reference_mismatch")
    )

    notes: list[str] = []

    # Explicit title values resolve both audited conflicts:
    # Time Square 11: 1 -> 2
    # Aeon-area penthouse: 3 -> 4
    if (
        conflict
        and title_value is not None
        and 0 <= title_value <= REVIEW_LIMITS["bedrooms_max"]
    ):
        if current != title_value:
            add_reason(
                notes,
                "bedrooms corrected from explicit title: "
                f"{current} -> {title_value}",
            )

        add_reason(
            notes,
            f"resolved bedrooms_conflict: {conflict}",
        )

        return (
            title_value,
            title_source
            or "camrealtyservice_com_title",
            notes,
        )

    # Explicit "Studio" is represented as zero bedrooms.
    if (
        mismatch
        and title_value == 0
    ):
        if current != 0:
            add_reason(
                notes,
                f"studio bedrooms corrected: {current} -> 0",
            )

        add_reason(
            notes,
            f"resolved bedrooms_reference_mismatch: {mismatch}",
        )

        return (
            0,
            title_source
            or "camrealtyservice_com_title",
            notes,
        )

    if mismatch:
        add_reason(
            notes,
            "kept current bedroom value; "
            f"reference mismatch: {mismatch}",
        )

    return current, current_source, notes


def normalize_record(
    raw: dict[str, Any],
) -> dict[str, Any]:
    source_listing_id = clean_text(
        raw.get("listing_id")
    )
    title = clean_text(
        raw.get("title")
    )

    source_listing_code, code_notes = (
        choose_source_listing_code(raw)
    )

    price_usd = safe_float(
        raw.get("price_usd")
    )
    price_source = clean_text(
        raw.get("price_usd_source")
    )

    notes: list[str] = []
    notes.extend(code_notes)

    if price_usd is None:
        recovered_price = recover_price_from_title(
            title
        )

        if recovered_price is not None:
            price_usd = recovered_price
            price_source = (
                "camrealtyservice_com_title"
            )
            add_reason(
                notes,
                f"price recovered from title: {recovered_price:g}",
            )

    size_m2 = safe_float(
        raw.get("size_m2")
    )

    bedrooms, bedrooms_source, bed_notes = (
        resolve_bedrooms(raw)
    )
    notes.extend(bed_notes)

    listing_type = normalize_listing_type(
        raw.get("listing_type")
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

    property_type_mismatch = clean_text(
        raw.get("property_type_reference_mismatch")
    )

    if property_type_mismatch:
        add_reason(
            notes,
            "kept current property type; "
            f"reference mismatch: {property_type_mismatch}",
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

    record: dict[str, Any] = {
        # Identity
        "listing_id": build_global_listing_id(
            source_listing_id
        ),
        "source": SOURCE_NAME,
        "source_listing_id": source_listing_id,
        "source_listing_code": source_listing_code,
        "url": clean_text(raw.get("url")),
        "canonical_url": normalize_url(
            raw.get("url")
        ),

        # Listing
        "title": title,
        "description": clean_text(
            raw.get("description")
        ),
        "listing_type": listing_type,
        "property_type": normalize_property_type_label(
            raw.get("property_type")
        ),
        "property_type_original": (
            normalize_property_type_label(
                raw.get("property_type")
            )
        ),
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
        "unit_floor": safe_int(
            raw.get("unit_floor")
        ),
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
            or clean_text(raw.get("commune"))
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

        # Cleaning status
        "record_status": None,
        "needs_manual_review": False,
        "review_reason": None,
        "reject_reason": None,
        "duplicate_group_id": None,
        "duplicate_reason": None,
        "cleaning_notes": join_reasons(notes),

        # Field sources
        "price_usd_source": price_source,
        "size_m2_source": clean_text(
            raw.get("size_m2_source")
        ),
        "bedrooms_source": bedrooms_source,
        "bathrooms_source": clean_text(
            raw.get("bathrooms_source")
        ),
        "unit_floor_source": clean_text(
            raw.get("unit_floor_source")
        ),
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
        "_display_as_project": bool(
            raw.get("display_as_project")
        ),
        "_explicit_multi_unit": (
            title_is_explicit_multi_unit(title)
        ),
    }

    return record


def exact_listing_signature(
    record: dict[str, Any],
) -> tuple[Any, ...] | None:
    title_signature = normalize_signature_text(
        record.get("title")
    )

    price = safe_float(
        record.get("price_usd")
    )
    size = safe_float(
        record.get("size_m2")
    )

    if not title_signature or price is None or size is None:
        return None

    return (
        title_signature,
        record.get("listing_type"),
        record.get("property_type"),
        price,
        size,
        safe_int(record.get("bedrooms")),
        safe_int(record.get("bathrooms")),
        safe_int(record.get("unit_floor")),
    )


def classify_record(
    record: dict[str, Any],
) -> dict[str, Any]:
    reject_reasons: list[str] = []
    review_reasons: list[str] = []

    listing_type = record.get(
        "listing_type"
    )
    property_type = record.get(
        "property_type"
    )

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

    if record.get("_display_as_project"):
        add_reason(
            reject_reasons,
            "project_level_listing",
        )

    if record.get("_explicit_multi_unit"):
        add_reason(
            reject_reasons,
            "multi_unit_listing",
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
        and ppm2
        < REVIEW_LIMITS["price_per_m2_min"]
    ):
        add_reason(
            review_reasons,
            "price_per_m2_below_review_limit",
        )
    elif (
        ppm2 is not None
        and ppm2
        > REVIEW_LIMITS["price_per_m2_max"]
    ):
        add_reason(
            review_reasons,
            "price_per_m2_above_review_limit",
        )

    if (
        bathrooms is not None
        and bathrooms
        > REVIEW_LIMITS["bathrooms_max"]
    ):
        add_reason(
            review_reasons,
            "bathrooms_above_review_limit",
        )

    if (
        unit_floor is not None
        and unit_floor
        > REVIEW_LIMITS["unit_floor_max"]
    ):
        add_reason(
            review_reasons,
            "unit_floor_above_review_limit",
        )

    if (
        total_floors is not None
        and total_floors
        > REVIEW_LIMITS[
            "building_total_floors_max"
        ]
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
    seen_exact_signatures: set[
        tuple[Any, ...]
    ] = set()

    for raw in raw_records:
        record = normalize_record(raw)

        source_listing_id = clean_text(
            record.get("source_listing_id")
        )
        canonical_url = clean_text(
            record.get("canonical_url")
        )
        signature = exact_listing_signature(
            record
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

        elif (
            canonical_url
            and canonical_url in seen_urls
        ):
            duplicate_reason = (
                "duplicate_canonical_url"
            )
            group_id = duplicate_group_id(
                "url",
                canonical_url,
            )

        elif (
            signature is not None
            and signature in seen_exact_signatures
        ):
            duplicate_reason = (
                "duplicate_exact_listing_signature"
            )
            group_id = duplicate_group_id(
                "exact_signature",
                repr(signature),
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
            seen_listing_ids.add(
                source_listing_id
            )

        if canonical_url:
            seen_urls.add(
                canonical_url
            )

        if signature is not None:
            seen_exact_signatures.add(
                signature
            )

        classified = classify_record(
            record
        )

        status = str(
            classified["record_status"]
        )

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

    recovered_prices = sum(
        "price recovered from title:"
        in str(row.get("cleaning_notes") or "")
        for row in all_rows
    )

    corrected_bedrooms = sum(
        (
            "bedrooms corrected from explicit title:"
            in str(row.get("cleaning_notes") or "")
        )
        or (
            "resolved bedrooms_reference_mismatch:"
            in str(row.get("cleaning_notes") or "")
        )
        for row in all_rows
    )

    code_mismatch_notes = sum(
        "property code mismatch preserved:"
        in str(row.get("cleaning_notes") or "")
        for row in all_rows
    )

    listing_type_mismatch_notes = sum(
        "current title-derived listing type"
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
        "prices_recovered_from_title": recovered_prices,
        "bedroom_conflicts_or_studios_resolved": (
            corrected_bedrooms
        ),
        "property_code_mismatches_preserved": (
            code_mismatch_notes
        ),
        "listing_type_url_mismatches_preserved": (
            listing_type_mismatch_notes
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
            "Duplicate source IDs, canonical URLs, and exact "
            "same-source listing signatures are removed. Property "
            "codes alone are not used because the audit found code "
            "collisions and raw-versus-URL mismatches."
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
    print(
        "\nCAMREALTY SERVICE CLEANING SUMMARY — V1"
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
        "Prices recovered from explicit title     : "
        f"{summary['prices_recovered_from_title']:,}"
    )
    print(
        "Bedroom conflicts/studios resolved       : "
        f"{summary['bedroom_conflicts_or_studios_resolved']:,}"
    )
    print(
        "Property-code mismatches preserved       : "
        f"{summary['property_code_mismatches_preserved']:,}"
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
    review_counts = summary[
        "review_reason_counts"
    ]

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
    reject_counts = summary[
        "reject_reason_counts"
    ]

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
    duplicate_counts = summary[
        "duplicate_reason_counts"
    ]

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

    print_summary(
        summary
    )


if __name__ == "__main__":
    main()
