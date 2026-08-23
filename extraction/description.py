from extraction.html_parser import ParsedPage


class DescriptionExtractor:
    """Extract the best available description from a parsed webpage."""

    def extract(self, page: ParsedPage) -> str | None:
        # Highest priority: Open Graph description.
        if page.og_description:
            return self._clean(page.og_description)

        # Second priority: standard meta description.
        if page.meta_description:
            return self._clean(page.meta_description)

        # Fallback: first meaningful visible paragraph.
        for paragraph in page.paragraphs:
            cleaned = self._clean(paragraph)

            if len(cleaned) >= 40:
                return cleaned

        return None

    @staticmethod
    def _clean(text: str) -> str:
        return " ".join(text.split()).strip()