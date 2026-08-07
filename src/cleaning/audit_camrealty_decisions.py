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
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


POSSIBLE_INPUT_PATHS = [
    PROJECT_ROOT / "data" / "bronze" / "camrealtyservice_com" / "raw_listings.json",
    PROJECT_ROOT / "data" / "bronze" / "camrealtyservice" / "raw_listings.json",
    PROJECT_ROOT / "data" / "bronze" / "camrealty" / "raw_listings.json",
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

VALID_CODE_RE = re.compile(r"^[SR]\d{5,}$", re.I)
URL_CODE_RE = re.compile(r"(?:-|/)([SR]\d{5,})/?$", re.I)


def find_input_path() -> Path:
    for path in POSSIBLE_INPUT_PATHS:
        if path.exists():
            return path

    checked = "\n".join(str(path) for path in POSSIBLE_INPUT_PATHS)
    raise FileNotFoundError(
        "CamRealtyService Bronze file was not found.\n"
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


def normalized_signature_text(value: Any) -> str:
    text = clean_text(value) or ""
    text = text.casefold()
    text = re.sub(r"[^\w\u1780-\u17ff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_url_code(value: Any) -> str | None:
    url = normalize_url(value)

    if not url:
        return None

    match = URL_CODE_RE.search(urlsplit(url).path)
    return match.group(1).upper() if match else None


def normalize_raw_code(value: Any) -> str | None:
    code = clean_text(value)

    if not code:
        return None

    code = code.upper()
    return code if VALID_CODE_RE.fullmatch(code) else None


def load_records(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        raise TypeError("Expected raw_listings.json to contain a JSON list.")

    return [row for row in data if isinstance(row, dict)]


def price_per_m2(row: dict[str, Any]) -> float | None:
    price = as_float(row.get("price_usd"))
    size = as_float(row.get("size_m2"))

    if price is None or size is None or price <= 0 or size <= 0:
        return None

    return round(price / size, 2)


def print_record(row: dict[str, Any]) -> None:
    raw_code = clean_text(row.get("property_code"))
    normalized_code = normalize_raw_code(raw_code)
    url_code = parse_url_code(row.get("url"))

    print("\n" + "-" * 110)
    print("ID                    :", row.get("listing_id"))
    print("Raw property code     :", raw_code)
    print("Normalized raw code   :", normalized_code)
    print("URL property code     :", url_code)
    print("Title                 :", row.get("title"))
    print("Listing type          :", row.get("listing_type"))
    print("Property type         :", row.get("property_type"))
    print("Price                 :", row.get("price_usd"))
    print("Size                  :", row.get("size_m2"))
    print("Price/m²              :", price_per_m2(row))
    print("Bedrooms              :", row.get("bedrooms"))
    print("Title bedrooms        :", row.get("bedrooms_title_value"))
    print("Structured bedrooms   :", row.get("bedrooms_candidate_value"))
    print("Bathrooms             :", row.get("bathrooms"))
    print("Unit floor            :", row.get("unit_floor"))
    print("Building total floors :", row.get("building_total_floors"))
    print("District              :", row.get("district"))
    print("Commune               :", row.get("commune"))
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


def print_group(title: str, rows: list[dict[str, Any]], limit: int = 12) -> None:
    print("\n" + "=" * 110)
    print(f"{title}: {len(rows)} records")
    print("=" * 110)

    for row in rows[:limit]:
        print_record(row)


def print_duplicate_groups(
    title: str,
    groups: dict[Any, list[dict[str, Any]]],
    limit: int = 20,
) -> None:
    print("\n" + "=" * 110)
    print(f"{title}: {len(groups)} groups")
    print("=" * 110)

    if not groups:
        print("No groups found.")
        return

    for signature, rows in sorted(
        groups.items(),
        key=lambda item: len(item[1]),
        reverse=True,
    )[:limit]:
        print("\n" + "-" * 110)
        print("Signature:", signature)
        print("Records  :", len(rows))

        for row in rows:
            print(
                "  -",
                row.get("listing_id"),
                "| raw_code=",
                row.get("property_code"),
                "| url_code=",
                parse_url_code(row.get("url")),
                "| price=",
                row.get("price_usd"),
                "| size=",
                row.get("size_m2"),
                "| title=",
                row.get("title"),
            )


def main() -> None:
    input_path = find_input_path()
    records = load_records(input_path)

    rent_only = [r for r in records if r.get("listing_type") == "rent"]
    non_condo = [
        r for r in records
        if r.get("property_type") not in {"Condo", "Penthouse"}
    ]
    missing_price = [r for r in records if is_missing(r.get("price_usd"))]
    missing_size = [r for r in records if is_missing(r.get("size_m2"))]
    missing_district = [r for r in records if is_missing(r.get("district"))]

    low_price = [
        r for r in records
        if as_float(r.get("price_usd")) is not None
        and as_float(r.get("price_usd")) < SALE_PRICE_MIN
    ]
    high_price = [
        r for r in records
        if as_float(r.get("price_usd")) is not None
        and as_float(r.get("price_usd")) > SALE_PRICE_MAX
    ]
    small_size = [
        r for r in records
        if as_float(r.get("size_m2")) is not None
        and as_float(r.get("size_m2")) < SIZE_MIN
    ]
    large_size = [
        r for r in records
        if as_float(r.get("size_m2")) is not None
        and as_float(r.get("size_m2")) > SIZE_MAX
    ]
    low_ppm2 = [
        r for r in records
        if price_per_m2(r) is not None and price_per_m2(r) < PPM2_MIN
    ]
    high_ppm2 = [
        r for r in records
        if price_per_m2(r) is not None and price_per_m2(r) > PPM2_MAX
    ]
    high_bedrooms = [
        r for r in records
        if as_float(r.get("bedrooms")) is not None
        and as_float(r.get("bedrooms")) > BEDROOM_MAX
    ]
    high_bathrooms = [
        r for r in records
        if as_float(r.get("bathrooms")) is not None
        and as_float(r.get("bathrooms")) > BATHROOM_MAX
    ]
    high_floor = [
        r for r in records
        if as_float(r.get("unit_floor")) is not None
        and as_float(r.get("unit_floor")) > UNIT_FLOOR_MAX
    ]

    floor_above_building = []
    for row in records:
        floor = as_float(row.get("unit_floor"))
        total = as_float(row.get("building_total_floors"))
        if floor is not None and total is not None and floor > total:
            floor_above_building.append(row)

    bedroom_conflicts = [r for r in records if r.get("bedrooms_conflict")]
    bedroom_mismatches = [
        r for r in records if r.get("bedrooms_reference_mismatch")
    ]
    property_conflicts = [
        r for r in records if r.get("property_type_conflict")
    ]
    listing_type_url_mismatches = [
        r for r in records if r.get("listing_type_url_mismatch")
    ]

    raw_invalid_code_records = [
        r for r in records
        if clean_text(r.get("property_code"))
        and not normalize_raw_code(r.get("property_code"))
    ]

    code_mismatches = []
    raw_code_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    url_code_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in records:
        raw_code = normalize_raw_code(row.get("property_code"))
        url_code = parse_url_code(row.get("url"))

        if raw_code:
            raw_code_groups[raw_code].append(row)

        if url_code:
            url_code_groups[url_code].append(row)

        if raw_code and url_code and raw_code != url_code:
            code_mismatches.append(row)

    duplicate_raw_code_groups = {
        code: rows
        for code, rows in raw_code_groups.items()
        if len(rows) > 1
    }
    duplicate_url_code_groups = {
        code: rows
        for code, rows in url_code_groups.items()
        if len(rows) > 1
    }

    exact_signature_groups: dict[
        tuple[Any, ...],
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in records:
        signature = (
            normalized_signature_text(row.get("title")),
            as_float(row.get("price_usd")),
            as_float(row.get("size_m2")),
            as_float(row.get("bedrooms")),
            as_float(row.get("bathrooms")),
        )
        exact_signature_groups[signature].append(row)

    duplicate_signature_groups = {
        signature: rows
        for signature, rows in exact_signature_groups.items()
        if len(rows) > 1 and signature[0]
    }

    out_of_scope_counts = Counter(
        clean_text(r.get("out_of_scope_reason"))
        for r in records
        if clean_text(r.get("out_of_scope_reason"))
    )

    print("\nCAMREALTY CLEANING DECISION AUDIT")
    print("=" * 110)
    print(f"Total Bronze records                : {len(records):,}")
    print(f"Rent-only records                   : {len(rent_only):,}")
    print(f"Non-condo property records          : {len(non_condo):,}")
    print(f"Missing price                       : {len(missing_price):,}")
    print(f"Missing size                        : {len(missing_size):,}")
    print(f"Missing district                    : {len(missing_district):,}")
    print(f"Price below ${SALE_PRICE_MIN:,}                 : {len(low_price):,}")
    print(f"Price above ${SALE_PRICE_MAX:,}              : {len(high_price):,}")
    print(f"Size below {SIZE_MIN}m²                        : {len(small_size):,}")
    print(f"Size above {SIZE_MAX}m²                       : {len(large_size):,}")
    print(f"Price/m² below ${PPM2_MIN:,}                  : {len(low_ppm2):,}")
    print(f"Price/m² above ${PPM2_MAX:,}               : {len(high_ppm2):,}")
    print(f"Bedrooms above {BEDROOM_MAX}                   : {len(high_bedrooms):,}")
    print(f"Bathrooms above {BATHROOM_MAX}                  : {len(high_bathrooms):,}")
    print(f"Unit floor above {UNIT_FLOOR_MAX}                 : {len(high_floor):,}")
    print(
        "Unit floor > building total floors  : "
        f"{len(floor_above_building):,}"
    )
    print(f"Bedroom conflicts                    : {len(bedroom_conflicts):,}")
    print(f"Bedroom reference mismatches         : {len(bedroom_mismatches):,}")
    print(f"Property-type conflicts              : {len(property_conflicts):,}")
    print(
        "Listing-type URL mismatches         : "
        f"{len(listing_type_url_mismatches):,}"
    )
    print(
        "Invalid raw property-code records   : "
        f"{len(raw_invalid_code_records):,}"
    )
    print(
        "Raw-code versus URL-code mismatches : "
        f"{len(code_mismatches):,}"
    )
    print(
        "Duplicate valid raw-code groups     : "
        f"{len(duplicate_raw_code_groups):,}"
    )
    print(
        "Duplicate URL-code groups           : "
        f"{len(duplicate_url_code_groups):,}"
    )
    print(
        "Exact listing-signature groups      : "
        f"{len(duplicate_signature_groups):,}"
    )

    print("\nOUT-OF-SCOPE REASONS")
    print("-" * 110)

    if out_of_scope_counts:
        for reason, count in out_of_scope_counts.most_common():
            print(f"{reason:<75}: {count}")
    else:
        print("No out-of-scope reasons found.")

    print_group("RENT-ONLY", rent_only)
    print_group("NON-CONDO PROPERTY", non_condo)
    print_group("MISSING PRICE", missing_price)
    print_group("MISSING SIZE", missing_size)
    print_group("HIGH PRICE", high_price)
    print_group("LARGE SIZE", large_size)
    print_group("LOW PRICE/M²", low_ppm2)
    print_group("HIGH PRICE/M²", high_ppm2)
    print_group("BEDROOM CONFLICT", bedroom_conflicts)
    print_group("BEDROOM REFERENCE MISMATCH", bedroom_mismatches)
    print_group("PROPERTY-TYPE CONFLICT", property_conflicts)
    print_group("LISTING-TYPE URL MISMATCH", listing_type_url_mismatches)
    print_group("INVALID RAW PROPERTY CODE", raw_invalid_code_records)
    print_group("RAW CODE VS URL CODE MISMATCH", code_mismatches, limit=20)

    print_duplicate_groups(
        "DUPLICATE VALID RAW PROPERTY CODE",
        duplicate_raw_code_groups,
    )
    print_duplicate_groups(
        "DUPLICATE URL PROPERTY CODE",
        duplicate_url_code_groups,
    )
    print_duplicate_groups(
        "EXACT LISTING SIGNATURE",
        duplicate_signature_groups,
    )

    print("\n" + "=" * 110)
    print("CamRealty decision audit completed.")
    print("=" * 110)


if __name__ == "__main__":
    main()
