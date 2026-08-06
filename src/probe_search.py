

#!/usr/bin/env python
"""
probe_search.py - PP PropertyLens
=================================

You now have a filtered search URL per site, each already scoped to
    condo + for sale + Phnom Penh.

This script answers, for each one:

    1. How many listings appear on page 1?
    2. Does the site state a total result count?
    3. Is the page server-rendered, or does it need a browser?
    4. Does pagination work, and what shape is it?
    5. Roughly how many pages / listings can be reached?

That is everything needed to decide which sites are worth an adapter.

Nothing is scraped beyond 2-3 pages per site.

Usage:
    python src/probe_search.py                 # probe every configured site
    python src/probe_search.py --site aps
    python src/probe_search.py --browser       # force Playwright for all
    python src/probe_search.py --verbose       # show sample listing urls

Config:
    config/search_urls.json    created on first run, edit freely
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlencode, parse_qsl, urlunparse

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
sys.path.insert(0, str(CONFIG_DIR))
import settings  # noqa: E402

import requests  # noqa: E402


# ========================================================================
# DEFAULT SEARCH URLS - already filtered to condo / sale / Phnom Penh
# ========================================================================

DEFAULT_SEARCH_URLS = {
    "ips-cambodia.com": "https://ips-cambodia.com/advanced-search/?rent_sale=sale&category_id=21&region=Phnom+Penh",
    "aps.com.kh": "https://aps.com.kh/apartment-condo-for-sale/",
    "harbor-property.com": "https://www.harbor-property.com/house/buy/area=0%2F0&btypes=1&nearByTagId=0&price=0%2F0&regions=1%2C0%2C0",
    "camrealtyservice.com": "https://camrealtyservice.com/property-search/?search_for=house&status%5B%5D=for-sale&location%5B%5D=phnom-penh&type%5B%5D=resale-condominium",
    "estatecambodia.com": "https://estatecambodia.com/search?available=0&status=sale&categories%5B%5D=Condo&q=Phnom+Penh&list_type=lists&order=Desc",
    "pointerasia.com": "https://pointerasia.com/buy/phnom-penh/condo",
    "khpropertyhub.com": "https://khpropertyhub.com/km/property-for-sale/condo/phnom-penh?subPropertyTypeIds=245",
}

# A link on a search page is treated as a listing if it matches one of these.
LISTING_PATTERNS = [
    r"/property/[^/]+/?$",
    r"/properties/[^/]+/?$",
    r"/listing/[^/]+/?$",
    r"/listings/[^/]+/?$",
    r"/p/[^/]+/?$",
    r"/house/detail",
    r"/detail/",
    r"-adid-\d+",
    r"/\d{4,}/?$",
    r"-\d{4,}/?$",
    r"/buy/[^/]+/[^/]+/[^/]+",
    r"/condo[^/]*/[^/]+/?$",
    r"/apartment[^/]*/[^/]+/?$",
    # confirmed live shapes
    r"/property/condo-phnom-penh-[a-z-]+-\d+/?$",   # khpropertyhub, pointerasia
    r"/property/[a-z0-9-]*condo[a-z0-9-]*-s?\d{4,}/?$",  # camrealtyservice
]

# A real listing URL nearly always ends with a numeric id. Requiring this
# removes taxonomy pages such as /property/sub_type_warehousing/.
LISTING_MUST_END_IN_ID = re.compile(r"[-/](?:s)?\d{3,}/?$")

# Words used to exclude browse pages picked up as listings.
NOT_LISTING = [
    # taxonomy and filter pages seen live on aps.com.kh and estatecambodia.com
    "record_type_", "sub_type_", "property_type_", "/properties/all",
    "/properties/villa", "/properties/house", "/properties/land",
    "/properties/condo", "/properties/hotel", "/properties/office",
    # out of scope by project definition
    "/boreys/", "/borey/", "/land-for", "/villa-for", "/house-for",
    "/property-for-sale/", "/property-for-rent/", "/for-sale/condo",
    "/page/", "?page=", "/category/", "/tag/", "/search", "/advanced-search",
    "/agent", "/agency", "/blog", "/news", "/about", "/contact", "/login",
    "/register", "/wp-content", "/wp-json", "/feed", "/privacy", "/terms",
    "facebook.com", "twitter.com", "instagram.com", "youtube.com", "t.me",
    "wa.me", "linkedin.com", "tiktok.com", "mailto:", "tel:",
]

# "1,234 properties found", "Showing 1-20 of 415 results", Khmer variants
# A result count must sit next to a word like "properties" or "results".
# The bare "of N" pattern was removed: it matched copyright years such as
# "(c) 2026" and reported 2026 listings.
COUNT_PATTERNS = [
    r"([\d,]+)\s*(?:properties|property|listings|listing|results|items|ads)\b",
    r"(?:found|showing|total of)\s*([\d,]+)",
    r"of\s*([\d,]+)\s*(?:properties|listings|results|items)",
    r"([\d,]+)\s*(?:លទ្ធផល|អចលនទ្រព្យ)",
]

# Values that are almost certainly years, not counts.
YEAR_RANGE = range(1990, 2100)

TIMEOUT = 25
DELAY = 2.0

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": settings.USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9,km;q=0.8",
})


# ========================================================================
# RESULT
# ========================================================================

@dataclass
class Probe:
    domain: str
    url: str
    ok: bool = False
    rendering: str = "unknown"
    needs_browser: bool = False
    page1_listings: int = 0
    stated_total: int | None = None
    pagination: str | None = None
    page2_new: int | None = None
    sample: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def estimated_total(self) -> int | None:
        if self.stated_total:
            return self.stated_total
        if self.pagination and self.page1_listings:
            return None          # unknown page count
        return self.page1_listings or None

    @property
    def effort(self) -> str:
        if not self.ok:
            return "-"
        if self.needs_browser and not self.pagination:
            return "HARD (browser + scroll)"
        if self.needs_browser:
            return "MEDIUM (browser)"
        if self.pagination:
            return "EASY (http + pages)"
        return "EASY (single page)"

    @property
    def verdict(self) -> str:
        if not self.ok:
            return "SKIP - could not load"
        if self.page1_listings == 0:
            return "INVESTIGATE - no listings parsed"
        total = self.stated_total or 0
        if total >= 300 or (self.pagination and self.page1_listings >= 15):
            return "SCRAPE"
        if total >= 100 or self.page1_listings >= 12:
            return "MAYBE"
        return "SKIP - too few"


# ========================================================================
# HELPERS
# ========================================================================

def is_listing_link(url: str, domain: str) -> bool:
    low = url.lower()
    if any(bad in low for bad in NOT_LISTING):
        return False
    host = urlparse(url).netloc.replace("www.", "")
    if host and domain.replace("www.", "") not in host:
        return False
    path = urlparse(url).path
    if len(path.strip("/")) < 4:
        return False
    if not any(re.search(pattern, low) for pattern in LISTING_PATTERNS):
        return False
    # keep slug-only listing URLs, but drop taxonomy pages that merely sit
    # under /property/ without an id
    if re.search(r"/(?:property|properties|listing|listings)/[^/]+/?$", low):
        return bool(LISTING_MUST_END_IN_ID.search(low)) or low.count("-") >= 3
    return True


def extract_links(html: str, base: str, domain: str) -> list[str]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
    seen: dict[str, None] = {}
    for href in hrefs:
        absolute = urljoin(base, href.strip())
        if is_listing_link(absolute, domain):
            seen.setdefault(absolute.split("#")[0], None)
    return list(seen)


def find_stated_total(html: str) -> int | None:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    best = None
    for pattern in COUNT_PATTERNS:
        for match in re.finditer(pattern, text, re.I):
            try:
                value = int(match.group(1).replace(",", ""))
            except (ValueError, IndexError):
                continue
            if value in YEAR_RANGE and match.group(0).strip() == match.group(1):
                continue                      # bare year, e.g. a copyright line
            if 5 <= value <= 200_000:
                best = value if best is None else max(best, value)
    return best


def body_word_count(html: str) -> int:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return len(text.split())


def with_page(url: str, page: int, style: str) -> str:
    parts = urlparse(url)
    if style == "query_page":
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["page"] = str(page)
        return urlunparse(parts._replace(query=urlencode(query)))
    if style == "query_paged":
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["paged"] = str(page)
        return urlunparse(parts._replace(query=urlencode(query)))
    if style == "path_page":
        path = parts.path.rstrip("/")
        return urlunparse(parts._replace(path=f"{path}/page/{page}"))
    return url


PAGINATION_STYLES = ["query_page", "path_page", "query_paged"]


# ========================================================================
# FETCHING
# ========================================================================

_BROWSER: dict = {}


def fetch_http(url: str) -> str | None:
    try:
        response = SESSION.get(url, timeout=TIMEOUT)
        if response.status_code == 200:
            return response.text
        return None
    except Exception:
        return None


def fetch_browser(url: str) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    if "page" not in _BROWSER:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(user_agent=settings.USER_AGENT,
                                      viewport={"width": 1400, "height": 1000})
        _BROWSER.update({"pw": pw, "browser": browser, "page": context.new_page()})

    page = _BROWSER["page"]
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT * 1000)
        page.wait_for_timeout(3500)
        page.mouse.wheel(0, 6000)
        page.wait_for_timeout(1500)
        return page.content()
    except Exception:
        return None


def close_browser() -> None:
    if "browser" in _BROWSER:
        try:
            _BROWSER["browser"].close()
            _BROWSER["pw"].stop()
        except Exception:
            pass
        _BROWSER.clear()


# ========================================================================
# PROBE ONE SITE
# ========================================================================

def probe(domain: str, url: str, force_browser: bool, verbose: bool) -> Probe:
    result = Probe(domain=domain, url=url)
    print(f"\n{domain}")
    print("-" * 68)

    # ---- page 1 --------------------------------------------------------
    html = None if force_browser else fetch_http(url)
    via = "http"

    if html:
        links = extract_links(html, url, domain)
        words = body_word_count(html)
        if not links or words < 200:
            print("  http gave little content, retrying with a browser ...")
            browser_html = fetch_browser(url)
            if browser_html and len(extract_links(browser_html, url, domain)) > len(links):
                html, via = browser_html, "browser"
                result.needs_browser = True
    else:
        html = fetch_browser(url)
        via = "browser"
        result.needs_browser = True

    if html is None:
        result.notes.append("could not load page 1")
        print("  FAILED to load")
        return result

    result.ok = True
    links = extract_links(html, url, domain)
    result.page1_listings = len(links)
    result.sample = links[:5]
    result.stated_total = find_stated_total(html)
    words = body_word_count(html)
    result.rendering = ("server-rendered" if via == "http" and links
                        else "js-app" if via == "browser" else "partial")

    print(f"  loaded via     : {via}  ({len(html):,} bytes, {words:,} words)")
    print(f"  listings found : {result.page1_listings}")
    print(f"  stated total   : {result.stated_total if result.stated_total else 'not stated'}")

    if verbose and result.sample:
        print("  samples:")
        for link in result.sample:
            print(f"    {link}")

    if result.page1_listings == 0:
        result.notes.append("no listing links matched - patterns may need adjusting")
        print("  NOTE: no listing links matched. Open the page and check the URL")
        print("        shape of one listing, then add it to LISTING_PATTERNS.")
        return result

    # ---- pagination ----------------------------------------------------
    print("  pagination     : testing ...", end=" ", flush=True)
    ids1 = set(links)

    for style in PAGINATION_STYLES:
        page2_url = with_page(url, 2, style)
        if page2_url == url:
            continue
        time.sleep(DELAY)
        page2_html = (fetch_browser(page2_url) if result.needs_browser
                      else fetch_http(page2_url))
        if not page2_html:
            continue
        ids2 = set(extract_links(page2_html, page2_url, domain))
        new = ids2 - ids1
        if len(new) >= max(3, len(ids1) * 0.3):
            result.pagination = style
            result.page2_new = len(new)
            print(f"WORKS ({style}, {len(new)} new on page 2)")
            break
    else:
        print("none detected")
        result.notes.append(
            "pagination not detected - the site may use infinite scroll "
            "(like khmer24) or a different parameter"
        )

    print(f"  -> {result.verdict}   ({result.effort})")
    return result


# ========================================================================
# MAIN
# ========================================================================

def load_urls() -> dict[str, str]:
    path = CONFIG_DIR / "search_urls.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(DEFAULT_SEARCH_URLS, indent=2), encoding="utf-8")
        print(f"Created {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return DEFAULT_SEARCH_URLS


def main() -> None:
    ap = argparse.ArgumentParser(description="Probe filtered search URLs")
    ap.add_argument("--site", help="substring match on domain")
    ap.add_argument("--browser", action="store_true", help="force Playwright")
    ap.add_argument("--verbose", action="store_true", help="show sample urls")
    args = ap.parse_args()

    urls = load_urls()
    targets = {d: u for d, u in urls.items()
               if not args.site or args.site.lower() in d.lower()}

    print(f"\nProbing {len(targets)} filtered search page(s)")
    print("scope: condo + for sale + Phnom Penh")

    results = []
    try:
        for domain, url in targets.items():
            try:
                results.append(probe(domain, url, args.browser, args.verbose))
            except Exception as exc:
                print(f"  ERROR {type(exc).__name__}: {exc}")
                failed = Probe(domain=domain, url=url)
                failed.notes.append(str(exc))
                results.append(failed)
            time.sleep(DELAY)
    finally:
        close_browser()

    print("\n" + "=" * 78)
    print(f"{'SITE':<24}{'PG1':>5}{'TOTAL':>8}  {'PAGINATION':<14}{'EFFORT':<24}VERDICT")
    print("=" * 78)
    for r in sorted(results, key=lambda x: -(x.stated_total or x.page1_listings)):
        total = str(r.stated_total) if r.stated_total else "-"
        print(f"{r.domain:<24}{r.page1_listings:>5}{total:>8}  "
              f"{str(r.pagination or '-'):<14}{r.effort:<24}{r.verdict}")
    print("=" * 78)

    out = settings.REPORT_DIR
    out.mkdir(parents=True, exist_ok=True)
    payload = [{
        "domain": r.domain, "url": r.url, "ok": r.ok,
        "page1_listings": r.page1_listings, "stated_total": r.stated_total,
        "pagination": r.pagination, "needs_browser": r.needs_browser,
        "rendering": r.rendering, "effort": r.effort, "verdict": r.verdict,
        "sample": r.sample, "notes": r.notes,
    } for r in results]
    (out / "search_probe.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {out / 'search_probe.json'}")
    print("\nPick the top 2 marked SCRAPE. Build adapters for those only.\n")


if __name__ == "__main__":
    main()