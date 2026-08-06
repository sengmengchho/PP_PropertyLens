#!/usr/bin/env python
"""
scrape_agencies.py - PP PropertyLens (v13)
====================================

One pipeline, several site adapters.

Adding a site means writing a small Adapter subclass - roughly 40 lines - and
nothing else. Caching, resume, polite delays, deduplication, filtering and
saving are shared.

CONFIRMED BY PROBING (scope: condo + for sale + Phnom Penh)

    khpropertyhub.com   184 listings   ?page=N        22 per page
    aps.com.kh          137 listings   /page/N        28 per page

    pointerasia.com     DROPPED - shares khpropertyhub's database. Identical
                        slugs and ids were returned by both sites, e.g.
                        condo-phnom-penh-boeng-keng-kang-23406


TWO PHASES
----------
  Phase 1  walk the filtered search pages, collect listing URLs
  Phase 2  fetch each listing page, extract fields with site-specific adapters

Both phases cache raw HTML, so a wrong parser is fixed with --from-cache
instead of re-downloading.


USAGE
-----
    python src/scrape_agencies.py --site khpropertyhub --inspect
    python src/scrape_agencies.py --site khpropertyhub
    python src/scrape_agencies.py --site aps
    python src/scrape_agencies.py --all
    python src/scrape_agencies.py --site aps --from-cache --reset-output
    python src/scrape_agencies.py --site harbor --detail-limit 20


OUTPUT
------
    data/bronze/<site>/html/search_0001.html
    data/bronze/<site>/html/detail_<id>.html
    data/bronze/<site>/raw_listings.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlencode, parse_qsl, urlunparse

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
sys.path.insert(0, str(CONFIG_DIR))
import settings  # noqa: E402

import requests  # noqa: E402

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing dependency:  pip install beautifulsoup4")
    sys.exit(1)


BRONZE = settings.BRONZE_DIR


# ========================================================================
# DISTRICT NORMALISATION
# ========================================================================
# Every source spells the khans differently. All of them must land on one
# label or the merged dataset will treat them as separate districts.
# Seen so far: realestate.com.kh "Toul Kork", khmer24 "ទួលគោក" / "Tuol Kouk",
# khpropertyhub "tuol-kouk", aps "toul-tumpung".

DISTRICT_ALIASES = {
    "toulkork": "Toul Kork", "tuolkouk": "Toul Kork", "tuolkork": "Toul Kork",
    "saensokh": "Sen Sok", "sensok": "Sen Sok", "seansokh": "Sen Sok",
    "chamkarmon": "Chamkarmon", "chamkarmorn": "Chamkarmon",
    "boengkengkang": "Boeung Keng Kang", "boeungkengkang": "Boeung Keng Kang",
    "bkk": "Boeung Keng Kang", "bkk1": "Boeung Keng Kang",
    "daunpenh": "Daun Penh", "dounpenh": "Daun Penh",
    "meanchey": "Meanchey",
    "chraoychongvar": "Chroy Changvar", "chroychangvar": "Chroy Changvar",
    "chroychongvar": "Chroy Changvar",
    "ruesseikaev": "Russey Keo", "russeykeo": "Russey Keo",
    "chbarampov": "Chbar Ampov",
    "praekpnov": "Prek Pnov", "prekpnov": "Prek Pnov",
    "dangkao": "Dangkao", "dangkor": "Dangkao",
    "pousenchey": "Pur Senchey", "pursenchey": "Pur Senchey",
    "prampirmeakkakra": "Prampi Makara", "prampimakara": "Prampi Makara",
    "kamboul": "Kamboul",
    # These are sangkats, not khans. They map up to their parent khan so the
    # district field stays consistent across sources; the original name is
    # preserved separately as the commune.
    "tonlebassac": "Chamkarmon", "tonlebasak": "Chamkarmon",
    "toultumpung": "Chamkarmon", "toultompoung": "Chamkarmon",
    "tuoltumpung": "Chamkarmon",
}


# Some sites report the SANGKAT (commune) rather than the KHAN (district).
# harbor-property.com puts it in the URL: /house/detail/110586/chak-angrae-leu/condo
# The model uses khan, so sangkats are mapped up. The original value is kept
# as `commune`, which is finer-grained and may itself be a useful feature -
# BKK1 prices differ sharply from the rest of Chamkarmon.
SANGKAT_TO_KHAN = {
    # Chamkarmon
    "bkk1": "Boeung Keng Kang", "bkk2": "Boeung Keng Kang",
    "bkk3": "Boeung Keng Kang", "boeungkengkang": "Boeung Keng Kang",
    "tonlebassac": "Chamkarmon", "boeungtrobaek": "Chamkarmon",
    "boeungtrabek": "Chamkarmon", "toultumpung": "Chamkarmon",
    "toultumpungi": "Chamkarmon", "toultumpungii": "Chamkarmon",
    "phsardaeumthkov": "Chamkarmon", "olympic": "Chamkarmon",
    # Meanchey
    "chakangraeleu": "Meanchey", "chakangraekraom": "Meanchey",
    "boengtompun": "Meanchey", "boengtompuni": "Meanchey",
    "boengtompunii": "Meanchey", "stuengmeanchey": "Meanchey",
    "stuengmeancheyi": "Meanchey",
    # Sen Sok
    "phnompenhthmei": "Sen Sok", "teukthla": "Sen Sok", "khmuonh": "Sen Sok",
    "krangthnong": "Sen Sok", "obek kaam": "Sen Sok", "obekkaam": "Sen Sok",
    # Toul Kork
    "boeungkak": "Toul Kork", "boeungkaki": "Toul Kork",
    "boeungkakii": "Toul Kork", "teuklaak": "Toul Kork",
    "teuklaaki": "Toul Kork", "teuklaakii": "Toul Kork",
    "teuklaakiii": "Toul Kork", "phsardepou": "Toul Kork",
    "phsardepoui": "Toul Kork", "phsardepouii": "Toul Kork",
    # Daun Penh
    "srahchak": "Daun Penh", "watphnom": "Daun Penh", "phsarchas": "Daun Penh",
    "cheychumneas": "Daun Penh", "phsarthmei": "Daun Penh",
    "phsarthmeii": "Daun Penh", "chaktomuk": "Daun Penh",
    # Prampi Makara
    "vealvong": "Prampi Makara", "mittapheap": "Prampi Makara",
    "ourussei": "Prampi Makara", "orussei": "Prampi Makara",
    "monourom": "Prampi Makara",
    # Russey Keo
    "toulsangke": "Russey Keo", "chrangchamres": "Russey Keo",
    "svaypak": "Russey Keo", "kilomaetrlekh6": "Russey Keo",
    # Chroy Changvar
    "chroychangvar": "Chroy Changvar", "prekleap": "Chroy Changvar",
    "prektasek": "Chroy Changvar", "bakkheng": "Chroy Changvar",
    # Chbar Ampov
    "chbarampov": "Chbar Ampov", "chbarampovi": "Chbar Ampov",
    "niroth": "Chbar Ampov", "prekpra": "Chbar Ampov",
    # Pur Senchey
    "chaomchau": "Pur Senchey", "kakab": "Pur Senchey",
    "samraongkraom": "Pur Senchey", "phleungchehroteh": "Pur Senchey",
    # others
    "prekpnov": "Prek Pnov", "dangkao": "Dangkao", "kamboul": "Kamboul",
}


def normalise_district(raw: str | None) -> str | None:
    if not raw:
        return None
    key = re.sub(r"[^a-z0-9]", "", str(raw).lower())
    if key in DISTRICT_ALIASES:
        return DISTRICT_ALIASES[key]
    if key in SANGKAT_TO_KHAN:
        return SANGKAT_TO_KHAN[key]
    # try the longest alias contained in the string
    for alias in sorted(DISTRICT_ALIASES, key=len, reverse=True):
        if alias in key:
            return DISTRICT_ALIASES[alias]
    return str(raw).replace("-", " ").title()


# ========================================================================
# FIELD PARSERS
# ========================================================================

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_price(value: Any) -> int | None:
    """Parse common agency price formats into whole USD."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        amount = float(value)
        return int(amount) if 1_000 <= amount <= 50_000_000 else None

    raw = clean_text(str(value))
    low = raw.lower()
    if not raw or low in {"poa", "n/a", "-", "contact"} or "negotiab" in low:
        return None

    compact = raw.replace(",", "").replace(" ", "")
    multiplier = 1
    if re.search(r"\d(?:\.\d+)?k(?:usd)?$", compact, re.I):
        multiplier = 1_000
    elif re.search(r"\d(?:\.\d+)?m(?:usd)?$", compact, re.I):
        multiplier = 1_000_000

    match = re.search(r"(\d+(?:\.\d+)?)", compact)
    if not match:
        return None

    amount = float(match.group(1)) * multiplier
    return int(round(amount)) if 1_000 <= amount <= 50_000_000 else None


def parse_size(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    text = str(value).lower().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    number = float(match.group(1))
    if "sqft" in text or "sq ft" in text or "ft2" in text:
        number *= 0.092903
    return round(number, 2) if 5 <= number <= 2_000 else None


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def clean_text(text: Any) -> str:
    return re.sub(
        r"[\u200b\u200c\u200d\ufeff\u00a0\s]+",
        " ",
        str(text or ""),
    ).strip()


# ------------------------------------------------------------------ JSON-LD

# Elements that carry numbers which are NOT the listing price. Mortgage
# calculators are the worst offender: camrealtyservice.com ships one with a
# default loan amount, and every listing was read as $20,000 until these were
# stripped out first.
NOISE_SELECTORS = [
    "script", "style", "noscript", "nav", "header", "footer", "form",
    "[class*='calculator']", "[id*='calculator']",
    "[class*='mortgage']", "[id*='mortgage']",
    "[class*='loan']", "[id*='loan']",
    "[class*='amortization']", "[class*='similar']", "[class*='related']",
    "[class*='nearby']", "[class*='recommend']", "[class*='suggest']",
    "[class*='newsletter']", "[class*='subscribe']", "[class*='cookie']",
]

NOISE_TEXT_MARKERS = [
    "down payment", "loan amount", "total interest", "total payment",
    "monthly payment", "interest rate", "amortization", "loan term",
    "mortgage calculator", "similar properties", "related properties",
    "you may also like", "recently viewed",
]


def strip_noise(soup: BeautifulSoup) -> BeautifulSoup:
    """Remove calculators, related-listing blocks and chrome, in place."""
    for selector in NOISE_SELECTORS:
        for element in soup.select(selector):
            element.decompose()

    for element in soup.find_all(["div", "section", "aside", "table"]):
        try:
            text = element.get_text(" ", strip=True).lower()
        except Exception:
            continue
        if len(text) > 4000:
            continue                     # too big to be a widget
        hits = sum(marker in text for marker in NOISE_TEXT_MARKERS)
        if hits >= 2:
            element.decompose()
    return soup


def extract_json_ld(soup: BeautifulSoup) -> list[dict]:
    """schema.org blocks often carry price and area in clean form."""
    blocks: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            blocks.extend(d for d in data if isinstance(d, dict))
        elif isinstance(data, dict):
            blocks.append(data)
            graph = data.get("@graph")
            if isinstance(graph, list):
                blocks.extend(d for d in graph if isinstance(d, dict))
    return blocks


def price_from_json_ld(blocks: list[dict]) -> int | None:
    for block in blocks:
        for key in ("price", "lowPrice", "highPrice"):
            if key in block:
                value = parse_price(block[key])
                if value:
                    return value
        offers = block.get("offers")
        if isinstance(offers, dict):
            value = parse_price(offers.get("price"))
            if value:
                return value
        elif isinstance(offers, list):
            for offer in offers:
                if isinstance(offer, dict):
                    value = parse_price(offer.get("price"))
                    if value:
                        return value
    return None


# ------------------------------------------------- generic label/value pairs

LABEL_MAP = {
    "bedroom": "bedrooms", "bedrooms": "bedrooms", "bed": "bedrooms",
    "បន្ទប់គេង": "bedrooms",
    "bathroom": "bathrooms", "bathrooms": "bathrooms", "bath": "bathrooms",
    "បន្ទប់ទឹក": "bathrooms",
    "size": "size_m2", "area": "size_m2", "floor area": "size_m2",
    "interior size": "size_m2", "unit size": "size_m2", "ទំហំ": "size_m2",
    "net area": "size_m2", "gross area": "size_m2",
    "land area": "land_area_m2",
    "sale price": "price_usd", "price": "price_usd", "តម្លៃ": "price_usd",
    "property code": "property_code",
    "updated at": "updated_at", "listed at": "created_at",

    # A plain structured "Floor" label normally means the advertised unit's
    # floor. Building height must have an explicit total/building label.
    "floor": "unit_floor", "floor level": "unit_floor",
    "unit floor": "unit_floor", "level": "unit_floor", "ជាន់": "unit_floor",
    "total floors": "building_total_floors",
    "number of floors": "building_total_floors",
    "building floors": "building_total_floors",
    "total storeys": "building_total_floors",
    "number of storeys": "building_total_floors",

    "property type": "property_type_raw", "type": "property_type_raw",
    "district": "district", "khan": "district", "location": "location_text",
    "project": "project_name", "building": "project_name",
    "condition": "condition", "parking": "parking", "year built": "year_built",
    "property id": "property_code", "property id #": "property_code",
    "id": "property_code", "sub type": "property_type_raw",

    # Chinese labels commonly rendered by Harbor Property.
    "售价": "price_usd", "价格": "price_usd", "总价": "price_usd",
    "面积": "size_m2", "建筑面积": "size_m2", "套内面积": "size_m2",
    "房屋面积": "size_m2", "净面积": "size_m2",
    "卧室": "bedrooms", "房间": "bedrooms", "房数": "bedrooms",
    "浴室": "bathrooms", "卫生间": "bathrooms", "卫浴": "bathrooms",
    "楼层": "unit_floor", "所在楼层": "unit_floor",
    "总楼层": "building_total_floors", "楼高": "building_total_floors",
    "物业类型": "property_type_raw", "房屋类型": "property_type_raw",
}


def extract_pairs(scope: BeautifulSoup) -> dict[str, str]:
    """
    Collect label/value pairs from common property-detail markup.

    The caller passes the current property's main content only, after
    calculators, related listings and page chrome have been removed.
    """
    found: dict[str, str] = {}

    def record(label: str, value: str) -> None:
        normalized = clean_text(label).lower().rstrip(":")
        key = LABEL_MAP.get(normalized)
        if key and value:
            found.setdefault(key, clean_text(value))

    for dl in scope.find_all("dl"):
        dts, dds = dl.find_all("dt"), dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            record(dt.get_text(" ", strip=True), dd.get_text(" ", strip=True))

    for row in scope.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            record(
                cells[0].get_text(" ", strip=True),
                cells[1].get_text(" ", strip=True),
            )

    for element in scope.select("li, div, p"):
        label_el = element.select_one(".label, .title, .name, strong, b")
        value_el = element.select_one(".value, .val, .data, .text")
        if label_el and value_el and label_el is not value_el:
            record(
                label_el.get_text(" ", strip=True),
                value_el.get_text(" ", strip=True),
            )

    # Utility-CSS sites often use two adjacent spans with no semantic classes.
    for container in scope.find_all(["div", "li"]):
        spans = container.find_all("span", recursive=False)
        if len(spans) != 2:
            all_spans = container.find_all("span")
            if len(all_spans) == 2 and all_spans[0].parent is container:
                spans = all_spans
            else:
                continue

        label = clean_text(spans[0].get_text(" ", strip=True))
        value = clean_text(spans[1].get_text(" ", strip=True))

        if label and value and len(label) <= 35:
            record(label, value)

    return found


# Some sites identify specification tiles using icon filenames.
ICON_SPEC_MAP = {
    "size": "size_m2", "area": "size_m2", "net_area": "size_m2",
    "floor": "unit_floor", "level": "unit_floor", "unit_floor": "unit_floor",
    "total_floor": "building_total_floors",
    "total_floors": "building_total_floors",
    "building_floor": "building_total_floors",
    "bed": "bedrooms", "bedroom": "bedrooms",
    "bath": "bathrooms", "bathroom": "bathrooms",
    "parking": "parking", "car": "parking",
}


def extract_icon_specs(scope: BeautifulSoup) -> dict[str, str]:
    """Read specification tiles identified by an icon image filename."""
    found: dict[str, str] = {}

    for img in scope.find_all("img", src=True):
        match = re.search(r"/([a-z_]+)\.svg(?:\?.*)?$", img["src"].lower())
        if not match:
            continue

        key = ICON_SPEC_MAP.get(match.group(1))
        if not key:
            continue

        node = img
        for _ in range(4):
            node = node.find_parent(["div", "li"])
            if node is None:
                break

            spans = node.find_all("span")
            if len(spans) >= 2:
                value = clean_text(spans[-1].get_text(" ", strip=True))
                if value:
                    found.setdefault(key, value)
                break

    return found


# ========================================================================
# SAFE FIELD RECOVERY AND CONFLICT HANDLING
# ========================================================================

TRACKED_FIELDS = {
    "listing_type", "property_type", "price_usd", "size_m2",
    "bedrooms", "bathrooms", "unit_floor", "building_total_floors",
    "district", "province", "commune", "project_name",
}

NUMERIC_LIMITS: dict[str, tuple[float, float]] = {
    "price_usd": (1_000, 50_000_000),
    "size_m2": (5, 2_000),
    "bedrooms": (0, 15),
    "bathrooms": (0, 20),
    "unit_floor": (1, 100),
    "building_total_floors": (1, 150),
}


def source_priority(source: str | None) -> int:
    low = clean_text(source or "").lower()

    # APS Overview values are canonical for the current advertised unit.
    # ``Unit Size`` maps to size_m2 and ``Level`` maps to unit_floor, so both
    # must outrank stale URL/title/summary text.
    if "detail_structured_unit_size" in low or "overview_level" in low:
        return 80

    if any(token in low for token in (
        "site_structured", "detail_structured", "embedded_json",
        "json_ld", "detail_price", "icon_structured",
    )):
        return 60
    if "url" in low:
        return 40
    if "search_scope" in low:
        return 30
    if "title" in low:
        return 20
    if "description" in low or "overview" in low:
        return 10
    return 0


def append_conflict(record: dict[str, Any], field: str, message: str) -> None:
    """Append one conflict message without duplicating existing text."""
    key = f"{field}_conflict"
    existing = [
        part.strip()
        for part in clean_text(record.get(key) or "").split(";")
        if part.strip()
    ]
    incoming = [part.strip() for part in message.split(";") if part.strip()]

    for part in incoming:
        if part not in existing:
            existing.append(part)

    record[key] = "; ".join(existing)
    record["needs_manual_review"] = True


def refresh_review_flag(record: dict[str, Any]) -> None:
    """Recalculate the review flag from the conflict fields that remain."""
    record["needs_manual_review"] = any(
        key.endswith("_conflict") and bool(value)
        for key, value in record.items()
    )


def clear_conflict(record: dict[str, Any], field: str) -> None:
    """Remove a known false-positive conflict and refresh the review flag."""
    record.pop(f"{field}_conflict", None)
    refresh_review_flag(record)


def values_differ(field: str, left: Any, right: Any) -> bool:
    if field == "size_m2":
        try:
            left_value = float(left)
            right_value = float(right)
            tolerance = max(1.0, 0.02 * max(abs(left_value), abs(right_value)))
            return abs(left_value - right_value) > tolerance
        except (TypeError, ValueError):
            return clean_text(left) != clean_text(right)

    if field in {"price_usd", "bedrooms", "bathrooms", "unit_floor",
                 "building_total_floors"}:
        return parse_int(left) != parse_int(right)

    return clean_text(left).lower() != clean_text(right).lower()


def normalize_property_type(value: Any) -> str | None:
    """Return only recognised property types.

    Agency pages often contain generic label/value pairs such as ``Type = Name``.
    Treating unknown words as property types created false values like ``Name``.
    Unknown text is therefore preserved only in raw audit fields and is not used
    as the canonical ``property_type``.
    """
    text = clean_text(value)
    if not text:
        return None

    low = text.lower()
    if "penthouse" in low or "ផេនហោស៍" in text:
        return "Penthouse"
    if "condo" in low or "condominium" in low or "ខុនដូ" in text:
        return "Condo"
    if "apartment" in low or "អាផាតមិន" in text:
        return "Apartment"
    if "villa" in low or "វីឡា" in text:
        return "Villa"
    if ("flat" in low or "shophouse" in low or "shop house" in low
            or "ផ្ទះល្វែង" in text):
        return "Flat"
    # ``home`` is marketing language on condo listings (for example,
    # "smart home at Le Condé"), so only an explicit house term should
    # classify a record as House.
    if "house" in low or "ផ្ទះ" in text:
        return "House"
    if "land" in low or "ដី" in text:
        return "Land"
    if ("commercial" in low or "office" in low or "hotel" in low
            or "សណ្ឋាគារ" in text):
        return "Commercial"
    if "project" in low or "development" in low:
        return "Project"

    return None


def normalize_candidate(field: str, value: Any) -> Any:
    if value in (None, "", [], {}):
        return None

    if field == "price_usd":
        return parse_price(value)
    if field == "size_m2":
        return parse_size(value)
    if field in {"bedrooms", "bathrooms", "unit_floor",
                 "building_total_floors"}:
        return parse_int(value)
    if field == "property_type":
        return normalize_property_type(value)
    if field == "district":
        return normalise_district(clean_text(value))
    if field in {"listing_type", "province", "commune", "project_name"}:
        return clean_text(value) or None

    return value


def candidate_slot(source: str) -> str:
    low = source.lower()
    if "detail_structured" in low or "icon_structured" in low:
        return "detail"
    if "url" in low:
        return "url"
    if "title" in low:
        return "title"
    if "description" in low or "overview" in low:
        return "description"
    return "candidate"


def apply_candidate(
    record: dict[str, Any],
    field: str,
    value: Any,
    source: str,
    confidence: str,
    *,
    raw_text: str | None = None,
    compare_conflict: bool = True,
) -> None:
    """
    Apply one candidate using source priority.

    Weak prose extraction may set ``compare_conflict=False``. In that mode it
    can fill a missing value, but it cannot overwrite or flag a stronger
    structured/URL value. This prevents project descriptions mentioning
    several unit types from flagging nearly every listing.
    """
    normalized = normalize_candidate(field, value)
    if normalized is None:
        return

    if field in NUMERIC_LIMITS:
        minimum, maximum = NUMERIC_LIMITS[field]
        try:
            numeric = float(normalized)
        except (TypeError, ValueError):
            numeric = None

        if numeric is None or not (minimum <= numeric <= maximum):
            # An impossible parsed number is parser noise, not evidence that the
            # listing itself is inconsistent.  Keep it for diagnostics, but do
            # not turn every page with a stray ID/area number into manual review.
            record[f"{field}_invalid_value"] = normalized
            record[f"{field}_invalid_source"] = source
            if raw_text:
                record[f"{field}_invalid_text_raw"] = clean_text(raw_text)
            return

    slot = candidate_slot(source)
    record[f"{field}_{slot}_value"] = normalized
    record[f"{field}_{slot}_source"] = source
    if raw_text:
        record[f"{field}_{slot}_text_raw"] = clean_text(raw_text)

    current = record.get(field)
    current_source = clean_text(record.get(f"{field}_source") or "")

    if current in (None, "", [], {}):
        record[field] = normalized
        record[f"{field}_source"] = source
        record[f"{field}_confidence"] = confidence
        if raw_text:
            record[f"{field}_text_raw"] = clean_text(raw_text)
        return

    if field == "property_type":
        current_type = normalize_property_type(current)
        candidate_type = normalize_property_type(normalized)
        condo_family = {"Condo", "Apartment", "Penthouse"}

        if current_type in condo_family and candidate_type in condo_family:
            # Search URLs usually use the broad Condo category.  Apartment is
            # equivalent for this project, while Penthouse is a more specific
            # condo subtype.  These are refinements, not contradictions.
            if candidate_type == "Penthouse" and current_type != "Penthouse":
                record[f"{field}_previous_value"] = current
                record[f"{field}_previous_source"] = current_source or "unknown"
                record[field] = "Penthouse"
                record[f"{field}_source"] = source
                record[f"{field}_confidence"] = confidence
                if raw_text:
                    record[f"{field}_text_raw"] = clean_text(raw_text)
            elif (current_type == "Apartment" and candidate_type == "Condo"
                  and source_priority(source) > source_priority(current_source)):
                record[field] = "Condo"
                record[f"{field}_source"] = source
                record[f"{field}_confidence"] = confidence
                if raw_text:
                    record[f"{field}_text_raw"] = clean_text(raw_text)
            return

        if (current_type in condo_family
                and candidate_type not in condo_family
                and candidate_type is not None
                and ("title" in source.lower()
                     or source_priority(source) >= 60)
                and ("url" in current_source.lower()
                     or "search_scope" in current_source.lower())):
            # A filtered condo category can contain incorrectly categorised
            # houses, villas, land or commercial buildings.  An explicit title
            # or structured type is stronger evidence than the broad category.
            record[f"{field}_previous_value"] = current
            record[f"{field}_previous_source"] = current_source or "unknown"
            record[field] = candidate_type
            record[f"{field}_source"] = source
            record[f"{field}_confidence"] = confidence
            if raw_text:
                record[f"{field}_text_raw"] = clean_text(raw_text)
            append_conflict(
                record,
                field,
                f"{current_source or 'existing'}={current}; "
                f"reclassified by {source}={candidate_type}",
            )
            return

    if not values_differ(field, current, normalized):
        if source_priority(source) > source_priority(current_source):
            record[field] = normalized
            record[f"{field}_source"] = source
            record[f"{field}_confidence"] = confidence
            if raw_text:
                record[f"{field}_text_raw"] = clean_text(raw_text)
        return

    if not compare_conflict:
        # Preserve the weak candidate for audit, but do not replace or flag.
        return

    if source_priority(source) > source_priority(current_source):
        record[f"{field}_previous_value"] = current
        record[f"{field}_previous_source"] = current_source or "unknown"
        record[field] = normalized
        record[f"{field}_source"] = source
        record[f"{field}_confidence"] = confidence
        if raw_text:
            record[f"{field}_text_raw"] = clean_text(raw_text)
        append_conflict(
            record,
            field,
            f"{current_source or 'existing'}={current}; replaced by {source}={normalized}",
        )
    else:
        append_conflict(
            record,
            field,
            f"{source}={normalized}; kept {current_source or 'existing'}={current}",
        )


RoomResult = tuple[int, str] | None

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
    r"\b(\d{1,3})(?:st|nd|rd|th)\s+floor\b",
    r"\b(?:located|situated)\s+on\s+(?:the\s+)?"
    r"(\d{1,3})(?:st|nd|rd|th)?\s+floor\b",
    r"\bunit\s+(?:is\s+)?(?:located\s+)?on\s+(?:the\s+)?"
    r"(\d{1,3})(?:st|nd|rd|th)?\s+floor\b",
    r"\bon\s+(?:the\s+)?(\d{1,3})(?:st|nd|rd|th)?\s+floor\b",
    r"\bunit\s+floor\s*[:\-]?\s*(\d{1,3})(?:st|nd|rd|th)?\b",
    r"\bfloor\s+level\s*[:\-]?\s*(\d{1,3})(?:st|nd|rd|th)?\b",
    r"\bfloor\s*[:\-]\s*(\d{1,3})(?:st|nd|rd|th)?\b",
    r"\bunit\s+(\d{1,3})\s*[Ff]\b",
    r"ជាន់?ទី\s*(\d{1,3})",
    r"ជាន់\s*[:\-]?\s*(\d{1,3})",
]

BUILDING_FLOOR_PATTERNS = [
    r"\b(\d{1,3})\s*(?:storey|storeys|story|stories)\s+high\b",
    r"\b(\d{1,3})\s*[- ]\s*(?:storey|storeys|story|stories)"
    r"\s+(?:building|tower|condominium|development)\b",
    r"\b(?:building|tower)\s+(?:has|with)\s+(\d{1,3})\s+floors?\b",
    r"\btotal\s+(?:floors?|storeys?)\s*[:\-]?\s*(\d{1,3})\b",
    r"\bnumber\s+of\s+(?:floors?|storeys?)\s*[:\-]?\s*(\d{1,3})\b",
]

FLOOR_CONTEXT_BEFORE_ROOM = re.compile(
    r"(?:floor|level|storey|story|ជាន់ទី|ជាន់)\s*[:\-]?\s*$",
    re.IGNORECASE,
)


def _room_from_patterns(
    text: Any,
    patterns: list[str],
    maximum: int,
) -> RoomResult:
    cleaned = clean_text(text or "")
    if not cleaned:
        return None

    for pattern in patterns:
        for match in re.finditer(pattern, cleaned, re.IGNORECASE):
            prefix = cleaned[max(0, match.start() - 30):match.start()]
            if FLOOR_CONTEXT_BEFORE_ROOM.search(prefix):
                continue

            value = int(match.group(1))
            if 0 <= value <= maximum:
                return value, match.group(0)

    return None


def extract_bedrooms(text: Any) -> RoomResult:
    result = _room_from_patterns(text, BEDROOM_PATTERNS, 15)
    if result is not None:
        return result

    cleaned = clean_text(text or "")
    studio = re.search(r"\bstudio\b", cleaned, re.IGNORECASE)
    if studio:
        return 0, studio.group(0)

    return None


def extract_bathrooms(text: Any) -> RoomResult:
    return _room_from_patterns(text, BATHROOM_PATTERNS, 20)


def _first_pattern(
    text: Any,
    patterns: list[str],
    minimum: int,
    maximum: int,
) -> RoomResult:
    cleaned = clean_text(text or "")
    if not cleaned:
        return None

    for pattern in patterns:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if not match:
            continue

        value = int(match.group(1))
        if minimum <= value <= maximum:
            return value, match.group(0)

    return None


def extract_unit_floor(text: Any) -> RoomResult:
    return _first_pattern(text, UNIT_FLOOR_PATTERNS, 1, 100)


def extract_building_total_floors(text: Any) -> RoomResult:
    return _first_pattern(text, BUILDING_FLOOR_PATTERNS, 1, 150)


def infer_property_type(text: Any) -> tuple[str, str] | None:
    cleaned = clean_text(text or "")
    if not cleaned:
        return None

    patterns = [
        ("Penthouse", r"\bpenthouse\b|ផេនហោស៍"),
        ("Condo", r"\b(?:condo|condominium)\b|ខុនដូ"),
        ("Apartment", r"\bapartment\b|អាផាតមិន"),
        ("Villa", r"\bvilla\b|វីឡា"),
        ("Flat", r"\b(?:flat|shophouse|shop house)\b|ផ្ទះល្វែង"),
        # ``home`` alone is not a property type; condo ads often use it
        # as lifestyle wording such as "smart home".
        ("House", r"\bhouse\b|ផ្ទះ"),
        ("Land", r"\bland\b|ដី"),
        ("Commercial", r"\b(?:commercial|office|hotel)\b|សណ្ឋាគារ"),
    ]

    for property_type, pattern in patterns:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            return property_type, match.group(0)

    return None


def recover_from_text(
    record: dict[str, Any],
    title: str,
    description: str,
    source_key: str,
) -> None:
    """
    Recover missing values from exact title text and broader description text.

    Title disagreements are review-worthy. Description values are used only
    to fill gaps because agency/project descriptions frequently mention
    several unit configurations in the same paragraph.
    """
    for text_value, kind, confidence, compare_conflict in (
        (title, "title", "medium", True),
        (description, "description", "low", False),
    ):
        if not text_value:
            continue

        source = f"{source_key}_{kind}"
        extractors = {
            "bedrooms": extract_bedrooms,
            "bathrooms": extract_bathrooms,
            "unit_floor": extract_unit_floor,
            "building_total_floors": extract_building_total_floors,
        }

        for field, extractor in extractors.items():
            result = extractor(text_value)
            if result:
                value, matched = result
                apply_candidate(
                    record,
                    field,
                    value,
                    source,
                    confidence,
                    raw_text=matched,
                    compare_conflict=compare_conflict,
                )

        property_result = infer_property_type(text_value)
        if property_result:
            value, matched = property_result
            apply_candidate(
                record,
                "property_type",
                value,
                source,
                confidence,
                raw_text=matched,
                compare_conflict=(kind == "title"),
            )


# ========================================================================
# PRICE, DESCRIPTION AND RECORD HELPERS
# ========================================================================

PRICE_SELECTORS = [
    "[itemprop='price']", "[class*='property-price']", "[class*='item-price']",
    "[class*='listing-price']", "[class*='price-value']", "[class='price']",
    "[class*='price']",
]


def size_from_json_ld(blocks: list[dict]) -> float | None:
    keys = (
        "floorSize", "floorArea", "area", "size", "livingArea",
    )

    def parse_area(value: Any) -> float | None:
        if isinstance(value, dict):
            value = value.get("value") or value.get("name")
        return parse_size(value)

    for block in blocks:
        for key in keys:
            if key in block:
                size = parse_area(block[key])
                if size:
                    return size
    return None


def find_price(
    soup: BeautifulSoup,
    body_text: str,
    json_ld_blocks: list[dict] | None = None,
) -> tuple[int | None, str | None]:
    """Locate the current listing price without using calculator defaults."""
    blocks = json_ld_blocks or []
    price = price_from_json_ld(blocks)
    if price:
        return price, "json_ld_price"

    meta = soup.find("meta", attrs={"property": "product:price:amount"})
    if meta and meta.get("content"):
        price = parse_price(meta["content"])
        if price:
            return price, "detail_price_meta"

    for selector in PRICE_SELECTORS:
        for element in soup.select(selector):
            text = clean_text(element.get_text(" ", strip=True))
            if not text or len(text) > 40:
                continue
            price = parse_price(text)
            if price and price >= 10_000:
                return price, "detail_price_element"

    currency_tokens = re.findall(
        r"(?:US\$|USD|\$)\s*[\d,]+(?:\.\d+)?"
        r"|[\d,]+(?:\.\d+)?\s*(?:USD|US\$)",
        body_text,
        re.IGNORECASE,
    )
    amounts = [parse_price(match) for match in currency_tokens]
    amounts = [value for value in amounts if value and 10_000 <= value <= 20_000_000]

    return (max(amounts), "detail_price_body") if amounts else (None, None)


BOILERPLATE_MARKERS = [
    "leading real estate platform", "since opening in", "we have grown",
    "market leader", "all rights reserved", "cookie", "privacy policy",
    "terms and conditions", "subscribe to our newsletter", "follow us on",
    "our mission", "about us", "contact us today for more information about our",
    "loan calculation", "follow share", "details facility location",
    "down payment", "loan amount", "total interest", "total payment",
    "monthly payment", "amortization", "add to favourite",
    "share this property", "mortgage calculator", "similar properties",
    "related properties", "recently viewed",
]

PROPERTY_WORDS = [
    "bedroom", "bathroom", "sqm", "m2", "m²", "square", "floor", "balcony",
    "furnished", "condo", "apartment", "unit", "located", "swimming",
    "parking", "gym", "view", "kitchen", "price", "sale", "district",
]

DESCRIPTION_HEADINGS = {
    "description", "property description", "overview", "property overview",
    "about this property", "about the property", "details", "property details",
}


def is_boilerplate(text: str) -> bool:
    low = text.lower()
    return any(marker in low for marker in BOILERPLATE_MARKERS)


def extract_title(soup: BeautifulSoup) -> str | None:
    """h1, then og:title, then <title>."""
    heading = soup.find("h1")
    if heading:
        text = clean_text(heading.get_text(" ", strip=True))
        if text:
            return text[:300]

    meta = soup.find("meta", property="og:title")
    if meta and meta.get("content"):
        return clean_text(meta["content"])[:300]

    if soup.title and soup.title.string:
        text = clean_text(soup.title.string)
        text = re.split(r"\s*[|–]\s*", text)[0]
        if len(text) > 5:
            return text[:300]

    return None


def extract_description(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """Extract the current listing's Description/Overview section safely."""
    selectors = [
        ("[id*='property-description' i]", "property_description_section"),
        ("[class*='property-description' i]", "property_description_section"),
        ("[id*='description' i]", "description_section"),
        ("[class*='description' i]", "description_section"),
        ("[id*='overview' i]", "overview_section"),
        ("[class*='overview' i]", "overview_section"),
        ("[id*='property-detail' i]", "property_details_section"),
        ("[class*='property-detail' i]", "property_details_section"),
        ("article", "article"),
    ]

    candidates: list[tuple[int, int, str, str]] = []

    for selector, source in selectors:
        for block in soup.select(selector):
            text = clean_text(block.get_text(" ", strip=True))
            if not (80 <= len(text) <= 8_000) or is_boilerplate(text):
                continue

            low = text.lower()
            score = sum(word in low for word in PROPERTY_WORDS)
            if score >= 2:
                candidates.append((score, -len(text), text[:5000], source))

    if candidates:
        candidates.sort(reverse=True)
        _, _, text, source = candidates[0]
        return text, source

    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "strong"]):
        heading_text = clean_text(heading.get_text(" ", strip=True)).lower().strip(" :")
        if heading_text not in DESCRIPTION_HEADINGS:
            continue

        collected: list[str] = []
        for sibling in heading.find_next_siblings():
            if getattr(sibling, "name", None) in {"h1", "h2", "h3", "h4", "h5"}:
                break
            text = clean_text(sibling.get_text(" ", strip=True))
            if text:
                collected.append(text)
            if sum(len(item) for item in collected) >= 5000:
                break

        combined = clean_text(" ".join(collected))
        if len(combined) >= 80 and not is_boilerplate(combined):
            source = "overview_heading" if "overview" in heading_text else "description_heading"
            return combined[:5000], source

    paragraph_candidates: list[tuple[int, int, str]] = []
    for element in soup.find_all("p"):
        text = clean_text(element.get_text(" ", strip=True))
        if not (80 <= len(text) <= 4_000) or is_boilerplate(text):
            continue
        score = sum(word in text.lower() for word in PROPERTY_WORDS)
        if score >= 2:
            paragraph_candidates.append((score, len(text), text))

    if paragraph_candidates:
        paragraph_candidates.sort(key=lambda item: (-item[0], -item[1]))
        return paragraph_candidates[0][2][:5000], "property_paragraph"

    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        text = clean_text(meta["content"])
        if len(text) > 40 and not is_boilerplate(text):
            return text[:5000], "meta_description"

    return None, None


def choose_main_scope(soup: BeautifulSoup) -> BeautifulSoup:
    selectors = [
        "main", "[class*='property-detail' i]", "[id*='property-detail' i]",
        "[class*='listing-detail' i]", "article",
    ]
    for selector in selectors:
        scope = soup.select_one(selector)
        if scope is not None:
            return scope
    return soup



def extract_heading_section(
    soup: BeautifulSoup,
    headings: set[str],
    *,
    max_chars: int = 5000,
) -> tuple[str | None, str | None]:
    """Collect text after a named heading until the next section heading."""
    normalized = {clean_text(item).lower().strip(" :") for item in headings}

    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "strong", "b"]):
        name = clean_text(heading.get_text(" ", strip=True)).lower().strip(" :")
        if name not in normalized:
            continue

        collected: list[str] = []
        for sibling in heading.find_next_siblings():
            if getattr(sibling, "name", None) in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                break
            value = clean_text(sibling.get_text(" ", strip=True))
            if value:
                collected.append(value)
            if sum(len(item) for item in collected) >= max_chars:
                break

        combined = clean_text(" ".join(collected))
        if combined:
            return combined[:max_chars], name.replace(" ", "_") + "_heading"

        # Some themes put the section body inside the heading's parent.
        parent = heading.parent
        if parent is not None:
            parent_text = clean_text(parent.get_text(" ", strip=True))
            if parent_text.lower().startswith(name) and len(parent_text) > len(name) + 20:
                return parent_text[len(name):].strip(" :-")[:max_chars], name.replace(" ", "_") + "_container"

    return None, None


def find_text_label_value(
    soup: BeautifulSoup,
    labels: tuple[str, ...],
    *,
    max_value_chars: int = 200,
    allow_body_fallback: bool = True,
) -> str | None:
    """Find a value adjacent to an exact human-readable label."""
    wanted = {clean_text(label).lower().strip(" :") for label in labels}

    for element in soup.find_all(["dt", "th", "span", "div", "p", "li", "strong", "b"]):
        label = clean_text(element.get_text(" ", strip=True)).lower().strip(" :")
        if label not in wanted:
            continue

        candidates = []
        sibling = element.find_next_sibling()
        if sibling is not None:
            candidates.append(sibling)

        parent = element.parent
        if parent is not None:
            for child in parent.find_all(recursive=False):
                if child is not element:
                    candidates.append(child)

        for candidate in candidates:
            value = clean_text(candidate.get_text(" ", strip=True))
            if value and value.lower().strip(" :") not in wanted and len(value) <= max_value_chars:
                return value

    if not allow_body_fallback:
        return None

    body = clean_text(soup.get_text(" ", strip=True))
    label_pattern = "|".join(re.escape(label) for label in sorted(labels, key=len, reverse=True))
    match = re.search(
        rf"(?:{label_pattern})\s*[:：-]?\s*([^|;]{{1,{max_value_chars}}}?)(?=\s+(?:Bedrooms?|Bathrooms?|Unit Size|Net Area|Gross Area|Level|Floor|Price|Property ID|Sub Type|Updated)\b|$)",
        body,
        re.IGNORECASE,
    )
    return clean_text(match.group(1)) if match else None


def extract_price_tokens(text_value: str) -> list[int]:
    tokens = re.findall(
        r"(?:US\$|USD|\$)\s*[\d,]+(?:\.\d+)?"
        r"|[\d,]+(?:\.\d+)?\s*(?:USD|US\$)",
        clean_text(text_value),
        re.IGNORECASE,
    )
    prices = [parse_price(token) for token in tokens]
    return [price for price in prices if price is not None]


def extract_size_near_label(text_value: str) -> tuple[float | None, str | None]:
    text_value = clean_text(text_value)
    patterns = [
        r"(?:net area|unit size|interior size|floor area|size|area|建筑面积|套内面积|面积)\s*[:：-]?\s*([\d,.]+)\s*(m²|m2|sqm|sq\.?\s*m|㎡)",
        r"([\d,.]+)\s*(m²|m2|sqm|sq\.?\s*m|㎡)\s*(?:net area|unit size|interior size|floor area)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text_value, re.IGNORECASE)
        if match:
            raw = f"{match.group(1)} {match.group(2)}"
            return parse_size(raw), match.group(0)
    return None, None


def best_current_property_scope(soup: BeautifulSoup, title: str | None) -> BeautifulSoup:
    """Choose the smallest ancestor that looks like the current property card."""
    heading = soup.find("h1")
    if heading is None and title:
        heading = soup.find(
            lambda tag: getattr(tag, "name", None) in {"h2", "h3"}
            and clean_text(tag.get_text(" ", strip=True)) == clean_text(title)
        )
    if heading is None:
        return choose_main_scope(soup)

    candidates: list[tuple[int, int, Any]] = []
    node = heading
    for depth in range(8):
        node = node.parent
        if node is None:
            break
        value = clean_text(node.get_text(" ", strip=True))
        low = value.lower()
        score = 0
        for marker in (
            "property id", "bedrooms", "bathrooms", "net area",
            "unit size", "description", "price", "for sale",
        ):
            if marker in low:
                score += 1
        if score:
            candidates.append((score, -len(value), node))

    if not candidates:
        return choose_main_scope(soup)

    candidates.sort(reverse=True, key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _walk_json(node: Any, depth: int = 0):
    if depth > 30:
        return
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_json(value, depth + 1)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_json(value, depth + 1)


def extract_script_json(html: str) -> list[Any]:
    """Parse JSON script blocks and simple global-state assignments."""
    soup = BeautifulSoup(html, "html.parser")
    objects: list[Any] = []

    for script in soup.find_all("script"):
        raw = script.string or script.get_text("", strip=False)
        if not raw:
            continue
        stripped = raw.strip()

        if script.get("type") in {"application/json", "application/ld+json"} or stripped.startswith(("{", "[")):
            try:
                objects.append(json.loads(stripped))
                continue
            except (json.JSONDecodeError, TypeError):
                pass

        for marker in ("window.__NUXT__", "window.__INITIAL_STATE__", "window.__PRELOADED_STATE__", "__NEXT_DATA__"):
            position = stripped.find(marker)
            if position < 0:
                continue
            brace = stripped.find("{", position)
            if brace < 0:
                continue
            try:
                value, _ = json.JSONDecoder().raw_decode(stripped[brace:])
                objects.append(value)
            except json.JSONDecodeError:
                pass

    return objects


def select_json_listing(html: str, listing_id: str | None) -> dict[str, Any] | None:
    """Find the embedded JSON dictionary that most resembles this listing."""
    target = clean_text(listing_id or "")
    candidates: list[tuple[int, dict[str, Any]]] = []
    id_keys = {"id", "houseid", "listingid", "propertyid", "house_id", "listing_id"}
    signal_keys = {
        "price", "saleprice", "sellingprice", "area", "size", "floorarea",
        "bedroom", "bedrooms", "bathroom", "bathrooms", "title", "name",
        "description", "desc",
    }

    for root in extract_script_json(html):
        for item in _walk_json(root):
            lowered = {str(key).lower(): value for key, value in item.items()}
            score = len(set(lowered) & signal_keys)
            for key in id_keys:
                if key in lowered and target and clean_text(lowered[key]) == target:
                    score += 30
            if score >= 3:
                candidates.append((score, item))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def first_json_value(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    lowered = {str(key).lower(): value for key, value in item.items()}
    for key in keys:
        if key.lower() in lowered and lowered[key.lower()] not in (None, "", [], {}):
            return lowered[key.lower()]
    return None

def blank_record(source: str) -> dict[str, Any]:
    record: dict[str, Any] = {
        "listing_id": None,
        "source": source,
        "listing_type": "sale",
        "listing_type_source": "search_scope",
        "price_usd": None,
        "size_m2": None,
        "land_area_m2": None,
        "bedrooms": None,
        "bathrooms": None,
        "unit_floor": None,
        "building_total_floors": None,
        "property_type": "Condo",
        "property_type_raw": None,
        "property_type_source": "search_scope",
        "district": None,
        "commune": None,
        "location_text": None,
        "province": "Phnom Penh",
        "province_source": "search_scope",
        "project_name": None,
        "latitude": None,
        "longitude": None,
        "title": None,
        "description": None,
        "description_source": None,
        "created_at": None,
        "condition": None,
        "parking": None,
        "year_built": None,
        "property_code": None,
        "price_original_usd": None,
        "price_reduced": None,
        "display_as_project": False,
        "needs_manual_review": False,
        "detail_scraped": False,
        "detail_parsed_at": None,
        "url": None,
        "scraped_at": now_iso(),
    }
    return record


# ========================================================================
# ADAPTERS
# ========================================================================

class Adapter:
    """A site adapter defines its URLs and can override detail parsing."""

    name: str = ""
    domain: str = ""
    search_url: str = ""
    pagination: str = "query_page"
    per_page: int = 20
    expected_total: int | None = None
    needs_browser: bool = False
    page_url_known: bool = False

    @property
    def source_key(self) -> str:
        return self.name.replace(".", "_")

    def page_url(self, page: int) -> str:
        if page == 1 or self.pagination == "none":
            return self.search_url
        parts = urlparse(self.search_url)
        if self.pagination == "query_page":
            query = dict(parse_qsl(parts.query, keep_blank_values=True))
            query["page"] = str(page)
            return urlunparse(parts._replace(query=urlencode(query)))
        path = parts.path.rstrip("/")
        return urlunparse(parts._replace(path=f"{path}/page/{page}"))

    def is_listing_url(self, url: str) -> bool:
        raise NotImplementedError

    def listing_id(self, url: str) -> str | None:
        match = re.search(r"(\d{3,})/?$", url.rstrip("/"))
        return match.group(1) if match else None

    def detail_cache_key(self, url: str) -> str | None:
        """Filename key for existing cached detail HTML."""
        return self.listing_id(url)

    def from_url(self, url: str) -> dict[str, Any]:
        return {}

    def apply_url_fields(self, record: dict[str, Any], url: str) -> None:
        for field, value in self.from_url(url).items():
            if field in TRACKED_FIELDS:
                apply_candidate(
                    record,
                    field,
                    value,
                    f"{self.source_key}_url",
                    "high",
                )
            elif value not in (None, "", [], {}):
                record[field] = value

    def parse_detail(self, html: str, url: str) -> dict[str, Any] | None:
        """Safe default parser for WordPress and utility-CSS agency pages."""
        original_soup = BeautifulSoup(html, "html.parser")
        json_ld_blocks = extract_json_ld(original_soup)
        title = extract_title(original_soup)

        soup = BeautifulSoup(html, "html.parser")
        strip_noise(soup)
        scope = choose_main_scope(soup)
        body_text = clean_text(scope.get_text(" ", strip=True))

        record = blank_record(self.name)
        record["url"] = url
        record["listing_id"] = f"{self.name}_{self.listing_id(url) or ''}"
        self.apply_url_fields(record, url)

        if title:
            record["title"] = title

        description, description_source = extract_description(scope)
        if description:
            record["description"] = description
            record["description_source"] = description_source

        pairs = extract_pairs(scope)
        icons = extract_icon_specs(scope)
        for key, value in icons.items():
            pairs.setdefault(key, value)

        structured_source = f"{self.source_key}_detail_structured"

        for field in (
            "bedrooms", "bathrooms", "unit_floor",
            "building_total_floors", "size_m2",
        ):
            if pairs.get(field):
                apply_candidate(
                    record,
                    field,
                    pairs[field],
                    structured_source,
                    "high",
                    raw_text=pairs[field],
                )

        if pairs.get("property_type_raw"):
            raw_property_type = clean_text(pairs["property_type_raw"])
            if normalize_property_type(raw_property_type):
                record["property_type_raw"] = raw_property_type
                apply_candidate(
                    record,
                    "property_type",
                    raw_property_type,
                    structured_source,
                    "high",
                    raw_text=raw_property_type,
                )
            else:
                record["property_type_invalid_raw"] = raw_property_type

        if pairs.get("district"):
            apply_candidate(
                record,
                "district",
                pairs["district"],
                structured_source,
                "high",
                raw_text=pairs["district"],
            )

        for field in (
            "project_name", "location_text", "property_code", "condition",
            "parking", "year_built", "land_area_m2",
        ):
            if pairs.get(field):
                record[field] = clean_text(pairs[field])

        if pairs.get("updated_at"):
            record["created_at"] = record.get("created_at") or pairs["updated_at"]
        if pairs.get("created_at"):
            record["created_at"] = record.get("created_at") or pairs["created_at"]

        if pairs.get("price_usd"):
            apply_candidate(
                record,
                "price_usd",
                pairs["price_usd"],
                structured_source,
                "high",
                raw_text=pairs["price_usd"],
            )

        price, price_source = find_price(soup, body_text, json_ld_blocks)
        if price is not None and price_source:
            apply_candidate(
                record,
                "price_usd",
                price,
                f"{self.source_key}_{price_source}",
                "high" if "body" not in price_source else "medium",
            )

        json_size = size_from_json_ld(json_ld_blocks)
        if json_size is not None:
            apply_candidate(
                record,
                "size_m2",
                json_size,
                f"{self.source_key}_json_ld",
                "high",
            )

        recover_from_text(
            record,
            title or "",
            description or "",
            self.source_key,
        )

        transaction_text = clean_text(f"{title or ''} {description or ''}").lower()
        has_rent = bool(re.search(r"\bfor rent\b|\bper month\b|/month", transaction_text))
        has_sale = bool(re.search(r"\bfor sale\b|\bsale\b", transaction_text))
        if has_rent and not has_sale:
            apply_candidate(
                record,
                "listing_type",
                "rent",
                f"{self.source_key}_description",
                "medium",
            )
        elif has_rent and has_sale:
            apply_candidate(
                record,
                "listing_type",
                "sale/rent",
                f"{self.source_key}_description",
                "medium",
            )

        unit_floor = parse_int(record.get("unit_floor"))
        building_floors = parse_int(record.get("building_total_floors"))
        if unit_floor is not None and building_floors is not None and unit_floor > building_floors:
            append_conflict(
                record,
                "unit_floor",
                f"unit_floor={unit_floor} exceeds building_total_floors={building_floors}",
            )

        record["display_as_project"] = bool(
            normalize_property_type(record.get("property_type")) == "Project"
        )
        record["detail_scraped"] = True
        record["detail_parsed_at"] = now_iso()

        # Keep incomplete Bronze records for review, but reject empty shells.
        meaningful = any(record.get(field) not in (None, "") for field in (
            "title", "price_usd", "size_m2", "description",
        ))
        return record if meaningful else None


# ------------------------------------------------------------------------
# KHPropertyHub-specific canonicalisation
# ------------------------------------------------------------------------

def _kh_title_transaction_type(title: Any) -> str | None:
    """Classify transaction type from the current KHPropertyHub title.

    The filtered search scope is sale, while descriptions frequently mention
    rental yield, current tenants or possible monthly rent.  Description text
    is therefore only a hint.  An explicit current-page title can override the
    search scope.
    """
    cleaned = clean_text(title or "")
    if not cleaned:
        return None

    low = cleaned.lower()
    # Do not treat investment phrases as a rental listing.
    low_for_rent = re.sub(
        r"\brental\s+(?:income|return|yield)\b|\brent\s+return\b",
        " ",
        low,
    )

    has_sale = bool(re.search(
        r"\bfor\s+sale\b|\burgent\s+sale\b|\bhot\s+sale\b|"
        r"\bsale\b|\bfor\s+sell\b|\bsell\b|លក់",
        low,
        re.IGNORECASE,
    ))
    has_rent = bool(re.search(
        r"\bfor\s+rent\b|\brent\s+only\b|\brental\s+price\b|"
        r"\bprice\s*(?:for|:)?\s*rent\b|\brent\b|តម្លៃជួល|ជួល",
        low_for_rent,
        re.IGNORECASE,
    ))

    if has_sale and has_rent:
        return "sale/rent"
    if has_rent:
        return "rent"
    if has_sale:
        return "sale"
    return None


def _kh_title_bedroom_options(title: Any) -> list[int]:
    """Return explicit bedroom options from a KHPropertyHub title.

    The parser is deliberately strict.  Project numbers such as ``Time Square
    11`` and bathroom counts such as ``3 bedrooms 4 bathrooms`` must never be
    interpreted as extra bedroom options.
    """
    cleaned = clean_text(title or "")
    if not cleaned:
        return []

    options: set[int] = set()
    if re.search(r"\bstudio\b", cleaned, re.IGNORECASE):
        options.add(0)

    # Number directly attached to a bedroom label: ``2 Bedroom``, ``2BR``.
    number_first_patterns = (
        r"(?<!\d)(\d{1,2})\s*[- ]?\s*(?:bed(?:room)?s?|br|bdr)\b",
        r"(?<!\d)(\d{1,2})\s*បន្ទប់គេង",
    )
    for pattern in number_first_patterns:
        for match in re.finditer(pattern, cleaned, re.IGNORECASE):
            value = int(match.group(1))
            if 0 <= value <= 10:
                options.add(value)

    # Label-first forms are accepted only at the beginning of a field or with
    # punctuation.  This prevents ``3 bedrooms 4 bathrooms`` from matching
    # the ``4`` after the word ``bedrooms``.
    label_first_patterns = (
        r"(?:^|[|•,;(\[])\s*(?:bed(?:room)?s?)\s*[:\-]\s*(\d{1,2})\b",
        r"(?:^|[|•,;(\[])\s*បន្ទប់គេង\s*[:\-]\s*(\d{1,2})",
    )
    for pattern in label_first_patterns:
        for match in re.finditer(pattern, cleaned, re.IGNORECASE):
            value = int(match.group(1))
            if 0 <= value <= 10:
                options.add(value)

    # Explicit option lists: ``1/2/3 bedrooms`` or ``studio/1/2 bedrooms``.
    # All numeric tokens must be plausible bedroom counts.  This rejects a
    # project name such as ``Time Square 11 /1Bedroom`` because 11 is not a
    # plausible option for the target condo dataset.
    option_list_re = re.compile(
        r"(?:\bstudio\s*/\s*)?"
        r"(\d{1,2}(?:\s*/\s*\d{1,2})+)"
        r"\s*(?:bed(?:room)?s?|br)\b",
        re.IGNORECASE,
    )
    for match in option_list_re.finditer(cleaned):
        tokens = [int(token) for token in re.findall(r"\d{1,2}", match.group(1))]
        if tokens and all(0 <= value <= 10 for value in tokens):
            options.update(tokens)
            prefix = cleaned[max(0, match.start() - 10):match.start()]
            if re.search(r"studio\s*/\s*$", prefix, re.IGNORECASE):
                options.add(0)

    return sorted(options)

def _kh_title_property_type(title: Any) -> str | None:
    """Classify explicit KHPropertyHub title types without marketing traps."""
    cleaned = clean_text(title or "")
    if not cleaned:
        return None
    low = cleaned.lower()

    condo_context = bool(re.search(
        r"\b(?:condo|condominium|apartment|residence|unit|studio|"
        r"\d{1,2}\s*(?:bed(?:room)?s?|br))\b|ខុនដូ|អាផាតមិន|បន្ទប់គេង",
        cleaned,
        re.IGNORECASE,
    ))

    # These are high-rise unit names, not landed villas.
    if re.search(r"\b(?:sky|flat)\s+villa\b", low):
        return "Penthouse"
    if re.search(r"\bpenthouse\b|ផេនហោស៍", cleaned, re.IGNORECASE):
        return "Penthouse"

    # Strong commercial words remain authoritative even when the broad search
    # URL says Condo.
    if re.search(r"\b(?:office|commercial)\b", low):
        return "Commercial"
    if re.search(r"\b(?:shophouse|shop\s+house)\b|ផ្ទះល្វែង|ផ្ទះអាជីវកម្ម", cleaned, re.IGNORECASE):
        return "Flat"

    # ``Park Land Condo`` is a project name, not a land listing.  Reclassify
    # only when the title explicitly advertises land/plot for sale.
    explicit_land = bool(re.search(
        r"\bland\s+(?:for\s+(?:sale|sell)|sale|plot)\b|"
        r"\b(?:plot|parcel)\s+of\s+land\b|"
        r"ដី\s*(?:លក់|សម្រាប់លក់)",
        cleaned,
        re.IGNORECASE,
    ))
    if explicit_land:
        return "Land"

    # Hotel residences and hotel-branded apartments are still individual
    # condo units when the title advertises a unit/bedroom/studio.
    if re.search(r"\bhotel\b|សណ្ឋាគារ", cleaned, re.IGNORECASE):
        has_building_context = bool(re.search(
            r"\b(?:entire|building)\s+hotel\b|"
            r"\bhotel\s+(?:building|for\s+(?:sale|sell))\b|"
            r"អគារសណ្ឋាគារ",
            cleaned,
            re.IGNORECASE,
        ))
        if condo_context and not has_building_context:
            return "Condo"
        return "Commercial"

    if re.search(r"\bvilla\b|វីឡា", cleaned, re.IGNORECASE):
        return "Villa"

    # Do not classify the Khmer word for house when it appears in ordinary
    # phrases such as ``furniture in the home``.  Require an explicit property
    # sale phrase, and let clear condo context win.
    explicit_house = bool(re.search(
        r"\bhouse\s+(?:for\s+(?:sale|sell)|sale|urgent\s+sale)\b|"
        r"ផ្ទះ\s*(?:លក់|សម្រាប់លក់|បន្ទាន់|វីឡា)",
        cleaned,
        re.IGNORECASE,
    ))
    if explicit_house and not condo_context:
        return "House"

    if condo_context:
        return "Condo"

    return None

def _kh_set_canonical(
    record: dict[str, Any],
    field: str,
    value: Any,
    source: str,
    *,
    raw_text: str | None = None,
    mismatch_field: str | None = None,
) -> None:
    """Set a resolved KHPropertyHub value without creating a conflict."""
    normalized = normalize_candidate(field, value)
    if normalized is None:
        return

    current = record.get(field)
    current_source = record.get(f"{field}_source")
    if current not in (None, "", [], {}) and values_differ(field, current, normalized):
        key = mismatch_field or f"{field}_reference_mismatch"
        record[key] = (
            f"{current_source or 'existing'}={current}; "
            f"canonical_{source}={normalized}"
        )

    record[field] = normalized
    record[f"{field}_source"] = source
    record[f"{field}_confidence"] = "high"
    if raw_text:
        record[f"{field}_text_raw"] = clean_text(raw_text)
    clear_conflict(record, field)


class KHPropertyHub(Adapter):
    """
    URLs encode everything we need:
        /km/property/condo-phnom-penh-saensokh-23338
                     ^type ^city      ^district ^id
    """
    name = "khpropertyhub.com"
    domain = "khpropertyhub.com"
    search_url = ("https://khpropertyhub.com/en/property-for-sale/condo/"
                  "phnom-penh?subPropertyTypeIds=245")
    pagination = "query_page"
    per_page = 22
    expected_total = None

    URL_RE = re.compile(
        r"/property/(?P<type>[a-z]+)-(?P<city>phnom-penh)-(?P<district>[a-z-]+?)-(?P<id>\d+)/?$"
    )

    def is_listing_url(self, url: str) -> bool:
        return bool(self.URL_RE.search(url.lower()))

    def listing_id(self, url: str) -> str | None:
        match = self.URL_RE.search(url.lower())
        return match.group("id") if match else None

    def from_url(self, url: str) -> dict:
        match = self.URL_RE.search(url.lower())
        if not match:
            return {}
        return {
            "district": normalise_district(match.group("district")),
            "property_type": match.group("type").title(),
            "province": "Phnom Penh",
        }

    def parse_detail(self, html: str, url: str) -> dict | None:
        record = super().parse_detail(html, url)
        if record is None:
            return None

        soup = BeautifulSoup(html, "html.parser")
        scope = best_current_property_scope(soup, record.get("title"))

        # KHPropertyHub can expose the current price, an old struck-through
        # price and prices from related cards on the same page.  The generic
        # parser may therefore choose a different amount before this adapter
        # runs.  Treat the exact current-listing price element as authoritative
        # and do not turn that expected difference into a manual-review flag.
        prices: list[tuple[int, bool]] = []
        for span in scope.find_all("span"):
            price_text = clean_text(span.get_text(" ", strip=True))
            if not re.fullmatch(r"\$\s?[\d,]+(?:\.\d+)?", price_text or ""):
                continue
            value = parse_price(price_text)
            if value is None:
                continue
            classes = " ".join(span.get("class") or []).lower()
            struck = "line-through" in classes or span.find_parent(["s", "del"]) is not None
            prices.append((value, struck))

        current = [value for value, struck in prices if not struck]
        struck = [value for value, is_struck in prices if is_struck]

        if current:
            exact_price = current[0]
            record["price_usd"] = exact_price
            record["price_usd_source"] = f"{self.source_key}_site_current_price"
            record["price_usd_confidence"] = "high"
            record["price_usd_detail_value"] = exact_price
            clear_conflict(record, "price_usd")

        if struck:
            old_price = struck[0]
            record["price_original_usd"] = old_price
            if record.get("price_usd") and old_price > record["price_usd"]:
                record["price_reduced"] = round(
                    100 * (old_price - record["price_usd"]) / old_price, 2
                )

        # KHPropertyHub often places the unit floor inside the Description
        # summary instead of a labelled specification tile, for example:
        #
        #     15th | 103m² | 2 Bedrooms | 2 Bathrooms
        #     Floor 45th
        #     45th Floor
        #
        # These patterns are intentionally site-specific and strict.  A bare
        # number is never accepted, so area, price, property-code and phone
        # numbers cannot become the unit floor.
        # The generic prose parser can bind unrelated numbers to ``floor``.
        # Remove that weak canonical value before the strict site patterns run.
        # Keep the candidate audit fields so the raw extraction is not lost.
        if record.get("unit_floor_source") == f"{self.source_key}_description":
            record["unit_floor_generic_description_value"] = record.get("unit_floor")
            record["unit_floor_generic_description_text_raw"] = record.get("unit_floor_text_raw")
            for key in (
                "unit_floor", "unit_floor_source", "unit_floor_confidence",
                "unit_floor_text_raw", "unit_floor_previous_value",
                "unit_floor_previous_source",
            ):
                record.pop(key, None)
            clear_conflict(record, "unit_floor")

        floor_texts: list[str] = []

        if record.get("description"):
            floor_texts.append(str(record["description"]))

        # Preserve line boundaries from the rendered description section.
        # This helps recognise a summary row beginning with ``15th |``.
        for selector in (
            "[class*='description']",
            "[id*='description']",
            "[class*='property-detail']",
            "[class*='detail-content']",
        ):
            for block in scope.select(selector):
                candidate_text = block.get_text("\n", strip=True)
                if candidate_text:
                    floor_texts.append(candidate_text)

        # The full current-property scope is only a final fallback.  The
        # regexes below still require an explicit floor marker or ordinal.
        floor_texts.append(scope.get_text("\n", strip=True))

        explicit_floor_patterns = [
            # ``Floor 45th``, ``Floor: 45``, ``Floor - 45th``
            r"\bfloor\s*[:\-]?\s*(\d{1,3})(?:st|nd|rd|th)?\b",
            # ``45th Floor``
            r"\b(\d{1,3})(?:st|nd|rd|th)\s+floor\b",
            # APS-like prose that occasionally appears in reposted content.
            r"\b(?:located|situated)\s+on\s+(?:the\s+)?"
            r"(\d{1,3})(?:st|nd|rd|th)?\s+floor\b",
            # KHPropertyHub compact description row: ``15th | 103m² | ...``
            r"(?:^|[|•\n\r])\s*(\d{1,3})(?:st|nd|rd|th)"
            r"\s*(?=[|•\n\r])",
            # Compact alternatives such as ``15F |`` or ``15 FL |``.
            r"(?:^|[|•\n\r])\s*(\d{1,3})\s*(?:F|FL)\b"
            r"\s*(?=[|•\n\r])",
            # Khmer explicit unit-floor formats: ``ជាន់ទី 12``,
            # ``ជាន់ទី១២`` and ``ជាន់: 12``. Python's ``\d`` and ``int``
            # also support Khmer numerals such as ``១២``.
            r"ជាន់\s*ទី\s*[:：\-]?\s*(\d{1,3})",
            r"ជាន់\s*[:：\-]\s*(\d{1,3})",
        ]

        explicit_floor: tuple[int, str] | None = None
        for floor_text in floor_texts:
            for pattern in explicit_floor_patterns:
                match = re.search(pattern, floor_text, re.IGNORECASE | re.MULTILINE)
                if not match:
                    continue
                value = int(match.group(1))
                if 1 <= value <= 100:
                    explicit_floor = (value, clean_text(match.group(0)))
                    break
            if explicit_floor is not None:
                break

        if explicit_floor is not None:
            floor_value, floor_raw = explicit_floor
            floor_source = f"{self.source_key}_site_structured_description_floor"
            current_floor = parse_int(record.get("unit_floor"))
            current_source = record.get("unit_floor_source")

            # A labelled Building Specification value is more reliable than
            # prose.  Keep it as canonical and preserve a differing explicit
            # description floor only as lineage, not as an unresolved conflict.
            if current_source == f"{self.source_key}_detail_structured":
                if current_floor is not None and current_floor != floor_value:
                    record["unit_floor_reference_mismatch"] = (
                        f"detail_structured={current_floor}; "
                        f"explicit_description={floor_value}"
                    )
                    record["unit_floor_description_value"] = floor_value
                    record["unit_floor_description_source"] = floor_source
                    record["unit_floor_description_text_raw"] = floor_raw
                clear_conflict(record, "unit_floor")
            else:
                apply_candidate(
                    record,
                    "unit_floor",
                    floor_value,
                    floor_source,
                    "high",
                    raw_text=floor_raw,
                )
            record["unit_floor_kind"] = "unit"

        # -------------------- current-title transaction type -----------------
        title_text = clean_text(record.get("title") or "")
        title_transaction = _kh_title_transaction_type(title_text)
        description_transaction = record.get("listing_type_description_value")

        if description_transaction and description_transaction != "sale":
            record["listing_type_description_hint"] = description_transaction

        if title_transaction:
            _kh_set_canonical(
                record,
                "listing_type",
                title_transaction,
                f"{self.source_key}_site_structured_title",
                raw_text=title_text,
                mismatch_field="listing_type_search_mismatch",
            )
            if title_transaction == "rent":
                record["out_of_scope_reason"] = "explicit_rent_title_in_sale_search"
            elif title_transaction == "sale/rent":
                record["out_of_scope_reason"] = "mixed_sale_rent_title"
        else:
            # Description rent words often describe rental yield or a current
            # tenant.  Without an explicit rent title, keep the filtered sale
            # scope and preserve the description only as a hint.
            record["listing_type"] = "sale"
            record["listing_type_source"] = "search_scope"
            record["listing_type_confidence"] = "high"
            clear_conflict(record, "listing_type")

        # ----------------------- title bedroom rules -------------------------
        bedroom_options = _kh_title_bedroom_options(title_text)
        if len(bedroom_options) == 1:
            bedroom_value = bedroom_options[0]
            _kh_set_canonical(
                record,
                "bedrooms",
                bedroom_value,
                f"{self.source_key}_site_structured_title",
                raw_text=title_text,
                mismatch_field="bedrooms_reference_mismatch",
            )
            record["is_studio"] = bedroom_value == 0
        elif len(bedroom_options) > 1:
            record["bedroom_options"] = bedroom_options
            record["multi_unit_options"] = True
            record["display_as_project"] = True
            # Do not keep one arbitrary structured value for a title that
            # advertises several configurations.
            record["bedrooms"] = None
            record["bedrooms_source"] = None
            record["bedrooms_confidence"] = None
            clear_conflict(record, "bedrooms")
            append_conflict(
                record,
                "bedrooms",
                f"multiple bedroom options in title={bedroom_options}",
            )

        # ----------------------- title property type -------------------------
        title_property_type = _kh_title_property_type(title_text)
        condo_family = {"Condo", "Apartment", "Penthouse"}

        if title_property_type in condo_family:
            canonical_type = "Penthouse" if title_property_type == "Penthouse" else "Condo"
            _kh_set_canonical(
                record,
                "property_type",
                canonical_type,
                f"{self.source_key}_site_structured_title",
                raw_text=title_text,
                mismatch_field="property_type_reference_mismatch",
            )
        elif title_property_type:
            # Explicit land/house/villa/flat/commercial titles are genuine
            # out-of-scope records even when the broad URL category says Condo.
            record["property_type"] = title_property_type
            record["property_type_source"] = f"{self.source_key}_site_structured_title"
            record["property_type_confidence"] = "high"
            record["property_type_text_raw"] = title_text
            clear_conflict(record, "property_type")
            append_conflict(
                record,
                "property_type",
                f"search_scope=Condo; explicit title={title_property_type}",
            )
            record["out_of_scope_reason"] = "not_condo_or_penthouse"
        else:
            # Undo generic false positives caused by lifestyle words.
            current_type = normalize_property_type(record.get("property_type"))
            if current_type not in condo_family:
                record["property_type_false_positive_raw"] = current_type
                record["property_type"] = "Condo"
                record["property_type_source"] = "search_scope"
                record["property_type_confidence"] = "high"
                clear_conflict(record, "property_type")

        refresh_review_flag(record)
        return record


class APSCambodia(Adapter):
    """APS adapter with explicit Overview, Description and Price parsing."""

    name = "aps.com.kh"
    domain = "aps.com.kh"
    search_url = "https://aps.com.kh/apartment-condo-for-sale/"
    pagination = "path_page"
    per_page = 28
    expected_total = 137

    def is_listing_url(self, url: str) -> bool:
        low = url.lower()
        if "/properties/" not in low:
            return False
        if any(bad in low for bad in ("record_type_", "sub_type_", "property_type_")):
            return False
        slug = low.rstrip("/").rsplit("/", 1)[-1]
        return slug.count("-") >= 3

    def listing_id(self, url: str) -> str | None:
        slug = url.lower().rstrip("/").rsplit("/", 1)[-1]
        return re.sub(r"[^a-z0-9]+", "-", slug).strip("-")[:100] or None

    def from_url(self, url: str) -> dict[str, Any]:
        slug = url.lower().rstrip("/").rsplit("/", 1)[-1]
        out: dict[str, Any] = {}

        if "for-rent" in slug:
            out["listing_type"] = "rent"
        elif "for-sale" in slug:
            out["listing_type"] = "sale"

        # APS sometimes converts decimal sizes in slugs from 38.35sqm to
        # ``38-35sqm``. Recover that form before trying the normal integer form.
        decimal_size = re.search(r"(?<!\d)(\d{1,4})-(\d{1,2})sqm\b", slug)
        if decimal_size:
            out["size_m2"] = float(
                f"{decimal_size.group(1)}.{decimal_size.group(2)}"
            )
        else:
            size = re.search(r"(?<!\d)(\d+(?:\.\d+)?)[- ]?sqm\b", slug)
            if size:
                out["size_m2"] = float(size.group(1))

        beds = re.search(r"(\d+)-bedroom", slug)
        if beds:
            out["bedrooms"] = int(beds.group(1))
        elif "studio" in slug:
            out["bedrooms"] = 0

        floor = re.search(r"(\d+)(?:st|nd|rd|th)-floor", slug)
        if floor:
            out["unit_floor"] = int(floor.group(1))

        if "penthouse" in slug:
            out["property_type"] = "Penthouse"

        flat = re.sub(r"[^a-z0-9]", "", slug)
        for alias, standard in sorted(DISTRICT_ALIASES.items(), key=lambda kv: -len(kv[0])):
            if alias in flat:
                out["district"] = standard
                break
        return out

    def parse_detail(self, html: str, url: str) -> dict[str, Any] | None:
        record = super().parse_detail(html, url)
        if record is None:
            record = blank_record(self.name)
            record["url"] = url
            record["listing_id"] = f"{self.name}_{self.listing_id(url) or ''}"
            self.apply_url_fields(record, url)

        soup = BeautifulSoup(html, "html.parser")
        title = extract_title(soup)
        if title:
            record["title"] = title

        scope = best_current_property_scope(soup, title)
        body = clean_text(scope.get_text(" ", strip=True))
        source = f"{self.source_key}_site_structured"
        title_source = f"{self.source_key}_site_structured_title"

        # -----------------------------------------------------------------
        # APS identifiers
        # -----------------------------------------------------------------
        # The compact line near the title commonly contains an internal code:
        #     ID: S-10359   50 sqm   2 Bedrooms
        code_match = re.search(r"\bID\s*:\s*([A-Z0-9-]+)\b", body, re.I)
        if code_match:
            record["property_code"] = code_match.group(1).upper()

        # The page title ends with a stable APS numeric listing code. Several
        # different URL slugs can point to the same code, so preserve it for
        # Silver-layer duplicate removal without collapsing Bronze records.
        aps_code_match = re.search(
            r"APS\s+Cambodia\s+(\d{4,})\s*$",
            title or "",
            re.IGNORECASE,
        )
        if aps_code_match:
            record["aps_listing_code"] = aps_code_match.group(1)

        # -----------------------------------------------------------------
        # Current page title is stronger than an old/stale APS URL slug.
        # -----------------------------------------------------------------
        title_low = clean_text(title or "").lower()
        url_low = url.lower()
        title_type = None
        if re.search(r"\bfor sale\b", title_low):
            title_type = "sale"
        elif re.search(r"\bfor rent\b", title_low):
            title_type = "rent"

        url_type = (
            "rent" if "for-rent" in url_low
            else "sale" if "for-sale" in url_low
            else None
        )

        if title_type:
            apply_candidate(
                record,
                "listing_type",
                title_type,
                title_source,
                "high",
                raw_text=title or "",
            )

            # APS URL slugs are sometimes stale. The current page title is the
            # canonical transaction type. Preserve a URL disagreement for
            # diagnostics, but do not send an otherwise clear record to manual
            # review.
            if url_type and url_type != title_type:
                record["listing_type_url_mismatch"] = (
                    f"url={url_type}; current_title={title_type}"
                )
                clear_conflict(record, "listing_type")

        # A page that clearly says rent in both URL and current title is simply
        # out of scope, not ambiguous. Keep it in Bronze and remove the false
        # manual-review flag caused by the sale search category.
        if title_type == "rent" and url_type == "rent":
            record["out_of_scope_reason"] = "rent_listing_in_sale_search"
            clear_conflict(record, "listing_type")

        # APS slugs can be stale. Use the current title as the canonical room
        # count while preserving a disagreement for review.
        title_bedrooms = extract_bedrooms(title or "")
        if title_bedrooms:
            bed_value, bed_raw = title_bedrooms
            apply_candidate(
                record,
                "bedrooms",
                bed_value,
                title_source,
                "high",
                raw_text=bed_raw,
            )

            url_bedrooms = record.get("bedrooms_url_value")
            if (
                url_bedrooms is not None
                and parse_int(url_bedrooms) != parse_int(bed_value)
            ):
                record["bedrooms_url_mismatch"] = (
                    f"url={url_bedrooms}; current_title={bed_value}"
                )
                clear_conflict(record, "bedrooms")

        # A floor written in the current title (for example, 28th Floor) is
        # stronger than the URL slug and can be compared with Overview Level.
        title_floor = extract_unit_floor(title or "")
        if title_floor:
            floor_value, floor_raw = title_floor
            apply_candidate(
                record,
                "unit_floor",
                floor_value,
                title_source,
                "high",
                raw_text=floor_raw,
            )

        # -----------------------------------------------------------------
        # APS size extraction
        # -----------------------------------------------------------------
        # 1) Exact compact summary near the title.
        summary_size_patterns = (
            r"\bID\s*:\s*[A-Z0-9-]+\s+([\d,]+(?:\.\d+)?)\s*"
            r"(?:sqm|m²|m2|sq\.?\s*m)\b",
            r"\b([\d,]+(?:\.\d+)?)\s*"
            r"(?:sqm|m²|m2|sq\.?\s*m)\s+\d+\s*Bedrooms?\b",
        )
        for pattern in summary_size_patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                apply_candidate(
                    record,
                    "size_m2",
                    match.group(1),
                    source,
                    "high",
                    raw_text=match.group(0),
                )
                break

        # 2) Size written directly in the current page title.
        title_size = re.search(
            r"(?<!\d)([\d,]+(?:\.\d+)?)\s*"
            r"(?:sqm|m²|m2|sq\.?\s*m)\b",
            title or "",
            re.IGNORECASE,
        )
        if title_size:
            apply_candidate(
                record,
                "size_m2",
                title_size.group(1),
                title_source,
                "high",
                raw_text=title_size.group(0),
            )

        # 3) APS canonical area: the advertised unit area is written as
        #    ``Unit Size: 55.2 sqm`` in the Overview section. This is the
        #    value stored in ``size_m2``. Other size text is only fallback.
        overview_text, _ = extract_heading_section(soup, {"Overview"})
        overview_clean = clean_text(overview_text or "")

        overview_size = re.search(
            r"\bUnit\s+Size\s*[:：-]?\s*"
            r"([\d,]+(?:\.\d+)?)\s*"
            r"(?:sqm|m²|m2|sq\.?\s*m)\b",
            overview_clean,
            re.IGNORECASE,
        )

        # Some APS layouts split the label and value into different elements.
        # Use the label/value parser as a second exact method.
        unit_size_value = (
            overview_size.group(1)
            if overview_size
            else find_text_label_value(
                scope,
                ("Unit Size",),
                allow_body_fallback=False,
            )
        )

        if unit_size_value:
            unit_size_raw = (
                overview_size.group(0)
                if overview_size
                else clean_text(str(unit_size_value))
            )
            apply_candidate(
                record,
                "size_m2",
                unit_size_value,
                f"{self.source_key}_detail_structured_unit_size",
                "high",
                raw_text=unit_size_raw,
            )
            record["size_m2_kind"] = "unit"

            # Unit Size is APS's canonical current unit area. Older URL/title
            # text can describe a previous version of the listing. Keep those
            # differences as audit metadata, not as manual-review conflicts.
            canonical_size = parse_size(unit_size_value)
            size_references = []
            for label, key in (
                ("url", "size_m2_url_value"),
                ("title", "size_m2_title_value"),
                ("summary", "size_m2_candidate_value"),
            ):
                reference = record.get(key)
                if (
                    reference is not None
                    and canonical_size is not None
                    and values_differ("size_m2", reference, canonical_size)
                ):
                    size_references.append(f"{label}={reference}")

            if size_references:
                record["size_m2_reference_mismatch"] = (
                    "; ".join(size_references)
                    + f"; canonical_unit_size={canonical_size}"
                )
            clear_conflict(record, "size_m2")

        # -----------------------------------------------------------------
        # Other structured APS fields
        # -----------------------------------------------------------------
        property_type_value = find_text_label_value(
            scope,
            ("Sub Type", "Property Type"),
            allow_body_fallback=False,
        )
        if property_type_value:
            record["property_type_raw"] = clean_text(property_type_value)
            apply_candidate(
                record,
                "property_type",
                property_type_value,
                source,
                "high",
                raw_text=property_type_value,
            )

        # Only use these area labels when APS does not publish Unit Size.
        if not unit_size_value and record.get("size_m2") is None:
            fallback_size = find_text_label_value(
                scope,
                ("Floor Area", "Net Area", "Size"),
                allow_body_fallback=False,
            )
            if fallback_size:
                apply_candidate(
                    record,
                    "size_m2",
                    fallback_size,
                    f"{self.source_key}_detail_structured_size_fallback",
                    "medium",
                    raw_text=fallback_size,
                )
                record["size_m2_kind"] = "fallback"

        # APS writes the advertised unit floor in Overview as ``Level: 29``.
        # This is unit_floor, not the building's total number of floors.
        level_search_text = clean_text(overview_text or body)
        level_match = re.search(
            r"(?:^|\b)Level\s*[:：-]?\s*(\d{1,3})(?:\b|$)",
            level_search_text,
            re.IGNORECASE,
        )
        if level_match:
            level_value = int(level_match.group(1))
            if 1 <= level_value <= 100:
                apply_candidate(
                    record,
                    "unit_floor",
                    level_value,
                    f"{self.source_key}_overview_level",
                    "high",
                    raw_text=level_match.group(0),
                )

                # APS explicitly labels this field as Level, so it is the
                # canonical unit floor. Preserve stale URL/title differences
                # for audit without treating them as unresolved conflicts.
                floor_references = []
                for label, key in (
                    ("url", "unit_floor_url_value"),
                    ("title", "unit_floor_title_value"),
                ):
                    reference = record.get(key)
                    if (
                        reference is not None
                        and parse_int(reference) != level_value
                    ):
                        floor_references.append(f"{label}={reference}")

                if floor_references:
                    record["unit_floor_reference_mismatch"] = (
                        "; ".join(floor_references)
                        + f"; canonical_level={level_value}"
                    )
                clear_conflict(record, "unit_floor")
            else:
                record["unit_floor_invalid_value"] = level_value
                record["unit_floor_invalid_source"] = (
                    f"{self.source_key}_overview_level"
                )

        price_match = re.search(
            r"(?:Price\s*:\s*)?([\d,]+(?:\.\d+)?)\s*USD\b",
            body,
            re.IGNORECASE,
        )
        if price_match:
            apply_candidate(
                record,
                "price_usd",
                price_match.group(0),
                source,
                "high",
                raw_text=price_match.group(0),
            )

        description, description_source = extract_heading_section(
            soup,
            {"Description", "Property Description"},
        )
        if description:
            record["description"] = description
            record["description_source"] = description_source

        # Description may fill missing values but cannot override the current
        # title or exact Overview labels.
        recover_from_text(record, "", description or "", self.source_key)
        refresh_review_flag(record)
        record["detail_scraped"] = True
        record["detail_parsed_at"] = now_iso()
        return record



def _harbor_project_overview_text(scope: BeautifulSoup) -> str:
    """Return only Harbor's current-listing ``Project Overview`` text.

    Harbor renders Bedroom, Bathroom, Floor Area and Floor in a dedicated
    section.  Reading that section directly is safer than scanning the full
    page, which can contain related properties and other unrelated numbers.
    """
    section_text, _ = extract_heading_section(
        scope,
        {"Project Overview", "Property Overview", "项目概况", "房源概况"},
        max_chars=2500,
    )
    if section_text:
        return clean_text(section_text)

    body = clean_text(scope.get_text(" ", strip=True))
    match = re.search(
        r"(?:Project Overview|Property Overview|项目概况|房源概况)\s*"
        r"(.{1,2500}?)"
        r"(?=\s+(?:Description|Property Description|Location|Facilities|"
        r"Amenities|Contact|Similar Properties|Related Properties|Mortgage)\b|$)",
        body,
        re.IGNORECASE,
    )
    return clean_text(match.group(1)) if match else ""


def _harbor_overview_fields(overview_text: str) -> dict[str, tuple[Any, str]]:
    """Parse Harbor's visible Project Overview label/value fields."""
    text = clean_text(overview_text)
    if not text:
        return {}

    patterns: dict[str, list[str]] = {
        "bedrooms": [
            r"\bBedrooms?\s*[:：-]?\s*(\d{1,2})\b",
            r"卧室\s*[:：-]?\s*(\d{1,2})",
        ],
        "bathrooms": [
            r"\bBathrooms?\s*[:：-]?\s*(\d{1,2})\b",
            r"(?:浴室|卫生间)\s*[:：-]?\s*(\d{1,2})",
        ],
        "size_m2": [
            r"\bFloor\s+Area\s*[:：-]?\s*([\d,.]+)\s*(?:m²|m2|sqm|sq\.?\s*m)\b",
            r"(?:建筑面积|套内面积|面积)\s*[:：-]?\s*([\d,.]+)\s*(?:m²|m2|sqm|㎡)?",
        ],
        "unit_floor": [
            # Negative lookahead prevents ``Floor Area`` from becoming floor.
            r"\bFloor(?!\s+Area)\s*[:：-]?\s*(\d{1,3})(?:st|nd|rd|th)?\b",
            r"(?:所在楼层|楼层)\s*[:：-]?\s*(\d{1,3})",
        ],
    }

    result: dict[str, tuple[Any, str]] = {}
    for field, field_patterns in patterns.items():
        for pattern in field_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            raw = clean_text(match.group(0))
            value: Any = match.group(1)
            if field == "size_m2":
                value = parse_size(value)
            else:
                value = parse_int(value)
            if value is not None:
                result[field] = (value, raw)
                break

    updated = re.search(
        r"\b(?:Update\s+time|Updated(?:\s+At)?)\s*[:：-]?\s*"
        r"(\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2})?)",
        text,
        re.IGNORECASE,
    )
    if updated:
        result["created_at"] = (clean_text(updated.group(1)), clean_text(updated.group(0)))

    return result


def _apply_harbor_overview_canonical(
    record: dict[str, Any],
    field: str,
    value: Any,
    raw_text: str,
    source_key: str,
) -> None:
    """Use Harbor's visible Project Overview as the canonical unit value."""
    normalized = normalize_candidate(field, value)
    if normalized is None:
        return

    source = f"{source_key}_project_overview_structured"
    current = record.get(field)
    current_source = clean_text(record.get(f"{field}_source") or "")

    if current not in (None, "", [], {}) and values_differ(field, current, normalized):
        record[f"{field}_reference_mismatch"] = (
            f"{current_source or 'existing'}={current}; "
            f"project_overview={normalized}"
        )
        record[f"{field}_previous_value"] = current
        record[f"{field}_previous_source"] = current_source or "unknown"

    record[field] = normalized
    record[f"{field}_source"] = source
    record[f"{field}_confidence"] = "high"
    record[f"{field}_text_raw"] = clean_text(raw_text)
    record[f"{field}_overview_value"] = normalized
    record[f"{field}_overview_source"] = source
    record[f"{field}_overview_text_raw"] = clean_text(raw_text)
    clear_conflict(record, field)


class HarborProperty(Adapter):
    """Harbor adapter for browser-rendered Vue pages and embedded state."""

    name = "harbor-property.com"
    domain = "harbor-property.com"
    search_url = (
        "https://www.harbor-property.com/house/buy/"
        "area=0%2F0&btypes=1&nearByTagId=0&price=0%2F0&regions=1%2C0%2C0"
    )
    pagination = "browser_pages"
    per_page = 21
    expected_total = 967
    needs_browser = True
    PAGE_PARAM = "pageIndex"
    page_url_known = True

    def page_url(self, page: int) -> str:
        if page <= 1:
            return self.search_url
        prefix, marker, params_text = self.search_url.partition("/house/buy/")
        if not marker:
            return self.search_url
        params: dict[str, str] = {}
        for pair in params_text.split("&"):
            if "=" in pair:
                key, value = pair.split("=", 1)
                params[key] = value
        params.setdefault("orderBy", "0")
        params[self.PAGE_PARAM] = str(page)
        ordered = "&".join(f"{key}={params[key]}" for key in sorted(params))
        return f"{prefix}/house/buy/{ordered}"

    URL_RE = re.compile(
        r"/house/detail/(?P<id>\d+)/(?P<sangkat>[a-z0-9-]+)/(?P<type>[a-z-]+)/?$"
    )

    def is_listing_url(self, url: str) -> bool:
        return bool(self.URL_RE.search(url.lower()))

    def listing_id(self, url: str) -> str | None:
        match = self.URL_RE.search(url.lower())
        return match.group("id") if match else None

    def from_url(self, url: str) -> dict[str, Any]:
        match = self.URL_RE.search(url.lower())
        if not match:
            return {}
        sangkat = match.group("sangkat")
        out: dict[str, Any] = {
            "commune": sangkat.replace("-", " ").title(),
            "province": "Phnom Penh",
            "property_type": match.group("type").replace("-", " ").title(),
        }
        district = normalise_district(sangkat)
        known = set(SANGKAT_TO_KHAN.values()) | set(DISTRICT_ALIASES.values())
        if district in known:
            out["district"] = district
        return out

    def parse_detail(self, html: str, url: str) -> dict[str, Any] | None:
        record = super().parse_detail(html, url)
        if record is None:
            record = blank_record(self.name)
            record["url"] = url
            record["listing_id"] = f"{self.name}_{self.listing_id(url) or ''}"
            self.apply_url_fields(record, url)

        source = f"{self.source_key}_embedded_json"
        listing = select_json_listing(html, self.listing_id(url))
        if listing:
            field_keys = {
                "price_usd": ("price", "salePrice", "sellingPrice", "totalPrice", "priceUsd"),
                "size_m2": ("area", "size", "floorArea", "houseArea", "buildingArea", "grossArea"),
                "bedrooms": ("bedroom", "bedrooms", "bedroomNum", "roomNum"),
                "bathrooms": ("bathroom", "bathrooms", "bathroomNum", "toiletNum"),
                "unit_floor": ("floor", "floorLevel", "currentFloor", "unitFloor"),
                "building_total_floors": ("totalFloor", "totalFloors", "buildingFloor", "buildingFloors"),
                "property_type": ("propertyType", "houseType", "typeName"),
            }
            for field, keys in field_keys.items():
                value = first_json_value(listing, keys)
                if value not in (None, "", [], {}):
                    if field == "property_type":
                        record["property_type_raw"] = clean_text(value)
                    apply_candidate(record, field, value, source, "high", raw_text=str(value))

            json_title = first_json_value(listing, ("title", "name", "houseTitle", "listingTitle"))
            if json_title and not record.get("title"):
                record["title"] = clean_text(json_title)[:300]
            json_description = first_json_value(listing, ("description", "desc", "introduction", "content"))
            if isinstance(json_description, str) and len(clean_text(json_description)) >= 40:
                record["description"] = clean_text(json_description)[:5000]
                record["description_source"] = "embedded_json_description"

        soup = BeautifulSoup(html, "html.parser")
        title = record.get("title") or extract_title(soup)
        scope = best_current_property_scope(soup, title)
        body = clean_text(scope.get_text(" ", strip=True))
        structured_source = f"{self.source_key}_site_structured"

        pairs = extract_pairs(scope)
        for field in ("price_usd", "size_m2", "bedrooms", "bathrooms", "unit_floor", "building_total_floors"):
            if pairs.get(field):
                apply_candidate(record, field, pairs[field], structured_source, "high", raw_text=pairs[field])

        # Rendered Harbor pages often expose values only as label text.
        for field, labels in {
            "price_usd": ("Price", "Sale Price", "Selling Price", "售价", "价格", "总价"),
            "size_m2": ("Size", "Area", "Floor Area", "建筑面积", "套内面积", "面积"),
            "bedrooms": ("Bedrooms", "Bedroom", "卧室", "房间"),
            "bathrooms": ("Bathrooms", "Bathroom", "浴室", "卫生间"),
            "unit_floor": ("Floor", "Floor Level", "楼层", "所在楼层"),
            "building_total_floors": ("Total Floors", "Building Floors", "总楼层", "楼高"),
        }.items():
            value = find_text_label_value(scope, labels, allow_body_fallback=False)
            if value:
                apply_candidate(record, field, value, structured_source, "high", raw_text=value)

        # Harbor's visible Project Overview is the most direct source for the
        # advertised unit.  In pages such as:
        #   Bedroom 2 | Bathroom 2 | Floor Area 145m² | Floor 16
        # use those values as canonical and keep any embedded-JSON difference
        # only as a lineage mismatch.
        project_overview = _harbor_project_overview_text(scope)
        if project_overview:
            record["project_overview_text"] = project_overview
            record["project_overview_source"] = (
                f"{self.source_key}_project_overview_section"
            )
            for field, (value, raw_value) in _harbor_overview_fields(project_overview).items():
                if field == "created_at":
                    record["created_at"] = value
                    record["created_at_source"] = (
                        f"{self.source_key}_project_overview_structured"
                    )
                    record["created_at_text_raw"] = raw_value
                    continue
                _apply_harbor_overview_canonical(
                    record,
                    field,
                    value,
                    raw_value,
                    self.source_key,
                )

        if record.get("price_usd") is None:
            prices = extract_price_tokens(body)
            if prices:
                apply_candidate(record, "price_usd", max(prices), f"{self.source_key}_detail_price_body", "medium")

        if record.get("size_m2") is None:
            size, raw = extract_size_near_label(body)
            if size is not None:
                apply_candidate(record, "size_m2", size, structured_source, "medium", raw_text=raw)

        if title:
            record["title"] = clean_text(title)[:300]
        recover_from_text(record, record.get("title") or "", record.get("description") or "", self.source_key)

        # This adapter is fed only from Harbor's /house/buy/ result set.
        # Descriptions sometimes mention rental yield, rent prices or related
        # rental units, which must not change the transaction type of the
        # current listing or create a false listing_type conflict.
        record["listing_type"] = "sale"
        record["listing_type_source"] = f"{self.source_key}_buy_search_scope"
        record["listing_type_confidence"] = "high"
        clear_conflict(record, "listing_type")

        record["detail_scraped"] = True
        record["detail_parsed_at"] = now_iso()
        refresh_review_flag(record)
        return record


class CamRealtyService(Adapter):
    """CAM Realty adapter with current-page canonical rules.

    CAM Realty keeps many old slugs alive after a listing is edited.  The URL
    may still say ``for-rent`` or ``studio`` while the visible current title
    says ``For Sale`` or another bedroom configuration.  Therefore the visible
    title is canonical for transaction type, while explicit studio wording and
    title+URL agreement are canonical for bedrooms.  The old values remain in
    mismatch fields for lineage instead of creating false manual-review flags.
    """

    name = "camrealtyservice.com"
    domain = "camrealtyservice.com"
    search_url = (
        "https://camrealtyservice.com/property-search/"
        "?search_for=house&status%5B0%5D=for-sale"
        "&location%5B0%5D=phnom-penh&type%5B0%5D=resale-condominium"
    )
    pagination = "path_page"
    per_page = 12
    expected_total = None
    page_url_known = True

    def page_url(self, page: int) -> str:
        if page <= 1:
            return self.search_url
        base, _, query = self.search_url.partition("?")
        return f"{base.rstrip('/')}/page/{page}/?{query}"

    def is_listing_url(self, url: str) -> bool:
        low = url.lower()
        if "/boreys/" in low or "/borey/" in low:
            return False
        if "/property/" not in low:
            return False
        slug = low.rstrip("/").rsplit("/", 1)[-1]
        return slug.count("-") >= 3

    @staticmethod
    def _legacy_slug_id(url: str) -> str:
        slug = url.lower().rstrip("/").rsplit("/", 1)[-1]
        return re.sub(r"[^a-z0-9]+", "-", slug)[:80]

    def detail_cache_key(self, url: str) -> str | None:
        # Preserve compatibility with previously downloaded cache filenames.
        return self._legacy_slug_id(url)

    def listing_id(self, url: str) -> str | None:
        # Always include a URL hash. CAM Realty sometimes reuses the same
        # property code for more than one public URL.
        slug = url.lower().rstrip("/").rsplit("/", 1)[-1]
        readable = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")[:48]
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        return f"{readable}-{digest}"

    def from_url(self, url: str) -> dict[str, Any]:
        slug = url.lower()
        out: dict[str, Any] = {}
        if "for-rent" in slug:
            out["listing_type"] = "rent"
        elif "for-sale" in slug:
            out["listing_type"] = "sale"

        beds = re.search(r"(\d+)-bedroom", slug)
        if beds:
            out["bedrooms"] = int(beds.group(1))
        elif "studio" in slug:
            out["bedrooms"] = 0

        floor = re.search(r"(\d+)(?:st|nd|rd|th)-floor", slug)
        if floor:
            out["unit_floor"] = int(floor.group(1))

        if "penthouse" in slug:
            out["property_type"] = "Penthouse"

        flat = re.sub(r"[^a-z0-9]", "", slug)
        for alias, standard in sorted(DISTRICT_ALIASES.items(), key=lambda kv: -len(kv[0])):
            if len(alias) >= 5 and alias in flat:
                out["district"] = standard
                break
        else:
            for alias, standard in sorted(SANGKAT_TO_KHAN.items(), key=lambda kv: -len(kv[0])):
                if len(alias) >= 5 and alias in flat:
                    out["district"] = standard
                    out["commune"] = alias
                    break
        return out

    @staticmethod
    def _title_listing_type(title: str | None) -> str | None:
        """Read transaction type from the visible current title only."""
        value = clean_text(title or "").lower()
        if not value:
            return None

        has_sale = bool(re.search(r"\bfor\s+sale\b|\bsale\s+and\s+rent\b", value))
        has_rent = bool(re.search(r"\bfor\s+rent\b|\brent\s+and\s+sale\b", value))

        # Handle titles such as "Hotel for sale & Rent".
        if re.search(r"\bfor\s+sale\b.{0,20}\b(?:&|and)\s*rent\b", value):
            has_sale = has_rent = True
        if re.search(r"\bfor\s+rent\b.{0,20}\b(?:&|and)\s*sale\b", value):
            has_sale = has_rent = True

        if has_sale and has_rent:
            return "sale/rent"
        if has_sale:
            return "sale"
        if has_rent:
            return "rent"
        return None

    @staticmethod
    def _title_bedroom_info(title: str | None) -> tuple[int | None, int | None, str | None]:
        """Return (main bedrooms, extra room count, matched title text)."""
        value = clean_text(title or "")
        if not value:
            return None, None, None

        studio = re.search(r"\bstudio(?:\s+room)?\b", value, re.IGNORECASE)
        if studio:
            return 0, None, studio.group(0)

        # "3+1 Bedrooms" usually means three main bedrooms plus one helper /
        # maid room.  Keep the model bedroom count at 3 and preserve +1.
        plus = re.search(
            r"(?<!\d)(\d{1,2})\s*\+\s*(\d{1,2})\s*(?:bed(?:room)?s?|br)\b",
            value,
            re.IGNORECASE,
        )
        if plus:
            return int(plus.group(1)), int(plus.group(2)), plus.group(0)

        explicit = re.search(
            r"(?<!\d)(\d{1,2})\s*[- ]?\s*(?:bed(?:room)?s?|br)\b",
            value,
            re.IGNORECASE,
        )
        if explicit:
            return int(explicit.group(1)), None, explicit.group(0)

        return None, None, None

    @staticmethod
    def _set_canonical(
        record: dict[str, Any],
        field: str,
        value: Any,
        source: str,
        *,
        raw_text: str | None = None,
        mismatch_field: str | None = None,
        mismatch_text: str | None = None,
    ) -> None:
        """Set a verified current-page value without treating stale references as conflicts."""
        normalized = normalize_candidate(field, value)
        if normalized is None:
            return

        current = record.get(field)
        current_source = record.get(f"{field}_source")
        if current not in (None, "", [], {}) and values_differ(field, current, normalized):
            record[f"{field}_previous_value"] = current
            record[f"{field}_previous_source"] = current_source or "unknown"
            if mismatch_field and mismatch_text:
                record[mismatch_field] = mismatch_text

        record[field] = normalized
        record[f"{field}_source"] = source
        record[f"{field}_confidence"] = "high"
        if raw_text:
            record[f"{field}_text_raw"] = clean_text(raw_text)
        clear_conflict(record, field)

    def parse_detail(self, html: str, url: str) -> dict[str, Any] | None:
        soup = BeautifulSoup(html, "html.parser")
        title = extract_title(soup)
        scope = best_current_property_scope(soup, title)
        body = clean_text(scope.get_text(" ", strip=True))

        record = blank_record(self.name)
        record["url"] = url
        record["listing_id"] = f"{self.name}_{self.listing_id(url) or ''}"
        self.apply_url_fields(record, url)
        if title:
            record["title"] = title

        source = f"{self.source_key}_site_structured"

        property_code = find_text_label_value(
            scope,
            ("Property ID", "Property Code", "ID"),
            allow_body_fallback=False,
        )
        if not property_code:
            match = re.search(r"\bID\s*:?\s*([A-Z]\d{5,})\b", body, re.IGNORECASE)
            property_code = match.group(1) if match else None
        if property_code:
            record["property_code"] = clean_text(property_code).replace(" ", "")

        for field, labels in {
            "bedrooms": ("Bedrooms", "Bedroom"),
            "bathrooms": ("Bathrooms", "Bathroom"),
            "size_m2": ("Net Area", "Unit Size", "Floor Area", "Size"),
            "unit_floor": ("Floor", "Floor Level", "Level"),
            "property_type": ("Property Type", "Type"),
        }.items():
            value = find_text_label_value(scope, labels, allow_body_fallback=False)
            if not value:
                continue
            if field == "property_type":
                if normalize_property_type(value):
                    record["property_type_raw"] = value
                else:
                    record["property_type_invalid_raw"] = clean_text(value)
                    continue
            apply_candidate(record, field, value, source, "high", raw_text=value)

        # Prefer Net Area; only fall back to Gross Area when net size is absent.
        if record.get("size_m2") is None:
            gross = find_text_label_value(scope, ("Gross Area",), allow_body_fallback=False)
            if gross:
                apply_candidate(record, "size_m2", gross, source, "medium", raw_text=gross)
                record["size_m2_kind"] = "gross"
        else:
            record["size_m2_kind"] = "net"

        prices = extract_price_tokens(body)
        if prices:
            apply_candidate(
                record,
                "price_usd",
                prices[0],
                f"{self.source_key}_detail_price_element",
                "high",
            )

        description, description_source = extract_heading_section(
            scope,
            {"Description", "Property Description"},
        )
        if not description:
            description, description_source = extract_description(scope)
        if description:
            record["description"] = description
            record["description_source"] = description_source

        # Generic title/description recovery supplies floors and missing fields.
        recover_from_text(record, title or "", description or "", self.source_key)

        # -----------------------------------------------------------------
        # CAM Realty canonical transaction type
        # -----------------------------------------------------------------
        title_type = self._title_listing_type(title)
        url_type = record.get("listing_type_url_value")

        if title_type:
            mismatch = None
            if url_type and clean_text(url_type).lower() != title_type:
                mismatch = f"url={url_type}; current_title={title_type}"
            self._set_canonical(
                record,
                "listing_type",
                title_type,
                f"{self.source_key}_site_structured_title",
                raw_text=title,
                mismatch_field="listing_type_url_mismatch",
                mismatch_text=mismatch,
            )
        elif url_type:
            # With no explicit current-title transaction, the URL is the best
            # available evidence.  It is not a conflict with the broad search.
            self._set_canonical(
                record,
                "listing_type",
                url_type,
                f"{self.source_key}_url",
            )
        else:
            record["listing_type"] = "sale"
            record["listing_type_source"] = "search_scope"
            record["listing_type_confidence"] = "high"
            clear_conflict(record, "listing_type")

        if record.get("listing_type") == "rent":
            record["out_of_scope_reason"] = "rent_listing"
        elif record.get("listing_type") == "sale/rent":
            record["out_of_scope_reason"] = "mixed_sale_rent_listing"
        else:
            record.pop("out_of_scope_reason", None)

        # -----------------------------------------------------------------
        # CAM Realty canonical bedroom rules
        # -----------------------------------------------------------------
        title_beds, extra_rooms, bedroom_raw = self._title_bedroom_info(title)
        if title_beds is not None:
            url_beds = record.get("bedrooms_url_value")
            current_beds = record.get("bedrooms")
            is_studio = title_beds == 0
            corroborated = url_beds is not None and parse_int(url_beds) == title_beds
            plus_layout = extra_rooms is not None

            if is_studio or corroborated or plus_layout or current_beds is None:
                mismatch_parts = []
                if current_beds is not None and values_differ("bedrooms", current_beds, title_beds):
                    mismatch_parts.append(
                        f"{record.get('bedrooms_source') or 'existing'}={current_beds}"
                    )
                if url_beds is not None and parse_int(url_beds) != title_beds:
                    mismatch_parts.append(f"url={url_beds}")
                mismatch_parts.append(f"current_title={title_beds}")

                self._set_canonical(
                    record,
                    "bedrooms",
                    title_beds,
                    f"{self.source_key}_site_structured_title",
                    raw_text=bedroom_raw,
                    mismatch_field="bedrooms_reference_mismatch",
                    mismatch_text="; ".join(mismatch_parts),
                )

            if extra_rooms is not None:
                record["additional_room_count"] = extra_rooms
                record["bedroom_layout_text"] = bedroom_raw

        # A Sky Villa inside a tower/condominium is a high-rise penthouse unit,
        # not a landed villa.
        if title and re.search(r"\bsky\s+villa\b", title, re.IGNORECASE):
            self._set_canonical(
                record,
                "property_type",
                "Penthouse",
                f"{self.source_key}_site_structured_title",
                raw_text="Sky Villa",
                mismatch_field="property_type_reference_mismatch",
                mismatch_text=(
                    f"previous={record.get('property_type')}; current_title=Penthouse"
                ),
            )

        record["detail_scraped"] = True
        record["detail_parsed_at"] = now_iso()
        refresh_review_flag(record)

        meaningful = any(record.get(field) not in (None, "") for field in (
            "title", "price_usd", "size_m2", "description",
        ))
        return record if meaningful else None


ADAPTERS = {
    "khpropertyhub": KHPropertyHub(),
    "aps": APSCambodia(),
    "harbor": HarborProperty(),
    "camrealty": CamRealtyService(),
}


# ========================================================================
# SHARED PIPELINE
# ========================================================================

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": settings.USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9,km;q=0.8",
})


def site_dir(adapter: Adapter) -> Path:
    return BRONZE / adapter.name.replace(".", "_")


def html_dir(adapter: Adapter) -> Path:
    return site_dir(adapter) / "html"


def out_json(adapter: Adapter) -> Path:
    return site_dir(adapter) / "raw_listings.json"


def polite_sleep() -> None:
    time.sleep(settings.REQUEST_DELAY_SECONDS + random.uniform(0, 1.0))


def fetch(url: str) -> str | None:
    for attempt in range(1, settings.MAX_RETRIES + 1):
        try:
            response = SESSION.get(url, timeout=settings.REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response.text
            if response.status_code == 404:
                return None
            print(f"HTTP {response.status_code}", end=" ", flush=True)
        except Exception as exc:
            print(f"retry{attempt}({type(exc).__name__})", end=" ", flush=True)
        time.sleep(3 * attempt)
    return None


_BROWSER: dict = {}


def fetch_browser(url: str, scroll: bool = False, max_scrolls: int = 200,
                  patience: int = 6, count_fn=None,
                  headful: bool = False) -> str | None:
    """
    Render a page in a real browser. With scroll=True, keep scrolling until no
    new listing links appear - the only way to reach everything on a site that
    loads results lazily instead of paginating.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\nPlaywright required:  pip install playwright && playwright install chromium")
        sys.exit(1)

    if "page" not in _BROWSER:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=not headful)
        context = browser.new_context(user_agent=settings.USER_AGENT,
                                      viewport={"width": 1400, "height": 1000},
                                      locale="en-US")
        _BROWSER.update({"pw": pw, "browser": browser, "page": context.new_page()})

    page = _BROWSER["page"]
    try:
        page.goto(url, wait_until="domcontentloaded",
                  timeout=settings.REQUEST_TIMEOUT * 1000)
        page.wait_for_timeout(3500)
    except Exception as exc:
        print(f"browser goto failed ({type(exc).__name__})", end=" ", flush=True)
        return None

    if not scroll:
        page.mouse.wheel(0, 5000)
        page.wait_for_timeout(1200)
        return page.content()

    seen = 0
    stalls = 0
    html = page.content()
    for step in range(1, max_scrolls + 1):
        page.keyboard.press("End")
        page.mouse.wheel(0, 25000)
        page.wait_for_timeout(2000)

        clicked = False
        for label in ("Load more", "Show more", "See more", "View more",
                      "More", "Next", "បន្ថែម"):
            try:
                button = page.get_by_text(label, exact=False).first
                if button.is_visible(timeout=300):
                    button.click(timeout=1200)
                    page.wait_for_timeout(2000)
                    clicked = True
                    break
            except Exception:
                pass

        if not clicked:
            # some sites paginate with an arrow or a rel=next link
            for selector in ("a[rel='next']", "[aria-label*='ext']",
                             ".pagination a.next", "button.next"):
                try:
                    element = page.locator(selector).first
                    if element.is_visible(timeout=250):
                        element.click(timeout=1200)
                        page.wait_for_timeout(2000)
                        break
                except Exception:
                    pass

        html = page.content()
        count = count_fn(html) if count_fn else 0
        if count > seen:
            print(f"    scroll {step:>3}  {count} listings (+{count - seen})")
            seen, stalls = count, 0
        else:
            stalls += 1
            if stalls >= patience:
                print(f"    scroll {step:>3}  {count} listings - no change, stopping")
                break
    return html


def close_browser() -> None:
    if "browser" in _BROWSER:
        try:
            _BROWSER["browser"].close()
            _BROWSER["pw"].stop()
        except Exception:
            pass
        _BROWSER.clear()


def load_store(adapter: Adapter) -> dict[str, dict]:
    path = out_json(adapter)
    if not path.exists():
        return {}
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {r["listing_id"]: r for r in records if r.get("listing_id")}


def save_store(adapter: Adapter, store: dict[str, dict]) -> None:
    path = out_json(adapter)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(store.values()), indent=2, ensure_ascii=False),
                    encoding="utf-8")


def collect_urls(adapter: Adapter, force: bool = False,
                 max_pages: int = 40, headful: bool = False) -> list[str]:
    """Phase 1 - walk the filtered search pages and gather listing URLs."""
    directory = html_dir(adapter)
    directory.mkdir(parents=True, exist_ok=True)

    # Sites that load results lazily cannot be paginated; scroll instead.
    if adapter.pagination == "scroll":
        return collect_urls_by_scrolling(adapter, force=force, headful=headful)
    if adapter.pagination == "browser_pages":
        return collect_urls_browser_pages(adapter, force=force,
                                          max_pages=max_pages, headful=headful)

    urls: dict[str, None] = {}
    empty_streak = 0

    print(f"\nPhase 1 - collecting listing URLs from {adapter.name}")
    if adapter.expected_total:
        print(f"  expecting about {adapter.expected_total} listings")

    for page in range(1, max_pages + 1):
        path = directory / f"search_{page:04d}.html"
        if path.exists() and not force:
            html = path.read_text(encoding="utf-8")
            source = "cached"
        else:
            url = adapter.page_url(page)
            print(f"  page {page:>3}  fetching ...", end=" ", flush=True)
            html = fetch(url)
            if html is None:
                print("no response - stopping")
                break
            path.write_text(html, encoding="utf-8")
            source = f"{len(html):,} bytes"
            polite_sleep()

        base = adapter.page_url(page)
        hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
        found = []
        for href in hrefs:
            absolute = urljoin(base, href.strip()).split("#")[0].split("?")[0] \
                if adapter.name != "khpropertyhub.com" else urljoin(base, href.strip()).split("#")[0]
            if adapter.domain not in urlparse(absolute).netloc:
                continue
            if adapter.is_listing_url(absolute):
                found.append(absolute)

        new = [u for u in dict.fromkeys(found) if u not in urls]
        for u in new:
            urls[u] = None
        print(f"  page {page:>3}  {source:>14}  {len(found):>3} links, "
              f"{len(new):>3} new  (total {len(urls)})")

        if not new:
            empty_streak += 1
            if empty_streak >= 2:
                print("  no new URLs for 2 pages - stopping")
                break
        else:
            empty_streak = 0

        if adapter.pagination == "none":
            break

    url_list = list(urls)
    (site_dir(adapter) / "listing_urls.txt").write_text(
        "\n".join(url_list), encoding="utf-8")
    print(f"  collected {len(url_list)} unique listing URLs")
    return url_list


def extract_listing_urls(adapter: Adapter, html: str, base: str) -> list[str]:
    """Pull listing URLs out of a rendered page."""
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
    found: dict[str, None] = {}
    for href in hrefs:
        absolute = urljoin(base, href.strip()).split("#")[0]
        if adapter.domain not in urlparse(absolute).netloc:
            continue
        if adapter.is_listing_url(absolute):
            found.setdefault(absolute, None)
    return list(found)


def _walk_known_pages(adapter: Adapter, urls: dict, directory: Path,
                      force: bool, max_pages: int, headful: bool) -> list[str]:
    """Page through a site whose URL form the adapter already knows."""
    empty_streak = 0
    for page in range(2, max_pages + 1):
        path = directory / f"search_{page:04d}.html"
        url = adapter.page_url(page)

        if path.exists() and not force:
            html = path.read_text(encoding="utf-8")
            source = "cached"
        else:
            print(f"  page {page:>3}  loading ...", end=" ", flush=True)
            html = fetch_browser(url, headful=headful)
            if html is None:
                print("FAILED - stopping")
                break
            path.write_text(html, encoding="utf-8")
            source = "loaded"
            polite_sleep()

        found = extract_listing_urls(adapter, html, url)
        new = [u for u in found if u not in urls]
        for u in new:
            urls[u] = None
        print(f"  page {page:>3}  {source:>8}  {len(found):>3} links, "
              f"{len(new):>3} new  (total {len(urls)})")

        if not new:
            empty_streak += 1
            if empty_streak >= 2:
                print("  no new URLs for 2 pages - stopping")
                break
        else:
            empty_streak = 0

    url_list = list(urls)
    (site_dir(adapter) / "listing_urls.txt").write_text(
        "\n".join(url_list), encoding="utf-8")
    print(f"  collected {len(url_list)} unique listing URLs")
    return url_list


def collect_urls_browser_pages(adapter: Adapter, force: bool = False,
                               max_pages: int = 60,
                               headful: bool = False) -> list[str]:
    """
    Walk numbered pages of a JavaScript-rendered site.

    The page parameter's name and position are detected once by testing
    candidates on page 2, rather than assumed - this site keeps its parameters
    in the path, so a normal ?page=2 query does nothing.
    """
    directory = html_dir(adapter)
    directory.mkdir(parents=True, exist_ok=True)

    print(f"\nPhase 1 - paging {adapter.name} in a browser")
    if adapter.expected_total:
        print(f"  expecting about {adapter.expected_total} listings")

    # ---- page 1 ---------------------------------------------------------
    first_path = directory / "search_0001.html"
    if first_path.exists() and not force:
        html = first_path.read_text(encoding="utf-8")
        print("  page   1  cached", end="")
    else:
        print("  page   1  loading ...", end=" ", flush=True)
        html = fetch_browser(adapter.search_url, headful=headful)
        if html is None:
            print("FAILED")
            return []
        first_path.write_text(html, encoding="utf-8")
    urls = {u: None for u in extract_listing_urls(adapter, html, adapter.search_url)}
    print(f"  {len(urls)} listings")

    if not urls:
        print("  nothing found on page 1 - check is_listing_url()")
        return []

    # ---- work out how page 2 is addressed -------------------------------
    if getattr(adapter, "page_url_known", False):
        print(f"  page 2 -> {adapter.page_url(2)[-60:]}")
        return _walk_known_pages(adapter, urls, directory, force, max_pages, headful)

    print("  detecting the page parameter ...")
    builder = None
    for param in getattr(adapter, "PAGE_PARAM_CANDIDATES", ["page"]):
        for template in ("{url}&{param}={n}", "{url}?{param}={n}",
                         "{url}/{param}/{n}"):
            candidate = template.format(url=adapter.search_url, param=param, n=2)
            probe_html = fetch_browser(candidate, headful=headful)
            if probe_html is None:
                continue
            found = extract_listing_urls(adapter, probe_html, candidate)
            new = [u for u in found if u not in urls]
            if len(new) >= max(3, len(urls) * 0.3):
                builder = template
                page_param = param
                print(f"    -> '{template.format(url='...', param=param, n='N')}'"
                      f"  ({len(new)} new on page 2)")
                for u in found:
                    urls.setdefault(u, None)
                (directory / "search_0002.html").write_text(probe_html, encoding="utf-8")
                break
        if builder:
            break

    if builder is None:
        print("    no working page parameter found - keeping page 1 only")
        print("    open the site, click page 2, and send the URL from the bar")
        url_list = list(urls)
        (site_dir(adapter) / "listing_urls.txt").write_text(
            "\n".join(url_list), encoding="utf-8")
        return url_list

    # ---- remaining pages -------------------------------------------------
    empty_streak = 0
    for page in range(3, max_pages + 1):
        path = directory / f"search_{page:04d}.html"
        url = builder.format(url=adapter.search_url, param=page_param, n=page)

        if path.exists() and not force:
            page_html = path.read_text(encoding="utf-8")
            source = "cached"
        else:
            print(f"  page {page:>3}  loading ...", end=" ", flush=True)
            page_html = fetch_browser(url, headful=headful)
            if page_html is None:
                print("FAILED - stopping")
                break
            path.write_text(page_html, encoding="utf-8")
            source = "loaded"
            polite_sleep()

        found = extract_listing_urls(adapter, page_html, url)
        new = [u for u in found if u not in urls]
        for u in new:
            urls[u] = None
        print(f"  page {page:>3}  {source:>8}  {len(found):>3} links, "
              f"{len(new):>3} new  (total {len(urls)})")

        if not new:
            empty_streak += 1
            if empty_streak >= 2:
                print("  no new URLs for 2 pages - stopping")
                break
        else:
            empty_streak = 0

    url_list = list(urls)
    (site_dir(adapter) / "listing_urls.txt").write_text(
        "\n".join(url_list), encoding="utf-8")
    print(f"  collected {len(url_list)} unique listing URLs")
    return url_list


def collect_urls_by_scrolling(adapter: Adapter, force: bool = False,
                              headful: bool = False) -> list[str]:
    directory = html_dir(adapter)
    directory.mkdir(parents=True, exist_ok=True)
    cache = directory / "search_scrolled.html"

    print(f"\nPhase 1 - scrolling {adapter.name}")
    if adapter.expected_total:
        print(f"  expecting about {adapter.expected_total} listings")

    if cache.exists() and not force:
        html = cache.read_text(encoding="utf-8")
        print("  using cached scrolled page")
    else:
        def count_listings(page_html: str) -> int:
            """
            Count listing links in a full HTML document.

            The adapter's URL_RE is anchored with $ so it can validate a single
            URL; that anchor makes it match nothing when scanned across a whole
            page, so links are extracted first and validated individually.
            """
            hrefs = re.findall(r'href=["\']([^"\']+)["\']', page_html)
            found = {urljoin(adapter.search_url, h.strip()).split("#")[0]
                     for h in hrefs}
            return sum(1 for u in found if adapter.is_listing_url(u))

        html = fetch_browser(adapter.search_url, scroll=True,
                             count_fn=count_listings, headful=headful)
        if html is None:
            print("  could not load the search page")
            return []
        cache.write_text(html, encoding="utf-8")

    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
    urls: dict[str, None] = {}
    for href in hrefs:
        absolute = urljoin(adapter.search_url, href.strip()).split("#")[0]
        if adapter.domain in urlparse(absolute).netloc and adapter.is_listing_url(absolute):
            urls.setdefault(absolute, None)

    url_list = list(urls)
    (site_dir(adapter) / "listing_urls.txt").write_text(
        "\n".join(url_list), encoding="utf-8")
    print(f"  collected {len(url_list)} unique listing URLs")
    return url_list


def fetch_details(
    adapter: Adapter,
    urls: list[str],
    force: bool = False,
    limit: int | None = None,
    from_cache: bool = False,
    reset_output: bool = False,
) -> None:
    """Phase 2: fetch or reparse every current listing detail page."""
    directory = html_dir(adapter)
    directory.mkdir(parents=True, exist_ok=True)

    if from_cache and force:
        print("\nNote: --force is ignored together with --from-cache.")
        force = False

    store = {} if reset_output else load_store(adapter)
    before = len(store)
    todo = urls[:limit] if limit else urls

    print(f"\nPhase 2 - processing {len(todo)} listing pages")
    if not from_cache:
        minutes = len(todo) * (settings.REQUEST_DELAY_SECONDS + 0.5) / 60
        print(f"  estimated time: {minutes:.0f} min")

    parsed = 0
    skipped = 0
    failed = 0
    missing_cache = 0
    downloaded = 0

    for i, url in enumerate(todo, 1):
        listing_id = adapter.listing_id(url) or str(i)
        cache_id = adapter.detail_cache_key(url) or listing_id
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", cache_id)[:60]
        path = directory / f"detail_{safe}.html"
        html: str | None = None

        if path.exists() and not force:
            html = path.read_text(encoding="utf-8")
        elif from_cache:
            missing_cache += 1
            print(f"  [{i}/{len(todo)}] missing cache  {listing_id}")
            continue
        else:
            html = fetch(url)
            if adapter.needs_browser and (html is None or len(html) < 20_000):
                html = fetch_browser(url)
            if html is None:
                failed += 1
                print(f"  [{i}/{len(todo)}] download failed  {listing_id}")
                continue
            path.write_text(html, encoding="utf-8")
            downloaded += 1
            polite_sleep()

        try:
            record = adapter.parse_detail(html, url)
        except Exception as exc:
            print(
                f"  parse error on {url[:60]}: "
                f"{type(exc).__name__}: {exc}"
            )
            failed += 1
            continue

        if record is None:
            skipped += 1
            continue

        store[record["listing_id"]] = record
        parsed += 1

        if i % 25 == 0 or i == len(todo):
            save_store(adapter, store)
            print(
                f"  [{i}/{len(todo)}] parsed {parsed}, skipped {skipped}, "
                f"failed {failed}"
            )

    save_store(adapter, store)

    print("\nDETAIL SUMMARY")
    print("=" * 68)
    print(f"  candidates             : {len(todo)}")
    print(f"  downloaded             : {downloaded}")
    print(f"  detail pages parsed    : {parsed}")
    print(f"  missing cached pages   : {missing_cache}")
    print(f"  skipped empty pages    : {skipped}")
    print(f"  failed                 : {failed}")
    print("=" * 68)

    summarise(
        adapter,
        store,
        before,
        parsed,
        skipped,
        failed,
        missing_cache,
    )


def summarise(
    adapter: Adapter,
    store: dict[str, dict],
    before: int,
    parsed: int,
    skipped: int,
    failed: int,
    missing_cache: int = 0,
) -> None:
    records = list(store.values())
    sale = [
        row for row in records
        if row.get("listing_type") in {"sale", "sale/rent"}
    ]
    usable = [
        row for row in sale
        if row.get("price_usd") is not None
        and row.get("size_m2") is not None
    ]

    def count_present(field: str) -> int:
        return sum(row.get(field) is not None for row in sale)

    with_description = sum(bool(clean_text(row.get("description") or "")) for row in sale)
    with_district = sum(bool(row.get("district")) for row in sale)
    needs_review = sum(bool(row.get("needs_manual_review")) for row in sale)
    non_condo = sum(
        normalize_property_type(row.get("property_type"))
        not in {None, "Condo", "Penthouse", "Apartment"}
        for row in sale
    )
    districts = sorted({row["district"] for row in sale if row.get("district")})
    property_types = Counter(
        normalize_property_type(row.get("property_type")) or "MISSING"
        for row in sale
    )

    recovered_from_text: dict[str, int] = {}
    for field in (
        "bedrooms", "bathrooms", "unit_floor", "building_total_floors",
    ):
        recovered_from_text[field] = sum(
            1
            for row in sale
            if any(
                token in clean_text(row.get(f"{field}_source") or "").lower()
                for token in ("title", "description", "overview")
            )
        )

    print("\n" + "=" * 68)
    print(f"  {adapter.name}")
    print(f"  new this run             : {len(store) - before}")
    print(f"  total stored             : {len(records)}")
    print(f"  sale or sale/rent        : {len(sale)}")
    print(f"  usable (price + size)    : {len(usable)}")
    print(f"  with bedrooms            : {count_present('bedrooms')}")
    print(f"  with bathrooms           : {count_present('bathrooms')}")
    print(f"  with unit floor          : {count_present('unit_floor')}")
    print(f"  with building floors     : {count_present('building_total_floors')}")
    print(f"  with description         : {with_description}")
    print(f"  with district            : {with_district}")
    print(f"  flagged for review       : {needs_review}")
    print(f"  non-condo property types : {non_condo}")

    conflict_counts = Counter(
        key
        for row in sale
        for key, value in row.items()
        if key.endswith("_conflict") and value
    )
    if conflict_counts:
        print("  conflict fields          : " + ", ".join(
            f"{field}={count}" for field, count in conflict_counts.most_common()
        ))
    print(
        f"  parsed/skipped/fail/cache: "
        f"{parsed}/{skipped}/{failed}/{missing_cache}"
    )

    print("\n  recovered from title/description:")
    for field, count in recovered_from_text.items():
        print(f"    {field:<27}{count:>6}")

    print("\n  property types:")
    for value, count in property_types.most_common():
        print(f"    {value:<27}{count:>6}")

    # Detect accidental extraction of one template default.
    for column in ("price_usd", "size_m2", "unit_floor"):
        values = [row.get(column) for row in records if row.get(column) is not None]
        if len(values) >= 20:
            top, count = Counter(values).most_common(1)[0]
            if count / len(values) > 0.5:
                print(
                    f"\n  WARNING: {count}/{len(values)} listings share "
                    f"{column} = {top}."
                )
                print("  This may be a template default rather than listing data.")

    if districts:
        print(f"\n  districts ({len(districts)}): {', '.join(districts)}")

    print(f"  saved to                 : {out_json(adapter)}")
    print("=" * 68)


def run_inspect(adapter: Adapter, headful: bool = False) -> None:
    print(f"\nINSPECT - {adapter.name}")
    print(f"  {adapter.page_url(1)}\n")
    html = None if adapter.needs_browser else fetch(adapter.page_url(1))
    if html is None or len(html) < 20_000:
        html = fetch_browser(adapter.page_url(1), headful=headful)
    if html is None:
        print("  could not load the search page")
        return

    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
    urls = [u for u in dict.fromkeys(
        urljoin(adapter.search_url, h.strip()).split("#")[0] for h in hrefs)
        if adapter.is_listing_url(u)]
    print(f"  listing URLs on page 1: {len(urls)}")
    for url in urls[:5]:
        print(f"    {url}")
        derived = adapter.from_url(url)
        if derived:
            print(f"      from url -> {derived}")

    if not urls:
        print("  none matched - check is_listing_url()")
        return

    print(f"\n  fetching one listing page ...")
    polite_sleep()
    detail = fetch(urls[0])
    if adapter.needs_browser and (detail is None or len(detail) < 20_000):
        detail = fetch_browser(urls[0], headful=headful)
    if detail is None:
        print("  could not load it")
        return
    html_dir(adapter).mkdir(parents=True, exist_ok=True)
    (html_dir(adapter) / "inspect_sample.html").write_text(detail, encoding="utf-8")

    record = adapter.parse_detail(detail, urls[0])
    if record is None:
        print("  parse_detail returned nothing - no price and no size found")
        print(f"  saved page to {html_dir(adapter) / 'inspect_sample.html'}")
        return
    print("\n  parsed record:")
    for key, value in record.items():
        if value not in (None, ""):
            shown = str(value)
            print(f"    {key:<15} = {shown[:70]}")


# ========================================================================
# MAIN
# ========================================================================

def main() -> None:
    ap = argparse.ArgumentParser(description="Scrape agency property sites")
    ap.add_argument("--site", choices=list(ADAPTERS), help="which site")
    ap.add_argument("--all", action="store_true", help="run every adapter")
    ap.add_argument("--inspect", action="store_true",
                    help="check one search page and one detail page")
    ap.add_argument("--urls-only", action="store_true", help="phase 1 only")
    ap.add_argument("--from-cache", action="store_true",
                    help="reparse saved HTML only; do not use the network")
    ap.add_argument("--force", action="store_true",
                    help="redownload cached search and detail pages")
    ap.add_argument("--detail-force", action="store_true",
                    help="redownload detail pages but keep search cache")
    ap.add_argument("--reset-output", action="store_true",
                    help="rebuild raw_listings.json instead of merging")
    ap.add_argument("--limit", "--detail-limit", dest="limit", type=int,
                    help="cap detail pages processed")
    ap.add_argument("--max-pages", type=int, default=40)
    ap.add_argument("--headful", action="store_true",
                    help="show the browser window")
    args = ap.parse_args()

    if not args.site and not args.all:
        ap.error("choose --site or --all")

    targets = list(ADAPTERS.values()) if args.all else [ADAPTERS[args.site]]

    try:
        for adapter in targets:
            if args.inspect:
                run_inspect(adapter, headful=args.headful)
                continue

            url_file = site_dir(adapter) / "listing_urls.txt"
            if args.from_cache:
                if not url_file.exists():
                    print(
                        f"\n{adapter.name}: no cached listing_urls.txt. "
                        "Run phase 1 once without --from-cache."
                    )
                    continue
                urls = [
                    url
                    for url in url_file.read_text(encoding="utf-8").splitlines()
                    if url
                ]
                print(f"\n{adapter.name}: {len(urls)} URLs from cache")
            else:
                urls = collect_urls(
                    adapter,
                    force=args.force,
                    max_pages=args.max_pages,
                    headful=args.headful,
                )

            if args.urls_only:
                continue

            fetch_details(
                adapter,
                urls,
                force=args.detail_force or args.force,
                limit=args.limit,
                from_cache=args.from_cache,
                reset_output=args.reset_output,
            )
    finally:
        close_browser()


if __name__ == "__main__":
    main()
