"""
Structured output schema. These dataclasses ARE the contract with
downstream systems -- keep field names stable; add fields rather than
renaming them.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass
class PageRecord:
    url: str
    page_type: str                  # category, e.g. "about", "contact"
    final_url: str | None = None    # set only if different from `url` (redirect target)
    title: str | None = None
    http_status: int | None = None
    fetched_ok: bool = False
    extraction_result: str = "not_attempted"  # success | partial | failed | skipped
    error: str | None = None
    depth: int = 0
    rendered_with: str = "static"   # static | dynamic
    discovered_from: str | None = None
    is_third_party: bool = False    # True if this page describes a DIFFERENT
                                     # entity than the one being crawled (e.g. a
                                     # directory-listing detail page for another
                                     # business) -- crawled for discovery, but its
                                     # data is excluded from company aggregation.

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CompanyInfo:
    company_name: str | None = None
    website: str | None = None
    description: str | None = None
    headquarters: str | None = None
    other_locations: list[str] = field(default_factory=list)
    products: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    solutions: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    social_links: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CrawlReport:
    input_url: str
    started_at: str
    finished_at: str | None = None
    pages_discovered: int = 0
    pages_fetched_ok: int = 0
    pages_failed: int = 0
    max_pages_limit: int = 0
    stop_reason: str | None = None
    company: CompanyInfo = field(default_factory=CompanyInfo)
    pages: list[PageRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "input_url": self.input_url,
            "crawl_meta": {
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "pages_discovered": self.pages_discovered,
                "pages_fetched_ok": self.pages_fetched_ok,
                "pages_failed": self.pages_failed,
                "max_pages_limit": self.max_pages_limit,
                "stop_reason": self.stop_reason,
            },
            "company": self.company.to_dict(),
            "pages": [p.to_dict() for p in self.pages],
        }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
