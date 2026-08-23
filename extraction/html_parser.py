from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup

@dataclass
class LinkInfo:
    url: str
    link_type: str

@dataclass
class ParsedPage:
    url: str
    title: str | None
    headings: list[str]
    paragraphs: list[str]
    links: list[LinkInfo]
    meta_description: str | None
    og_title: str | None
    og_site_name: str | None
    og_description: str | None
    application_name: str | None


class HTMLParser:
    """Parse HTML into structured page-level content."""

    def parse(self, html: str, url: str) -> ParsedPage:
        soup = BeautifulSoup(html, "lxml")

        title = None

        if soup.title:
            title = soup.title.get_text(" ", strip=True)

        headings = [
            heading.get_text(" ", strip=True)
            for heading in soup.find_all(["h1", "h2", "h3"])
            if heading.get_text(" ", strip=True)
        ]

        paragraphs = [
            paragraph.get_text(" ", strip=True)
            for paragraph in soup.find_all("p")
            if paragraph.get_text(" ", strip=True)
        ]

        links = []

        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href")

            if not href:
                continue

            link_type = self._classify_link(href)

            if link_type in {"email", "phone"}:
                normalized_url = href.strip()

            elif link_type == "other":
                normalized_url = href.strip()

            else:
                normalized_url = urljoin(url, href)

            links.append(
                LinkInfo(
                    url=normalized_url,
                    link_type=link_type,
                )
            )

        meta_description = None

        meta_tag = soup.find(
            "meta",
            attrs={"name": "description"},
        )

        if meta_tag:
            meta_description = meta_tag.get("content")

        og_title = None

        og_title_tag = soup.find(
            "meta",
            attrs={"property": "og:title"},
        )

        if og_title_tag:
            og_title = og_title_tag.get("content")


        og_site_name = None

        og_site_name_tag = soup.find(
            "meta",
            attrs={"property": "og:site_name"},
        )

        if og_site_name_tag:
            og_site_name = og_site_name_tag.get("content")


        og_description = None

        og_description_tag = soup.find(
            "meta",
            attrs={"property": "og:description"},
        )

        if og_description_tag:
            og_description = og_description_tag.get("content")


        application_name = None

        application_name_tag = soup.find(
            "meta",
            attrs={"name": "application-name"},
        )

        if application_name_tag:
            application_name = application_name_tag.get("content")

        return ParsedPage(
            url=url,
            title=title,
            headings=headings,
            paragraphs=paragraphs,
            links=links,
            meta_description=meta_description,
            og_title=og_title,
            og_site_name=og_site_name,
            og_description=og_description,
            application_name=application_name,
        )

    @staticmethod
    def _classify_link(href: str) -> str:
        """Classify a link based on its scheme and destination."""

        lower_href = href.lower()

        if lower_href.startswith("mailto:"):
            return "email"

        if lower_href.startswith("tel:"):
            return "phone"

        if lower_href.startswith(
            (
                "https://linkedin.com/",
                "https://www.linkedin.com/",
                "http://linkedin.com/",
                "http://www.linkedin.com/",
                "https://facebook.com/",
                "https://www.facebook.com/",
                "http://facebook.com/",
                "http://www.facebook.com/",
                "https://instagram.com/",
                "https://www.instagram.com/",
                "http://instagram.com/",
                "http://www.instagram.com/",
                "https://x.com/",
                "https://www.x.com/",
                "http://x.com/",
                "http://www.x.com/",
                "https://twitter.com/",
                "https://www.twitter.com/",
                "http://twitter.com/",
                "http://www.twitter.com/",
                "https://youtube.com/",
                "https://www.youtube.com/",
                "http://youtube.com/",
                "http://www.youtube.com/",
            )
        ):
            return "social"

        if lower_href.startswith(("javascript:", "#")):
            return "other"

        return "page"