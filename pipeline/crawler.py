from extraction.company import CompanyExtractor
from extraction.html_parser import HTMLParser
from crawler.http_fetcher import HTTPFetcher
from storage.repository import CompanyRepository


class CompanyCrawler:
    """Coordinate fetching, parsing, extraction, and persistence."""

    def __init__(
        self,
        fetcher: HTTPFetcher | None = None,
        parser: HTMLParser | None = None,
        extractor: CompanyExtractor | None = None,
        repository: CompanyRepository | None = None,
    ) -> None:
        self.fetcher = fetcher or HTTPFetcher()
        self.parser = parser or HTMLParser()
        self.extractor = extractor or CompanyExtractor()
        self.repository = repository or CompanyRepository()

    def crawl(self, url: str):
        """Crawl a website and persist the extracted company."""

        response = self.fetcher.fetch(url)

        if not response.success:
            raise RuntimeError(
                response.error or "Failed to fetch website"
            )

        if not response.html:
            raise RuntimeError(
                "Website returned empty HTML"
            )

        page = self.parser.parse(
            response.html,
            response.final_url or response.url,
        )

        company = self.extractor.extract(page)

        self.repository.save(company)

        return company