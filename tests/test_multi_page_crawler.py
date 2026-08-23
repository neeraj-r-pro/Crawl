from crawler.http_fetcher import FetchResult
from pipeline.crawler import CompanyCrawler


HOME_HTML = """
<html>
<head>
    <title>Acme Technologies</title>
</head>
<body>
    <h1>Acme Technologies</h1>

    <p>Enterprise software company.</p>

    <a href="/about">About</a>
    <a href="/services">Services</a>
    <a href="https://google.com">External</a>
</body>
</html>
"""


ABOUT_HTML = """
<html>
<head>
    <title>About Acme</title>
</head>
<body>
    <h1>About Us</h1>

    <p>We build software for businesses.</p>

    <a href="/">Home</a>
</body>
</html>
"""


SERVICES_HTML = """
<html>
<head>
    <title>Acme Services</title>
</head>
<body>
    <h1>Services</h1>

    <p>Cloud consulting services.</p>
</body>
</html>
"""


class FakeHTTPFetcher:
    """Fake website used for multi-page crawler tests."""

    def __init__(self):
        self.urls_fetched = []

        self.pages = {
            "https://acme.com/": HOME_HTML,
            "https://acme.com/about": ABOUT_HTML,
            "https://acme.com/services": SERVICES_HTML,
        }

    def fetch(self, url: str) -> FetchResult:
        self.urls_fetched.append(url)

        html = self.pages.get(url)

        if html is None:
            return FetchResult(
                url=url,
                final_url=url,
                status_code=404,
                content_type="text/html",
                html=None,
                error="Page not found",
            )

        return FetchResult(
            url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
            html=html,
        )


class FakeRepository:
    """Fake repository used to avoid database writes."""

    def __init__(self):
        self.saved_company = None

    def save(self, company):
        self.saved_company = company
        return company


def test_crawler_discovers_internal_pages():
    fetcher = FakeHTTPFetcher()
    repository = FakeRepository()

    crawler = CompanyCrawler(
        fetcher=fetcher,
        repository=repository,
    )

    crawler.crawl(
        "https://acme.com",
        max_pages=10,
    )

    assert "https://acme.com/" in fetcher.urls_fetched
    assert "https://acme.com/about" in fetcher.urls_fetched
    assert "https://acme.com/services" in fetcher.urls_fetched


def test_crawler_does_not_follow_external_links():
    fetcher = FakeHTTPFetcher()
    repository = FakeRepository()

    crawler = CompanyCrawler(
        fetcher=fetcher,
        repository=repository,
    )

    crawler.crawl(
        "https://acme.com",
        max_pages=10,
    )

    assert "https://google.com" not in fetcher.urls_fetched


def test_crawler_respects_max_pages():
    fetcher = FakeHTTPFetcher()
    repository = FakeRepository()

    crawler = CompanyCrawler(
        fetcher=fetcher,
        repository=repository,
    )

    crawler.crawl(
        "https://acme.com",
        max_pages=2,
    )

    assert len(fetcher.urls_fetched) == 2


def test_crawler_does_not_crawl_duplicate_urls():
    fetcher = FakeHTTPFetcher()
    repository = FakeRepository()

    crawler = CompanyCrawler(
        fetcher=fetcher,
        repository=repository,
    )

    crawler.crawl(
        "https://acme.com",
        max_pages=10,
    )

    assert fetcher.urls_fetched.count(
        "https://acme.com/"
    ) == 1