#!/usr/bin/env python
"""
Recover property attributes from listing titles and descriptions.

Priority:
    1. Existing structured website value
    2. Listing title
    3. Listing description

The functions never overwrite an existing structured value.
They also record the source, matched text and possible conflicts.
"""

from __future__ import annotations

import re
from typing import Any, Callable


ExtractionResult = tuple[int, str] | None


# ======================================================================
# TEXT HELPERS
# ======================================================================

def clean_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return int(value)

    match = re.search(r"-?\d+", str(value))

    return int(match.group()) if match else None


def search_patterns(
    text: str,
    patterns: list[str],
    minimum: int,
    maximum: int,
) -> ExtractionResult:
    """
    Return:
        (value, matched_text)

    The first capture group containing a number is used.
    """
    if not text:
        return None

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if not match:
            continue

        value_text = next(
            (
                group
                for group in match.groups()
                if group is not None and str(group).isdigit()
            ),
            None,
        )

        if value_text is None:
            continue

        value = int(value_text)

        if minimum <= value <= maximum:
            return value, match.group(0)

    return None


# ======================================================================
# BEDROOM EXTRACTION
# ======================================================================

BEDROOM_PATTERNS = [
    # 2 Bedroom, 2-Bedroom, 2Beds, 4BR, 4 BDR
    r"(?<!\d)(\d{1,2})\s*[- ]?\s*(?:bed(?:room)?s?|br|bdr)\b",

    # Bedroom: 2, Bedrooms 2
    r"\b(?:bed(?:room)?s?)\s*[:\-]?\s*(\d{1,2})\b",

    # Khmer: 2 បន្ទប់គេង
    r"(?<!\d)(\d{1,2})\s*បន្ទប់គេង",

    # Khmer: បន្ទប់គេង 2
    r"បន្ទប់គេង\s*[:\-]?\s*(\d{1,2})",
]


def extract_bedrooms(text: Any) -> ExtractionResult:
    cleaned = clean_text(text)

    result = search_patterns(
        text=cleaned,
        patterns=BEDROOM_PATTERNS,
        minimum=0,
        maximum=15,
    )

    if result is not None:
        return result

    studio = re.search(r"\bstudio\b", cleaned, re.IGNORECASE)

    if studio:
        return 0, studio.group(0)

    return None


# ======================================================================
# BATHROOM EXTRACTION
# ======================================================================

BATHROOM_PATTERNS = [
    # 2 Bathroom, 2 Bathrooms, 2 Bath, 5Ba
    r"(?<!\d)(\d{1,2})\s*[- ]?\s*(?:bath(?:room)?s?|ba)\b",

    # Bathroom: 2, Bathrooms 2
    r"\b(?:bath(?:room)?s?)\s*[:\-]?\s*(\d{1,2})\b",

    # Khmer: 2 បន្ទប់ទឹក
    r"(?<!\d)(\d{1,2})\s*បន្ទប់ទឹក",

    # Khmer: បន្ទប់ទឹក 2
    r"បន្ទប់ទឹក\s*[:\-]?\s*(\d{1,2})",
]


def extract_bathrooms(text: Any) -> ExtractionResult:
    return search_patterns(
        text=clean_text(text),
        patterns=BATHROOM_PATTERNS,
        minimum=0,
        maximum=20,
    )


# ======================================================================
# UNIT FLOOR EXTRACTION
# ======================================================================

UNIT_FLOOR_PATTERNS = [
    # Located on the 15th floor
    r"\b(?:located|situated)\s+on\s+(?:the\s+)?"
    r"(\d{1,3})(?:st|nd|rd|th)?\s+floor\b",

    # Unit on the 15th floor
    r"\bunit\s+(?:is\s+)?(?:located\s+)?on\s+(?:the\s+)?"
    r"(\d{1,3})(?:st|nd|rd|th)?\s+floor\b",

    # On the 15th floor
    r"\bon\s+(?:the\s+)?"
    r"(\d{1,3})(?:st|nd|rd|th)?\s+floor\b",

    # 15th Floor
    r"\b(\d{1,3})(?:st|nd|rd|th)\s+floor\b",

    # Floor level: 15
    r"\bfloor\s+level\s*[:\-]\s*(\d{1,3})\b",

    # Unit floor: 15
    r"\bunit\s+floor\s*[:\-]\s*(\d{1,3})\b",

    # Level: 15
    r"\blevel\s*[:\-]\s*(\d{1,3})\b",

    # 31F
    r"\b(\d{1,3})\s*[Ff]\b",

    # Khmer: ជាន់ទី 15
    r"ជាន់ទី\s*(\d{1,3})",

    # Khmer: ជាន់ 15
    r"ជាន់\s*[:\-]?\s*(\d{1,3})",
]


def extract_unit_floor(text: Any) -> ExtractionResult:
    """
    Does not match expressions such as:

        2 Floors
        77 Stories High
        30-storey building

    Those do not identify the unit's floor.
    """
    return search_patterns(
        text=clean_text(text),
        patterns=UNIT_FLOOR_PATTERNS,
        minimum=1,
        maximum=100,
    )


# ======================================================================
# BUILDING TOTAL FLOORS
# ======================================================================

BUILDING_FLOOR_PATTERNS = [
    # 77 stories high
    r"\b(\d{1,3})\s*(?:storey|storeys|story|stories)\s+high\b",

    # 30-storey building
    r"\b(\d{1,3})\s*[- ]\s*(?:storey|storeys|story|stories)"
    r"\s+(?:building|tower)\b",

    # 30 floor building
    r"\b(\d{1,3})\s+floors?\s+(?:building|tower)\b",

    # Total floors: 30
    r"\btotal\s+floors?\s*[:\-]\s*(\d{1,3})\b",

    # Building has 30 floors
    r"\bbuilding\s+(?:has|with)\s+(\d{1,3})\s+floors?\b",

    # 30-storey tower
    r"\b(\d{1,3})\s*[- ]\s*(?:storey|storeys|story|stories)"
    r"\s+(?:tower|condominium|development)\b",
]


def extract_building_total_floors(text: Any) -> ExtractionResult:
    return search_patterns(
        text=clean_text(text),
        patterns=BUILDING_FLOOR_PATTERNS,
        minimum=1,
        maximum=150,
    )


# ======================================================================
# RECORD RECOVERY
# ======================================================================

def recover_field(
    record: dict[str, Any],
    field: str,
    extractor: Callable[[Any], ExtractionResult],
    title: str,
    description: str,
) -> None:
    """
    Fill one missing field from title or description.

    Existing values are preserved. When text disagrees with an existing
    value, a conflict column is added for later review.
    """
    existing = to_int(record.get(field))

    title_result = extractor(title)
    description_result = extractor(description)

    # ------------------------------------------------ existing value
    if existing is not None:
        record[field] = existing
        record.setdefault(f"{field}_source", "structured")

        conflicts: list[str] = []

        if title_result and title_result[0] != existing:
            conflicts.append(
                f"title={title_result[0]} from '{title_result[1]}'"
            )

        if description_result and description_result[0] != existing:
            conflicts.append(
                f"description={description_result[0]} "
                f"from '{description_result[1]}'"
            )

        if conflicts:
            record[f"{field}_conflict"] = "; ".join(conflicts)

        return

    # ------------------------------------------------ title first
    if title_result:
        value, matched_text = title_result

        record[field] = value
        record[f"{field}_source"] = "title"
        record[f"{field}_confidence"] = "high"
        record[f"{field}_text_raw"] = matched_text
        return

    # ------------------------------------------------ description second
    if description_result:
        value, matched_text = description_result

        record[field] = value
        record[f"{field}_source"] = "description"
        record[f"{field}_confidence"] = "medium"
        record[f"{field}_text_raw"] = matched_text


def recover_missing_fields(record: dict[str, Any]) -> dict[str, Any]:
    """
    Recover bedrooms, bathrooms, unit floor and building height.

    Structured values are never overwritten.
    """
    output = dict(record)

    title = clean_text(output.get("title"))
    description = clean_text(output.get("description"))

    recover_field(
        record=output,
        field="bedrooms",
        extractor=extract_bedrooms,
        title=title,
        description=description,
    )

    recover_field(
        record=output,
        field="bathrooms",
        extractor=extract_bathrooms,
        title=title,
        description=description,
    )

    recover_field(
        record=output,
        field="unit_floor",
        extractor=extract_unit_floor,
        title=title,
        description=description,
    )

    recover_field(
        record=output,
        field="building_total_floors",
        extractor=extract_building_total_floors,
        title=title,
        description=description,
    )

    return output