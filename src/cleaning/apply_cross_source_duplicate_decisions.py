from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any


# Supports:
#   python -m src.cleaning.apply_cross_source_duplicate_decisions
#   python src/cleaning/apply_cross_source_duplicate_decisions.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="replace",
    )


from src.cleaning.common import (
    STANDARD_COLUMNS,
    clean_text,
    ensure_standard_columns,
    load_json_records,
    save_csv_records,
    save_json_records,
)


INPUT_ACCEPTED = (
    PROJECT_ROOT
    / "data"
    / "silver"
    / "review_resolved"
    / "accepted_after_manual_review.json"
)

V2_DIR = (
    PROJECT_ROOT
    / "data"
    / "silver"
    / "cross_source_dedupe"
    / "v2_strict"
)

STRICT_REVIEWED_CSV = (
    V2_DIR
    / "strict_duplicate_candidates.csv"
)

UNCERTAIN_REVIEWED_CSV = (
    V2_DIR
    / "uncertain_duplicate_candidates.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "silver"
    / "deduplicated"
)

FINAL_ACCEPTED_JSON = (
    OUTPUT_DIR
    / "accepted_after_cross_source_dedupe.json"
)

FINAL_ACCEPTED_CSV = (
    OUTPUT_DIR
    / "accepted_after_cross_source_dedupe.csv"
)

REMOVED_JSON = (
    OUTPUT_DIR
    / "cross_source_duplicates_removed.json"
)

REMOVED_CSV = (
    OUTPUT_DIR
    / "cross_source_duplicates_removed.csv"
)

DECISION_AUDIT_CSV = (
    OUTPUT_DIR
    / "cross_source_duplicate_decisions_audit.csv"
)

SUMMARY_JSON = (
    OUTPUT_DIR
    / "cross_source_dedupe_summary.json"
)


ALLOWED_DECISIONS = {
    "duplicate",
    "not_duplicate",
    "uncertain",
}


def read_csv(
    path: Path,
) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Required decision CSV was not found: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)
        rows = [
            {
                key: value or ""
                for key, value in row.items()
            }
            for row in reader
        ]
        fields = list(reader.fieldnames or [])

    return rows, fields


def validate_decision_rows(
    rows: list[dict[str, str]],
    filename: str,
) -> None:
    required = {
        "pair_id",
        "manual_decision",
        "manual_note",
        "keep_listing_id",
        "listing_id_a",
        "listing_id_b",
    }

    if not rows:
        return

    actual = set(rows[0].keys())
    missing = sorted(required - actual)

    if missing:
        raise ValueError(
            f"{filename} is missing required columns: {missing}"
        )

    seen_pair_ids: set[str] = set()

    for row in rows:
        pair_id = clean_text(row.get("pair_id"))

        if not pair_id:
            raise ValueError(
                f"{filename} contains a blank pair_id."
            )

        if pair_id in seen_pair_ids:
            raise ValueError(
                f"{filename} contains duplicate pair_id={pair_id}"
            )

        seen_pair_ids.add(pair_id)

        decision = (
            clean_text(row.get("manual_decision"))
            or ""
        ).lower()

        if decision not in ALLOWED_DECISIONS:
            raise ValueError(
                f"{filename} pair {pair_id} has invalid "
                f"manual_decision={decision!r}. "
                f"Allowed: {sorted(ALLOWED_DECISIONS)}"
            )

        note = clean_text(
            row.get("manual_note")
        )

        if not note:
            raise ValueError(
                f"{filename} pair {pair_id} has a blank manual_note."
            )

        listing_a = clean_text(
            row.get("listing_id_a")
        )
        listing_b = clean_text(
            row.get("listing_id_b")
        )

        if not listing_a or not listing_b:
            raise ValueError(
                f"{filename} pair {pair_id} is missing listing IDs."
            )

        keep_id = clean_text(
            row.get("keep_listing_id")
        )

        if decision == "duplicate":
            if not keep_id:
                raise ValueError(
                    f"{filename} pair {pair_id} is duplicate "
                    "but keep_listing_id is blank."
                )

            if keep_id not in {
                listing_a,
                listing_b,
            }:
                raise ValueError(
                    f"{filename} pair {pair_id} has "
                    f"keep_listing_id={keep_id!r}, but it is not "
                    "listing_id_a or listing_id_b."
                )

        else:
            if keep_id:
                raise ValueError(
                    f"{filename} pair {pair_id} is {decision!r} "
                    "but keep_listing_id is not blank."
                )


def build_duplicate_actions(
    strict_rows: list[dict[str, str]],
    uncertain_rows: list[dict[str, str]],
) -> tuple[
    set[str],
    dict[str, dict[str, str]],
    list[dict[str, str]],
]:
    remove_ids: set[str] = set()
    removal_metadata: dict[
        str,
        dict[str, str],
    ] = {}
    audit_rows: list[dict[str, str]] = []

    for queue_name, rows in [
        ("strict", strict_rows),
        ("uncertain", uncertain_rows),
    ]:
        for row in rows:
            decision = (
                clean_text(
                    row.get("manual_decision")
                )
                or ""
            ).lower()

            audit = dict(row)
            audit["decision_queue"] = queue_name
            audit_rows.append(audit)

            if decision != "duplicate":
                continue

            listing_a = clean_text(
                row.get("listing_id_a")
            )
            listing_b = clean_text(
                row.get("listing_id_b")
            )
            keep_id = clean_text(
                row.get("keep_listing_id")
            )

            remove_id = (
                listing_b
                if keep_id == listing_a
                else listing_a
            )

            if remove_id == keep_id:
                raise RuntimeError(
                    f"Pair {row.get('pair_id')} generated "
                    "the same keep/remove listing ID."
                )

            if remove_id in removal_metadata:
                previous = removal_metadata[
                    remove_id
                ]

                # Repeated duplicate edges are okay only when
                # they agree on which record is kept.
                if (
                    previous["keep_listing_id"]
                    != keep_id
                ):
                    raise ValueError(
                        "Conflicting duplicate decisions for "
                        f"{remove_id}: keep "
                        f"{previous['keep_listing_id']} vs {keep_id}"
                    )

            remove_ids.add(remove_id)
            removal_metadata[
                remove_id
            ] = {
                "pair_id": (
                    clean_text(
                        row.get("pair_id")
                    )
                    or ""
                ),
                "keep_listing_id": (
                    keep_id or ""
                ),
                "manual_note": (
                    clean_text(
                        row.get("manual_note")
                    )
                    or ""
                ),
            }

    return (
        remove_ids,
        removal_metadata,
        audit_rows,
    )


def write_audit_csv(
    rows: list[dict[str, str]],
) -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not rows:
        return

    fieldnames: list[str] = []

    for row in rows:
        for field in row.keys():
            if field not in fieldnames:
                fieldnames.append(field)

    with DECISION_AUDIT_CSV.open(
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
    if not INPUT_ACCEPTED.exists():
        raise FileNotFoundError(
            "Accepted-after-manual-review dataset was not found:\n"
            f"{INPUT_ACCEPTED}"
        )

    accepted_records = load_json_records(
        INPUT_ACCEPTED
    )

    strict_rows, _ = read_csv(
        STRICT_REVIEWED_CSV
    )
    uncertain_rows, _ = read_csv(
        UNCERTAIN_REVIEWED_CSV
    )

    validate_decision_rows(
        strict_rows,
        STRICT_REVIEWED_CSV.name,
    )
    validate_decision_rows(
        uncertain_rows,
        UNCERTAIN_REVIEWED_CSV.name,
    )

    (
        remove_ids,
        removal_metadata,
        audit_rows,
    ) = build_duplicate_actions(
        strict_rows,
        uncertain_rows,
    )

    accepted_by_id: dict[
        str,
        dict[str, Any],
    ] = {}

    for record in accepted_records:
        listing_id = clean_text(
            record.get("listing_id")
        )

        if not listing_id:
            raise ValueError(
                "Accepted dataset contains a blank listing_id."
            )

        if listing_id in accepted_by_id:
            raise ValueError(
                f"Duplicate listing_id in accepted input: "
                f"{listing_id}"
            )

        accepted_by_id[listing_id] = record

    missing_remove_ids = sorted(
        listing_id
        for listing_id in remove_ids
        if listing_id not in accepted_by_id
    )

    if missing_remove_ids:
        raise ValueError(
            "Some confirmed duplicate records are not present "
            "in accepted_after_manual_review.json. Examples: "
            f"{missing_remove_ids[:5]}"
        )

    final_records: list[
        dict[str, Any]
    ] = []

    removed_records: list[
        dict[str, Any]
    ] = []

    for record in accepted_records:
        listing_id = clean_text(
            record.get("listing_id")
        )

        if listing_id in remove_ids:
            row = ensure_standard_columns(
                dict(record)
            )

            meta = removal_metadata[
                listing_id
            ]

            row["record_status"] = "duplicate"
            row["needs_manual_review"] = False
            row["duplicate_reason"] = (
                "confirmed_cross_source_duplicate"
            )
            row["duplicate_group_id"] = (
                meta["pair_id"]
            )

            existing_notes = clean_text(
                row.get("cleaning_notes")
            )

            note = (
                "cross-source duplicate removed; "
                f"kept={meta['keep_listing_id']}; "
                f"reason={meta['manual_note']}"
            )

            row["cleaning_notes"] = (
                f"{existing_notes}; {note}"
                if existing_notes
                else note
            )

            removed_records.append(row)
            continue

        final_records.append(
            ensure_standard_columns(
                dict(record)
            )
        )

    expected_final = (
        len(accepted_records)
        - len(remove_ids)
    )

    if len(final_records) != expected_final:
        raise RuntimeError(
            "Final accepted count does not match expected count."
        )

    if (
        len(final_records)
        + len(removed_records)
        != len(accepted_records)
    ):
        raise RuntimeError(
            "Input records were lost during cross-source dedupe."
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    save_json_records(
        final_records,
        FINAL_ACCEPTED_JSON,
    )

    save_csv_records(
        final_records,
        FINAL_ACCEPTED_CSV,
        columns=STANDARD_COLUMNS,
    )

    save_json_records(
        removed_records,
        REMOVED_JSON,
    )

    save_csv_records(
        removed_records,
        REMOVED_CSV,
        columns=STANDARD_COLUMNS,
    )

    write_audit_csv(
        audit_rows
    )

    strict_counts: dict[str, int] = {
        "duplicate": 0,
        "not_duplicate": 0,
        "uncertain": 0,
    }

    for row in strict_rows:
        strict_counts[
            (
                clean_text(
                    row.get("manual_decision")
                )
                or ""
            ).lower()
        ] += 1

    uncertain_counts: dict[str, int] = {
        "duplicate": 0,
        "not_duplicate": 0,
        "uncertain": 0,
    }

    for row in uncertain_rows:
        uncertain_counts[
            (
                clean_text(
                    row.get("manual_decision")
                )
                or ""
            ).lower()
        ] += 1

    summary = {
        "accepted_before_cross_source_dedupe": len(
            accepted_records
        ),
        "strict_candidate_pairs_reviewed": len(
            strict_rows
        ),
        "uncertain_candidate_pairs_reviewed": len(
            uncertain_rows
        ),
        "strict_decision_counts": strict_counts,
        "uncertain_decision_counts": uncertain_counts,
        "confirmed_duplicate_records_removed": len(
            removed_records
        ),
        "accepted_after_cross_source_dedupe": len(
            final_records
        ),
        "counts_match": (
            len(final_records)
            + len(removed_records)
            == len(accepted_records)
        ),
        "removed_listing_ids": sorted(
            remove_ids
        ),
        "next_step": (
            "Create the Gold modeling dataset from "
            "accepted_after_cross_source_dedupe.json."
        ),
    }

    SUMMARY_JSON.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "\nCROSS-SOURCE DUPLICATE DECISIONS APPLIED"
    )
    print("=" * 82)
    print(
        "Accepted before dedupe       : "
        f"{len(accepted_records):,}"
    )
    print(
        "Strict pairs reviewed        : "
        f"{len(strict_rows):,}"
    )
    print(
        "Uncertain pairs reviewed     : "
        f"{len(uncertain_rows):,}"
    )
    print(
        "Confirmed duplicate records  : "
        f"{len(removed_records):,}"
    )
    print(
        "Accepted after dedupe        : "
        f"{len(final_records):,}"
    )
    print(
        "Counts match                 : "
        f"{summary['counts_match']}"
    )

    print("\nREMOVED LISTINGS")
    print("-" * 82)

    for listing_id in sorted(
        remove_ids
    ):
        meta = removal_metadata[
            listing_id
        ]

        print(
            f"Remove: {listing_id}"
        )
        print(
            f"  Keep: {meta['keep_listing_id']}"
        )
        print(
            f"  Pair: {meta['pair_id']}"
        )

    print(
        f"\nSaved to: {OUTPUT_DIR}"
    )
    print("=" * 82)


if __name__ == "__main__":
    main()
