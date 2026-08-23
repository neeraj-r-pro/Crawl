from extraction.company import CompanyExtractor
from extraction.company_merger import CompanyMerger
from extraction.html_parser import HTMLParser
from crawler.http_fetcher import HTTPFetcher
from storage.repository import CompanyRepository
from crawler.crawl_queue import CrawlQueue
from crawler.url_manager import URLManager

class CompanyCrawler:
    """Coordinate fetching, parsing, extraction, and persistence."""

    def __init__(
        self,
        fetcher: HTTPFetcher | None = None,
        parser: HTMLParser | None = None,
        extractor: CompanyExtractor | None = None,
        merger: CompanyMerger | None = None,
        repository: CompanyRepository | None = None,
    ) -> None:
        self.fetcher = fetcher or HTTPFetcher()
        self.parser = parser or HTMLParser()
        self.extractor = extractor or CompanyExtractor()
        self.merger = merger or CompanyMerger()
        self.repository = repository or CompanyRepository()

    def crawl(
        self,
        url: str,
        max_pages: int = 10,
    ):
        """Crawl multiple pages within the same domain."""

        start_url = URLManager.normalize(url)

        queue = CrawlQueue()
        queue.add(start_url)

        pages_crawled = 0
        company = None

        while queue.has_pending() and pages_crawled < max_pages:
            current_url = queue.next()

            if current_url is None:
                break

            response = self.fetcher.fetch(current_url)

            if not response.success:
                continue

            if not response.html:
                continue

            final_url = response.final_url or response.url

            page = self.parser.parse(
                response.html,
                final_url,
            )

            page_company = self.extractor.extract(page)

            company = self.merger.merge(
                company,
                page_company,
            )

            pages_crawled += 1

            for link in page.links:
                if link.link_type != "page":
                    continue

                try:
                    normalized_link = URLManager.normalize(
                        link.url
                    )
                except ValueError:
                    continue

                if URLManager.is_same_domain(
                    normalized_link,
                    start_url,
                ):
                    queue.add(normalized_link)

        if company is None:
            raise RuntimeError(
                "Unable to extract company information."
            )

        self.repository.save(company)

        return company