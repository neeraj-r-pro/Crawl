from crawler.fetcher import Fetcher
from crawler import config
from .local_site import LocalSite


def test_successful_fetch():
    with LocalSite() as site:
        f = Fetcher(respect_robots=False, delay=0)
        result = f.fetch(site.base_url + "/")
        assert result.ok is True
        assert result.status_code == 200
        assert "TestCo" in result.html


def test_404_recorded_not_raised():
    with LocalSite() as site:
        f = Fetcher(respect_robots=False, delay=0)
        result = f.fetch(site.base_url + "/error404")
        assert result.ok is False
        assert result.status_code == 404
        assert result.error == "http_404"


def test_500_is_retried_then_recorded_failed():
    with LocalSite() as site:
        f = Fetcher(respect_robots=False, delay=0)
        result = f.fetch(site.base_url + "/error500")
        assert result.ok is False
        assert result.status_code == 500


def test_redirect_followed_and_final_url_recorded():
    with LocalSite() as site:
        f = Fetcher(respect_robots=False, delay=0)
        result = f.fetch(site.base_url + "/redirect-me")
        assert result.ok is True
        assert result.url.endswith("/about")
        assert len(result.redirect_chain) == 1


def test_non_html_content_type_rejected():
    with LocalSite() as site:
        f = Fetcher(respect_robots=False, delay=0)
        result = f.fetch(site.base_url + "/binary.pdf")
        assert result.ok is False
        assert "non_html_content_type" in result.error


def test_empty_page_still_returns_ok_result():
    with LocalSite() as site:
        f = Fetcher(respect_robots=False, delay=0)
        result = f.fetch(site.base_url + "/empty")
        assert result.ok is True
        assert result.html == ""


def test_oversized_page_rejected():
    with LocalSite() as site:
        f = Fetcher(respect_robots=False, delay=0)
        result = f.fetch(site.base_url + "/huge")
        assert result.ok is False
        assert result.error == "page_too_large"


def test_robots_txt_disallow_is_honoured():
    with LocalSite() as site:
        f = Fetcher(respect_robots=True, delay=0)
        result = f.fetch(site.base_url + "/disallowed")
        assert result.ok is False
        assert result.error == "blocked_by_robots_txt"


def test_robots_txt_can_be_ignored_when_disabled():
    with LocalSite() as site:
        f = Fetcher(respect_robots=False, delay=0)
        result = f.fetch(site.base_url + "/disallowed")
        assert result.ok is True


def test_timeout_is_handled_gracefully():
    # Use a request timeout shorter than the server's deliberate 2s sleep.
    original_timeout = config.REQUEST_TIMEOUT
    original_retries = config.MAX_RETRIES
    config.REQUEST_TIMEOUT = 0.3
    config.MAX_RETRIES = 1
    try:
        with LocalSite() as site:
            f = Fetcher(respect_robots=False, delay=0)
            result = f.fetch(site.base_url + "/slow")
            assert result.ok is False
            assert "Timeout" in (result.error or "") or "timeout" in (result.error or "").lower()
    finally:
        config.REQUEST_TIMEOUT = original_timeout
        config.MAX_RETRIES = original_retries
