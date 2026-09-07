"""
Browser-based fetching for JavaScript-rendered content.

Design decision: we do NOT render every page with a browser. Browser
rendering is 5-20x slower and far heavier (a real Chromium process) than
an HTTP GET, so it is used selectively:

  1. First, always fetch statically (fetcher.py / requests).
  2. Run `looks_like_js_shell()` on the static HTML. If the body is
     mostly empty (a near-bare <div id="root"></div>/<div id="app">
     with a handful of <script> tags and almost no visible text), the
     content is very likely injected client-side by React/Vue/Angular
     and the static HTML is not representative of what a user sees.
  3. Only THEN do we pay for a real browser render of that specific URL.

This keeps the common case (server-rendered / static sites, which is
most company marketing sites) fast and cheap, while still handling SPA
company sites correctly.

Playwright is an optional dependency. If it (or its browser binaries)
is not installed, `is_available()` returns False and the crawler simply
skips the dynamic-rendering step, still using whatever the static fetch
returned, and this is recorded on the page record (extraction_result:
"partial_static_only") rather than crashing the run.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

MIN_VISIBLE_TEXT_CHARS = 200
SPA_ROOT_IDS = {"root", "app", "__next", "__nuxt", "gatsby-focus-wrapper"}


def looks_like_js_shell(html: str) -> bool:
    """Heuristic: True if this HTML is probably a client-side-rendered
    shell rather than real content."""
    if not html:
        return False
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    visible_text = soup.get_text(separator=" ", strip=True)

    if len(visible_text) >= MIN_VISIBLE_TEXT_CHARS:
        return False  # plenty of real content already, no need to render

    # a near-empty body plus a known SPA mount point is a strong signal
    for root_id in SPA_ROOT_IDS:
        if soup.find(id=root_id):
            return True

    # empty-ish body with very little text and at least one script tag
    return len(visible_text) < 60


@dataclass
class DynamicFetchResult:
    url: str
    ok: bool
    html: str | None = None
    error: str | None = None


class DynamicFetcher:
    """Thin wrapper around Playwright, imported lazily so the rest of the
    system works even when Playwright / its browsers aren't installed."""

    def __init__(self, timeout_ms: int = 15000):
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._browser = None
        self._available: bool | None = None

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError:
            self._available = False
            return False
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
            self._available = True
        except Exception:
            # Playwright installed but browser binaries missing / launch
            # failed (common in restricted sandboxes) -- degrade gracefully.
            self._available = False
        return self._available

    def fetch(self, url: str, wait_for_selector: str | None = None) -> DynamicFetchResult:
        if not self.is_available():
            return DynamicFetchResult(url=url, ok=False, error="playwright_unavailable")
        try:
            page = self._browser.new_page(user_agent="CompanyInfoBot/1.0 (dynamic)")
            page.set_default_timeout(self.timeout_ms)
            page.goto(url, wait_until="networkidle")
            if wait_for_selector:
                try:
                    page.wait_for_selector(wait_for_selector, timeout=self.timeout_ms)
                except Exception:
                    pass  # best-effort; fall through and use whatever rendered
            html = page.content()
            page.close()
            return DynamicFetchResult(url=url, ok=True, html=html)
        except Exception as e:
            return DynamicFetchResult(url=url, ok=False, error=f"{type(e).__name__}: {e}")

    def close(self):
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
