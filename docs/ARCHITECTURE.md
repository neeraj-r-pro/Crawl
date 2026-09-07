# Technical Documentation

## 1. Architecture

```
                    ┌─────────────┐
   --url  ────────► │  main.py    │  (CLI)
                    └──────┬──────┘
                           ▼
                    ┌─────────────┐
                    │ crawler.py  │  orchestrator: priority-queue BFS
                    └──┬───────┬──┘
             ┌─────────┘       └─────────┐
             ▼                           ▼
      ┌─────────────┐            ┌───────────────┐
      │ fetcher.py  │            │page_classifier│
      │ (requests)  │            │ .py           │
      └──────┬──────┘            └───────────────┘
             │  (if page looks like a JS shell)
             ▼
      ┌─────────────────┐
      │dynamic_fetcher.py│  (Playwright, optional)
      └──────┬───────────┘
             ▼
      ┌─────────────┐
      │extractor.py │  HTML -> ExtractedPage (per page)
      └──────┬──────┘
             ▼
      ┌───────────────────────┐
      │aggregate_company_info │  many ExtractedPage -> one CompanyInfo
      │ (in crawler.py)       │
      └──────┬─────────────────┘
             ▼
      ┌─────────────┐
      │ storage.py  │  -> JSON / SQLite
      └─────────────┘
```

**Major components and how they talk to each other:**

- `Crawler.crawl()` owns a priority queue of URLs to visit and a `visited`
  set for dedup. For each URL it pops, it calls `_process_url()`, which:
  1. asks `page_classifier` for a pre-fetch category guess (from the URL/anchor text),
  2. calls `fetcher.Fetcher.fetch()` to get the HTML (with retries/timeouts/robots.txt handled inside),
  3. if the static HTML looks like an empty JS shell, calls `dynamic_fetcher.DynamicFetcher.fetch()` for a browser-rendered version instead,
  4. calls `extractor.extract()` to pull structured fields out of whichever HTML it ended up with,
  5. returns a `PageRecord` (for the audit trail) + an `ExtractedPage` (for aggregation) + the list of links found, so the crawler can enqueue new URLs.
  - Every page — success or failure — produces exactly one `PageRecord`. Nothing is silently dropped.
- After the crawl finishes, `aggregate_company_info()` merges every page's `ExtractedPage` into one `CompanyInfo` record, using an explicit, explainable conflict-resolution policy (section 4).
- `storage.py` just serializes the final `CrawlReport` (crawl metadata + `CompanyInfo` + all `PageRecord`s) to JSON and/or SQLite. It has no crawling logic in it — swapping storage backends (e.g. to Postgres/Mongo) touches only this file.

I kept each of these as separate, independently-testable modules with one
job each (single-responsibility), rather than one large script, because
the assignment explicitly asks me to be able to explain and defend each
piece in isolation during the interview, and because it makes the test
suite meaningful (69 tests, most of them exercising exactly one module).

## 2. Technology Choices

| Choice | Why |
|---|---|
| `requests` over `httpx`/raw `urllib` | Mature, synchronous, simplest to reason about and to test with retries/timeouts. This assignment isn't at a scale (yet) where async I/O pays for its added complexity — see section 9 for where that changes. |
| `BeautifulSoup` + `lxml` parser over raw regex-on-HTML | HTML is not regular; BeautifulSoup gives a real DOM to query (`select`, `find_all`), which is what makes heuristics like "headings inside `<main>` but not `<nav>`" possible at all. `lxml` as the parser backend because it's fast and tolerant of malformed HTML (real-world requirement — see section 5). |
| Hand-rolled crawler (not Scrapy) | Scrapy is excellent at scale, but it is a full asynchronous framework with its own project structure, settings, and deployment model. For an assignment whose deliverable is "runnable source code I can explain end-to-end in an interview", a from-scratch crawler makes every decision (queueing, dedup, retries, robots.txt) visible and testable rather than delegated to a framework's defaults. Section 9 explains what I'd reach for at real scale (which does include Scrapy or an async/Celery-based rewrite). |
| Playwright over Selenium | Playwright's Python API is synchronous-friendly, ships browser binaries via a simple `playwright install` step, and has first-class `wait_for_selector`/`networkidle` support that made the SPA-detection-and-wait logic in `dynamic_fetcher.py` straightforward. It's also the more actively maintained of the two today. |
| SQLite (optional) over a full DB server | Zero setup, ships with Python, good enough to demonstrate the storage-layer seam. `storage.py` is intentionally the *only* file that knows about the storage format, so swapping in Postgres/Mongo for production is a contained change (see section 6/9). |
| Dataclasses (`models.py`) as the schema | Explicit, typed, and `asdict()`-serializable to JSON for free. This is the actual contract with "another system" the assignment asks for — field names are treated as an API and are additive-only going forward. |

## 3. Crawling Strategy

### URL discovery, normalization, and dedup (`url_utils.py`)

Two URLs are treated as the same page if they differ only in: fragment
(`#section`), trailing slash, scheme/host case, default port, or a known
set of tracking query parameters (`utm_*`, `gclid`, `ref`, ...). Everything
else in the query string is preserved, because on many sites
`/products?category=pumps` is genuinely a different page from `/products`
— stripping all query strings would under-crawl those sites.

`mailto:`, `tel:`, `javascript:`, and bare `#anchor` links are rejected
immediately (they were never real pages). Non-HTML file extensions
(`.pdf`, `.jpg`, `.zip`, `.css`, `.js`, ...) and known crawl-trap paths
(`/login`, `/cart`, `/tag/`, `/page/`, pagination, etc.) are filtered
*before* they're ever queued — this is a pre-fetch decision, not a
post-fetch failure, because there's no reason to spend a network request
proving a `.pdf` isn't HTML.

### Same-site scope

`example.com` and `www.example.com` are treated as the same site (very
common in the wild — same content, different canonical host). An
unrelated subdomain like `blog.example.com` or `careers.example.com` is
treated as **out of scope by default**, because those are frequently
separate systems (a hosted CMS, a third-party careers portal, a
completely different tech stack) that would otherwise explode the crawl
well beyond the page budget without adding much company-info value. This
is a deliberate trade-off, not an oversight — a broader "same registrable
domain across all subdomains" mode would be a one-line change in
`url_utils.is_same_site()` if a specific target company's structure
called for it.

### Which pages to crawl, which to skip

Every discovered link gets a cheap pre-fetch category guess from
`page_classifier.classify_from_url()`, based on keywords in the URL path
and (if available) the anchor text — e.g. `/about-us` → `about`,
`/products/pumps` → `products`. Pages in "priority" categories (home,
about, products, services, solutions, industries, projects, locations,
contact) are pushed onto a **priority queue** ahead of everything else;
"other" pages (and blog/news, which is rarely load-bearing for company
info) are still crawled if the page budget allows, just after the
higher-value pages.

This is why the queue is a `heapq` keyed on `(is_priority_category, depth)`
rather than plain BFS or DFS:
- **Plain DFS** can burn the entire page budget wandering deep into one
  unimportant subsection (e.g. a paginated blog) before ever reaching the
  Contact or Products pages linked directly from the homepage.
- **Plain BFS** treats every link as equally interesting, wasting fetches
  on the same footer/legal links that appear on every single page.
- The priority queue fetches the homepage first, then the pages most
  likely to contain company info, and only falls back to lower-value
  pages if budget remains — which matters a lot once `max_pages` is
  smaller than the site's total page count (the normal case on anything
  beyond a small site).

**When to stop** — any one of four conditions ends the crawl, and the
report always records which one (`stop_reason`):
- `max_pages_reached` — hit the page budget.
- `time_budget_exceeded` — wall-clock safety valve, in case a site is
  just slow rather than broken (protects against one pathological site
  hanging a batch run).
- `queue_exhausted` — genuinely ran out of in-scope, not-yet-visited URLs
  (small sites finish this way well under the page budget).
- `max_depth` — not a global stop condition, but caps how far each
  individual branch is followed from the homepage (default 3 hops),
  so the crawl doesn't chase an infinitely deep path even if the page
  budget would otherwise allow it.

### Duplicate URLs, redirects, and preventing unnecessary crawling

- URLs are deduped at *queue time* (`queued` set) so the same link found
  on five different pages is only ever fetched once.
- A URL that redirects is fetched once; `PageRecord.url` is the URL that
  was *requested*, and `PageRecord.final_url` is populated only if the
  destination differs — so the audit trail shows both "what did we ask
  for" and "where did it actually end up" without creating a second,
  duplicate page entry for the same content. This surfaced a real bug
  during testing (see `docs/TEST_RESULTS.md`, Findings 3) where an
  earlier version recorded the *final* URL as the primary key and ended
  up with two records for the same page reached two different ways.
- `robots.txt` is fetched once per host and cached (`fetcher.RobotsCache`);
  a disallowed URL is never fetched at all and is recorded with
  `error: "blocked_by_robots_txt"` rather than silently skipped, so it's
  visible in the audit trail *why* a page the site clearly links to never
  shows up as crawled.

## 4. Extraction Strategy

There is no fixed schema for "company name" or "address" on the open web,
so every field extractor in `extractor.py` tries several signals **in
order of trust** and keeps the first one that works, rather than
assuming one fixed CSS selector will work everywhere:

- **Company name**: `og:site_name` meta tag → `application-name` meta →
  logo `<img alt="...">` → `<h1>` (if the `<title>` looks generic/
  placeholder — e.g. a client-rendered app whose `<title>` never updates
  past "Loading...") → cleaned `<title>` text → the domain name as a
  last resort. A live crawl of yarnpkg.com surfaced a real case where
  naively picking the "longest" segment of a piped title
  (`"Home page | Yarn"`) chose the wrong one; fixed by expanding the
  generic-word filter rather than by hardcoding anything Yarn-specific.
- **Description**: `meta[name=description]` → `og:description`.
- **Emails / phones**: regex over the page's visible text, filtered
  against a placeholder blocklist (`you@company.com`, `test@example.com`,
  image filenames that regex-match the email pattern, etc.) — a real
  false positive I caught while testing against github.com's docs pages,
  which are full of `you@company.com`-style example snippets.
- **Addresses**: `<address>` tags, plus elements whose `class`/`id`
  hints at a location block, plus schema.org `PostalAddress` microdata.
- **Products / services / solutions / industries**: `<h2>`/`<h3>`/`<h4>`
  headings and linked list items, scoped to pages already classified as
  that category, with `<nav>`/`<header>`/`<footer>` explicitly excluded
  from consideration. Without that exclusion, every page's shared footer
  links (visible on every single page of a site) flood every category
  with the same repeated boilerplate — this was caught on a real crawl
  of github.com, where "Products" was initially full of nav items like
  "Support" and "Company" instead of actual product names.
- **Social links**: exact-domain match against a known list
  (LinkedIn/Twitter-X/Facebook/Instagram/YouTube/GitHub), explicitly
  excluding links back to the site's *own* domain — otherwise, crawling
  github.com itself would misreport an internal link like
  `github.com/features/actions` as a "GitHub" social profile link.

This extractor is deliberately layered and conservative rather than
trying to be exhaustive — see section 7 for exactly what was and wasn't
tested, and `docs/TEST_RESULTS.md` for the specific false positives this
approach caught during development.

### Handling duplicates, conflicts, and missing information

Per-page results are merged into one `CompanyInfo` by
`aggregate_company_info()` with two different policies depending on the
field type:

- **Scalar fields** (name, description, headquarters): **first good
  candidate from the most authoritative page type wins.** For company
  name and headquarters, "about" and "contact"/"home" pages rank above
  everything else; for description, "about" ranks above "home" which
  ranks above others. This is a simple, explainable rule — I can point
  at exactly which page a field came from — rather than something like
  a voting/similarity scheme that would be harder to defend when asked
  "why did you pick that value".
- **List fields** (products, services, emails, phones, social links):
  **union across all pages, case-insensitive deduplication**, order
  preserved by first appearance. The same product name appearing on both
  the homepage and the dedicated products page is expected, not an
  error, so it's merged rather than flagged.
- **Contact details specifically** (emails/phones) are only trusted from
  pages whose *purpose* is representing the organisation itself — home,
  about, contact, locations. This was a deliberate fix after a live
  crawl of pypi.org pulled in individual package maintainers' personal
  emails from `/project/<name>` pages and (correctly, technically, but
  wrongly for the "company info" use case) attributed them to PyPI
  itself. Pages like `/products/<item>` or `/project/<name>` frequently
  embed third-party contact details that don't belong to the company
  being profiled.
- **Missing information** is simply left as `null` / `[]` — there is no
  guessing or fabrication. `CompanyInfo.headquarters` is `null` on the
  github.com sample run precisely because none of the crawled pages had
  a recognizable address block; that's a correct, honest result, not a
  bug to paper over.
- **Incorrectly extracted information**: rather than try to catch every
  possible false positive after the fact, the strategy throughout is to
  narrow the *source* of each field (see the placeholder-email filter,
  the own-domain exclusion for social links, the nav/footer exclusion
  for product headings, and the trusted-page-type restriction on
  contact info above) — each of these was added in response to a
  specific false positive observed on a real, live crawl during
  development, not invented speculatively.

## 5. Dynamic Websites

**Not every page is rendered with a browser.** Browser rendering is
5–20× slower than a plain HTTP GET and needs a real Chromium process, so
`dynamic_fetcher.py` uses it selectively, in three steps:

1. Every page is fetched statically first (`fetcher.py`).
2. `looks_like_js_shell()` checks the static HTML: strip `<script>`/
   `<style>`, measure the remaining visible text. If it's under ~200
   characters *and* either the body is almost empty or there's a known
   SPA mount point (`id="root"`, `id="app"`, `id="__next"`, etc.), the
   page is very likely a client-side-rendered shell whose real content
   never shipped in the initial HTML response.
3. **Only then** is a real Playwright/Chromium render triggered for that
   specific URL, waiting for network-idle (and an optional CSS selector)
   before capturing the rendered HTML.

This was proven end-to-end (not just described) against a local test
page that fetches its real content from a separate endpoint via
client-side JavaScript after the initial page load — the same pattern a
real API-driven SPA uses. The static fetch genuinely returns zero usable
content (an empty shell); the Playwright fetch correctly recovers the
company name and contact email that only exist after JavaScript runs.
See `tests/test_crawler_e2e.py::test_dynamic_rendering_recovers_js_injected_content`
and `output/4_dynamic_content_demo.json` for the actual proof, and
`docs/TEST_RESULTS.md` for the raw before/after HTML.

**When I'd use plain HTTP requests vs. a browser:**
- HTTP requests for the large majority of company marketing sites, which
  are still server-rendered (confirmed directly on all three live sites
  crawled for this assignment — github.com, pypi.org, and yarnpkg.com are
  all server-rendered and never triggered the dynamic fallback).
- A browser only for pages that the shell-detection heuristic flags,
  and only for *that* page, not the whole site — keeping the common case
  fast while still handling genuinely JS-only company sites correctly.

**Graceful degradation**: if Playwright (or its browser binaries) isn't
installed, `DynamicFetcher.is_available()` returns `False` and the
crawler simply keeps the static result, recording
`extraction_result: "partial_static_only"` on that page rather than
crashing the whole run. A missing optional dependency should never take
down a batch crawl of hundreds of other, unrelated sites.

**Performance implication**: this is precisely why the shell-detection
gate exists rather than "render everything with Playwright to be safe" —
at the 600-sites/day scale discussed in section 9, unconditional browser
rendering would multiply infrastructure cost and latency for content
that, on the large majority of company sites, was never necessary.

## 6. Data Quality and Storage

Output is JSON by default (`storage.write_json`) — structured,
schema-stable (`models.py`'s dataclasses are the contract), and readable
by literally any downstream system with zero setup. An optional SQLite
writer (`storage.write_sqlite`) is included specifically to demonstrate
the seam for a real persistent store; `storage.py` is the *only* file
that knows about the output format, so adding a Postgres or MongoDB
writer later is a contained, additive change that doesn't touch crawling
or extraction logic at all.

Every page — successful or not — gets a `PageRecord` with: URL, category,
title, HTTP status, whether it was fetched successfully, an
`extraction_result` (`success` / `partial` / `partial_static_only` /
`failed`), and an `error` string when applicable. This satisfies the
assignment's explicit ask to retain "whether the page was successfully
processed" for every discovered page, not just the ones that worked.

Duplicate/conflicting/missing information handling is covered in section
4 above (it's the same aggregation logic, not a separate storage-layer
concern).

## 7. Error Handling

The crawler never stops because one page fails — every failure mode is
caught, recorded, and the crawl continues:

| Situation | Handling |
|---|---|
| Connection timeout | Retried (up to `MAX_RETRIES`, exponential backoff), then recorded as failed with the exception type/message. Proven live against a local server route that deliberately sleeps past the configured timeout. |
| HTTP 404 / 403 | Recorded as `fetched_ok=False`, `error="http_404"` / `"http_403"`; crawl continues to the next queued URL. |
| HTTP 500 | Retried automatically (transient-server-error assumption), then recorded as failed if retries are exhausted. |
| Redirect | Followed automatically (`requests`' default); final URL recorded separately from the requested URL (section 3) so redirects are visible in the audit trail without creating duplicate page entries. |
| Invalid URL | Rejected during normalization (`url_utils.normalize_url` returns `None`) before a network request is ever attempted. |
| Malformed HTML | `lxml`'s parser is deliberately tolerant of broken/unclosed tags — proven against a fixture with intentionally malformed HTML; extraction degrades gracefully (whatever *is* parseable gets extracted) rather than raising. |
| Unexpected page structure | Every extractor field is independently optional — a page missing an `<address>` tag just yields `null`/`[]` for that field, it doesn't fail the whole page. |
| JavaScript-only content | Detected and handled per section 5; if Playwright is unavailable, degrades to `partial_static_only` rather than crashing. |
| Non-HTML content served | Content-Type is checked even when the URL slipped past the extension filter (e.g. a PDF served without a `.pdf` suffix) — rejected before the body is even fully downloaded. |
| Oversized page | Streamed and size-capped (default ~5MB) — aborted mid-download rather than pulling an arbitrarily large response into memory. |
| `robots.txt` disallow | Never fetched; recorded with `error="blocked_by_robots_txt"`. |

**What happens when a page can't be processed**: it gets exactly one
`PageRecord` with `fetched_ok=False` and a specific `error` string
explaining why, its links are never followed (nothing to extract them
from), and the crawl moves on to the next item in the queue. Nothing
raises out of `Crawler.crawl()` for any of the situations above — I
proved this with a dedicated local mock server
(`tests/local_site.py`) that serves all of these failure modes on
purpose, specifically so the error handling could be tested without
depending on a real site happening to be broken in the right way at
test time.

## 8. Testing

**69 automated tests** (`pytest tests/ -v`), organized by what they
exercise:

- `test_url_utils.py` (14 tests) — normalization, dedup keys, same-site
  logic, tracking-param stripping, non-HTML/skip-path detection.
- `test_page_classifier.py` (11 tests) — URL/content-based category
  classification, crawl-worthiness gating, priority ordering.
- `test_extractor.py` (19 tests) — every extracted field, against both
  local HTML fixtures and hand-crafted edge cases (placeholder emails,
  own-domain social links, nav/footer boilerplate exclusion, generic
  title fallback).
- `test_aggregation.py` (7 tests) — the cross-page merge/conflict policy
  in isolation, using synthetic `ExtractedPage` objects (no network,
  no HTML parsing — purely the aggregation logic).
- `test_fetcher.py` (10 tests) — retries, timeouts, redirects, all the
  HTTP status codes in section 7's table, oversized pages, robots.txt,
  content-type rejection — run against an in-process mock HTTP server,
  not the real network.
- `test_crawler_e2e.py` (8 tests) — full crawls end-to-end against the
  same mock server: priority-queue behaviour, max-pages/robots.txt
  enforcement, dedup, and the dynamic-rendering proof from section 5.

**Why a local mock server (`tests/local_site.py`) instead of mocking
`requests` with a library like `responses`**: it exercises the *real*
`requests`/`urllib3` networking stack (real sockets, real timeouts, real
redirects) rather than a mocked substitute, which is a stronger test of
the actual failure-handling code paths — and it deliberately serves every
error condition from section 7 on demand, which a real website would
only do by chance.

**What was tested**: URL handling, page discovery/classification,
extraction (every field, including edge cases and false-positive
sources found during development), duplicate prevention (queue-level and
redirect-aware), the full range of failed-request types, malformed/empty
content, and structured JSON output shape.

**What was *not* tested** (and why): actual visual rendering correctness
of Playwright output (Playwright's own test suite covers its rendering
fidelity — not something to re-test here); performance/load testing at
the 600-sites/day scale (that's a design discussion in section 9, not
something a single machine's test run could meaningfully validate);
exhaustive fuzzing of every conceivable malformed-HTML shape (one
deliberately-broken fixture proves the parser degrades gracefully rather
than raising, which is the property that matters — it wouldn't be a good
use of time to enumerate every way HTML can be malformed). See
`docs/TEST_RESULTS.md` for the full test run output and the specific
real-world extraction bugs this test-driven process caught and fixed.

## 9. Performance and Scalability — 3 sites to 600/day

The current design (single process, synchronous `requests`, in-memory
queue) is intentionally simple and comprehensible for a 3-site demo. Here
is what would actually change to reach 600 company sites/day (potentially
tens of pages each, so tens of thousands of page fetches/day —
roughly 1 page every ~3 seconds sustained, which is easy in aggregate but
needs to not hammer any *individual* site):

- **Concurrency**: move from one synchronous process to either (a) an
  `asyncio` + `httpx`/`aiohttp` rewrite of `fetcher.py`, or (b) a worker
  pool (Celery/RQ) where each worker crawls one site at a time using the
  existing synchronous code largely unchanged. I'd lean toward (b) first
  — it reuses everything already built and tested, and site-level
  isolation (one worker = one site) is a natural fit for "600 independent
  websites" rather than needing fine-grained async orchestration within
  a single site's crawl.
- **Queues**: a real message queue (Redis/RabbitMQ/SQS) holding
  "crawl this company" jobs, decoupling job intake from execution and
  giving natural backpressure, retry, and dead-letter handling instead
  of the current in-memory `heapq`.
- **Rate limiting**: the per-host delay (`Fetcher._throttle`) already
  exists per-crawl; at scale this needs to be a *shared*, cross-worker
  rate limit per host (e.g. a Redis-backed token bucket keyed on
  registrable domain), so that if two of the 600 companies happen to
  resolve to the same infrastructure/CDN, we still don't hammer it.
- **Retry handling**: currently in-process, exponential backoff, bounded
  retries. At scale, failed jobs should go back onto the queue with their
  own backoff/retry-count metadata rather than blocking a worker thread
  during backoff sleeps.
- **Resource usage**: Playwright/Chromium is the expensive resource — a
  small dedicated pool of browser workers (not one per crawl worker)
  that static-fetch workers hand off to *only* when the shell-detection
  heuristic fires, so the 5-20x cost of a real browser is paid rarely,
  not by default. This is the same selective-rendering principle from
  section 5, just applied at fleet scale.
- **Database/storage**: SQLite doesn't survive concurrent writers well;
  swap `storage.py`'s backend for Postgres (structured company/page
  tables, which `storage.py`'s schema already mirrors almost directly)
  or a document store like MongoDB if the field set is expected to stay
  volatile per-industry. Either way, this is a contained change confined
  to `storage.py`.
- **Scheduling**: a daily batch scheduler (cron/Airflow/a simple queue
  producer) enqueues the day's 600 company URLs; workers pull from the
  shared queue until it's empty. Re-crawls (e.g. weekly refresh) reuse
  the same pipeline with a different trigger.
- **Monitoring**: per-crawl metrics already exist in `CrawlReport`
  (`pages_discovered`, `pages_fetched_ok`, `pages_failed`, `stop_reason`)
  — at scale these get emitted to a metrics system (Prometheus/
  CloudWatch) per job, with alerting on abnormal failure rates for a
  given company (e.g. "this site went from 90% success to 10% success
  overnight" is a much more useful signal than any single page's status).
- **Failure recovery**: a company whose crawl fails entirely (site down,
  aggressive bot-blocking, etc.) shouldn't block the batch — it gets
  logged with its failure reason and retried on the next scheduled run,
  the same way an individual page failure doesn't block the rest of that
  site's crawl today.

**What would become the bottleneck first**: at moderate scale, the
Chromium/Playwright rendering step — it's an order of magnitude more
expensive per page than a static fetch, and if the shell-detection
heuristic under- or over-fires on a batch of sites with unusually
JS-heavy company templates, that cost compounds fast across hundreds of
sites. I'd instrument and monitor "% of pages that triggered dynamic
rendering" per run specifically to catch that early, and the first thing
I'd change is decoupling the browser pool from the static-fetch worker
pool (as above) so a browser-heavy batch of sites doesn't starve
unrelated static-only crawls of resources.

**What I'd change first, concretely, moving toward production**: swap
the in-memory queue for a real message queue and make `storage.py`
write to Postgres instead of SQLite — those two changes alone turn this
from "a script that processes one site per invocation" into "a system
that can have many workers pulling from a shared backlog and writing to
a shared, concurrently-readable store", which is most of what's needed
to go from 3 sites to 600/day without a full rewrite of the crawling or
extraction logic that's already built and tested.

## 10. Limitations (honest accounting)

- **Heuristic extraction, not guaranteed-complete.** Company name,
  description, and address extraction are pattern-based, not a solved
  problem — a site with an unusual structure can still produce a
  partial or empty field. This is why every field defaults to `null`/`[]`
  rather than guessing, and why the assignment's own evaluation
  principle ("a solution that extracts everything from one website but
  fails on a different website is not necessarily a strong solution")
  drove most of the actual engineering effort here: three real, live,
  structurally different sites were crawled during development
  specifically to surface and fix extraction bugs (see
  `docs/TEST_RESULTS.md`), rather than tuning against one target site.
- **Subdomain scoping is a deliberate trade-off** (section 3) that could
  under-crawl a company whose "About"/"Careers" content genuinely lives
  on a different subdomain. Configurable, not hardcoded, but off by
  default for crawl-budget reasons.
- **Product/service heading extraction is intentionally broad/noisy**
  (section 4) — it's a discovery aid for a downstream consumer to filter
  further, not a guarantee that every list item is actually a product.
  The blocklist-based filtering added for Finding 9 (company-profile
  template sections like "About Us"/"GST"/"PAN Number" leaking into
  products/industries lists) and the listing/card-aware extraction added
  for Finding 10 (business-entity names, CTAs, dates, ratings, metric
  callouts, testimonial sentences) both reduce this noise substantially,
  but neither is complete. A specifically observed residual case: short
  marketing taglines and customer-logo names on SaaS marketing pages
  (e.g. a case-study card reading "Stripe" or a headline reading "Reduce
  risk") are structurally indistinguishable from a legitimate short
  product/service name without genuine semantic understanding of the
  page's intent — no shape-based or keyword-based rule reliably tells
  them apart, and this project does not claim to have solved that. This
  is a genuinely open problem, not something the current fixes claim to
  have eliminated outright. Fixing the industries page-classification
  bug (Finding 11e) means this exact noise class now surfaces in
  `industries` on github.com too (customer-logo names like "3M",
  "Stripe", "Doctolib" on industry case-study cards) — not a new bug,
  the same open problem appearing wherever the relevant cards actually
  live on a given site.
- **Cross-company contamination is mitigated by URL pattern, not
  guaranteed.** `is_third_party_listing_url()` (Finding 11a) catches the
  common `/business/`, `/listing/`, `/vendor/`, `/supplier/`, `/member/`,
  `/seller/`, `/profile/`, `/biz/` directory-detail conventions, but a
  directory site using a different URL scheme for individual listings
  (e.g. numeric IDs with no distinguishing path segment, or a completely
  custom routing scheme) would not be caught, and its data could still
  leak into aggregation. This is a URL-convention heuristic, not a
  content-understanding check of "does this page describe a different
  legal entity than the one I started crawling" — a fully general
  solution to that would need something closer to named-entity
  resolution, which is out of scope for a heuristic crawler.
- **Dynamic-rendering coverage depends on the shell-detection heuristic**
  firing correctly. A page that's mostly server-rendered but has one
  critical JS-injected detail (e.g. a phone number swapped in by a
  personalization script) could be missed if the heuristic doesn't judge
  the page "thin enough" to warrant a browser render. This is a real,
  named trade-off, not an unknown gap.
- **No JavaScript execution timeout tuning per-site** — a single
  `timeout_ms` is used for all dynamic renders; a genuinely slow SPA
  could still time out. Configurable in `dynamic_fetcher.py` but not yet
  exposed as a CLI flag.
- **Sandbox network restriction affected how this was demoed, not how it
  works.** As noted in the README, every live sample was a real crawl of
  a real, reachable site from within a network-restricted development
  sandbox — the code has no dependency on that restriction and behaves
  identically against any company site from a normal network.
