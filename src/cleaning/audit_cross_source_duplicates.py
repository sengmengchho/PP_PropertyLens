from __future__ import annotations

import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


# Supports:
#   python -m src.cleaning.audit_cross_source_duplicates
#   python src/cleaning/audit_cross_source_duplicates.py
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
    safe_float,
    safe_int,
)


INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "silver"
    / "review_resolved"
    / "accepted_after_manual_review.json"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "silver"
    / "cross_source_dedupe"
)

OUTPUT_CSV = (
    OUTPUT_DIR
    / "cross_source_duplicate_candidates.csv"
)

OUTPUT_JSON = (
    OUTPUT_DIR
    / "cross_source_duplicate_candidates.json"
)

OUTPUT_SUMMARY = (
    OUTPUT_DIR
    / "cross_source_duplicate_summary.json"
)


# Conservative tolerances.
PRICE_REL_TOL_STRONG = 0.03
PRICE_REL_TOL_MEDIUM = 0.08

SIZE_REL_TOL_STRONG = 0.03
SIZE_REL_TOL_MEDIUM = 0.08

SIZE_ABS_TOL_STRONG = 2.0
SIZE_ABS_TOL_MEDIUM = 5.0

FLOOR_ABS_TOL = 1

HIGH_TITLE_SIM = 0.84
MEDIUM_TITLE_SIM = 0.68


STOPWORDS = {
    "for",
    "sale",
    "condo",
    "condominium",
    "apartment",
    "penthouse",
    "bedroom",
    "bedrooms",
    "br",
    "studio",
    "unit",
    "phnom",
    "penh",
    "cambodia",
    "property",
    "properties",
    "residence",
    "residences",
    "project",
    "type",
    "sqm",
    "sq",
    "m",
    "m2",
    "floor",
    "floors",
    "fully",
    "furnished",
    "semi",
    "unfurnished",
    "new",
    "urgent",
    "hot",
    "best",
    "price",
    "available",
}


def normalize_text(value: Any) -> str:
    text = clean_text(value)

    if not text:
        return ""

    text = text.lower()
    text = text.replace("é", "e")
    text = text.replace("è", "e")
    text = text.replace("ê", "e")
    text = text.replace("–", " ")
    text = text.replace("—", " ")
    text = text.replace("-", " ")
    text = text.replace("_", " ")

    text = re.sub(
        r"\baps\s+cambodia\s+\d+\b",
        " ",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"\b(?:usd|us\$|\$)\s*[\d,.]+\b",
        " ",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"\b\d+(?:\.\d+)?\s*(?:sqm|sq\.?\s*m|m2|m²)\b",
        " ",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"\b\d+(?:st|nd|rd|th)?\s+floor\b",
        " ",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"\b\d+\s*(?:bed|beds|bedroom|bedrooms|br)\b",
        " ",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    tokens = [
        token
        for token in text.split()
        if token not in STOPWORDS
        and len(token) > 1
    ]

    return " ".join(tokens)


def title_tokens(value: Any) -> set[str]:
    return set(
        normalize_text(value).split()
    )


def jaccard_similarity(
    a: set[str],
    b: set[str],
) -> float:
    if not a or not b:
        return 0.0

    union = a | b

    if not union:
        return 0.0

    return len(a & b) / len(union)


def title_similarity(
    a: Any,
    b: Any,
) -> float:
    a_norm = normalize_text(a)
    b_norm = normalize_text(b)

    if not a_norm or not b_norm:
        return 0.0

    seq = SequenceMatcher(
        None,
        a_norm,
        b_norm,
    ).ratio()

    jac = jaccard_similarity(
        set(a_norm.split()),
        set(b_norm.split()),
    )

    return round(
        max(seq, jac),
        4,
    )


def relative_difference(
    a: float | None,
    b: float | None,
) -> float | None:
    if (
        a is None
        or b is None
        or a <= 0
        or b <= 0
    ):
        return None

    denominator = max(
        abs(a),
        abs(b),
    )

    if denominator == 0:
        return None

    return abs(a - b) / denominator


def numeric_close(
    a: float | None,
    b: float | None,
    rel_tol: float,
    abs_tol: float = 0.0,
) -> bool:
    if a is None or b is None:
        return False

    return math.isclose(
        a,
        b,
        rel_tol=rel_tol,
        abs_tol=abs_tol,
    )


def canonical_district(
    value: Any,
) -> str:
    text = clean_text(value)

    if not text:
        return ""

    text = text.lower()
    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )
    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


def source_key(
    row: dict[str, Any],
) -> str:
    return (
        clean_text(row.get("source"))
        or ""
    ).lower()


def build_block_keys(
    row: dict[str, Any],
) -> set[tuple[Any, ...]]:
    """
    Build several blocking keys so we avoid comparing all 2,676 x 2,676 rows.

    We intentionally use multiple blocks for recall:
      1. property type + district + bedrooms
      2. property type + bedrooms + rounded size band
      3. property type + district + rounded price band
      4. title token anchors
    """
    property_type = (
        clean_text(row.get("property_type"))
        or ""
    ).lower()

    district = canonical_district(
        row.get("district")
    )

    bedrooms = safe_int(
        row.get("bedrooms")
    )

    size = safe_float(
        row.get("size_m2")
    )

    price = safe_float(
        row.get("price_usd")
    )

    keys: set[tuple[Any, ...]] = set()

    if district and bedrooms is not None:
        keys.add(
            (
                "district_bed",
                property_type,
                district,
                bedrooms,
            )
        )

    if size is not None and bedrooms is not None:
        size_band = round(
            size / 5
        )
        keys.add(
            (
                "size_bed",
                property_type,
                bedrooms,
                size_band,
            )
        )

        # Neighbor band prevents boundary misses.
        keys.add(
            (
                "size_bed",
                property_type,
                bedrooms,
                size_band - 1,
            )
        )
        keys.add(
            (
                "size_bed",
                property_type,
                bedrooms,
                size_band + 1,
            )
        )

    if price is not None and district:
        price_band = round(
            price / 10_000
        )
        keys.add(
            (
                "district_price",
                property_type,
                district,
                price_band,
            )
        )

        keys.add(
            (
                "district_price",
                property_type,
                district,
                price_band - 1,
            )
        )
        keys.add(
            (
                "district_price",
                property_type,
                district,
                price_band + 1,
            )
        )

    tokens = sorted(
        title_tokens(
            row.get("title")
        )
    )

    # Use up to 3 longest title tokens as anchor blocks.
    longest_tokens = sorted(
        tokens,
        key=lambda token: (
            -len(token),
            token,
        ),
    )[:3]

    for token in longest_tokens:
        if len(token) >= 4:
            keys.add(
                (
                    "title_token",
                    property_type,
                    token,
                )
            )

    return keys


def compare_pair(
    a: dict[str, Any],
    b: dict[str, Any],
) -> dict[str, Any] | None:
    if source_key(a) == source_key(b):
        return None

    property_a = (
        clean_text(a.get("property_type"))
        or ""
    )
    property_b = (
        clean_text(b.get("property_type"))
        or ""
    )

    if (
        property_a
        and property_b
        and property_a != property_b
    ):
        # Condo/Penthouse mismatch can happen across websites,
        # so do not hard reject it, but penalize later.
        property_match = False
    else:
        property_match = True

    price_a = safe_float(
        a.get("price_usd")
    )
    price_b = safe_float(
        b.get("price_usd")
    )

    size_a = safe_float(
        a.get("size_m2")
    )
    size_b = safe_float(
        b.get("size_m2")
    )

    bed_a = safe_int(
        a.get("bedrooms")
    )
    bed_b = safe_int(
        b.get("bedrooms")
    )

    bath_a = safe_int(
        a.get("bathrooms")
    )
    bath_b = safe_int(
        b.get("bathrooms")
    )

    floor_a = safe_int(
        a.get("unit_floor")
    )
    floor_b = safe_int(
        b.get("unit_floor")
    )

    district_a = canonical_district(
        a.get("district")
    )
    district_b = canonical_district(
        b.get("district")
    )

    district_match = (
        bool(district_a)
        and bool(district_b)
        and district_a == district_b
    )

    bedrooms_match = (
        bed_a is not None
        and bed_b is not None
        and bed_a == bed_b
    )

    bathrooms_match = (
        bath_a is not None
        and bath_b is not None
        and bath_a == bath_b
    )

    floor_match = (
        floor_a is not None
        and floor_b is not None
        and abs(floor_a - floor_b)
        <= FLOOR_ABS_TOL
    )

    price_rel_diff = relative_difference(
        price_a,
        price_b,
    )

    size_rel_diff = relative_difference(
        size_a,
        size_b,
    )

    price_close_strong = numeric_close(
        price_a,
        price_b,
        PRICE_REL_TOL_STRONG,
        abs_tol=1_000,
    )

    price_close_medium = numeric_close(
        price_a,
        price_b,
        PRICE_REL_TOL_MEDIUM,
        abs_tol=3_000,
    )

    size_close_strong = numeric_close(
        size_a,
        size_b,
        SIZE_REL_TOL_STRONG,
        abs_tol=SIZE_ABS_TOL_STRONG,
    )

    size_close_medium = numeric_close(
        size_a,
        size_b,
        SIZE_REL_TOL_MEDIUM,
        abs_tol=SIZE_ABS_TOL_MEDIUM,
    )

    t_sim = title_similarity(
        a.get("title"),
        b.get("title"),
    )

    reasons: list[str] = []
    score = 0

    if property_match:
        score += 5
        reasons.append(
            "same_property_type"
        )

    if district_match:
        score += 15
        reasons.append(
            "same_district"
        )

    if bedrooms_match:
        score += 15
        reasons.append(
            "same_bedrooms"
        )

    if bathrooms_match:
        score += 5
        reasons.append(
            "same_bathrooms"
        )

    if floor_match:
        score += 10
        reasons.append(
            "same_or_adjacent_floor"
        )

    if price_close_strong:
        score += 20
        reasons.append(
            "price_within_3pct"
        )
    elif price_close_medium:
        score += 10
        reasons.append(
            "price_within_8pct"
        )

    if size_close_strong:
        score += 20
        reasons.append(
            "size_within_3pct_or_2sqm"
        )
    elif size_close_medium:
        score += 10
        reasons.append(
            "size_within_8pct_or_5sqm"
        )

    if t_sim >= HIGH_TITLE_SIM:
        score += 25
        reasons.append(
            "high_title_similarity"
        )
    elif t_sim >= MEDIUM_TITLE_SIM:
        score += 15
        reasons.append(
            "medium_title_similarity"
        )
    elif t_sim >= 0.50:
        score += 7
        reasons.append(
            "some_title_similarity"
        )

    # Require at least a meaningful combination.
    strong_core = (
        bedrooms_match
        and size_close_strong
        and price_close_strong
    )

    location_core = (
        district_match
        and bedrooms_match
        and size_close_medium
        and price_close_medium
    )

    title_core = (
        t_sim >= HIGH_TITLE_SIM
        and size_close_medium
        and price_close_medium
    )

    if not (
        strong_core
        or location_core
        or title_core
        or score >= 60
    ):
        return None

    if score >= 85:
        confidence = "high"
    elif score >= 70:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "score": score,
        "confidence": confidence,
        "reasons": "; ".join(reasons),
        "title_similarity": t_sim,
        "price_relative_difference": (
            round(price_rel_diff, 4)
            if price_rel_diff is not None
            else None
        ),
        "size_relative_difference": (
            round(size_rel_diff, 4)
            if size_rel_diff is not None
            else None
        ),
        "district_match": district_match,
        "bedrooms_match": bedrooms_match,
        "bathrooms_match": bathrooms_match,
        "floor_match": floor_match,
    }


def candidate_row(
    pair_number: int,
    a: dict[str, Any],
    b: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "pair_id": f"pair_{pair_number:05d}",
        "manual_decision": "",
        "manual_note": "",
        "score": metrics["score"],
        "confidence": metrics["confidence"],
        "reasons": metrics["reasons"],
        "title_similarity": metrics[
            "title_similarity"
        ],
        "price_relative_difference": metrics[
            "price_relative_difference"
        ],
        "size_relative_difference": metrics[
            "size_relative_difference"
        ],
        "district_match": metrics[
            "district_match"
        ],
        "bedrooms_match": metrics[
            "bedrooms_match"
        ],
        "bathrooms_match": metrics[
            "bathrooms_match"
        ],
        "floor_match": metrics[
            "floor_match"
        ],

        "listing_id_a": a.get("listing_id"),
        "source_a": a.get("source"),
        "source_listing_id_a": a.get(
            "source_listing_id"
        ),
        "title_a": a.get("title"),
        "price_usd_a": a.get("price_usd"),
        "size_m2_a": a.get("size_m2"),
        "bedrooms_a": a.get("bedrooms"),
        "bathrooms_a": a.get("bathrooms"),
        "unit_floor_a": a.get("unit_floor"),
        "district_a": a.get("district"),
        "property_type_a": a.get(
            "property_type"
        ),
        "project_name_a": a.get(
            "project_name"
        ),
        "url_a": a.get("url"),

        "listing_id_b": b.get("listing_id"),
        "source_b": b.get("source"),
        "source_listing_id_b": b.get(
            "source_listing_id"
        ),
        "title_b": b.get("title"),
        "price_usd_b": b.get("price_usd"),
        "size_m2_b": b.get("size_m2"),
        "bedrooms_b": b.get("bedrooms"),
        "bathrooms_b": b.get("bathrooms"),
        "unit_floor_b": b.get("unit_floor"),
        "district_b": b.get("district"),
        "property_type_b": b.get(
            "property_type"
        ),
        "project_name_b": b.get(
            "project_name"
        ),
        "url_b": b.get("url"),
    }


def find_candidate_pairs(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    block_map: dict[
        tuple[Any, ...],
        list[int],
    ] = defaultdict(list)

    for index, row in enumerate(records):
        for key in build_block_keys(row):
            block_map[key].append(index)

    pair_indexes: set[
        tuple[int, int]
    ] = set()

    for indexes in block_map.values():
        if len(indexes) < 2:
            continue

        # Skip huge generic blocks to avoid noisy explosions.
        if len(indexes) > 300:
            continue

        unique_indexes = sorted(
            set(indexes)
        )

        for pos, left in enumerate(
            unique_indexes
        ):
            source_left = source_key(
                records[left]
            )

            for right in unique_indexes[
                pos + 1:
            ]:
                if (
                    source_left
                    == source_key(records[right])
                ):
                    continue

                pair_indexes.add(
                    (left, right)
                )

    candidates: list[dict[str, Any]] = []

    for left, right in sorted(
        pair_indexes
    ):
        a = records[left]
        b = records[right]

        metrics = compare_pair(
            a,
            b,
        )

        if metrics is None:
            continue

        candidates.append(
            candidate_row(
                pair_number=0,
                a=a,
                b=b,
                metrics=metrics,
            )
        )

    # Sort strongest candidates first.
    candidates.sort(
        key=lambda row: (
            -int(row["score"]),
            -float(
                row["title_similarity"]
                or 0
            ),
            str(row["source_a"]),
            str(row["source_b"]),
            str(row["listing_id_a"]),
            str(row["listing_id_b"]),
        )
    )

    for index, row in enumerate(
        candidates,
        start=1,
    ):
        row["pair_id"] = (
            f"pair_{index:05d}"
        )

    return candidates


def save_csv(
    rows: list[dict[str, Any]],
) -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not rows:
        # Still create an empty CSV with useful headers.
        fieldnames = [
            "pair_id",
            "manual_decision",
            "manual_note",
            "score",
            "confidence",
            "reasons",
            "title_similarity",
            "price_relative_difference",
            "size_relative_difference",
            "district_match",
            "bedrooms_match",
            "bathrooms_match",
            "floor_match",
            "listing_id_a",
            "source_a",
            "source_listing_id_a",
            "title_a",
            "price_usd_a",
            "size_m2_a",
            "bedrooms_a",
            "bathrooms_a",
            "unit_floor_a",
            "district_a",
            "property_type_a",
            "project_name_a",
            "url_a",
            "listing_id_b",
            "source_b",
            "source_listing_id_b",
            "title_b",
            "price_usd_b",
            "size_m2_b",
            "bedrooms_b",
            "bathrooms_b",
            "unit_floor_b",
            "district_b",
            "property_type_b",
            "project_name_b",
            "url_b",
        ]
    else:
        fieldnames = list(
            rows[0].keys()
        )

    with OUTPUT_CSV.open(
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

        if rows:
            writer.writerows(rows)


def build_summary(
    records: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    confidence_counts = Counter(
        row["confidence"]
        for row in candidates
    )

    source_pair_counts: Counter[str] = Counter()

    for row in candidates:
        pair = " <-> ".join(
            sorted(
                [
                    str(row["source_a"]),
                    str(row["source_b"]),
                ]
            )
        )
        source_pair_counts[pair] += 1

    unique_candidate_listing_ids = set()

    for row in candidates:
        unique_candidate_listing_ids.add(
            row["listing_id_a"]
        )
        unique_candidate_listing_ids.add(
            row["listing_id_b"]
        )

    return {
        "input_path": str(INPUT_PATH),
        "accepted_input_records": len(
            records
        ),
        "candidate_pairs": len(
            candidates
        ),
        "unique_listings_in_candidates": len(
            unique_candidate_listing_ids
        ),
        "confidence_counts": dict(
            confidence_counts
        ),
        "source_pair_counts": dict(
            source_pair_counts.most_common()
        ),
        "output_csv": str(
            OUTPUT_CSV
        ),
        "output_json": str(
            OUTPUT_JSON
        ),
        "manual_decisions_to_use": [
            "duplicate",
            "not_duplicate",
            "uncertain",
        ],
        "note": (
            "This is an audit queue only. No records are removed "
            "automatically. Review candidate pairs manually before "
            "building the Gold modeling dataset."
        ),
    }


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            "Accepted-after-manual-review file was not found:\n"
            f"{INPUT_PATH}"
        )

    records = load_json_records(
        INPUT_PATH
    )

    for row in records:
        if (
            clean_text(row.get("record_status"))
            != "accepted"
        ):
            raise ValueError(
                "Cross-source duplicate audit expects only accepted "
                f"records, but found {row.get('listing_id')} with "
                f"status={row.get('record_status')!r}."
            )

    print(
        f"Loaded accepted records: {len(records):,}"
    )
    print(
        "Building cross-source duplicate candidates..."
    )

    candidates = find_candidate_pairs(
        records
    )

    save_csv(candidates)

    OUTPUT_JSON.write_text(
        json.dumps(
            candidates,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = build_summary(
        records,
        candidates,
    )

    OUTPUT_SUMMARY.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nCROSS-SOURCE DUPLICATE AUDIT")
    print("=" * 88)
    print(
        "Accepted input records       : "
        f"{summary['accepted_input_records']:,}"
    )
    print(
        "Candidate pairs              : "
        f"{summary['candidate_pairs']:,}"
    )
    print(
        "Unique candidate listings    : "
        f"{summary['unique_listings_in_candidates']:,}"
    )

    print("\nCONFIDENCE COUNTS")
    print("-" * 88)

    for confidence in [
        "high",
        "medium",
        "low",
    ]:
        print(
            f"{confidence:<12}: "
            f"{summary['confidence_counts'].get(confidence, 0):,}"
        )

    print("\nTOP SOURCE PAIRS")
    print("-" * 88)

    for pair, count in list(
        summary["source_pair_counts"].items()
    )[:15]:
        print(
            f"{pair:<65}: {count:,}"
        )

    print(
        f"\nSaved CSV : {OUTPUT_CSV}"
    )
    print(
        f"Saved JSON: {OUTPUT_JSON}"
    )
    print("=" * 88)


if __name__ == "__main__":
    main()
