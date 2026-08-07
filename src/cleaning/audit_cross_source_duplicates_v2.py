from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any


# Supports:
#   python -m src.cleaning.audit_cross_source_duplicates_v2
#   python src/cleaning/audit_cross_source_duplicates_v2.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="replace",
    )


INPUT_CSV = (
    PROJECT_ROOT
    / "data"
    / "silver"
    / "cross_source_dedupe"
    / "cross_source_duplicate_candidates.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "silver"
    / "cross_source_dedupe"
    / "v2_strict"
)

STRICT_CSV = OUTPUT_DIR / "strict_duplicate_candidates.csv"
UNCERTAIN_CSV = OUTPUT_DIR / "uncertain_duplicate_candidates.csv"
REJECTED_CSV = OUTPUT_DIR / "filtered_out_pairs.csv"
SUMMARY_JSON = OUTPUT_DIR / "strict_duplicate_summary.json"


# Conservative duplicate rules.
PRICE_REL_TOL = 0.03
PRICE_ABS_TOL = 1000.0

SIZE_REL_TOL = 0.03
SIZE_ABS_TOL = 2.0

STRICT_TITLE_SIM = 0.68
UNCERTAIN_TITLE_SIM = 0.75


def clean_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).strip()

    if text.lower() in {"", "none", "null", "nan"}:
        return ""

    return text


def safe_float(value: Any) -> float | None:
    text = clean_text(value)

    if not text:
        return None

    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def safe_int(value: Any) -> int | None:
    number = safe_float(value)

    if number is None:
        return None

    if not float(number).is_integer():
        return None

    return int(number)


def truthy(value: Any) -> bool:
    return clean_text(value).lower() in {
        "true",
        "1",
        "yes",
    }


def numeric_close(
    a: float | None,
    b: float | None,
    rel_tol: float,
    abs_tol: float,
) -> bool:
    if a is None or b is None:
        return False

    return math.isclose(
        a,
        b,
        rel_tol=rel_tol,
        abs_tol=abs_tol,
    )


def district_conflict(
    row: dict[str, str],
) -> bool:
    a = clean_text(row.get("district_a")).lower()
    b = clean_text(row.get("district_b")).lower()

    # Missing district is not a conflict.
    if not a or not b:
        return False

    return a != b


def property_type_conflict(
    row: dict[str, str],
) -> bool:
    a = clean_text(
        row.get("property_type_a")
    ).lower()

    b = clean_text(
        row.get("property_type_b")
    ).lower()

    if not a or not b:
        return False

    # Condo vs Penthouse can be source-label disagreement for the
    # same unit, so do not treat that pair as an automatic conflict.
    allowed = {"condo", "penthouse"}

    if a in allowed and b in allowed:
        return False

    return a != b


def classify_pair(
    row: dict[str, str],
) -> tuple[str, list[str]]:
    reasons: list[str] = []

    title_sim = safe_float(
        row.get("title_similarity")
    ) or 0.0

    price_a = safe_float(
        row.get("price_usd_a")
    )
    price_b = safe_float(
        row.get("price_usd_b")
    )

    size_a = safe_float(
        row.get("size_m2_a")
    )
    size_b = safe_float(
        row.get("size_m2_b")
    )

    bed_a = safe_int(
        row.get("bedrooms_a")
    )
    bed_b = safe_int(
        row.get("bedrooms_b")
    )

    floor_a = safe_int(
        row.get("unit_floor_a")
    )
    floor_b = safe_int(
        row.get("unit_floor_b")
    )

    bedrooms_match = (
        bed_a is not None
        and bed_b is not None
        and bed_a == bed_b
    )

    price_close = numeric_close(
        price_a,
        price_b,
        rel_tol=PRICE_REL_TOL,
        abs_tol=PRICE_ABS_TOL,
    )

    size_close = numeric_close(
        size_a,
        size_b,
        rel_tol=SIZE_REL_TOL,
        abs_tol=SIZE_ABS_TOL,
    )

    both_floors_known = (
        floor_a is not None
        and floor_b is not None
    )

    same_floor = (
        both_floors_known
        and floor_a == floor_b
    )

    different_floor = (
        both_floors_known
        and floor_a != floor_b
    )

    if property_type_conflict(row):
        reasons.append(
            "property_type_conflict"
        )
        return "filtered_out", reasons

    if district_conflict(row):
        reasons.append(
            "district_conflict"
        )
        return "filtered_out", reasons

    if different_floor:
        reasons.append(
            f"different_known_floors:{floor_a}!={floor_b}"
        )
        return "filtered_out", reasons

    if not bedrooms_match:
        reasons.append(
            "bedrooms_do_not_match_or_missing"
        )
        return "filtered_out", reasons

    if not price_close:
        reasons.append(
            "price_not_close_enough"
        )
        return "filtered_out", reasons

    if not size_close:
        reasons.append(
            "size_not_close_enough"
        )
        return "filtered_out", reasons

    if same_floor:
        if title_sim < STRICT_TITLE_SIM:
            reasons.append(
                "title_similarity_too_low"
            )
            return "filtered_out", reasons

        reasons.extend(
            [
                "same_bedrooms",
                "same_exact_floor",
                "price_within_3pct_or_1000usd",
                "size_within_3pct_or_2sqm",
                f"title_similarity={title_sim:.3f}",
            ]
        )

        return "strict", reasons

    # One or both floors missing. Even if every other feature matches,
    # do not auto-mark as a strict candidate.
    if title_sim >= UNCERTAIN_TITLE_SIM:
        reasons.extend(
            [
                "same_bedrooms",
                "floor_missing_on_one_or_both",
                "price_within_3pct_or_1000usd",
                "size_within_3pct_or_2sqm",
                f"title_similarity={title_sim:.3f}",
            ]
        )

        return "uncertain", reasons

    reasons.append(
        "floor_missing_and_title_similarity_not_high_enough"
    )

    return "filtered_out", reasons


def add_review_columns(
    row: dict[str, str],
    category: str,
    reasons: list[str],
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "manual_decision": "",
        "manual_note": "",
        "keep_listing_id": "",
        "strict_category": category,
        "strict_reasons": "; ".join(reasons),
    }

    output.update(row)

    return output


def save_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(
            "Cross-source candidate CSV was not found:\n"
            f"{INPUT_CSV}"
        )

    with INPUT_CSV.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)
        input_fieldnames = list(
            reader.fieldnames or []
        )
        rows = list(reader)

    strict_rows: list[dict[str, Any]] = []
    uncertain_rows: list[dict[str, Any]] = []
    filtered_rows: list[dict[str, Any]] = []

    for row in rows:
        category, reasons = classify_pair(
            row
        )

        output = add_review_columns(
            row,
            category,
            reasons,
        )

        if category == "strict":
            strict_rows.append(output)
        elif category == "uncertain":
            uncertain_rows.append(output)
        else:
            filtered_rows.append(output)

    review_prefix = [
        "manual_decision",
        "manual_note",
        "keep_listing_id",
        "strict_category",
        "strict_reasons",
    ]

    output_fieldnames = review_prefix + [
        field
        for field in input_fieldnames
        if field not in review_prefix
    ]

    save_csv(
        STRICT_CSV,
        strict_rows,
        output_fieldnames,
    )

    save_csv(
        UNCERTAIN_CSV,
        uncertain_rows,
        output_fieldnames,
    )

    save_csv(
        REJECTED_CSV,
        filtered_rows,
        output_fieldnames,
    )

    source_pair_counts: Counter[str] = Counter()

    for row in strict_rows:
        source_a = clean_text(
            row.get("source_a")
        )
        source_b = clean_text(
            row.get("source_b")
        )

        pair_name = " <-> ".join(
            sorted(
                [source_a, source_b]
            )
        )
        source_pair_counts[
            pair_name
        ] += 1

    summary = {
        "input_candidate_pairs": len(rows),
        "strict_duplicate_candidates": len(
            strict_rows
        ),
        "uncertain_candidates": len(
            uncertain_rows
        ),
        "filtered_out_pairs": len(
            filtered_rows
        ),
        "counts_match": (
            len(rows)
            == len(strict_rows)
            + len(uncertain_rows)
            + len(filtered_rows)
        ),
        "strict_rules": {
            "same_bedrooms": True,
            "same_exact_floor": True,
            "price_tolerance": (
                "within 3% or $1,000"
            ),
            "size_tolerance": (
                "within 3% or 2 sqm"
            ),
            "minimum_title_similarity": (
                STRICT_TITLE_SIM
            ),
            "different_known_floor": (
                "filtered out"
            ),
            "missing_floor": (
                "never strict; may become uncertain"
            ),
        },
        "strict_source_pair_counts": dict(
            source_pair_counts.most_common()
        ),
        "manual_decisions_for_strict_csv": [
            "duplicate",
            "not_duplicate",
            "uncertain",
        ],
        "keep_listing_id": (
            "When manual_decision=duplicate, enter the listing_id "
            "of the record you want to keep. Leave blank for "
            "not_duplicate/uncertain."
        ),
        "files": {
            "strict": str(STRICT_CSV),
            "uncertain": str(UNCERTAIN_CSV),
            "filtered_out": str(
                REJECTED_CSV
            ),
        },
    }

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SUMMARY_JSON.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nSTRICT CROSS-SOURCE DUPLICATE AUDIT — V2")
    print("=" * 88)
    print(
        "Input candidate pairs      : "
        f"{len(rows):,}"
    )
    print(
        "Strict candidates          : "
        f"{len(strict_rows):,}"
    )
    print(
        "Uncertain (missing floor)  : "
        f"{len(uncertain_rows):,}"
    )
    print(
        "Filtered out               : "
        f"{len(filtered_rows):,}"
    )
    print(
        "Counts match               : "
        f"{summary['counts_match']}"
    )

    print("\nSTRICT RULES")
    print("-" * 88)
    print(
        "Same bedrooms + same exact floor + "
        "close price + close size + similar title"
    )
    print(
        "Different known floors => not treated as duplicate"
    )
    print(
        "Missing floor => uncertain, never strict"
    )

    print("\nSaved:")
    print(f"  {STRICT_CSV}")
    print(f"  {UNCERTAIN_CSV}")
    print(f"  {REJECTED_CSV}")
    print("=" * 88)


if __name__ == "__main__":
    main()
