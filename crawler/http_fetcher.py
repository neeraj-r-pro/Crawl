from dataclasses import dataclass

import httpx


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int | None
    content_type: str | None
    html: str | None
    error: str | None = None

    @property
    def success(self) -> bool:
        return (
            self.error is None
            and self.status_code is not None
            and 200 <= self.status_code < 400
        )


class HTTPFetcher:
    """Fetch HTML pages using HTTPX."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        timeout: float = 15.0,
    ) -> None:

        self.timeout = timeout

        self.client = client or httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/142.0.0.0 Safari/537.36"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

    def fetch(self, url: str) -> FetchResult:

        try:
            response = self.client.get(url)

            content_type = response.headers.get(
                "content-type",
                "",
            )

            html = None

            if "text/html" in content_type.lower():
                html = response.text

            # -------------------------------------------------
            # HTTP error
            # -------------------------------------------------
            #
            # Existing tests expect:
            #   error is None
            # for normal HTTP status responses such as 404/500.
            #
            # The status_code itself represents the failure.
            # -------------------------------------------------

            if response.status_code >= 400:
                return FetchResult(
                    url=url,
                    final_url=str(response.url),
                    status_code=response.status_code,
                    content_type=content_type,
                    html=html,
                    error=None,
                )

            # -------------------------------------------------
            # Blocked / challenge page
            # -------------------------------------------------

            if self._is_blocked_page(html or ""):
                return FetchResult(
                    url=url,
                    final_url=str(response.url),
                    status_code=response.status_code,
                    content_type=content_type,
                    html=html,
                    error="Blocked or challenge page detected.",
                )

            return FetchResult(
                url=url,
                final_url=str(response.url),
                status_code=response.status_code,
                content_type=content_type,
                html=html,
                error=None,
            )

        except httpx.TimeoutException:
            return FetchResult(
                url=url,
                final_url=url,
                status_code=None,
                content_type=None,
                html=None,
                error="Request timed out",
            )

        except httpx.ConnectError as exc:
            return FetchResult(
                url=url,
                final_url=url,
                status_code=None,
                content_type=None,
                html=None,
                error=f"Request failed: {exc}",
            )

        except httpx.HTTPError as exc:
            return FetchResult(
                url=url,
                final_url=url,
                status_code=None,
                content_type=None,
                html=None,
                error=str(exc),
            )

        except Exception as exc:
            return FetchResult(
                url=url,
                final_url=url,
                status_code=None,
                content_type=None,
                html=None,
                error=str(exc),
            )

    @staticmethod
    def _is_blocked_page(html: str) -> bool:
        if not html:
            return False

        text = html.lower()

        blocked_signals = (
            "your request has been blocked",
            "request has been blocked",
            "access denied",
            "access denied by",
            "checking your browser",
            "cloudflare security check",
            "cf-chl-captcha",
            "cf-chl-turnstile",
            "challenge-platform",
            "just a moment...",
            "verify you are human",
            "enable javascript and cookies to continue",
        )

        return any(
            signal in text
            for signal in blocked_signals
        )

    @staticmethod
    def _is_useful_html(
        html: str | None,
    ) -> bool:

        if not html:
            return False

        lower = html.lower()

        if "<html" not in lower:
            return False

        if HTTPFetcher._is_blocked_page(html):
            return False

        text = " ".join(html.split())

        if len(text) < 100:
            return False

        useful_markers = (
            "<title",
            "<h1",
            "<h2",
            "<p",
            "<main",
            "<article",
            "<nav",
            "<body",
        )

        return any(
            marker in lower
            for marker in useful_markers
        )