from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


PROJECT_ROOT = Path(__file__).resolve().parents[2]


STANDARD_COLUMNS = [
    # Identity
    "listing_id",
    "source",
    "source_listing_id",
    "source_listing_code",
    "url",
    "canonical_url",

    # Main listing information
    "title",
    "description",
    "listing_type",
    "property_type",
    "property_type_original",
    "project_name",

    # Price and size
    "price_usd",
    "size_m2",
    "price_per_m2",
    "price_original",

    # Property features
    "bedrooms",
    "bathrooms",
    "unit_floor",
    "building_total_floors",
    "bedroom_options",
    "multi_unit_options",

    # Location
    "city",
    "district",
    "commune",
    "address",
    "location_text",
    "latitude",
    "longitude",

    # Dates
    "listing_created_at",
    "listing_updated_at",
    "scraped_at",

    # Cleaning result
    "record_status",
    "needs_manual_review",
    "review_reason",
    "reject_reason",
    "duplicate_group_id",
    "duplicate_reason",
    "cleaning_notes",

    # Field origins
    "price_usd_source",
    "size_m2_source",
    "bedrooms_source",
    "bathrooms_source",
    "unit_floor_source",
    "building_total_floors_source",
    "district_source",
    "listing_type_source",
    "property_type_source",
]


DISTRICT_MAP = {
    # Boeung Keng Kang
    "bkk": "Boeung Keng Kang",
    "bkk1": "Boeung Keng Kang",
    "bkk 1": "Boeung Keng Kang",
    "boeng keng kang": "Boeung Keng Kang",
    "boeung keng kang": "Boeung Keng Kang",

    # Chamkarmon
    "chamkar mon": "Chamkarmon",
    "chamkarmon": "Chamkarmon",

    # Chbar Ampov
    "chbar ampov": "Chbar Ampov",
    "chbar ampo": "Chbar Ampov",

    # Chroy Changvar
    "chroy changvar": "Chroy Changvar",
    "chraoy changvar": "Chroy Changvar",
    "chroy chongvar": "Chroy Changvar",

    # Daun Penh
    "daun penh": "Daun Penh",
    "doun penh": "Daun Penh",

    # Kamboul
    "kamboul": "Kamboul",

    # Meanchey
    "mean chey": "Meanchey",
    "meanchey": "Meanchey",
    "meanchey": "Meanchey",

    # Prampi Makara
    "7 makara": "Prampi Makara",
    "7makara": "Prampi Makara",
    "prampi makara": "Prampi Makara",
    "prampir meakkakra": "Prampi Makara",

    # Pur Senchey
    "por sen chey": "Pur Senchey",
    "pou senchey": "Pur Senchey",
    "pur senchey": "Pur Senchey",
    "porsenchey": "Pur Senchey",

    # Russey Keo
    "russey keo": "Russey Keo",
    "ruessei kaev": "Russey Keo",

    # Sen Sok
    "sen sok": "Sen Sok",
    "saen sokh": "Sen Sok",
    "sensok": "Sen Sok",

    # Toul Kork
    "toul kork": "Toul Kork",
    "tuol kork": "Toul Kork",
    "tuol kouk": "Toul Kork",
}


def is_missing(value: Any) -> bool:
    """Return True when a value should be treated as missing."""

    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0

    return False


def clean_text(value: Any) -> str | None:
    """Clean whitespace while preserving Khmer and Unicode text."""

    if is_missing(value):
        return None

    text = str(value)

    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\ufeff", "")

    text = re.sub(r"\s+", " ", text).strip()

    return text or None


def safe_float(value: Any) -> float | None:
    """Convert a value to float without raising an error."""

    if is_missing(value):
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()

    text = text.replace("$", "")
    text = text.replace(",", "")
    text = text.replace("USD", "")
    text = text.replace("usd", "")
    text = text.strip()

    match = re.search(r"-?\d+(?:\.\d+)?", text)

    if not match:
        return None

    try:
        return float(match.group())
    except ValueError:
        return None


def safe_int(value: Any) -> int | None:
    """Convert a value to integer when possible."""

    number = safe_float(value)

    if number is None:
        return None

    if not number.is_integer():
        return None

    return int(number)


def normalize_url(value: Any) -> str | None:
    """
    Remove URL query parameters and fragments.

    Example:
    https://example.com/property/1/?utm_source=x#top

    becomes:
    https://example.com/property/1
    """

    text = clean_text(value)

    if text is None:
        return None

    try:
        parts = urlsplit(text)
    except ValueError:
        return text

    path = parts.path.rstrip("/")

    normalized = urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            path,
            "",
            "",
        )
    )

    return normalized or text


def normalize_listing_type(value: Any) -> str | None:
    """Standardize sale and rent labels."""

    text = clean_text(value)

    if text is None:
        return None

    lowered = text.lower()

    sale_words = {
        "sale",
        "for sale",
        "sell",
        "buy",
    }

    rent_words = {
        "rent",
        "for rent",
        "rental",
        "lease",
    }

    sale_rent_words = {
        "sale/rent",
        "sale & rent",
        "sale and rent",
        "for sale or rent",
        "for sale and rent",
    }

    if lowered in sale_rent_words:
        return "sale/rent"

    if lowered in sale_words:
        return "sale"

    if lowered in rent_words:
        return "rent"

    has_sale = bool(
        re.search(r"\b(?:sale|sell|buy)\b", lowered)
    )

    has_rent = bool(
        re.search(r"\b(?:rent|rental|lease)\b", lowered)
    )

    if has_sale and has_rent:
        return "sale/rent"

    if has_sale:
        return "sale"

    if has_rent:
        return "rent"

    return lowered


def normalize_property_type_label(
    value: Any,
) -> str | None:
    """
    Standardize spelling only.

    This function does not automatically convert Apartment,
    Studio or Project to Condo. That decision is source-specific.
    """

    text = clean_text(value)

    if text is None:
        return None

    lowered = text.lower()

    mapping = {
        "condo": "Condo",
        "condominium": "Condo",
        "penthouse": "Penthouse",
        "studio": "Studio",
        "apartment": "Apartment",
        "serviced apartment": "Serviced Apartment",
        "project": "Project",
        "house": "House",
        "villa": "Villa",
        "land": "Land",
        "commercial": "Commercial",
        "office": "Commercial",
        "flat": "Flat",
    }

    return mapping.get(lowered, text.title())


def normalize_district(value: Any) -> str | None:
    """Convert district spelling variants to one standard name."""

    text = clean_text(value)

    if text is None:
        return None

    key = text.lower()
    key = re.sub(r"\s+", " ", key).strip()

    return DISTRICT_MAP.get(key, text)


def calculate_price_per_m2(
    price_usd: Any,
    size_m2: Any,
) -> float | None:
    """Calculate USD price per square metre."""

    price = safe_float(price_usd)
    size = safe_float(size_m2)

    if price is None or size is None:
        return None

    if price <= 0 or size <= 0:
        return None

    return round(price / size, 2)


def add_reason(
    reasons: list[str],
    reason: str | None,
) -> None:
    """Add a reason once without duplicates."""

    if reason and reason not in reasons:
        reasons.append(reason)


def join_reasons(
    reasons: list[str],
) -> str | None:
    """Join a list of reasons for JSON and CSV output."""

    cleaned = [
        clean_text(reason)
        for reason in reasons
        if clean_text(reason)
    ]

    unique = list(dict.fromkeys(cleaned))

    return "; ".join(unique) if unique else None


def load_json_records(
    path: Path,
) -> list[dict[str, Any]]:
    """Load a JSON list containing dictionary records."""

    if not path.exists():
        raise FileNotFoundError(
            f"Input file was not found:\n{path}"
        )

    try:
        data = json.loads(
            path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid JSON in {path}:\n{error}"
        ) from error

    if not isinstance(data, list):
        raise TypeError(
            f"Expected a JSON list in:\n{path}"
        )

    records = [
        row
        for row in data
        if isinstance(row, dict)
    ]

    return records


def ensure_standard_columns(
    record: dict[str, Any],
) -> dict[str, Any]:
    """
    Return columns in the same order for every source.

    Extra source-specific columns are not included here.
    """

    return {
        column: record.get(column)
        for column in STANDARD_COLUMNS
    }


def save_json_records(
    records: list[dict[str, Any]],
    path: Path,
) -> None:
    """Save records as readable UTF-8 JSON."""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            records,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def serialize_csv_value(value: Any) -> Any:
    """Prepare nested values for CSV output."""

    if value is None:
        return ""

    if isinstance(value, (list, dict, tuple)):
        return json.dumps(
            value,
            ensure_ascii=False,
        )

    return value


def save_csv_records(
    records: list[dict[str, Any]],
    path: Path,
    columns: list[str] | None = None,
) -> None:
    """
    Save records using UTF-8 with BOM.

    UTF-8 with BOM helps Excel display Khmer text correctly.
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_columns = columns or STANDARD_COLUMNS

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=output_columns,
            extrasaction="ignore",
        )

        writer.writeheader()

        for record in records:
            row = {
                column: serialize_csv_value(
                    record.get(column)
                )
                for column in output_columns
            }

            writer.writerow(row)