from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup


@dataclass
class ParsedPage:
    url: str
    title: str | None
    headings: list[str]
    paragraphs: list[str]
    links: list[str]
    meta_description: str | None


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

            if href:
                absolute_url = urljoin(url, href)
                links.append(absolute_url)

        meta_description = None

        meta_tag = soup.find(
            "meta",
            attrs={"name": "description"},
        )

        if meta_tag:
            meta_description = meta_tag.get("content")

        return ParsedPage(
            url=url,
            title=title,
            headings=headings,
            paragraphs=paragraphs,
            links=links,
            meta_description=meta_description,
        )