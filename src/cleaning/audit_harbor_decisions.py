from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


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
    / "harbor-property_com"
    / "raw_listings.json",

    PROJECT_ROOT
    / "data"
    / "bronze"
    / "harbor_property_com"
    / "raw_listings.json",

    PROJECT_ROOT
    / "data"
    / "bronze"
    / "harbor"
    / "raw_listings.json",
]


SALE_PRICE_MIN = 20_000
SALE_PRICE_MAX = 2_000_000
SIZE_MIN = 20
SIZE_MAX = 500
PPM2_MIN = 300
PPM2_MAX = 10_000
BEDROOM_MAX = 10
BATHROOM_MAX = 10
UNIT_FLOOR_MAX = 100


def find_input_path() -> Path:
    for path in POSSIBLE_INPUT_PATHS:
        if path.exists():
            return path

    checked = "\n".join(str(path) for path in POSSIBLE_INPUT_PATHS)

    raise FileNotFoundError(
        "Harbor Property Bronze file was not found.\n"
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


def normalize_url(value: Any) -> str | None:
    text = clean_text(value)

    if text is None:
        return None

    try:
        parts = urlsplit(text)
    except ValueError:
        return text

    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            "",
            "",
        )
    )


def normalize_signature_text(value: Any) -> str:
    text = clean_text(value) or ""
    text = text.casefold()
    text = re.sub(r"[^\w\u1780-\u17ff]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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


def price_per_m2(row: dict[str, Any]) -> float | None:
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


def unique_commune_district_map(
    records: list[dict[str, Any]],
) -> tuple[
    dict[str, str],
    dict[str, Counter[str]],
]:
    evidence: dict[str, Counter[str]] = defaultdict(Counter)

    for row in records:
        commune = clean_text(row.get("commune"))
        district = clean_text(row.get("district"))

        if commune and district:
            evidence[commune][district] += 1

    unique_map: dict[str, str] = {}

    for commune, counts in evidence.items():
        if len(counts) == 1:
            unique_map[commune] = next(iter(counts))

    return unique_map, evidence


def print_record(row: dict[str, Any]) -> None:
    print("\n" + "-" * 110)
    print("ID                 :", row.get("listing_id"))
    print("Title              :", row.get("title"))
    print("Listing type       :", row.get("listing_type"))
    print("Property type      :", row.get("property_type"))
    print("Price              :", row.get("price_usd"))
    print("Size               :", row.get("size_m2"))
    print("Price/m²           :", price_per_m2(row))
    print("Bedrooms           :", row.get("bedrooms"))
    print("Bathrooms          :", row.get("bathrooms"))
    print("Unit floor         :", row.get("unit_floor"))
    print("Building floors    :", row.get("building_total_floors"))
    print("District           :", row.get("district"))
    print("Commune            :", row.get("commune"))
    print("Current bed source :", row.get("bedrooms_source"))
    print("Current bath source:", row.get("bathrooms_source"))
    print("Current floor src  :", row.get("unit_floor_source"))

    for key in [
        "bedrooms_previous_value",
        "bedrooms_reference_mismatch",
        "bathrooms_previous_value",
        "bathrooms_reference_mismatch",
        "unit_floor_previous_value",
        "unit_floor_reference_mismatch",
    ]:
        value = row.get(key)

        if not is_missing(value):
            print(f"{key:<32}: {value}")

    print("URL                :", row.get("url"))


def print_group(
    title: str,
    rows: list[dict[str, Any]],
    limit: int = 12,
) -> None:
    print("\n" + "=" * 110)
    print(f"{title}: {len(rows)} records")
    print("=" * 110)

    for row in rows[:limit]:
        print_record(row)


def print_duplicate_groups(
    title: str,
    groups: dict[Any, list[dict[str, Any]]],
    limit: int = 15,
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

    for signature, rows in sorted_groups[:limit]:
        print("\n" + "-" * 110)
        print("Signature:", signature)
        print("Records  :", len(rows))

        for row in rows:
            print(
                "  -",
                row.get("listing_id"),
                "|",
                row.get("title"),
                "| price=",
                row.get("price_usd"),
                "| size=",
                row.get("size_m2"),
                "| commune=",
                row.get("commune"),
            )


def main() -> None:
    input_path = find_input_path()
    records = load_records(input_path)

    missing_price = [
        row for row in records
        if is_missing(row.get("price_usd"))
    ]

    missing_size = [
        row for row in records
        if is_missing(row.get("size_m2"))
    ]

    missing_district = [
        row for row in records
        if is_missing(row.get("district"))
    ]

    low_price = [
        row for row in records
        if (
            as_float(row.get("price_usd")) is not None
            and as_float(row.get("price_usd")) < SALE_PRICE_MIN
        )
    ]

    high_price = [
        row for row in records
        if (
            as_float(row.get("price_usd")) is not None
            and as_float(row.get("price_usd")) > SALE_PRICE_MAX
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
        unit_floor = as_float(row.get("unit_floor"))
        total_floors = as_float(
            row.get("building_total_floors")
        )

        if (
            unit_floor is not None
            and total_floors is not None
            and unit_floor > total_floors
        ):
            floor_above_building.append(row)

    bedroom_mismatch = [
        row for row in records
        if row.get("bedrooms_reference_mismatch")
    ]

    bathroom_mismatch = [
        row for row in records
        if row.get("bathrooms_reference_mismatch")
    ]

    floor_mismatch = [
        row for row in records
        if row.get("unit_floor_reference_mismatch")
    ]

    unique_commune_map, commune_evidence = (
        unique_commune_district_map(records)
    )

    missing_district_resolvable = []
    missing_district_ambiguous = []
    missing_district_unmapped = []

    for row in missing_district:
        commune = clean_text(row.get("commune"))

        if not commune:
            missing_district_unmapped.append(row)
        elif commune in unique_commune_map:
            missing_district_resolvable.append(row)
        elif commune in commune_evidence:
            missing_district_ambiguous.append(row)
        else:
            missing_district_unmapped.append(row)

    commune_counts_missing_district = Counter(
        clean_text(row.get("commune")) or "Missing"
        for row in missing_district
    )

    exact_signature_groups: dict[
        tuple[Any, ...],
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in records:
        signature = (
            normalize_signature_text(row.get("title")),
            as_float(row.get("price_usd")),
            as_float(row.get("size_m2")),
            clean_text(row.get("commune")),
        )

        exact_signature_groups[signature].append(row)

    exact_duplicate_groups = {
        signature: rows
        for signature, rows in exact_signature_groups.items()
        if (
            len(rows) > 1
            and signature[0]
        )
    }

    value_signature_groups: dict[
        tuple[Any, ...],
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in records:
        signature = (
            as_float(row.get("price_usd")),
            as_float(row.get("size_m2")),
            as_float(row.get("bedrooms")),
            as_float(row.get("bathrooms")),
            as_float(row.get("unit_floor")),
            clean_text(row.get("commune")),
        )

        value_signature_groups[signature].append(row)

    value_duplicate_groups = {
        signature: rows
        for signature, rows in value_signature_groups.items()
        if (
            len(rows) > 1
            and signature[0] is not None
            and signature[1] is not None
        )
    }

    print("\nHARBOR PROPERTY CLEANING DECISION AUDIT")
    print("=" * 110)
    print(f"Total Bronze records               : {len(records):,}")
    print(f"Missing price                      : {len(missing_price):,}")
    print(f"Missing size                       : {len(missing_size):,}")
    print(f"Missing district                   : {len(missing_district):,}")
    print(
        "  Resolvable from unique commune   : "
        f"{len(missing_district_resolvable):,}"
    )
    print(
        "  Ambiguous commune mapping        : "
        f"{len(missing_district_ambiguous):,}"
    )
    print(
        "  Unmapped/no commune              : "
        f"{len(missing_district_unmapped):,}"
    )
    print(f"Price below ${SALE_PRICE_MIN:,}                : {len(low_price):,}")
    print(f"Price above ${SALE_PRICE_MAX:,}             : {len(high_price):,}")
    print(f"Size below {SIZE_MIN}m²                       : {len(small_size):,}")
    print(f"Size above {SIZE_MAX}m²                      : {len(large_size):,}")
    print(f"Price/m² below ${PPM2_MIN:,}                 : {len(low_ppm2):,}")
    print(f"Price/m² above ${PPM2_MAX:,}              : {len(high_ppm2):,}")
    print(f"Bedrooms above {BEDROOM_MAX}                  : {len(high_bedrooms):,}")
    print(f"Bathrooms above {BATHROOM_MAX}                 : {len(high_bathrooms):,}")
    print(f"Unit floor above {UNIT_FLOOR_MAX}                : {len(high_floor):,}")
    print(
        "Unit floor > building total floors : "
        f"{len(floor_above_building):,}"
    )
    print(f"Bedroom reference mismatches        : {len(bedroom_mismatch):,}")
    print(f"Bathroom reference mismatches       : {len(bathroom_mismatch):,}")
    print(f"Unit-floor reference mismatches     : {len(floor_mismatch):,}")
    print(
        "Exact title+price+size+commune groups: "
        f"{len(exact_duplicate_groups):,}"
    )
    print(
        "Same numeric/property value groups : "
        f"{len(value_duplicate_groups):,}"
    )

    print("\nMISSING-DISTRICT COMMUNES")
    print("-" * 110)

    for commune, count in commune_counts_missing_district.most_common(40):
        inferred = unique_commune_map.get(commune)
        suffix = (
            f" -> {inferred}"
            if inferred
            else ""
        )
        print(f"{commune:<60}: {count}{suffix}")

    print_group(
        "MISSING PRICE",
        missing_price,
        limit=10,
    )

    print_group(
        "MISSING SIZE",
        missing_size,
        limit=12,
    )

    print_group(
        "LOW PRICE",
        low_price,
        limit=12,
    )

    print_group(
        "HIGH PRICE",
        high_price,
        limit=12,
    )

    print_group(
        "SMALL SIZE",
        small_size,
        limit=10,
    )

    print_group(
        "LARGE SIZE",
        large_size,
        limit=15,
    )

    print_group(
        "LOW PRICE/M²",
        low_ppm2,
        limit=15,
    )

    print_group(
        "HIGH PRICE/M²",
        high_ppm2,
        limit=10,
    )

    print_group(
        "BEDROOMS ABOVE LIMIT",
        high_bedrooms,
        limit=10,
    )

    print_group(
        "BATHROOMS ABOVE LIMIT",
        high_bathrooms,
        limit=10,
    )

    print_group(
        "BEDROOM REFERENCE MISMATCH",
        bedroom_mismatch,
        limit=15,
    )

    print_group(
        "BATHROOM REFERENCE MISMATCH",
        bathroom_mismatch,
        limit=15,
    )

    print_group(
        "UNIT-FLOOR REFERENCE MISMATCH",
        floor_mismatch,
        limit=15,
    )

    print_group(
        "MISSING DISTRICT — RESOLVABLE",
        missing_district_resolvable,
        limit=12,
    )

    print_group(
        "MISSING DISTRICT — AMBIGUOUS",
        missing_district_ambiguous,
        limit=12,
    )

    print_group(
        "MISSING DISTRICT — UNMAPPED",
        missing_district_unmapped,
        limit=12,
    )

    print_duplicate_groups(
        "EXACT LISTING-SIGNATURE DUPLICATES",
        exact_duplicate_groups,
        limit=15,
    )

    print_duplicate_groups(
        "SAME NUMERIC/PROPERTY SIGNATURE",
        value_duplicate_groups,
        limit=15,
    )

    print("\n" + "=" * 110)
    print("Harbor Property decision audit completed.")
    print("=" * 110)


if __name__ == "__main__":
    main()