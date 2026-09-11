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
  5. for pages classified as products/services/solutions/industries, additionally runs the listing/taxonomy-aware extraction (`extractor.extract_listing_items()`) and a URL-derived taxonomy name (`extractor.derive_taxonomy_name_from_url()`) — see section 4,
  6. checks `url_utils.is_third_party_listing_url()` to flag pages that describe a *different* entity than the one being crawled — see section 4.5,
  7. returns a `PageRecord` (for the audit trail) + an `ExtractedPage` (for aggregation, unless third-party) + the list of links found, so the crawler can enqueue new URLs.
  - Every page — success or failure — produces exactly one `PageRecord`. Nothing is silently dropped.
- After the crawl finishes, `aggregate_company_info()` merges every *first-party* page's `ExtractedPage` into one `CompanyInfo` record, using an explicit, explainable conflict-resolution policy (section 4).
- `storage.py` just serializes the final `CrawlReport` (crawl metadata + `CompanyInfo` + all `PageRecord`s) to JSON and/or SQLite. It has no crawling logic in it — swapping storage backends (e.g. to Postgres/Mongo) touches only this file.

I kept each of these as separate, independently-testable modules with one
job each (single-responsibility), rather than one large script, because
the assignment explicitly asks me to be able to explain and defend each
piece in isolation during the interview, and because it makes the test
suite meaningful (113 tests, most of them exercising exactly one module).

## 2. Technology Choices

| Choice | Why |
|---|---|
| `requests` over `httpx`/raw `urllib` | Mature, synchronous, simplest to reason about and to test with retries/timeouts. This assignment isn't at a scale (yet) where async I/O pays for its added complexity — see section 9 for where that changes. |
| `BeautifulSoup` + `lxml` parser over raw regex-on-HTML | HTML is not regular; BeautifulSoup gives a real DOM to query (`select`, `find_all`), which is what makes heuristics like "repeated sibling elements = a card grid" or "headings inside `<main>` but not `<nav>`" possible at all. `lxml` as the parser backend because it's fast and tolerant of malformed HTML (real-world requirement — see section 7). |
| Hand-rolled crawler (not Scrapy) | Scrapy is excellent at scale, but it is a full asynchronous framework with its own project structure, settings, and deployment model. For an assignment whose deliverable is "runnable source code I can explain end-to-end in an interview", a from-scratch crawler makes every decision (queueing, dedup, retries, robots.txt) visible and testable rather than delegated to a framework's defaults. Section 9 explains what I'd reach for at real scale (which does include Scrapy or an async/Celery-based rewrite). |
| Playwright over Selenium | Playwright's Python API is synchronous-friendly, ships browser binaries via a simple `playwright install` step, and has first-class `wait_for_selector`/`networkidle` support that made the SPA-detection-and-wait logic in `dynamic_fetcher.py` straightforward. It's also the more actively maintained of the two today. |
| SQLite (optional) over a full DB server | Zero setup, ships with Python, good enough to demonstrate the storage-layer seam. `storage.py` is intentionally the *only* file that knows about the storage format, so swapping in Postgres/Mongo for production is a contained change (see section 6/9). |
| Dataclasses (`models.py`) as the schema | Explicit, typed, and `asdict()`-serializable to JSON for free. This is the actual contract with "another system" the assignment asks for — field names are treated as an API and are additive-only going forward (e.g. `PageRecord.is_third_party` and `PageRecord.final_url` were added without breaking any existing field). |

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
`/products/pumps` → `products`. A specific pre-check for
`/industr(y|ies)/` path segments runs *before* the generic keyword loop,
so a nested, more specific segment (e.g. `/solutions/industry/healthcare`)
correctly resolves to `industries` rather than the broader `solutions`
substring match it also happens to contain (this was a real bug found
during live testing — see `docs/TEST_RESULTS.md`, Finding 11e). Blog/news
URL conventions (`/blog/`, `/articles/`, `/press/`) are checked early too,
so an article whose slug incidentally contains another category's
keyword (e.g. `.../shaping-industry-2026...`) isn't misclassified as a
taxonomy page.

Pages in "priority" categories (home, about, products, services,
solutions, industries, projects, locations, contact) are pushed onto a
**priority queue** ahead of everything else; "other" pages (and
blog/news, which is rarely load-bearing for company info) are still
crawled if the page budget allows, just after the higher-value pages.

This is why the queue is a `heapq` keyed on
`(is_priority_category, depth, variant_rank)` rather than plain BFS or DFS:
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

**Path-variant-aware prioritization** (`variant_rank`): some sites expose
the same page in dozens of query-string variants — e.g. a filtered
product listing at `/products?categories=<uuid>` repeated once per
category. Rather than blacklisting query strings (which would break
genuinely distinct pages like `?category=pumps`), the crawler tracks how
many variants of a given *path* have already been queued and
deprioritizes further variants relative to fresh, never-seen paths at
the same depth/category. The first variant of a path is treated exactly
like any other page; the 8th is pushed behind `/about`, `/contact`, and
other distinct, not-yet-seen pages — so a small page budget isn't
consumed entirely by one repeated pattern. This was a direct fix for a
real case (a business-directory site with dozens of `?categories=`
variants competing with `/about`/`/contact` for a 40-page budget).

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
  during testing (see `docs/TEST_RESULTS.md`, Finding 2) where an
  earlier version recorded the *final* URL as the primary key and ended
  up with two records for the same page reached two different ways.
  Verified correct even in combination with dynamic rendering (a
  redirect target that itself needs a Playwright render).
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
- **Emails**: regex over the page's visible text, filtered against a
  placeholder blocklist (`you@company.com`, `test@example.com`, image
  filenames that regex-match the email pattern, etc.) — a real false
  positive caught while testing against github.com's docs pages, which
  are full of `you@company.com`-style example snippets.
- **Phones**: two independent sources merged — regex over visible text,
  *and* `tel:` link hrefs (recovers numbers rendered as icon-only
  buttons with no visible digits at all). Both paths are validated
  against a range-list-shape rejection: a candidate like
  `"10 10-99 100-499 500"` (an employee-count bucket table on a company
  page) looks superficially phone-shaped to a naive digit-group regex,
  so any candidate containing two or more ascending `N-M` range tokens
  is rejected. A real false positive caught on a live github.com crawl.
- **Addresses / headquarters**: `<address>` tags and class/id-hinted
  location blocks, *plus* a dedicated scan for explicit
  "Registered Office" / "Head Office" / "Corporate Office" / "Branch
  Office" labels — a stronger, more explainable signal for
  headquarters-vs-branch than guessing from page type alone, and a
  near-universal convention on business/compliance pages.
- **Products / services / solutions / industries**: this is the most
  heavily-iterated part of the extractor, covered in its own subsection
  below.
- **Social links**: exact-domain match against a known list
  (LinkedIn/Twitter-X/Facebook/Instagram/YouTube/GitHub), explicitly
  excluding links back to the site's *own* domain — otherwise, crawling
  github.com itself would misreport an internal link like
  `github.com/features/actions` as a "GitHub" social profile link.

### Products / services / solutions / industries: listing-aware extraction

A plain heading scan (`<h2>`/`<h3>`/`<h4>`) works fine for a simple
company site with a static products page, but breaks down badly on
marketplace/directory-style sites and marketing-heavy SaaS sites — both
of which showed up in live testing. The extractor therefore layers two
strategies:

1. **Plain heading/list scan** (the original, simpler approach) — still
   used as a fallback when nothing more structured is found, with
   `<nav>`/`<header>`/`<footer>` explicitly excluded (otherwise every
   page's shared footer links flood every category with the same
   boilerplate — caught on a live github.com crawl, where "Products" was
   initially full of nav items like "Support" and "Company").
2. **Listing-aware extraction** (`extract_listing_items()`), used
   whenever a page is classified as products/services/solutions/
   industries, combining:
   - **Structural card detection** (`_find_card_groups()`): a purely
     shape-based detector for "repeated sibling elements sharing the
     same tag+class" — a card grid rendered from an array, regardless
     of what topic the cards are about. Each card's title is taken from
     its heading, or its first meaningful link, or its own short text,
     in that order.
   - **Taxonomy-link detection** (`extract_taxonomy_link_items()`):
     category/industry/solution names are identified by *where a link
     points* (a URL containing `categor`, `industr`, `solution`, etc.),
     not by its text — this is what distinguishes a real taxonomy
     widget from an unrelated business name sitting on the same
     results page.
   - **URL-derived taxonomy names** (`derive_taxonomy_name_from_url()`):
     a URL like `/solutions/industry/healthcare` names the industry
     directly in its own path structure (`"Healthcare"`) — a stronger
     signal than anything extractable from page text, and it works even
     on pages whose visible content is sparse or dominated by marketing
     copy. Crucially, this derived candidate is still passed through the
     *same* noise filters as everything else (a real bug found during
     testing: `/solutions/use-case` derives the literal label `"Use
     Case"`, which is boilerplate, not an actual solution — the fix was
     exposing a public `extractor.is_listing_noise()` so this path
     can't bypass filtering).
   - **Noise filtering** (`_is_listing_noise()`), the single most
     iterated function in the codebase, combining:
     - a business-entity-name heuristic (`_looks_like_entity_name()`):
       common registered-business suffixes ("Pvt Ltd", "LLP", "&
       Sons", "Industries") and an ALL-CAPS-multi-word shape check —
       filters out company names appearing where a product/solution
       name was expected (e.g. `"ALFA AQUA SOLUTION CHEM INDUSTRY"`
       showing up as a "solution" purely because a business-directory
       listing page happened to be classified that way);
     - CTA/badge phrases (both B2B-marketplace style — "Ask for
       Quote", "GST Verified" — and general SaaS style — "Start a Free
       Trial", "Contact Sales", "Book a Demo");
     - date/rating/location/metric shape checks (`"Established Since
       2017 - 9 years old"`, `"4.5 out of 5"`, `"Location KOLKATA"`,
       `"~25% increase..."`, `"1min set-up time..."`);
     - a sentence/prose-shape check (product names are short noun
       phrases, not full sentences — catches testimonial/case-study
       blurbs);
     - an imperative-verb/marketing-adjective lead-word check (real
       offering names are noun phrases, not verb-first marketing
       copy — catches `"Increase visibility and widen impact"`,
       `"Enhance patient care"`, `"Quick loan inquiry system"`);
     - a WH-question-word check (`"What is DevOps?"` is a headline, not
       an entity name);
     - `<form>`/`<select>`/`<option>`/`<label>` stripping (form fields
       and dropdown options — e.g. a full ISO country-picker dropdown —
       are never products, regardless of site);
     - self-duplication and repeated-leading-phrase detection (catches
       two distinct rendering-artifact patterns: `"3M 3M"` and
       `"Electronics & Electrical this is Electronics & Electrical
       description"`, the latter a common unfilled-CMS-template
       placeholder pattern);
     - business-role and bare-category-word blocklists (`"Manufacturer"`,
       `"Supplier"`, bare `"Services"`, bare `"Use Case"`).

   Nearly every entry in this filter set was added in direct response to
   a specific false positive observed on a real, live crawl during
   development (github.com and a business-directory platform), not
   invented speculatively — see `docs/TEST_RESULTS.md` for the full,
   dated history of what broke and how each fix was verified.

This extractor is deliberately layered and conservative rather than
trying to be exhaustive — see section 8 for exactly what was and wasn't
tested.

## 4.5 First-party vs. third-party page content

A real-world case surfaced during testing that the original design
didn't account for: on a directory/marketplace platform, some pages on
the *crawled site's own domain* describe a **completely different
company** — e.g. `boncnetwork.com/business/some-other-company` is a
listing *for* another business, hosted *on* BONC Network. Domain
matching alone cannot distinguish this from BONC's own `/about-us` page.

**Fix**: `url_utils.is_third_party_listing_url()` detects common
directory "detail page" URL conventions (`/business/`, `/listing/`,
`/vendor/`, `/supplier/`, `/member/`, `/seller/`, `/profile/`, `/biz/`)
combined with a slug-shaped remainder (hyphenated or unusually long —
distinguishing `/business/alfa-aqua-solution-chem-industry` from a
generic subpage like `/business/register`). Flagged pages:
- are still fetched and their links still followed (useful for
  discovery — the crawler doesn't just refuse to touch them),
- get a clear `page_type: "third_party_listing"` in the audit trail
  (rather than whatever generic category their own slug superficially
  resembled — e.g. not "projects" or "locations"),
- but are **excluded from `aggregate_company_info()`** entirely — their
  name, address, contact details, and any products/services/solutions/
  industries they contain never reach the target company's profile.

This is a URL-convention heuristic, not true entity resolution — see
section 10 for the honest limitation.

### Handling duplicates, conflicts, and missing information

Per-page results are merged into one `CompanyInfo` by
`aggregate_company_info()` with two different policies depending on the
field type:

- **Scalar fields** (name, description, headquarters): **first good
  candidate from the most authoritative page type wins.** For company
  name and headquarters, "about" and "contact"/"home" pages rank above
  everything else; for description, "about" ranks above "home" which
  ranks above others. Explicit "Registered Office"/"Head Office"
  candidates (section 4) are tracked separately and preferred over the
  page-type-based guess when present. This is a simple, explainable
  rule — I can point at exactly which page a field came from — rather
  than something like a voting/similarity scheme that would be harder
  to defend when asked "why did you pick that value".
- **List fields** (products, services, solutions, industries, social
  links): **union across all *first-party* pages, case-insensitive
  deduplication**, order preserved by first appearance. The same
  product name appearing on both the homepage and the dedicated
  products page is expected, not an error, so it's merged rather than
  flagged.
- **Contact details specifically** (emails/phones) are only trusted from
  pages whose *purpose* is representing the organisation itself — home,
  about, contact, locations. This was a deliberate fix after a live
  crawl of pypi.org pulled in individual package maintainers' personal
  emails from `/project/<name>` pages and (correctly, technically, but
  wrongly for the "company info" use case) attributed them to PyPI
  itself.
- **Third-party pages are excluded before any of the above runs** —
  see section 4.5. This is the primary defense against cross-company
  contamination; the noise filters above are a secondary layer for
  content that isn't caught by the URL-pattern check.
- **Missing information** is simply left as `null` / `[]` — there is no
  guessing or fabrication. `CompanyInfo.headquarters` is `null` on
  several live sample runs precisely because no crawled *first-party*
  page had a recognizable address block; that's a correct, honest
  result, not a bug to paper over.
- **Incorrectly extracted information**: rather than try to catch every
  possible false positive after the fact, the strategy throughout is to
  narrow the *source* of each field — each filter in section 4 and each
  exclusion rule in 4.5 was added in response to a specific false
  positive observed on a real, live crawl during development, not
  invented speculatively.

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
It was also confirmed on a real production site during live validation
(a business-directory platform whose entire front end is React-rendered
— every page in that crawl shows `"rendered_with": "dynamic"`).
See `tests/test_crawler_e2e.py::test_dynamic_rendering_recovers_js_injected_content`
and `output/4_dynamic_content_demo.json` for the local proof.

**When I'd use plain HTTP requests vs. a browser:**
- HTTP requests for the large majority of company marketing sites, which
  are still server-rendered (confirmed directly on github.com, pypi.org,
  and yarnpkg.com — all server-rendered, never triggering the dynamic
  fallback).
- A browser for genuinely client-rendered sites — confirmed on a live
  React-based business-directory platform, where the shell-detection
  heuristic correctly fired on effectively every page.
- Either way, the decision is made *per page*, not per site, and only
  for pages the heuristic actually flags — keeping the common case fast.

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

Every page — successful or not, first-party or not — gets a `PageRecord`
with: URL, category, title, HTTP status, whether it was fetched
successfully, an `extraction_result` (`success` / `partial` /
`partial_static_only` / `failed`), an `error` string when applicable,
`final_url` if it redirected, and `is_third_party`. This satisfies the
assignment's explicit ask to retain "whether the page was successfully
processed" for every discovered page, not just the ones that worked or
the ones that counted toward the company profile.

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
| Redirect | Followed automatically (`requests`' default); final URL recorded separately from the requested URL (section 3) so redirects are visible in the audit trail without creating duplicate page entries — verified even combined with dynamic rendering. |
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
raises out of `Crawler.crawl()` for any of the situations above — proven
with a dedicated local mock server (`tests/local_site.py`) that serves
all of these failure modes on purpose, specifically so the error
handling could be tested without depending on a real site happening to
be broken in the right way at test time.

## 8. Testing

**113 automated tests** (`pytest tests/ -v`), organized by what they
exercise:

- `test_url_utils.py` (14 tests) — normalization, dedup keys, same-site
  logic, tracking-param stripping, non-HTML/skip-path detection,
  third-party listing-URL detection.
- `test_page_classifier.py` (15 tests) — URL/content-based category
  classification, crawl-worthiness gating, priority ordering, the
  nested-industry-segment-priority fix, the blog/news-vs-taxonomy
  ordering fix.
- `test_extractor.py` (54 tests) — every extracted field against local
  HTML fixtures and hand-crafted edge cases, plus the full listing/card/
  taxonomy-aware extraction suite: real products vs. company names,
  CTAs vs. metadata, services vs. prose, industries vs. business
  listings, solutions vs. company names containing "solution", phone
  extraction (text and `tel:` links) including the range-list rejection,
  headquarters/office-label extraction, URL-derived taxonomy names
  (including the noise-filter-bypass fix), metric callouts,
  self-duplication and placeholder-template artifacts, form-field/
  dropdown stripping, WH-question and imperative-verb filtering.
- `test_aggregation.py` (7 tests) — the cross-page merge/conflict policy
  in isolation, using synthetic `ExtractedPage` objects (no network,
  no HTML parsing — purely the aggregation logic), including the
  trusted-contact-page-type restriction.
- `test_fetcher.py` (10 tests) — retries, timeouts, redirects, all the
  HTTP status codes in section 7's table, oversized pages, robots.txt,
  content-type rejection — run against an in-process mock HTTP server,
  not the real network.
- `test_crawler_e2e.py` (13 tests) — full crawls end-to-end against the
  same mock server: priority-queue behaviour, path-variant
  deprioritization, max-pages/robots.txt enforcement, dedup, the
  dynamic-rendering proof, `final_url` correctness through a combined
  redirect + dynamic-render case, and third-party page exclusion from
  aggregation (crawled and labeled, but not merged into the profile).

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
content, structured JSON output shape, and cross-company data isolation.

**What was *not* tested** (and why): actual visual rendering correctness
of Playwright output (Playwright's own test suite covers its rendering
fidelity — not something to re-test here); performance/load testing at
the 600-sites/day scale (that's a design discussion in section 9, not
something a single machine's test run could meaningfully validate);
exhaustive fuzzing of every conceivable malformed-HTML shape or every
possible marketing-copy phrasing (each noise filter targets a specific,
observed false positive rather than attempting to enumerate every
possible variant — see section 10 for what that leaves unsolved). See
`docs/TEST_RESULTS.md` for the full test run output and the real-world
extraction bugs this process caught and fixed, across multiple rounds of
live validation.

## 9. Performance and Scalability — 3 sites to 600/day

The current design (single process, synchronous `requests`, in-memory
queue) is intentionally simple and comprehensible for a small-scale demo.
Here is what would actually change to reach 600 company sites/day
(potentially tens of pages each, so tens of thousands of page fetches/day
— roughly 1 page every ~3 seconds sustained, which is easy in aggregate
but needs to not hammer any *individual* site):

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
  given company. A "% of pages flagged third-party" and "% of extracted
  fields that came from the noise-filter fallback vs. a clean match"
  metric would also be worth tracking at scale, to catch a new site
  template that's slipping past the current heuristics before it
  contaminates a large batch.
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
to go from a handful of sites to 600/day without a full rewrite of the
crawling or extraction logic that's already built and tested.

## 10. Limitations (honest accounting)

- **Heuristic extraction, not guaranteed-complete.** Company name,
  description, and address extraction are pattern-based, not a solved
  problem — a site with an unusual structure can still produce a
  partial or empty field. This is why every field defaults to `null`/`[]`
  rather than guessing, and why the assignment's own evaluation
  principle ("a solution that extracts everything from one website but
  fails on a different website is not necessarily a strong solution")
  drove most of the actual engineering effort here: multiple real, live,
  structurally different sites — including a large open-source platform
  and a real business-directory marketplace — were crawled repeatedly
  during development specifically to surface and fix extraction bugs
  (see `docs/TEST_RESULTS.md`), rather than tuning against one target
  site.
- **Subdomain scoping is a deliberate trade-off** (section 3) that could
  under-crawl a company whose "About"/"Careers" content genuinely lives
  on a different subdomain. Configurable, not hardcoded, but off by
  default for crawl-budget reasons.
- **Product/service/solution/industry extraction noise is reduced
  substantially, but not eliminated.** The listing/card-aware extraction
  and its extensive filter set (section 4) fixed every specific false
  positive found across several rounds of live testing — business
  entity names, CMS placeholder artifacts, form fields, CTAs, dates,
  ratings, metric callouts, WH-question headlines, marketing-imperative
  phrasing. What remains, observed live on github.com: short marketing
  taglines and customer-logo names on case-study cards (e.g. a card
  reading "Stripe" or a headline reading "Found means fixed") are
  structurally indistinguishable from a legitimate short product/
  solution name without genuine semantic understanding of the page's
  intent — no shape-based or keyword-based rule reliably tells them
  apart, and this project does not claim to have solved that. This is a
  genuinely open problem; each fix in this project targets a specific,
  observed false positive rather than attempting to enumerate every
  possible marketing phrasing, which would be both infeasible and prone
  to overfitting to one site's copywriting style.
- **Cross-company contamination is mitigated by URL pattern, not
  guaranteed.** `is_third_party_listing_url()` catches the common
  `/business/`, `/listing/`, `/vendor/`, `/supplier/`, `/member/`,
  `/seller/`, `/profile/`, `/biz/` directory-detail conventions
  (confirmed working correctly on a real business-directory platform
  during live testing — every third-party listing page was correctly
  flagged and excluded, while the platform's own pages were not), but a
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
- **Sandbox network restriction affected how some of this was demoed,
  not how it works.** Some development happened inside a
  network-restricted sandbox that could only reach a short allow-list of
  developer domains — the live samples from that environment
  (github.com, pypi.org, yarnpkg.com) are genuine live crawls, not
  mocks, but represent server-rendered, non-directory sites. The
  cross-company-contamination and dynamic-rendering-at-scale fixes were
  additionally validated against a real business-directory platform from
  outside that sandbox. The code itself has no dependency on either
  environment and behaves identically against any company site from a
  normal network.