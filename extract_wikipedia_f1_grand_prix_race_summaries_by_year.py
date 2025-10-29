#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extract Wikipedia F1 Grand Prix race summaries by year.

Overview
--------
Given a Wikipedia Category page URL (e.g.
  https://en.wikipedia.org/wiki/Category:Mexican_Grand_Prix
),
this script:
  1) fetches all race-year article links from that category page,
  2) visits each race-year page (remotely, unless --local-html is supplied),
  3) extracts:
       - the opening lead paragraphs (unclassed <p> only) until the first H2,
       - the “Race…” section (first H2/H3 whose heading text matches ^Race.*$),
         capturing all subsequent sibling elements until the next H2/H3 at the
         same level (so we include text, lists, and tables, not just <p>),
     then
  4) merges (lead + race section) as the “race_summary” HTML string and
     writes a {year -> {...}} JSON document to --output.

Key Behaviors
-------------
- **Order**: years are written from **oldest to newest** (ascending).
- **Skipping**: any **future** years are always skipped; you can optionally
  skip the current year with --exclude-current-year.
- **Remote vs Local**:
  * remote (default): fetch category + race pages over HTTP(S)
  * local testing: use --only-year + --local-html <path> to parse a saved page
- **Robustness**: Uses a browsery User-Agent + small polite sleep between fetches.

CLI Examples
------------
Remote full run (Mexico GP), verbose logs, older->newer in JSON:
    python extract_wikipedia_f1_grand_prix_race_summaries_by_year.py \
      --category-url https://en.wikipedia.org/wiki/Category:Mexican_Grand_Prix \
      --output mexico_gp_race_summaries.json \
      --sleep 0.5 \
      --verbose

Remote single year:
    python extract_wikipedia_f1_grand_prix_race_summaries_by_year.py \
      --category-url https://en.wikipedia.org/wiki/Category:Mexican_Grand_Prix \
      --only-year 2015 \
      --verbose

Local single-year test (no network):
    python extract_wikipedia_f1_grand_prix_race_summaries_by_year.py \
      --only-year 2015 \
      --local-html view-source_https___en.wikipedia.org_wiki_2015_Mexican_Grand_Prix.html \
      --output mexico_gp_2015_only.json \
      --verbose
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup, Tag, NavigableString

# --------------- HTTP helpers ---------------

DEFAULT_HEADERS = {
    # Be nice & look like a browser to avoid 403s
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive",
}


def fetch_url(url: str, sleep_sec: float = 0.0, verbose: bool = False) -> str:
    if verbose:
        print(f"[fetch] GET {url}")
    with requests.Session() as sess:
        sess.headers.update(DEFAULT_HEADERS)
        resp = sess.get(url, timeout=30)
        resp.raise_for_status()
    if sleep_sec > 0:
        time.sleep(sleep_sec)
    return resp.text


# --------------- Parsing helpers ---------------

CONTENT_DIV_SELECTOR = "div.mw-content-ltr.mw-parser-output"
H2_DIV_CLASS = "mw-heading mw-heading2"
H3_DIV_CLASS = "mw-heading mw-heading3"

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def find_main_content_div(soup: BeautifulSoup) -> Optional[Tag]:
    return soup.select_one(CONTENT_DIV_SELECTOR)


def extract_opening_paragraphs(main_div: Tag, verbose: bool = False) -> Tuple[str, int, Optional[Tag]]:
    """
    Step #1 from your plan:
    - Iterate children of the main content div.
    - Stop when we hit a div.mw-heading.mw-heading2 (i.e. the first H2 boundary).
    - Collect ONLY <p> tags that have *no* class attribute (skip classed p e.g. 'mw-empty-elt').
    - Return (html_blob, count_of_p, last_child_seen_before_stop)
      so caller can resume scanning *after* this point for #2.
    """
    parts: List[str] = []
    p_count = 0
    stop_node: Optional[Tag] = None

    for child in main_div.children:
        if isinstance(child, NavigableString):
            # ignore raw strings at top level
            continue
        if not isinstance(child, Tag):
            continue

        # Stop when we encounter the first H2 heading container div
        if child.name == "div" and "class" in child.attrs:
            classes = " ".join(child.get("class", []))
            if classes == H2_DIV_CLASS:
                stop_node = child
                break

        # Only capture unclassed <p> tags
        if child.name == "p" and not child.get("class"):
            parts.append(str(child))
            p_count += 1

    if verbose:
        print(f"[intro] paragraphs_kept={p_count}")
    return ("\n\n".join(parts), p_count, stop_node)


def _heading_text_from_div(div: Tag) -> str:
    """Extract text from an H2/H3 'mw-heading' wrapper div."""
    # Newer MW skin wraps <h2>/<h3> in the div; find first h2/h3 child
    h = div.find(["h2", "h3"], recursive=False)
    return h.get_text(" ", strip=True) if h else div.get_text(" ", strip=True)


def _is_heading_div(tag: Tag) -> bool:
    if tag.name != "div":
        return False
    classes = " ".join(tag.get("class", []))
    return classes in (H2_DIV_CLASS, H3_DIV_CLASS)


def _level_of_heading_div(div: Tag) -> Optional[int]:
    # Returns 2 or 3 depending on whether H2 or H3 container
    classes = " ".join(div.get("class", []))
    if classes == H2_DIV_CLASS:
        return 2
    if classes == H3_DIV_CLASS:
        return 3
    return None


def extract_race_section_after(main_div: Tag, start_after: Optional[Tag], verbose: bool = False) -> Tuple[str, int]:
    """
    Step #2 from your plan:
    - Starting *after* the node returned by #1 (first H2 boundary), scan forward
      through main_div children to find the FIRST heading div (H2 or H3) whose
      heading text matches ^Race.*$  (case-insensitive).
    - Once found, capture *all subsequent sibling elements* until the next heading
      div of the SAME LEVEL (i.e., if we matched an H3, stop at the next H3; if H2, stop at next H2).
    - Return (html_blob, paragraph_count_in_this_capture).
    - If nothing found, return ("", 0). #1’s capture must remain intact regardless.
    """
    # Gather main_div children into a list so we can index
    children: List[Tag] = [c for c in main_div.children if isinstance(c, Tag)]

    # Find the start index: the position after the stop node we returned in #1
    start_idx = 0
    if start_after is not None:
        try:
            start_idx = children.index(start_after) + 1
        except ValueError:
            start_idx = 0  # be resilient

    # 1) Locate the first matching "Race..." heading div (H2/H3)
    race_heading_idx = None
    race_heading_level = None

    for i in range(start_idx, len(children)):
        node = children[i]
        if not _is_heading_div(node):
            continue
        txt = _heading_text_from_div(node)
        if re.match(r"^Race.*$", txt, re.IGNORECASE):
            race_heading_idx = i
            race_heading_level = _level_of_heading_div(node)
            break

    if race_heading_idx is None or race_heading_level is None:
        if verbose:
            print("[race] no 'Race*' heading found")
        return ("", 0)

    if verbose:
        htxt = _heading_text_from_div(children[race_heading_idx])
        print(f"[race] matched heading='{htxt}' level={race_heading_level}")

    # 2) Capture nodes AFTER the race heading until the next heading of same level
    parts: List[str] = []
    p_count = 0
    for j in range(race_heading_idx + 1, len(children)):
        node = children[j]
        if _is_heading_div(node):
            # stop at next heading of the SAME level
            lvl = _level_of_heading_div(node)
            if lvl == race_heading_level:
                break
        # Count paragraphs encountered in this capture (for debug only)
        if node.name == "p":
            p_count += 1
        parts.append(str(node))

    if verbose:
        print(f"[race] captured nodes (all types)={len(parts)}; <p> count={p_count}")

    return ("\n\n".join(parts), p_count)


def extract_iso_date(soup: BeautifulSoup, verbose: bool = False) -> Optional[str]:
    """
    Attempts to find a YYYY-MM-DD date from typical Wikipedia markup.
    We look for an element with a title/datetime attribute shaped like '2015-11-01',
    which appears in various infobox/time tags across skins.
    Returns an ISO date (YYYY-MM-DD) or None.
    """
    # Common patterns: <time datetime="YYYY-MM-DD"> or title="YYYY-MM-DD" on spans
    # 1) datetime attribute
    for t in soup.find_all(["time", "span"], attrs=True):
        dt = t.get("datetime")
        if dt and re.match(r"^\d{4}-\d{2}-\d{2}$", dt):
            return dt
    # 2) title attribute
    for t in soup.find_all(attrs={"title": True}):
        title = t.get("title", "")
        if re.match(r"^\d{4}-\d{2}-\d{2}$", title):
            return title
    # 3) last resort: search raw text for first date-like title
    # (kept minimal to avoid false positives)
    return None


# --------------- Category parsing ---------------

def parse_year_links_from_category(html: str, verbose: bool = False) -> Dict[int, str]:
    """
    Parse a Wikipedia Category page to map {year -> href} for race pages.
    We try to be generous to catch both 'Mexican Grand Prix' and 'Mexico City Grand Prix' naming.
    """
    soup = BeautifulSoup(html, "lxml")
    links: Dict[int, str] = {}
    for a in soup.select("a[href^='/wiki/']"):
        text = (a.get_text() or "").strip()
        href = a.get("href") or ""
        if not text or not href:
            continue
        # Look for a plausible year in link text
        m = YEAR_RE.search(text)
        if not m:
            continue
        year = int(m.group(0))
        if "Grand Prix" not in text:
            # Sometimes the link text might be shorter; allow href fallback check
            if "Grand_Prix" not in href:
                continue
        # Basic filter: exclude obvious non-article links (talk, category, file, etc.)
        if any(href.startswith(prefix) for prefix in ("/wiki/Talk:", "/wiki/Category:", "/wiki/File:", "/wiki/Help:")):
            continue
        # Store first-seen link per year; if duplicates exist we keep the first
        links.setdefault(year, "https://en.wikipedia.org" + href)

    # Return years ascending (oldest -> newest)
    if verbose:
        yrs = ", ".join(map(str, sorted(links.keys())))
        print(f"[category] discovered years: {yrs}")
    return {k: links[k] for k in sorted(links.keys())}


# --------------- Main extraction per page ---------------

def extract_page_summary(html: str, verbose: bool = False) -> Dict[str, str]:
    """
    Extracts:
      - pretty_date (e.g., 'November 1, 2015') if available
      - race_summary (lead paragraphs + Race section HTML joined by two newlines)
    """
    soup = BeautifulSoup(html, "lxml")
    main_div = find_main_content_div(soup)
    if not main_div:
        if verbose:
            print("[error] main content div not found")
        return {"date": None, "race_summary": ""}

    # Step #1: opening paragraphs (always independent of #2)
    lead_html, i_count, stop_node = extract_opening_paragraphs(main_div, verbose=verbose)

    # Step #2: race section (may be blank if absent; should not affect lead result)
    race_html, j_count = extract_race_section_after(main_div, stop_node, verbose=verbose)

    # Glue together (intro first, then race section)
    combined_parts = []
    if lead_html.strip():
        combined_parts.append(lead_html.strip())
    if race_html.strip():
        combined_parts.append(race_html.strip())

    combined_html = "\n\n".join(combined_parts)

    # Date (pretty)
    iso = extract_iso_date(soup, verbose=verbose)
    pretty_date = None
    if iso:
        try:
            pretty_date = datetime.strptime(iso, "%Y-%m-%d").strftime("%B %-d, %Y")
        except Exception:
            # %-d is unix-y; add Windows fallback
            try:
                pretty_date = datetime.strptime(iso, "%Y-%m-%d").strftime("%B %d, %Y")
            except Exception:
                pretty_date = None

    if verbose:
        print(f"[date] iso={iso!r} pretty={pretty_date!r}")

    return {
        "date": pretty_date,
        "race_summary": combined_html,
    }


# --------------- Orchestration ---------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract F1 GP race summaries by year from Wikipedia.")
    parser.add_argument(
        "--category-url",
        required=False,
        default="https://en.wikipedia.org/wiki/Category:Mexican_Grand_Prix",
        help="Wikipedia Category URL to crawl (default: Mexican Grand Prix).",
    )
    parser.add_argument("--output", required=True, help="Output JSON path.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Sleep between HTTP requests (seconds).")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging.")
    parser.add_argument("--only-year", type=int, default=None, help="Only scrape a single year.")
    parser.add_argument("--exclude-current-year", action="store_true", help="Skip the current year, if present.")
    parser.add_argument("--local-html", default=None, help="Parse a single local HTML file (use with --only-year).")

    args = parser.parse_args()

    now_year = datetime.now().year

    # Local single-year mode (useful for debugging)
    if args.local_html:
        if args.only_year is None:
            print("[error] --local-html requires --only-year <YYYY>", file=sys.stderr)
            sys.exit(2)
        html = Path(args.local_html).read_text(encoding="utf-8")
        data = extract_page_summary(html, verbose=args.verbose)
        # Write one-year JSON
        payload = {args.only_year: data}
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        if args.verbose:
            print(f"[done] wrote {args.output} with 1 year (local)")
        return

    # Remote mode
    try:
        cat_html = fetch_url(args.category_url, sleep_sec=args.sleep, verbose=args.verbose)
    except requests.HTTPError as e:
        print(f"[fetch] Error fetching {args.category_url}: {e}", file=sys.stderr)
        print("Failed to fetch category page.", file=sys.stderr)
        sys.exit(1)

    year_links = parse_year_links_from_category(cat_html, verbose=args.verbose)

    # Apply single-year filter (if any)
    if args.only_year is not None:
        year_links = {y: url for (y, url) in year_links.items() if y == args.only_year}

    # Exclude future + (optional) current year
    filtered: Dict[int, str] = {}
    for y, url in year_links.items():
        if y > now_year:
            # always skip future years
            continue
        if args.exclude_current_year and y == now_year:
            continue
        filtered[y] = url

    # Keep ascending order (oldest -> newest)
    years_sorted = sorted(filtered.keys())

    results: Dict[int, Dict[str, str]] = {}
    for y in years_sorted:
        page_url = filtered[y]
        if args.verbose:
            print(f"[child] {y} -> {page_url}")

        try:
            html = fetch_url(page_url, sleep_sec=args.sleep, verbose=args.verbose)
        except requests.HTTPError as e:
            print(f"[fetch] Error fetching {page_url}: {e}", file=sys.stderr)
            continue

        summary = extract_page_summary(html, verbose=args.verbose)
        results[y] = summary

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    if args.verbose:
        print(f"[done] wrote {args.output} with {len(results)} years")


if __name__ == "__main__":
    main()
