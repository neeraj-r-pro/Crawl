from crawler.crawler import Crawler
from .local_site import LocalSite


def test_crawl_discovers_priority_pages_and_skips_broken_ones():
    with LocalSite() as site:
        crawler = Crawler(
            max_pages=20, max_depth=2, use_dynamic_rendering=False,
            respect_robots=True, crawl_delay=0, time_budget_seconds=30,
        )
        report = crawler.crawl(site.base_url + "/")

        fetched_urls = {p.url for p in report.pages if p.fetched_ok}
        assert site.base_url + "/" in fetched_urls
        assert site.base_url + "/about" in fetched_urls
        assert site.base_url + "/products" in fetched_urls
        assert site.base_url + "/contact" in fetched_urls

        # broken links that WERE attempted should be recorded, not silently
        # dropped, but should not crash the crawl
        failed = {p.url: p.error for p in report.pages if not p.fetched_ok}
        assert any("error404" in u for u in failed)
        assert any("error500" in u for u in failed)

        # binary.pdf is filtered out before it's ever queued (non-HTML
        # extension) -- it should never appear as an attempted page at all
        attempted_urls = {p.url for p in report.pages}
        assert not any("binary.pdf" in u for u in attempted_urls)


def test_crawl_respects_robots_disallow():
    with LocalSite() as site:
        crawler = Crawler(
            max_pages=15, max_depth=2, use_dynamic_rendering=False,
            respect_robots=True, crawl_delay=0, time_budget_seconds=30,
        )
        report = crawler.crawl(site.base_url + "/")
        disallowed_records = [p for p in report.pages if "disallowed" in p.url]
        # It's fine if it was never queued at all, or queued-and-blocked --
        # either way it must never appear as fetched_ok.
        assert all(not p.fetched_ok for p in disallowed_records)


def test_crawl_stops_at_max_pages():
    with LocalSite() as site:
        crawler = Crawler(
            max_pages=3, max_depth=3, use_dynamic_rendering=False,
            respect_robots=False, crawl_delay=0, time_budget_seconds=30,
        )
        report = crawler.crawl(site.base_url + "/")
        assert len(report.pages) <= 3
        assert report.stop_reason == "max_pages_reached"


def test_crawl_produces_populated_company_info():
    with LocalSite() as site:
        crawler = Crawler(
            max_pages=15, max_depth=2, use_dynamic_rendering=False,
            respect_robots=False, crawl_delay=0, time_budget_seconds=30,
        )
        report = crawler.crawl(site.base_url + "/")
        company = report.company
        assert company.company_name == "TestCo Solutions"
        assert "Bengaluru" in (company.headquarters or "")
        assert "support@testco.example" in company.emails or "hello@testco.example" in company.emails
        assert "Widget A" in company.products


def test_duplicate_pages_not_fetched_twice():
    with LocalSite() as site:
        crawler = Crawler(
            max_pages=15, max_depth=3, use_dynamic_rendering=False,
            respect_robots=False, crawl_delay=0, time_budget_seconds=30,
        )
        report = crawler.crawl(site.base_url + "/")
        urls = [p.url for p in report.pages]
        assert len(urls) == len(set(urls))


def test_dynamic_rendering_recovers_js_injected_content():
    """End-to-end proof that the JS-shell heuristic + Playwright fallback
    actually recovers content a static-only fetch would miss entirely.
    This is the core of the assignment's 'dynamic websites' requirement."""
    with LocalSite() as site:
        crawler = Crawler(
            max_pages=5, max_depth=1, use_dynamic_rendering=True,
            respect_robots=False, crawl_delay=0, time_budget_seconds=30,
        )
        report = crawler.crawl(site.base_url + "/spa")

        spa_page = next(p for p in report.pages if p.url == site.base_url + "/spa")
        assert spa_page.fetched_ok is True
        assert spa_page.rendered_with == "dynamic"
        assert spa_page.title == "Loading"  # <title> never changes, only body does

        assert "hello@acmejscorp.example" in report.company.emails
        assert report.company.company_name == "Acme JS Corp"


def test_report_serializes_to_json_cleanly():
    import json
    with LocalSite() as site:
        crawler = Crawler(
            max_pages=5, max_depth=1, use_dynamic_rendering=False,
            respect_robots=False, crawl_delay=0, time_budget_seconds=30,
        )
        report = crawler.crawl(site.base_url + "/")
        blob = json.dumps(report.to_dict())
        assert '"company_name"' in blob
        assert '"pages"' in blob


def test_parameterized_urls_deprioritized_but_not_blacklisted():
    """The homepage links to /about, /products, /services, /contact AND
    8 parameterized /products?categories=N variants. With a small page
    budget, the crawler should prefer the distinct, higher-value pages
    over exhausting the query-string variants of one path -- but the
    variants must still be reachable, not blacklisted outright."""
    with LocalSite() as site:
        crawler = Crawler(
            max_pages=6, max_depth=2, use_dynamic_rendering=False,
            respect_robots=False, crawl_delay=0, time_budget_seconds=30,
        )
        report = crawler.crawl(site.base_url + "/")
        fetched_urls = {p.url for p in report.pages if p.fetched_ok}

        # the distinct, high-value pages should have made it in within
        # a 6-page budget despite 8 parameterized variants competing
        assert site.base_url + "/about" in fetched_urls
        assert site.base_url + "/products" in fetched_urls
        assert site.base_url + "/services" in fetched_urls
        assert site.base_url + "/contact" in fetched_urls


def test_parameterized_variants_still_reachable_with_larger_budget():
    with LocalSite() as site:
        crawler = Crawler(
            max_pages=20, max_depth=2, use_dynamic_rendering=False,
            respect_robots=False, crawl_delay=0, time_budget_seconds=30,
        )
        report = crawler.crawl(site.base_url + "/")
        fetched_urls = {p.url for p in report.pages if p.fetched_ok}
        variant_urls = [u for u in fetched_urls if "categories=" in u]
        # not blacklisted -- with enough budget, variants do get crawled
        assert len(variant_urls) > 0


def test_final_url_recorded_correctly_through_redirect_and_dynamic_render():
    """Combines two things that each touch `final_url` independently:
    a redirect, AND the dynamic-rendering fallback -- proving the
    redirect target is still tracked correctly even when the destination
    page also needs a Playwright render."""
    with LocalSite() as site:
        crawler = Crawler(
            max_pages=5, max_depth=1, use_dynamic_rendering=True,
            respect_robots=False, crawl_delay=0, time_budget_seconds=30,
        )
        report = crawler.crawl(site.base_url + "/redirect-to-spa")

        record = next(p for p in report.pages if p.url == site.base_url + "/redirect-to-spa")
        assert record.fetched_ok is True
        assert record.final_url == site.base_url + "/spa"
        assert record.rendered_with == "dynamic"

        # a page that never redirected should have final_url == None,
        # not a fabricated value
        spa_direct = next((p for p in report.pages if p.url == site.base_url + "/spa"), None)
        if spa_direct is not None:
            assert spa_direct.final_url is None


def test_third_party_business_listing_crawled_but_excluded_from_aggregation():
    """The homepage links to /business/other-company-example -- a
    third-party listing for a DIFFERENT company on the same domain. It
    should still be fetched and recorded (for discovery/audit), flagged
    as third-party, but its name/contact/address must NOT contaminate
    the target company's aggregated profile."""
    with LocalSite() as site:
        crawler = Crawler(
            max_pages=15, max_depth=2, use_dynamic_rendering=False,
            respect_robots=False, crawl_delay=0, time_budget_seconds=30,
        )
        report = crawler.crawl(site.base_url + "/")

        # still crawled and recorded, flagged correctly
        listing_record = next(
            p for p in report.pages if "other-company-example" in p.url
        )
        assert listing_record.fetched_ok is True
        assert listing_record.is_third_party is True

        # the target site's own pages are NOT flagged third-party
        home_record = next(p for p in report.pages if p.url == site.base_url + "/")
        assert home_record.is_third_party is False

        # none of the other company's data leaked into aggregation
        company = report.company
        assert company.company_name == "TestCo Solutions"
        assert "othercompanyexample.example" not in " ".join(company.emails)
        assert not any("Chennai" in loc for loc in ([company.headquarters or ""] + company.other_locations))
        assert not any("9999 8888" in p for p in company.phones)


def test_third_party_pages_get_clear_audit_label_regardless_of_url_guess():
    """A third-party listing's page_type should read as
    "third_party_listing" for audit clarity, not whatever generic
    category its own slug happened to superficially resemble."""
    with LocalSite() as site:
        crawler = Crawler(
            max_pages=20, max_depth=2, use_dynamic_rendering=False,
            respect_robots=False, crawl_delay=0, time_budget_seconds=30,
        )
        report = crawler.crawl(site.base_url + "/")
        listing_record = next(
            p for p in report.pages if "other-company-example" in p.url
        )
        assert listing_record.page_type == "third_party_listing"
