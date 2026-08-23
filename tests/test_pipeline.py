from crawler.http_fetcher import FetchResult
from pipeline.crawler import CompanyCrawler


HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Acme Technologies | Software</title>

    <meta
        name="description"
        content="Acme provides enterprise software solutions."
    >

    <meta
        property="og:site_name"
        content="Acme Technologies"
    >

    <meta
        property="og:description"
        content="Enterprise software for modern businesses."
    >
</head>

<body>

    <h1>Acme Technologies</h1>

    <p>
        Contact us at sales@acme.com
    </p>

    <a href="tel:+919876543210">
        Call us
    </a>

</body>
</html>
"""


class FakeHTTPFetcher:
    """Fake fetcher used to test the pipeline without the internet."""

    def fetch(self, url: str) -> FetchResult:
        return FetchResult(
            url=url,
            final_url="https://acme.com/",
            status_code=200,
            content_type="text/html",
            html=HTML,
        )


class FakeCompanyRepository:
    """Fake repository used to test pipeline persistence."""

    def __init__(self):
        self.saved_company = None

    def save(self, company):
        self.saved_company = company
        return company


def test_company_crawler_builds_company():
    repository = FakeCompanyRepository()

    crawler = CompanyCrawler(
        repository=repository,
    )

    crawler.fetcher = FakeHTTPFetcher()

    company = crawler.crawl(
        "https://acme.com"
    )

    assert company.name == "Acme Technologies"

    assert str(company.website) == (
        "https://acme.com/"
    )

    assert company.description == (
        "Enterprise software for modern businesses."
    )

    assert company.contact.emails == [
        "sales@acme.com"
    ]

    assert company.contact.phone_numbers == [
        "+919876543210"
    ]

    assert repository.saved_company is company


def test_company_crawler_uses_visible_paragraph_for_description():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Example Domain</title>
    </head>

    <body>
        <h1>Example Domain</h1>

        <p>
            This domain is for use in documentation examples
            without needing permission. Avoid use in operations.
        </p>
    </body>
    </html>
    """

    class ExampleHTTPFetcher:
        def fetch(self, url: str) -> FetchResult:
            return FetchResult(
                url=url,
                final_url="https://example.com/",
                status_code=200,
                content_type="text/html",
                html=html,
            )

    repository = FakeCompanyRepository()

    crawler = CompanyCrawler(
        repository=repository,
    )

    crawler.fetcher = ExampleHTTPFetcher()

    company = crawler.crawl(
        "https://example.com"
    )

    assert company.name == "Example Domain"

    assert company.description == (
        "This domain is for use in documentation examples "
        "without needing permission. Avoid use in operations."
    )

    assert repository.saved_company is company