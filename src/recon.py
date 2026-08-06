#!/usr/bin/env python
"""
recon.py - PP PropertyLens
==========================

Answers the Step 0 questions for every candidate property website, so you can
decide which ones are worth scraping BEFORE writing any adapter code.

For each site it reports:

    1. Is it reachable?
    2. What does robots.txt allow, and does it declare a sitemap?
    3. Does a sitemap exist, and how many property URLs are in it?
    4. Is there a WordPress REST API? (turns a day of work into an hour)
    5. Is the page server-rendered, a JS app with embedded JSON, or neither?
    6. Roughly how many listings can we reach?

Nothing is scraped here. Only robots.txt, sitemaps, one API probe and one
page per site are downloaded - a handful of requests in total.

Usage:
    python src/recon.py                    # check the default site list
    python src/recon.py --site ips-cambodia.com
    python src/recon.py --verbose          # show every sitemap found

Output:
    outputs/reports/site_recon.md          # the comparison table
    outputs/reports/urls_<site>.txt        # property URLs found per site
"""

from __future__ import annotations

import argparse
import gzip
import io
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
sys.path.insert(0, str(CONFIG_DIR))
import settings  # noqa: E402

import requests  # noqa: E402


# ========================================================================
# SITES TO CHECK
# ========================================================================

SITES = [
    "ips-cambodia.com",
    "aps.com.kh",
    "harbor-property.com",
    "camrealtyservice.com",
    "estatecambodia.com",
    "pointerasia.com",
    "khpropertyhub.com",
]

# Sitemap locations to try when robots.txt does not declare one.
SITEMAP_CANDIDATES = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/wp-sitemap.xml",
    "/sitemap/sitemap-index.xml",
    "/sitemap1.xml",
    "/property-sitemap.xml",
]

# WordPress REST endpoints worth probing. Property plugins register custom
# post types, so several names are tried.
WP_API_CANDIDATES = [
    "/wp-json/wp/v2/property?per_page=1",
    "/wp-json/wp/v2/properties?per_page=1",
    "/wp-json/wp/v2/listing?per_page=1",
    "/wp-json/wp/v2/listings?per_page=1",
    "/wp-json/wp/v2/estate_property?per_page=1",
    "/wp-json/wp/v2/posts?per_page=1",
]

# A URL is treated as a property page if it matches any of these.
PROPERTY_URL_PATTERNS = [
    r"/property/", r"/properties/", r"/listing/", r"/listings/",
    r"/for-sale/", r"/rent/", r"/condo", r"/apartment",
    r"/real-estate/", r"/p/", r"-adid-\d+", r"/id-\d+",
]

# Signals that the page is a JavaScript app with data embedded in the HTML.
JSON_MARKERS = {
    "__NEXT_DATA__": "Next.js JSON",
    "window.__NUXT__": "Nuxt JSON",
    "__NUXT_DATA__": "Nuxt JSON",
    "application/ld+json": "JSON-LD",
    "window.__INITIAL_STATE__": "Vue/Redux state",
}

TIMEOUT = 15
DELAY = 1.5


# ========================================================================
# RESULT CONTAINER
# ========================================================================

@dataclass
class SiteReport:
    domain: str
    reachable: bool = False
    scheme: str = "https"
    robots_found: bool = False
    robots_disallows_all: bool = False
    robots_sitemaps: list[str] = field(default_factory=list)
    sitemap_url: str | None = None
    sitemap_urls_total: int = 0
    property_urls: list[str] = field(default_factory=list)
    wp_api: str | None = None
    wp_api_total: int | None = None
    rendering: str = "unknown"
    json_marker: str | None = None
    platform: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def property_count(self) -> int:
        return len(self.property_urls)

    @property
    def effort(self) -> str:
        if self.wp_api:
            return "EASY (REST API)"
        if self.property_count >= 100:
            return "EASY (sitemap)"
        if self.rendering == "server-rendered":
            return "MEDIUM (parse HTML)"
        if self.json_marker:
            return "MEDIUM (embedded JSON)"
        if self.rendering == "js-app":
            return "HARD (browser needed)"
        return "UNKNOWN"

    @property
    def verdict(self) -> str:
        reachable_count = max(self.property_count, self.wp_api_total or 0)
        if not self.reachable:
            return "SKIP - unreachable"
        if self.robots_disallows_all:
            return "SKIP - robots.txt disallows"
        if self.wp_api and (self.wp_api_total or 0) >= 100:
            return "SCRAPE - API available"
        if reachable_count >= 150:
            return "SCRAPE"
        if reachable_count >= 50:
            return "MAYBE - small"
        if reachable_count > 0:
            return "SKIP - too few"
        return "INVESTIGATE - count unknown"


# ========================================================================
# HTTP
# ========================================================================

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": settings.USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
})


def get(url: str, allow_redirects: bool = True) -> requests.Response | None:
    try:
        return SESSION.get(url, timeout=TIMEOUT, allow_redirects=allow_redirects)
    except Exception:
        return None


def get_text(url: str) -> str | None:
    """Fetch text, transparently decompressing .gz sitemaps."""
    response = get(url)
    if response is None or response.status_code != 200:
        return None
    content = response.content
    if url.endswith(".gz") or content[:2] == b"\x1f\x8b":
        try:
            content = gzip.decompress(content)
        except Exception:
            return None
    try:
        return content.decode("utf-8", errors="replace")
    except Exception:
        return None


# ========================================================================
# CHECKS
# ========================================================================

def check_reachable(report: SiteReport) -> None:
    for scheme in ("https", "http"):
        response = get(f"{scheme}://{report.domain}")
        if response is not None and response.status_code < 500:
            report.reachable = True
            report.scheme = scheme
            final = urlparse(response.url).netloc
            if final and final != report.domain:
                report.notes.append(f"redirects to {final}")
            return
    report.notes.append("no response on http or https")


def base_url(report: SiteReport) -> str:
    return f"{report.scheme}://{report.domain}"


def check_robots(report: SiteReport) -> None:
    """
    Read robots.txt. Two things matter: whether crawling is disallowed, and
    whether it points at a sitemap (the fastest route to every listing URL).
    """
    text = get_text(urljoin(base_url(report), "/robots.txt"))
    if text is None:
        report.notes.append("no robots.txt (treated as allowed, per RFC 9309)")
        return

    report.robots_found = True

    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("sitemap:"):
            url = line.split(":", 1)[1].strip()
            if url:
                report.robots_sitemaps.append(url)

    # look only at the wildcard user-agent block
    in_star = False
    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("user-agent:"):
            in_star = stripped.split(":", 1)[1].strip() == "*"
        elif in_star and stripped.startswith("disallow:"):
            value = stripped.split(":", 1)[1].strip()
            if value == "/":
                report.robots_disallows_all = True


def parse_sitemap(text: str) -> tuple[list[str], list[str]]:
    """Return (child_sitemaps, page_urls) from one sitemap document."""
    children: list[str] = []
    pages: list[str] = []
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError:
        # some sites serve HTML sitemaps; fall back to link extraction
        pages = re.findall(r'href=["\'](https?://[^"\']+)["\']', text)
        return [], pages

    def tag_of(element) -> str:
        return element.tag.split("}")[-1].lower()

    for child in root:
        name = tag_of(child)
        loc = None
        for sub in child:
            if tag_of(sub) == "loc" and sub.text:
                loc = sub.text.strip()
                break
        if not loc:
            continue
        if name == "sitemap":
            children.append(loc)
        elif name == "url":
            pages.append(loc)

    # Some "sitemaps" are really HTML link pages that happen to be well-formed
    # XML. If no <sitemap>/<url> entries were found, fall back to link scraping.
    if not children and not pages:
        pages = re.findall(r'href=["\'](https?://[^"\']+)["\']', text)

    return children, pages


def is_property_url(url: str) -> bool:
    low = url.lower()
    return any(re.search(pattern, low) for pattern in PROPERTY_URL_PATTERNS)


def check_sitemap(report: SiteReport, verbose: bool = False,
                  max_children: int = 25) -> None:
    """
    Find a sitemap and count the property URLs inside it.

    A sitemap index points at child sitemaps, so this follows one level down.
    """
    candidates = list(report.robots_sitemaps)
    candidates += [urljoin(base_url(report), path) for path in SITEMAP_CANDIDATES]

    root_text = None
    for url in candidates:
        text = get_text(url)
        time.sleep(0.4)
        if text and ("<urlset" in text or "<sitemapindex" in text or "<url>" in text):
            report.sitemap_url = url
            root_text = text
            break

    if root_text is None:
        report.notes.append("no sitemap found")
        return

    children, pages = parse_sitemap(root_text)

    if children:
        if verbose:
            print(f"      sitemap index with {len(children)} children")
        # prioritise children whose name suggests properties
        def score(url: str) -> int:
            low = url.lower()
            return -sum(word in low for word in
                        ("propert", "listing", "estate", "condo", "sale", "post"))
        children.sort(key=score)

        for child in children[:max_children]:
            text = get_text(child)
            time.sleep(0.3)
            if not text:
                continue
            _, child_pages = parse_sitemap(text)
            pages.extend(child_pages)
            if verbose:
                hits = sum(1 for u in child_pages if is_property_url(u))
                print(f"      {child.split('/')[-1]:<40} "
                      f"{len(child_pages):>5} urls, {hits:>5} property")

    report.sitemap_urls_total = len(pages)
    report.property_urls = sorted({u for u in pages if is_property_url(u)})

    if report.sitemap_urls_total and not report.property_urls:
        report.notes.append(
            f"sitemap has {report.sitemap_urls_total} urls but none matched "
            "the property patterns - inspect urls_<site>.txt"
        )
        report.property_urls = sorted(set(pages))[:2000]


def check_wp_api(report: SiteReport) -> None:
    """
    WordPress sites expose a REST API. If a property post type is registered,
    every listing can be pulled as JSON - no HTML parsing at all.

    The X-WP-Total header gives the exact record count.
    """
    for path in WP_API_CANDIDATES:
        url = urljoin(base_url(report), path)
        response = get(url)
        time.sleep(0.3)
        if response is None or response.status_code != 200:
            continue
        if "application/json" not in response.headers.get("Content-Type", ""):
            continue
        total = response.headers.get("X-WP-Total")
        try:
            count = int(total) if total is not None else None
        except ValueError:
            count = None
        # ignore the generic /posts endpoint unless nothing else worked
        if path.endswith("posts?per_page=1") and report.wp_api:
            continue
        report.wp_api = url
        report.wp_api_total = count
        if not path.endswith("posts?per_page=1"):
            return


def check_rendering(report: SiteReport) -> None:
    """
    Decide how the page delivers its data:
      server-rendered  -> requests + BeautifulSoup is enough
      js-app + JSON    -> extract the embedded JSON blob
      js-app           -> Playwright required
    """
    url = report.property_urls[0] if report.property_urls else base_url(report)
    response = get(url)
    if response is None or response.status_code != 200:
        report.notes.append("could not fetch a page to test rendering")
        return

    html = response.text
    low = html.lower()

    if "wp-content" in low or "wp-json" in low:
        report.platform = "WordPress"
    elif "__next_data__" in low:
        report.platform = "Next.js"
    elif "__nuxt__" in low or "nuxt" in low:
        report.platform = "Nuxt/Vue"
    elif "shopify" in low:
        report.platform = "Shopify"

    for marker, label in JSON_MARKERS.items():
        if marker.lower() in low:
            report.json_marker = label
            break

    # Does the served HTML already contain prices and areas?
    has_price = bool(re.search(r"\$\s?\d{2,3}[,.]\d{3}", html))
    has_area = bool(re.search(r"\d+\s?(?:m²|m2|sqm|sq\.?m)", html, re.I))
    body_text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    body_text = re.sub(r"<[^>]+>", " ", body_text)
    text_len = len(body_text.split())

    if has_price and has_area and text_len > 200:
        report.rendering = "server-rendered"
    elif report.json_marker:
        report.rendering = "js-app (JSON embedded)"
    elif text_len < 150:
        report.rendering = "js-app"
    else:
        report.rendering = "partial"


# ========================================================================
# RUN
# ========================================================================

def run_site(domain: str, verbose: bool) -> SiteReport:
    report = SiteReport(domain=domain)
    print(f"\n{domain}")
    print("-" * 60)

    print("  reachable      ...", end=" ", flush=True)
    check_reachable(report)
    print("yes" if report.reachable else "NO")
    if not report.reachable:
        return report

    print("  robots.txt     ...", end=" ", flush=True)
    check_robots(report)
    if report.robots_disallows_all:
        print("DISALLOWS ALL")
    elif report.robots_sitemaps:
        print(f"ok, declares {len(report.robots_sitemaps)} sitemap(s)")
    else:
        print("ok" if report.robots_found else "none")

    print("  sitemap        ...", end=" ", flush=True)
    check_sitemap(report, verbose=verbose)
    if report.sitemap_url:
        print(f"{report.property_count} property urls "
              f"(of {report.sitemap_urls_total} total)")
    else:
        print("not found")

    print("  wordpress api  ...", end=" ", flush=True)
    check_wp_api(report)
    if report.wp_api:
        total = report.wp_api_total
        print(f"YES - {total if total is not None else '?'} records")
    else:
        print("no")

    print("  rendering      ...", end=" ", flush=True)
    check_rendering(report)
    print(f"{report.rendering}"
          + (f" [{report.json_marker}]" if report.json_marker else ""))

    print(f"  -> {report.verdict}   ({report.effort})")
    return report


def write_report(reports: list[SiteReport]) -> Path:
    out_dir = settings.REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Site Recon - candidate property websites",
        "",
        "Automated Step 0 check. No listings were scraped; only robots.txt,",
        "sitemaps, one API probe and one page were fetched per site.",
        "",
        "| Site | Property URLs | WP API | Rendering | Platform | Effort | Verdict |",
        "|---|---:|---|---|---|---|---|",
    ]
    for r in sorted(reports, key=lambda x: -max(x.property_count, x.wp_api_total or 0)):
        api = f"{r.wp_api_total}" if r.wp_api else "-"
        lines.append(
            f"| {r.domain} | {r.property_count or '-'} | {api} | "
            f"{r.rendering} | {r.platform or '-'} | {r.effort} | {r.verdict} |"
        )

    lines += ["", "## Details", ""]
    for r in reports:
        lines.append(f"### {r.domain}")
        lines.append("")
        lines.append(f"- reachable: {r.reachable} ({r.scheme})")
        lines.append(f"- robots.txt: {'found' if r.robots_found else 'none'}"
                     f"{' - DISALLOWS ALL' if r.robots_disallows_all else ''}")
        if r.sitemap_url:
            lines.append(f"- sitemap: {r.sitemap_url}")
            lines.append(f"- urls in sitemap: {r.sitemap_urls_total}")
            lines.append(f"- property urls: {r.property_count}")
        if r.wp_api:
            lines.append(f"- wordpress api: {r.wp_api} ({r.wp_api_total} records)")
        lines.append(f"- rendering: {r.rendering}")
        if r.json_marker:
            lines.append(f"- embedded json: {r.json_marker}")
        for note in r.notes:
            lines.append(f"- note: {note}")
        if r.property_urls[:3]:
            lines.append("- sample urls:")
            for url in r.property_urls[:3]:
                lines.append(f"    - {url}")
        lines.append("")

    path = out_dir / "site_recon.md"
    path.write_text("\n".join(lines), encoding="utf-8")

    for r in reports:
        if r.property_urls:
            safe = r.domain.replace(".", "_")
            # First line records the true domain: dots and hyphens both become
            # underscores in the filename, so it cannot be reconstructed.
            (out_dir / f"urls_{safe}.txt").write_text(
                f"# domain: {r.domain}\n" + "\n".join(r.property_urls),
                encoding="utf-8",
            )
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description="Check candidate property sites")
    ap.add_argument("--site", action="append",
                    help="check one site (repeatable); default checks all")
    ap.add_argument("--verbose", action="store_true",
                    help="show every child sitemap examined")
    args = ap.parse_args()

    targets = args.site or SITES
    print(f"\nChecking {len(targets)} site(s)")

    reports = []
    for domain in targets:
        domain = domain.replace("https://", "").replace("http://", "").strip("/")
        try:
            reports.append(run_site(domain, args.verbose))
        except Exception as exc:
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            failed = SiteReport(domain=domain)
            failed.notes.append(f"crashed: {exc}")
            reports.append(failed)
        time.sleep(DELAY)

    path = write_report(reports)

    print("\n" + "=" * 72)
    print(f"{'SITE':<26}{'PROPS':>7}{'API':>7}  {'EFFORT':<20}VERDICT")
    print("=" * 72)
    for r in sorted(reports, key=lambda x: -max(x.property_count, x.wp_api_total or 0)):
        api = str(r.wp_api_total) if r.wp_api else "-"
        print(f"{r.domain:<26}{r.property_count or '-':>7}{api:>7}  "
              f"{r.effort:<20}{r.verdict}")
    print("=" * 72)
    print(f"\nFull report: {path}")
    print("Per-site URL lists: outputs/reports/urls_<site>.txt\n")
    print("Next: pick the top 2-3 with verdict SCRAPE, then build adapters.\n")


if __name__ == "__main__":
    main()