#!/usr/bin/env python
"""
clean.py - PP PropertyLens
==========================

Bronze -> Silver.

Merges the four scraped sources into one clean dataset, applying the project
scope: condominiums, for sale, in Phnom Penh.

    realestate.com.kh   data/bronze/realestate/raw_listings.json
    khmer24.com         data/bronze/khmer24/raw_listings.json
    khpropertyhub.com   data/bronze/khpropertyhub_com/raw_listings.json
    aps.com.kh          data/bronze/aps_com_kh/raw_listings.json

WHAT IT DOES

    1. load every source into one standard schema
    2. recover missing fields from text already collected
         - bedrooms from titles like "1 Bedroom Condo ..."
         - district from location text when the URL did not carry it
    3. standardise districts across all sources (one label per khan)
    4. apply the scope filter, counting every exclusion
    5. remove duplicates - within a source, then across sources
    6. flag outliers by price per square metre
    7. write the silver dataset and a full cleaning report

Nothing is deleted silently. Every row that leaves the pipeline is counted,
and the funnel is printed and written to the report.

Usage:
    python src/clean.py
    python src/clean.py --keep-rentals      # also write a rental file
    python src/clean.py --verbose

Output:
    data/silver/cleaned_listings.csv
    data/silver/duplicates.csv
    outputs/reports/cleaning_report.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
sys.path.insert(0, str(CONFIG_DIR))
import settings  # noqa: E402

import pandas as pd  # noqa: E402


# ========================================================================
# SOURCES
# ========================================================================

SOURCE_FILES = {
    "realestate.com.kh": settings.BRONZE_DIR / "realestate" / "raw_listings.json",
    "khmer24.com": settings.BRONZE_DIR / "khmer24" / "raw_listings.json",
    "khpropertyhub.com": settings.BRONZE_DIR / "khpropertyhub_com" / "raw_listings.json",
    "aps.com.kh": settings.BRONZE_DIR / "aps_com_kh" / "raw_listings.json",
    "harbor-property.com": settings.BRONZE_DIR / "harbor-property_com" / "raw_listings.json",
    "camrealtyservice.com": settings.BRONZE_DIR / "camrealtyservice_com" / "raw_listings.json",
}

COLUMNS = [
    "listing_id", "source", "url",
    "price_usd", "size_m2", "price_per_m2",
    "bedrooms", "bathrooms", "floor",
    "property_type", "listing_type",
    "district", "commune", "province",
    "project_name", "latitude", "longitude",
    "title", "created_at",
    "price_original_usd", "price_reduced", "property_code",
    "bedrooms_recovered", "district_recovered", "coord_precision",
    "scraped_at",
]


# ========================================================================
# DISTRICT STANDARDISATION
# ========================================================================
# Every source spells the khans differently. This is the single place where
# they are reconciled. Seen live:
#   realestate.com.kh  "Toul Kork"          khmer24 (km)  "ទួលគោក"
#   khmer24 (en)       "Tuol Kouk"          khpropertyhub "tuol-kouk"
#   aps.com.kh         "toul-tumpung"

DISTRICT_ALIASES = {
    "toulkork": "Toul Kork", "tuolkouk": "Toul Kork", "tuolkork": "Toul Kork",
    "ទួលគោក": "Toul Kork",
    "saensokh": "Sen Sok", "sensok": "Sen Sok", "seansokh": "Sen Sok",
    "សែនសុខ": "Sen Sok",
    "chamkarmon": "Chamkarmon", "chamkarmorn": "Chamkarmon",
    "chamkarmon1": "Chamkarmon", "ចំការមន": "Chamkarmon",
    "boengkengkang": "Boeung Keng Kang", "boeungkengkang": "Boeung Keng Kang",
    "boeungkengkang1": "Boeung Keng Kang", "boeungkengkang2": "Boeung Keng Kang",
    "boeungkengkang3": "Boeung Keng Kang", "bkk": "Boeung Keng Kang",
    "bkk1": "Boeung Keng Kang", "bkk2": "Boeung Keng Kang",
    "bkk3": "Boeung Keng Kang", "បឹងកេងកង": "Boeung Keng Kang",
    "daunpenh": "Daun Penh", "dounpenh": "Daun Penh", "ដូនពេញ": "Daun Penh",
    "meanchey": "Meanchey", "មានជ័យ": "Meanchey",
    "chraoychongvar": "Chroy Changvar", "chroychangvar": "Chroy Changvar",
    "chroychongvar": "Chroy Changvar", "ជ្រោយចង្វារ": "Chroy Changvar",
    "ruesseikaev": "Russey Keo", "russeykeo": "Russey Keo", "ឫស្សីកែវ": "Russey Keo",
    "chbarampov": "Chbar Ampov", "ច្បារអំពៅ": "Chbar Ampov",
    "praekpnov": "Prek Pnov", "prekpnov": "Prek Pnov", "ព្រែកព្នៅ": "Prek Pnov",
    "dangkao": "Dangkao", "dangkor": "Dangkao", "ដង្កោ": "Dangkao",
    "pousenchey": "Pur Senchey", "pursenchey": "Pur Senchey",
    "porsenchey": "Pur Senchey", "ពោធិ៍សែនជ័យ": "Pur Senchey",
    "prampirmeakkakra": "Prampi Makara", "prampimakara": "Prampi Makara",
    "7makara": "Prampi Makara", "៧មករា": "Prampi Makara",
    "kamboul": "Kamboul", "កំបូល": "Kamboul",
    # sangkats that sources sometimes report as districts
    "tonlebassac": "Chamkarmon", "tonlebasak": "Chamkarmon",
    "toultumpung": "Chamkarmon", "toultompoung": "Chamkarmon",
    "tuoltumpung": "Chamkarmon", "boeungtrabek": "Chamkarmon",
    "phsarchas": "Daun Penh", "watphnom": "Daun Penh",
    "boeungkak": "Toul Kork", "boeungkak1": "Toul Kork", "boeungkak2": "Toul Kork",
}

# ---------------------------------------------------------------- sangkats
# Phnom Penh has 14 khans and about 105 sangkats. Several sources report the
# sangkat instead of the khan - harbor-property.com puts it in the URL
# (/house/detail/110586/chak-angrae-leu/condo), and khmer24 listings often
# name one in the title. The model uses khan, so sangkats are mapped up while
# the original value is preserved in `commune`.
SANGKAT_TO_KHAN_MAP = {
    # Boeung Keng Kang (khan since 2019, split from Chamkarmon)
    "boeungkengkang1": "Boeung Keng Kang", "boeungkengkang2": "Boeung Keng Kang",
    "boeungkengkang3": "Boeung Keng Kang", "bkk1": "Boeung Keng Kang",
    "bkk2": "Boeung Keng Kang", "bkk3": "Boeung Keng Kang",
    "olympic": "Boeung Keng Kang", "toulsvayprey1": "Boeung Keng Kang",
    "toulsvayprey2": "Boeung Keng Kang", "tuolsvayprey1": "Boeung Keng Kang",
    "tuolsvayprey2": "Boeung Keng Kang", "tumnobtuek": "Boeung Keng Kang",
    "tumnuptuek": "Boeung Keng Kang",
    # Chamkarmon
    "tonlebassac": "Chamkarmon", "tonlebasak": "Chamkarmon",
    "boeungtrabek": "Chamkarmon", "boeungtrobaek": "Chamkarmon",
    "toultumpung1": "Chamkarmon", "toultumpung2": "Chamkarmon",
    "toultumpungi": "Chamkarmon", "toultumpungii": "Chamkarmon",
    "tuoltumpung1": "Chamkarmon", "tuoltumpung2": "Chamkarmon",
    "phsardoeumthkov": "Chamkarmon", "phsardaeumthkov": "Chamkarmon",
    "phsardaeumkor": "Chamkarmon", "phsardeumkor": "Chamkarmon",
    # Daun Penh
    "srahchak": "Daun Penh", "watphnom": "Daun Penh", "phsarchas": "Daun Penh",
    "phsarthmei1": "Daun Penh", "phsarthmei2": "Daun Penh",
    "phsarthmei3": "Daun Penh", "phsarthmeyi": "Daun Penh",
    "phsarkandal1": "Daun Penh", "phsarkandal2": "Daun Penh",
    "cheychumneas": "Daun Penh", "cheychumneah": "Daun Penh",
    "chaktomuk": "Daun Penh", "chaktomukh": "Daun Penh",
    "boeungreang": "Daun Penh", "boeungraing": "Daun Penh",
    # Prampi Makara
    "ourussei1": "Prampi Makara", "ourussei2": "Prampi Makara",
    "ourussei3": "Prampi Makara", "ourussei4": "Prampi Makara",
    "orussei1": "Prampi Makara", "orussei2": "Prampi Makara",
    "orussei3": "Prampi Makara", "orussei4": "Prampi Makara",
    "boeungprolit": "Prampi Makara", "mittapheap": "Prampi Makara",
    "vealvong": "Prampi Makara", "monourom": "Prampi Makara",
    # Toul Kork
    "boeungkak1": "Toul Kork", "boeungkak2": "Toul Kork",
    "boeungkaki": "Toul Kork", "boeungkakii": "Toul Kork",
    "phsardepou1": "Toul Kork", "phsardepou2": "Toul Kork",
    "phsardepou3": "Toul Kork", "phsardepoui": "Toul Kork",
    "teuklaak1": "Toul Kork", "teuklaak2": "Toul Kork", "teuklaak3": "Toul Kork",
    "tueklak1": "Toul Kork", "tueklak2": "Toul Kork", "tueklak3": "Toul Kork",
    "boeungsalang": "Toul Kork", "boengsalang": "Toul Kork",
    # Sen Sok
    "phnompenhthmei": "Sen Sok", "teukthla": "Sen Sok", "tuekthla": "Sen Sok",
    "khmuonh": "Sen Sok", "krangthnong": "Sen Sok", "koukkleang": "Sen Sok",
    "obekkaam": "Sen Sok", "oubaekkam": "Sen Sok", "oubekkaam": "Sen Sok",
    # Meanchey
    "stuengmeanchey": "Meanchey", "stuengmeanchey1": "Meanchey",
    "stuengmeanchey2": "Meanchey", "stuengmeanchey3": "Meanchey",
    "steungmeanchey": "Meanchey", "boeungtumpun": "Meanchey",
    "boeungtumpun1": "Meanchey", "boeungtumpun2": "Meanchey",
    "boengtompun": "Meanchey", "boengtompuni": "Meanchey",
    "boengtompunii": "Meanchey", "chakangraeleu": "Meanchey",
    "chakangraekraom": "Meanchey", "chakangrekrom": "Meanchey",
    # Russey Keo
    "toulsangke": "Russey Keo", "toulsangke1": "Russey Keo",
    "toulsangke2": "Russey Keo", "tuolsangkae": "Russey Keo",
    "chrangchamres": "Russey Keo", "chrangchamres1": "Russey Keo",
    "chrangchamres2": "Russey Keo", "svaypak": "Russey Keo",
    "kilomaetrlekhprammuoy": "Russey Keo", "ruesseikaev": "Russey Keo",
    # Chroy Changvar
    "chroychangvar": "Chroy Changvar", "chraoychongvar": "Chroy Changvar",
    "prekleap": "Chroy Changvar", "praeklieb": "Chroy Changvar",
    "prektasek": "Chroy Changvar", "praektasek": "Chroy Changvar",
    "bakkheng": "Chroy Changvar", "kaohdach": "Chroy Changvar",
    # Chbar Ampov
    "chbarampov1": "Chbar Ampov", "chbarampov2": "Chbar Ampov",
    "chbarampovi": "Chbar Ampov", "nirouth": "Chbar Ampov",
    "niroth": "Chbar Ampov", "prekpra": "Chbar Ampov",
    "praekpra": "Chbar Ampov", "prekaeng": "Chbar Ampov",
    "praekaeng": "Chbar Ampov", "vealsbov": "Chbar Ampov",
    "kbalkaoh": "Chbar Ampov", "prekthmei": "Chbar Ampov",
    # Pur Senchey
    "chaomchau": "Pur Senchey", "chaomchau1": "Pur Senchey",
    "chaomchau2": "Pur Senchey", "chaomchau3": "Pur Senchey",
    "chomchao": "Pur Senchey", "kakab": "Pur Senchey", "kakab1": "Pur Senchey",
    "kakab2": "Pur Senchey", "samraongkraom": "Pur Senchey",
    "phleungchehroteh": "Pur Senchey", "trapeangkrasang": "Pur Senchey",
    "boengthum": "Pur Senchey",
    # Dangkao
    "preysa": "Dangkao", "cheungaek": "Dangkao", "kongnoy": "Dangkao",
    "preyveaeng": "Dangkao", "krangpongro": "Dangkao", "saksampov": "Dangkao",
    "roluos": "Dangkao", "pongtuek": "Dangkao", "tien": "Dangkao",
    "skoas": "Dangkao", "koukroka": "Dangkao",
    # Prek Pnov
    "praekphnov": "Prek Pnov", "ponheapon": "Prek Pnov",
    "samraong": "Prek Pnov", "ponsang": "Prek Pnov",
    # Kamboul
    "kantaok": "Kamboul", "ovlaok": "Kamboul", "sambuormeas": "Kamboul",
    "snaor": "Kamboul",
}

DISTRICT_ALIASES.update(SANGKAT_TO_KHAN_MAP)

# Kept so the original value can still be reported as the commune.
SANGKAT_TO_KHAN = set(SANGKAT_TO_KHAN_MAP)

VALID_DISTRICTS = {
    "Toul Kork", "Sen Sok", "Chamkarmon", "Boeung Keng Kang", "Daun Penh",
    "Meanchey", "Chroy Changvar", "Russey Keo", "Chbar Ampov", "Prek Pnov",
    "Dangkao", "Pur Senchey", "Prampi Makara", "Kamboul",
}


def district_key(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    if re.search(r"[\u1780-\u17FF]", text):        # Khmer script: keep as-is
        return re.sub(r"\s+", "", text)
    return re.sub(r"[^a-z0-9]", "", text)


def standardise_district(raw: Any) -> tuple[str | None, bool]:
    """Return (standard name, was_sangkat). None if unrecognised."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None, False
    key = district_key(raw)
    if not key:
        return None, False
    if key in DISTRICT_ALIASES:
        return DISTRICT_ALIASES[key], key in SANGKAT_TO_KHAN
    for alias in sorted(DISTRICT_ALIASES, key=len, reverse=True):
        if len(alias) >= 5 and alias in key:
            return DISTRICT_ALIASES[alias], alias in SANGKAT_TO_KHAN
    return None, False


# ========================================================================
# FIELD RECOVERY
# ========================================================================

def recover_bedrooms(row: dict) -> int | None:
    """
    khmer24 cards rarely state bedrooms, but the titles almost always do:
        "Urban Loft - 1 Bedroom for Sale"      -> 1
        "Studio condo for sale"                -> 0
    """
    text = " ".join(str(row.get(field) or "") for field in
                    ("title", "description", "card_text"))
    if not text.strip():
        return None
    low = text.lower()

    match = re.search(r"(\d)\s*[- ]?\s*(?:bed\s?rooms?|br\b|bdr\b)", low)
    if match:
        value = int(match.group(1))
        if 0 <= value <= 10:
            return value

    match = re.search(r"(?:bed\s?rooms?)\s*[:\-]?\s*(\d)", low)
    if match:
        value = int(match.group(1))
        if 0 <= value <= 10:
            return value

    if re.search(r"\bstudio\b", low):
        return 0

    match = re.search(r"បន្ទប់គេង\s*(\d)", text)
    if match:
        return int(match.group(1))
    return None


def recover_district(row: dict) -> str | None:
    """
    aps.com.kh puts the district in the slug, but 30 of 124 slugs omit it.
    The location text and title usually still name it.
    """
    for field in ("location_text", "address", "commune", "title", "description"):
        value = row.get(field)
        if not value:
            continue
        standard, _ = standardise_district(value)
        if standard:
            return standard
        for part in re.split(r"[,\|\-/]", str(value)):
            standard, _ = standardise_district(part)
            if standard:
                return standard
    return None


def to_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value) if not pd.isna(value) else None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None


# ========================================================================
# LOAD
# ========================================================================

def load_source(name: str, path: Path) -> list[dict]:
    if not path.exists():
        print(f"  {name:<22} MISSING  ({path})")
        return []
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"  {name:<22} UNREADABLE: {exc}")
        return []
    if not isinstance(records, list):
        return []
    for record in records:
        record["source"] = record.get("source") or name
    print(f"  {name:<22} {len(records):>6} records")
    return records


def to_standard(row: dict) -> dict:
    """Map any source's row onto the shared schema."""
    out = {column: None for column in COLUMNS}

    out["listing_id"] = str(row.get("listing_id") or "")
    out["source"] = row.get("source")
    out["url"] = row.get("url")
    out["price_usd"] = to_number(row.get("price_usd"))
    out["size_m2"] = to_number(row.get("size_m2"))
    out["bedrooms"] = to_number(row.get("bedrooms"))
    out["bathrooms"] = to_number(row.get("bathrooms"))
    out["floor"] = to_number(row.get("floor"))
    out["property_type"] = row.get("property_type") or "Condo"
    out["listing_type"] = (row.get("listing_type") or "sale").lower()
    out["project_name"] = row.get("project_name")
    out["latitude"] = to_number(row.get("latitude"))
    out["longitude"] = to_number(row.get("longitude"))
    out["title"] = row.get("title")
    out["created_at"] = row.get("created_at") or row.get("listed_date_text")
    out["price_original_usd"] = to_number(row.get("price_original_usd"))
    out["price_reduced"] = to_number(row.get("price_reduced"))
    out["property_code"] = row.get("property_code")
    out["scraped_at"] = row.get("scraped_at")
    out["province"] = row.get("province") or "Phnom Penh"

    # ---- district ----------------------------------------------------
    district, was_sangkat = standardise_district(row.get("district"))
    recovered = False
    if district is None:
        district = recover_district(row)
        recovered = district is not None
    out["district"] = district
    out["district_recovered"] = recovered

    commune = row.get("commune")
    if not commune and was_sangkat:
        commune = row.get("district")
    out["commune"] = commune

    # ---- bedrooms ------------------------------------------------------
    if out["bedrooms"] is None:
        recovered_beds = recover_bedrooms(row)
        out["bedrooms"] = recovered_beds
        out["bedrooms_recovered"] = recovered_beds is not None
    else:
        out["bedrooms_recovered"] = False

    out["coord_precision"] = ("exact" if out["latitude"] and out["longitude"]
                              else "district")

    if out["price_usd"] and out["size_m2"]:
        out["price_per_m2"] = round(out["price_usd"] / out["size_m2"], 2)

    return out


# ========================================================================
# DEDUPLICATION
# ========================================================================

# Matching tolerances. Platforms round differently - one may list 58 m2 and
# another 58.2 - so exact equality would miss real duplicates.
SIZE_TOL_PCT = 0.03          # 3%
SIZE_TOL_ABS = 2.0           # or 2 m2, whichever is larger
PRICE_TOL_PCT = 0.03         # 3%


def _both(a: Any, b: Any) -> bool:
    """True when both values are present."""
    return pd.notna(a) and pd.notna(b)


def _norm_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def same_property(a: pd.Series, b: pd.Series) -> tuple[bool, str]:
    """
    Decide whether two listings describe the same physical unit.

    The logic has two halves.

    REQUIRED - these must agree, or the listings cannot be the same unit:
        district, price (within 3%), size (within 3% or 2 m2), bedrooms

    DISCRIMINATORS - checked only when BOTH records carry the value. If they
    are present and differ, the listings are different units even when price
    and size match:
        floor, bathrooms, commune, project name

    The floor rule matters most. Two units in the same building, same layout,
    same asking price, on the 12th and the 15th floor, are two properties -
    not one listing posted twice. Without this check they would be merged and
    the dataset would silently lose a real unit.

    Discriminators are skipped when either side is missing, because absence is
    not disagreement.
    """
    # ---- required ------------------------------------------------------
    if a["district"] != b["district"]:
        return False, ""

    if not (_both(a["price_usd"], b["price_usd"])):
        return False, ""
    high_price = max(a["price_usd"], b["price_usd"])
    if abs(a["price_usd"] - b["price_usd"]) > high_price * PRICE_TOL_PCT:
        return False, ""

    if not (_both(a["size_m2"], b["size_m2"])):
        return False, ""
    size_gap = abs(a["size_m2"] - b["size_m2"])
    size_allow = max(SIZE_TOL_ABS, max(a["size_m2"], b["size_m2"]) * SIZE_TOL_PCT)
    if size_gap > size_allow:
        return False, ""

    if _both(a["bedrooms"], b["bedrooms"]) and a["bedrooms"] != b["bedrooms"]:
        return False, ""

    # ---- discriminators ------------------------------------------------
    if _both(a["floor"], b["floor"]) and a["floor"] != b["floor"]:
        return False, "different floor"

    if _both(a["bathrooms"], b["bathrooms"]) and a["bathrooms"] != b["bathrooms"]:
        return False, "different bathrooms"

    if (_both(a["commune"], b["commune"])
            and _norm_name(a["commune"]) != _norm_name(b["commune"])):
        return False, "different commune"

    if (_both(a["project_name"], b["project_name"])
            and _norm_name(a["project_name"]) != _norm_name(b["project_name"])):
        return False, "different project"

    # ---- confidence ----------------------------------------------------
    strong = []
    if _both(a["project_name"], b["project_name"]):
        strong.append("project")
    if _both(a["floor"], b["floor"]):
        strong.append("floor")
    if _both(a["bathrooms"], b["bathrooms"]):
        strong.append("bathrooms")
    if _both(a["commune"], b["commune"]):
        strong.append("commune")

    if len(strong) >= 2:
        return True, "high: " + "+".join(strong)
    if strong:
        return True, "medium: " + "+".join(strong)
    return True, "low: price+size+bedrooms only"


class _Union:
    """Minimal union-find, so A=B and B=C collapse into one group."""

    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, i: int, j: int) -> None:
        ri, rj = self.find(i), self.find(j)
        if ri != rj:
            self.parent[max(ri, rj)] = min(ri, rj)


def deduplicate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Find duplicate listings and keep the most complete record of each group.

    Candidates are found with a sliding window over price-sorted rows: two
    listings can only match if their prices are within 3%, so the window is
    small and no pair is missed.
    """
    df = df.copy().reset_index(drop=True)
    df["_completeness"] = df[["price_usd", "size_m2", "bedrooms", "bathrooms",
                              "floor", "project_name", "commune",
                              "latitude"]].notna().sum(axis=1)

    order = df.sort_values("price_usd", kind="mergesort").index.tolist()
    union = _Union(len(df))
    reasons: dict[tuple[int, int], str] = {}
    rejected: Counter = Counter()

    for pos, i in enumerate(order):
        row_i = df.loc[i]
        if pd.isna(row_i["price_usd"]):
            continue
        ceiling = row_i["price_usd"] * (1 + PRICE_TOL_PCT)
        for j in order[pos + 1:]:
            row_j = df.loc[j]
            if pd.isna(row_j["price_usd"]) or row_j["price_usd"] > ceiling:
                break
            match, reason = same_property(row_i, row_j)
            if match:
                union.union(i, j)
                reasons[(min(i, j), max(i, j))] = reason
            elif reason:
                rejected[reason] += 1

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(df)):
        groups[union.find(i)].append(i)

    keep, drop = [], []
    overlap: Counter = Counter()
    confidence: Counter = Counter()

    df["duplicate_group"] = -1
    df["match_confidence"] = None

    group_id = 0
    for members in groups.values():
        if len(members) == 1:
            keep.append(members[0])
            continue
        group_id += 1
        block = df.loc[members].sort_values("_completeness", ascending=False)
        winner = block.index[0]
        keep.append(winner)
        drop.extend(block.index[1:])

        df.loc[members, "duplicate_group"] = group_id
        for pair, reason in reasons.items():
            if pair[0] in members and pair[1] in members:
                confidence[reason.split(":")[0]] += 1
                df.loc[list(pair), "match_confidence"] = reason

        sources = sorted(set(block["source"]))
        if len(sources) > 1:
            for x, first in enumerate(sources):
                for second in sources[x + 1:]:
                    overlap[(first, second)] += 1
        else:
            overlap[(sources[0], sources[0])] += len(members) - 1

    kept = df.loc[sorted(keep)].drop(columns=["_completeness"])
    removed = df.loc[sorted(drop)].drop(columns=["_completeness"])

    stats = {
        "overlap": dict(overlap),
        "confidence": dict(confidence),
        "rejected": dict(rejected),
        "groups": group_id,
    }
    return kept, removed, stats


# ========================================================================
# MAIN
# ========================================================================

def main() -> None:
    ap = argparse.ArgumentParser(description="Merge and clean all sources")
    ap.add_argument("--keep-rentals", action="store_true",
                    help="also write rentals to a separate file")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    funnel: list[tuple[str, int]] = []

    print("\nLoading sources")
    print("-" * 58)
    raw: list[dict] = []
    per_source_raw: dict[str, int] = {}
    for name, path in SOURCE_FILES.items():
        records = load_source(name, path)
        per_source_raw[name] = len(records)
        raw.extend(records)

    if not raw:
        print("\nNo data found. Run the scrapers first.")
        return

    funnel.append(("collected from all sources", len(raw)))

    print(f"\nStandardising {len(raw)} records ...")
    df = pd.DataFrame([to_standard(r) for r in raw], columns=COLUMNS)

    # ---------------------------------------------------------- filters
    stages = []

    before = len(df)
    rentals = df[df["listing_type"] != "sale"]
    df = df[df["listing_type"] == "sale"]
    stages.append(("removed rentals", before - len(df)))
    funnel.append(("for sale only", len(df)))

    before = len(df)
    df = df[df["province"].fillna("Phnom Penh").str.contains("Phnom Penh", case=False)]
    stages.append(("removed outside Phnom Penh", before - len(df)))
    funnel.append(("Phnom Penh only", len(df)))

    before = len(df)
    df = df[df["price_usd"].notna() & df["size_m2"].notna()]
    stages.append(("removed missing price or size", before - len(df)))
    funnel.append(("has price and size", len(df)))

    before = len(df)
    df = df[(df["price_usd"] >= 5_000) & (df["price_usd"] <= 5_000_000)]
    df = df[(df["size_m2"] >= 15) & (df["size_m2"] <= 800)]
    stages.append(("removed impossible price or size", before - len(df)))
    funnel.append(("plausible values", len(df)))

    # ------------------------------------------------------- duplicates
    print("Deduplicating ...")
    df, removed, dedup_stats = deduplicate(df)
    overlap = dedup_stats["overlap"]
    stages.append(("removed duplicates", len(removed)))
    funnel.append(("unique properties", len(df)))

    # --------------------------------------------------------- outliers
    if len(df) > 20:
        low = df["price_per_m2"].quantile(0.01)
        high = df["price_per_m2"].quantile(0.99)
        df["price_outlier"] = ~df["price_per_m2"].between(low, high)
    else:
        low = high = None
        df["price_outlier"] = False

    df = df.sort_values(["district", "price_usd"], na_position="last")

    # ------------------------------------------------------------ write
    settings.SILVER_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = settings.CLEANED_CSV
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    if len(removed):
        removed.to_csv(settings.SILVER_DIR / "duplicates.csv",
                       index=False, encoding="utf-8-sig")
    if args.keep_rentals and len(rentals):
        rentals.to_csv(settings.SILVER_DIR / "rentals.csv",
                       index=False, encoding="utf-8-sig")

    # ----------------------------------------------------------- report
    print("\n" + "=" * 58)
    print("  CLEANING FUNNEL")
    print("=" * 58)
    for label, count in funnel:
        print(f"  {label:<32} {count:>7,}")
    print("-" * 58)
    for label, count in stages:
        if count:
            print(f"  {label:<32} {-count:>7,}")

    print("\n" + "=" * 58)
    print("  BY SOURCE")
    print("=" * 58)
    print(f"  {'source':<22}{'raw':>7}{'kept':>7}{'med $':>10}{'med $/m2':>10}"
          f"{'distinct':>9}")
    kept_counts = df["source"].value_counts()
    for name in SOURCE_FILES:
        subset = df[df["source"] == name]
        kept = len(subset)
        if kept:
            median_price = f"${subset['price_usd'].median():,.0f}"
            median_ppm = f"${subset['price_per_m2'].median():,.0f}"
            distinct = subset["price_usd"].nunique()
            share = f"{distinct}/{kept}"
        else:
            median_price = median_ppm = share = "-"
        print(f"  {name:<22}{per_source_raw.get(name, 0):>7,}{kept:>7,}"
              f"{median_price:>10}{median_ppm:>10}{share:>9}")

    # A source whose prices are nearly all identical has captured a page
    # default rather than the listing price - the mortgage-calculator trap.
    for name in SOURCE_FILES:
        subset = df[df["source"] == name]
        if len(subset) >= 20:
            distinct = subset["price_usd"].nunique()
            if distinct / len(subset) < 0.3:
                print(f"\n  WARNING: {name} has only {distinct} distinct prices "
                      f"across {len(subset)} listings.")
                print("  Check the parser for that source before modelling.")

    print("\n" + "=" * 58)
    print("  DISTRICTS")
    print("=" * 58)
    district_counts = df["district"].value_counts(dropna=False)
    for district, count in district_counts.items():
        label = district if isinstance(district, str) else "(unknown)"
        median = df.loc[df["district"] == district, "price_per_m2"].median()
        median_text = f"${median:,.0f}/m2" if pd.notna(median) else "-"
        flag = "  <- thin" if count < 30 else ""
        print(f"  {label:<22}{count:>6,}   {median_text:>12}{flag}")

    unknown = int(df["district"].isna().sum())
    if unknown:
        print(f"\n  {unknown} rows have no district.")
        missing = df[df["district"].isna()]
        stragglers = Counter()
        for _, row in missing.iterrows():
            for field in ("commune", "title"):
                value = row.get(field)
                if isinstance(value, str) and value.strip():
                    stragglers[value.strip()[:40]] += 1
                    break
        if stragglers:
            print("  most common unmapped location values:")
            for value, count in stragglers.most_common(15):
                print(f"    {count:>4}  {value}")
            print("  add these to DISTRICT_ALIASES in clean.py, then re-run")
            path = settings.REPORT_DIR / "unmapped_locations.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "\n".join(f"{c}\t{v}" for v, c in stragglers.most_common()),
                encoding="utf-8")
            print(f"  full list -> {path}")

    print("\n" + "=" * 58)
    print("  COMPLETENESS")
    print("=" * 58)
    for column in ("price_usd", "size_m2", "bedrooms", "bathrooms", "floor",
                   "district", "project_name", "latitude"):
        filled = df[column].notna().sum()
        print(f"  {column:<22}{filled:>7,} / {len(df):,}  {filled/len(df):>6.0%}")
    recovered_beds = int(df["bedrooms_recovered"].sum())
    recovered_district = int(df["district_recovered"].sum())
    print(f"\n  bedrooms recovered from text : {recovered_beds}")
    print(f"  districts recovered from text: {recovered_district}")

    if overlap or dedup_stats["confidence"]:
        print("\n" + "=" * 58)
        print("  DUPLICATE DETECTION")
        print("=" * 58)
        print(f"  duplicate groups found : {dedup_stats['groups']}")
        print(f"  listings removed       : {len(removed)}")

        if dedup_stats["confidence"]:
            print("\n  match confidence:")
            for level in ("high", "medium", "low"):
                count = dedup_stats["confidence"].get(level, 0)
                if count:
                    print(f"    {level:<8}{count:>6}")
            print("    high   = 2+ of project/floor/bathrooms/commune agreed")
            print("    low    = only price, size and bedrooms were comparable")

        if dedup_stats["rejected"]:
            print("\n  pairs rejected despite matching price and size:")
            for reason, count in sorted(dedup_stats["rejected"].items(),
                                        key=lambda kv: -kv[1]):
                print(f"    {reason:<24}{count:>6}")
            print("    (same building, different unit - correctly kept apart)")

        if overlap:
            print("\n  where duplicates came from:")
            for (a, b), count in sorted(overlap.items(), key=lambda kv: -kv[1]):
                label = f"{a} = {b}" if a != b else f"{a} (reposted)"
                print(f"    {label:<50}{count:>5}")

    if len(df):
        print("\n" + "=" * 58)
        print("  PRICE")
        print("=" * 58)
        print(f"  median price        : ${df['price_usd'].median():,.0f}")
        print(f"  median price per m2 : ${df['price_per_m2'].median():,.0f}")
        print(f"  median size         : {df['size_m2'].median():.0f} m2")
        if low is not None:
            print(f"  outliers flagged    : {int(df['price_outlier'].sum())} "
                  f"(outside ${low:,.0f}-${high:,.0f} per m2)")

    print(f"\n  saved -> {out_csv}")
    print(f"  rows  -> {len(df):,}\n")

    write_report(df, funnel, stages, per_source_raw, overlap, district_counts)


def write_report(df, funnel, stages, per_source_raw, overlap, district_counts) -> None:
    lines = [
        "# Data Cleaning Report - PP PropertyLens",
        "",
        "Bronze to Silver. Scope: condominiums, for sale, Phnom Penh.",
        "",
        "## Cleaning funnel",
        "",
        "| Stage | Records |",
        "|---|---:|",
    ]
    for label, count in funnel:
        lines.append(f"| {label} | {count:,} |")

    lines += ["", "### Exclusions", "", "| Reason | Removed |", "|---|---:|"]
    for label, count in stages:
        if count:
            lines.append(f"| {label} | {count:,} |")

    lines += ["", "## By source", "",
              "| Source | Raw records | Kept | Share |", "|---|---:|---:|---:|"]
    kept_counts = df["source"].value_counts()
    for name in SOURCE_FILES:
        kept = int(kept_counts.get(name, 0))
        share = f"{kept / len(df):.0%}" if len(df) else "-"
        lines.append(f"| {name} | {per_source_raw.get(name, 0):,} | {kept:,} | {share} |")

    lines += ["", "## Districts", "",
              "| District | Listings | Median price per m2 |", "|---|---:|---:|"]
    for district, count in district_counts.items():
        if not isinstance(district, str):
            continue
        median = df.loc[df["district"] == district, "price_per_m2"].median()
        median_text = f"${median:,.0f}" if pd.notna(median) else "-"
        lines.append(f"| {district} | {count:,} | {median_text} |")

    if overlap:
        lines += ["", "## Cross-source duplicate overlap", "",
                  "Matched on district, bedrooms, size within 2 m2, and price within 3%.",
                  "", "| Sources | Duplicates removed |", "|---|---:|"]
        for (a, b), count in sorted(overlap.items(), key=lambda kv: -kv[1]):
            label = f"{a} / {b}" if a != b else f"{a} (internal)"
            lines.append(f"| {label} | {count:,} |")

    lines += ["", "## Completeness", "",
              "| Field | Filled | Share |", "|---|---:|---:|"]
    for column in ("price_usd", "size_m2", "bedrooms", "bathrooms", "floor",
                   "district", "project_name", "latitude"):
        filled = int(df[column].notna().sum())
        lines.append(f"| {column} | {filled:,} | {filled/len(df):.0%} |")

    lines += [
        "",
        "## Known limitations",
        "",
        "- Prices are **asking prices**, not final transaction prices.",
        "- Coordinates are absent from most sources, so `coord_precision` is",
        "  mostly `district`; distance features will use district or commune",
        "  centroids.",
        "- Some bedroom and district values were recovered from listing text",
        "  rather than structured fields; these are flagged by",
        "  `bedrooms_recovered` and `district_recovered`.",
        "",
    ]

    path = settings.REPORT_DIR / "cleaning_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  report -> {path}\n")


if __name__ == "__main__":
    main()