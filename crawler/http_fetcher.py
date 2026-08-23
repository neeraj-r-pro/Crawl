from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class FetchResult:
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
        )


class HTTPFetcher:
    """Fetch web pages using HTTPX."""

    def __init__(
        self,
        timeout: float = 10.0,
        max_redirects: int = 5,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.client = client

    def fetch(self, url: str) -> FetchResult:
        """Fetch a URL and return structured response information."""

        if self.client is not None:
            return self._fetch_with_client(url, self.client)

        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                max_redirects=self.max_redirects,
                headers=self._default_headers(),
            ) as client:
                return self._fetch_with_client(url, client)

        except httpx.TimeoutException:
            return self._timeout_result(url)

        except httpx.RequestError as exc:
            return self._error_result(
                url,
                f"Request failed: {exc}",
            )

    def _fetch_with_client(
        self,
        url: str,
        client: httpx.Client,
    ) -> FetchResult:
        """Perform the request using the supplied client."""

        try:
            response = client.get(url)

            return FetchResult(
                url=url,
                final_url=str(response.url),
                status_code=response.status_code,
                content_type=response.headers.get("content-type"),
                html=response.text,
            )

        except httpx.TimeoutException:
            return self._timeout_result(url)

        except httpx.RequestError as exc:
            return self._error_result(
                url,
                f"Request failed: {exc}",
            )

    @staticmethod
    def _default_headers() -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        }

    @staticmethod
    def _timeout_result(url: str) -> FetchResult:
        return FetchResult(
            url=url,
            final_url=None,
            status_code=None,
            content_type=None,
            html=None,
            error="Request timed out",
        )

    @staticmethod
    def _error_result(
        url: str,
        error: str,
    ) -> FetchResult:
        return FetchResult(
            url=url,
            final_url=None,
            status_code=None,
            content_type=None,
            html=None,
            error=error,
        )