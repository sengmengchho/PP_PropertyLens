from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.cleaning.common import (
    calculate_price_per_m2,
    clean_text,
    is_missing,
    load_json_records,
    normalize_listing_type,
    safe_float,
)

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "bronze"
    / "khmer24"
    / "raw_listings.json"
)

LIMITS = {
    "price_min": 20_000,
    "price_max": 2_000_000,
    "size_min": 20,
    "size_max": 500,
    "ppm2_min": 300,
    "ppm2_max": 10_000,
}

DISTRICT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Boeung Keng Kang", re.compile(r"\b(?:boeung|boeng)\s+keng\s+kang\b|\bbkk\b", re.I)),
    ("Chamkarmon", re.compile(r"\bchamkar\s*mon\b|\bchamkarmon\b", re.I)),
    ("Chbar Ampov", re.compile(r"\bchbar\s+ampov\b", re.I)),
    ("Chroy Changvar", re.compile(r"\b(?:chrouy|chroy|chraoy)\s+(?:changva|changvar|chongvar)\b", re.I)),
    ("Daun Penh", re.compile(r"\b(?:daun|doun)\s+penh\b", re.I)),
    ("Dangkao", re.compile(r"\bdangkao\b|\bdangkor\b", re.I)),
    ("Kamboul", re.compile(r"\bkamboul\b", re.I)),
    ("Meanchey", re.compile(r"\bmean\s*chey\b|\bmeanchey\b", re.I)),
    ("Preaek Pnov", re.compile(r"\b(?:preaek|preek)\s+pnov\b", re.I)),
    ("Prampi Makara", re.compile(r"\b(?:7\s*makara|prampi\s+makara|prampir\s+meakkakra)\b", re.I)),
    ("Pur Senchey", re.compile(r"\b(?:por|pur|pou)\s*sen\s*chey\b", re.I)),
    ("Russey Keo", re.compile(r"\b(?:russey|ruessei)\s+(?:keo|kaev)\b", re.I)),
    ("Sen Sok", re.compile(r"\b(?:sen\s+sok|saen\s+sokh|sensok)\b", re.I)),
    ("Toul Kork", re.compile(r"\b(?:toul|tuol)\s+(?:kork|kouk)\b", re.I)),
]

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


def normalize_khmer24_district(value: Any) -> str | None:
    text = clean_text(value)
    if text is None:
        return None

    for standard, pattern in DISTRICT_PATTERNS:
        if pattern.search(text):
            return standard

    return text


def strip_age_suffix(value: Any) -> str | None:
    text = clean_text(value)
    if text is None:
        return None

    # Khmer24 card titles often end with relative age metadata such as
    # "21h •", "3d •", "24m •", or a date such as "Jun 14 •".
    text = re.sub(
        r"\s+(?:\d+\s*[mhdw]|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2})\s*•\s*$",
        "",
        text,
        flags=re.I,
    )
    return text.strip() or None


def parse_title_bedrooms(value: Any) -> int | None:
    text = strip_age_suffix(value)
    if text is None:
        return None

    lowered = text.lower()

    if re.search(r"\bstudio\b", lowered):
        return 0

    plus_match = re.search(
        r"\b(\d{1,2})\s*\+\s*(\d{1,2})\s*(?:bedrooms?|beds?|br)\b",
        lowered,
    )
    if plus_match:
        return int(plus_match.group(1)) + int(plus_match.group(2))

    digit_match = re.search(
        r"\b(\d{1,2})\s*[- ]?\s*(?:bedrooms?|beds?|br)\b",
        lowered,
    )
    if digit_match:
        return int(digit_match.group(1))

    words = "|".join(NUMBER_WORDS)
    word_match = re.search(
        rf"\b({words})\s*[- ]?\s*(?:bedrooms?|beds?|br)\b",
        lowered,
    )
    if word_match:
        return NUMBER_WORDS[word_match.group(1)]

    return None


def is_sale_like(record: dict[str, Any]) -> bool:
    price = safe_float(record.get("price_usd"))
    size = safe_float(record.get("size_m2"))
    ppm2 = calculate_price_per_m2(price, size)

    return bool(
        price is not None
        and size is not None
        and LIMITS["price_min"] <= price <= LIMITS["price_max"]
        and LIMITS["size_min"] <= size <= LIMITS["size_max"]
        and ppm2 is not None
        and LIMITS["ppm2_min"] <= ppm2 <= LIMITS["ppm2_max"]
    )


def print_examples(title: str, records: list[dict[str, Any]], limit: int = 10) -> None:
    print("\n" + "=" * 100)
    print(f"{title}: {len(records)} records")
    print("=" * 100)

    for row in records[:limit]:
        price = safe_float(row.get("price_usd"))
        size = safe_float(row.get("size_m2"))
        ppm2 = calculate_price_per_m2(price, size)

        print("\n" + "-" * 100)
        print("ID            :", row.get("listing_id"))
        print("Title raw     :", row.get("title"))
        print("Title cleaned :", strip_age_suffix(row.get("title")))
        print("Listing type  :", row.get("listing_type"))
        print("Province      :", row.get("province"))
        print("District raw  :", row.get("district"))
        print("District clean:", normalize_khmer24_district(row.get("district")))
        print("Price         :", price)
        print("Size          :", size)
        print("Price/m²      :", ppm2)
        print("Bedrooms      :", row.get("bedrooms"))
        print("Title bedroom :", parse_title_bedrooms(row.get("title")))
        print("Bathrooms     :", row.get("bathrooms"))
        print("Unit floor    :", row.get("unit_floor"))
        print("Property      :", row.get("property_type"))
        print("Detail type   :", row.get("property_type_detail_value"))

        for key, value in row.items():
            if key.endswith("_conflict") and not is_missing(value):
                print(f"{key:<30}: {value}")

        print("URL           :", row.get("url"))


def main() -> None:
    records = load_json_records(INPUT_PATH)

    non_phnom_penh = [
        row
        for row in records
        if (clean_text(row.get("province")) or "").lower() != "phnom penh"
    ]

    rent_records = [
        row
        for row in records
        if normalize_listing_type(row.get("listing_type")) == "rent"
    ]

    sale_rent = [
        row
        for row in records
        if normalize_listing_type(row.get("listing_type")) == "sale/rent"
    ]
    sale_rent_sale_like = [row for row in sale_rent if is_sale_like(row)]
    sale_rent_ambiguous = [row for row in sale_rent if not is_sale_like(row)]

    missing_size = [row for row in records if safe_float(row.get("size_m2")) is None]
    low_price = [
        row
        for row in records
        if safe_float(row.get("price_usd")) is not None
        and safe_float(row.get("price_usd")) < LIMITS["price_min"]
    ]
    high_price = [
        row
        for row in records
        if safe_float(row.get("price_usd")) is not None
        and safe_float(row.get("price_usd")) > LIMITS["price_max"]
    ]
    small_size = [
        row
        for row in records
        if safe_float(row.get("size_m2")) is not None
        and safe_float(row.get("size_m2")) < LIMITS["size_min"]
    ]
    large_size = [
        row
        for row in records
        if safe_float(row.get("size_m2")) is not None
        and safe_float(row.get("size_m2")) > LIMITS["size_max"]
    ]

    property_conflicts = [
        row for row in records if not is_missing(row.get("property_type_conflict"))
    ]
    house_or_flat = [
        row
        for row in property_conflicts
        if str(row.get("property_type_detail_value") or "").lower()
        in {"house", "flat", "villa", "land", "commercial"}
    ]

    bedroom_conflicts = [
        row for row in records if not is_missing(row.get("bedrooms_conflict"))
    ]
    title_resolvable_bedrooms = [
        row for row in bedroom_conflicts if parse_title_bedrooms(row.get("title")) is not None
    ]
    unresolved_bedrooms = [
        row for row in bedroom_conflicts if parse_title_bedrooms(row.get("title")) is None
    ]

    age_suffix_records = [
        row
        for row in records
        if strip_age_suffix(row.get("title")) != clean_text(row.get("title"))
    ]

    district_changed = [
        row
        for row in records
        if normalize_khmer24_district(row.get("district"))
        != clean_text(row.get("district"))
    ]

    detail_missing = [row for row in records if not row.get("detail_parsed_at")]

    print("\nKHMER24 CLEANING DECISION AUDIT")
    print("=" * 100)
    print(f"Total Bronze records                  : {len(records):,}")
    print(f"Phnom Penh records                    : {len(records) - len(non_phnom_penh):,}")
    print(f"Non-Phnom Penh records                : {len(non_phnom_penh):,}")
    print(f"Rent-only records                     : {len(rent_records):,}")
    print(f"Sale/rent records                     : {len(sale_rent):,}")
    print(f"  Sale-like numeric profile           : {len(sale_rent_sale_like):,}")
    print(f"  Ambiguous numeric profile           : {len(sale_rent_ambiguous):,}")
    print(f"Missing size                          : {len(missing_size):,}")
    print(f"Price below ${LIMITS['price_min']:,}                : {len(low_price):,}")
    print(f"Price above ${LIMITS['price_max']:,}             : {len(high_price):,}")
    print(f"Size below {LIMITS['size_min']}m²                    : {len(small_size):,}")
    print(f"Size above {LIMITS['size_max']}m²                   : {len(large_size):,}")
    print(f"Property-type conflicts               : {len(property_conflicts):,}")
    print(f"  Explicit House/Flat/etc.            : {len(house_or_flat):,}")
    print(f"Bedroom conflicts                     : {len(bedroom_conflicts):,}")
    print(f"  Resolvable from current title       : {len(title_resolvable_bedrooms):,}")
    print(f"  Still unresolved                    : {len(unresolved_bedrooms):,}")
    print(f"Titles with Khmer24 age suffix        : {len(age_suffix_records):,}")
    print(f"District labels needing normalization : {len(district_changed):,}")
    print(f"Records without parsed detail page    : {len(detail_missing):,}")

    district_pairs = Counter(
        (
            clean_text(row.get("district")) or "Missing",
            normalize_khmer24_district(row.get("district")) or "Missing",
        )
        for row in district_changed
    )

    print("\nDISTRICT NORMALIZATION PREVIEW")
    print("-" * 100)
    if district_pairs:
        for (raw, cleaned), count in district_pairs.most_common():
            print(f"{raw:<42} -> {cleaned:<25} ({count})")
    else:
        print("No district labels need normalization.")

    print_examples("NON-PHNOM PENH", non_phnom_penh)
    print_examples("RENT-ONLY", rent_records)
    print_examples("SALE/RENT — SALE-LIKE", sale_rent_sale_like)
    print_examples("SALE/RENT — AMBIGUOUS", sale_rent_ambiguous)
    print_examples("LOW-PRICE", low_price)
    print_examples("HIGH-PRICE", high_price)
    print_examples("LARGE-SIZE", large_size)
    print_examples("EXPLICIT NON-CONDO PROPERTY", house_or_flat)
    print_examples("TITLE-RESOLVABLE BEDROOM CONFLICT", title_resolvable_bedrooms)
    print_examples("UNRESOLVED BEDROOM CONFLICT", unresolved_bedrooms)
    print_examples("MISSING DETAIL PAGE", detail_missing)

    print("\n" + "=" * 100)
    print("Khmer24 decision audit completed.")
    print("=" * 100)


if __name__ == "__main__":
    main()