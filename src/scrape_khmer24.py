#!/usr/bin/env python
"""
scrape_khmer24.py - PP PropertyLens
===================================

Scrapes Phnom Penh condominium sale listings from khmer24.com.

WORKFLOW
--------
Phase 1:
    Search/scroll pages -> listing ID, URL, title, price, size, rooms,
    location, listing type.

Phase 2 (--details):
    Individual detail pages -> structured specifications, title,
    description/overview, rooms, unit floor, building floors, condition,
    posting time, and field provenance.

FIELD PRIORITY
--------------
    1. Search-card value
    2. Structured detail-page value
    3. Title
    4. Description / Overview
    5. Missing

Existing values are never silently overwritten. When sources disagree, the
record keeps the higher-priority value, stores the alternative value, and sets:

    needs_manual_review = True

FLOOR RULE
----------
    unit_floor             = floor of the advertised unit
    building_total_floors  = total floors/storeys of the building

A phrase such as "77-storey building" is never stored as unit_floor=77.

USAGE
-----
Inspect the first search batch:
    python src/scrape_khmer24.py --inspect

Collect all search results by scrolling:
    python src/scrape_khmer24.py --all

Reparse cached search HTML and rebuild raw JSON:
    python src/scrape_khmer24.py --from-cache --reset-output

Enrich the first 20 target records:
    python src/scrape_khmer24.py --details --limit 20

Reparse the first 20 cached detail pages:
    python src/scrape_khmer24.py --details --from-cache --limit 20

Enrich all target records:
    python src/scrape_khmer24.py --details

Rebuild search and detail data entirely from cache:
    python src/scrape_khmer24.py --details --from-cache --reset-output

OUTPUT
------
    data/bronze/khmer24/html/search_0001.html
    data/bronze/khmer24/html/detail_<listing_id>.html
    data/bronze/khmer24/raw_listings.json
    data/bronze/khmer24/scrape_log.json
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urljoin

# -----------------------------------------------------------------------
# Make config/settings.py importable
# -----------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
sys.path.insert(0, str(CONFIG_DIR))

import settings  # noqa: E402
import requests  # noqa: E402

try:
    from bs4 import BeautifulSoup, Tag
except ImportError:
    print("Missing dependency. Run: pip install beautifulsoup4")
    sys.exit(1)


# =======================================================================
# CONFIGURATION
# =======================================================================

SEARCH_PATH = "c-condo-for-sale"
SEARCH_PARAMS = "province=phnom-penh"
DEFAULT_LANG = "en"
SITE_ROOT = "https://www.khmer24.com"

HTML_DIR = settings.K24_HTML_DIR
OUT_JSON = settings.K24_RAW_JSON
LOG_JSON = HTML_DIR.parent / "scrape_log.json"

LISTING_URL_RE = re.compile(r"-adid-(\d+)", re.IGNORECASE)

LANG = DEFAULT_LANG

KHMER_DISTRICT = {
    "ទួលគោក": "Toul Kork",
    "សែនសុខ": "Sen Sok",
    "បឹងកេងកង": "Boeung Keng Kang",
    "ចំការមន": "Chamkarmon",
    "ដូនពេញ": "Daun Penh",
    "មានជ័យ": "Meanchey",
    "ជ្រោយចង្វារ": "Chroy Changvar",
    "ឫស្សីកែវ": "Russey Keo",
    "ច្បារអំពៅ": "Chbar Ampov",
    "ព្រែកព្នៅ": "Prek Pnov",
    "ដង្កោ": "Dangkao",
    "ពោធិ៍សែនជ័យ": "Pur Senchey",
    "៧មករា": "Prampi Makara",
    "៧ មករា": "Prampi Makara",
    "ប្រាំពីរមករា": "Prampi Makara",
    "កំបូល": "Kamboul",
}

ENGLISH_DISTRICT = {
    "Saensokh": "Sen Sok",
    "Sen Sok": "Sen Sok",
    "Sensok": "Sen Sok",
    "Tuol Kouk": "Toul Kork",
    "Toul Kork": "Toul Kork",
    "Boeng Keng Kang": "Boeung Keng Kang",
    "Boeung Keng Kang": "Boeung Keng Kang",
    "Chamkar Mon": "Chamkarmon",
    "Chamkarmon": "Chamkarmon",
    "Mean Chey": "Meanchey",
    "Meanchey": "Meanchey",
    "Doun Penh": "Daun Penh",
    "Daun Penh": "Daun Penh",
    "Chraoy Chongvar": "Chroy Changvar",
    "Chroy Changvar": "Chroy Changvar",
    "Ruessei Kaev": "Russey Keo",
    "Russey Keo": "Russey Keo",
    "Chbar Ampov": "Chbar Ampov",
    "Praek Pnov": "Prek Pnov",
    "Prek Pnov": "Prek Pnov",
    "Dangkao": "Dangkao",
    "Pou Senchey": "Pur Senchey",
    "Pur Senchey": "Pur Senchey",
    "Prampir Meakkakra": "Prampi Makara",
    "Prampi Makara": "Prampi Makara",
    "Kamboul": "Kamboul",
}

PHNOM_PENH = {"ភ្នំពេញ", "phnom penh", "phnompenh"}

SALE_WORDS = {"លក់", "sale", "for sale"}
RENT_WORDS = {"ជួល", "rent", "for rent"}

SPEC_LABELS = {
    # English
    "type": "property_type_raw",
    "property type": "property_type_raw",
    "size": "size_m2",
    "floor area": "size_m2",
    "bedroom": "bedrooms",
    "bedrooms": "bedrooms",
    "bathroom": "bathrooms",
    "bathrooms": "bathrooms",
    "floor": "unit_floor",
    "floor level": "unit_floor",
    "unit floor": "unit_floor",
    "total floors": "building_total_floors",
    "building floors": "building_total_floors",
    "number of floors": "building_total_floors",
    "condition": "condition",
    # Khmer
    "ប្រភេទ": "property_type_raw",
    "ទំហំ": "size_m2",
    "បន្ទប់គេង": "bedrooms",
    "បន្ទប់ទឹក": "bathrooms",
    "ជាន់": "unit_floor",
    "ចំនួនជាន់": "building_total_floors",
    "លក្ខខណ្ឌ": "condition",
}

DESCRIPTION_HEADINGS = {
    "description",
    "property description",
    "overview",
    "property overview",
    "about this property",
    "about the property",
    "details",
    "property details",
    "ពិពណ៌នា",
    "ព័ត៌មានលម្អិត",
}

PROPERTY_TYPE_PATTERNS = [
    ("Condo", ("condo", "condominium", "ខុនដូ")),
    ("Apartment", ("apartment", "អាផាតមិន")),
    ("Penthouse", ("penthouse",)),
    ("House", ("house", "villa", "ផ្ទះ", "វីឡា")),
    ("Commercial", ("commercial", "office", "shop", "warehouse")),
    ("Land", ("land", "ដី")),
]

WORD_NUMBERS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
}

DETAIL_SOURCE_PRIORITY = {
    "detail_structured": 3,
    "title": 2,
    "description": 1,
}


# =======================================================================
# GENERAL HELPERS
# =======================================================================

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""

    text = html_lib.unescape(str(value))
    text = re.sub(r"[\u200b\u200c\u200d\ufeff\u00a0]+", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def search_url(page_num: int) -> str:
    url = f"{SITE_ROOT}/{LANG}/{SEARCH_PATH}"
    params = [SEARCH_PARAMS] if SEARCH_PARAMS else []

    if page_num > 1:
        params.append(f"page={page_num}")

    return url + ("?" + "&".join(params) if params else "")


def search_path(page_num: int) -> Path:
    return HTML_DIR / f"search_{page_num:04d}.html"


def detail_path(listing_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", listing_id)
    return HTML_DIR / f"detail_{safe_id}.html"


def polite_sleep() -> None:
    delay = float(settings.REQUEST_DELAY_SECONDS)
    time.sleep(delay + random.uniform(0, 1.0))


def parse_price(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None

    text = clean_text(value)
    low = text.lower()

    if not text or "negotiab" in low or low in {"poa", "p.o.a.", "n/a", "-", ""}:
        return None

    compact = text.replace(",", "").replace(" ", "")
    multiplier = 1

    if re.search(r"\d(?:\.\d+)?[kK]\b", compact) or compact.lower().endswith("k"):
        multiplier = 1_000
    elif compact.lower().endswith("m"):
        multiplier = 1_000_000

    match = re.search(r"(\d+(?:\.\d+)?)", compact)

    if not match:
        return None

    amount = float(match.group(1)) * multiplier

    return int(amount) if amount > 0 else None


def parse_size(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return round(float(value), 2) if value > 0 else None

    text = clean_text(value).lower().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)", text)

    if not match:
        return None

    number = float(match.group(1))

    if any(unit in text for unit in ("sqft", "sq ft", "ft2", "ft²")):
        number *= 0.092903

    return round(number, 2) if number > 0 else None


def parse_int(value: Any) -> int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return int(value)

    match = re.search(r"-?\d+", clean_text(value))

    return int(match.group()) if match else None


def value_missing(value: Any) -> bool:
    return value in (None, "", [], {})


def merge_nonempty(
    base: dict[str, Any],
    updates: dict[str, Any],
    *,
    overwrite_fields: set[str] | None = None,
) -> dict[str, Any]:
    overwrite_fields = overwrite_fields or set()
    merged = dict(base)

    for key, value in updates.items():
        if value_missing(value):
            continue

        if key in overwrite_fields or value_missing(merged.get(key)):
            merged[key] = value

    return merged


def values_differ(field: str, left: Any, right: Any) -> bool:
    if field == "size_m2":
        try:
            return abs(float(left) - float(right)) > 0.5
        except (TypeError, ValueError):
            return clean_text(left).lower() != clean_text(right).lower()

    if field in {
        "bedrooms",
        "bathrooms",
        "unit_floor",
        "building_total_floors",
    }:
        return parse_int(left) != parse_int(right)

    return clean_text(left).lower() != clean_text(right).lower()


def append_conflict(
    record: dict[str, Any],
    field: str,
    message: str,
) -> None:
    key = f"{field}_conflict"
    previous = clean_text(record.get(key))

    existing_messages = [
        part.strip()
        for part in previous.split(";")
        if part.strip()
    ]

    new_messages = [
        part.strip()
        for part in clean_text(message).split(";")
        if part.strip()
    ]

    for message_part in new_messages:
        if message_part not in existing_messages:
            existing_messages.append(message_part)

    record[key] = "; ".join(existing_messages)
    record["needs_manual_review"] = True


def normalize_property_type(value: Any) -> str | None:
    text = clean_text(value).lower()

    if not text:
        return None

    for normalized, patterns in PROPERTY_TYPE_PATTERNS:
        if any(pattern in text for pattern in patterns):
            return normalized

    return clean_text(value)[:100] or None


# =======================================================================
# LOCATION AND LISTING TYPE
# =======================================================================

_PROVINCES = [
    "ភ្នំពេញ",
    "Phnom Penh",
    "សៀមរាប",
    "Siem Reap",
    "កណ្តាល",
    "Kandal",
    "ព្រះសីហនុ",
    "Preah Sihanouk",
    "Sihanoukville",
    "បាត់ដំបង",
    "Battambang",
    "កំពត",
    "Kampot",
]


def _build_location_regex() -> re.Pattern[str]:
    names = (
        list(KHMER_DISTRICT.keys())
        + list(set(KHMER_DISTRICT.values()))
        + list(ENGLISH_DISTRICT.keys())
        + list(set(ENGLISH_DISTRICT.values()))
    )

    names.sort(key=len, reverse=True)

    districts = "|".join(re.escape(name) for name in names)
    provinces = "|".join(
        re.escape(province)
        for province in sorted(_PROVINCES, key=len, reverse=True)
    )

    return re.compile(rf"({districts})\s*,\s*({provinces})", re.IGNORECASE)


LOC_KNOWN_RE = _build_location_regex()
LOC_KHMER_RE = re.compile(
    r"([\u1780-\u17FF]{2,})\s*,\s*([\u1780-\u17FF]{2,})"
)
LOC_LATIN_RE = re.compile(
    r"\b([A-Z][A-Za-z]*(?:\s+[A-Za-z]+){0,2})\s*,\s*"
    r"(Phnom Penh|Siem Reap|Sihanoukville|Battambang|Kandal|"
    r"Kampot|Preah Sihanouk)\b",
    re.IGNORECASE,
)


def find_location(text: str) -> str | None:
    for pattern in (LOC_KNOWN_RE, LOC_KHMER_RE, LOC_LATIN_RE):
        matches = list(pattern.finditer(text))

        if matches:
            return clean_text(matches[-1].group(0))

    return None


def map_district(raw: str | None) -> tuple[str | None, str | None]:
    if not raw:
        return None, None

    parts = [
        part.strip()
        for part in clean_text(raw).split(",")
        if part.strip()
    ]

    if not parts:
        return None, None

    district_raw = parts[0]
    province_raw = parts[1] if len(parts) > 1 else None

    lookup = {
        key.replace(" ", "").lower(): value
        for key, value in {
            **KHMER_DISTRICT,
            **ENGLISH_DISTRICT,
        }.items()
    }

    district = lookup.get(
        district_raw.replace(" ", "").lower(),
        district_raw,
    )

    province_clean = clean_text(province_raw).lower()

    province = (
        "Phnom Penh"
        if province_clean in PHNOM_PENH
        else province_raw
    )

    return district, province


def listing_type_of(text: str) -> str | None:
    cleaned = clean_text(text)
    low = cleaned.lower()

    has_sale = any(word in cleaned or word in low for word in SALE_WORDS)
    has_rent = any(word in cleaned or word in low for word in RENT_WORDS)

    if has_sale and has_rent:
        return "sale/rent"

    if has_sale:
        return "sale"

    if has_rent:
        return "rent"

    return None


def is_target_listing(record: dict[str, Any]) -> bool:
    return (
        record.get("province") == "Phnom Penh"
        and record.get("listing_type") in {"sale", "sale/rent"}
    )


# =======================================================================
# SAFE TEXT FIELD RECOVERY
# =======================================================================

ExtractionResult = tuple[int, str] | None


def search_patterns(
    text: Any,
    patterns: Iterable[str],
    minimum: int,
    maximum: int,
) -> ExtractionResult:
    cleaned = clean_text(text)

    if not cleaned:
        return None

    for pattern in patterns:
        match = re.search(pattern, cleaned, re.IGNORECASE)

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
            return value, clean_text(match.group(0))

    return None


BEDROOM_PATTERNS = [
    r"\b(?:bed(?:room)?s?)\s*[:\-]\s*(\d{1,2})\b",
    r"(?<!\d)(\d{1,2})\s*[- ]?\s*(?:bed(?:room)?s?|br|bdr)\b",
    r"\b(?:bed(?:room)?s?)\s+(\d{1,2})\b",
    r"(?<!\d)(\d{1,2})\s*បន្ទប់គេង",
    r"បន្ទប់គេង\s*[:\-]?\s*(\d{1,2})",
]

BATHROOM_PATTERNS = [
    r"\b(?:bath(?:room)?s?)\s*[:\-]\s*(\d{1,2})\b",
    r"(?<!\d)(\d{1,2})\s*[- ]?\s*(?:bath(?:room)?s?|ba)\b",
    r"\b(?:bath(?:room)?s?)\s+(\d{1,2})\b",
    r"(?<!\d)(\d{1,2})\s*បន្ទប់ទឹក",
    r"បន្ទប់ទឹក\s*[:\-]?\s*(\d{1,2})",
]

UNIT_FLOOR_PATTERNS = [
    r"\b(?:located|situated)\s+on\s+(?:the\s+)?"
    r"(\d{1,3})(?:st|nd|rd|th)?\s+floor\b",
    r"\bunit\s+(?:is\s+)?(?:located\s+)?on\s+(?:the\s+)?"
    r"(\d{1,3})(?:st|nd|rd|th)?\s+floor\b",
    r"\bon\s+(?:the\s+)?"
    r"(\d{1,3})(?:st|nd|rd|th)?\s+floor\b",
    r"\b(\d{1,3})(?:st|nd|rd|th)\s+floor\b",
    r"\bfloor\s+level\s*[:\-]?\s*"
    r"(\d{1,3})(?:st|nd|rd|th)?\b",
    r"\bunit\s+floor\s*[:\-]?\s*"
    r"(\d{1,3})(?:st|nd|rd|th)?\b",
    r"\bfloor\s*[:\-]\s*(\d{1,3})(?:st|nd|rd|th)?\b",
    r"\blevel\s*[:\-]\s*(\d{1,3})\b",
    r"\bunit\s+(\d{1,3})\s*[Ff]\b",
    r"(?:ជាន់ទី|ជានទី)\s*(\d{1,3})",
    r"ជាន់\s*[:\-]?\s*(\d{1,3})",
]

BUILDING_FLOOR_PATTERNS = [
    r"\b(\d{1,3})\s*(?:storey|storeys|story|stories)\s+high\b",
    r"\b(\d{1,3})\s*[- ]\s*(?:storey|storeys|story|stories)"
    r"\s+(?:building|tower|condominium|development)\b",
    r"\b(\d{1,3})\s+floors?\s+(?:building|tower)\b",
    r"\btotal\s+floors?\s*[:\-]?\s*(\d{1,3})\b",
    r"\bbuilding\s+(?:has|with)\s+(\d{1,3})\s+floors?\b",
    r"អគារ(?:មាន)?\s*(\d{1,3})\s*ជាន់",
]


def extract_bedrooms(text: Any) -> ExtractionResult:
    result = search_patterns(text, BEDROOM_PATTERNS, 0, 15)

    if result is not None:
        return result

    cleaned = clean_text(text)
    words = "|".join(WORD_NUMBERS)

    spelled = re.search(
        rf"\b({words})\s*[- ]?\s*(?:bed(?:room)?s?|br)\b",
        cleaned,
        re.IGNORECASE,
    )

    if spelled:
        return WORD_NUMBERS[spelled.group(1).lower()], clean_text(spelled.group(0))

    studio = re.search(r"\bstudio\b", cleaned, re.IGNORECASE)

    if studio:
        return 0, clean_text(studio.group(0))

    return None


def extract_bathrooms(text: Any) -> ExtractionResult:
    result = search_patterns(text, BATHROOM_PATTERNS, 0, 20)

    if result is not None:
        return result

    words = "|".join(WORD_NUMBERS)

    spelled = re.search(
        rf"\b({words})\s*[- ]?\s*(?:bath(?:room)?s?)\b",
        clean_text(text),
        re.IGNORECASE,
    )

    if spelled:
        return WORD_NUMBERS[spelled.group(1).lower()], clean_text(spelled.group(0))

    return None


def extract_unit_floor(text: Any) -> ExtractionResult:
    return search_patterns(text, UNIT_FLOOR_PATTERNS, 1, 100)


def extract_building_total_floors(text: Any) -> ExtractionResult:
    return search_patterns(text, BUILDING_FLOOR_PATTERNS, 1, 150)


def candidate_is_valid(field: str, value: Any) -> bool:
    """Apply conservative ranges to fields commonly corrupted by stray IDs."""
    if value_missing(value):
        return False

    parsed = parse_int(value)

    if field == "bedrooms":
        return parsed is not None and 0 <= parsed <= 15

    if field == "bathrooms":
        return parsed is not None and 0 <= parsed <= 20

    if field == "unit_floor":
        return parsed is not None and 1 <= parsed <= 100

    if field == "building_total_floors":
        return parsed is not None and 1 <= parsed <= 150

    return True


def apply_detail_candidate(
    base_record: dict[str, Any],
    updates: dict[str, Any],
    field: str,
    value: Any,
    source: str = "detail_structured",
    confidence: str = "high",
) -> None:
    """
    Fill a missing search-card field from a structured detail value.

    Search-card values are preserved. Disagreements are retained as
    <field>_detail_value and flagged for manual review.
    """
    if value_missing(value):
        return

    if not candidate_is_valid(field, value):
        updates[f"{field}_invalid_value"] = value
        updates[f"{field}_invalid_source"] = source
        append_conflict(
            updates,
            field,
            f"invalid {source}={value}",
        )
        return

    existing = base_record.get(field)

    if value_missing(existing):
        current_update = updates.get(field)

        if value_missing(current_update):
            updates[field] = value
            updates[f"{field}_source"] = source
            updates[f"{field}_confidence"] = confidence
            return

        if values_differ(field, current_update, value):
            updates[f"{field}_detail_value"] = value
            updates[f"{field}_detail_source"] = source
            append_conflict(
                updates,
                field,
                f"{source}={value}; kept {updates.get(f'{field}_source')}="
                f"{current_update}",
            )

        return

    if values_differ(field, existing, value):
        updates[f"{field}_detail_value"] = value
        updates[f"{field}_detail_source"] = source
        append_conflict(
            updates,
            field,
            f"{source}={value}; kept search value={existing}",
        )


def apply_text_candidate(
    record: dict[str, Any],
    field: str,
    extractor: Callable[[Any], ExtractionResult],
    title: str,
    description: str,
) -> None:
    existing = parse_int(record.get(field))
    title_result = extractor(title)
    description_result = extractor(description)

    if title_result:
        record[f"{field}_title_value"] = title_result[0]

    if description_result:
        record[f"{field}_description_value"] = description_result[0]

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
            append_conflict(record, field, "; ".join(conflicts))

        return

    if title_result:
        value, matched = title_result
        record[field] = value
        record[f"{field}_source"] = "title"
        record[f"{field}_confidence"] = "high"
        record[f"{field}_text_raw"] = matched
        return

    if description_result:
        value, matched = description_result
        record[field] = value
        record[f"{field}_source"] = "description"
        record[f"{field}_confidence"] = "medium"
        record[f"{field}_text_raw"] = matched


def recover_missing_fields(record: dict[str, Any]) -> dict[str, Any]:
    output = dict(record)
    title = clean_text(output.get("title"))
    description = clean_text(output.get("description"))

    apply_text_candidate(
        output,
        "bedrooms",
        extract_bedrooms,
        title,
        description,
    )
    apply_text_candidate(
        output,
        "bathrooms",
        extract_bathrooms,
        title,
        description,
    )
    apply_text_candidate(
        output,
        "unit_floor",
        extract_unit_floor,
        title,
        description,
    )
    apply_text_candidate(
        output,
        "building_total_floors",
        extract_building_total_floors,
        title,
        description,
    )

    return output


# =======================================================================
# FETCHING
# =======================================================================

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": settings.USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9,km;q=0.8",
    }
)

_BROWSER_CTX: dict[str, Any] = {}


def fetch(url: str, use_browser: bool = False) -> str | None:
    if use_browser:
        return fetch_with_browser(url)

    for attempt in range(1, settings.MAX_RETRIES + 1):
        try:
            response = SESSION.get(
                url,
                timeout=settings.REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                return response.text

            print(
                f"HTTP {response.status_code}",
                end=" ",
                flush=True,
            )

        except Exception as exc:
            print(
                f"retry {attempt} ({type(exc).__name__})",
                end=" ",
                flush=True,
            )

        time.sleep(3 * attempt)

    return None


def fetch_with_browser(url: str) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "\nPlaywright not installed. Run:\n"
            "    pip install playwright\n"
            "    playwright install chromium"
        )
        sys.exit(1)

    if "page" not in _BROWSER_CTX:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=settings.USER_AGENT,
            viewport={"width": 1400, "height": 1000},
            locale="en-US",
        )

        _BROWSER_CTX.update(
            {
                "playwright": playwright,
                "browser": browser,
                "context": context,
                "page": context.new_page(),
            }
        )

    page = _BROWSER_CTX["page"]

    try:
        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=settings.REQUEST_TIMEOUT * 1000,
        )
        page.wait_for_timeout(2500)
        page.mouse.wheel(0, 6000)
        page.wait_for_timeout(1500)

        return page.content()

    except Exception as exc:
        print(
            f"browser failed ({type(exc).__name__})",
            end=" ",
            flush=True,
        )
        return None


def close_browser() -> None:
    if "browser" in _BROWSER_CTX:
        _BROWSER_CTX["browser"].close()

    if "playwright" in _BROWSER_CTX:
        _BROWSER_CTX["playwright"].stop()

    _BROWSER_CTX.clear()


# =======================================================================
# PHASE 1 - SEARCH-PAGE PARSING
# =======================================================================

def collapse_card_title(text: str, location_raw: str | None) -> str | None:
    title = text

    if location_raw:
        title = text.split(location_raw)[0]

    title = clean_text(title)

    duplicate = re.match(
        r"^(.{6,}?)\s+\d{1,3}\s+\1(?:\s|$)",
        title,
    )

    if duplicate:
        title = duplicate.group(1)
    else:
        plain_duplicate = re.match(
            r"^(.{6,}?)\s+\1(?:\s|$)",
            title,
        )

        if plain_duplicate:
            title = plain_duplicate.group(1)

    title = re.sub(r"^\s*\d{1,3}\s+", "", title)
    title = re.sub(r"\s+\d{1,3}\s*$", "", title)

    title = clean_text(title)

    return title[:300] or None


def parse_search_page(html: str, page_num: int) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    seen: dict[str, dict[str, Any]] = {}

    for anchor in soup.find_all("a", href=True):
        href = clean_text(anchor.get("href"))
        match = LISTING_URL_RE.search(href)

        if not match:
            continue

        listing_id = match.group(1)

        if listing_id in seen:
            continue

        url = urljoin(SITE_ROOT, href)
        card_text = clean_text(anchor.get_text(" ", strip=True))

        if not card_text:
            continue

        prices = re.findall(
            r"\$\s?[\d,]+(?:\.\d+)?\s?[KkMm]?",
            card_text,
        )
        price = parse_price(prices[-1]) if prices else None

        size_match = re.search(
            r"([\d.,]+)\s*(?:m[²2]|sqm|sq\.?\s*m)",
            card_text,
            re.IGNORECASE,
        )
        size = parse_size(size_match.group(1)) if size_match else None

        bedroom_result = extract_bedrooms(card_text)
        bathroom_result = extract_bathrooms(card_text)

        location_raw = find_location(card_text)
        district, province = map_district(location_raw)

        if province is None:
            province = "Phnom Penh"
            province_source = "search_filter"
        else:
            province_source = "card_location"

        detected_listing_type = listing_type_of(card_text)

        if detected_listing_type is None:
            detected_listing_type = "sale"
            listing_type_source = "search_category"
        else:
            listing_type_source = "card_text"

        title = collapse_card_title(card_text, location_raw)

        record: dict[str, Any] = {
            "listing_id": listing_id,
            "source": "khmer24.com",
            "source_page": page_num,
            "listing_type": detected_listing_type,
            "listing_type_source": listing_type_source,

            "price_usd": price,
            "size_m2": size,
            "bedrooms": bedroom_result[0] if bedroom_result else None,
            "bathrooms": bathroom_result[0] if bathroom_result else None,
            "unit_floor": None,
            "building_total_floors": None,

            "property_type": "Condo",
            "property_type_source": "search_category",
            "property_type_raw": None,

            "district": district,
            "province": province,
            "province_source": province_source,
            "commune": None,
            "address": location_raw,
            "latitude": None,
            "longitude": None,

            "project_name": None,
            "title": title,
            "created_at": None,
            "description": None,
            "description_source": None,
            "condition": None,

            "card_text": card_text[:1000],
            "url": url,

            "bedrooms_source": (
                "search_card_text" if bedroom_result else None
            ),
            "bedrooms_confidence": (
                "medium" if bedroom_result else None
            ),
            "bedrooms_text_raw": (
                bedroom_result[1] if bedroom_result else None
            ),
            "bathrooms_source": (
                "search_card_text" if bathroom_result else None
            ),
            "bathrooms_confidence": (
                "medium" if bathroom_result else None
            ),
            "bathrooms_text_raw": (
                bathroom_result[1] if bathroom_result else None
            ),

            "detail_scraped": False,
            "scraped_at": now_iso(),
        }

        seen[listing_id] = recover_missing_fields(record)

    return list(seen.values())


# =======================================================================
# PHASE 2 - DETAIL-PAGE PARSING
# =======================================================================

def extract_spec_pairs(soup: BeautifulSoup) -> dict[str, str]:
    specs: dict[str, str] = {}

    for dl in soup.find_all("dl"):
        dt = dl.find("dt")
        dd = dl.find("dd")

        if not dt or not dd:
            continue

        label = clean_text(
            dt.get_text(" ", strip=True)
        ).lower().rstrip(":")

        value = clean_text(
            dd.get_text(" ", strip=True)
        )

        column = SPEC_LABELS.get(label)

        if column and value:
            specs.setdefault(column, value)

    # Additional table/label-value layouts.
    for label_element in soup.select(
        "dt, th, [class*='label' i]"
    ):
        label = clean_text(
            label_element.get_text(" ", strip=True)
        ).lower().rstrip(":")

        column = SPEC_LABELS.get(label)

        if not column or column in specs:
            continue

        value_element = label_element.find_next_sibling()

        if value_element is None:
            continue

        value = clean_text(
            value_element.get_text(" ", strip=True)
        )

        if value:
            specs[column] = value

    return specs


def extract_title_from_soup(soup: BeautifulSoup) -> str | None:
    selectors = [
        "h1",
        "[class*='listing-title' i]",
        "[class*='property-title' i]",
        "meta[property='og:title']",
    ]

    for selector in selectors:
        element = soup.select_one(selector)

        if element is None:
            continue

        if element.name == "meta":
            text = clean_text(element.get("content"))
        else:
            text = clean_text(
                element.get_text(" ", strip=True)
            )

        if text:
            return text[:500]

    return None


def description_candidate_score(text: str, source: str) -> int:
    low = text.lower()
    score = 0

    if "overview" in source or "description" in source:
        score += 8

    if 100 <= len(text) <= 5000:
        score += 4

    property_words = (
        "bedroom",
        "bathroom",
        "floor",
        "condo",
        "apartment",
        "price",
        "size",
        "sqm",
        "m²",
        "បន្ទប់",
        "ជាន់",
        "ទំហំ",
    )

    score += min(
        sum(word in low for word in property_words),
        6,
    )

    noisy_words = (
        "privacy policy",
        "terms and conditions",
        "related ads",
        "download app",
        "follow us",
        "contact us",
    )

    score -= 4 * sum(word in low for word in noisy_words)

    return score


def extract_description_from_soup(
    soup: BeautifulSoup,
) -> tuple[str | None, str | None]:
    candidates: list[tuple[int, int, str, str]] = []

    selectors = [
        ("[id*='description' i]", "description_section"),
        ("[class*='description' i]", "description_section"),
        ("[id*='overview' i]", "overview_section"),
        ("[class*='overview' i]", "overview_section"),
        ("[id*='property-detail' i]", "property_details_section"),
        ("[class*='property-detail' i]", "property_details_section"),
        ("[id*='about-property' i]", "about_property_section"),
        ("[class*='about-property' i]", "about_property_section"),
    ]

    for selector, source in selectors:
        for element in soup.select(selector):
            text = clean_text(
                element.get_text(" ", strip=True)
            )

            if 80 <= len(text) <= 20_000:
                score = description_candidate_score(text, source)
                candidates.append(
                    (score, -len(text), text[:5000], source)
                )

    # Heading-based extraction.
    for heading in soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "strong"]
    ):
        heading_text = clean_text(
            heading.get_text(" ", strip=True)
        )
        normalized = heading_text.lower().strip(" :")

        if normalized not in DESCRIPTION_HEADINGS:
            continue

        collected: list[str] = []

        for sibling in heading.find_next_siblings():
            if Tag is not None and not isinstance(sibling, Tag):
                continue

            if sibling.name in {"h1", "h2", "h3", "h4", "h5"}:
                break

            text = clean_text(
                sibling.get_text(" ", strip=True)
            )

            if text:
                collected.append(text)

            if sum(len(item) for item in collected) >= 5000:
                break

        combined = clean_text(" ".join(collected))

        if len(combined) >= 80:
            source = (
                "overview_heading"
                if "overview" in normalized
                else "description_heading"
            )
            score = description_candidate_score(combined, source)
            candidates.append(
                (score, -len(combined), combined[:5000], source)
            )

    # JSON-LD fallback.
    for script in soup.select(
        "script[type='application/ld+json']"
    ):
        raw = script.string

        if not raw:
            continue

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        objects = data if isinstance(data, list) else [data]

        for item in objects:
            if not isinstance(item, dict):
                continue

            value = item.get("description")

            if isinstance(value, str):
                text = clean_text(value)

                if len(text) >= 80:
                    source = "json_ld_description"
                    score = description_candidate_score(text, source)
                    candidates.append(
                        (score, -len(text), text[:5000], source)
                    )

    # Meta fallback.
    meta = soup.select_one(
        "meta[name='description'], "
        "meta[property='og:description']"
    )

    if meta is not None:
        text = clean_text(meta.get("content"))

        if len(text) >= 80:
            source = "meta_description"
            score = description_candidate_score(text, source)
            candidates.append(
                (score, -len(text), text[:5000], source)
            )

    # Paragraph fallback. Do not automatically choose the longest paragraph.
    for paragraph in soup.find_all("p"):
        text = clean_text(
            paragraph.get_text(" ", strip=True)
        )

        if not 80 <= len(text) <= 5000:
            continue

        score = description_candidate_score(
            text,
            "paragraph_fallback",
        )

        if score >= 4:
            candidates.append(
                (
                    score,
                    -len(text),
                    text[:5000],
                    "paragraph_fallback",
                )
            )

    if not candidates:
        return None, None

    candidates.sort(
        key=lambda item: (item[0], item[1]),
        reverse=True,
    )

    _, _, description, source = candidates[0]

    return description, source


def extract_detail_price(soup: BeautifulSoup) -> int | None:
    selectors = [
        "[class*='price' i]",
        "meta[property='product:price:amount']",
        "meta[property='og:price:amount']",
    ]

    candidates: list[int] = []

    for selector in selectors:
        for element in soup.select(selector):
            if element.name == "meta":
                text = clean_text(element.get("content"))
            else:
                text = clean_text(
                    element.get_text(" ", strip=True)
                )

            for raw_price in re.findall(
                r"\$\s?[\d,]+(?:\.\d+)?\s?[KkMm]?",
                text,
            ):
                parsed = parse_price(raw_price)

                if parsed is not None:
                    candidates.append(parsed)

    return candidates[0] if candidates else None


def parse_detail_page(
    html: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    base = dict(record)
    updates: dict[str, Any] = {}

    specs = extract_spec_pairs(soup)

    apply_detail_candidate(
        base,
        updates,
        "size_m2",
        parse_size(specs.get("size_m2")),
    )
    apply_detail_candidate(
        base,
        updates,
        "bedrooms",
        parse_int(specs.get("bedrooms")),
    )
    apply_detail_candidate(
        base,
        updates,
        "bathrooms",
        parse_int(specs.get("bathrooms")),
    )
    apply_detail_candidate(
        base,
        updates,
        "unit_floor",
        parse_int(specs.get("unit_floor")),
    )
    apply_detail_candidate(
        base,
        updates,
        "building_total_floors",
        parse_int(specs.get("building_total_floors")),
    )

    if specs.get("condition"):
        updates["condition"] = specs["condition"]

    raw_property_type = specs.get("property_type_raw")

    if raw_property_type:
        detail_property_type = normalize_property_type(
            raw_property_type
        )

        updates["property_type_raw"] = raw_property_type
        updates["property_type_detail_value"] = detail_property_type

        existing_type = base.get("property_type")

        if value_missing(existing_type):
            updates["property_type"] = detail_property_type
            updates["property_type_source"] = "detail_structured"

        elif (
            detail_property_type
            and clean_text(existing_type).lower()
            != clean_text(detail_property_type).lower()
        ):
            append_conflict(
                updates,
                "property_type",
                f"detail_structured={detail_property_type}; "
                f"kept search category={existing_type}",
            )

    detail_title = extract_title_from_soup(soup)

    if detail_title:
        if clean_text(base.get("title")):
            updates["detail_title"] = detail_title

            if clean_text(base.get("title")).lower() != detail_title.lower():
                updates["title_changed_on_detail"] = True
        else:
            updates["title"] = detail_title

    description, description_source = (
        extract_description_from_soup(soup)
    )

    if description:
        updates["description"] = description
        updates["description_source"] = description_source

    # Detail-page price selectors can also contain related advertisements.
    # Use them only to fill a missing search-card price; never create a
    # conflict against an existing search price from this broad fallback.
    detail_price = extract_detail_price(soup)

    if value_missing(base.get("price_usd")) and detail_price is not None:
        updates["price_usd"] = detail_price
        updates["price_usd_source"] = "detail_page_price"
        updates["price_usd_confidence"] = "medium"

    time_element = soup.find("time")

    if time_element is not None:
        datetime_value = time_element.get("datetime")

        if datetime_value:
            updates["created_at"] = clean_text(datetime_value)

    overwrite_fields = {
        "description",
        "description_source",
        "condition",
        "property_type_raw",
        "property_type_detail_value",
        "detail_title",
        "title_changed_on_detail",
        "created_at",
        "detail_scraped",
        "detail_parsed_at",
        "needs_manual_review",
        "price_usd_detail_value",
        "size_m2_detail_value",
        "bedrooms_detail_value",
        "bathrooms_detail_value",
        "unit_floor_detail_value",
        "building_total_floors_detail_value",
        "property_type_conflict",
        "price_usd_conflict",
        "size_m2_conflict",
        "bedrooms_conflict",
        "bathrooms_conflict",
        "unit_floor_conflict",
        "building_total_floors_conflict",
    }

    merged = merge_nonempty(
        base,
        updates,
        overwrite_fields=overwrite_fields,
    )

    merged["detail_scraped"] = True
    merged["detail_parsed_at"] = now_iso()

    merged = recover_missing_fields(merged)

    unit_floor = parse_int(merged.get("unit_floor"))
    building_floors = parse_int(
        merged.get("building_total_floors")
    )

    if (
        unit_floor is not None
        and building_floors is not None
        and unit_floor > building_floors
    ):
        append_conflict(
            merged,
            "unit_floor",
            f"unit_floor={unit_floor} exceeds "
            f"building_total_floors={building_floors}",
        )

    return merged


# =======================================================================
# STORAGE AND SUMMARY
# =======================================================================

def load_existing() -> dict[str, dict[str, Any]]:
    if not OUT_JSON.exists():
        return {}

    try:
        records = json.loads(
            OUT_JSON.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(records, list):
        return {}

    return {
        str(record["listing_id"]): record
        for record in records
        if isinstance(record, dict)
        and record.get("listing_id")
    }


def save(store: dict[str, dict[str, Any]]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            list(store.values()),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def append_log(entry: dict[str, Any]) -> None:
    log: list[dict[str, Any]] = []

    if LOG_JSON.exists():
        try:
            loaded = json.loads(
                LOG_JSON.read_text(encoding="utf-8")
            )

            if isinstance(loaded, list):
                log = loaded

        except json.JSONDecodeError:
            log = []

    log.append(entry)
    LOG_JSON.parent.mkdir(parents=True, exist_ok=True)
    LOG_JSON.write_text(
        json.dumps(
            log,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def summarise(
    store: dict[str, dict[str, Any]],
    label: str = "",
) -> None:
    records = list(store.values())
    total = len(records)

    pp = [
        record
        for record in records
        if record.get("province") == "Phnom Penh"
    ]
    sale = [
        record
        for record in records
        if record.get("listing_type") in {"sale", "sale/rent"}
    ]
    target = [
        record
        for record in records
        if is_target_listing(record)
    ]
    usable = [
        record
        for record in target
        if record.get("price_usd") is not None
        and record.get("size_m2") is not None
    ]

    def present(field: str) -> int:
        return sum(
            not value_missing(record.get(field))
            for record in target
        )

    details = sum(
        bool(record.get("detail_scraped"))
        for record in target
    )
    descriptions = present("description")
    review = sum(
        bool(record.get("needs_manual_review"))
        for record in target
    )

    source_counts: dict[str, int] = {}

    for field in (
        "bedrooms",
        "bathrooms",
        "unit_floor",
        "building_total_floors",
    ):
        source_counts[field] = sum(
            record.get(f"{field}_source")
            in {"title", "description"}
            for record in target
        )

    print("\n" + "=" * 64)

    if label:
        print(f"  {label}")

    print(f"  total listings            : {total}")
    print(f"  in Phnom Penh             : {len(pp)}")
    print(f"  sale or sale/rent         : {len(sale)}")
    print(f"  Phnom Penh target         : {len(target)}")
    print(f"  detail pages parsed       : {details}")
    print(f"  usable (price + size)     : {len(usable)}")
    print(f"  with bedrooms             : {present('bedrooms')}")
    print(f"  with bathrooms            : {present('bathrooms')}")
    print(f"  with unit floor           : {present('unit_floor')}")
    print(
        f"  with building floors      : "
        f"{present('building_total_floors')}"
    )
    print(f"  with description/overview : {descriptions}")
    print(f"  flagged for review        : {review}")

    print("\n  recovered from title/description:")

    for field, count in source_counts.items():
        print(f"    {field:<26}{count:>6}")

    type_counts = Counter(
        record.get("property_type") or "MISSING"
        for record in target
    )

    print("\n  property types:")

    for property_type, count in type_counts.most_common():
        print(f"    {property_type:<26}{count:>6}")

    print(f"\n  saved to                  : {OUT_JSON}")
    print("=" * 64)


# =======================================================================
# MODES
# =======================================================================

def collect_by_scrolling(
    max_scrolls: int = 120,
    headful: bool = False,
    patience: int = 4,
) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "\nPlaywright is required for scrolling. Run:\n"
            "    pip install playwright\n"
            "    playwright install chromium\n"
        )
        return None

    HTML_DIR.mkdir(parents=True, exist_ok=True)
    url = search_url(1)

    print(f"\nScrolling {url}\n")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=not headful
        )
        context = browser.new_context(
            user_agent=settings.USER_AGENT,
            viewport={"width": 1400, "height": 1000},
            locale="en-US",
        )
        page = context.new_page()

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=settings.REQUEST_TIMEOUT * 1000,
        )
        page.wait_for_timeout(4000)

        seen = 0
        stalls = 0
        html = page.content()

        for step in range(1, max_scrolls + 1):
            page.keyboard.press("End")
            page.mouse.wheel(0, 25_000)
            page.wait_for_timeout(2200)

            for label in (
                "បន្ថែម",
                "Load more",
                "See more",
                "More",
            ):
                try:
                    button = page.get_by_text(
                        label,
                        exact=False,
                    ).first

                    if button.is_visible(timeout=400):
                        button.click(timeout=1500)
                        page.wait_for_timeout(2000)
                        break

                except Exception:
                    pass

            html = page.content()
            count = len(
                set(LISTING_URL_RE.findall(html))
            )

            if count > seen:
                print(
                    f"  scroll {step:>3}  "
                    f"{count} listings (+{count - seen})"
                )
                seen = count
                stalls = 0

            else:
                stalls += 1
                print(
                    f"  scroll {step:>3}  "
                    f"{count} listings "
                    f"(no change {stalls}/{patience})"
                )

                if stalls >= patience:
                    print("\n  No new listings - stopping.")
                    break

            if step % 10 == 0:
                search_path(step // 10).write_text(
                    html,
                    encoding="utf-8",
                )

        search_path(999).write_text(
            html,
            encoding="utf-8",
        )
        browser.close()

    print(f"\n  collected {seen} unique listing links")

    return html


def load_search_cache() -> list[tuple[int, str]]:
    files = sorted(HTML_DIR.glob("search_*.html"))

    pages: list[tuple[int, str]] = []

    for file in files:
        try:
            page_num = int(file.stem.split("_")[1])
        except (IndexError, ValueError):
            continue

        pages.append(
            (
                page_num,
                file.read_text(encoding="utf-8"),
            )
        )

    return pages


def build_store_from_search_pages(
    pages: list[tuple[int, str]],
) -> dict[str, dict[str, Any]]:
    store: dict[str, dict[str, Any]] = {}

    for page_num, html in pages:
        for record in parse_search_page(html, page_num):
            listing_id = str(record["listing_id"])
            existing = store.get(listing_id, {})

            store[listing_id] = merge_nonempty(
                existing,
                record,
                overwrite_fields=set(record.keys()),
            )

    return store


def run_inspect(use_browser: bool) -> None:
    print("\nINSPECT - downloading search page 1")
    print(f"  {search_url(1)}\n")

    HTML_DIR.mkdir(parents=True, exist_ok=True)

    html = fetch(
        search_url(1),
        use_browser,
    )

    if html is None:
        print("Could not download. Try --browser")
        return

    search_path(1).write_text(
        html,
        encoding="utf-8",
    )

    listings = parse_search_page(html, 1)

    print(f"HTML size: {len(html):,} bytes")
    print(
        f"Listings found on page 1: "
        f"{len(listings)}\n"
    )

    for record in listings[:5]:
        print(f"  id       {record['listing_id']}")
        print(f"  title    {record['title']}")
        print(f"  price    {record['price_usd']}")
        print(f"  size     {record['size_m2']}")
        print(f"  bedrooms {record['bedrooms']}")
        print(f"  bathrooms {record['bathrooms']}")
        print(
            f"  district {record['district']} "
            f"({record['province']})"
        )
        print(f"  type     {record['listing_type']}")
        print(f"  url      {record['url']}")
        print()

    priced = sum(
        record["price_usd"] is not None
        for record in listings
    )
    sized = sum(
        record["size_m2"] is not None
        for record in listings
    )
    bedroom_count = sum(
        record["bedrooms"] is not None
        for record in listings
    )

    print(
        f"  with price    : "
        f"{priced}/{len(listings)}"
    )
    print(
        f"  with size     : "
        f"{sized}/{len(listings)}"
    )
    print(
        f"  with bedrooms : "
        f"{bedroom_count}/{len(listings)}"
    )

    print(
        "\nNOTE: Khmer24 may ignore ?page=N. "
        "Use --all to collect by scrolling.\n"
    )


def run_search(args: argparse.Namespace) -> None:
    HTML_DIR.mkdir(parents=True, exist_ok=True)

    store = {} if args.reset_output else load_existing()
    before = len(store)

    if args.from_cache:
        pages = load_search_cache()

        if not pages:
            print(
                "No cached search pages. "
                "Run without --from-cache first."
            )
            return

        print(
            f"\nRe-parsing {len(pages)} "
            f"cached search pages\n"
        )

    elif args.all or args.scroll:
        html = collect_by_scrolling(
            max_scrolls=args.max_scrolls,
            headful=args.headful,
        )

        if html is None:
            return

        pages = [(999, html)]

    else:
        print(
            "\nNOTE: Khmer24 may return only the first batch "
            "for ?page=N. Use --all for scrolling.\n"
        )

        path = search_path(1)

        if path.exists() and not args.force:
            html = path.read_text(encoding="utf-8")

        else:
            html = fetch(
                search_url(1),
                args.browser,
            )

            if html is None:
                print("Could not download.")
                return

            path.write_text(
                html,
                encoding="utf-8",
            )

        pages = [(1, html)]

    parsed_store = build_store_from_search_pages(pages)

    for listing_id, record in parsed_store.items():
        existing = store.get(listing_id, {})

        store[listing_id] = merge_nonempty(
            existing,
            record,
            overwrite_fields=set(record.keys()),
        )

    save(store)

    added = len(store) - before

    summarise(
        store,
        f"PHASE 1 - added {added} new listings",
    )

    append_log(
        {
            "run_at": now_iso(),
            "mode": "search",
            "from_cache": args.from_cache,
            "reset_output": args.reset_output,
            "added": added,
            "total": len(store),
        }
    )


def prepare_detail_store(
    args: argparse.Namespace,
) -> dict[str, dict[str, Any]]:
    """
    With --reset-output, rebuild Phase 1 from cached search HTML first.
    This makes --from-cache --details --reset-output reproducible.
    """
    if not args.reset_output:
        return load_existing()

    pages = load_search_cache()

    if not pages:
        print(
            "No cached search pages are available "
            "for --reset-output."
        )
        return {}

    print(
        f"\nRebuilding Phase 1 from "
        f"{len(pages)} cached search pages\n"
    )

    return build_store_from_search_pages(pages)


def run_details(args: argparse.Namespace) -> None:
    store = prepare_detail_store(args)

    if not store:
        print("No listings yet. Run Phase 1 first.")
        return

    if args.from_cache and args.detail_force:
        print(
            "\nNote: --detail-force is ignored with --from-cache."
        )
        args.detail_force = False

    target = [
        record
        for record in store.values()
        if is_target_listing(record)
        and clean_text(record.get("url"))
    ]

    if args.limit is not None:
        target = target[: args.limit]

    if not target:
        print("No Phnom Penh sale listings are available.")
        summarise(store)
        return

    print(
        f"\nPHASE 2 - processing "
        f"{len(target)} detail pages\n"
    )

    downloaded = 0
    parsed = 0
    missing_cache = 0
    failed = 0

    for index, record in enumerate(target, start=1):
        listing_id = str(record["listing_id"])
        path = detail_path(listing_id)
        html = None

        if path.exists() and not args.detail_force:
            html = path.read_text(encoding="utf-8")

        elif args.from_cache:
            missing_cache += 1
            print(
                f"  [{index}/{len(target)}] "
                f"{listing_id} missing cached detail"
            )
            continue

        else:
            html = fetch(
                record["url"],
                args.browser,
            )

            if html is None:
                failed += 1
                print(
                    f"  [{index}/{len(target)}] "
                    f"{listing_id} FAILED"
                )
                continue

            path.write_text(
                html,
                encoding="utf-8",
            )
            downloaded += 1
            polite_sleep()

        store[listing_id] = parse_detail_page(
            html,
            record,
        )
        parsed += 1

        if (
            index % 25 == 0
            or index == len(target)
        ):
            save(store)
            print(
                f"  [{index}/{len(target)}] "
                f"processed and saved"
            )

    save(store)

    print("\nDETAIL SUMMARY")
    print("=" * 64)
    print(f"  candidates             : {len(target)}")
    print(f"  downloaded             : {downloaded}")
    print(f"  detail pages parsed    : {parsed}")
    print(f"  missing cached pages   : {missing_cache}")
    print(f"  failed downloads       : {failed}")
    print("=" * 64)

    summarise(
        store,
        f"PHASE 2 - enriched {parsed} listings",
    )

    append_log(
        {
            "run_at": now_iso(),
            "mode": "details",
            "from_cache": args.from_cache,
            "reset_output": args.reset_output,
            "limit": args.limit,
            "candidates": len(target),
            "downloaded": downloaded,
            "parsed": parsed,
            "missing_cache": missing_cache,
            "failed": failed,
        }
    )


# =======================================================================
# MAIN
# =======================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape Phnom Penh condo sale listings "
            "from khmer24.com"
        )
    )

    parser.add_argument(
        "--pages",
        type=int,
        default=5,
        help=(
            "retained for compatibility; Khmer24 "
            "may ignore numbered pagination"
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "scroll the search page until "
            "no new listings appear"
        ),
    )
    parser.add_argument(
        "--scroll",
        action="store_true",
        help="same as --all",
    )
    parser.add_argument(
        "--max-scrolls",
        type=int,
        default=120,
        help="maximum scroll steps (default: 120)",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="show the browser while scrolling",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="visit or reparse listing detail pages",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="process only the first N target details",
    )
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="read cached HTML only; no network",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="redownload the search page",
    )
    parser.add_argument(
        "--detail-force",
        action="store_true",
        help="redownload detail pages even if cached",
    )
    parser.add_argument(
        "--reset-output",
        action="store_true",
        help="ignore old raw JSON and rebuild it",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="use Playwright instead of requests",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="download one search batch and inspect it",
    )
    parser.add_argument(
        "--lang",
        choices=["en", "km"],
        default=DEFAULT_LANG,
        help="site language used for labels",
    )

    args = parser.parse_args()

    global LANG
    LANG = args.lang

    try:
        if args.inspect:
            run_inspect(args.browser)

        elif args.details:
            run_details(args)

        else:
            run_search(args)

    finally:
        close_browser()


if __name__ == "__main__":
    main()
