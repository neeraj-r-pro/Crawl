"""
Central configuration and tunables for the crawler.

Kept in one place so behaviour (limits, keyword lists, timeouts) can be
adjusted without touching logic in the other modules.
"""

USER_AGENT = "CompanyInfoBot/1.0 (+contact: assignment-crawler; respects robots.txt)"

REQUEST_TIMEOUT = 10          # seconds, per HTTP request
MAX_RETRIES = 2                # retries for transient failures (timeout/connection/5xx)
RETRY_BACKOFF = 1.5            # seconds, exponential backoff base

MAX_PAGES_DEFAULT = 40         # hard ceiling on pages fetched per site
MAX_DEPTH_DEFAULT = 3          # BFS depth from the homepage
MAX_PAGE_SIZE_BYTES = 5_000_000  # skip / truncate anything bigger than ~5MB
CRAWL_DELAY_DEFAULT = 0.5      # politeness delay between requests to the same host

# File extensions that are never worth fetching as "pages" -- we still may
# record that we saw the link, but we don't download the bytes.
NON_HTML_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".mp4", ".mp3", ".avi", ".mov", ".wav",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".css", ".js", ".json", ".xml", ".rss", ".woff", ".woff2", ".ttf", ".eot",
}

# URL path / query patterns that are almost never useful for company-info
# extraction and are common crawl traps (pagination, filters, auth walls,
# ecommerce noise, etc). Matched case-insensitively against the path.
SKIP_PATH_KEYWORDS = {
    "login", "signin", "sign-in", "signup", "sign-up", "register",
    "cart", "checkout", "wishlist", "account", "logout",
    "search", "print", "share", "feed", "wp-json", "wp-admin",
    "tag/", "tags/", "category/", "author/", "page/",
    "privacy", "terms", "cookie", "cookies", "sitemap",
}

# Keyword -> page category mapping used by the classifier. Order matters:
# first match wins, so more specific categories should be listed first.
CATEGORY_KEYWORDS = {
    "contact": ["contact", "get-in-touch", "reach-us", "enquiry", "enquire"],
    "about": ["about", "who-we-are", "our-story", "company", "overview", "profile"],
    # Checked before products/services/solutions/industries: a blog/news
    # article's slug can incidentally contain a substring that also
    # matches one of those keywords (e.g. "...shaping-industry-2026..."
    # contains "industr"), which would otherwise misclassify an article
    # as a taxonomy page. Blog/news URL conventions (/articles/, /blog/,
    # /press/, ...) are a strong enough signal to take priority.
    "blog_news": ["blog", "news", "press", "media", "insight", "article"],
    "products": ["product", "portfolio", "catalog", "catalogue"],
    "services": ["service"],
    "solutions": ["solution"],
    "industries": ["industr", "sector", "verticals", "markets"],
    "projects": ["project", "case-stud", "portfolio", "work"],
    "locations": ["location", "branch", "office", "presence", "global-network"],
    "careers": ["career", "jobs", "join-us", "hiring"],
    "home": ["/", ""],
}

SOCIAL_DOMAINS = {
    "linkedin.com": "linkedin",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "youtube.com": "youtube",
    "github.com": "github",
}

# Categories we actively want to crawl outward from (i.e. worth following
# their internal links a bit further). Everything else is still recorded if
# encountered but is not prioritised in the queue.
PRIORITY_CATEGORIES = {
    "home", "about", "products", "services", "solutions",
    "industries", "projects", "locations", "contact",
}
