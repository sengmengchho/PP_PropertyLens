from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="replace",
    )

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = PROJECT_ROOT / "data" / "bronze" / "realestate" / "raw_listings.json"

AMBIGUOUS_TYPES = {"Apartment", "Serviced Apartment", "Project"}


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def as_float(value: Any) -> float | None:
    if is_missing(value) or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found:\n{path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError("Expected a JSON list.")

    return [row for row in data if isinstance(row, dict)]


def text(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(field) or "")
        for field in ("title", "description", "detail_title")
    ).lower()


def ppm2(row: dict[str, Any]) -> float | None:
    price = as_float(row.get("price_usd"))
    size = as_float(row.get("size_m2"))

    if price is None or size is None or price <= 0 or size <= 0:
        return None

    return price / size


def print_examples(title: str, rows: list[dict[str, Any]], limit: int = 5) -> None:
    print("\n" + "=" * 100)
    print(f"{title}: {len(rows)} records")
    print("=" * 100)

    for row in rows[:limit]:
        print("\n" + "-" * 100)
        print("ID          :", row.get("listing_id"))
        print("Title       :", row.get("title"))
        print("Listing type:", row.get("listing_type"))
        print("Property    :", row.get("property_type"))
        print("Project page:", row.get("display_as_project"))
        print("Price       :", row.get("price_usd"))
        print("Size        :", row.get("size_m2"))
        value = ppm2(row)
        print("Price/m²    :", round(value, 2) if value is not None else None)
        print("Bedrooms    :", row.get("bedrooms"))
        print("Conflict    :", row.get("bedrooms_conflict"))
        print("URL         :", row.get("url"))


def main() -> None:
    rows = load_rows(INPUT_PATH)

    project_pages = [row for row in rows if bool(row.get("display_as_project"))]
    project_page_types = Counter(
        str(row.get("property_type") or "Missing")
        for row in project_pages
    )

    sale_rent = [
        row for row in rows
        if str(row.get("listing_type") or "").strip().lower() == "sale/rent"
    ]

    sale_rent_low_price = [
        row for row in sale_rent
        if (as_float(row.get("price_usd")) or 0) < 20_000
    ]

    sale_rent_sale_like = []
    sale_rent_suspicious = []

    for row in sale_rent:
        price = as_float(row.get("price_usd"))
        size = as_float(row.get("size_m2"))
        value = ppm2(row)

        looks_sale_like = (
            price is not None
            and size is not None
            and 20_000 <= price <= 2_000_000
            and 20 <= size <= 500
            and value is not None
            and 300 <= value <= 10_000
        )

        if looks_sale_like:
            sale_rent_sale_like.append(row)
        else:
            sale_rent_suspicious.append(row)

    bedroom_conflicts = [
        row for row in rows
        if not is_missing(row.get("bedrooms_conflict"))
    ]

    studio_conflicts = [
        row for row in bedroom_conflicts
        if re.search(r"\bstudio\b", text(row), re.I)
    ]

    project_bedroom_conflicts = [
        row for row in bedroom_conflicts
        if bool(row.get("display_as_project"))
    ]

    other_bedroom_conflicts = [
        row for row in bedroom_conflicts
        if row not in studio_conflicts and row not in project_bedroom_conflicts
    ]

    ambiguous = [
        row for row in rows
        if str(row.get("property_type") or "").strip() in AMBIGUOUS_TYPES
    ]

    ambiguous_with_condo_evidence = [
        row for row in ambiguous
        if re.search(r"\b(?:condo|condominium|penthouse)\b", text(row), re.I)
    ]

    ambiguous_without_condo_evidence = [
        row for row in ambiguous
        if row not in ambiguous_with_condo_evidence
    ]

    print("\nREALESTATE CLEANING DECISION AUDIT")
    print("=" * 100)
    print(f"Total Bronze records                    : {len(rows):,}")
    print(f"display_as_project=True                 : {len(project_pages):,}")
    print(f"Sale/rent records                       : {len(sale_rent):,}")
    print(f"  Sale-like numeric profile             : {len(sale_rent_sale_like):,}")
    print(f"  Suspicious/ambiguous numeric profile  : {len(sale_rent_suspicious):,}")
    print(f"  Price below $20,000                   : {len(sale_rent_low_price):,}")
    print(f"Bedroom conflicts                       : {len(bedroom_conflicts):,}")
    print(f"  Studio-related                        : {len(studio_conflicts):,}")
    print(f"  Project-page related                  : {len(project_bedroom_conflicts):,}")
    print(f"  Other                                 : {len(other_bedroom_conflicts):,}")
    print(f"Ambiguous raw property types            : {len(ambiguous):,}")
    print(f"  Explicit condo/penthouse evidence     : {len(ambiguous_with_condo_evidence):,}")
    print(f"  No condo/penthouse evidence           : {len(ambiguous_without_condo_evidence):,}")

    print("\nPROJECT-PAGE PROPERTY TYPES")
    for value, count in project_page_types.most_common():
        print(f"{value:<30}: {count}")

    print_examples("PROJECT-LEVEL PAGE EXAMPLES", project_pages)
    print_examples("SALE/RENT — SALE-LIKE EXAMPLES", sale_rent_sale_like)
    print_examples("SALE/RENT — SUSPICIOUS EXAMPLES", sale_rent_suspicious)
    print_examples("STUDIO BEDROOM-CONFLICT EXAMPLES", studio_conflicts)
    print_examples("PROJECT-PAGE BEDROOM-CONFLICT EXAMPLES", project_bedroom_conflicts)
    print_examples("OTHER BEDROOM-CONFLICT EXAMPLES", other_bedroom_conflicts)
    print_examples("AMBIGUOUS TYPES WITH CONDO EVIDENCE", ambiguous_with_condo_evidence)
    print_examples("AMBIGUOUS TYPES WITHOUT CONDO EVIDENCE", ambiguous_without_condo_evidence)

    print("\n" + "=" * 100)
    print("Decision audit completed.")
    print("=" * 100)


if __name__ == "__main__":
    main()