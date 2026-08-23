from extraction.html_parser import ParsedPage


class CompanyNameExtractor:
    """Extract a company name from a parsed webpage."""

    def extract(self, page: ParsedPage) -> str | None:
        """Return the best available company name."""

        if page.og_site_name:
            return self._clean_name(page.og_site_name)

        if page.application_name:
            return self._clean_name(page.application_name)

        if page.title:
            return self._clean_title(page.title)

        if page.headings:
            return self._clean_name(page.headings[0])

        return None

    @staticmethod
    def _clean_name(name: str) -> str:
        return " ".join(name.split()).strip()

    @staticmethod
    def _clean_title(title: str) -> str:
        separators = ["|", " - ", " — ", " – "]

        cleaned = title

        for separator in separators:
            if separator in cleaned:
                cleaned = cleaned.split(separator)[0]

        return " ".join(cleaned.split()).strip()