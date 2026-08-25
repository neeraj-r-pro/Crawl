from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import sync_playwright


@dataclass
class BrowserFetchResult:
    url: str
    final_url: Optional[str]
    status_code: Optional[int]
    content_type: Optional[str]
    html: Optional[str]
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return (
            self.error is None
            and self.status_code is not None
            and 200 <= self.status_code < 400
            and bool(self.html)
        )


class BrowserFetcher:
    """Fetch JavaScript-rendered pages using Chromium."""

    def __init__(
        self,
        timeout: int = 30000,
    ) -> None:
        self.timeout = timeout

    def fetch(self, url: str) -> BrowserFetchResult:
        """Open a page in Chromium and return rendered HTML."""

        try:
            with sync_playwright() as playwright:

                browser = playwright.chromium.launch(
                    headless=True
                )

                page = browser.new_page(
                    user_agent=(
                        "Mozilla/5.0 "
                        "(Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 "
                        "(KHTML, like Gecko) "
                        "Chrome/120.0 Safari/537.36"
                    )
                )

                response = page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=self.timeout,
                )

                # Give client-side applications a little
                # additional time to render.
                page.wait_for_timeout(1000)

                html = page.content()

                final_url = page.url

                status_code = (
                    response.status
                    if response is not None
                    else None
                )

                content_type = (
                    response.headers.get("content-type")
                    if response is not None
                    else None
                )

                browser.close()

                return BrowserFetchResult(
                    url=url,
                    final_url=final_url,
                    status_code=status_code,
                    content_type=content_type,
                    html=html,
                )

        except Exception as exc:

            return BrowserFetchResult(
                url=url,
                final_url=None,
                status_code=None,
                content_type=None,
                html=None,
                error=f"Browser request failed: {exc}",
            )