from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


# Supports:
#   python -m src.cleaning.apply_manual_review_decisions
#   python src/cleaning/apply_manual_review_decisions.py
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
    safe_float,
    safe_int,
    save_csv_records,
    save_json_records,
)


COMBINED_DIR = (
    PROJECT_ROOT
    / "data"
    / "silver"
    / "combined"
)

INPUT_ACCEPTED = (
    COMBINED_DIR
    / "accepted.json"
)

INPUT_REVIEW = (
    COMBINED_DIR
    / "review.json"
)

DECISION_CSV = (
    PROJECT_ROOT
    / "data"
    / "silver"
    / "manual_review"
    / "manual_review_queue.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "silver"
    / "review_resolved"
)

ALLOWED_DECISIONS = {
    "approve",
    "reject",
    "keep_review",
}

CORRECTION_FIELDS = [
    "corrected_price_usd",
    "corrected_size_m2",
    "corrected_bedrooms",
    "corrected_bathrooms",
    "corrected_unit_floor",
    "corrected_building_total_floors",
    "corrected_district",
    "corrected_property_type",
    "corrected_listing_type",
]


def read_decision_rows() -> list[dict[str, str]]:
    if not DECISION_CSV.exists():
        raise FileNotFoundError(
            f"Manual-review CSV was not found: "
            f"{DECISION_CSV}"
        )

    with DECISION_CSV.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        required = {
            "listing_id",
            "manual_decision",
            "manual_note",
            *CORRECTION_FIELDS,
        }

        actual = set(
            reader.fieldnames or []
        )
        missing = sorted(
            required - actual
        )

        if missing:
            raise ValueError(
                "Decision CSV is missing columns: "
                f"{missing}"
            )

        rows = [
            {
                key: value or ""
                for key, value in row.items()
            }
            for row in reader
        ]

    return rows


def append_cleaning_note(
    record: dict[str, Any],
    note: str,
) -> None:
    notes: list[str] = []

    existing = clean_text(
        record.get("cleaning_notes")
    )

    if existing:
        notes.extend(
            existing.split("; ")
        )

    add_reason(
        notes,
        note,
    )

    record["cleaning_notes"] = join_reasons(
        notes
    )


def parse_optional_float(
    row: dict[str, str],
    field: str,
) -> float | None:
    text = clean_text(
        row.get(field)
    )

    if text is None:
        return None

    value = safe_float(text)

    if value is None:
        raise ValueError(
            f"Invalid numeric correction for "
            f"{field}: {text!r}"
        )

    return value


def parse_optional_int(
    row: dict[str, str],
    field: str,
) -> int | None:
    text = clean_text(
        row.get(field)
    )

    if text is None:
        return None

    value = safe_int(text)

    if value is None:
        raise ValueError(
            f"Invalid integer correction for "
            f"{field}: {text!r}"
        )

    return value


def apply_corrections(
    record: dict[str, Any],
    decision_row: dict[str, str],
) -> None:
    price = parse_optional_float(
        decision_row,
        "corrected_price_usd",
    )

    size = parse_optional_float(
        decision_row,
        "corrected_size_m2",
    )

    bedrooms = parse_optional_int(
        decision_row,
        "corrected_bedrooms",
    )

    bathrooms = parse_optional_int(
        decision_row,
        "corrected_bathrooms",
    )

    unit_floor = parse_optional_int(
        decision_row,
        "corrected_unit_floor",
    )

    total_floors = parse_optional_int(
        decision_row,
        "corrected_building_total_floors",
    )

    district_text = clean_text(
        decision_row.get(
            "corrected_district"
        )
    )

    property_type_text = clean_text(
        decision_row.get(
            "corrected_property_type"
        )
    )

    listing_type_text = clean_text(
        decision_row.get(
            "corrected_listing_type"
        )
    )

    correction_notes: list[str] = []

    if price is not None:
        correction_notes.append(
            f"price_usd {record.get('price_usd')} -> {price}"
        )
        record["price_usd"] = price
        record["price_usd_source"] = (
            "manual_review"
        )

    if size is not None:
        correction_notes.append(
            f"size_m2 {record.get('size_m2')} -> {size}"
        )
        record["size_m2"] = size
        record["size_m2_source"] = (
            "manual_review"
        )

    if bedrooms is not None:
        correction_notes.append(
            f"bedrooms {record.get('bedrooms')} -> {bedrooms}"
        )
        record["bedrooms"] = bedrooms
        record["bedrooms_source"] = (
            "manual_review"
        )

    if bathrooms is not None:
        correction_notes.append(
            f"bathrooms {record.get('bathrooms')} -> {bathrooms}"
        )
        record["bathrooms"] = bathrooms
        record["bathrooms_source"] = (
            "manual_review"
        )

    if unit_floor is not None:
        correction_notes.append(
            f"unit_floor {record.get('unit_floor')} -> {unit_floor}"
        )
        record["unit_floor"] = unit_floor
        record["unit_floor_source"] = (
            "manual_review"
        )

    if total_floors is not None:
        correction_notes.append(
            "building_total_floors "
            f"{record.get('building_total_floors')} "
            f"-> {total_floors}"
        )
        record[
            "building_total_floors"
        ] = total_floors
        record[
            "building_total_floors_source"
        ] = "manual_review"

    if district_text is not None:
        district = normalize_district(
            district_text
        )
        correction_notes.append(
            f"district {record.get('district')} -> {district}"
        )
        record["district"] = district
        record["district_source"] = (
            "manual_review"
        )

    if property_type_text is not None:
        property_type = (
            normalize_property_type_label(
                property_type_text
            )
        )
        correction_notes.append(
            "property_type "
            f"{record.get('property_type')} "
            f"-> {property_type}"
        )
        record["property_type"] = property_type
        record["property_type_source"] = (
            "manual_review"
        )

    if listing_type_text is not None:
        listing_type = normalize_listing_type(
            listing_type_text
        )
        correction_notes.append(
            "listing_type "
            f"{record.get('listing_type')} "
            f"-> {listing_type}"
        )
        record["listing_type"] = listing_type
        record["listing_type_source"] = (
            "manual_review"
        )

    record["price_per_m2"] = (
        calculate_price_per_m2(
            safe_float(record.get("price_usd")),
            safe_float(record.get("size_m2")),
        )
    )

    if correction_notes:
        append_cleaning_note(
            record,
            "manual corrections: "
            + ", ".join(correction_notes),
        )


def validate_approved_record(
    record: dict[str, Any],
) -> None:
    price = safe_float(
        record.get("price_usd")
    )
    size = safe_float(
        record.get("size_m2")
    )

    listing_type = clean_text(
        record.get("listing_type")
    )
    property_type = clean_text(
        record.get("property_type")
    )

    problems: list[str] = []

    if price is None or price <= 0:
        problems.append(
            "missing_or_invalid_price"
        )

    if size is None or size <= 0:
        problems.append(
            "missing_or_invalid_size"
        )

    if listing_type not in {
        "sale",
        "sale/rent",
    }:
        problems.append(
            "not_sale_listing"
        )

    if property_type not in {
        "Condo",
        "Penthouse",
    }:
        problems.append(
            "not_condo_or_penthouse"
        )

    if problems:
        raise ValueError(
            "Cannot approve "
            f"{record.get('listing_id')}: "
            + ", ".join(problems)
        )


def apply_decision(
    original: dict[str, Any],
    decision_row: dict[str, str],
) -> tuple[str, dict[str, Any]]:
    record = ensure_standard_columns(
        dict(original)
    )

    original_review_reason = clean_text(
        record.get("review_reason")
    )

    decision = clean_text(
        decision_row.get(
            "manual_decision"
        )
    )

    if decision is None:
        raise ValueError(
            "manual_decision is blank for "
            f"{record.get('listing_id')}"
        )

    decision = decision.lower()

    if decision not in ALLOWED_DECISIONS:
        raise ValueError(
            f"Invalid manual_decision={decision!r} "
            f"for {record.get('listing_id')}. "
            f"Allowed: {sorted(ALLOWED_DECISIONS)}"
        )

    apply_corrections(
        record,
        decision_row,
    )

    note = clean_text(
        decision_row.get("manual_note")
    )

    if original_review_reason:
        append_cleaning_note(
            record,
            "original review reason: "
            f"{original_review_reason}",
        )

    if decision == "approve":
        validate_approved_record(
            record
        )

        record["record_status"] = "accepted"
        record["needs_manual_review"] = False
        record["review_reason"] = None
        record["reject_reason"] = None

        append_cleaning_note(
            record,
            (
                "manual review approved"
                + (
                    f": {note}"
                    if note
                    else ""
                )
            ),
        )

        return "approved", record

    if decision == "reject":
        record["record_status"] = "rejected"
        record["needs_manual_review"] = False
        record["review_reason"] = None
        record["reject_reason"] = (
            note
            or "rejected_after_manual_review"
        )

        append_cleaning_note(
            record,
            (
                "manual review rejected"
                + (
                    f": {note}"
                    if note
                    else ""
                )
            ),
        )

        return "rejected", record

    record["record_status"] = "review"
    record["needs_manual_review"] = True
    record["review_reason"] = (
        original_review_reason
        or "manual_review_unresolved"
    )
    record["reject_reason"] = None

    append_cleaning_note(
        record,
        (
            "manual review kept unresolved"
            + (
                f": {note}"
                if note
                else ""
            )
        ),
    )

    return "unresolved", record


def save_decision_audit(
    decision_rows: list[dict[str, str]],
) -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        OUTPUT_DIR
        / "manual_review_decisions_audit.csv"
    )

    fieldnames = list(
        decision_rows[0].keys()
    ) if decision_rows else []

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        if fieldnames:
            writer.writeheader()
            writer.writerows(
                decision_rows
            )


def main() -> None:
    for path in [
        INPUT_ACCEPTED,
        INPUT_REVIEW,
        DECISION_CSV,
    ]:
        if not path.exists():
            raise FileNotFoundError(
                f"Required file was not found: "
                f"{path}"
            )

    original_accepted = load_json_records(
        INPUT_ACCEPTED
    )
    review_records = load_json_records(
        INPUT_REVIEW
    )
    decision_rows = read_decision_rows()

    review_by_id = {
        clean_text(
            row.get("listing_id")
        ): row
        for row in review_records
    }

    decision_by_id: dict[
        str,
        dict[str, str],
    ] = {}

    for row in decision_rows:
        listing_id = clean_text(
            row.get("listing_id")
        )

        if not listing_id:
            raise ValueError(
                "A decision row has a blank listing_id."
            )

        if listing_id in decision_by_id:
            raise ValueError(
                "Duplicate listing_id in decision CSV: "
                f"{listing_id}"
            )

        decision_by_id[
            listing_id
        ] = row

    missing_decisions = sorted(
        listing_id
        for listing_id in review_by_id
        if listing_id not in decision_by_id
    )

    extra_decisions = sorted(
        listing_id
        for listing_id in decision_by_id
        if listing_id not in review_by_id
    )

    if missing_decisions:
        raise ValueError(
            f"{len(missing_decisions)} review records "
            "are missing from the decision CSV. "
            f"Examples: {missing_decisions[:5]}"
        )

    if extra_decisions:
        raise ValueError(
            f"{len(extra_decisions)} decision rows do "
            "not exist in combined/review.json. "
            f"Examples: {extra_decisions[:5]}"
        )

    outputs: dict[
        str,
        list[dict[str, Any]],
    ] = {
        "approved": [],
        "rejected": [],
        "unresolved": [],
    }

    for listing_id, original in (
        review_by_id.items()
    ):
        category, record = apply_decision(
            original,
            decision_by_id[listing_id],
        )

        outputs[category].append(
            ensure_standard_columns(record)
        )

    reviewed_total = sum(
        len(rows)
        for rows in outputs.values()
    )

    if reviewed_total != len(
        review_records
    ):
        raise RuntimeError(
            "Manual review output count does not "
            "match combined review input."
        )

    accepted_after_manual_review = [
        ensure_standard_columns(row)
        for row in original_accepted
    ] + outputs["approved"]

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

    save_json_records(
        accepted_after_manual_review,
        OUTPUT_DIR
        / "accepted_after_manual_review.json",
    )

    save_csv_records(
        accepted_after_manual_review,
        OUTPUT_DIR
        / "accepted_after_manual_review.csv",
        columns=STANDARD_COLUMNS,
    )

    save_decision_audit(
        decision_rows
    )

    decision_counts = {
        name: len(records)
        for name, records in outputs.items()
    }

    source_decisions: dict[
        str,
        Counter[str],
    ] = {}

    for category, records in outputs.items():
        for row in records:
            source = (
                clean_text(
                    row.get("source")
                )
                or "unknown"
            )

            source_decisions.setdefault(
                source,
                Counter(),
            )[category] += 1

    summary = {
        "combined_accepted_before_review": len(
            original_accepted
        ),
        "combined_review_input": len(
            review_records
        ),
        "manual_decision_counts": decision_counts,
        "accepted_after_manual_review": len(
            accepted_after_manual_review
        ),
        "remaining_unresolved_review": len(
            outputs["unresolved"]
        ),
        "rejected_after_manual_review": len(
            outputs["rejected"]
        ),
        "counts_match": (
            reviewed_total
            == len(review_records)
        ),
        "source_decision_counts": {
            source: dict(counts)
            for source, counts
            in source_decisions.items()
        },
        "next_step": (
            "Run cross-source duplicate auditing "
            "on accepted_after_manual_review.json."
        ),
    }

    (
        OUTPUT_DIR
        / "manual_review_summary.json"
    ).write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nMANUAL REVIEW DECISIONS APPLIED")
    print("=" * 82)
    print(
        "Combined accepted before review : "
        f"{len(original_accepted):,}"
    )
    print(
        "Review records processed        : "
        f"{len(review_records):,}"
    )
    print(
        "Approved                        : "
        f"{len(outputs['approved']):,}"
    )
    print(
        "Rejected                        : "
        f"{len(outputs['rejected']):,}"
    )
    print(
        "Keep review                     : "
        f"{len(outputs['unresolved']):,}"
    )
    print(
        "Accepted after manual review    : "
        f"{len(accepted_after_manual_review):,}"
    )
    print(
        "Counts match                    : "
        f"{summary['counts_match']}"
    )
    print(f"\nSaved to: {OUTPUT_DIR}")
    print("=" * 82)


if __name__ == "__main__":
    main()
