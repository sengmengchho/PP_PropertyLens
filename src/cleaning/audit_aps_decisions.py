from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="replace",
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


PRICE_MIN = 20_000
PRICE_MAX = 2_000_000
SIZE_MIN = 20
SIZE_MAX = 500
PPM2_MIN = 300
PPM2_MAX = 10_000
BEDROOM_MAX = 10
BATHROOM_MAX = 10
UNIT_FLOOR_MAX = 100

TITLE_PRICE_RE = re.compile(
    r"""
    (?:
        \$\s*
        (?P<prefix>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,9}(?:\.\d+)?)
    )
    |
    (?:
        (?P<suffix>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,9}(?:\.\d+)?)
        \s*(?:USD|\$)
    )
    """,
    re.I | re.X,
)

TITLE_SIZE_RE = re.compile(
    r"""
    (?P<size>\d{1,4}(?:\.\d+)?)
    \s*
    (?:
        SQM
        |
        M2
        |
        M²
        |
        SQ\.?\s*M
    )
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


def is_missing(value: Any) -> bool:
    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0

    return False


def clean_text(value: Any) -> str | None:
    if is_missing(value):
        return None

    text = str(value)
    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\ufeff", "")
    text = re.sub(r"\s+", " ", text).strip()

    return text or None


def as_float(value: Any) -> float | None:
    if isinstance(value, bool) or is_missing(value):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).replace(",", "").replace("$", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)

    if not match:
        return None

    try:
        return float(match.group())
    except ValueError:
        return None


def load_records(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        raise TypeError(
            "Expected raw_listings.json to contain a JSON list."
        )

    return [
        row
        for row in data
        if isinstance(row, dict)
    ]


def price_per_m2(
    row: dict[str, Any],
) -> float | None:
    price = as_float(row.get("price_usd"))
    size = as_float(row.get("size_m2"))

    if (
        price is None
        or size is None
        or price <= 0
        or size <= 0
    ):
        return None

    return round(price / size, 2)


def title_prices(value: Any) -> list[float]:
    text = clean_text(value)

    if not text:
        return []

    values: list[float] = []

    for match in TITLE_PRICE_RE.finditer(text):
        raw = match.group("prefix") or match.group("suffix")

        if not raw:
            continue

        try:
            amount = float(raw.replace(",", ""))
        except ValueError:
            continue

        if 1_000 <= amount <= 20_000_000:
            values.append(amount)

    return values


def title_sizes(value: Any) -> list[float]:
    text = clean_text(value)

    if not text:
        return []

    values: list[float] = []

    for match in TITLE_SIZE_RE.finditer(text):
        try:
            size = float(match.group("size"))
        except ValueError:
            continue

        if 1 <= size <= 20_000:
            values.append(size)

    return values


def print_record(row: dict[str, Any]) -> None:
    print("\n" + "-" * 110)
    print("ID                    :", row.get("listing_id"))
    print("APS listing code      :", row.get("aps_listing_code"))
    print("Property code         :", row.get("property_code"))
    print("Title                 :", row.get("title"))
    print("Listing type          :", row.get("listing_type"))
    print("Property type         :", row.get("property_type"))
    print("Price                 :", row.get("price_usd"))
    print("Title price candidates:", title_prices(row.get("title")))
    print("Size                  :", row.get("size_m2"))
    print("Title size candidates :", title_sizes(row.get("title")))
    print("Price/m²              :", price_per_m2(row))
    print("Bedrooms              :", row.get("bedrooms"))
    print("Title bedrooms        :", row.get("bedrooms_title_value"))
    print("URL bedrooms          :", row.get("bedrooms_url_value"))
    print("Bathrooms             :", row.get("bathrooms"))
    print("Unit floor            :", row.get("unit_floor"))
    print("Previous unit floor   :", row.get("unit_floor_previous_value"))
    print("Building total floors :", row.get("building_total_floors"))
    print("District              :", row.get("district"))
    print("Manual review         :", row.get("needs_manual_review"))
    print("Out of scope          :", row.get("out_of_scope_reason"))

    for key, value in row.items():
        if (
            key.endswith("_conflict")
            or key.endswith("_reference_mismatch")
            or key.endswith("_url_mismatch")
        ) and value:
            print(f"{key:<38}: {value}")

    print("URL                   :", row.get("url"))


def print_group(
    title: str,
    rows: list[dict[str, Any]],
    limit: int = 15,
) -> None:
    print("\n" + "=" * 110)
    print(f"{title}: {len(rows)} records")
    print("=" * 110)

    for row in rows[:limit]:
        print_record(row)


def print_duplicate_groups(
    title: str,
    groups: dict[str, list[dict[str, Any]]],
    limit: int = 20,
) -> None:
    print("\n" + "=" * 110)
    print(f"{title}: {len(groups)} groups")
    print("=" * 110)

    if not groups:
        print("No groups found.")
        return

    sorted_groups = sorted(
        groups.items(),
        key=lambda item: len(item[1]),
        reverse=True,
    )

    for key, rows in sorted_groups[:limit]:
        print("\n" + "-" * 110)
        print("Group value:", key)
        print("Records    :", len(rows))

        for row in rows:
            print(
                "  -",
                row.get("listing_id"),
                "| APS=",
                row.get("aps_listing_code"),
                "| property_code=",
                row.get("property_code"),
                "| price=",
                row.get("price_usd"),
                "| size=",
                row.get("size_m2"),
                "| floor=",
                row.get("unit_floor"),
                "| title=",
                row.get("title"),
            )


def duplicate_groups(
    records: list[dict[str, Any]],
    field: str,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in records:
        value = clean_text(row.get(field))

        if value:
            grouped[value].append(row)

    return {
        key: rows
        for key, rows in grouped.items()
        if len(rows) > 1
    }


def main() -> None:
    input_path = find_input_path()
    records = load_records(input_path)

    rent_only = [
        row for row in records
        if row.get("listing_type") == "rent"
    ]

    missing_price = [
        row for row in records
        if is_missing(row.get("price_usd"))
    ]

    missing_size = [
        row for row in records
        if is_missing(row.get("size_m2"))
    ]

    low_price = [
        row for row in records
        if (
            as_float(row.get("price_usd")) is not None
            and as_float(row.get("price_usd")) < PRICE_MIN
        )
    ]

    high_price = [
        row for row in records
        if (
            as_float(row.get("price_usd")) is not None
            and as_float(row.get("price_usd")) > PRICE_MAX
        )
    ]

    small_size = [
        row for row in records
        if (
            as_float(row.get("size_m2")) is not None
            and as_float(row.get("size_m2")) < SIZE_MIN
        )
    ]

    large_size = [
        row for row in records
        if (
            as_float(row.get("size_m2")) is not None
            and as_float(row.get("size_m2")) > SIZE_MAX
        )
    ]

    low_ppm2 = [
        row for row in records
        if (
            price_per_m2(row) is not None
            and price_per_m2(row) < PPM2_MIN
        )
    ]

    high_ppm2 = [
        row for row in records
        if (
            price_per_m2(row) is not None
            and price_per_m2(row) > PPM2_MAX
        )
    ]

    high_bedrooms = [
        row for row in records
        if (
            as_float(row.get("bedrooms")) is not None
            and as_float(row.get("bedrooms")) > BEDROOM_MAX
        )
    ]

    high_bathrooms = [
        row for row in records
        if (
            as_float(row.get("bathrooms")) is not None
            and as_float(row.get("bathrooms")) > BATHROOM_MAX
        )
    ]

    high_floor = [
        row for row in records
        if (
            as_float(row.get("unit_floor")) is not None
            and as_float(row.get("unit_floor")) > UNIT_FLOOR_MAX
        )
    ]

    floor_above_building = []

    for row in records:
        floor = as_float(row.get("unit_floor"))
        total = as_float(row.get("building_total_floors"))

        if (
            floor is not None
            and total is not None
            and floor > total
        ):
            floor_above_building.append(row)

    size_mismatches = [
        row for row in records
        if row.get("size_m2_reference_mismatch")
    ]

    bedroom_url_mismatches = [
        row for row in records
        if row.get("bedrooms_url_mismatch")
    ]

    listing_type_url_mismatches = [
        row for row in records
        if row.get("listing_type_url_mismatch")
    ]

    floor_mismatches = [
        row for row in records
        if row.get("unit_floor_reference_mismatch")
    ]

    recoverable_price = [
        row for row in missing_price
        if title_prices(row.get("title"))
    ]

    recoverable_size = [
        row for row in missing_size
        if title_sizes(row.get("title"))
    ]

    aps_code_groups = duplicate_groups(
        records,
        "aps_listing_code",
    )

    property_code_groups = duplicate_groups(
        records,
        "property_code",
    )

    duplicate_records_by_aps = sum(
        len(rows) - 1
        for rows in aps_code_groups.values()
    )

    exact_signature_groups: dict[
        tuple[Any, ...],
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in records:
        signature = (
            clean_text(row.get("title")),
            as_float(row.get("price_usd")),
            as_float(row.get("size_m2")),
            as_float(row.get("bedrooms")),
            as_float(row.get("bathrooms")),
            as_float(row.get("unit_floor")),
        )

        exact_signature_groups[signature].append(row)

    exact_duplicate_groups = {
        repr(key): rows
        for key, rows in exact_signature_groups.items()
        if len(rows) > 1 and key[0]
    }

    print("\nAPS CLEANING DECISION AUDIT")
    print("=" * 110)
    print(f"Total Bronze records                 : {len(records):,}")
    print(f"Rent-only records                    : {len(rent_only):,}")
    print(f"Missing price                        : {len(missing_price):,}")
    print(f"Missing price recoverable from title : {len(recoverable_price):,}")
    print(f"Missing size                         : {len(missing_size):,}")
    print(f"Missing size recoverable from title  : {len(recoverable_size):,}")
    print(f"Price below ${PRICE_MIN:,}                  : {len(low_price):,}")
    print(f"Price above ${PRICE_MAX:,}               : {len(high_price):,}")
    print(f"Size below {SIZE_MIN}m²                         : {len(small_size):,}")
    print(f"Size above {SIZE_MAX}m²                        : {len(large_size):,}")
    print(f"Price/m² below ${PPM2_MIN:,}                   : {len(low_ppm2):,}")
    print(f"Price/m² above ${PPM2_MAX:,}                : {len(high_ppm2):,}")
    print(f"Bedrooms above {BEDROOM_MAX}                    : {len(high_bedrooms):,}")
    print(f"Bathrooms above {BATHROOM_MAX}                   : {len(high_bathrooms):,}")
    print(f"Unit floor above {UNIT_FLOOR_MAX}                  : {len(high_floor):,}")
    print(
        "Unit floor > building total floors   : "
        f"{len(floor_above_building):,}"
    )
    print(f"Size reference mismatches             : {len(size_mismatches):,}")
    print(f"Bedroom URL mismatches                : {len(bedroom_url_mismatches):,}")
    print(
        "Listing-type URL mismatches          : "
        f"{len(listing_type_url_mismatches):,}"
    )
    print(f"Unit-floor reference mismatches       : {len(floor_mismatches):,}")
    print(f"Duplicate APS-code groups             : {len(aps_code_groups):,}")
    print(
        "Expected duplicate rows by APS code  : "
        f"{duplicate_records_by_aps:,}"
    )
    print(f"Duplicate property-code groups        : {len(property_code_groups):,}")
    print(f"Exact listing-signature groups        : {len(exact_duplicate_groups):,}")

    print_group("RENT-ONLY", rent_only)
    print_group("MISSING PRICE", missing_price)
    print_group("MISSING SIZE", missing_size)
    print_group("LOW PRICE", low_price)
    print_group("HIGH PRICE", high_price)
    print_group("SMALL SIZE", small_size)
    print_group("LARGE SIZE", large_size)
    print_group("LOW PRICE/M²", low_ppm2)
    print_group("HIGH PRICE/M²", high_ppm2)
    print_group("SIZE REFERENCE MISMATCH", size_mismatches)
    print_group("BEDROOM URL MISMATCH", bedroom_url_mismatches)
    print_group(
        "LISTING-TYPE URL MISMATCH",
        listing_type_url_mismatches,
    )
    print_group(
        "UNIT-FLOOR REFERENCE MISMATCH",
        floor_mismatches,
    )

    print_duplicate_groups(
        "DUPLICATE APS LISTING CODE",
        aps_code_groups,
    )

    print_duplicate_groups(
        "DUPLICATE PROPERTY CODE",
        property_code_groups,
    )

    print_duplicate_groups(
        "EXACT LISTING SIGNATURE",
        exact_duplicate_groups,
    )

    print("\n" + "=" * 110)
    print("APS decision audit completed.")
    print("=" * 110)


if __name__ == "__main__":
    main()
