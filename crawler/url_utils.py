"""
URL normalization, deduplication keys, and same-domain checks.

Design decision: two URLs that differ only in fragment, trailing slash,
default-port, case of scheme/host, or a known set of tracking query
params should be treated as the SAME page. Everything else in the query
string is kept, because on some sites query params are meaningful
(e.g. /products?category=pumps is a different page than /products).
"""
from __future__ import annotations

import posixpath
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

from . import config

# Query params that are tracking / session noise and never change page
# content -- safe to strip for the purposes of deduplication.
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "msclkid", "ref", "source", "sessionid", "sid",
}


def normalize_url(url: str, base: str | None = None) -> str | None:
    """Resolve relative URLs against `base` and normalize to a canonical form.

    Returns None for URLs we should never even consider (mailto:, tel:,
    javascript:, empty anchors).
    """
    if not url:
        return None
    url = url.strip()
    if url.startswith(("mailto:", "tel:", "javascript:", "#")):
        return None
    if base:
        url = urljoin(base, url)

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    # strip default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[: -3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[: -4]
    # strip leading "www." for the purposes of comparison? -- NO: keep it.
    # www.example.com and example.com are sometimes genuinely different
    # (different hosting/CDN), so normalization only lowercases, it does
    # not merge them. Same-domain checks below handle the common case.

    path = posixpath.normpath(parsed.path) if parsed.path else "/"
    if parsed.path.endswith("/") and path != "/":
        path += "/"
    if path == ".":
        path = "/"

    # drop tracking params, sort the rest for a stable dedup key
    q = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
         if k.lower() not in TRACKING_PARAMS]
    q.sort()
    query = urlencode(q)

    # fragments are dropped -- #section anchors are the same document
    return urlunparse((scheme, netloc, path, "", query, ""))


def registrable_domain(netloc: str) -> str:
    """Best-effort 'site identity' for same-site comparisons without an
    extra dependency: strips a single leading 'www.' label."""
    netloc = netloc.split(":")[0].lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def is_same_site(url: str, root_url: str) -> bool:
    """True if `url` belongs to the same site as `root_url`.

    Treats `example.com` and `www.example.com` as the same site (very
    common in the wild), but treats unrelated subdomains
    (blog.example.com vs example.com) as OUT of scope by default, since
    those are frequently separate systems (marketing blog CMS, careers
    portal on a different stack, etc.) that would explode the crawl.
    """
    a = registrable_domain(urlparse(url).netloc)
    b = registrable_domain(urlparse(root_url).netloc)
    return a == b


def has_non_html_extension(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in config.NON_HTML_EXTENSIONS)


def looks_like_skip_path(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(kw in path for kw in config.SKIP_PATH_KEYWORDS)


# Path segments that, on a directory/marketplace/listing site, introduce a
# DETAIL PAGE FOR ONE SPECIFIC LISTED ENTITY (a business, vendor, member,
# seller, ...) rather than the crawled site's own first-party content.
# This is the generic signal behind "domain matching alone isn't enough
# to determine ownership": boncnetwork.com/business/some-other-company
# is on the target's own domain but describes a DIFFERENT company.
THIRD_PARTY_PATH_HINTS = ("/business/", "/listing/", "/vendor/", "/supplier/",
                           "/member/", "/seller/", "/profile/", "/biz/")


def is_third_party_listing_url(url: str) -> bool:
    """True if `url` looks like a directory/marketplace detail page for
    ONE SPECIFIC listed entity, not the crawled site's own page.

    Two conditions must both hold:
      1. The path contains one of the known "detail page" segments above.
      2. What follows that segment looks like a specific entity's slug
         (contains a hyphen, or is unusually long) rather than a generic
         sub-page name -- this distinguishes
         "/business/alfa-aqua-solution-chem-industry-12345" (a listing)
         from "/business/register" or "/business/faq" (ordinary pages
         that happen to share the "/business/" prefix).

    This is a heuristic based on common directory-site URL conventions,
    not a certainty -- see docs/ARCHITECTURE.md for the honest
    limitations of this approach.
    """
    path = urlparse(url).path.lower()
    for hint in THIRD_PARTY_PATH_HINTS:
        idx = path.find(hint)
        if idx == -1:
            continue
        remainder = path[idx + len(hint):].strip("/")
        if not remainder:
            continue
        first_segment = remainder.split("/")[0]
        if "-" in first_segment or len(first_segment) > 15:
            return True
    return False
