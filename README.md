# 🏎️ Wikipedia F1 Grand Prix Race Summary Extractor

This Python script fetches and parses Wikipedia pages for a specified **Formula 1 Grand Prix** category, extracting:

✅ Race date  
✅ Opening race summary paragraphs  
✅ Detailed race narrative under the **Race** section (if present)  
✅ Output saved to structured JSON

This tooling is built for motorsports analytics, historical research, and content creation projects  
(e.g., TikTok breakdowns, race history dashboards, weather trend studies).

---

## 🚀 Features

| Feature | Description |
|--------|-------------|
| Auto-scrapes all year pages from a GP Category page | Uses Wikipedia category listings to discover yearly race pages |
| Robust HTML parsing | Handles Wikipedia page structure variations across decades |
| Dual-layer summary extraction | ✅ Intro paragraphs + ✅ Detailed **Race** section |
| Future-proof year filtering | Option to exclude upcoming seasons |
| Debug mode | Output helpful trace logs of parsing decisions |
| Friendly rate-limiting | Optional sleep delays between requests |

---

## 📦 Requirements

Create a virtual environment (recommended), then install:

pip install -r requirements.txt

sql
Copy code

Where **requirements.txt** contains:

requests>=2.31.0,<3
beautifulsoup4>=4.12.3
lxml>=5.2.1

yaml
Copy code

These are used for:

| Library | Purpose |
|--------|---------|
| `requests` | Fetch Wikipedia HTML pages |
| `beautifulsoup4` | Parse DOM trees |
| `lxml` | Faster & more reliable HTML parser backend |

---

## 🧑‍💻 Usage

Example command:

python extract_wikipedia_f1_grand_prix_race_summaries_by_year.py
--category-url https://en.wikipedia.org/wiki/Category:Mexican_Grand_Prix
--out mexico_gp_race_summaries.json
--exclude-current-year
--sleep 0.5
--debug

yaml
Copy code

---

### ✅ Argument Reference

| Argument | Required? | Description |
|---------|-----------|-------------|
| `--category-url URL` | ✅ Yes | Wikipedia category for a specific GP event |
| `--out FILE.json` | ✅ Yes | Output JSON file |
| `--exclude-current-year` | Optional | Skip current or future listed seasons |
| `--sleep N` | Optional | Delay (seconds) between page requests (avoid rate-limits) |
| `--debug` | Optional | Print parsing details for troubleshooting |
| `--timeout N` | Optional | HTTP timeout in seconds (default: 10) |

---

## 📂 Output Structure

Example JSON entry:

```json
{
  "2015": {
    "url": "https://en.wikipedia.org/wiki/2015_Mexican_Grand_Prix",
    "date": "November 1, 2015",
    "race_summary": "<p>The <b>2015 Mexican Grand Prix</b> ...",
    "summary_paragraph_count": {
      "intro": 3,
      "race_detail": 6
    }
  }
}
