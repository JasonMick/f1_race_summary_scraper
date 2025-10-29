# Wikipedia F1 Grand Prix Race Summaries Extractor

A Python 3 script that crawls a Wikipedia **Category** (e.g., *Category:Mexican Grand Prix*), visits each year’s race page, and extracts a concise HTML snippet composed of:

1) **Opening paragraph(s)** from the article lead, and  
2) The **Race** section (the `Race...` heading and the content between it and the next heading of the same level).

The script writes one JSON object keyed by **year**, where each value contains the ISO date (converted to a readable form) and the **race_summary** HTML string.

> Built for consistency across heterogeneous page layouts (h2/h3/`mw-heading*` containers) and to avoid pulling in unrelated sub‑sections like *Background*, *Free practice*, or *Qualifying* under long “Report” pages.

---

## Requirements

Python ≥ 3.8 and the following libraries:

- `requests>=2.31.0,<3`
- `beautifulsoup4>=4.12.3`
- `lxml>=5.2.1`

Install via:

```bash
pip install -r requirements.txt
```

---

## Usage (Remote: crawl a Wikipedia Category)

Typical call (old behavior preserved):

```bash
python extract_wikipedia_f1_grand_prix_race_summaries_by_year.py   --category-url https://en.wikipedia.org/wiki/Category:Mexican_Grand_Prix   --out mexico_gp_race_summaries.json   --exclude-current-year   --sleep 0.5   --debug
```

**Flags**

- `--category-url URL`  
  Wikipedia category page to crawl. Links to year pages are discovered from here.

- `--out FILE.json`  
  Output path for the aggregated JSON.

- `--exclude-current-year`  
  Skips the current in‑progress year if present on the category page.

- `--sleep SECONDS`  
  Polite delay between requests to avoid hammering Wikipedia.

- `--debug`  
  Print detailed parsing diagnostics, including paragraph counts for the lead (I) and the Race section (J).

> **Note on ordering:** Years in the output JSON are written **oldest → newest** (chronological).

---

## Usage (Local: test against a saved year page)

When iterating on parsing logic, you can supply a saved HTML file for a single race page:

```bash
python extract_wikipedia_f1_grand_prix_race_summaries_by_year.py   --local-year-html ./view-source_https___en.wikipedia.org_wiki_2015_Mexican_Grand_Prix.html   --out mexico_gp_2015_test.json   --debug
```

This bypasses network calls and parses only the provided file.

---

## Output Format

The JSON maps each **year** (string) to an object:

```json
{
  "2015": {
    "date": "November 1, 2015",
    "race_summary": "<p>...lead paragraphs...</p>\n\n<div class=\"mw-heading mw-heading3\"><h3 id=\"Race\">Race</h3>...</div>"
  },
  "2016": { "...": "..." }
}
```

You can inspect a real run in your `mexico_gp_race_summaries.json`.  (See the file in this workspace.)

---

## Parsing Strategy (TL;DR)

1. **Opening paragraphs (lead)**  
   - Find the top content wrapper: `<div class="mw-content-ltr mw-parser-output">`.  
   - Accumulate only **unclassed `<p>`** tags until the first h2 container (`<div class="mw-heading mw-heading2">`), skipping placeholder `<p class="mw-empty-elt">…</p>`.  
   - Emits debug counter **{I}** = number of `<p>` blocks captured from the lead.

2. **Race section**  
   - Continue through the same top-level content wrapper to find the first h2 **or** h3 container whose heading text matches `^Race.*$` (case‑insensitive).  
   - Capture **all sibling elements** following that heading **until the next heading of the same level** (h2 → next h2, h3 → next h3). This lets us include important lists, tables, and paragraphs under “Race”.  
   - Emits debug counter **{J}** = number of `<p>` blocks inside the Race section capture.

If no `Race` heading exists, the script leaves the Race portion blank but still writes any lead paragraphs captured.

---

## Troubleshooting

- **403 Forbidden on category fetch**: Ensure you’re using the script’s default **User‑Agent** and a reasonable `--sleep` value. Wikipedia may throttle aggressive clients.  
- **Year order reversed**: The script intentionally sorts years ascending (oldest → newest) before writing output.  
- **Too much content captured**: The Race capture stops strictly at the next heading of the same level to prevent pulling in *Background/Practice/Qualifying*. Keep `--debug` on and verify the DOM structure in the saved page when tuning.

---

## Example

Reproduce a full Mexico GP scrape with diagnostics:

```bash
python extract_wikipedia_f1_grand_prix_race_summaries_by_year.py   --category-url https://en.wikipedia.org/wiki/Category:Mexican_Grand_Prix   --out mexico_gp_race_summaries.json   --exclude-current-year   --sleep 0.5   --debug
```

---

## Notes

- Be mindful of Wikipedia’s terms of use and robots.txt.  
- For large categories, consider higher `--sleep` and occasional restarts.  
- The extractor targets stable MediaWiki structures but may require tweaks if Wikipedia templates change.
