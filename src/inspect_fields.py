#!/usr/bin/env python
"""
inspect_fields.py - PP PropertyLens diagnostic
==============================================

Reads a page you have ALREADY downloaded and shows the real field names
inside a listing, so the scraper's field mapping can be corrected.

No network access. Nothing is re-downloaded.

Usage:
    python src/inspect_fields.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
sys.path.insert(0, str(CONFIG_DIR))
import settings  # noqa: E402

RESULTS_PATH = ("props", "pageProps", "cacheData", "results", "data")


def get_path(node, path):
    current = node
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def preview(value, limit: int = 70) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def main() -> None:
    page_file = settings.RE_HTML_DIR / "page_0001.html"
    if not page_file.exists():
        candidates = sorted(settings.RE_HTML_DIR.glob("page_*.html"))
        if not candidates:
            print(f"No cached pages found in {settings.RE_HTML_DIR}")
            return
        page_file = candidates[0]

    print(f"\nReading: {page_file.name}  ({page_file.stat().st_size:,} bytes)\n")
    html = page_file.read_text(encoding="utf-8")

    match = re.search(
        r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    if not match:
        print("__NEXT_DATA__ not found.")
        return

    data = json.loads(match.group(1))
    block = get_path(data, RESULTS_PATH)
    if not isinstance(block, dict):
        print("Results block not found at the expected path.")
        return

    rows = block.get("results")
    if not isinstance(rows, list) or not rows:
        print("No listings in the results array.")
        return

    print(f"count    : {block.get('count')}")
    print(f"lastPage : {block.get('lastPage')}")
    print(f"listings : {len(rows)}\n")

    # ---------------------------------------------------------- top level
    first = rows[0]
    print("=" * 72)
    print("TOP-LEVEL FIELDS OF LISTING [0]")
    print("=" * 72)
    for key in sorted(first.keys()):
        value = first[key]
        kind = type(value).__name__
        print(f"  {key:<28} {kind:<8} {preview(value)}")

    # ------------------------------------------------------ nested dicts
    for key in sorted(first.keys()):
        value = first[key]
        if isinstance(value, dict) and value:
            print("\n" + "-" * 72)
            print(f"NESTED: {key}")
            print("-" * 72)
            for sub_key in sorted(value.keys()):
                sub = value[sub_key]
                print(f"  {key}.{sub_key:<24} {type(sub).__name__:<8} {preview(sub)}")
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            print("\n" + "-" * 72)
            print(f"NESTED LIST: {key}  (len {len(value)}, showing [0])")
            print("-" * 72)
            for sub_key in sorted(value[0].keys()):
                sub = value[0][sub_key]
                print(f"  {key}[0].{sub_key:<21} {type(sub).__name__:<8} {preview(sub)}")

    # ------------------------------------------------ key coverage stats
    print("\n" + "=" * 72)
    print(f"KEY COVERAGE ACROSS ALL {len(rows)} LISTINGS ON THIS PAGE")
    print("=" * 72)
    counter: Counter = Counter()
    for row in rows:
        if isinstance(row, dict):
            for key, value in row.items():
                if value not in (None, "", [], {}):
                    counter[key] += 1
    for key, hits in counter.most_common():
        bar = "#" * int(hits / len(rows) * 20)
        print(f"  {key:<28} {hits:>3}/{len(rows)}  {bar}")

    # --------------------------------------------- guess the price field
    print("\n" + "=" * 72)
    print("FIELDS THAT LOOK LIKE PRICE / SIZE / ROOMS")
    print("=" * 72)

    def scan(obj, prefix=""):
        hits = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                full = f"{prefix}.{key}" if prefix else key
                low = key.lower()
                if any(w in low for w in
                       ("price", "cost", "amount", "area", "size", "sqm",
                        "bed", "bath", "room", "floor", "lat", "lng", "lon",
                        "location", "district", "khan", "commune", "province",
                        "date", "created", "updated", "url", "slug", "id")):
                    if not isinstance(value, (dict, list)):
                        hits.append((full, type(value).__name__, preview(value, 45)))
                if isinstance(value, dict):
                    hits.extend(scan(value, full))
                elif isinstance(value, list) and value and isinstance(value[0], dict):
                    hits.extend(scan(value[0], f"{full}[0]"))
        return hits

    for full, kind, val in scan(first):
        print(f"  {full:<40} {kind:<8} {val}")

    # ---------------------------------------------------------- save it
    out = settings.REPORT_DIR / "sample_listing.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(first, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFull listing saved to: {out}\n")


if __name__ == "__main__":
    main()