# Company Website Crawler & Extractor

A Python system that takes a company website URL, discovers the pages worth
looking at (Home, About, Products, Services, Solutions, Industries,
Projects, Locations, Contact), extracts structured company information
from them, and writes it out as clean, reusable JSON (and optionally
SQLite).

Built for a "Python Developer — Web Automation & Data Extraction"
technical assignment. This README covers installation and running the
system (Deliverable A). See `docs/ARCHITECTURE.md` for the full technical
write-up (Deliverable C) and `docs/TEST_RESULTS.md` for test results and
live validation runs (Deliverable D). Sample output from real crawls is
in `output/` (Deliverable B).

## Deliverables map

| Assignment asks for | Where to find it |
|---|---|
| A. Source code + install/run instructions | This README + `crawler/` |
| B. Sample output from 3+ real, structurally different sites | `output/` |
| C. Technical documentation (architecture, strategy, error handling, limitations, scalability) | `docs/ARCHITECTURE.md` |
| D. Test results | `docs/TEST_RESULTS.md` + `python -m pytest tests/ -v` |
| E. Presentation | *(prepare separately for the interview — see note at the bottom)* |

## 1. Installation

Requires Python 3.10+.

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

# Optional, only if you want JavaScript-rendered ("dynamic") page support:
python -m playwright install chromium
```

If you skip the Playwright install, the crawler still works end-to-end —
it just can't render JS-heavy pages, and will say so in the output
(`extraction_result: "partial_static_only"`) instead of silently giving
you an empty page.

## 2. Running it

**Easiest way — interactive:**

```bash
python main.py
```

This prompts you for a URL (and whether to enable JavaScript rendering),
then runs with sensible defaults and writes to `output/<hostname>.json`.

**Full CLI — for scripting, batch runs, or custom settings:**

```bash
python -m crawler.main --url https://example-company.com
```

This crawls the site (default: up to 40 pages, depth 3), and writes
structured output to `output/<hostname>.json`.

Useful flags:

```bash
# Custom limits
python -m crawler.main --url https://example.com --max-pages 50 --max-depth 3

# Disable the Playwright/dynamic-rendering fallback (static-only, faster)
python -m crawler.main --url https://example.com --no-dynamic

# Also write to SQLite
python -m crawler.main --url https://example.com --sqlite output/companies.db

# Custom output path
python -m crawler.main --url https://example.com --output output/mycompany.json

# Be more/less polite to the target server (seconds between requests, same host)
python -m crawler.main --url https://example.com --delay 1.0

# Ignore robots.txt (not recommended -- only for sites you own/control)
python -m crawler.main --url https://example.com --no-robots
```

Run `python -m crawler.main --help` for the full list.

### A note on where this was built

Parts of this project were built inside a sandboxed development
environment whose outbound network access is restricted to a short
allow-list of developer domains (pypi.org, github.com, npmjs.com, etc.)
— it cannot reach arbitrary company websites. The code itself has **no
such restriction**; every sample run in `output/` and
`docs/TEST_RESULTS.md` was a genuine live crawl against a real, public,
reachable website (github.com, pypi.org, yarnpkg.com, and — from outside
that sandbox — boncnetwork.com), not a mock. Run it against any
company's site from a normal machine/network and it will work the same
way.

## 3. Viewing the output

Output is one JSON file per site, e.g. `output/example_com.json`:

```jsonc
{
  "input_url": "https://example-company.com",
  "crawl_meta": {
    "started_at": "...", "finished_at": "...",
    "pages_discovered": 40, "pages_fetched_ok": 40, "pages_failed": 0,
    "max_pages_limit": 40, "stop_reason": "max_pages_reached"
  },
  "company": {
    "company_name": "...", "website": "...", "description": "...",
    "headquarters": "...", "other_locations": [...],
    "products": [...], "services": [...], "solutions": [...], "industries": [...],
    "emails": [...], "phones": [...], "social_links": {...}
  },
  "pages": [
    { "url": "...", "page_type": "about", "title": "...",
      "http_status": 200, "fetched_ok": true,
      "extraction_result": "success", "depth": 1, "rendered_with": "static",
      "final_url": null, "is_third_party": false, ... },
    ...
  ]
}
```

`pages` is a full audit trail of every URL the crawler touched —
including ones that failed, and ones excluded from aggregation — with
why. That's deliberate: the assignment asks for "whether the page was
successfully processed", not just the successes.

`is_third_party` and `page_type: "third_party_listing"` cover a
real-world case that came up during testing: on directory/marketplace
sites (e.g. a business-listing platform), some pages on the *same
domain* describe a completely different company (another business
listed on the platform), not the one being crawled. Those pages are
still fetched and recorded for discovery, but their data is excluded
from the aggregated `company` profile — domain matching alone isn't
enough to establish page ownership. See `docs/ARCHITECTURE.md` and
`docs/TEST_RESULTS.md` for the full reasoning and how it's detected.

## 4. Running the tests

```bash
python -m pytest tests/ -v
```

113 tests, no network or external services required — they run against
either local HTML fixtures or an in-process mock HTTP server
(`tests/local_site.py`) that simulates timeouts, redirects, 404s, 500s,
robots.txt, oversized pages, and JS-injected content. See
`docs/TEST_RESULTS.md` for a full breakdown, the real extraction bugs
this process caught and fixed, and what's deliberately *not* covered.

## 5. Project layout