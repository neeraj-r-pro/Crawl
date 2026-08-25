import re

from extraction.html_parser import ParsedPage


class CategoryExtractor:
    """Extract business categories from parsed webpages."""

    CATEGORY_KEYWORDS = {
        "products": {
            "product",
            "products",
            "product-listing",
            "product-list",
            "catalog",
            "catalogue",
            "category",
            "categories",
        },
        "services": {
            "service",
            "services",
        },
        "solutions": {
            "solution",
            "solutions",
        },
        "industries": {
            "industry",
            "industries",
        },
        "locations": {
            "location",
            "locations",
            "branches",
            "offices",
        },
    }

    IGNORE_TEXT_PATTERNS = [
        r"^ask\s+for\s+quote$",
        r"^request\s+(a\s+)?quote$",
        r"^get\s+(a\s+)?quote$",
        r"^contact\s+us$",
        r"^contact$",
        r"^get\s+in\s+touch$",
        r"^email\s*:",
        r"^phone\s*:",
        r"^tel\s*:",
        r"^mobile\s*:",
        r"^fax\s*:",
        r"^address\s*:",
        r"^location\s+",
        r"^gst\s+verified$",
        r"^verified\s+business$",
        r"^verified$",
        r"^available\s+from\s+",
        r"^no\s+products?\s+found",
        r"^welcome\s+to\s+",
        r"^our\s+mission$",
        r"^our\s+vision$",
        r"^our\s+address$",
        r"^contact\s+info",
        r"^about\s+",
        r"^©",
        r"all\s+rights\s+reserved",
    ]

    MAX_ITEM_LENGTH = 150

    # Words that frequently indicate that a heading is marketing/UI
    # content rather than a product/service/category.
    NOISE_HEADING_PATTERNS = [
        r"\bwhy\s+choose\b",
        r"\bneed\s+.*\bfast\b",
        r"\bupcoming\b",
        r"\bevents?\b",
        r"\btop\s+in\b",
        r"\brecently\s+added\b",
        r"\bplatform\s+highlights?\b",
        r"\bjoin\s+.*\bbusiness",
        r"\b24\s*/\s*7\b",
        r"\bnotifications?\b",
        r"\blead\s+management\b",
        r"\barticles?\b",
        r"\babout\s+",
        r"\bcontact\s+",
        r"\boffice\s+",
    ]

    def extract(self, page: ParsedPage) -> dict[str, list[str]]:
        result = {
            "products": [],
            "services": [],
            "solutions": [],
            "industries": [],
            "locations": [],
        }

        page_type = self._detect_page_type(page)

        if page_type is None:
            return result

        if page_type == "products":
            result["products"] = self._extract_products(page)

        elif page_type == "services":
            result["services"] = self._extract_services(page)

        elif page_type == "solutions":
            result["solutions"] = self._extract_section(page)

        elif page_type == "industries":
            result["industries"] = self._extract_section(page)

        elif page_type == "locations":
            result["locations"] = self._extract_section(page)

        return result

    # ---------------------------------------------------------------
    # PAGE TYPE DETECTION
    # ---------------------------------------------------------------

    def _detect_page_type(self, page: ParsedPage) -> str | None:
        """
        Determine the type of page using strong signals first.

        Priority:
            1. URL/path
            2. Exact heading/title matches
            3. Heading phrase matches
            4. Title phrase matches

        We deliberately do NOT classify a page simply because a random
        piece of text contains the word "product", "service", etc.
        """

        url = self._normalize(page.url or "")
        title = self._normalize(page.title or "")
        headings = [
            self._clean_text(h)
            for h in (page.headings or [])
            if self._clean_text(h)
        ]

        # -----------------------------------------------------------
        # 1. URL is the strongest signal.
        # -----------------------------------------------------------

        url_type = self._type_from_url(url)

        if url_type:
            return url_type

        # -----------------------------------------------------------
        # 2. Exact heading matches.
        # -----------------------------------------------------------

        for heading in headings:
            exact_type = self._exact_heading_type(heading)

            if exact_type:
                return exact_type

        # -----------------------------------------------------------
        # 3. Strong heading phrases.
        # -----------------------------------------------------------

        for heading in headings:
            heading_type = self._type_from_heading_phrase(heading)

            if heading_type:
                return heading_type

        # -----------------------------------------------------------
        # 4. Title.
        # -----------------------------------------------------------

        title_type = self._type_from_title(title)

        if title_type:
            return title_type

        return None

    def _type_from_url(self, url: str) -> str | None:
        if not url:
            return None

        # Remove protocol/domain noise and inspect URL path.
        path = re.sub(
            r"^https?://[^/]+",
            "",
            url,
            flags=re.IGNORECASE,
        )

        path = path.split("?", 1)[0]
        path = path.split("#", 1)[0]

        segments = [
            segment
            for segment in path.split("/")
            if segment
        ]

        # Check the most specific path segment first.
        for segment in reversed(segments):
            normalized = self._normalize(segment)

            if not normalized:
                continue

            category_type = self._exact_keyword_type(normalized)

            if category_type:
                return category_type

            # Handle compound URL segments such as:
            # product-listing
            # product-list
            # filter-product-listing
            # our-services
            for category, keywords in self.CATEGORY_KEYWORDS.items():
                for keyword in keywords:
                    keyword_normalized = self._normalize(keyword)

                    if (
                        keyword_normalized
                        and keyword_normalized in normalized
                    ):
                        return category

        return None

    def _exact_heading_type(
        self,
        heading: str,
    ) -> str | None:
        normalized = self._normalize(heading)

        exact_matches = {
            "product": "products",
            "products": "products",
            "our products": "products",
            "services": "services",
            "service": "services",
            "our services": "services",
            "solutions": "solutions",
            "solution": "solutions",
            "our solutions": "solutions",
            "industries": "industries",
            "industry": "industries",
            "our industries": "industries",
            "industries we serve": "industries",
            "explore by industry": "industries",
            "explore product industry": "industries",
            "locations": "locations",
            "location": "locations",
            "our locations": "locations",
            "branches": "locations",
            "offices": "locations",
        }

        return exact_matches.get(normalized)

    def _type_from_heading_phrase(
        self,
        heading: str,
    ) -> str | None:
        normalized = self._normalize(heading)

        if not normalized:
            return None

        # Strong phrases only.
        phrase_matches = [
            (
                "industries",
                [
                    "industries we serve",
                    "explore by industry",
                    "explore product industry",
                    "industry we serve",
                ],
            ),
            (
                "products",
                [
                    "product listing",
                    "product listings",
                    "product catalogue",
                    "product catalog",
                    "product list",
                ],
            ),
            (
                "services",
                [
                    "our services",
                    "services we provide",
                    "services we offer",
                ],
            ),
            (
                "solutions",
                [
                    "our solutions",
                    "solutions we provide",
                    "solutions we offer",
                ],
            ),
            (
                "locations",
                [
                    "our locations",
                    "our branches",
                    "our offices",
                    "find us",
                ],
            ),
        ]

        for category, phrases in phrase_matches:
            for phrase in phrases:
                if phrase in normalized:
                    return category

        return None

    def _type_from_title(
        self,
        title: str,
    ) -> str | None:
        if not title:
            return None

        # Titles can contain company names, so only use strong phrases.
        exact = self._exact_heading_type(title)

        if exact:
            return exact

        title_patterns = [
            (r"\bproducts?\b", "products"),
            (r"\bservices?\b", "services"),
            (r"\bsolutions?\b", "solutions"),
            (r"\bindustr(?:y|ies)\b", "industries"),
            (r"\blocations?\b", "locations"),
            (r"\bbranches\b", "locations"),
            (r"\boffices\b", "locations"),
        ]

        for pattern, category in title_patterns:
            if re.search(pattern, title):
                return category

        return None

    def _exact_keyword_type(
        self,
        text: str,
    ) -> str | None:
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if self._normalize(keyword) == text:
                    return category

        return None

    # ---------------------------------------------------------------
    # PRODUCTS
    # ---------------------------------------------------------------

    def _extract_products(
        self,
        page: ParsedPage,
    ) -> list[str]:
        """
        Extract product names primarily from subordinate headings.

        This avoids treating arbitrary homepage paragraphs or marketing
        text as products.
        """

        headings = self._clean_candidates(page.headings)

        if len(headings) > 1:
            candidates = self._select_subordinate_headings(headings)

            if candidates:
                return self._deduplicate(candidates)

        # If there is only one heading, do not automatically treat it
        # as a product. It is normally the page title.
        #
        # Paragraph fallback is deliberately conservative.
        candidates = []

        for paragraph in page.paragraphs:
            paragraph = self._clean_text(paragraph)

            if not self._is_valid_category_item(paragraph):
                continue

            if self._looks_like_description(paragraph):
                continue

            if self._looks_like_ui_or_marketing(paragraph):
                continue

            candidates.append(paragraph)

        return self._deduplicate(candidates)

    # ---------------------------------------------------------------
    # SERVICES
    # ---------------------------------------------------------------

    def _extract_services(
        self,
        page: ParsedPage,
    ) -> list[str]:
        headings = self._clean_candidates(page.headings)

        if len(headings) > 1:
            candidates = self._select_subordinate_headings(headings)

            if candidates:
                return self._deduplicate(candidates)

        candidates = []

        for paragraph in page.paragraphs:
            paragraph = self._clean_text(paragraph)

            if not self._is_valid_category_item(paragraph):
                continue

            if self._looks_like_description(paragraph):
                continue

            if self._looks_like_ui_or_marketing(paragraph):
                continue

            candidates.append(paragraph)

        return self._deduplicate(candidates)

    # ---------------------------------------------------------------
    # SOLUTIONS / INDUSTRIES / LOCATIONS
    # ---------------------------------------------------------------

    def _extract_section(
        self,
        page: ParsedPage,
    ) -> list[str]:
        headings = self._clean_candidates(page.headings)

        if len(headings) > 1:
            candidates = self._select_subordinate_headings(headings)

            if candidates:
                return self._deduplicate(candidates)

        candidates = []

        for paragraph in page.paragraphs:
            paragraph = self._clean_text(paragraph)

            if not self._is_valid_category_item(paragraph):
                continue

            if self._looks_like_description(paragraph):
                continue

            if self._looks_like_ui_or_marketing(paragraph):
                continue

            candidates.append(paragraph)

        return self._deduplicate(candidates)

    # ---------------------------------------------------------------
    # HEADING SELECTION
    # ---------------------------------------------------------------

    def _select_subordinate_headings(
        self,
        headings: list[str],
    ) -> list[str]:
        if not headings:
            return []

        candidates = []

        # The first heading is usually the page/category heading.
        #
        # However, don't blindly discard it if it looks like an actual
        # candidate and the remaining headings clearly represent items.
        subordinate = headings[1:]

        for item in subordinate:
            if not self._is_valid_category_item(item):
                continue

            if self._looks_like_page_heading(item):
                continue

            if self._looks_like_ui_or_marketing(item):
                continue

            candidates.append(item)

        return candidates

    # ---------------------------------------------------------------
    # FILTERING
    # ---------------------------------------------------------------

    def _clean_candidates(
        self,
        values: list[str],
    ) -> list[str]:
        result = []

        for value in values:
            value = self._clean_text(value)

            if not value:
                continue

            if not self._is_valid_category_item(value):
                continue

            result.append(value)

        return result

    def _is_valid_category_item(
        self,
        text: str,
    ) -> bool:
        text = self._clean_text(text)

        if not text:
            return False

        if len(text) > self.MAX_ITEM_LENGTH:
            return False

        normalized = self._normalize(text)

        if not normalized:
            return False

        for pattern in self.IGNORE_TEXT_PATTERNS:
            if re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            ):
                return False

        if re.search(
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
            text,
            flags=re.IGNORECASE,
        ):
            return False

        if re.search(
            r"(?:\+?\d[\d\s().-]{7,}\d)",
            text,
        ):
            return False

        if "©" in text:
            return False

        return True

    def _looks_like_description(
        self,
        text: str,
    ) -> bool:
        """
        Detect sentence-like content rather than category names.
        """

        text = self._clean_text(text)

        if not text:
            return True

        words = text.split()

        # A category/product name can be long, but very long prose is
        # unlikely to be a category item.
        if len(words) > 12:
            return True

        if re.search(r"[.!?]", text):
            return True

        prose_patterns = [
            r"\bwe\s+(provide|offer|deliver|build|create|help|serve)\b",
            r"\bwe\s+are\b",
            r"\bwe\s+have\b",
            r"\bexperts?\s+in\b",
            r"\bdesigned\s+to\b",
            r"\bhelps?\s+(you|businesses|companies)\b",
            r"\bthat\s+(helps?|keeps?|provides?|allows?)\b",
            r"\bwith\s+(our|the)\b",
            r"\bfor\s+(businesses|companies|customers)\b",
            r"\bconnect\s+with\b",
            r"\bdiscover\s+the\b",
            r"\breliable\s+\w+\s+and\s+\w+\b",
        ]

        for pattern in prose_patterns:
            if re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            ):
                return True

        return False

    def _looks_like_ui_or_marketing(
        self,
        text: str,
    ) -> bool:
        normalized = self._normalize(text)

        if not normalized:
            return True

        for pattern in self.NOISE_HEADING_PATTERNS:
            if re.search(
                pattern,
                normalized,
                flags=re.IGNORECASE,
            ):
                return True

        return False

    def _looks_like_page_heading(
        self,
        text: str,
    ) -> bool:
        normalized = self._normalize(text)

        page_heading_terms = {
            "products",
            "product",
            "services",
            "service",
            "solutions",
            "solution",
            "industries",
            "industry",
            "locations",
            "location",
            "our products",
            "our services",
            "our solutions",
            "our industries",
            "industries we serve",
            "explore by industry",
            "explore product industry",
            "about",
            "about us",
            "contact",
            "contact us",
        }

        return normalized in page_heading_terms

    # ---------------------------------------------------------------
    # TEXT HELPERS
    # ---------------------------------------------------------------

    @staticmethod
    def _clean_text(
        text: str,
    ) -> str:
        if not text:
            return ""

        return re.sub(
            r"\s+",
            " ",
            str(text),
        ).strip()

    @staticmethod
    def _normalize(
        text: str,
    ) -> str:
        text = text.lower().strip()

        text = re.sub(
            r"[-_/]+",
            " ",
            text,
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text

    @staticmethod
    def _deduplicate(
        values: list[str],
    ) -> list[str]:
        result = []
        seen = set()

        for value in values:
            normalized = CategoryExtractor._normalize(value)

            if not normalized:
                continue

            if normalized in seen:
                continue

            seen.add(normalized)
            result.append(value)

        return result