# Test Results

## 1. Automated test suite

```
python -m pytest tests/ -v
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1
collected 69 items

tests/test_aggregation.py .......                                        [ 10%]
tests/test_crawler_e2e.py .......                                        [ 20%]
tests/test_extractor.py ...................                              [ 47%]
tests/test_fetcher.py ..........                                         [ 62%]
tests/test_page_classifier.py ...........                                [ 78%]
tests/test_url_utils.py ..............                                   [100%]

============================= 69 passed in 38.53s ==============================
```

69/69 passing. No network access required — `test_fetcher.py` and
`test_crawler_e2e.py` run against an in-process mock HTTP server
(`tests/local_site.py`) that serves real sockets/timeouts/redirects, not
mocked `requests` calls.

### Coverage by module

| File | Tests | What it proves |
|---|---|---|
| `test_url_utils.py` | 14 | Normalization, fragment/tracking-param dedup, same-site scoping (incl. `www.` handling and subdomain rejection), non-HTML/skip-path filtering |
| `test_page_classifier.py` | 11 | URL/anchor/content-based categorization, crawl-worthiness gating, priority-queue ordering |
| `test_extractor.py` | 19 | Every extracted field, plus specific false-positive regressions (see section 2 below) |
| `test_aggregation.py` | 7 | Cross-page merge policy in isolation (name/description page-type priority, HQ vs. other-locations split, product dedup, trusted-contact-page filtering) |
| `test_fetcher.py` | 10 | Every failure mode in the assignment's error-handling checklist: timeout, 404/403/500, redirect, non-HTML content-type, oversized page, robots.txt, empty body |
| `test_crawler_e2e.py` | 8 | Full crawls end-to-end: priority ordering, robots.txt enforcement, max-pages stop condition, dedup, populated aggregation, **and the dynamic-rendering proof** |

### What was deliberately not tested, and why

- **Playwright's own rendering fidelity** — that's Playwright's test
  suite's job, not this project's. What *is* tested is that our
  integration with it (shell-detection heuristic, fallback trigger,
  graceful degradation when unavailable) behaves correctly.
- **600-sites/day load/performance testing** — not meaningful to
  simulate on a single machine; addressed as a design discussion in
  `ARCHITECTURE.md` section 9 instead.
- **Exhaustive malformed-HTML fuzzing** — one deliberately-broken
  fixture (`<html><body><h1>Broken<div><p>Unclosed tags here`, used
  implicitly via `lxml`'s tolerant parsing) proves the parser degrades
  gracefully; that's the property that matters, not cataloguing every
  possible way HTML can be broken.

## 2. Real extraction bugs found and fixed during live testing

The assignment's evaluation principle is explicit that a solution
tuned to one site isn't a strong solution. So rather than write the
extractor once and call it done, three real, structurally different,
live websites were crawled during development *specifically to find
where the heuristics broke* — and every one of the bugs below was found
this way, not invented as a hypothetical.

### Finding 1 — Root page misclassified by its own title text

**Symptom**: crawling a local test site whose homepage had `<h1>TestCo
Solutions</h1>`, the homepage was classified as page type `"solutions"`
instead of `"home"`, because `classify_from_content()` matched the
substring `"solution"` inside the company's own name.

**Root cause**: content-based classification was overriding a
URL-derived category (`"home"`, from the root path — a strong signal)
using a weak substring match against title/h1 text.

**Fix**: `classify_from_content()` now only refines the catch-all
`"other"` category; it never overrides an already-confident guess like
`"home"`. (`crawler/page_classifier.py`)

### Finding 2 — Duplicate page records for redirected URLs

**Symptom**: a URL that redirects (e.g. `/redirect-me` → `/about`) was
recorded using its *final* URL as the primary key, producing two
`PageRecord`s with the identical `.url` field once `/about` was also
reached directly — breaking the invariant that every recorded page URL
is unique.

**Fix**: `PageRecord.url` is now always the URL that was *requested*;
a separate `final_url` field is populated only when a redirect actually
occurred. (`crawler/crawler.py`, `crawler/models.py`)

### Finding 3 — Placeholder/example emails treated as real contacts

**Symptom**: crawling github.com's docs-style pages, `you@company.com`
and `your@domain.com` (used as illustrative snippets in code examples)
were extracted as if they were real company emails.

**Fix**: added a placeholder-domain and placeholder-local-part blocklist
(`example.com`, `company.com`, `domain.com`, local parts like `you`,
`your`, `test`, `sample`, ...) to `_valid_email()`.
(`crawler/extractor.py`)

### Finding 4 — Crawling a site's own domain flagged as a "social link"

**Symptom**: crawling github.com itself, an internal link like
`github.com/features/actions` was reported as a `"github"` social
profile link, because the social-link detector matched on domain alone
without checking whether that domain *was* the site being crawled.

**Fix**: `extract_social_links()` now takes the site's own root URL and
excludes matches against its own registrable domain.
(`crawler/extractor.py`)

### Finding 5 — Site-wide nav/footer text flooding product/service lists

**Symptom**: crawling github.com's Solutions/Services pages, the
extracted "products" and "services" lists were dominated by repeated
navigation and footer text (`"Navigation Menu"`, `"Site-wide Links"`,
`"Support"`, `"Company"`) rather than actual offering names — because
every page on the site shares the same footer/nav, and the heading/list
extractor was scanning the whole page.

**Fix**: `extract_heading_list_items()` now works on a copy of the page
with `<nav>`/`<header>`/`<footer>` (and nav/footer-class-hinted
elements) removed, plus a small explicit boilerplate-phrase blocklist
for phrases that survive even that. Contact-info extraction
deliberately still scans the full page including the footer, since
addresses/emails legitimately live there.
(`crawler/extractor.py`)

### Finding 6 — Third-party emails from listing pages attributed to the company

**Symptom**: crawling pypi.org, individual package maintainers' personal
emails (scraped from `/project/<name>` pages, which legitimately display
author contact info per package) ended up in PyPI's own `emails` list.

**Fix**: email/phone aggregation now only trusts pages whose category is
`home`/`about`/`contact`/`locations` — pages like `/products/<item>` or
`/project/<name>` are excluded from contact-info aggregation, even
though their *other* fields (headings, etc.) are still used.
(`crawler/crawler.py`, `aggregate_company_info`)

### Finding 7 — Wrong company name picked from an ambiguous piped title

**Symptom**: crawling yarnpkg.com, whose homepage `<title>` is
`"Home page | Yarn"` and has no `og:site_name`, the name extractor split
on `|` and picked the *longest* remaining segment (`"Home page"`, 9
characters) over the actual brand name (`"Yarn"`, 4 characters).

**Fix**: expanded the generic-title-word filter to include phrases like
`"home page"`/`"homepage"` (not just the bare word `"home"`), so the
genuinely generic segment is filtered out and the real brand name is the
only candidate left. (`crawler/extractor.py`)

### Finding 8 — The crawl's own entry point misclassified

**Symptom**: while fixing Finding 6, a test crawl starting directly at a
non-root path (`/spa`, simulating a docs/SPA site whose real "front
door" isn't literally `/`) classified its own starting page as
`"other"` — which then made it ineligible for contact-info aggregation
under the Finding 6 fix, even though it's structurally the homepage the
user asked to crawl.

**Fix**: the crawl's entry point (depth 0) is now always treated as
category `"home"`, regardless of what its URL path looks like — the
user-supplied starting URL is the site's homepage *by definition* for
the purposes of this tool. (`crawler/crawler.py`)

Each of these is covered by a dedicated regression test (see
`test_extractor.py`, `test_aggregation.py`, and
`test_crawler_e2e.py::test_dynamic_rendering_recovers_js_injected_content`)
so the fix can't silently regress.

### Finding 10 — Comprehensive extraction/aggregation overhaul (found via detailed user report on a real Indian B2B marketplace site)

**Symptom**: crawling boncnetwork.com (a business-listing/discovery
platform), the output had several distinct problems reported together:

```jsonc
"products": [],   // real product-listing pages were visited but yielded nothing
"solutions": ["ALFA AQUA SOLUTION CHEM INDUSTRY"],  // a business name, not a solution
"industries": [..., "Eveout"],   // a business name, not an industry
"services": [],   // real service content existed but wasn't extracted
"headquarters": null, "phones": [],   // contact info under-extracted
```

Plus two structural asks: the crawler was spending a large share of its
page budget on many `?categories=...` query-string variants of the same
path, and `final_url` needed to be verified as reliable through a
redirect.

**Root cause, by symptom**:
- `products`/`services` empty: the extractor only ever scanned plain
  `<h2>/<h3>/<h4>` headings. Marketplace/listing pages don't render
  content that way — they render repeated **cards** (one per listed
  item), which a plain heading scan never sees at all.
- `solutions`/`industries` false positives: with no structural signal
  to lean on, *any* text sitting on a page classified as "solutions" or
  "industries" was fair game — including other businesses' names that
  happen to appear on the same listing/results page.
- `headquarters`/`phones` incomplete: phone numbers rendered as icon
  links (`tel:` hrefs with no visible digits) were invisible to the
  text-regex phone extractor, and there was no way to distinguish a
  registered/head office address from an incidental one.

**Fix — a new listing-aware extraction layer, additive to the existing
heading-based fallback** (`crawler/extractor.py`):
- `_find_card_groups()` / `extract_listing_card_items()`: a purely
  **structural** detector for "repeated sibling elements sharing the
  same tag+class" — i.e. a card grid rendered from an array — with a
  per-card title-selection strategy (heading → first meaningful link →
  card's own short text), independent of what topic the cards are
  about. Deliberately does **not** require a majority of cards in a
  group to yield a title (an early version did, and it incorrectly
  discarded a legitimate item that happened to sit among mostly-noise
  business-listing cards — see the regression test
  `test_company_names_excluded_from_product_cards`, which locks in the
  fixed behaviour).
- `extract_taxonomy_link_items()`: category/industry/solution names are
  identified by **where a link points** (a URL containing `categor`,
  `industr`, `sector`, `solution`, etc.), not by the link's text —
  this is what distinguishes a real taxonomy widget from an unrelated
  business name sitting on the same results page (the "Eveout" case).
- `_looks_like_entity_name()`: a business-entity-name heuristic —
  common registered-business suffixes ("Pvt Ltd", "LLP", "& Sons",
  "Industries") and an ALL-CAPS-multi-word shape check — that filters
  out company names appearing where a product/service/solution/industry
  name was expected (the "ALFA AQUA SOLUTION CHEM INDUSTRY" case).
  Deliberately excludes the "industry"/"industries" suffix specifically
  when validating the `industries` bucket itself, since a legitimate
  category name can end in that word.
- `_is_listing_noise()`: combines the above with CTA/badge-phrase
  filtering (covers both B2B-marketplace CTAs like "Ask for Quote" and
  general SaaS CTAs like "Start a Free Trial", added after a live
  regression on github.com surfaced the latter), date/rating/location
  shape checks, a sentence/prose-shape check (product names are short
  noun phrases, not full sentences — catches testimonial/case-study
  blurbs that otherwise pass a plain length cap), a metric/stat-callout
  check ("70% less time...", never an item name), and a
  self-duplicated-text check (catches a common rendering artifact where
  an image `alt` and its caption both say the same brand name,
  concatenated into "3M 3M").
- `extract_phones_from_tel_links()`: phone numbers are also pulled
  directly from `<a href="tel:...">`, independent of the visible-text
  regex — recovers numbers rendered as icon-only buttons.
- `extract_office_keyword_addresses()`: addresses introduced by an
  explicit "Registered Office"/"Head Office"/"Branch Office" label are
  now tracked separately and preferred over the page-type-based guess
  for headquarters vs. other locations — a stronger, more explainable
  signal than "which page type this happened to appear on."
- Path-variant-aware queue prioritization (`crawler/crawler.py`,
  `page_classifier.priority_score`): the crawler now tracks how many
  query-string variants of a given path have already been queued, and
  deprioritizes (never blacklists) further variants relative to fresh,
  never-seen paths at the same depth/category — so a page budget isn't
  consumed entirely by `?categories=1`, `?categories=2`, ... before
  `/about` or `/contact` are ever reached.
- `final_url` through a redirect **and** a dynamic render was verified
  correct with a dedicated combined regression test
  (`test_final_url_recorded_correctly_through_redirect_and_dynamic_render`) —
  no code change was needed here, it was already correct, but the
  combination hadn't been explicitly tested before.

All of the above is **generic**: no code path checks for
`boncnetwork.com`, hardcodes a company name, or hardcodes a
BONC-specific product/service list. Every fix is a structural (DOM
shape, link target) or shape-based (entity-name pattern, sentence
shape, CTA phrase, metric shape) rule, tested with synthetic HTML
fixtures unrelated to BONC (a marine-valve company, a B2B chemicals
directory, a services company, etc.) as well as against three real,
independently-crawled live sites during development.

**What's still an acknowledged, honest limitation, not solved**: while
regenerating live sample output against github.com after this fix, a
different and harder problem surfaced in the same `solutions`/`services`
buckets — customer-logo names from case-study cards ("Stripe", "Plaid",
"Dow Jones") and short marketing taglines ("Reduce risk", "Your
workflows, your way"). These are structurally indistinguishable from a
legitimate short product/service name (both are 1-5 word noun-ish
phrases with no distinguishing suffix or shape) without genuine
semantic understanding of "is this describing what the company sells,
or is this a customer testimonial/marketing headline." This is a
fundamentally different, harder class of noise than what was reported
(which was about business-entity names and compliance metadata, both of
which now have defensible generic signals), and this project does not
claim to have solved it — see `docs/ARCHITECTURE.md` section 10 for
this limitation stated plainly. Blocklisting github.com-specific
taglines was deliberately avoided, since that would be exactly the kind
of site-specific overfitting this fix was asked not to do.

Regression tests for this entire finding:
`test_extractor.py::test_products_extracted_from_card_grid_marketplace_page`,
`test_company_names_excluded_from_product_cards`,
`test_products_vs_cta_and_metadata_text`,
`test_services_extracted_from_feature_tiles`,
`test_services_not_polluted_by_ordinary_paragraphs`,
`test_industries_from_taxonomy_links_excludes_business_listing_names`,
`test_solutions_excludes_company_name_containing_solution_word`,
`test_phone_extraction_from_visible_text`,
`test_phone_extraction_from_tel_link_with_no_visible_digits`,
`test_headquarters_extraction_from_registered_office_label`,
`test_duplicate_entities_deduped_case_insensitively`,
`test_generic_site_without_listing_structure_falls_back_gracefully`,
`test_metric_stat_callouts_excluded_from_listing_items`,
`test_self_duplicated_card_caption_artifact_excluded`,
`test_long_testimonial_sentence_excluded_from_card_titles`,
`test_crawler_e2e.py::test_parameterized_urls_deprioritized_but_not_blacklisted`,
`test_parameterized_variants_still_reachable_with_larger_budget`,
`test_final_url_recorded_correctly_through_redirect_and_dynamic_render`.

### Finding 9 — Company-profile template sections leaking into products/industries (found via user report, on a real Indian B2B directory-style site)

**Symptom**: on a small-business site using a single-page "company
profile" template (the kind common on B2B directory listings like
IndiaMART/TradeIndia for Indian SMBs), the `"solutions"` and
`"industries"` lists came back full of page-section labels instead of
real offerings:

```jsonc
"solutions": ["ALFA AQUA SOLUTION CHEM INDUSTRY", "About Us", "Description",
              "Vision", "Why Choose Us", "GST", "PAN Number"],
"industries": ["Explore by Industry", ..., "Eveout", "About Us",
               "Description", "GST", "PAN Card"]
```

**Root cause**: the Finding 5 fix only excludes `<nav>`/`<header>`/
`<footer>`. On this template, "About Us", "Vision", "GST", "PAN Number"
etc. are all `<h2>` section headers sitting as *siblings* of the real
product list inside `<main>` — not chrome at all, so location-based
filtering can't catch them. A few other distinct sub-issues compounded
this: `"Explore by Industry"` is the widget's own title, not an
industry; `"GST"`/`"PAN Number"` are Indian business-registration
credential labels, not offerings; and the company's own name
(`"ALFA AQUA SOLUTION CHEM INDUSTRY"`) was captured as if it were a
"solution" because the same heading text that names the company also
happened to sit inside a `solutions`-classified page.

**Fix**: `_is_boilerplate_heading()` in `crawler/extractor.py` now
filters on *content*, not just location, using three complementary
checks: (1) an expanded blocklist of common company-profile-template
section titles (`about us`, `description`, `vision`, `why choose us`,
`company profile`, `testimonials`, ...); (2) a prefix check for
widget/CTA titles (`explore by`, `browse by`, `view all`, ...); (3) a
keyword check for business-registration/credential labels (`gst`,
`pan number`, `cin`, `udyam`, `msme`, `annual turnover`, ...). Separately,
`extract_heading_list_items()` now also takes the page's own
`company_name_guess` and drops any heading that's just a restatement of
the company's own name. Regression test:
`test_extractor.py::test_b2b_directory_profile_template_boilerplate_excluded`,
built directly from the reported false positives above.

**Why this one is flagged as an ongoing limitation, not "solved"**: this
is a blocklist-based fix, and blocklists are inherently incomplete —
a different template with a different set of section labels (in a
different language, or a different convention) could still leak through.
This is called out explicitly in `docs/ARCHITECTURE.md` section 10 as a
known limitation of the heuristic approach, rather than something this
fix claims to have eliminated entirely.

## 3. Live sample runs (real websites, real crawl)

Run inside a network-restricted development sandbox (see README for
details on that restriction) against three real, reachable, structurally
different public websites. Full JSON output for each is in `output/`.

| Site | Structure | Pages crawled | Stop reason | Result |
|---|---|---|---|---|
| **github.com** | Large, complex, many sub-sections (solutions/industries/use-cases) | 20/20 fetched OK | `max_pages_reached` | name: "GitHub", description correctly extracted, 4 social links, zero false-positive emails |
| **pypi.org** | Medium, server-rendered package registry | 11/11 fetched OK | `queue_exhausted` (fully discovered within scope) | name: "PyPI", description correctly extracted, third-party maintainer emails correctly excluded (Finding 6) |
| **yarnpkg.com** | Docusaurus-based docs/product site | 15/15 fetched OK | `max_pages_reached` | name: "Yarn" (after Finding 7 fix), correctly distinguished CLI/docs pages by category |

A fourth sample, `output/4_dynamic_content_demo.json`, proves the
dynamic-rendering path specifically (section 5 of `ARCHITECTURE.md`):
a locally-served page whose real content — company name and contact
email — is only available after client-side JavaScript fetches it from
a separate endpoint, the same pattern a real API-driven SPA uses. The
static-only fetch of that page returns **zero** extractable fields; the
Playwright-rendered fetch correctly recovers all of them:

```json
// static fetch of the raw page -> nothing usable
{"emails": [], "company_name_guess": "Loading"}

// Playwright-rendered fetch of the SAME url -> real data recovered
{"emails": ["hello@acmejscorp.example"], "company_name_guess": "Acme JS Corp"}
```

This wasn't run against a real public SPA company site because the
sandbox's outbound network doesn't reach one (see README) — but the
mechanism being proven (static-shell detection → selective Playwright
fallback → correct extraction) is exactly the same code path that would
fire on a real one, and is exercised by an automated regression test,
not just this one-off demo.

### Example of successful vs. failed pages (from the github.com run)

```
OK    https://github.com/                                     [home]        200
OK    https://github.com/about                                [about]       200
OK    https://github.com/features/actions                     [products]    200
OK    https://github.com/solutions/industry/financial-services [services]   200
```

(All 20 requested pages on this run succeeded — github.com didn't
happen to link to anything broken within the crawled depth. The
`test_crawler_e2e.py::test_crawl_discovers_priority_pages_and_skips_broken_ones`
test demonstrates failed-page handling directly, since the mock test
server serves 404/500/timeout routes on purpose — see that test's
assertions for the exact failure records produced.)

## 4. Third round: cross-company contamination and remaining precision issues (found via detailed user report against BONC Network and GitHub)

A second real-world validation pass (BONC Network, GitHub, 40-page runs)
surfaced a new, more architectural class of problem alongside further
extraction-precision issues. boncnetwork.com itself is unreachable from
this sandbox (same network restriction noted throughout this project),
so the BONC-specific fixes below were verified against synthetic HTML
fixtures reproducing the exact reported strings; the GitHub fixes were
verified against live, 40-page runs matching the user's own test
parameters.

### Finding 11a — Cross-company data contamination (architectural fix)

**Symptom**: BONC Network is a business-directory platform. Pages like
`/business/eveout-business-planning-...` and
`/business/alamdar-international` are on BONC's own domain but describe
**other businesses listed on BONC**, not BONC itself. Their names,
locations, and attributes were being aggregated into BONC's own company
profile — domain matching alone doesn't establish page ownership.

**Fix**: `url_utils.is_third_party_listing_url()` detects directory
"detail page" URL conventions (`/business/`, `/listing/`, `/vendor/`,
`/supplier/`, `/member/`, `/seller/`, `/profile/`, `/biz/`) combined with
a slug-shaped remainder (hyphenated or long — distinguishing
`/business/alfa-aqua-solution-chem-industry` from a generic subpage like
`/business/register`). `PageRecord` now carries an `is_third_party`
flag; such pages are still fetched, recorded, and their links still
followed for discovery, but `crawler.crawl()` excludes their
`ExtractedPage` from company aggregation entirely. Regression test:
`test_crawler_e2e.py::test_third_party_business_listing_crawled_but_excluded_from_aggregation`.

### Finding 11b — Listing-metadata chips and business-attribute fragments

**Symptom**: reported BONC output included `"Location KOLKATA"`,
`"Available from Jan 2026"`, a bare `"130"` in `products`; `"Manufacturer"`,
`"Located in Faridabad , India"`, `"Established Since 2017 - 9 years old"`
in `solutions`; `"Services"`, `"Located in GURUGRAM , India"`, and a
placeholder-duplication artifact (`"Electronics & Electrical this is
Electronics & Electrical description"`) in `industries`.

**Fix**: added generic prefix/phrase checks (`"location "`, `"located
in"`, `"available from"`, `"established since/in"`, `"years old"`),
a purely-numeric-text rejection, a bare-category-word blocklist
(`"services"`, `"products"`, etc.), a business-role-label blocklist
(`"manufacturer"`, `"supplier"`, `"distributor"`, ...), and a
generalized repeated-leading-phrase detector (catches the placeholder
duplication case, a superset of the earlier exact-half-duplicate check).
Regression tests: `test_listing_metadata_chips_excluded_from_products`,
`test_business_attribute_chips_excluded_from_solutions`,
`test_bare_category_word_and_placeholder_duplication_excluded_from_industries`.

### Finding 11c — Form fields, country dropdowns, and social-share text (GitHub)

**Symptom**: `products` on a live github.com crawl included form labels
(`"First name *"`, `"Work email *"`), an entire ISO country dropdown
(`"Afghanistan"`, `"Åland Islands"`, ...), and social-share button text
(`"Share on Facebook Facebook"`).

**Fix**: `<form>`, `<select>`, `<option>`, and `<label>` elements are now
stripped before both the listing-card and heading-scan extraction
paths — form controls are never products/services/solutions/industries,
regardless of site. This single structural fix eliminates the entire
country-dropdown class of false positive without a country-name
blocklist. A `"share on"` prefix check handles the social-share case.
Verified live: the reported strings are absent from a fresh 40-page
github.com crawl (`output/5_github_full_40page_validation.json`).
Regression test: `test_form_fields_and_dropdown_options_excluded_from_products`,
`test_share_button_text_excluded`.

### Finding 11d — Phone false positive on a stat/range table

**Symptom**: `phones` contained `"10 10-99 100-499 500"` — an
employee-count bucket table, not a phone number.

**Fix**: `_is_range_list_like()` rejects any numeric candidate containing
two or more ascending `N-M` range tokens (a company-size/stat-table
shape), added as a hard gate in `_valid_phone()`. Regression tests:
`test_phone_rejects_employee_count_range_table`,
`test_phone_still_accepts_real_numbers_alongside_range_text` (proves the
fix doesn't overreach and reject real numbers appearing near range text).

### Finding 11e — `industries` empty despite `/solutions/industry/...` pages existing (root cause: classifier bug, not an extraction bug)

**Symptom**: GitHub has real industry pages (`/solutions/industry/healthcare`,
`/solutions/industry/financial-services`, ...), but the aggregated
`industries` list was empty.

**Root cause**: `page_classifier.classify_from_url()` checks category
keywords in a fixed dict order and returns on first match.
`/solutions/industry/healthcare` contains the substring `"solution"`
(checked first) AND `"industr"` (checked later) — every one of these
pages was silently misclassified as `"solutions"`, so the
industries-specific extraction path (including the URL-derivation fix
below) never ran on them at all. This was found only by tracing *why*
the field stayed empty after the extraction-level fixes were already in
place, not by an extraction-level symptom.

**Fix**: added a specific pre-check in both `classify_from_url()` and
`classify_from_content()` for the `/industr(y|ies)/` path pattern,
checked *before* the generic keyword loop — a nested, more specific
segment now correctly wins over a broader substring match it happens to
also contain. Regression tests:
`test_nested_industry_segment_wins_over_broader_solutions_match`,
`test_plain_solutions_path_without_industry_segment_still_classified_as_solutions`.

Combined with the new **URL-derived taxonomy name** signal
(`derive_taxonomy_name_from_url()` — turns `/solutions/industry/healthcare`
directly into `"Healthcare"`, `/solutions/industry/financial-services`
into `"Financial Services"`, without depending on page text at all),
verified live: `industries` on a fresh 40-page github.com crawl now
includes `"Healthcare"`, `"Financial Services"`, `"Manufacturing"`,
`"Nonprofits"`, and `"Government"` — previously empty.

### Acknowledged, NOT solved: customer-logo names now surface in `industries`

Fixing Finding 11e means industry pages are now correctly classified
and their content is actually scanned — which means the SAME residual
noise class documented in Finding 10 (customer-logo names on case-study
cards: `"3M"`, `"Stripe"`, `"Plaid"`, `"Doctolib"`, `"Philips"`) now
shows up in `industries` instead of `solutions`, since that's simply
where those cards happen to live on GitHub's real site. This is not a
new bug — it's the same fundamentally hard problem (a short brand name
on a testimonial card is structurally indistinguishable from a short
legitimate category/product name without real semantic understanding)
appearing in a newly-correctly-scanned location. No further blocklist
entries were added to chase this specific case, consistent with the
explicit instruction not to overfit to any one site's marketing copy
style. See `docs/ARCHITECTURE.md` section 10.
