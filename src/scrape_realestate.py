#!/usr/bin/env python
"""
scrape_realestate.py - PP PropertyLens
======================================

Scrapes condominium and penthouse sale listings from realestate.com.kh.

Two stages:

1. Search-page collection
   - Downloads the filtered Phnom Penh result pages.
   - Reads the embedded Next.js JSON.
   - Extracts price, size, rooms, title, location, URL and structured floors.

2. Optional detail-page enrichment (--details)
   - Visits each listing URL.
   - Extracts Description, Overview, Property Overview and Property Details.
   - Uses structured fields first, then the title, then the description to
     recover missing bedrooms, bathrooms, unit floor and building floors.

Floor rule:
    unit_floor             = floor of the advertised unit
    building_total_floors  = total floors in the building

"77 stories high" is never read as unit_floor=77.

This revision also prevents a lower-priority DOM value from overwriting an
exact-listing JSON value discovered during the same detail-page parse.

USAGE
-----
    python src/scrape_realestate.py --inspect --headful
    python src/scrape_realestate.py --pages 3 --force
    python src/scrape_realestate.py --all --force --reset-output
    python src/scrape_realestate.py --from-cache --reset-output
    python src/scrape_realestate.py --details --detail-limit 20
    python src/scrape_realestate.py --details
    python src/scrape_realestate.py --from-cache --details

OUTPUT
------
    data/bronze/realestate/html/page_0001.html
    data/bronze/realestate/detail_html/<listing_id>.html
    data/bronze/realestate/raw_listings.json
    data/bronze/realestate/scrape_log.json
"""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urljoin

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
sys.path.insert(0, str(CONFIG_DIR))

import settings  # noqa: E402

try:
    from bs4 import BeautifulSoup, Tag
except ImportError:  # pragma: no cover
    BeautifulSoup = None
    Tag = None


# =======================================================================
# CONFIGURATION
# =======================================================================

BASE_URL = (
    "https://www.realestate.com.kh/buy/phnom-penh/"
    "?active_tab=popularLocations"
    "&categories=Condo"
    "&categories=Penthouse"
    "&order_by=relevance"
    "&property_type=residential"
    "&q=location%3A%20Phnom%20Penh"
    "&search_type=sale"
)

SITE_ROOT = "https://www.realestate.com.kh"

HTML_DIR = settings.RE_HTML_DIR
DETAIL_HTML_DIR = HTML_DIR.parent / "detail_html"
OUT_JSON = settings.RE_RAW_JSON
LOG_JSON = HTML_DIR.parent / "scrape_log.json"
INSPECT_DIR = settings.REPORT_DIR

RESULTS_PATH = ("props", "pageProps", "cacheData", "results", "data")

PRICE_KEYS = {
    "displayprice", "displayPrice", "price", "salePrice", "sale_price",
    "price_usd", "display_price", "min_price",
}

HINT_KEYS = {
    "specifications", "categoryname", "categoryName", "headline", "address",
    "listingtype", "listingType", "project", "url", "id",
    "bedroom", "bedrooms", "bathroom", "bathrooms",
    "floor_area", "floorarea", "size", "area",
    "title", "name", "slug", "location", "district", "commune",
    "latitude", "longitude", "lat", "lng", "createdat", "createdAt",
}

DESCRIPTION_JSON_KEYS = [
    ("description", "json_description"),
    ("propertyDescription", "json_property_description"),
    ("property_description", "json_property_description"),
    ("overview", "json_overview"),
    ("propertyOverview", "json_property_overview"),
    ("property_overview", "json_property_overview"),
    ("about", "json_about"),
    ("content", "json_content"),
]

DESCRIPTION_HEADINGS = {
    "description", "property description", "overview", "property overview",
    "about this property", "about the property", "details", "property details",
}

SPEC_TYPE_MAP = {
    "bedrooms": "bedrooms",
    "bathrooms": "bathrooms",
    "floor_area": "size_m2",
    "land_area": "land_area_m2",
    "floor_level": "unit_floor",
    "unit_floor": "unit_floor",
    "total_floors": "building_total_floors",
    "building_floors": "building_total_floors",
    "number_of_floors": "building_total_floors",
    "parking": "parking",
    "year_built": "year_built",
}

LABEL_MAP = {
    "bedroom": "bedrooms",
    "bathroom": "bathrooms",
    "floor area": "size_m2",
    "land area": "land_area_m2",
    "floor level": "unit_floor",
    "unit floor": "unit_floor",
    "total floors": "building_total_floors",
    "number of floors": "building_total_floors",
    "building floors": "building_total_floors",
    "parking": "parking",
    "year built": "year_built",
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
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def page_url(page_num: int) -> str:
    return BASE_URL if page_num == 1 else f"{BASE_URL}&page={page_num}"


def html_path(page_num: int) -> Path:
    return HTML_DIR / f"page_{page_num:04d}.html"


def safe_detail_filename(record: dict[str, Any]) -> str:
    listing_id = clean_text(record.get("listing_id"))

    if listing_id:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", listing_id) + ".html"

    url = clean_text(record.get("url"))
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]

    return f"url_{digest}.html"


def detail_html_path(record: dict[str, Any]) -> Path:
    return DETAIL_HTML_DIR / safe_detail_filename(record)


def polite_sleep() -> None:
    base = float(settings.REQUEST_DELAY_SECONDS)
    time.sleep(base + random.uniform(0, 1.2))


def first_key(d: dict[str, Any], candidates: Iterable[str]) -> Any:
    for key in candidates:
        if key in d and d[key] not in (None, "", []):
            return d[key]

    return None


def flatten_text(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        return clean_text(value) or None

    if isinstance(value, dict):
        for key in ("name", "title", "en", "label", "slug"):
            if key in value and isinstance(value[key], str):
                return clean_text(value[key]) or None

        return None

    if isinstance(value, list) and value:
        return flatten_text(value[0])

    return clean_text(value) or None


def parse_price(value: Any) -> int | None:
    """'$85,000' -> 85000, '85K' -> 85000, 'Negotiable' -> None."""
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None

    text = clean_text(value)
    low = text.lower()

    if not text or "negotiab" in low or low in {"poa", "p.o.a.", "n/a", "-"}:
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
    """'65 sqm' -> 65.0, '700 sqft' -> 65.03."""
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return round(float(value), 2) if value > 0 else None

    text = clean_text(value).lower().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)", text)

    if not match:
        return None

    number = float(match.group(1))

    if any(unit in text for unit in ("sqft", "ft2", "sq ft", "ft²")):
        number *= 0.092903

    return round(number, 2) if number > 0 else None


def parse_int(value: Any) -> int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return int(value)

    match = re.search(r"-?\d+", clean_text(value))

    return int(match.group()) if match else None


def get_path(node: Any, path: Iterable[str]) -> Any:
    current = node

    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None

        current = current[key]

    return current


def merge_nonempty(
    base: dict[str, Any],
    updates: dict[str, Any],
    *,
    overwrite_fields: set[str] | None = None,
) -> dict[str, Any]:
    """
    Merge non-empty values.

    Existing values are preserved unless the key is in overwrite_fields.
    """
    overwrite_fields = overwrite_fields or set()
    merged = dict(base)

    for key, value in updates.items():
        if value in (None, "", [], {}):
            continue

        if key in overwrite_fields or merged.get(key) in (None, "", [], {}):
            merged[key] = value

    return merged


# =======================================================================
# SAFE TEXT FIELD RECOVERY
# =======================================================================

ExtractionResult = tuple[int, str] | None


def search_patterns(
    text: Any,
    patterns: list[str],
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
            return value, match.group(0)

    return None


# Pattern order matters.
#
# The explicit "Label: N" form is tried first. In concatenated attribute text
# such as "Bathroom: 2 Bedroom: 3", a loose number-first pattern would read
# "2 Bedroom" and assign the bathroom's number to bedrooms.
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

# Counts are sometimes spelled out: "Unit one Bedroom olympia city".
WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
}

UNIT_FLOOR_PATTERNS = [
    r"\b(?:located|situated)\s+on\s+(?:the\s+)?"
    r"(\d{1,3})(?:st|nd|rd|th)?\s+floor\b",
    r"\bunit\s+(?:is\s+)?(?:located\s+)?on\s+(?:the\s+)?"
    r"(\d{1,3})(?:st|nd|rd|th)?\s+floor\b",
    r"\bon\s+(?:the\s+)?"
    r"(\d{1,3})(?:st|nd|rd|th)?\s+floor\b",
    r"\b(\d{1,3})(?:st|nd|rd|th)\s+floor\b",
    r"\bfloor\s+level\s*[:\-]?\s*(\d{1,3})(?:st|nd|rd|th)?\b",
    r"\bunit\s+floor\s*[:\-]?\s*(\d{1,3})(?:st|nd|rd|th)?\b",
    # "Floor: 6th"
    r"\bfloor\s*[:\-]\s*(\d{1,3})(?:st|nd|rd|th)?\b",
    r"\blevel\s*[:\-]\s*(\d{1,3})\b",
    # "Unit 31F". A bare "31F" is deliberately not matched, because ordinary
    # text such as "Special price 50 F only" or "30 F of parking" would
    # otherwise produce a floor number.
    r"\bunit\s+(\d{1,3})\s*[Ff]\b",
    # The coeng is often dropped, so listings contain both ជាន់ទី18 and ជានទី18.
    r"ជាន់?ទី\s*(\d{1,3})",
    r"ជាន់\s*[:\-]?\s*(\d{1,3})",
]

BUILDING_FLOOR_PATTERNS = [
    r"\b(\d{1,3})\s*(?:storey|storeys|story|stories)\s+high\b",
    r"\b(\d{1,3})\s*[- ]\s*(?:storey|storeys|story|stories)"
    r"\s+(?:building|tower|condominium|development)\b",
    r"\b(\d{1,3})\s+floors?\s+(?:building|tower)\b",
    r"\btotal\s+floors?\s*[:\-]?\s*(\d{1,3})\b",
    r"\bbuilding\s+(?:has|with)\s+(\d{1,3})\s+floors?\b",
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
        return WORD_NUMBERS[spelled.group(1).lower()], spelled.group(0)

    studio = re.search(r"\bstudio\b", cleaned, re.IGNORECASE)

    if studio:
        return 0, studio.group(0)

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
        return WORD_NUMBERS[spelled.group(1).lower()], spelled.group(0)

    return None


def extract_unit_floor(text: Any) -> ExtractionResult:
    return search_patterns(text, UNIT_FLOOR_PATTERNS, 1, 100)


def extract_building_total_floors(text: Any) -> ExtractionResult:
    return search_patterns(text, BUILDING_FLOOR_PATTERNS, 1, 150)


def recover_field(
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
            conflicts.append(f"title={title_result[0]} from '{title_result[1]}'")

        if description_result and description_result[0] != existing:
            conflicts.append(
                f"description={description_result[0]} "
                f"from '{description_result[1]}'"
            )

        if conflicts:
            append_conflict(
                record,
                field,
                "; ".join(conflicts),
            )

        return

    if title_result:
        value, matched_text = title_result
        record[field] = value
        record[f"{field}_source"] = "title"
        record[f"{field}_confidence"] = "high"
        record[f"{field}_text_raw"] = matched_text
        return

    if description_result:
        value, matched_text = description_result
        record[field] = value
        record[f"{field}_source"] = "description"
        record[f"{field}_confidence"] = "medium"
        record[f"{field}_text_raw"] = matched_text


def recover_missing_fields(record: dict[str, Any]) -> dict[str, Any]:
    output = dict(record)

    title = clean_text(output.get("title"))
    description = clean_text(output.get("description"))

    recover_field(output, "bedrooms", extract_bedrooms, title, description)
    recover_field(output, "bathrooms", extract_bathrooms, title, description)
    recover_field(output, "unit_floor", extract_unit_floor, title, description)
    recover_field(
        output,
        "building_total_floors",
        extract_building_total_floors,
        title,
        description,
    )

    return output


# =======================================================================
# SEARCH-PAGE JSON EXTRACTION
# =======================================================================

def extract_next_data(html: str) -> dict[str, Any] | None:
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    )

    if not match:
        return None

    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def looks_like_listing(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False

    keys = {str(key).lower() for key in obj.keys()}
    price_keys = {key.lower() for key in PRICE_KEYS}
    hint_keys = {key.lower() for key in HINT_KEYS}

    if not (keys & price_keys):
        return False

    return len(keys & hint_keys) >= 2


def walk_for_listings(
    node: Any,
    found: list[dict[str, Any]],
    depth: int = 0,
) -> None:
    if depth > 25:
        return

    if isinstance(node, dict):
        if looks_like_listing(node):
            found.append(node)
            return

        for value in node.values():
            walk_for_listings(value, found, depth + 1)

    elif isinstance(node, list):
        for item in node:
            walk_for_listings(item, found, depth + 1)


def extract_specifications(raw: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    specs = raw.get("specifications")

    if not isinstance(specs, dict):
        return out

    for group in ("detail", "general"):
        items = specs.get(group)

        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue

            spec_type = clean_text(item.get("type")).lower()
            column = SPEC_TYPE_MAP.get(spec_type)

            if not column:
                continue

            value = item.get("shortLabel") or item.get("label")

            if value not in (None, ""):
                out.setdefault(column, clean_text(value))

    return out


def extract_description_from_dict(
    raw: dict[str, Any],
) -> tuple[str | None, str | None]:
    for key, source in DESCRIPTION_JSON_KEYS:
        value = raw.get(key)

        if isinstance(value, str):
            text = clean_text(value)

            if len(text) >= 30:
                return text[:5000], source

        if isinstance(value, dict):
            nested = first_key(
                value, ["text", "content", "description", "overview"]
            )

            if isinstance(nested, str):
                text = clean_text(nested)

                if len(text) >= 30:
                    return text[:5000], source

    return None, None


def split_location(text: str | None) -> tuple[str | None, str | None]:
    if not text:
        return None, None

    parts = [part.strip() for part in str(text).split(",") if part.strip()]

    if len(parts) >= 3:
        return parts[-2], parts[-3]

    if len(parts) == 2:
        return parts[-2], None

    if len(parts) == 1:
        return parts[0], None

    return None, None


def normalise(raw: dict[str, Any], page_num: int) -> dict[str, Any]:
    specs = extract_specifications(raw)

    price = parse_price(
        first_key(raw, ["displayPrice", "price", "salePrice", "display_price"])
    )

    size = parse_size(
        specs.get("size_m2")
        or first_key(raw, ["floorArea", "floor_area", "size", "area"])
    )

    address = flatten_text(
        first_key(raw, ["address", "location", "fullAddress", "location_name"])
    )

    district = flatten_text(first_key(raw, ["district", "khan"]))
    commune = flatten_text(first_key(raw, ["commune", "sangkat"]))

    if district is None:
        district, commune_from_address = split_location(address)
        commune = commune or commune_from_address

    url = first_key(raw, ["url", "slug", "link", "detail_url"])

    if isinstance(url, str):
        url = urljoin(SITE_ROOT, url)

    project = raw.get("project") if isinstance(raw.get("project"), dict) else {}
    upgrades = raw.get("upgrades") if isinstance(raw.get("upgrades"), list) else []
    highlights = (
        raw.get("highlights") if isinstance(raw.get("highlights"), list) else []
    )

    description, description_source = extract_description_from_dict(raw)

    record: dict[str, Any] = {
        "listing_id": str(first_key(raw, ["id", "pk", "listing_id"]) or ""),
        "source": "realestate.com.kh",
        "source_page": page_num,
        "listing_type": flatten_text(
            first_key(raw, ["listingType", "listing_type"])
        ),

        "price_usd": price,
        "size_m2": size,

        "bedrooms": parse_int(specs.get("bedrooms")),
        "bathrooms": parse_int(specs.get("bathrooms")),
        "unit_floor": parse_int(specs.get("unit_floor")),
        "building_total_floors": parse_int(specs.get("building_total_floors")),

        "property_type": flatten_text(
            first_key(raw, ["categoryName", "category", "property_type"])
        ),

        "district": district,
        "commune": commune,
        "address": address,
        "latitude": first_key(raw, ["latitude", "lat"]),
        "longitude": first_key(raw, ["longitude", "lng", "lon"]),

        "project_name": flatten_text(project.get("projectName")),
        "project_id": project.get("id"),
        "display_as_project": bool(raw.get("displayAsProject")),

        "title": flatten_text(first_key(raw, ["headline", "title", "name"])),
        "description": description,
        "description_source": description_source,

        "bedrooms_source": (
            "structured_specification"
            if specs.get("bedrooms") is not None
            else None
        ),
        "bathrooms_source": (
            "structured_specification"
            if specs.get("bathrooms") is not None
            else None
        ),
        "unit_floor_source": (
            "structured_floor_level"
            if specs.get("unit_floor") is not None
            else None
        ),
        "building_total_floors_source": (
            "structured_specification"
            if specs.get("building_total_floors") is not None
            else None
        ),

        "price_display": flatten_text(raw.get("displayPrice")),
        "price_is_displayed": raw.get("priceIsDisplayed"),
        "created_at": flatten_text(first_key(raw, ["createdAt", "created_at"])),
        "listed_date_text": flatten_text(
            first_key(raw, ["listedDate", "displayDate"])
        ),
        "is_featured": "featured" in upgrades,
        "highlights": "; ".join(
            str(item.get("label"))
            for item in highlights
            if isinstance(item, dict) and item.get("label")
        ) or None,

        "site_estimate_usd": parse_price(raw.get("undermarketPrice")),
        "site_estimate_diff": flatten_text(raw.get("undermarketPriceDiff")),
        "ribbon": flatten_text(raw.get("ribbon")),

        "url": url if isinstance(url, str) else None,
        "scraped_at": now_iso(),
    }

    return recover_missing_fields(record)


def get_results_block(html: str) -> dict[str, Any] | None:
    data = extract_next_data(html)

    if data is None:
        return None

    block = get_path(data, RESULTS_PATH)

    return block if isinstance(block, dict) else None


def parse_via_json(html: str, page_num: int) -> list[dict[str, Any]]:
    data = extract_next_data(html)

    if data is None:
        return []

    block = get_path(data, RESULTS_PATH)

    if isinstance(block, dict) and isinstance(block.get("results"), list):
        rows = [row for row in block["results"] if isinstance(row, dict)]

        if rows:
            return [normalise(item, page_num) for item in rows]

    found: list[dict[str, Any]] = []
    walk_for_listings(data, found)

    return [normalise(item, page_num) for item in found]


# =======================================================================
# DOM EXTRACTION
# =======================================================================

def extract_value_label_pairs(scope: Any) -> dict[str, str]:
    found: dict[str, str] = {}

    for value_el in scope.select("span.value"):
        container = value_el.parent

        if container is None:
            continue

        label_el = (
            container.select_one("span.label span.text")
            or container.select_one("span.text")
        )

        if label_el is None:
            continue

        label = clean_text(label_el.get_text(" ", strip=True)).lower()
        value = clean_text(value_el.get_text(" ", strip=True))

        for prefix, column in LABEL_MAP.items():
            if label.startswith(prefix):
                found.setdefault(column, value)
                break

    for label_el in scope.select("dt, th, [class*='label' i]"):
        label = clean_text(label_el.get_text(" ", strip=True)).lower()

        if not label:
            continue

        value_el = label_el.find_next_sibling()

        if value_el is None:
            continue

        value = clean_text(value_el.get_text(" ", strip=True))

        for prefix, column in LABEL_MAP.items():
            if label.startswith(prefix) and value:
                found.setdefault(column, value)
                break

    return found


def extract_title_from_soup(soup: Any) -> str | None:
    selectors = [
        "h1.headline",
        "h1",
        "[class*='property-title' i]",
        "[class*='listing-title' i]",
        "meta[property='og:title']",
    ]

    for selector in selectors:
        element = soup.select_one(selector)

        if element is None:
            continue

        if element.name == "meta":
            text = clean_text(element.get("content"))
        else:
            text = clean_text(element.get_text(" ", strip=True))

        if text:
            return text[:500]

    return None


def extract_description_from_soup(soup: Any) -> tuple[str | None, str | None]:
    """Extract Description, Overview, Property Overview or similar."""
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

    candidates: list[tuple[str, str]] = []

    for selector, source in selectors:
        for element in soup.select(selector):
            text = clean_text(element.get_text(" ", strip=True))

            if 80 <= len(text) <= 20_000:
                candidates.append((text[:5000], source))

    if candidates:
        # Prefer the most specific match. These selectors match any ancestor
        # whose class merely contains the word, so an outer wrapper such as
        # class="page-with-description" would otherwise capture navigation,
        # the listing grid and the footer as the description.
        candidates.sort(key=lambda item: len(item[0]))
        return candidates[0]

    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "strong"]):
        heading_text = clean_text(heading.get_text(" ", strip=True))
        normalized_heading = heading_text.lower().strip(" :")

        if normalized_heading not in DESCRIPTION_HEADINGS:
            continue

        collected: list[str] = []

        for sibling in heading.find_next_siblings():
            if Tag is not None and not isinstance(sibling, Tag):
                continue

            if sibling.name in {"h1", "h2", "h3", "h4", "h5"}:
                break

            text = clean_text(sibling.get_text(" ", strip=True))

            if text:
                collected.append(text)

            if sum(len(item) for item in collected) >= 5000:
                break

        combined = clean_text(" ".join(collected))

        if len(combined) >= 80:
            source = (
                "overview_heading"
                if "overview" in normalized_heading
                else "description_heading"
            )

            return combined[:5000], source

    for script in soup.select("script[type='application/ld+json']"):
        raw = script.string

        if not raw:
            continue

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        objects = data if isinstance(data, list) else [data]

        for obj in objects:
            if not isinstance(obj, dict):
                continue

            description, source = extract_description_from_dict(obj)

            if description:
                return description, source or "json_ld_description"

    meta = soup.select_one(
        "meta[name='description'], meta[property='og:description']"
    )

    if meta is not None:
        text = clean_text(meta.get("content"))

        if len(text) >= 80:
            return text[:5000], "meta_description"

    return None, None


def parse_via_dom(html: str, page_num: int) -> list[dict[str, Any]]:
    if BeautifulSoup is None:
        return []

    soup = BeautifulSoup(html, "html.parser")

    headline = soup.select_one("h1.headline") or soup.select_one("h1")
    cards = soup.select(
        "[class*='listing-card' i], [class*='ListingCard'], article"
    )

    def build(scope: Any, title_el: Any) -> dict[str, Any] | None:
        attrs = extract_value_label_pairs(scope)

        price_el = (
            scope.select_one(".prices")
            or scope.select_one("[class*='price' i]")
        )

        price_text = (
            price_el.get_text(" ", strip=True)
            if price_el
            else scope.get_text(" ", strip=True)
        )

        price_match = re.search(r"\$\s?[\d,]+(?:\.\d+)?\s?[KkMm]?", price_text)
        price = parse_price(price_match.group()) if price_match else None

        title = (
            clean_text(title_el.get_text(" ", strip=True))
            if title_el
            else None
        )

        location_element = scope.select_one("h2")
        location_text = (
            clean_text(location_element.get_text(" ", strip=True))
            if location_element
            else None
        )

        district, commune = split_location(location_text)

        anchor = scope.find("a", href=True)
        url = urljoin(SITE_ROOT, anchor["href"]) if anchor else None

        if price is None and not attrs:
            return None

        record: dict[str, Any] = {
            "listing_id": "",
            "source": "realestate.com.kh",
            "source_page": page_num,
            "title": title,
            "description": None,
            "description_source": None,

            "price_usd": price,
            "size_m2": parse_size(attrs.get("size_m2")),
            "bedrooms": parse_int(attrs.get("bedrooms")),
            "bathrooms": parse_int(attrs.get("bathrooms")),
            "unit_floor": parse_int(attrs.get("unit_floor")),
            "building_total_floors": parse_int(
                attrs.get("building_total_floors")
            ),

            "property_type": None,
            "district": district,
            "commune": commune,
            "address": location_text,
            "latitude": None,
            "longitude": None,
            "url": url,
            "scraped_at": now_iso(),

            "bedrooms_source": (
                "structured_dom" if attrs.get("bedrooms") is not None else None
            ),
            "bathrooms_source": (
                "structured_dom" if attrs.get("bathrooms") is not None else None
            ),
            "unit_floor_source": (
                "structured_dom"
                if attrs.get("unit_floor") is not None
                else None
            ),
            "building_total_floors_source": (
                "structured_dom"
                if attrs.get("building_total_floors") is not None
                else None
            ),
        }

        return recover_missing_fields(record)

    listings: list[dict[str, Any]] = []

    if cards:
        for card in cards:
            record = build(card, card.find(["h1", "h2", "h3"]))

            if record:
                listings.append(record)

    if not listings and headline is not None:
        record = build(soup, headline)

        if record:
            listings.append(record)

    return listings


def parse_page(html: str, page_num: int) -> tuple[list[dict[str, Any]], str]:
    listings = parse_via_json(html, page_num)

    if listings:
        return listings, "json"

    listings = parse_via_dom(html, page_num)

    return listings, "dom" if listings else "none"


# =======================================================================
# DETAIL-PAGE EXTRACTION
# =======================================================================

def normalize_comparison_url(value: Any) -> str:
    if not value:
        return ""

    return urljoin(SITE_ROOT, str(value)).rstrip("/").lower()


def listing_node_score(
    node: dict[str, Any],
    target_listing_id: Any,
    target_url: Any,
) -> int:
    """
    Score a JSON object as a possible representation of the current listing.

    Finding a bedroom or floor value is not enough: detail-page JSON usually
    also contains related listings and project unit examples.
    """
    target_id = clean_text(target_listing_id)
    target_normalized_url = normalize_comparison_url(target_url)

    node_id = first_key(node, ["id", "pk", "listing_id"])
    node_url = first_key(node, ["url", "slug", "link", "detail_url"])

    score = 0

    if target_id and node_id is not None and clean_text(node_id) == target_id:
        score += 20

    if (
        target_normalized_url
        and node_url is not None
        and normalize_comparison_url(node_url) == target_normalized_url
    ):
        score += 20

    if isinstance(node.get("specifications"), dict):
        score += 8

    if first_key(node, ["headline", "title", "name"]):
        score += 4

    if first_key(node, ["displayPrice", "price", "salePrice"]):
        score += 3

    if first_key(node, ["listingType", "listing_type"]):
        score += 2

    if first_key(node, ["categoryName", "category", "property_type"]):
        score += 1

    return score


def find_exact_listing_node(
    node: Any,
    target_listing_id: Any,
    target_url: Any,
    depth: int = 0,
) -> dict[str, Any] | None:
    """
    Find the JSON object for the current listing only.

    This prevents attributes from related listings, recommended properties,
    project unit examples, images, owners or agents from being used.
    """
    if depth > 30:
        return None

    candidates: list[tuple[int, dict[str, Any]]] = []

    def visit(current: Any, current_depth: int) -> None:
        if current_depth > 30:
            return

        if isinstance(current, dict):
            score = listing_node_score(current, target_listing_id, target_url)

            # 20 or more requires an exact id or url match.
            if score >= 20:
                candidates.append((score, current))

            for value in current.values():
                visit(value, current_depth + 1)

        elif isinstance(current, list):
            for item in current:
                visit(item, current_depth + 1)

    visit(node, depth)

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)

    return candidates[0][1]


DETAIL_SOURCE_PRIORITY = {
    "detail_json_exact_listing": 30,
    "detail_dom_structured": 20,
    "title": 10,
    "description": 10,
}


def append_conflict(
    record: dict[str, Any],
    field: str,
    message: str,
) -> None:
    """
    Add one conflict message without creating duplicates.

    recover_missing_fields() may run more than once, so exact duplicate
    messages must not be appended repeatedly.
    """
    conflict_key = f"{field}_conflict"
    previous = clean_text(record.get(conflict_key))

    # New code separates complete conflict messages with `` || ``.
    # An older value that used semicolons is kept as one complete message.
    messages = (
        [part.strip() for part in previous.split(" || ") if part.strip()]
        if previous
        else []
    )

    cleaned_message = clean_text(message)

    if cleaned_message and cleaned_message not in messages:
        messages.append(cleaned_message)

    if messages:
        record[conflict_key] = " || ".join(messages)
        record["needs_manual_review"] = True


def values_differ(field: str, left: Any, right: Any) -> bool:
    if field == "size_m2":
        try:
            return abs(float(left) - float(right)) > 0.5
        except (TypeError, ValueError):
            return clean_text(left) != clean_text(right)

    return parse_int(left) != parse_int(right)


def source_priority(source: Any, *, base_value_exists: bool = False) -> int:
    """Return a reliability score for a candidate source."""
    if base_value_exists:
        # Search-page structured data is preserved over detail candidates.
        return 100

    return DETAIL_SOURCE_PRIORITY.get(clean_text(source), 0)


def apply_detail_candidate(
    base_record: dict[str, Any],
    updates: dict[str, Any],
    field: str,
    value: Any,
    source: str,
    confidence: str,
) -> None:
    """
    Add a value from the current listing's detail page safely.

    Priority:
        1. Existing search-page value
        2. Exact current-listing JSON
        3. Structured DOM from the current detail page

    A lower-priority candidate cannot overwrite a higher-priority candidate.
    Disagreements are retained for auditing and manual review.
    """
    if value in (None, "", [], {}):
        return

    base_value = base_record.get(field)
    updated_value = updates.get(field)

    base_exists = base_value not in (None, "", [], {})
    update_exists = updated_value not in (None, "", [], {})

    # The search-page value is authoritative at this stage.
    if base_exists:
        if values_differ(field, base_value, value):
            candidate_key = f"{field}_detail_value"
            candidate_source_key = f"{field}_detail_source"
            candidate_confidence_key = f"{field}_detail_confidence"

            existing_candidate = updates.get(candidate_key)
            existing_candidate_source = updates.get(candidate_source_key)

            if (
                existing_candidate in (None, "", [], {})
                or source_priority(source)
                > source_priority(existing_candidate_source)
            ):
                updates[candidate_key] = value
                updates[candidate_source_key] = source
                updates[candidate_confidence_key] = confidence

            append_conflict(
                updates,
                field,
                f"{source}={value}; kept search value={base_value}",
            )

        return

    # Nothing has filled the field yet.
    if not update_exists:
        updates[field] = value
        updates[f"{field}_source"] = source
        updates[f"{field}_confidence"] = confidence
        return

    # A previous detail source already found the same value.
    if not values_differ(field, updated_value, value):
        current_source = updates.get(f"{field}_source")

        if source_priority(source) > source_priority(current_source):
            updates[f"{field}_source"] = source
            updates[f"{field}_confidence"] = confidence

        return

    # Two detail sources disagree. Preserve the higher-priority value.
    current_source = updates.get(f"{field}_source")
    current_confidence = updates.get(f"{field}_confidence")
    current_priority = source_priority(current_source)
    new_priority = source_priority(source)

    if new_priority > current_priority:
        updates[f"{field}_detail_value"] = updated_value
        updates[f"{field}_detail_source"] = current_source
        updates[f"{field}_detail_confidence"] = current_confidence

        updates[field] = value
        updates[f"{field}_source"] = source
        updates[f"{field}_confidence"] = confidence

        append_conflict(
            updates,
            field,
            (
                f"{current_source}={updated_value}; replaced by "
                f"higher-priority {source}={value}"
            ),
        )
    else:
        existing_candidate_source = updates.get(f"{field}_detail_source")

        if (
            updates.get(f"{field}_detail_value") in (None, "", [], {})
            or new_priority > source_priority(existing_candidate_source)
        ):
            updates[f"{field}_detail_value"] = value
            updates[f"{field}_detail_source"] = source
            updates[f"{field}_detail_confidence"] = confidence

        append_conflict(
            updates,
            field,
            f"{source}={value}; kept {current_source}={updated_value}",
        )


def parse_detail_page(
    html: str,
    base_record: dict[str, Any],
) -> dict[str, Any]:
    if BeautifulSoup is None:
        return base_record

    soup = BeautifulSoup(html, "html.parser")
    updates: dict[str, Any] = {}

    next_data = extract_next_data(html)

    if next_data is not None:
        exact_listing = find_exact_listing_node(
            next_data,
            target_listing_id=base_record.get("listing_id"),
            target_url=base_record.get("url"),
        )

        updates["detail_json_exact_match"] = exact_listing is not None

        if exact_listing is not None:
            exact_specs = extract_specifications(exact_listing)

            apply_detail_candidate(
                base_record,
                updates,
                "size_m2",
                parse_size(exact_specs.get("size_m2")),
                "detail_json_exact_listing",
                "high",
            )

            for field in (
                "bedrooms",
                "bathrooms",
                "unit_floor",
                "building_total_floors",
            ):
                apply_detail_candidate(
                    base_record,
                    updates,
                    field,
                    parse_int(exact_specs.get(field)),
                    "detail_json_exact_listing",
                    "high",
                )

            exact_title = first_key(exact_listing, ["headline", "title", "name"])

            if isinstance(exact_title, str):
                updates["detail_json_title"] = clean_text(exact_title)[:500]

            json_description, json_description_source = (
                extract_description_from_dict(exact_listing)
            )

            if json_description:
                updates["description"] = json_description
                updates["description_source"] = (
                    json_description_source or "detail_json_exact_listing"
                )

    # DOM values are candidates only: they fill gaps, never replace.
    main_scope = soup.select_one("main") or soup
    attrs = extract_value_label_pairs(main_scope)

    apply_detail_candidate(
        base_record,
        updates,
        "size_m2",
        parse_size(attrs.get("size_m2")),
        "detail_dom_structured",
        "medium",
    )

    for field in (
        "bedrooms",
        "bathrooms",
        "unit_floor",
        "building_total_floors",
    ):
        apply_detail_candidate(
            base_record,
            updates,
            field,
            parse_int(attrs.get(field)),
            "detail_dom_structured",
            "medium",
        )

    detail_title = extract_title_from_soup(soup)

    if detail_title:
        if clean_text(base_record.get("title")):
            updates["detail_title"] = detail_title
        else:
            updates["title"] = detail_title

    description, description_source = extract_description_from_soup(soup)

    if description:
        updates["description"] = description
        updates["description_source"] = description_source

    merged = merge_nonempty(
        base_record,
        updates,
        overwrite_fields={
            "description",
            "description_source",
            "detail_title",
            "detail_json_title",
            "detail_json_exact_match",
            "detail_scraped",
            "detail_parsed_at",
            "needs_manual_review",
            "size_m2_detail_value",
            "bedrooms_detail_value",
            "bathrooms_detail_value",
            "unit_floor_detail_value",
            "building_total_floors_detail_value",
            "size_m2_detail_source",
            "bedrooms_detail_source",
            "bathrooms_detail_source",
            "unit_floor_detail_source",
            "building_total_floors_detail_source",
            "size_m2_detail_confidence",
            "bedrooms_detail_confidence",
            "bathrooms_detail_confidence",
            "unit_floor_detail_confidence",
            "building_total_floors_detail_confidence",
            "size_m2_conflict",
            "bedrooms_conflict",
            "bathrooms_conflict",
            "unit_floor_conflict",
            "building_total_floors_conflict",
        },
    )

    merged["detail_scraped"] = True
    merged["detail_parsed_at"] = now_iso()

    return recover_missing_fields(merged)


# =======================================================================
# FETCHING
# =======================================================================

def fetch_pages(
    page_numbers: list[int],
    headful: bool = False,
) -> dict[int, str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\nPlaywright is not installed. Run:")
        print("    pip install playwright")
        print("    playwright install chromium\n")
        sys.exit(1)

    HTML_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[int, str] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headful)
        context = browser.new_context(
            user_agent=settings.USER_AGENT,
            viewport={"width": 1400, "height": 1000},
            locale="en-US",
        )
        page = context.new_page()

        for page_num in page_numbers:
            url = page_url(page_num)
            print(f"  page {page_num:>3}  fetching ...", end=" ", flush=True)

            html = None

            for attempt in range(1, settings.MAX_RETRIES + 1):
                try:
                    page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=settings.REQUEST_TIMEOUT * 1000,
                    )
                    page.wait_for_timeout(3500)
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(1500)
                    html = page.content()
                    break

                except Exception as exc:
                    print(
                        f"retry {attempt} ({type(exc).__name__})",
                        end=" ",
                        flush=True,
                    )
                    time.sleep(3 * attempt)

            if html is None:
                print("FAILED")
                continue

            html_path(page_num).write_text(html, encoding="utf-8")
            results[page_num] = html

            print(f"saved ({len(html):,} bytes)")
            polite_sleep()

        browser.close()

    return results


def enrich_details(
    records: list[dict[str, Any]],
    *,
    from_cache: bool,
    headful: bool,
    force: bool,
    detail_limit: int | None,
) -> list[dict[str, Any]]:
    if BeautifulSoup is None:
        print("\nBeautifulSoup is required for detail parsing:")
        print("    pip install beautifulsoup4")
        return records

    # --detail-force means "redownload", which cannot happen without a
    # network. Ignoring it here prevents every cached page being skipped.
    if from_cache and force:
        print("\nNote: --detail-force is ignored with --from-cache.")
        force = False

    candidates = [
        record for record in records if clean_text(record.get("url"))
    ]

    if detail_limit is not None:
        candidates = candidates[:detail_limit]

    if not candidates:
        print("\nNo listing URLs are available for detail enrichment.")
        return records

    DETAIL_HTML_DIR.mkdir(parents=True, exist_ok=True)

    by_key: dict[str, dict[str, Any]] = {}

    for record in records:
        key = (
            clean_text(record.get("listing_id"))
            or clean_text(record.get("url"))
        )
        by_key[key] = record

    downloaded = 0
    parsed = 0
    missing_cache = 0
    with_description_before = sum(
        1 for record in records if clean_text(record.get("description"))
    )

    playwright_context = None
    playwright = None
    browser = None
    context = None
    page = None

    if not from_cache:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("\nPlaywright is not installed. Run:")
            print("    pip install playwright")
            print("    playwright install chromium\n")
            return records

        playwright_context = sync_playwright()
        playwright = playwright_context.start()
        browser = playwright.chromium.launch(headless=not headful)
        context = browser.new_context(
            user_agent=settings.USER_AGENT,
            viewport={"width": 1400, "height": 1000},
            locale="en-US",
        )
        page = context.new_page()

    print(f"\nDetail enrichment: {len(candidates)} listing(s)\n")

    try:
        for index, record in enumerate(candidates, start=1):
            path = detail_html_path(record)
            url = clean_text(record.get("url"))
            html = None

            if path.exists() and not force:
                html = path.read_text(encoding="utf-8")

            elif from_cache:
                missing_cache += 1
                print(
                    f"  [{index:>4}/{len(candidates)}] "
                    f"missing cache  {record.get('listing_id') or url}"
                )
                continue

            else:
                assert page is not None

                print(
                    f"  [{index:>4}/{len(candidates)}] fetching ...",
                    end=" ",
                    flush=True,
                )

                for attempt in range(1, settings.MAX_RETRIES + 1):
                    try:
                        page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=settings.REQUEST_TIMEOUT * 1000,
                        )
                        page.wait_for_timeout(3000)
                        page.mouse.wheel(0, 3500)
                        page.wait_for_timeout(1200)
                        html = page.content()
                        break

                    except Exception as exc:
                        print(
                            f"retry {attempt} ({type(exc).__name__})",
                            end=" ",
                            flush=True,
                        )
                        time.sleep(3 * attempt)

                if html is None:
                    print("FAILED")
                    continue

                path.write_text(html, encoding="utf-8")
                downloaded += 1
                print(f"saved ({len(html):,} bytes)")
                polite_sleep()

            enriched = parse_detail_page(html, record)
            key = (
                clean_text(record.get("listing_id"))
                or clean_text(record.get("url"))
            )
            by_key[key] = enriched
            parsed += 1

    finally:
        if browser is not None:
            browser.close()

        if playwright is not None:
            playwright.stop()

    output = list(by_key.values())

    with_description_after = sum(
        1 for record in output if clean_text(record.get("description"))
    )
    exact_matches = sum(
        1 for record in output if record.get("detail_json_exact_match")
    )
    needs_review = sum(
        1 for record in output if record.get("needs_manual_review")
    )

    print("\nDETAIL SUMMARY")
    print("=" * 58)
    print(f"  candidates               : {len(candidates)}")
    print(f"  downloaded               : {downloaded}")
    print(f"  detail pages parsed      : {parsed}")
    print(f"  missing cached pages     : {missing_cache}")
    print(f"  exact JSON listing match : {exact_matches}")
    print(f"  descriptions before      : {with_description_before}")
    print(f"  descriptions after       : {with_description_after}")
    print(f"  flagged for review       : {needs_review}")
    print("=" * 58)

    return output


# =======================================================================
# INSPECT MODE
# =======================================================================

def summarise_json(
    node: Any,
    prefix: str = "",
    depth: int = 0,
    max_depth: int = 6,
    lines: list[str] | None = None,
) -> list[str]:
    if lines is None:
        lines = []

    if depth > max_depth:
        return lines

    pad = "  " * depth

    if isinstance(node, dict):
        for key, value in list(node.items())[:40]:
            kind = type(value).__name__
            extra = (
                f" (len {len(value)})"
                if isinstance(value, (list, dict))
                else ""
            )
            lines.append(f"{pad}{key}: {kind}{extra}")
            summarise_json(value, f"{prefix}.{key}", depth + 1, max_depth, lines)

    elif isinstance(node, list) and node:
        lines.append(f"{pad}[0] of {len(node)}:")
        summarise_json(node[0], prefix + "[0]", depth + 1, max_depth, lines)

    return lines


def run_inspect(headful: bool) -> None:
    print("\nINSPECT MODE - downloading page 1 and analysing its structure\n")

    pages = fetch_pages([1], headful=headful)

    if 1 not in pages:
        print("Could not download the page. Try --headful.")
        return

    html = pages[1]
    INSPECT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"HTML size: {len(html):,} bytes")

    data = extract_next_data(html)

    if data is None:
        print("\n__NEXT_DATA__ : NOT FOUND")
        print("The DOM fallback will be used.")
        print(f"Open the cached page: {html_path(1)}")
        return

    print("__NEXT_DATA__ : found\n")

    blob_path = INSPECT_DIR / "next_data_page1.json"
    blob_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    tree_path = INSPECT_DIR / "next_data_structure.txt"
    tree_path.write_text(
        "\n".join(summarise_json(data, max_depth=9)), encoding="utf-8"
    )

    print(f"Full JSON written to : {blob_path}")
    print(f"Key structure written: {tree_path}")

    block = get_path(data, RESULTS_PATH)

    if isinstance(block, dict):
        print("\nRESULTS BLOCK")
        print(f"    listings on this page : {len(block.get('results') or [])}")
        print(f"    total count           : {block.get('count')}")
        print(f"    last page             : {block.get('lastPage')}")

    api = get_path(data, ("props", "pageProps", "cacheData", "results"))

    if isinstance(api, dict):
        endpoint = api.get("endpoint")
        query = api.get("query")
        headers = get_path(api, ("options", "headers"))

        if endpoint:
            print("\nSITE API")
            print(f"    endpoint : {endpoint}")
            print(f"    query    : {json.dumps(query, ensure_ascii=False)}")
            print(f"    headers  : {json.dumps(headers, ensure_ascii=False)}")

    rows = block.get("results") if isinstance(block, dict) else None

    if isinstance(rows, list) and rows:
        sample_path = INSPECT_DIR / "sample_listing.json"
        sample_path.write_text(
            json.dumps(rows[0], indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nOne complete listing written to: {sample_path}")

        print("\nAfter normalisation:")
        for key, value in normalise(rows[0], 1).items():
            print(f"    {key:<30} = {value}")


# =======================================================================
# STORAGE
# =======================================================================

def load_existing() -> dict[str, dict[str, Any]]:
    if not OUT_JSON.exists():
        return {}

    try:
        records = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(records, list):
        return {}

    store: dict[str, dict[str, Any]] = {}

    for record in records:
        if not isinstance(record, dict):
            continue

        key = (
            clean_text(record.get("listing_id"))
            or clean_text(record.get("url"))
            or json.dumps(record, sort_keys=True)
        )

        store[key] = record

    return store


def save_records(records: list[dict[str, Any]]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def append_log(entry: dict[str, Any]) -> None:
    log: list[dict[str, Any]] = []

    if LOG_JSON.exists():
        try:
            loaded = json.loads(LOG_JSON.read_text(encoding="utf-8"))

            if isinstance(loaded, list):
                log = loaded
        except json.JSONDecodeError:
            log = []

    log.append(entry)
    LOG_JSON.parent.mkdir(parents=True, exist_ok=True)
    LOG_JSON.write_text(
        json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# =======================================================================
# MAIN
# =======================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape condo listings from realestate.com.kh"
    )

    parser.add_argument("--pages", type=int, default=5,
                        help="number of result pages to process (default: 5)")
    parser.add_argument("--start", type=int, default=1,
                        help="first result-page number (default: 1)")
    parser.add_argument("--from-cache", action="store_true",
                        help="read cached HTML only; do not use the network")
    parser.add_argument("--force", action="store_true",
                        help="redownload result pages even when cached")
    parser.add_argument("--headful", action="store_true",
                        help="show the Chromium browser window")
    parser.add_argument("--inspect", action="store_true",
                        help="download page 1 and inspect the Next.js data")
    parser.add_argument("--all", action="store_true",
                        help="use the lastPage value reported by the website")
    parser.add_argument("--reset-output", action="store_true",
                        help="ignore the existing raw JSON and rebuild it")
    parser.add_argument("--details", action="store_true",
                        help="visit or reparse individual listing detail pages")
    parser.add_argument("--detail-limit", type=int, default=None,
                        help="enrich only the first N listing detail pages")
    parser.add_argument("--detail-force", action="store_true",
                        help="redownload detail pages even when cached")

    args = parser.parse_args()

    HTML_DIR.mkdir(parents=True, exist_ok=True)
    DETAIL_HTML_DIR.mkdir(parents=True, exist_ok=True)

    if args.inspect:
        run_inspect(args.headful)
        return

    # ----------------------------------------------------------- pages
    if args.from_cache:
        cached = sorted(HTML_DIR.glob("page_*.html"))

        if not cached:
            print("No cached search pages found.")
            return

        page_numbers = [int(path.stem.split("_")[1]) for path in cached]

        print(
            f"\nRe-parsing {len(page_numbers)} cached result pages "
            f"(no network)\n"
        )

        html_by_page = {
            number: html_path(number).read_text(encoding="utf-8")
            for number in page_numbers
        }

    else:
        total_pages = args.pages

        if args.all:
            print("\nAsking the site how many pages exist ...")

            first = fetch_pages([1], headful=args.headful)
            html_first = first.get(1)

            if html_first is None and html_path(1).exists():
                html_first = html_path(1).read_text(encoding="utf-8")

            block = get_results_block(html_first) if html_first else None
            last_page = (
                block.get("lastPage") if isinstance(block, dict) else None
            )
            count = block.get("count") if isinstance(block, dict) else None

            if isinstance(last_page, int) and last_page > 0:
                total_pages = last_page
                print(
                    f"  site reports {last_page} pages"
                    + (
                        f" / {count:,} listings"
                        if isinstance(count, int)
                        else ""
                    )
                )
            else:
                print(
                    f"  could not read lastPage; "
                    f"falling back to --pages {args.pages}"
                )

        page_numbers = list(range(args.start, args.start + total_pages))

        to_fetch = [
            number
            for number in page_numbers
            if args.force or not html_path(number).exists()
        ]

        already = len(page_numbers) - len(to_fetch)

        print("\nScraping realestate.com.kh")
        print(f"  pages requested : {page_numbers[0]} to {page_numbers[-1]}")
        print(f"  already cached  : {already}")
        print(f"  to download     : {len(to_fetch)}\n")

        html_by_page: dict[int, str] = {}

        if to_fetch:
            html_by_page.update(fetch_pages(to_fetch, headful=args.headful))

        for number in page_numbers:
            if number not in html_by_page and html_path(number).exists():
                html_by_page[number] = html_path(number).read_text(
                    encoding="utf-8"
                )

    # ----------------------------------------------------------- parse
    store = {} if args.reset_output else load_existing()
    before = len(store)
    methods: dict[str, int] = {}
    empty_pages = 0

    site_total = None
    site_last_page = None

    if html_by_page:
        first_block = get_results_block(html_by_page[min(html_by_page)])

        if isinstance(first_block, dict):
            site_total = first_block.get("count")
            site_last_page = first_block.get("lastPage")

    print("\nParsing result pages:")

    for page_num in sorted(html_by_page):
        listings, method = parse_page(html_by_page[page_num], page_num)

        methods[method] = methods.get(method, 0) + 1

        if not listings:
            empty_pages += 1

        for record in listings:
            key = (
                clean_text(record.get("listing_id"))
                or clean_text(record.get("url"))
                or json.dumps(record, sort_keys=True)
            )

            existing = store.get(key, {})
            store[key] = merge_nonempty(
                existing, record, overwrite_fields=set(record.keys())
            )

        print(
            f"  page {page_num:>3}  {len(listings):>3} listings  (via {method})"
        )

    records = list(store.values())

    # ----------------------------------------------------------- details
    if args.details:
        records = enrich_details(
            records,
            from_cache=args.from_cache,
            headful=args.headful,
            force=args.detail_force,
            detail_limit=args.detail_limit,
        )

    save_records(records)

    # ----------------------------------------------------------- report
    added = len(records) - before

    with_price = sum(1 for record in records if record.get("price_usd"))
    with_size = sum(1 for record in records if record.get("size_m2"))
    usable = sum(
        1
        for record in records
        if record.get("price_usd") and record.get("size_m2")
    )
    with_description = sum(
        1 for record in records if clean_text(record.get("description"))
    )
    with_unit_floor = sum(
        1 for record in records if record.get("unit_floor") is not None
    )
    with_building_floors = sum(
        1
        for record in records
        if record.get("building_total_floors") is not None
    )
    with_bedrooms = sum(
        1 for record in records if record.get("bedrooms") is not None
    )
    with_bathrooms = sum(
        1 for record in records if record.get("bathrooms") is not None
    )
    needs_review = sum(
        1 for record in records if record.get("needs_manual_review")
    )

    recovered_from_text: dict[str, int] = {}

    for field in (
        "bedrooms",
        "bathrooms",
        "unit_floor",
        "building_total_floors",
    ):
        recovered_from_text[field] = sum(
            1
            for record in records
            if record.get(f"{field}_source") in {"title", "description"}
        )

    print("\n" + "=" * 62)
    print(f"  pages parsed             : {len(html_by_page)}")
    print(f"  new listings added       : {added}")
    print(f"  total in file            : {len(records)}")
    print(f"  with a price             : {with_price}")
    print(f"  with a size              : {with_size}")
    print(f"  with bedrooms            : {with_bedrooms}")
    print(f"  with bathrooms           : {with_bathrooms}")
    print(f"  with unit floor          : {with_unit_floor}")
    print(f"  with building floors     : {with_building_floors}")
    print(f"  with description/overview: {with_description}")
    print(f"  usable (price + size)    : {usable}")
    print(f"  parse methods            : {methods}")

    print("\n  recovered from text (not structured):")
    for field, count in recovered_from_text.items():
        print(f"    {field:<24}{count:>6}")

    if needs_review:
        print(f"\n  flagged needs_manual_review: {needs_review}")
        print("  (a structured value disagreed with the title or description)")

    if site_total is not None:
        print(
            f"\n  site reports total       : "
            f"{site_total:,} listings across {site_last_page} pages"
        )

        if isinstance(site_total, int) and site_total:
            print(
                f"  exposed-search coverage  : "
                f"{len(records) / site_total:.1%}"
            )

    print(f"  saved to                 : {OUT_JSON}")
    print("=" * 62)

    if empty_pages:
        print(f"\n{empty_pages} result page(s) produced no listings.")
        print("Run: python src/scrape_realestate.py --inspect --headful")

    append_log(
        {
            "run_at": now_iso(),
            "pages": sorted(html_by_page.keys()),
            "added": added,
            "total": len(records),
            "usable": usable,
            "with_description": with_description,
            "with_unit_floor": with_unit_floor,
            "needs_manual_review": needs_review,
            "recovered_from_text": recovered_from_text,
            "methods": methods,
            "from_cache": args.from_cache,
            "details": args.details,
            "detail_limit": args.detail_limit,
        }
    )


if __name__ == "__main__":
    main()
