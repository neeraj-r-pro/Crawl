# Company Website Crawler & Extractor

A Python system that takes a company website URL, discovers the pages worth
looking at (About, Products, Services, Contact, ...), extracts structured
company information from them, and writes it out as clean, reusable JSON
(and optionally SQLite).

Built for the "Python Developer — Web Automation & Data Extraction"
technical assignment. See `docs/ARCHITECTURE.md` for the full write-up of
design decisions, and `docs/TEST_RESULTS.md` for what was tested and the
live run results.

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

This project was built inside a sandboxed development environment whose
outbound network access is restricted to a short allow-list of developer
domains (pypi.org, github.com, npmjs.com, etc.) — it cannot reach arbitrary
company websites. The code itself has **no such restriction**; every
sample run in `output/` and `docs/TEST_RESULTS.md` was a genuine live
crawl against a real, public, reachable website from within that sandbox
(github.com, pypi.org, yarnpkg.com), not a mock. Run it against any
company's site from a normal machine/network and it will work the same
way. If you want to point it at a specific set of target companies for
the interview demo, just pass their URLs with `--url`.

## 3. Viewing the output

Output is one JSON file per site, e.g. `output/example_com.json`:

```jsonc
{
  "input_url": "https://example-company.com",
  "crawl_meta": {
    "started_at": "...", "finished_at": "...",
    "pages_discovered": 18, "pages_fetched_ok": 16, "pages_failed": 2,
    "max_pages_limit": 40, "stop_reason": "queue_exhausted"
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
      "extraction_result": "success", "depth": 1, "rendered_with": "static", ... },
    ...
  ]
}
```

`pages` is a full audit trail of every URL the crawler touched — including
ones that failed — with why. That's deliberate: the assignment asks for
"whether the page was successfully processed", not just the successes.

## 4. Running the tests

```bash
pip install pytest
python -m pytest tests/ -v
```

69 tests, no network or external services required — they run against
either local HTML fixtures or an in-process mock HTTP server
(`tests/local_site.py`) that simulates timeouts, redirects, 404s, 500s,
robots.txt, oversized pages, and JS-injected content. See
`docs/TEST_RESULTS.md` for a breakdown and what's deliberately *not*
covered.

## 5. Project layout

```
crawler/
  config.py           tunables: limits, keyword lists, timeouts
  url_utils.py         normalization, dedup keys, same-site checks
  page_classifier.py    URL/content -> page category (about/products/contact/...)
  fetcher.py            static HTTP fetch: retries, timeouts, robots.txt, size caps
  dynamic_fetcher.py     Playwright fallback for JS-rendered pages + SPA detection
  extractor.py           pulls fields (name, description, contacts, ...) out of HTML
  models.py               the output schema (dataclasses)
  crawler.py               orchestration: priority-queue BFS + cross-page aggregation
  storage.py                JSON / SQLite writers
  main.py                    CLI entry point
tests/                        69 tests, fixtures + local mock server, no network needed
docs/
  ARCHITECTURE.md              full design write-up (read this for the "why")
  TEST_RESULTS.md               what was tested, live run results, known limitations
output/                          sample JSON output from real live crawls
```
