"""
Decides what a URL / link is likely to be about, using cheap signals
(URL path, anchor text) BEFORE we fetch it, and refines the label
afterwards using the fetched page's <title>/<h1> if available.

This two-stage approach (pre-fetch guess -> post-fetch confirmation) is
what lets the crawler prioritise its queue without downloading everything.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from . import config

# A nested path segment like "/industry/healthcare" or "/industries/"
# is a MORE SPECIFIC signal than a broader keyword match elsewhere in the
# same path (e.g. "/solutions/industry/healthcare" also contains the
# substring "solution", which would otherwise win by appearing first in
# CATEGORY_KEYWORDS). Checked before the generic keyword loop so the more
# specific classification wins regardless of dict ordering.
_INDUSTRY_PATH_RE = re.compile(r"/industr(?:y|ies)(?:/|$)")


def classify_from_url(url: str, anchor_text: str = "") -> str:
    path = urlparse(url).path.lower()
    text = (anchor_text or "").lower()
    combined = f"{path} {text}"

    if path in ("", "/"):
        return "home"

    if _INDUSTRY_PATH_RE.search(path):
        return "industries"

    for category, keywords in config.CATEGORY_KEYWORDS.items():
        if category == "home":
            continue
        for kw in keywords:
            if kw and kw in combined:
                return category
    return "other"


def classify_from_content(url: str, title: str, h1: str, current_guess: str) -> str:
    """Refine the category once we've actually fetched the page. A strong
    signal in the title/h1 can override a WEAK URL-based guess (e.g. a
    page at /en/company/vision-mission with title "About Us").

    Deliberately does NOT override "home" or any already-confident guess:
    the root path is a stronger, less ambiguous signal than title text,
    and title/h1 text can coincidentally contain a category keyword that
    has nothing to do with the page's purpose (e.g. a homepage titled
    "TestCo Solutions" contains the word "solutions" in the company name
    itself, which must not reclassify the homepage as a solutions page).
    Content-based refinement is only useful for the catch-all "other"
    bucket, where the URL alone told us nothing.
    """
    if current_guess != "other":
        return current_guess

    if _INDUSTRY_PATH_RE.search(urlparse(url).path.lower()):
        return "industries"

    text = f"{title} {h1}".lower()
    for category, keywords in config.CATEGORY_KEYWORDS.items():
        if category == "home":
            continue
        for kw in keywords:
            if kw and kw in text:
                return category
    return current_guess


def is_worth_crawling(url: str) -> bool:
    """Pre-fetch gate: should we even queue this URL?"""
    from . import url_utils
    if url_utils.has_non_html_extension(url):
        return False
    if url_utils.looks_like_skip_path(url):
        return False
    return True


def priority_score(category: str, depth: int, variant_rank: int = 0) -> tuple:
    """Lower tuple sorts first in the queue (heapq-style priority).
    Priority categories are explored before 'other'/'blog_news', and
    within a category, shallower pages go first (keeps the crawl close
    to the homepage rather than wandering).

    `variant_rank` lets the crawler deprioritize additional query-string
    variants of a path it's already queued several of (e.g. the 5th
    `/filter-product-listing?categories=X`), WITHOUT blacklisting
    parameterized URLs outright -- a fresh, never-seen path at the same
    category/depth is still tried first, but once a handful of variants
    of the same path are already queued, further ones sort after other
    not-yet-seen pages rather than eating the whole page budget."""
    is_priority = category in config.PRIORITY_CATEGORIES
    return (0 if is_priority else 1, depth, variant_rank)
