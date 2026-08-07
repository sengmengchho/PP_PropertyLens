from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


# Supports both:
#   python -m src.cleaning.merge_silver_sources
#   python src/cleaning/merge_silver_sources.py
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
    clean_text,
    ensure_standard_columns,
    load_json_records,
    save_csv_records,
    save_json_records,
)


SOURCE_DIRS: dict[str, Path] = {
    "realestate.com.kh": (
        PROJECT_ROOT / "data" / "silver" / "by_source" / "realestate"
    ),
    "khmer24.com": (
        PROJECT_ROOT / "data" / "silver" / "by_source" / "khmer24"
    ),
    "khpropertyhub.com": (
        PROJECT_ROOT / "data" / "silver" / "by_source" / "khpropertyhub"
    ),
    "harbor-property.com": (
        PROJECT_ROOT / "data" / "silver" / "by_source" / "harbor"
    ),
    "camrealtyservice.com": (
        PROJECT_ROOT / "data" / "silver" / "by_source" / "camrealty"
    ),
    "aps.com.kh": (
        PROJECT_ROOT / "data" / "silver" / "by_source" / "aps"
    ),
}

OUTPUT_DIR = PROJECT_ROOT / "data" / "silver" / "combined"

# JSON filenames use "duplicates", while individual rows use
# record_status="duplicate".
STATUSES = [
    "accepted",
    "review",
    "rejected",
    "duplicates",
]


def expected_record_status_for_file(
    file_status: str,
) -> str:
    """Map a JSON file category to its expected row status."""
    if file_status == "duplicates":
        return "duplicate"

    return file_status


def load_source_status(
    source_name: str,
    source_dir: Path,
    status: str,
) -> list[dict[str, Any]]:
    """Load and validate one source/status JSON file."""
    path = source_dir / f"{status}.json"

    if not path.exists():
        raise FileNotFoundError(
            f"Missing {status} output for {source_name}: {path}"
        )

    records = load_json_records(path)
    cleaned: list[dict[str, Any]] = []

    # Define this before the loop so it is always available.
    expected_record_status = expected_record_status_for_file(
        status
    )

    for row_number, record in enumerate(
        records,
        start=1,
    ):
        row = ensure_standard_columns(record)

        if not clean_text(row.get("source")):
            row["source"] = source_name

        if not clean_text(row.get("record_status")):
            row["record_status"] = expected_record_status

        if row.get("record_status") != expected_record_status:
            raise ValueError(
                f"Unexpected status in {path} at row {row_number}: "
                f"{row.get('record_status')!r}; "
                f"expected {expected_record_status!r}"
            )

        cleaned.append(row)

    return cleaned


def read_source_summary(
    source_name: str,
    source_dir: Path,
) -> dict[str, Any]:
    """Load cleaning_summary.json for one source."""
    path = source_dir / "cleaning_summary.json"

    if not path.exists():
        raise FileNotFoundError(
            f"Missing cleaning summary for {source_name}: {path}"
        )

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    if not isinstance(data, dict):
        raise TypeError(
            f"Expected a JSON object in {path}"
        )

    return data


def source_summary_total(
    summary: dict[str, Any],
) -> int | None:
    """Read a total count from different cleaner-summary formats."""
    candidate_keys = [
        "total_raw_records",
        "input_records",
        "total_records",
        "input_total",
    ]

    for key in candidate_keys:
        value = summary.get(key)

        if value is None:
            continue

        try:
            return int(value)
        except (TypeError, ValueError):
            continue

    return None


def duplicate_values(
    records: list[dict[str, Any]],
    field: str,
) -> dict[str, int]:
    """Return duplicated non-empty values in a field."""
    counts = Counter(
        clean_text(row.get(field))
        for row in records
        if clean_text(row.get(field))
    )

    return {
        value: count
        for value, count in counts.items()
        if count > 1
    }


def validate_columns(
    records: list[dict[str, Any]],
) -> None:
    """Ensure every combined row has exactly STANDARD_COLUMNS."""
    expected = set(STANDARD_COLUMNS)

    for index, row in enumerate(
        records,
        start=1,
    ):
        actual = set(row.keys())

        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)

            raise ValueError(
                f"Schema mismatch at combined row {index}. "
                f"Missing={missing}; extra={extra}"
            )


def build_combined() -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[str, Any],
]:
    """
    Combine all source-level Silver outputs.

    This step does not remove duplicates across different websites.
    """
    combined: dict[str, list[dict[str, Any]]] = {
        status: []
        for status in STATUSES
    }

    source_summaries: dict[str, dict[str, Any]] = {}
    source_counts: dict[str, dict[str, int]] = {}

    for source_name, source_dir in SOURCE_DIRS.items():
        print(f"Loading source: {source_name}")

        source_summary = read_source_summary(
            source_name,
            source_dir,
        )
        source_summaries[source_name] = source_summary

        counts: dict[str, int] = {}

        for status in STATUSES:
            records = load_source_status(
                source_name=source_name,
                source_dir=source_dir,
                status=status,
            )

            counts[status] = len(records)
            combined[status].extend(records)

        counts["total"] = sum(
            counts[status]
            for status in STATUSES
        )

        expected_total = source_summary_total(
            source_summary
        )

        if (
            expected_total is not None
            and expected_total != counts["total"]
        ):
            raise RuntimeError(
                f"{source_name} count mismatch: "
                f"summary={expected_total}; "
                f"merged={counts['total']}"
            )

        source_counts[source_name] = counts

    all_records = [
        row
        for status in STATUSES
        for row in combined[status]
    ]

    validate_columns(all_records)

    status_counts = {
        status: len(combined[status])
        for status in STATUSES
    }

    output_total = sum(
        status_counts.values()
    )

    expected_total = sum(
        counts["total"]
        for counts in source_counts.values()
    )

    if output_total != expected_total:
        raise RuntimeError(
            "Combined output count does not match source totals."
        )

    duplicate_listing_ids = duplicate_values(
        all_records,
        "listing_id",
    )

    source_id_rows: list[dict[str, Any]] = []

    for row in all_records:
        source = clean_text(
            row.get("source")
        )
        source_listing_id = clean_text(
            row.get("source_listing_id")
        )

        if not source_listing_id:
            continue

        source_id_rows.append(
            {
                "_source_pair": (
                    f"{source}|{source_listing_id}"
                )
            }
        )

    duplicate_source_id_pairs = duplicate_values(
        source_id_rows,
        "_source_pair",
    )

    summary: dict[str, Any] = {
        "sources": list(SOURCE_DIRS.keys()),
        "source_counts": source_counts,
        "status_counts": status_counts,
        "accepted_pre_cross_source_deduplication": (
            status_counts["accepted"]
        ),
        "review_pending_manual_decision": (
            status_counts["review"]
        ),
        "rejected_records": (
            status_counts["rejected"]
        ),
        "source_level_duplicate_records": (
            status_counts["duplicates"]
        ),
        "accepted_plus_review": (
            status_counts["accepted"]
            + status_counts["review"]
        ),
        "combined_output_total": output_total,
        "expected_source_total": expected_total,
        "counts_match": (
            output_total == expected_total
        ),
        "duplicate_global_listing_id_groups": (
            duplicate_listing_ids
        ),
        "duplicate_source_and_source_listing_id_groups": (
            duplicate_source_id_pairs
        ),
        "schema_column_count": len(
            STANDARD_COLUMNS
        ),
        "schema_columns": STANDARD_COLUMNS,
        "note": (
            "This step only combines source-cleaned outputs. "
            "It does not remove possible duplicates between "
            "different websites."
        ),
        "source_cleaning_summaries": source_summaries,
    }

    return combined, summary


def save_outputs(
    combined: dict[str, list[dict[str, Any]]],
    summary: dict[str, Any],
) -> None:
    """Save combined JSON, CSV and summary outputs."""
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for status in STATUSES:
        records = combined[status]

        save_json_records(
            records,
            OUTPUT_DIR / f"{status}.json",
        )

        save_csv_records(
            records,
            OUTPUT_DIR / f"{status}.csv",
            columns=STANDARD_COLUMNS,
        )

    save_json_records(
        combined["accepted"],
        OUTPUT_DIR
        / "accepted_pre_cross_source_dedupe.json",
    )

    save_csv_records(
        combined["accepted"],
        OUTPUT_DIR
        / "accepted_pre_cross_source_dedupe.csv",
        columns=STANDARD_COLUMNS,
    )

    (
        OUTPUT_DIR
        / "combined_summary.json"
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
    """Print the final combined validation summary."""
    print(
        "\nCOMBINED SILVER SUMMARY — "
        "PRE CROSS-SOURCE DEDUPE"
    )
    print("=" * 94)

    print("\nSOURCE COUNTS")
    print("-" * 94)
    print(
        f"{'Source':<28}"
        f"{'Accepted':>11}"
        f"{'Review':>10}"
        f"{'Rejected':>11}"
        f"{'Duplicates':>13}"
        f"{'Total':>10}"
    )

    for source, counts in (
        summary["source_counts"].items()
    ):
        print(
            f"{source:<28}"
            f"{counts['accepted']:>11,}"
            f"{counts['review']:>10,}"
            f"{counts['rejected']:>11,}"
            f"{counts['duplicates']:>13,}"
            f"{counts['total']:>10,}"
        )

    status_counts = summary["status_counts"]

    print("\nCOMBINED COUNTS")
    print("-" * 94)
    print(
        "Accepted                    : "
        f"{status_counts['accepted']:,}"
    )
    print(
        "Review                      : "
        f"{status_counts['review']:,}"
    )
    print(
        "Rejected                    : "
        f"{status_counts['rejected']:,}"
    )
    print(
        "Source-level duplicates     : "
        f"{status_counts['duplicates']:,}"
    )
    print(
        "Accepted + review           : "
        f"{summary['accepted_plus_review']:,}"
    )
    print(
        "Combined total              : "
        f"{summary['combined_output_total']:,}"
    )
    print(
        "Expected source total       : "
        f"{summary['expected_source_total']:,}"
    )
    print(
        "Counts match                : "
        f"{summary['counts_match']}"
    )

    print("\nIDENTITY VALIDATION")
    print("-" * 94)
    print(
        "Duplicate global listing-ID groups  : "
        f"{len(summary['duplicate_global_listing_id_groups']):,}"
    )
    print(
        "Duplicate source + source-ID groups : "
        f"{len(summary['duplicate_source_and_source_listing_id_groups']):,}"
    )
    print(
        "Standard schema columns             : "
        f"{summary['schema_column_count']:,}"
    )

    print(f"\nSaved to: {OUTPUT_DIR}")
    print("=" * 94)


def main() -> None:
    combined, summary = build_combined()

    save_outputs(
        combined,
        summary,
    )

    print_summary(summary)


if __name__ == "__main__":
    main()
