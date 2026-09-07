"""
Static HTTP fetching layer. Wraps `requests` with:
  - sane timeouts
  - bounded retries with backoff for transient failures
  - a page-size cap (avoid pulling multi-GB responses into memory)
  - content-type sniffing (skip non-HTML bodies even if the URL slipped
    past the extension filter, e.g. a PDF served without a .pdf suffix)
  - robots.txt awareness (best-effort; failures to fetch robots.txt do
    not block the crawl -- absence of robots.txt means "allowed")

Returns a FetchResult for every attempt, success or failure, so the
caller always has a record to store (this is what lets the crawler
report "page discovered but could not be processed" instead of silently
dropping it).
"""
from __future__ import annotations

import time
import urllib.robotparser as robotparser
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests
from requests.exceptions import RequestException, Timeout, ConnectionError as ReqConnectionError

from . import config


@dataclass
class FetchResult:
    url: str                       # final URL after redirects
    requested_url: str              # URL we asked for
    status_code: int | None
    ok: bool
    html: str | None = None
    content_type: str | None = None
    redirect_chain: list[str] = field(default_factory=list)
    error: str | None = None
    elapsed_ms: int = 0


class RobotsCache:
    """One robots.txt parser per host, fetched lazily and cached."""

    def __init__(self, session: requests.Session):
        self._session = session
        self._cache: dict[str, robotparser.RobotFileParser] = {}

    def _get_parser(self, url: str) -> robotparser.RobotFileParser:
        parsed = urlparse(url)
        host_key = f"{parsed.scheme}://{parsed.netloc}"
        if host_key in self._cache:
            return self._cache[host_key]

        rp = robotparser.RobotFileParser()
        robots_url = f"{host_key}/robots.txt"
        try:
            resp = self._session.get(robots_url, timeout=config.REQUEST_TIMEOUT)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:
                # No robots.txt (404 etc.) => everything allowed.
                rp.parse([])
        except RequestException:
            # Network failure fetching robots.txt: fail open (allow),
            # since we don't want one flaky request to block the whole
            # crawl of an otherwise-reachable site.
            rp.parse([])

        self._cache[host_key] = rp
        return rp

    def can_fetch(self, url: str) -> bool:
        try:
            rp = self._get_parser(url)
            return rp.can_fetch(config.USER_AGENT, url)
        except Exception:
            return True


class Fetcher:
    def __init__(self, respect_robots: bool = True, delay: float = config.CRAWL_DELAY_DEFAULT):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.USER_AGENT})
        self.respect_robots = respect_robots
        self.delay = delay
        self._robots = RobotsCache(self.session)
        self._last_request_time: dict[str, float] = {}

    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        last = self._last_request_time.get(host)
        if last is not None:
            wait = self.delay - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_request_time[host] = time.monotonic()

    def fetch(self, url: str) -> FetchResult:
        if self.respect_robots and not self._robots.can_fetch(url):
            return FetchResult(
                url=url, requested_url=url, status_code=None, ok=False,
                error="blocked_by_robots_txt",
            )

        self._throttle(url)

        attempt = 0
        last_exc: Exception | None = None
        while attempt <= config.MAX_RETRIES:
            attempt += 1
            start = time.monotonic()
            try:
                resp = self.session.get(
                    url,
                    timeout=config.REQUEST_TIMEOUT,
                    allow_redirects=True,
                    stream=True,  # so we can enforce the size cap before reading fully
                )
                elapsed_ms = int((time.monotonic() - start) * 1000)
                redirect_chain = [r.url for r in resp.history]
                content_type = resp.headers.get("Content-Type", "")

                if not content_type.startswith("text/html") and "xhtml" not in content_type:
                    resp.close()
                    return FetchResult(
                        url=resp.url, requested_url=url, status_code=resp.status_code,
                        ok=False, content_type=content_type,
                        redirect_chain=redirect_chain,
                        error=f"non_html_content_type:{content_type or 'unknown'}",
                        elapsed_ms=elapsed_ms,
                    )

                # Enforce size cap while streaming.
                chunks = []
                total = 0
                for chunk in resp.iter_content(chunk_size=65536):
                    total += len(chunk)
                    if total > config.MAX_PAGE_SIZE_BYTES:
                        resp.close()
                        return FetchResult(
                            url=resp.url, requested_url=url, status_code=resp.status_code,
                            ok=False, content_type=content_type,
                            redirect_chain=redirect_chain,
                            error="page_too_large", elapsed_ms=elapsed_ms,
                        )
                    chunks.append(chunk)
                html = b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")

                if resp.status_code >= 500 and attempt <= config.MAX_RETRIES:
                    # transient server error: retry
                    last_exc = RuntimeError(f"HTTP {resp.status_code}")
                    time.sleep(config.RETRY_BACKOFF * attempt)
                    continue

                ok = 200 <= resp.status_code < 300
                return FetchResult(
                    url=resp.url, requested_url=url, status_code=resp.status_code,
                    ok=ok, html=html if ok else None, content_type=content_type,
                    redirect_chain=redirect_chain,
                    error=None if ok else f"http_{resp.status_code}",
                    elapsed_ms=elapsed_ms,
                )

            except Timeout as e:
                last_exc = e
                if attempt <= config.MAX_RETRIES:
                    time.sleep(config.RETRY_BACKOFF * attempt)
                    continue
            except ReqConnectionError as e:
                last_exc = e
                if attempt <= config.MAX_RETRIES:
                    time.sleep(config.RETRY_BACKOFF * attempt)
                    continue
            except RequestException as e:
                # Non-transient (bad URL, SSL error, etc.) -- don't retry.
                last_exc = e
                break

        return FetchResult(
            url=url, requested_url=url, status_code=None, ok=False,
            error=f"{type(last_exc).__name__}: {last_exc}" if last_exc else "unknown_error",
        )
