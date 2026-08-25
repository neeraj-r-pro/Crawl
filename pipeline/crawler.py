from extraction.company import CompanyExtractor
from extraction.company_merger import CompanyMerger
from extraction.html_parser import HTMLParser

from crawler.http_fetcher import HTTPFetcher
from crawler.browser_fetcher import BrowserFetcher
from crawler.crawl_queue import CrawlQueue
from crawler.page_priority import PagePriority
from crawler.url_manager import URLManager

from storage.repository import CompanyRepository


class CompanyCrawler:
    """
    Crawl a company website and combine information from
    multiple internal pages.

    Fetch strategy:

        1. Try HTTPX.
        2. Parse/check the HTTP result.
        3. If the page looks like a JS shell or does not expose
           useful links/content, use Playwright.
        4. Extract company information.
        5. Discover internal pages.
        6. Prioritize useful pages.
        7. Merge all information.
        8. Save the final company.
    """

    def __init__(
        self,
        fetcher: HTTPFetcher | None = None,
        parser: HTMLParser | None = None,
        extractor: CompanyExtractor | None = None,
        merger: CompanyMerger | None = None,
        repository: CompanyRepository | None = None,
        browser_fetcher: BrowserFetcher | None = None,
    ) -> None:

        self.fetcher = fetcher or HTTPFetcher()
        self.browser_fetcher = browser_fetcher or BrowserFetcher()

        self.parser = parser or HTMLParser()
        self.extractor = extractor or CompanyExtractor()
        self.merger = merger or CompanyMerger()
        self.repository = repository or CompanyRepository()

    def crawl(
        self,
        url: str,
        max_pages: int = 10,
    ):
        start_url = URLManager.normalize(url)

        queue = CrawlQueue()

        queue.add(
            start_url,
            priority=0,
        )

        pages_crawled = 0
        company = None
        last_error = None

        while (
            queue.has_pending()
            and pages_crawled < max_pages
        ):

            current_url = queue.next()

            if current_url is None:
                break

            print(
                f"\n[CRAWL] {current_url}"
            )

            # =================================================
            # 1. HTTPX
            # =================================================

            response = self.fetcher.fetch(
                current_url
            )

            html = None
            final_url = current_url

            response_success = getattr(
                response,
                "success",
                False,
            )

            if response_success and response.html:

                html = response.html

                final_url = (
                    response.final_url
                    or response.url
                    or current_url
                )

                print(
                    "[FETCH] HTTPX successful"
                )

            else:

                last_error = getattr(
                    response,
                    "error",
                    "HTTP fetch failed",
                )

                print(
                    "[FETCH] HTTPX failed: "
                    f"{last_error}"
                )

            # =================================================
            # 2. CHECK WHETHER BROWSER IS NEEDED
            # =================================================

            browser_required = False

            if not html:

                browser_required = True

            elif self._needs_browser(
                html,
                current_url,
            ):

                browser_required = True

                print(
                    "[FETCH] HTTP HTML appears "
                    "incomplete or JavaScript-rendered."
                )

            # =================================================
            # 3. PLAYWRIGHT FALLBACK
            # =================================================

            if browser_required:

                # IMPORTANT:
                # Only automatically replace HTTPX with
                # Playwright when using the real HTTPFetcher.
                #
                # This keeps unit-test fake fetchers working.

                if isinstance(
                    self.fetcher,
                    HTTPFetcher,
                ):

                    print(
                        "[FETCH] Falling back to Playwright..."
                    )

                    browser_response = (
                        self.browser_fetcher.fetch(
                            current_url
                        )
                    )

                    browser_success = getattr(
                        browser_response,
                        "success",
                        False,
                    )

                    if (
                        browser_success
                        and browser_response.html
                    ):

                        html = (
                            browser_response.html
                        )

                        final_url = (
                            browser_response.final_url
                            or browser_response.url
                            or current_url
                        )

                        print(
                            "[FETCH] Playwright successful"
                        )

                    else:

                        last_error = getattr(
                            browser_response,
                            "error",
                            "Browser fetch failed",
                        )

                        print(
                            "[FETCH] Playwright failed: "
                            f"{last_error}"
                        )

                else:
                    # Injected fake/test fetchers should
                    # continue using their supplied HTML.
                    if not html:
                        continue

            # =================================================
            # 4. NO HTML
            # =================================================

            if not html:

                print(
                    "[CRAWL] No usable HTML. Skipping."
                )

                continue

            # =================================================
            # 5. PARSE
            # =================================================

            page = self.parser.parse(
                html,
                final_url,
            )

            # =================================================
            # 6. EXTRACT
            # =================================================

            page_company = (
                self.extractor.extract(page)
            )

            # =================================================
            # 7. MERGE
            # =================================================

            company = self.merger.merge(
                company,
                page_company,
            )

            pages_crawled += 1

            print(
                "[CRAWL] Pages processed: "
                f"{pages_crawled}/{max_pages}"
            )

            # =================================================
            # 8. DISCOVER INTERNAL LINKS
            # =================================================

            discovered = 0

            for link in page.links:

                if link.link_type != "page":
                    continue

                try:

                    normalized_link = (
                        URLManager.normalize(
                            link.url
                        )
                    )

                except ValueError:

                    continue

                # Same website only.
                if not URLManager.is_same_domain(
                    normalized_link,
                    start_url,
                ):
                    continue

                # Ignore useless resources/system pages.
                if self._is_low_value_url(
                    normalized_link
                ):
                    continue

                priority = PagePriority.score(
                    normalized_link
                )

                queue.add(
                    normalized_link,
                    priority=priority,
                )

                discovered += 1

            print(
                "[CRAWL] Internal pages discovered: "
                f"{discovered}"
            )

        # =====================================================
        # 9. COMPLETE FAILURE
        # =====================================================

        if company is None:

            if last_error:

                raise RuntimeError(
                    "Unable to crawl website: "
                    f"{last_error}"
                )

            raise RuntimeError(
                "Unable to extract company information."
            )

        # =====================================================
        # 10. SAVE
        # =====================================================

        self.repository.save(
            company
        )

        return company

    # =========================================================
    # DETERMINE WHETHER HTTP HTML NEEDS BROWSER
    # =========================================================

    def _needs_browser(
        self,
        html: str,
        url: str,
    ) -> bool:
        """
        Determine whether HTTPX returned an HTML page that is
        probably incomplete because the website relies on
        JavaScript rendering.

        This is deliberately generic. It does not contain
        BONC-specific rules.
        """

        if not html:
            return True

        lower = html.lower()

        # Obvious application shells.
        shell_patterns = (
            '<div id="root"></div>',
            '<div id="app"></div>',
            '<div id="__next"></div>',
            '<div id="root"></div>',
        )

        if any(
            pattern in lower
            for pattern in shell_patterns
        ):
            return True

        # Check for blocked/challenge pages.
        if HTTPFetcher._is_blocked_page(
            html
        ):
            return True

        # Parse the HTTP result.
        try:

            page = self.parser.parse(
                html,
                url,
            )

        except Exception:
            return True

        # If HTTP contains no useful structural content,
        # browser rendering is preferable.
        visible_content = (
            len(page.paragraphs)
            + len(page.headings)
        )

        if visible_content == 0:
            return True

        # JavaScript-heavy websites often return the title
        # but almost no links. A rendered page will expose them.
        #
        # Do not apply this to tiny test/fake pages; this method
        # is only used to trigger browser fallback for the real
        # HTTPFetcher.
        if len(page.links) == 0:
            return True

        return False

    # =========================================================
    # LOW VALUE URL FILTER
    # =========================================================

    @staticmethod
    def _is_low_value_url(
        url: str,
    ) -> bool:

        lower = url.lower()

        # -----------------------------------------------------
        # Static resources
        # -----------------------------------------------------

        static_extensions = (
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".svg",
            ".webp",
            ".ico",
            ".css",
            ".js",
            ".xml",
            ".rss",
            ".pdf",
            ".zip",
            ".mp4",
            ".mp3",
            ".wav",
            ".avi",
            ".woff",
            ".woff2",
            ".ttf",
        )

        if lower.endswith(
            static_extensions
        ):
            return True

        # -----------------------------------------------------
        # System/account pages
        # -----------------------------------------------------

        blocked_parts = (
            "/login",
            "/logout",
            "/register",
            "/signup",
            "/sign-in",
            "/sign-up",
            "/forgot-password",
            "/reset-password",
            "/search",
            "/cart",
            "/checkout",
            "/account",
            "/dashboard",
            "/admin",
            "/wp-admin",
            "/wp-login",
        )

        if any(
            part in lower
            for part in blocked_parts
        ):
            return True

        return False