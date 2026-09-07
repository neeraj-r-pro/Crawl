"""
Orchestrates the crawl: BFS over a priority queue, page-by-page fetch +
classify + extract, then aggregates per-page extractions into one
CompanyInfo record.

Stopping conditions (any one of these ends the crawl):
  - max_pages pages have been fetched
  - max_depth exceeded for all remaining queued URLs
  - the queue is empty (site fully discovered within scope)
  - wall-clock time budget exceeded (safety valve for slow/huge sites)

Why BFS with a priority queue rather than plain BFS or DFS:
  - Plain DFS can burn the entire page budget going deep into one
    unimportant subsection (e.g. a paginated blog) before ever reaching
    the Contact or Products pages linked from the homepage.
  - Plain BFS treats every link as equally interesting, which wastes
    fetches on footer/legal links repeated on every page.
  - A priority queue keyed on (is_relevant_category, depth) fetches the
    homepage first, then the pages most likely to contain company info
    (About/Products/Services/Contact/...), and only falls back to
    lower-value pages if budget remains.
"""
from __future__ import annotations

import heapq
import itertools
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from . import config, extractor, page_classifier, url_utils
from .dynamic_fetcher import DynamicFetcher, looks_like_js_shell
from .fetcher import Fetcher
from .models import CompanyInfo, CrawlReport, PageRecord, now_iso


class Crawler:
    def __init__(
        self,
        max_pages: int = config.MAX_PAGES_DEFAULT,
        max_depth: int = config.MAX_DEPTH_DEFAULT,
        use_dynamic_rendering: bool = True,
        respect_robots: bool = True,
        crawl_delay: float = config.CRAWL_DELAY_DEFAULT,
        time_budget_seconds: int = 180,
        verbose: bool = False,
    ):
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.use_dynamic_rendering = use_dynamic_rendering
        self.time_budget_seconds = time_budget_seconds
        self.verbose = verbose

        self.fetcher = Fetcher(respect_robots=respect_robots, delay=crawl_delay)
        self.dynamic_fetcher = DynamicFetcher() if use_dynamic_rendering else None

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[crawl] {msg}")

    def crawl(self, start_url: str) -> CrawlReport:
        start_time = time.monotonic()
        normalized_start = url_utils.normalize_url(start_url)
        if not normalized_start:
            raise ValueError(f"Invalid start URL: {start_url}")

        report = CrawlReport(
            input_url=start_url, started_at=now_iso(), max_pages_limit=self.max_pages
        )

        visited: set[str] = set()      # URLs we have popped from the queue and attempted
        queued: set[str] = set()       # URLs already enqueued (attempted or not)
        # Tracks how many query-string variants of a given path (scheme +
        # host + path, ignoring query) have already been queued, so later
        # variants of the same path can be deprioritized relative to
        # fresh, never-seen paths -- see page_classifier.priority_score.
        path_variant_counts: dict[str, int] = {}
        counter = itertools.count()  # tie-breaker so heap never compares URLs directly
        # heap items: (priority_tuple, tie_breaker, url, depth, discovered_from)
        queue: list = []
        heapq.heappush(
            queue,
            (page_classifier.priority_score("home", 0), next(counter), normalized_start, 0, None),
        )
        queued.add(normalized_start)

        per_page_extractions: list[tuple[str, "extractor.ExtractedPage"]] = []
        stop_reason = None

        while queue:
            if len(visited) >= self.max_pages:
                stop_reason = "max_pages_reached"
                break
            if time.monotonic() - start_time > self.time_budget_seconds:
                stop_reason = "time_budget_exceeded"
                break

            _, _, url, depth, discovered_from = heapq.heappop(queue)
            if url in visited:
                continue
            visited.add(url)

            page_record, extracted, links, link_base = self._process_url(
                url, depth, discovered_from, normalized_start
            )
            # A URL can be on the crawled site's own domain and still
            # describe a DIFFERENT entity entirely (e.g. a directory
            # listing's detail page for another business) -- domain
            # matching alone doesn't establish ownership. Such pages are
            # still fetched and recorded (useful for discovery/audit),
            # but their extracted content is excluded from this
            # company's aggregated profile below.
            page_record.is_third_party = url_utils.is_third_party_listing_url(url)
            if page_record.is_third_party:
                # A generic category guess ("projects", "locations", ...)
                # based on the listing's own slug is misleading here --
                # what matters for the audit trail is that this page
                # describes a DIFFERENT entity, not what topic its slug
                # superficially resembles.
                page_record.page_type = "third_party_listing"

            report.pages.append(page_record)
            report.pages_discovered += 1
            if page_record.fetched_ok:
                report.pages_fetched_ok += 1
            else:
                report.pages_failed += 1

            if extracted is not None and not page_record.is_third_party:
                per_page_extractions.append((page_record.page_type, extracted))

            if depth < self.max_depth:
                for link_url, anchor_text in links:
                    norm = url_utils.normalize_url(link_url, base=link_base)
                    if not norm or norm in visited or norm in queued:
                        continue
                    if not url_utils.is_same_site(norm, normalized_start):
                        continue
                    if not page_classifier.is_worth_crawling(norm):
                        continue
                    category = page_classifier.classify_from_url(norm, anchor_text)

                    parsed_norm = urlparse(norm)
                    path_key = f"{parsed_norm.scheme}://{parsed_norm.netloc}{parsed_norm.path}"
                    if parsed_norm.query:
                        variant_rank = path_variant_counts.get(path_key, 0)
                        path_variant_counts[path_key] = variant_rank + 1
                    else:
                        variant_rank = 0

                    heapq.heappush(
                        queue,
                        (page_classifier.priority_score(category, depth + 1, variant_rank),
                         next(counter), norm, depth + 1, url),
                    )
                    queued.add(norm)

        if stop_reason is None:
            stop_reason = "queue_exhausted"

        report.company = aggregate_company_info(normalized_start, per_page_extractions)
        report.finished_at = now_iso()
        report.stop_reason = stop_reason

        if self.dynamic_fetcher:
            self.dynamic_fetcher.close()

        return report

    def _process_url(self, url, depth, discovered_from, site_root):
        # The crawl's entry point is, by definition, the site's homepage
        # for our purposes -- regardless of what its URL path looks like
        # (e.g. a marketing site's "home" might live at /en/index or a
        # docs site's front door might be /introduction). Only the first
        # page popped at depth 0 gets this treatment; internal links that
        # happen to normalize back to the same URL later do not.
        if depth == 0:
            pre_category = "home"
        else:
            pre_category = page_classifier.classify_from_url(url)
        result = self.fetcher.fetch(url)

        if not result.ok or not result.html:
            self._log(f"FAIL  {url}  ({result.error})")
            return (
                PageRecord(
                    url=url, page_type=pre_category,
                    final_url=(result.url if result.url != url else None),
                    http_status=result.status_code,
                    fetched_ok=False, extraction_result="failed", error=result.error,
                    depth=depth, discovered_from=discovered_from,
                ),
                None,
                [],
                url,
            )

        html = result.html
        rendered_with = "static"

        if self.use_dynamic_rendering and looks_like_js_shell(html):
            self._log(f"THIN  {url}  -> attempting dynamic render")
            dyn = self.dynamic_fetcher.fetch(url)
            if dyn.ok and dyn.html:
                html = dyn.html
                rendered_with = "dynamic"
            else:
                self._log(f"      dynamic render unavailable/failed: {dyn.error}")

        soup = BeautifulSoup(html, "lxml")
        extracted = extractor.extract(html, url)

        title = extracted.title
        h1 = extracted.h1 or ""
        category = page_classifier.classify_from_content(url, title or "", h1, pre_category)

        # For pages classified as products/services/solutions/industries,
        # try the higher-precision listing-aware extraction (taxonomy
        # links + repeated card structures) and use it INSTEAD OF the
        # plain heading scan when it finds something -- it's a much
        # better fit for marketplace/directory-style pages, where a
        # single-page-of-headings assumption breaks down. Simpler sites
        # without any listing/taxonomy structure fall through to the
        # plain heading scan `extracted.heading_list_items` already
        # computed inside extractor.extract().
        if category in ("products", "services", "solutions", "industries"):
            listing_items = extractor.extract_listing_items(
                soup, category, extracted.company_name_guess
            )
            # A URL like /solutions/industry/healthcare names the industry
            # directly in its own structure -- a stronger, more reliable
            # signal than anything extractable from arbitrary page text,
            # and works even on pages whose visible content is otherwise
            # too sparse or too marketing-heavy to yield a clean result.
            url_derived = extractor.derive_taxonomy_name_from_url(url, category)
            if url_derived and url_derived.lower() not in {i.lower() for i in listing_items}:
                listing_items = [url_derived] + listing_items
            if listing_items:
                extracted.heading_list_items = listing_items

        extraction_result = "success"
        if extracted.is_thin_content:
            extraction_result = "partial_static_only" if rendered_with == "static" else "partial"

        self._log(f"OK    {url}  [{category}]  ({rendered_with})")

        page_record = PageRecord(
            url=url, page_type=category,
            final_url=(result.url if result.url != url else None),
            title=title, http_status=result.status_code, fetched_ok=True,
            extraction_result=extraction_result, depth=depth,
            rendered_with=rendered_with, discovered_from=discovered_from,
        )

        links = []
        for a in soup.find_all("a", href=True):
            links.append((a["href"], a.get_text(strip=True)))

        return page_record, extracted, links, result.url


def aggregate_company_info(site_root: str, per_page_extractions) -> CompanyInfo:
    """Merge per-page ExtractedPage records into one CompanyInfo.

    Conflict/duplication policy:
      - Scalar fields (name, description, headquarters): first good
        candidate wins, preferring extractions from more authoritative
        page types (about/contact/home) over others. This is a simple,
        explainable rule rather than a voting scheme, which matters
        because we need to be able to explain *why* a field was chosen.
      - List fields (products/services/emails/phones/etc.): union across
        all pages, case-insensitive dedup, order preserved by first
        appearance. Duplication across pages is expected and handled by
        the dedup step, not treated as an error.
    """
    company = CompanyInfo(website=site_root)

    name_priority = {"home": 0, "about": 1, "contact": 2}
    best_name = None
    best_name_rank = 99
    desc_candidates = []
    hq_candidates = []
    explicit_hq_candidates: list[str] = []
    other_locations: list[str] = []
    all_emails: set[str] = set()
    all_phones: set[str] = set()
    social_links: dict[str, str] = {}
    products, services, solutions, industries = [], [], [], []

    def dedup_extend(target: list[str], items: list[str]):
        seen = {t.lower() for t in target}
        for i in items:
            if i.lower() not in seen:
                target.append(i)
                seen.add(i.lower())

    # Emails/phones are only trusted from pages whose purpose is to
    # represent the organisation itself (home/about/contact/locations).
    # Pages like /products/<item> or /project/<name> frequently embed
    # THIRD-PARTY contact details (e.g. a package's individual maintainer
    # email on a package registry, a case-study client's contact info) --
    # pulling from every page type would silently mix those into the
    # company's own contact list.
    CONTACT_TRUSTED_TYPES = {"home", "about", "contact", "locations"}

    for page_type, ext in per_page_extractions:
        if ext.company_name_guess:
            rank = name_priority.get(page_type, 5)
            if rank < best_name_rank:
                best_name = ext.company_name_guess
                best_name_rank = rank

        if ext.meta_description:
            desc_candidates.append((page_type, ext.meta_description))

        for addr in ext.address_candidates:
            if page_type in ("contact", "about", "home") and not hq_candidates:
                hq_candidates.append(addr)
            elif addr not in other_locations:
                other_locations.append(addr)

        # Explicit "Registered Office" / "Head Office" style labels are a
        # stronger, more explainable signal than page-type guessing, so
        # they're tracked separately and preferred over the page-type
        # guess above at final assignment time (first one found wins,
        # same "first good candidate" rule as every other scalar field).
        for hq in ext.headquarters_candidates:
            if hq not in explicit_hq_candidates:
                explicit_hq_candidates.append(hq)
        for other in ext.other_location_candidates:
            if other not in other_locations:
                other_locations.append(other)

        all_emails.update(e for e in ext.emails if page_type in CONTACT_TRUSTED_TYPES)
        all_phones.update(p for p in ext.phones if page_type in CONTACT_TRUSTED_TYPES)
        for k, v in ext.social_links.items():
            social_links.setdefault(k, v)

        if page_type == "products":
            dedup_extend(products, ext.heading_list_items)
        elif page_type == "services":
            dedup_extend(services, ext.heading_list_items)
        elif page_type == "solutions":
            dedup_extend(solutions, ext.heading_list_items)
        elif page_type == "industries":
            dedup_extend(industries, ext.heading_list_items)

    company.company_name = best_name

    desc_priority = {"about": 0, "home": 1, "contact": 2}
    if desc_candidates:
        desc_candidates.sort(key=lambda pt_desc: desc_priority.get(pt_desc[0], 5))
        company.description = desc_candidates[0][1]

    company.headquarters = (
        explicit_hq_candidates[0] if explicit_hq_candidates
        else hq_candidates[0] if hq_candidates
        else None
    )
    company.other_locations = other_locations[:10]
    company.products = products[:25]
    company.services = services[:25]
    company.solutions = solutions[:25]
    company.industries = industries[:25]
    company.emails = sorted(all_emails)[:10]
    company.phones = sorted(all_phones)[:10]
    company.social_links = social_links

    return company
