from extraction.html_parser import ParsedPage


class CategoryExtractor:
    """
    Extract business categories from a parsed page.

    Supported:
        - products
        - services
        - solutions
        - industries
        - locations

    The extractor is intentionally conservative. It tries to return
    actual business/category names rather than navigation, descriptions,
    CTAs, footer content, or generic company text.
    """

    MAX_ITEM_LENGTH = 120
    MAX_DESCRIPTION_WORDS = 18

    CATEGORY_WORDS = {
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
        "categories",
        "category",
    }

    IGNORED_EXACT = {
        "products",
        "product",
        "our products",
        "services",
        "service",
        "our services",
        "solutions",
        "solution",
        "our solutions",
        "industries",
        "industry",
        "our industries",
        "industries we serve",
        "industries served",
        "industry we serve",
        "locations",
        "location",
        "our locations",
        "office location",
        "office locations",
        "categories",
        "category",
        "our categories",
        "contact",
        "contact us",
        "contact info",
        "contact information",
        "about",
        "about us",
        "home",
        "menu",
        "navigation menu",
        "site-wide links",
        "footer",
        "our mission",
        "our vision",
        "our address",
        "frequently asked questions",
        "faq",
        "faqs",
        "learn more",
        "read more",
        "click here",
        "explore",
        "explore more",
        "explore product industry",
        "explore by industry",
        "no products found",
    }

    IGNORED_PREFIXES = (
        "copyright",
        "privacy policy",
        "terms of",
        "all rights reserved",
        "email:",
        "phone:",
        "fax:",
        "address:",
        "contact:",
        "follow us",
        "subscribe",
    )

    # Generic navigation / marketing phrases that commonly appear
    # on dynamically rendered business websites.
    IGNORED_PHRASES = (
        "site-wide links",
        "navigation menu",
        "main menu",
        "footer menu",
        "quick links",
        "useful links",
        "learn more",
        "read more",
        "click here",
        "view all",
        "view more",
        "see all",
        "explore more",
        "get started",
        "sign up",
        "log in",
        "login",
        "register",
        "contact us",
        "about us",
        "know more",
        "discover more",
        "frequently asked questions",
        "no products found",
    )

    def extract(self, page: ParsedPage) -> dict[str, list[str]]:
        """
        Extract categories from a single parsed page.
        """

        categories = self._detect_page_categories(page)

        result = {
            "products": [],
            "services": [],
            "solutions": [],
            "industries": [],
            "locations": [],
        }

        if not categories:
            return result

        items = self._collect_text(page)

        for category in categories:
            result[category] = self._extract_items(
                items,
                category,
                page,
            )

        return result

    # =========================================================
    # PAGE CATEGORY DETECTION
    # =========================================================

    def _detect_page_categories(
        self,
        page: ParsedPage,
    ) -> set[str]:
        """
        Determine what kind of business information the page contains.

        Uses:
            - URL
            - page title
            - headings
        """

        categories = set()

        # -----------------------------------------------------
        # URL is particularly useful for BONC-style pages.
        # -----------------------------------------------------

        url = (page.url or "").lower()

        path = url.split("?", 1)[0].rstrip("/")

        if self._url_contains(path, "product"):
            categories.add("products")

        if self._url_contains(path, "catalog"):
            categories.add("products")

        if self._url_contains(path, "category"):
            categories.add("products")

        if self._url_contains(path, "categories"):
            categories.add("products")

        if self._url_contains(path, "filter-product-listing"):
            categories.add("products")

        if self._url_contains(path, "service"):
            categories.add("services")

        if self._url_contains(path, "solution"):
            categories.add("solutions")

        if self._url_contains(path, "industr"):
            categories.add("industries")

        if self._url_contains(path, "location"):
            categories.add("locations")

        # -----------------------------------------------------
        # Title + headings
        # -----------------------------------------------------

        texts = []

        if page.title:
            texts.append(page.title)

        texts.extend(page.headings)

        for text in texts:
            normalized = self._normalize(text)

            if not normalized:
                continue

            # PRODUCTS
            if self._is_product_heading(normalized):
                categories.add("products")

            # SERVICES
            if self._is_service_heading(normalized):
                categories.add("services")

            # SOLUTIONS
            if self._is_solution_heading(normalized):
                categories.add("solutions")

            # INDUSTRIES
            if self._is_industry_heading(normalized):
                categories.add("industries")

            # LOCATIONS
            if self._is_location_heading(normalized):
                categories.add("locations")

        return categories

    # =========================================================
    # CATEGORY HEADING DETECTION
    # =========================================================

    @staticmethod
    def _is_product_heading(text: str) -> bool:
        return (
            text in {
                "product",
                "products",
                "our products",
                "product list",
                "product listing",
                "product listings",
                "products list",
                "products listing",
                "product catalog",
                "product catalogue",
                "catalog",
                "catalogue",
                "categories",
                "category",
                "product categories",
            }
            or "products we offer" in text
            or "products we provide" in text
            or "our product range" in text
            or "product range" in text
            or "product listing" in text
            or "product catalog" in text
            or "product catalogue" in text
            or "explore product" in text
        )

    @staticmethod
    def _is_service_heading(text: str) -> bool:
        return (
            text in {
                "service",
                "services",
                "our services",
                "service list",
                "service listing",
                "service offerings",
            }
            or "services we offer" in text
            or "services we provide" in text
            or "our service" in text
            or "service offering" in text
        )

    @staticmethod
    def _is_solution_heading(text: str) -> bool:
        return (
            text in {
                "solution",
                "solutions",
                "our solutions",
                "solution list",
                "solution offering",
                "solution offerings",
            }
            or "solutions we offer" in text
            or "solutions we provide" in text
            or "our solution" in text
        )

    @staticmethod
    def _is_industry_heading(text: str) -> bool:
        return (
            text in {
                "industry",
                "industries",
                "our industries",
                "industries we serve",
                "industries served",
                "industry we serve",
                "industry served",
                "industries we work with",
                "industries we support",
            }
            or "by industry" in text
            or "by industries" in text
            or "explore by industry" in text
            or "explore industries" in text
            or "industry we" in text
            or "industries we" in text
        )

    @staticmethod
    def _is_location_heading(text: str) -> bool:
        return (
            text in {
                "location",
                "locations",
                "our locations",
                "office location",
                "office locations",
                "locations we serve",
                "locations served",
                "our offices",
                "offices",
                "branches",
                "our branches",
            }
            or "locations we serve" in text
            or "locations served" in text
            or "find us" in text
        )

    # =========================================================
    # TEXT COLLECTION
    # =========================================================

    def _collect_text(
        self,
        page: ParsedPage,
    ) -> list[str]:
        """
        Collect useful visible text.

        Headings are collected first, then paragraphs.
        """

        items = []

        for heading in page.headings:
            cleaned = self._clean_item(heading)

            if cleaned:
                items.append(cleaned)

        for paragraph in page.paragraphs:
            cleaned = self._clean_item(paragraph)

            if cleaned:
                items.append(cleaned)

        return self._deduplicate(items)

    # =========================================================
    # CATEGORY ITEM EXTRACTION
    # =========================================================

    def _extract_items(
        self,
        items: list[str],
        category: str,
        page: ParsedPage,
    ) -> list[str]:

        result = []

        for item in items:
            if not self._is_valid_item(
                item,
                category,
                page,
            ):
                continue

            result.append(item)

        return self._deduplicate(result)

    # =========================================================
    # ITEM VALIDATION
    # =========================================================

    def _is_valid_item(
        self,
        item: str,
        category: str,
        page: ParsedPage,
    ) -> bool:

        normalized = self._normalize(item)

        if not normalized:
            return False

        # -----------------------------------------------------
        # Never return category headings.
        # -----------------------------------------------------

        if normalized in self.IGNORED_EXACT:
            return False

        # -----------------------------------------------------
        # Footer/legal/contact content.
        # -----------------------------------------------------

        if any(
            normalized.startswith(prefix)
            for prefix in self.IGNORED_PREFIXES
        ):
            return False

        if any(
            phrase in normalized
            for phrase in self.IGNORED_PHRASES
        ):
            return False

        # -----------------------------------------------------
        # Email addresses.
        # -----------------------------------------------------

        if "@" in item:
            return False

        # -----------------------------------------------------
        # Phone numbers.
        # -----------------------------------------------------

        if self._contains_phone_number(item):
            return False

        # -----------------------------------------------------
        # URLs.
        # -----------------------------------------------------

        if self._looks_like_url(item):
            return False

        # -----------------------------------------------------
        # Very long descriptions.
        # -----------------------------------------------------

        if len(item) > self.MAX_ITEM_LENGTH:
            return False

        # -----------------------------------------------------
        # Sentence-like descriptions.
        # -----------------------------------------------------

        if self._looks_like_description(item):
            return False

        # -----------------------------------------------------
        # Generic company content.
        # -----------------------------------------------------

        if self._is_generic_company_text(item):
            return False

        # -----------------------------------------------------
        # Category-specific rules.
        # -----------------------------------------------------

        if category == "products":
            if not self._looks_like_business_item(item):
                return False

        elif category == "services":
            if not self._looks_like_business_item(item):
                return False

        elif category == "solutions":
            if not self._looks_like_business_item(item):
                return False

        elif category == "industries":
            if not self._looks_like_business_item(item):
                return False

        elif category == "locations":
            if not self._looks_like_business_item(item):
                return False

        return True

    # =========================================================
    # BUSINESS ITEM DETECTION
    # =========================================================

    def _looks_like_business_item(
        self,
        text: str,
    ) -> bool:
        """
        Determine whether text looks like a business/category name
        rather than a sentence or navigation element.
        """

        words = text.split()

        if not words:
            return False

        # Extremely long phrases are normally descriptions.
        if len(words) > 12:
            return False

        lower = text.lower()

        # CTA / navigation style text.
        bad_starts = (
            "discover ",
            "explore ",
            "learn ",
            "find ",
            "get ",
            "join ",
            "view ",
            "see ",
            "click ",
            "welcome ",
            "this is ",
            "who all ",
            "how ",
            "why ",
            "what ",
        )

        if lower.startswith(bad_starts):
            return False

        # Question-like text.
        if "?" in text:
            return False

        # Common sentence indicators.
        sentence_words = {
            "we",
            "our",
            "you",
            "your",
            "this",
            "these",
            "those",
            "the",
            "is",
            "are",
            "was",
            "were",
            "provides",
            "provide",
            "helps",
            "help",
            "offers",
            "offer",
            "designed",
            "includes",
            "include",
        }

        first_word = words[0].lower()

        if first_word in sentence_words and len(words) > 2:
            return False

        return True

    # =========================================================
    # GENERIC COMPANY CONTENT
    # =========================================================

    def _is_generic_company_text(
        self,
        text: str,
    ) -> bool:

        normalized = self._normalize(text)

        generic_phrases = (
            "welcome to ",
            "our mission",
            "our vision",
            "our address",
            "contact info",
            "contact information",
            "site-wide links",
            "navigation menu",
            "frequently asked questions",
            "learn more",
            "read more",
            "click here",
            "no products found",
            "all rights reserved",
            "privacy policy",
            "terms and conditions",
            "terms of use",
            "follow us",
            "subscribe",
            "sign in",
            "sign up",
            "create account",
        )

        for phrase in generic_phrases:
            if normalized.startswith(phrase):
                return True

        return False

    # =========================================================
    # DESCRIPTION DETECTION
    # =========================================================

    def _looks_like_description(
        self,
        text: str,
    ) -> bool:

        words = text.split()

        if not words:
            return False

        # Short category/product/service names are valid.
        if len(words) <= 6 and not text.endswith("."):
            return False

        # Long paragraphs are descriptions.
        if len(words) > self.MAX_DESCRIPTION_WORDS:
            return True

        # Sentences ending with punctuation are usually descriptions.
        if text.endswith("."):
            return True

        lower = text.lower()

        description_starts = (
            "we ",
            "our ",
            "the ",
            "this ",
            "these ",
            "discover ",
            "learn ",
            "join ",
            "get ",
            "find ",
            "provides ",
            "provide ",
            "offering ",
            "designed ",
            "welcome ",
            "experts ",
            "helping ",
            "helps ",
        )

        if lower.startswith(description_starts):
            return True

        return False

    # =========================================================
    # PHONE DETECTION
    # =========================================================

    @staticmethod
    def _contains_phone_number(
        text: str,
    ) -> bool:

        digits = sum(
            character.isdigit()
            for character in text
        )

        return digits >= 7

    # =========================================================
    # URL DETECTION
    # =========================================================

    @staticmethod
    def _looks_like_url(
        text: str,
    ) -> bool:

        lower = text.lower().strip()

        return (
            lower.startswith("http://")
            or lower.startswith("https://")
            or lower.startswith("www.")
        )

    # =========================================================
    # URL CATEGORY HELPERS
    # =========================================================

    @staticmethod
    def _url_contains(
        path: str,
        value: str,
    ) -> bool:

        segments = [
            segment
            for segment in path.split("/")
            if segment
        ]

        value = value.lower()

        return any(
            value in segment.lower()
            for segment in segments
        )

    # =========================================================
    # CLEANING
    # =========================================================

    @staticmethod
    def _clean_item(
        text: str,
    ) -> str | None:

        if not text:
            return None

        text = " ".join(
            text.split()
        ).strip()

        if not text:
            return None

        return text

    # =========================================================
    # NORMALIZATION
    # =========================================================

    @staticmethod
    def _normalize(
        text: str,
    ) -> str:

        return " ".join(
            text.lower().split()
        ).strip()

    # =========================================================
    # DEDUPLICATION
    # =========================================================

    def _deduplicate(
        self,
        items: list[str],
    ) -> list[str]:

        result = []
        seen = set()

        for item in items:

            normalized = self._normalize(item)

            if not normalized:
                continue

            if normalized in seen:
                continue

            seen.add(normalized)
            result.append(item)

        return result