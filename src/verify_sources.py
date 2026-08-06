#!/usr/bin/env python
"""
verify_sources.py - PP PropertyLens
===================================

recon.py gives a first estimate. Those numbers are usually TOO HIGH, because:

  * the URL patterns also match category, search and pagination pages
  * the counts cover all of Cambodia, all property types, sale AND rent
  * some sitemaps list the same property once per language or currency

This script checks what those URLs really are, and probes each WordPress API
endpoint individually so you know exactly which post type was found.

Run it before writing any adapter.

Usage:
    python src/verify_sources.py                     # all sites with url files
    python src/verify_sources.py --site aps.com.kh
    python src/verify_sources.py --api-only
    python src/verify_sources.py --sample 5          # fetch N pages per site
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
sys.path.insert(0, str(CONFIG_DIR))
import settings  # noqa: E402

import requests  # noqa: E402

REPORT_DIR = settings.REPORT_DIR

WP_ENDPOINTS = [
    "property", "properties", "listing", "listings",
    "estate_property", "houzez_property", "rem_property",
    "product", "posts", "pages", "types", "media",
]

# Words that mark a URL as a browse/search page rather than one property.
NON_LISTING_HINTS = [
    "/page/", "?page=", "/category/", "/tag/", "/search",
    "/author/", "/feed", "/amp", "/wp-content/", "/attachment",
    "/agent", "/agency", "/blog", "/news", "/city/", "/area/",
    "/type/", "/status/", "/feature/", "/label/",
]

PHNOM_PENH_HINTS = ["phnom-penh", "phnompenh", "phnom_penh", "pp-"]
CONDO_HINTS = ["condo", "apartment", "penthouse", "studio"]
SALE_HINTS = ["for-sale", "-sale", "/sale", "buy"]
RENT_HINTS = ["for-rent", "-rent", "/rent", "rental", "lease"]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": settings.USER_AGENT})


def looks_like_browse_page(url: str) -> bool:
    low = url.lower()
    return any(hint in low for hint in NON_LISTING_HINTS)


def has_any(url: str, hints: list[str]) -> bool:
    low = url.lower()
    return any(hint in low for hint in hints)


def path_shape(url: str) -> str:
    """
    Reduce a URL to its structural shape so similar URLs group together.

        /property/luxury-condo-bkk1/   ->  /property/*
        /en/listing/123/               ->  /en/listing/*
    """
    path = urlparse(url).path.strip("/")
    if not path:
        return "/"
    parts = path.split("/")
    shaped = []
    for i, part in enumerate(parts):
        if i < 2 and not re.search(r"\d{3,}", part) and len(part) < 20:
            shaped.append(part)
        else:
            shaped.append("*")
            break
    return "/" + "/".join(shaped)


# ========================================================================
# URL ANALYSIS
# ========================================================================

def analyse_urls(domain: str, urls: list[str], show: int = 8) -> dict:
    """
    Score URLs against the project scope:

        type        = condo / apartment / penthouse
        transaction = sale (not rent)
        location    = Phnom Penh

    URLs often encode only some of these, so both a STRICT count (all three
    visible in the URL) and a LOOSE count (condo, not rent) are reported.
    """
    total = len(urls)
    browse = [u for u in urls if looks_like_browse_page(u)]
    listings = [u for u in urls if not looks_like_browse_page(u)]

    pp = [u for u in listings if has_any(u, PHNOM_PENH_HINTS)]
    condo = [u for u in listings if has_any(u, CONDO_HINTS)]
    sale = [u for u in listings if has_any(u, SALE_HINTS)]
    rent = [u for u in listings if has_any(u, RENT_HINTS)]

    # LOOSE: condo, definitely not rent
    loose = [u for u in listings
             if has_any(u, CONDO_HINTS) and not has_any(u, RENT_HINTS)]

    # STRICT: all three scope filters visible in the URL
    strict = [u for u in loose if has_any(u, PHNOM_PENH_HINTS)]

    # URLs that say nothing about type or location - cannot be judged offline
    unknown = [u for u in listings
               if not has_any(u, CONDO_HINTS) and not has_any(u, PHNOM_PENH_HINTS)]

    print(f"\n{domain}")
    print("=" * 68)
    print(f"  urls in file                 : {total:>7,}")
    print(f"  minus browse/category pages  : {len(listings):>7,}"
          f"   (removed {len(browse):,})")
    print()
    print("  SCOPE: condo + for sale + Phnom Penh")
    print(f"    mentions Phnom Penh        : {len(pp):>7,}")
    print(f"    mentions condo/apartment   : {len(condo):>7,}")
    print(f"    mentions sale              : {len(sale):>7,}")
    print(f"    mentions rent  (excluded)  : {len(rent):>7,}")
    print()
    print(f"  STRICT target (all 3 in url) : {len(strict):>7,}")
    print(f"  LOOSE  target (condo, no rent): {len(loose):>6,}")
    print(f"  undeterminable from url      : {len(unknown):>7,}")

    shapes = Counter(path_shape(u) for u in listings)
    print("\n  url shapes:")
    for shape, count in shapes.most_common(show):
        print(f"    {count:>7,}  {shape}")

    target_urls = strict or loose
    if target_urls:
        print("\n  target samples:")
        for url in target_urls[:4]:
            print(f"    {url}")

        safe = domain.replace(".", "_").replace("-", "_")
        out = REPORT_DIR / f"target_urls_{safe}.txt"
        out.write_text(f"# domain: {domain}\n" + "\n".join(target_urls),
                       encoding="utf-8")
        print(f"\n  target list -> {out.name}  ({len(target_urls):,} urls)")

    if len(unknown) > len(listings) * 0.5:
        print("\n  NOTE: most URLs carry no type or location information, so the")
        print("        real count cannot be judged offline. Either use the site's")
        print("        own filtered search URL, or run --sample 5 to check pages.")

    return {
        "domain": domain,
        "total": total,
        "listings": len(listings),
        "phnom_penh": len(pp),
        "condo": len(condo),
        "sale": len(sale),
        "rent": len(rent),
        "strict": len(strict),
        "loose": len(loose),
        "unknown": len(unknown),
        "shapes": shapes.most_common(show),
        "sample_urls": target_urls[:5],
    }


# ========================================================================
# WORDPRESS API PROBE
# ========================================================================

def probe_wp_api(domain: str) -> list[dict]:
    """
    Probe each endpoint separately and report its exact record count.

    This matters: recon.py falls back to /wp-json/wp/v2/posts, which counts
    blog posts, not properties. A large number there means nothing.
    """
    print(f"\n{domain} - WordPress API")
    print("=" * 68)

    base = f"https://{domain}/wp-json/wp/v2/"
    found = []

    # what post types does the site actually register?
    try:
        response = SESSION.get(f"https://{domain}/wp-json/wp/v2/types", timeout=15)
        if response.status_code == 200 and "json" in response.headers.get("Content-Type", ""):
            types = response.json()
            if isinstance(types, dict):
                print("  registered post types:")
                for key, value in types.items():
                    name = value.get("name") if isinstance(value, dict) else key
                    rest = value.get("rest_base") if isinstance(value, dict) else None
                    print(f"    {key:<24} {str(name):<24} rest_base={rest}")
                    if rest and rest not in WP_ENDPOINTS:
                        WP_ENDPOINTS.append(rest)
                print()
    except Exception:
        pass

    for endpoint in WP_ENDPOINTS:
        url = f"{base}{endpoint}?per_page=1"
        try:
            response = SESSION.get(url, timeout=15)
        except Exception:
            continue
        time.sleep(0.3)
        if response.status_code != 200:
            continue
        if "application/json" not in response.headers.get("Content-Type", ""):
            continue

        total = response.headers.get("X-WP-Total")
        pages = response.headers.get("X-WP-TotalPages")
        try:
            data = response.json()
        except Exception:
            continue

        marker = "  <- property data" if endpoint not in {
            "posts", "pages", "media", "types"} else ""
        print(f"  {endpoint:<20} {str(total):>8} records, "
              f"{str(pages):>5} pages{marker}")

        record = data[0] if isinstance(data, list) and data else None
        found.append({
            "endpoint": endpoint,
            "url": f"{base}{endpoint}",
            "total": int(total) if total and total.isdigit() else None,
            "sample_keys": sorted(record.keys())[:25] if isinstance(record, dict) else [],
        })

    if not found:
        print("  no JSON endpoints responded")
        return found

    property_like = [f for f in found
                     if f["endpoint"] not in {"posts", "pages", "media", "types"}]
    best = max(property_like or found, key=lambda f: f["total"] or 0)

    print(f"\n  best candidate: {best['endpoint']} ({best['total']} records)")
    if best["sample_keys"]:
        print("  fields on one record:")
        for key in best["sample_keys"]:
            print(f"    {key}")
        print("\n  Pull everything with:")
        print(f"    {best['url']}?per_page=100&page=1")

    return found


# ========================================================================
# PAGE SAMPLING
# ========================================================================

def sample_pages(domain: str, urls: list[str], count: int) -> None:
    """Fetch a few real pages and check what is actually on them."""
    print(f"\n{domain} - sampling {count} pages")
    print("=" * 68)

    step = max(1, len(urls) // count)
    picked = urls[::step][:count]

    stats = Counter()
    for url in picked:
        try:
            response = SESSION.get(url, timeout=20)
        except Exception as exc:
            print(f"  FAIL {type(exc).__name__}  {url[:60]}")
            continue
        time.sleep(1.0)
        if response.status_code != 200:
            print(f"  HTTP {response.status_code}  {url[:60]}")
            continue

        html = response.text
        text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        low = text.lower()

        price = re.search(r"\$\s?\d{1,3}(?:,\d{3})+", text)
        area = re.search(r"(\d+(?:\.\d+)?)\s*(?:m²|m2|sqm|sq\.?\s?m)", text, re.I)
        beds = re.search(r"(\d+)\s*(?:bed|bedroom)", low)
        is_pp = "phnom penh" in low
        is_condo = any(word in low for word in ("condo", "apartment", "penthouse"))
        is_rent = bool(re.search(r"per month|/month|for rent", low))

        stats["fetched"] += 1
        stats["price"] += bool(price)
        stats["area"] += bool(area)
        stats["beds"] += bool(beds)
        stats["phnom_penh"] += is_pp
        stats["condo"] += is_condo
        stats["rent"] += is_rent

        print(f"  {'$' if price else '-'}{'m' if area else '-'}"
              f"{'b' if beds else '-'}{'P' if is_pp else '-'}"
              f"{'C' if is_condo else '-'}{'R' if is_rent else '-'}  "
              f"{(price.group() if price else ''):>10}  "
              f"{(area.group() if area else ''):>8}  {url[:52]}")

    n = stats["fetched"] or 1
    print(f"\n  legend: $ price  m area  b bedrooms  P Phnom Penh  C condo  R rent")
    print(f"\n  fill rates over {n} pages:")
    for key in ("price", "area", "beds", "phnom_penh", "condo", "rent"):
        print(f"    {key:<12} {stats[key]:>3}/{n}  {stats[key] / n:>5.0%}")

    if stats["price"] / n < 0.6 or stats["area"] / n < 0.6:
        print("\n  WARNING: low price or area fill rate - this source may not be")
        print("           worth building an adapter for.")


# ========================================================================
# MAIN
# ========================================================================

def load_url_files(only: str | None) -> dict[str, list[str]]:
    files = sorted(REPORT_DIR.glob("urls_*.txt"))
    out: dict[str, list[str]] = {}
    for path in files:
        lines = [line.strip() for line in
                 path.read_text(encoding="utf-8").splitlines() if line.strip()]

        # recon.py writes "# domain: example.com" as the first line, because
        # the filename cannot distinguish a dot from a hyphen.
        domain = None
        if lines and lines[0].startswith("# domain:"):
            domain = lines[0].split(":", 1)[1].strip()
            lines = lines[1:]
        if not domain:
            stem = path.stem.replace("urls_", "")
            parts = stem.rsplit("_", 1)
            domain = (parts[0].replace("_", "-") + "." + parts[1]
                      if len(parts) == 2 else stem.replace("_", "."))

        if only and only not in domain:
            continue
        out[domain] = [u for u in lines if u.startswith("http")]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Verify recon results before building adapters")
    ap.add_argument("--site", help="limit to one domain")
    ap.add_argument("--api-only", action="store_true", help="only probe WordPress APIs")
    ap.add_argument("--sample", type=int, default=0,
                    help="fetch N real pages per site to check fill rates")
    args = ap.parse_args()

    url_files = load_url_files(args.site)
    if not url_files and not args.site:
        print(f"No urls_*.txt files in {REPORT_DIR}. Run recon.py first.")
        return

    summaries = []

    if not args.api_only:
        for domain, urls in url_files.items():
            summaries.append(analyse_urls(domain, urls))
            if args.sample:
                sample_pages(domain, urls, args.sample)

    api_domains = [args.site] if args.site else list(url_files)
    for domain in api_domains:
        probe_wp_api(domain)

    if summaries:
        print("\n" + "=" * 68)
        print(f"{'SITE':<24}{'URLS':>8}{'LISTINGS':>10}{'STRICT':>8}{'LOOSE':>8}{'?':>8}")
        print("=" * 68)
        for s in sorted(summaries, key=lambda x: -(x["strict"] or x["loose"])):
            print(f"{s['domain']:<24}{s['total']:>8,}{s['listings']:>10,}"
                  f"{s['strict']:>8,}{s['loose']:>8,}{s['unknown']:>8,}")
        print("=" * 68)
        print("\nSCOPE: condo + for sale + Phnom Penh")
        print("  STRICT = all three visible in the URL")
        print("  LOOSE  = condo and not rent (location unverified)")
        print("  ?      = URL says nothing about type or location")
        print("\nIf ? is large, prefer the site's own filtered search URL,")
        print("e.g. /property-type/condo/?status=for-sale&city=phnom-penh\n")

        out = REPORT_DIR / "source_verification.json"
        out.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
        print(f"Saved: {out}\n")


if __name__ == "__main__":
    main()