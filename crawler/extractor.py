"""
Pulls structured fields out of a fetched page's HTML.

Extraction is heuristic and layered on purpose: the web has no fixed
schema for "company name" or "address", so every extractor here tries
several signals in order of reliability and keeps the first that works,
rather than assuming one fixed selector.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse, unquote

from bs4 import BeautifulSoup

from . import config, url_utils

EMAIL_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._%+\-]*@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
# Deliberately conservative phone regex: requires at least 7 digits total
# and typical separators, to cut down on false positives like dates or
# product codes. International-friendly (leading +, spaces, dashes, parens).
PHONE_RE = re.compile(
    r"(?<!\d)(\+?\d{1,3}[\s.-]?)?(\(?\d{2,4}\)?[\s.-]?){2,4}\d{3,4}(?!\d)"
)
IMAGE_EXT_RE = re.compile(r"\.(png|jpe?g|gif|svg|webp)$", re.I)


@dataclass
class ExtractedPage:
    title: str | None = None
    h1: str | None = None
    meta_description: str | None = None
    visible_text_sample: str | None = None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    social_links: dict[str, str] = field(default_factory=dict)
    address_candidates: list[str] = field(default_factory=list)
    headquarters_candidates: list[str] = field(default_factory=list)
    other_location_candidates: list[str] = field(default_factory=list)
    heading_list_items: list[str] = field(default_factory=list)  # candidate products/services bullets
    company_name_guess: str | None = None
    is_thin_content: bool = False


def _clean_text(s: str | None) -> str | None:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _valid_email(addr: str) -> bool:
    low = addr.lower()
    if IMAGE_EXT_RE.search(low):
        return False
    local_part, _, domain = low.partition("@")
    placeholder_domains = {
        "example.com", "example.org", "example.net", "domain.com",
        "yourcompany.com", "company.com", "yourdomain.com", "email.com",
        "sentry.io", "wixpress.com", "test.com",
    }
    placeholder_locals = {"you", "your", "user", "someone", "test", "sample", "name", "email"}
    if domain in placeholder_domains:
        return False
    if local_part in placeholder_locals:
        return False
    if low.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
        return False
    return True


def _valid_phone(candidate: str) -> bool:
    digits = re.sub(r"\D", "", candidate)
    if not (7 <= len(digits) <= 15):
        return False
    if _is_range_list_like(candidate):
        return False
    return True


def extract_phones_from_tel_links(soup: BeautifulSoup) -> list[str]:
    """`tel:` links are a much more reliable phone signal than regex over
    visible text -- the number is often rendered as an icon/button with
    no adjacent readable digits at all (e.g. a phone icon linking to
    tel:+911234567890 with no visible text), which the text-regex path
    can never see."""
    phones = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().startswith("tel:"):
            raw = unquote(href[4:]).strip()
            if raw and _valid_phone(raw):
                phones.append(raw)
    return phones


GENERIC_TITLE_WORDS = {
    "home", "homepage", "home page", "welcome", "official website",
    "official site", "contact us", "about us", "about", "products",
    "services", "solutions", "docs", "documentation", "overview",
    "index", "getting started", "loading", "loading...", "please wait",
    "untitled", "untitled document",
}


def extract_company_name(soup: BeautifulSoup, url: str) -> str | None:
    """Try, in order of trust: og:site_name -> application-name meta ->
    logo image alt text -> first <h1> (if the <title> looks generic/
    placeholder, e.g. a client-rendered app whose <title> never updates
    from "Loading...") -> <title> (trimmed of boilerplate like ' | Home')
    -> domain name as last resort."""
    og = soup.find("meta", property="og:site_name")
    if og and og.get("content"):
        return _clean_text(og["content"])

    app_name = soup.find("meta", attrs={"name": "application-name"})
    if app_name and app_name.get("content"):
        return _clean_text(app_name["content"])

    logo = soup.select_one("img[alt*=logo], img.logo, a.navbar-brand img, header img[alt]")
    if logo and logo.get("alt"):
        alt = _clean_text(logo["alt"])
        if alt and "logo" not in alt.lower():
            return alt

    title_tag = soup.find("title")
    raw_title = _clean_text(title_tag.text) if title_tag else None
    title_is_generic = raw_title is None or raw_title.lower().strip(".") in GENERIC_TITLE_WORDS

    if title_is_generic:
        h1_tag = soup.find("h1")
        if h1_tag:
            h1_text = _clean_text(h1_tag.get_text(separator=" "))
            if h1_text:
                return h1_text

    if raw_title:
        # strip common suffixes/prefixes after separators
        parts = re.split(r"\s*[|\-\u2013:]\s*", raw_title)
        if parts:
            # Heuristic: the company name is usually the longest
            # segment that isn't a generic page word like "Home".
            candidates = [p for p in parts if p.strip().lower() not in GENERIC_TITLE_WORDS]
            if candidates:
                return max(candidates, key=len).strip()
            return raw_title

    return registrable_name_from_domain(url)


def registrable_name_from_domain(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    label = host.split(".")[0]
    return label.capitalize() if label else None


def extract_meta_description(soup: BeautifulSoup) -> str | None:
    for attrs in ({"name": "description"}, {"property": "og:description"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return _clean_text(tag["content"])
    return None


def extract_emails(text: str) -> list[str]:
    found = {m.group(0) for m in EMAIL_RE.finditer(text)}
    return sorted(e for e in found if _valid_email(e))


def extract_phones(text: str) -> list[str]:
    found = set()
    for m in PHONE_RE.finditer(text):
        candidate = m.group(0).strip()
        if _valid_phone(candidate):
            found.add(candidate)
    return sorted(found)


def extract_social_links(soup: BeautifulSoup, site_root: str = "") -> dict[str, str]:
    own_domain = url_utils.registrable_domain(urlparse(site_root).netloc) if site_root else ""
    links = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        host = url_utils.registrable_domain(urlparse(href).netloc)
        if not host or host == own_domain:
            continue  # skip internal links and relative hrefs with no host
        for domain, key in config.SOCIAL_DOMAINS.items():
            if host == domain and key not in links:
                links[key] = href
    return links


def extract_address_candidates(soup: BeautifulSoup) -> list[str]:
    """Looks for <address> tags and elements whose class/id hints at an
    address/location block, plus schema.org PostalAddress microdata."""
    candidates = []

    for tag in soup.find_all("address"):
        txt = _clean_text(tag.get_text(separator=" "))
        if txt:
            candidates.append(txt)

    for tag in soup.select(
        "[class*=address], [class*=location], [id*=address], "
        "[class*=office], [id*=office], "
        "[itemtype*=PostalAddress]"
    ):
        txt = _clean_text(tag.get_text(separator=" "))
        if txt and 10 < len(txt) < 300:
            candidates.append(txt)

    # de-dup while preserving order
    seen = set()
    out = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:10]


HQ_OFFICE_KEYWORDS = (
    "registered office", "regd. office", "regd office", "regd. address",
    "head office", "corporate office", "headquarters", "registered address",
    "principal place of business",
)
OTHER_OFFICE_KEYWORDS = (
    "branch office", "branch address", "regional office", "other office",
    "office address", "additional office", "satellite office",
)


def extract_office_keyword_addresses(soup: BeautifulSoup) -> tuple[list[str], list[str]]:
    """A much stronger, generic signal for headquarters-vs-branch than
    guessing from page type alone: an explicit label like "Registered
    Office" / "Head Office" / "Branch Office" sitting next to an address,
    which is a near-universal convention on Indian company/compliance
    pages in particular, but not limited to them. Whichever element
    contains the keyword is taken as the address block (works when the
    label and the address share a container, e.g.
    `<div>Registered Office: 12 MG Road, ...</div>`).
    """
    hq, other = [], []
    seen_hq, seen_other = set(), set()

    for element in soup.find_all(string=True):
        low = element.lower()
        parent = element.parent
        if not parent:
            continue
        block = _clean_text(parent.get_text(separator=" "))
        if not block or not (10 < len(block) < 300):
            continue

        if any(kw in low for kw in HQ_OFFICE_KEYWORDS) and block not in seen_hq:
            hq.append(block)
            seen_hq.add(block)
        elif any(kw in low for kw in OTHER_OFFICE_KEYWORDS) and block not in seen_other:
            other.append(block)
            seen_other.add(block)

    return hq[:5], other[:5]


def extract_heading_list_items(soup: BeautifulSoup, company_name: str | None = None) -> list[str]:
    """Candidate product/service/solution names: text of <h2>/<h3>/<h4>
    elements and list items inside sections that look like a grid/list
    of offerings. Deliberately noisy/broad -- downstream aggregation in
    the crawler dedups and the human/consumer of the JSON can filter
    further. This is a discovery aid, not a guarantee of precision.

    Two distinct sources of noise are filtered here:

    1. Repeated site chrome (nav bars, footers, cookie banners) -- every
       page on a site shares the same footer, so without excluding it,
       "products" ends up full of footer link text like "Support" or
       "Careers" repeated verbatim across every page. Handled by working
       on a copy of the soup with <nav>/<header>/<footer> removed.

    2. Template section labels that sit in the MAIN content itself, not
       chrome -- this is common on single-page "company profile"
       templates (e.g. B2B directory listings like IndiaMART/TradeIndia,
       common for small Indian businesses), where "About Us", "Vision",
       "GST", "PAN Number", "Why Choose Us" are all just section headers
       on the same page as the real product list, not nav/footer at all.
       These can't be filtered by location, so they're filtered by
       content: an explicit blocklist of common boilerplate section
       titles, a set of prefixes for "browse/explore by X"-style widget
       titles, and a keyword list for business-registration/credential
       labels (GST, PAN, CIN, MSME, turnover, etc.) that are never
       product/service/industry names themselves.
    """
    stripped = BeautifulSoup(str(soup), "lxml")
    for tag in stripped(["nav", "header", "footer", "form", "select", "option", "label"]):
        tag.decompose()
    for tag in stripped.select(
        "[class*=nav], [class*=footer], [class*=cookie], [id*=nav], [id*=footer]"
    ):
        tag.decompose()

    items = []
    for tag in stripped.find_all(["h2", "h3", "h4"]):
        txt = _clean_text(tag.get_text(separator=" "))
        if txt and 2 <= len(txt) <= 80 and not _is_boilerplate_heading(txt, company_name):
            items.append(txt)

    for li in stripped.select("ul li, ol li"):
        txt = _clean_text(li.get_text(separator=" "))
        if txt and 2 <= len(txt) <= 80 and li.find("a") and not _is_boilerplate_heading(txt, company_name):
            items.append(txt)

    seen = set()
    out = []
    for i in items:
        key = i.lower()
        if key not in seen:
            seen.add(key)
            out.append(i)
    return out[:40]


BOILERPLATE_HEADINGS = {
    "navigation menu", "site-wide links", "additional resources",
    "frequently asked questions", "the developer newsletter", "platform",
    "ecosystem", "support", "company", "get started today", "table of contents",
    # Generic company-profile / B2B-directory template sections -- these
    # describe a PAGE SECTION, never a product/service/industry name.
    "about us", "description", "vision", "mission", "our vision", "our mission",
    "why choose us", "company details", "company profile", "company overview",
    "overview", "trade information", "company factsheet", "additional information",
    "contact us", "send inquiry", "enquire now", "get best price", "get latest price",
    "request a quote", "business type", "faq", "faqs", "testimonials", "reviews",
    "related products", "similar products", "recommended products",
    "recently viewed", "you may also like", "video", "images", "gallery",
    "documentation", "contact", "pricing", "plans & pricing", "see plans & pricing",
    # Generic B2B-directory business-role/type labels -- describe the
    # LISTING's role, never a product/service/industry/solution name.
    "manufacturer", "trader", "exporter", "importer", "wholesaler",
    "retailer", "distributor", "dealer", "service provider", "supplier",
    # Bare category-word labels -- a card/heading reading just "Services"
    # or "Products" is a generic section label, not a specific offering.
    "services", "products", "solutions", "industries", "categories",
}

# Section titles that describe a widget/CTA, not an item in the list it
# introduces -- e.g. "Explore by Industry" is the heading OF an industry
# list, not itself an industry.
GENERIC_HEADING_PREFIXES = (
    "explore by", "browse by", "shop by", "view all", "see all",
    "more about", "read more", "learn more", "find more", "share on",
    "location ", "located in", "available from", "established since",
    "established in", "established ", "read the",
)

# Business-registration / credential labels -- common on Indian B2B
# directory listings (GST, PAN, CIN, MSME/Udyam registration, etc.).
# These are compliance metadata, never a product, service, or industry.
ID_LABEL_KEYWORDS = (
    "gst", "gstin", "pan number", "pan card", "cin number", "tan number",
    "iec code", "udyam", "msme", "vat number", "tin number",
    "registration number", "license number", "annual turnover",
    "nature of business", "legal status of firm", "year of establishment",
    "number of employees",
)


def _is_boilerplate_heading(text: str, company_name: str | None = None) -> bool:
    low = text.lower().strip()
    if low in BOILERPLATE_HEADINGS:
        return True
    if low.startswith(GENERIC_HEADING_PREFIXES):
        return True
    if any(kw in low for kw in ID_LABEL_KEYWORDS):
        return True
    if company_name and low == company_name.lower().strip():
        # A heading that just repeats the company's own name (common on
        # profile-page templates) isn't itself a product/service.
        return True
    return False


# ---------------------------------------------------------------------------
# Listing/marketplace-aware extraction (products, services, solutions,
# industries on pages that render a repeated grid/list of "cards" or a
# category/filter widget, rather than plain prose headings).
# ---------------------------------------------------------------------------

# Common designators for a REGISTERED BUSINESS ENTITY's name -- a
# near-universal naming convention that essentially never appears at the
# end of a product/service/category name. Checked as a suffix.
ENTITY_NAME_SUFFIXES = (
    "pvt ltd", "pvt. ltd.", "pvt. ltd", "private limited", "limited",
    " ltd.", " ltd", "llp", "llc", "inc.", " inc", "incorporated",
    "corporation", "corp.", " corp", "industries", "industry",
    "enterprises", "enterprise", "& sons", "and sons", "trading co",
    "trading company", "group of companies", "& co", "and co",
    "brothers", "associates",
)


def _looks_like_entity_name(text: str, bucket: str | None = None) -> bool:
    """True if `text` looks like the name of a business/company entity
    rather than an actual product, service, industry, or solution name.

    Two deliberately generic (not company-specific) signals:
      1. Ends with a common business-entity designator ("Pvt Ltd",
         "Industries", "LLP", "& Sons", ...).
      2. Is fully upper-case with 3+ words -- a common rendering
         convention for business/brand names on directory-listing sites
         ("ALFA AQUA SOLUTION CHEM INDUSTRY"), whereas genuine product/
         service/category labels are conventionally Title Case or
         Sentence case ("Water Treatment Chemicals").

    The "industry"/"industries" suffix is deliberately NOT checked when
    `bucket == "industries"`, since a legitimate industry-category name
    can itself end in that word (e.g. "Automotive Industry") -- for that
    bucket specifically, the ALL-CAPS signal and the other suffixes still
    apply, but that one specific suffix would do more harm than good.

    This is a heuristic, not a certainty -- see docs/ARCHITECTURE.md for
    the honest limitations of a blocklist/heuristic approach.
    """
    low = text.lower().strip()
    suffixes = ENTITY_NAME_SUFFIXES
    if bucket == "industries":
        suffixes = tuple(s for s in suffixes if s.strip() not in ("industries", "industry"))
    if any(low.endswith(suffix) for suffix in suffixes):
        return True
    if text.isupper() and len(text.split()) >= 3:
        return True
    return False


# Phrases that show up on marketplace/listing cards but are never the
# name of the thing being listed: calls-to-action, verification badges,
# and stock/order metadata. Covers both B2B-marketplace-style CTAs
# ("Ask for Quote") and general SaaS/marketing-site CTAs ("Start a Free
# Trial") -- the underlying pattern (a card's action button/badge, not
# its title) is the same regardless of industry.
LISTING_NOISE_PHRASES = (
    "ask for quote", "ask for price", "get best price", "get latest price",
    "get quote", "request a quote", "request quote", "send inquiry",
    "send enquiry", "enquire now", "contact supplier", "contact seller",
    "contact us", "contact sales", "talk to sales", "view details",
    "view profile", "view more", "know more", "read more", "call now",
    "request callback", "book now", "add to cart", "buy now", "in stock",
    "out of stock", "moq", "min order", "minimum order quantity",
    "verified", "gst verified", "trustseal verified", "verified business",
    "verified supplier", "star supplier", "premium member", "trusted seller",
    "start a free trial", "start your free trial", "start free trial",
    "try for free", "try it free", "sign up free", "sign up now",
    "get started", "get started free", "book a demo", "schedule a demo",
    "request a demo", "watch demo", "watch a demo", "learn more",
    "explore more", "see how it works", "years old", "years experience",
)

# "1998", "Established 1998", "01/02/2024", "Jan 2024" -- dates/years are
# never a product/service/industry/solution name.
_DATE_LIKE_RE = re.compile(
    r"^(established\s*(in)?\s*)?\d{4}$"
    r"|^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$"
    r"|^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}$",
    re.IGNORECASE,
)
# "Mumbai, Maharashtra" -- a "City, State"-shaped string is a location, not
# a product/service/industry name. Generic shape check, no place-name list.
_LOCATION_LIKE_RE = re.compile(r"^[A-Z][a-zA-Z.]+(?:\s[A-Z][a-zA-Z.]+)?,\s*[A-Z][a-zA-Z]+$")
# "4.5 out of 5", "4.5/5" -- a rating, never an item name.
_RATING_LIKE_RE = re.compile(r"^\d(\.\d)?\s*(/|out of)\s*5\b", re.IGNORECASE)

# Product/service/industry/solution names are conventionally short noun
# phrases (1-6 words). A long, punctuation-heavy string with many words
# is much more likely to be a testimonial excerpt, case-study blurb, or
# other marketing prose that happened to sit inside a card/list item --
# e.g. "Read how Societe Generale tripled their releases and cut
# development time by more than half." This is a generic shape check,
# not a topic-specific one: it doesn't care WHAT the sentence is about.
_MAX_ITEM_WORDS = 9


def _looks_like_sentence_or_prose(text: str) -> bool:
    words = text.strip().split()
    if len(words) > _MAX_ITEM_WORDS:
        return True
    if text.strip().endswith((".", "!", "?")) and len(words) > 5:
        return True
    return False


# "70% less time spent...", "500k+ lines of code changed..." -- marketing
# stat callouts, never an item name. Generic shape check: starts with a
# number followed by a %/k+/m+/x-style suffix.
_METRIC_LIKE_RE = re.compile(r"^\d[\d,.]*\s*(%|k\+|m\+|x\b)", re.IGNORECASE)


def _is_self_duplicated(text: str) -> bool:
    """Catches a common rendering artifact where a card's image `alt`
    text and its adjacent visible caption both say the same thing,
    concatenated by `.get_text()` into e.g. "3M 3M" or "Ernst and Young
    Ernst and Young" -- the same word sequence repeated back-to-back.
    A generic string-shape check, not tied to any specific brand name."""
    words = text.split()
    n = len(words)
    if n >= 2 and n % 2 == 0:
        half = n // 2
        first = [w.lower() for w in words[:half]]
        second = [w.lower() for w in words[half:]]
        if first == second:
            return True
    return False


def _has_repeated_leading_phrase(text: str) -> bool:
    """A more general version of `_is_self_duplicated` for artifacts that
    aren't a clean half-and-half split -- e.g. a card whose name and
    unfilled placeholder description both got concatenated:
    "Electronics & Electrical this is Electronics & Electrical
    description". Checks whether the string's own leading 2-4 word
    phrase reappears again later in the same string."""
    words = text.split()
    if len(words) < 4:
        return False
    low_words = [w.lower() for w in words]
    for k in (2, 3, 4):
        if len(low_words) < 2 * k:
            continue
        lead = " ".join(low_words[:k])
        rest = " ".join(low_words[k:])
        if lead in rest:
            return True
    return False


# Numeric ranges written as "N-M" (e.g. "10-99", "100-499") are a common
# shape for company-size / stat-bucket tables ("10 10-99 100-499 500+"),
# never a phone number. Two or more such ascending ranges in one string
# is a strong "this is a bucket table, not digits I dialed" signal.
_RANGE_TOKEN_RE = re.compile(r"^\d{1,4}-\d{1,4}$")


def _is_range_list_like(candidate: str) -> bool:
    tokens = candidate.split()
    range_tokens = 0
    for t in tokens:
        if _RANGE_TOKEN_RE.match(t):
            lo, hi = t.split("-")
            if int(hi) > int(lo):
                range_tokens += 1
    return range_tokens >= 2


# Purely numeric text ("130", "1,234") is never a product/service/
# industry/solution name.
_PURELY_NUMERIC_RE = re.compile(r"^[\d,.\s]+$")

# Common imperative/gerund lead words for marketing taglines and activity
# descriptions ("Increase visibility...", "Refactoring and code
# migrations..."). Real product/service/solution names are conventionally
# NOUN PHRASES ("Cloud Backup", "Managed Hosting"), not verb-first
# sentences describing an action or benefit. A generic grammatical-shape
# signal, not tied to any specific company's marketing copy.
_ACTION_PHRASE_LEAD_WORDS = {
    "increase", "improve", "reduce", "streamline", "transform", "discover",
    "implement", "empower", "provide", "modernize", "stay", "unlock",
    "explore", "achieve", "drive", "simplify", "accelerate", "enable",
    "maximize", "minimize", "optimize", "scale", "power", "build",
    "create", "deliver", "ensure", "boost", "let", "tap", "find", "start",
    "get", "turn", "eliminate", "clear", "secure", "ship",
    "refactoring", "understanding", "generating", "enhancing", "supporting",
    "automating", "migrating", "maintaining", "improving",
}


def _looks_like_action_phrase(text: str) -> bool:
    words = text.strip().split()
    if not words:
        return False
    first = words[0].lower().strip(",.:;")
    return first in _ACTION_PHRASE_LEAD_WORDS and len(words) >= 2


def _is_listing_noise(text: str, bucket: str | None, company_name: str | None) -> bool:
    """Combines every noise filter that applies to a candidate pulled off
    a listing/marketplace-style page: CTA/badge phrases, dates, location
    strings, ratings, metric callouts, sentence/prose shape, business
    role labels, marketing-imperative phrasing, self-duplication
    artifacts, purely-numeric text, required-field markers, the existing
    boilerplate-heading filters, and the business-entity-name heuristic."""
    stripped_text = text.strip()
    low = stripped_text.lower()
    if any(phrase in low for phrase in LISTING_NOISE_PHRASES):
        return True
    if _DATE_LIKE_RE.match(stripped_text):
        return True
    if _LOCATION_LIKE_RE.match(stripped_text):
        return True
    if _RATING_LIKE_RE.match(stripped_text):
        return True
    if _looks_like_sentence_or_prose(stripped_text):
        return True
    if _METRIC_LIKE_RE.match(stripped_text):
        return True
    if _is_self_duplicated(stripped_text):
        return True
    if _has_repeated_leading_phrase(stripped_text):
        return True
    if _PURELY_NUMERIC_RE.match(stripped_text):
        return True
    if stripped_text.endswith("*"):
        # A trailing "*" is the near-universal convention for marking a
        # required FORM FIELD label ("First name *"), never an item name.
        return True
    if _looks_like_action_phrase(stripped_text):
        return True
    if _is_boilerplate_heading(text, company_name):
        return True
    if _looks_like_entity_name(text, bucket):
        return True
    return False


def _element_signature(tag) -> tuple:
    classes = tag.get("class") or []
    return (tag.name, tuple(sorted(classes)))


def _find_card_groups(soup: BeautifulSoup, min_group_size: int = 3) -> list[list]:
    """Finds sets of >=min_group_size sibling elements sharing the same
    tag+class signature -- a purely STRUCTURAL signal that "this is a
    repeated list of entries rendered from an array" (product cards,
    business listings, service tiles, ...), independent of what the
    entries actually say. This is what lets extraction work on listing/
    marketplace-style pages without keyword-matching the page's topic."""
    groups = []
    for parent in soup.find_all(True):
        children = [c for c in parent.find_all(recursive=False) if c.name]
        if len(children) < min_group_size:
            continue
        buckets: dict[tuple, list] = {}
        for child in children:
            if child.name in ("script", "style", "br", "hr"):
                continue
            buckets.setdefault(_element_signature(child), []).append(child)
        for members in buckets.values():
            if len(members) >= min_group_size:
                groups.append(members)
    return groups


def _card_title(card, bucket: str | None, company_name: str | None) -> str | None:
    """Best-effort single title string for one 'card' in a repeated
    listing group: prefer a heading tag, then the first meaningful link,
    then the card's own short text -- rejecting anything that matches
    the noise filters at each step."""
    heading = card.find(["h1", "h2", "h3", "h4", "h5"])
    if heading:
        txt = _clean_text(heading.get_text(separator=" "))
        if txt and 2 <= len(txt) <= 100 and not _is_listing_noise(txt, bucket, company_name):
            return txt

    for a in card.find_all("a"):
        txt = _clean_text(a.get_text(separator=" "))
        if txt and 2 <= len(txt) <= 100 and not _is_listing_noise(txt, bucket, company_name):
            return txt

    own_text = _clean_text(card.get_text(separator=" "))
    if own_text and 2 <= len(own_text) <= 100 and not _is_listing_noise(own_text, bucket, company_name):
        return own_text

    return None


def extract_listing_card_items(soup: BeautifulSoup, bucket: str | None, company_name: str | None = None) -> list[str]:
    """Pulls candidate item names out of repeated 'card' structures
    (product cards, service tiles, business listing cards, ...).

    Deliberately does NOT require a majority of cards in a group to
    yield a title. A real-world mixed listing (e.g. a marketplace page
    where most "cards" are supplier business listings and only one is
    an actual own-catalog product) can have the legitimate item as a
    minority within the group -- rejecting the whole group whenever
    most cards are noise would throw away that one real item along with
    the noise. Cards that yield nothing simply contribute nothing;
    there's no extra penalty for a group being mostly noise.
    """
    items = []
    for group in _find_card_groups(soup):
        for card in group:
            title = _card_title(card, bucket, company_name)
            if title:
                items.append(title)

    seen = set()
    out = []
    for i in items:
        key = i.lower()
        if key not in seen:
            seen.add(key)
            out.append(i)
    return out


# Href substrings that indicate a link points at a category/filter view --
# a far more reliable "this is a taxonomy entry" signal than the link's
# text content, which can't distinguish a real category from an unrelated
# business/brand name that happens to sit on the same page.
TAXONOMY_HREF_HINTS = ("categor", "industr", "sector", "solution", "/service", "tag=", "filter")

# The URL's own PATH STRUCTURE can directly name an industry/solution --
# e.g. /solutions/industry/healthcare -> "Healthcare". This is a stronger
# signal than anything extractable from page text, since it works even
# on pages whose visible content is sparse or dominated by marketing copy.
_INDUSTRY_SLUG_RE = re.compile(r"/industr(?:y|ies)/([a-z0-9][a-z0-9\-]*)", re.IGNORECASE)
# Deliberately excludes a slug of "industry"/"industries" itself, so that
# a URL like /solutions/industry/healthcare -- which also matches
# "/solutions/" as a PREFIX -- doesn't get "Industry" extracted as a
# bogus solution name; the industries-specific pattern above takes that
# case instead.
_SOLUTION_SLUG_RE = re.compile(
    r"/solutions?/(?!industr(?:y|ies)\b)([a-z0-9][a-z0-9\-]*)", re.IGNORECASE
)


def _humanize_slug(slug: str) -> str | None:
    words = [w for w in slug.split("-") if w and not w.isdigit()]
    if not words:
        return None
    return " ".join(w.capitalize() for w in words)


def derive_taxonomy_name_from_url(url: str, bucket: str) -> str | None:
    """Derives a candidate industry/solution name directly from the
    URL's path structure, e.g. /solutions/industry/financial-services ->
    "Financial Services". Only applies to the "industries" and
    "solutions" buckets, where a URL slug reliably names the thing
    itself (unlike "products"/"services", where a URL segment like
    /products/sku-4471 doesn't reliably name anything human-readable)."""
    path = urlparse(url).path
    if bucket == "industries":
        m = _INDUSTRY_SLUG_RE.search(path)
    elif bucket == "solutions":
        m = _SOLUTION_SLUG_RE.search(path)
    else:
        return None
    if not m:
        return None
    return _humanize_slug(m.group(1))


def extract_taxonomy_link_items(soup: BeautifulSoup, bucket: str | None, company_name: str | None = None) -> list[str]:
    """Category/industry/solution names identified by WHERE a link points
    (a category/filter URL), not by its text -- text-based keyword
    matching alone can't tell a real category ("Textiles") from an
    unrelated business/brand name sitting on the same listing page."""
    candidates = []
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if not any(hint in href for hint in TAXONOMY_HREF_HINTS):
            continue
        txt = _clean_text(a.get_text(separator=" "))
        if not txt or not (2 <= len(txt) <= 100):
            continue
        if _is_listing_noise(txt, bucket, company_name):
            continue
        candidates.append(txt)

    seen = set()
    out = []
    for c in candidates:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def extract_listing_items(soup: BeautifulSoup, bucket: str, company_name: str | None = None) -> list[str]:
    """Higher-precision extraction for a page already classified as
    products/services/solutions/industries: combines taxonomy-link
    detection and card-structure detection. Returns an empty list if
    neither structural signal is found, so the caller (crawler.py) can
    fall back to the plain heading scan (`extract_heading_list_items`)
    for simpler, non-listing sites -- this function is additive, not a
    replacement for the simpler case."""
    stripped = BeautifulSoup(str(soup), "lxml")
    for tag in stripped(["nav", "header", "footer", "form", "select", "option", "label"]):
        tag.decompose()
    for tag in stripped.select(
        "[class*=nav], [class*=footer], [class*=cookie], [id*=nav], [id*=footer]"
    ):
        tag.decompose()

    items = []
    items.extend(extract_taxonomy_link_items(stripped, bucket, company_name))
    items.extend(extract_listing_card_items(stripped, bucket, company_name))

    seen = set()
    out = []
    for i in items:
        key = i.lower()
        if key not in seen:
            seen.add(key)
            out.append(i)
    return out[:40]


def extract(html: str, url: str) -> ExtractedPage:
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()

    title = _clean_text(soup.find("title").text) if soup.find("title") else None
    h1_tag = soup.find("h1")
    h1 = _clean_text(h1_tag.get_text(separator=" ")) if h1_tag else None
    visible_text = _clean_text(soup.get_text(separator=" "))
    company_name_guess = extract_company_name(soup, url)

    hq_candidates, other_office_candidates = extract_office_keyword_addresses(soup)
    all_phones = sorted(set(extract_phones(visible_text or "") + extract_phones_from_tel_links(soup)))

    result = ExtractedPage(
        title=title,
        h1=h1,
        meta_description=extract_meta_description(soup),
        visible_text_sample=(visible_text[:1000] if visible_text else None),
        emails=extract_emails(html),
        phones=all_phones,
        social_links=extract_social_links(soup, site_root=url),
        address_candidates=extract_address_candidates(soup),
        headquarters_candidates=hq_candidates,
        other_location_candidates=other_office_candidates,
        heading_list_items=extract_heading_list_items(soup, company_name=company_name_guess),
        company_name_guess=company_name_guess,
        is_thin_content=(not visible_text or len(visible_text) < 200),
    )
    return result
