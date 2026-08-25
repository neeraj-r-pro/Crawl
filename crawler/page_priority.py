from urllib.parse import urlsplit


class PagePriority:
    """
    Score internal URLs so useful business pages are crawled first.

    Higher score = crawled earlier.

    The scoring is intentionally generic. It does not depend on
    any particular website.
    """

    HIGH_PRIORITY = {
        "products": 100,
        "product": 100,
        "services": 95,
        "service": 95,
        "solutions": 90,
        "solution": 90,
        "categories": 88,
        "category": 88,
        "industries": 85,
        "industry": 85,
        "about": 80,
        "company": 75,
        "contact": 70,
        "locations": 65,
        "location": 65,
        "branches": 65,
        "catalog": 90,
        "catalogue": 90,
        "portfolio": 80,
    }

    MEDIUM_PRIORITY = {
        "business",
        "businesses",
        "market",
        "markets",
        "capabilities",
        "offerings",
        "what-we-do",
        "what-we-offer",
        "sectors",
        "brands",
        "projects",
        "case-studies",
        "case-study",
        "partners",
        "customers",
        "clients",
        "technology",
        "technologies",
    }

    LOW_PRIORITY = {
        "blog",
        "blogs",
        "news",
        "updates",
        "events",
        "careers",
        "career",
        "jobs",
        "login",
        "signin",
        "sign-in",
        "register",
        "signup",
        "sign-up",
        "privacy",
        "terms",
        "sitemap",
        "feed",
        "rss",
    }

    STATIC_EXTENSIONS = {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".svg",
        ".ico",
        ".css",
        ".js",
        ".json",
        ".xml",
        ".pdf",
        ".zip",
        ".mp4",
        ".mp3",
        ".wav",
        ".avi",
    }

    # ---------------------------------------------------------
    # MAIN SCORING
    # ---------------------------------------------------------

    @classmethod
    def score(cls, url: str) -> int:
        """
        Return a priority score for an internal URL.

        Higher values are crawled earlier.
        """

        if not url:
            return 0

        parsed = urlsplit(url)

        path = parsed.path.lower().strip("/")
        query = parsed.query.lower()

        # Homepage/root.
        if not path:
            return 0

        # Static resources should effectively never be crawled.
        if cls._is_static_resource(path):
            return -100

        # -----------------------------------------------------
        # Filtered listing variants
        # -----------------------------------------------------
        #
        # Example:
        #
        # /filter-product-listing
        # /filter-product-listing?categories=abc
        #
        # The base listing page is valuable, but filtered variants
        # should not consume the initial crawl budget.
        #
        # This check MUST happen before normal listing scoring.
        # Otherwise the query variant would receive the same high
        # score as the base listing page.
        # -----------------------------------------------------

        if cls._is_filtered_listing_variant(path, query):
            return 25

        parts = cls._split_path(path)

        if not parts:
            return 0

        # -----------------------------------------------------
        # Product/detail handling comes BEFORE normal scoring.
        # -----------------------------------------------------

        if cls._is_product_detail(parts):
            return cls._detail_score(parts)

        # -----------------------------------------------------
        # Strong listing/page-section detection.
        # -----------------------------------------------------

        listing_score = cls._listing_score(parts)

        if listing_score is not None:
            return listing_score

        # -----------------------------------------------------
        # Normal business-page scoring.
        # -----------------------------------------------------

        score = 0

        for part in parts:

            if part in cls.HIGH_PRIORITY:
                score = max(
                    score,
                    cls.HIGH_PRIORITY[part],
                )

            elif part in cls.MEDIUM_PRIORITY:
                score = max(score, 50)

            elif part in cls.LOW_PRIORITY:
                score = max(score, 10)

        # Embedded keyword matching.
        if score == 0:
            score = cls._keyword_score(parts)

        # -----------------------------------------------------
        # Depth penalty.
        #
        # /about             -> 80
        # /about/company     -> lower
        # /about/company/x   -> lower again
        # -----------------------------------------------------

        if score > 0:
            depth = len(parts)

            score -= max(
                0,
                depth - 1,
            ) * 4

        # Unknown pages remain crawlable.
        if score == 0:
            score = 20

        return max(score, 1)

    # ---------------------------------------------------------
    # FILTERED LISTING DETECTION
    # ---------------------------------------------------------

    @classmethod
    def _is_filtered_listing_variant(
        cls,
        path: str,
        query: str,
    ) -> bool:
        """
        Detect listing URLs that contain query parameters.

        A base listing page should receive high priority:

            /filter-product-listing

        But filtered variants should receive lower priority:

            /filter-product-listing?categories=abc
            /filter-product-listing?categories=xyz

        This prevents many nearly-identical filtered pages from
        consuming the initial crawl budget.
        """

        # No query means this is the base page.
        if not query:
            return False

        # Normalize the path.
        normalized_path = path.strip("/").lower()

        listing_paths = {
            "filter-product-listing",
            "product-listing",
            "product-list",
            "products-list",
            "product-categories",
            "product-category",
            "products",
            "categories",
            "category",
            "catalog",
            "catalogue",
        }

        return normalized_path in listing_paths

    # ---------------------------------------------------------
    # PATH HELPERS
    # ---------------------------------------------------------

    @classmethod
    def _split_path(cls, path: str) -> list[str]:
        """
        Normalize URL path segments.

        Example:

            /products/electrical_items/
            ->
            ["products", "electrical-items"]
        """

        parts = []

        for part in path.split("/"):
            part = part.strip()

            if not part:
                continue

            part = (
                part
                .replace("_", "-")
                .replace(" ", "-")
                .strip("-")
                .lower()
            )

            if part:
                parts.append(part)

        return parts

    # ---------------------------------------------------------
    # PRODUCT LISTINGS
    # ---------------------------------------------------------

    @classmethod
    def _listing_score(
        cls,
        parts: list[str],
    ) -> int | None:
        """
        Detect genuine product/category listing pages.

        Listing pages receive high priority.

        Examples:

            /products
            /products/furniture
            /product-list
            /catalog
            /categories/furniture

        Deep product-detail pages are handled separately.
        """

        if not parts:
            return None

        first = parts[0]

        # Exact top-level product/listing pages.
        top_level = {
            "products": 105,
            "product-list": 103,
            "product-listing": 103,
            "products-list": 103,
            "catalog": 100,
            "catalogue": 100,
            "categories": 98,
            "category": 98,
        }

        if first in top_level:

            base_score = top_level[first]

            # A direct listing/category page is valuable.
            #
            # /products
            # /products/furniture
            #
            # But deeper pages receive a modest penalty.
            depth_penalty = max(
                0,
                len(parts) - 1,
            ) * 5

            return max(
                base_score - depth_penalty,
                60,
            )

        # Some websites use:
        #
        # /filter-product-listing
        # /product-categories
        # /product-list
        #
        combined_listing_terms = (
            "product-list",
            "product-listing",
            "products-list",
            "product-categories",
            "product-category",
            "filter-product-listing",
        )

        if any(
            term in first
            for term in combined_listing_terms
        ):
            return 95

        return None

    # ---------------------------------------------------------
    # PRODUCT DETAILS
    # ---------------------------------------------------------

    @classmethod
    def _is_product_detail(
        cls,
        parts: list[str],
    ) -> bool:
        """
        Identify individual product/detail pages.

        These should remain crawlable but should not consume the
        initial crawl budget before useful company-level pages.
        """

        if not parts:
            return False

        lower_path = "/" + "/".join(parts) + "/"

        detail_prefixes = (
            "/product-overview/",
            "/product-detail/",
            "/product-details/",
        )

        if any(
            lower_path.startswith(prefix)
            for prefix in detail_prefixes
        ):
            return True

        # /product/<slug>
        if (
            len(parts) >= 2
            and parts[0] == "product"
        ):
            return True

        # Common detail structures.
        detail_words = {
            "details",
            "detail",
            "overview",
            "specification",
            "specifications",
            "item",
        }

        if any(
            part in detail_words
            for part in parts[1:]
        ):
            return True

        return False

    @classmethod
    def _detail_score(
        cls,
        parts: list[str],
    ) -> int:
        """
        Score a product/detail page.

        Keep it crawlable, but below major business pages.
        """

        depth = len(parts)

        # Detail pages start around 45.
        score = 45

        # Deeper detail pages get progressively lower priority.
        score -= max(
            0,
            depth - 2,
        ) * 4

        return max(score, 25)

    # ---------------------------------------------------------
    # KEYWORD SCORING
    # ---------------------------------------------------------

    @classmethod
    def _keyword_score(
        cls,
        parts: list[str],
    ) -> int:
        """
        Detect business keywords embedded in URL slugs.

        Example:

            /our-business-solutions
            /technology-services
            /industrial-solutions
        """

        score = 0

        for part in parts:

            words = set(
                word
                for word in part.split("-")
                if word
            )

            # High-priority keywords.
            for keyword, value in cls.HIGH_PRIORITY.items():

                keyword_parts = (
                    keyword
                    .replace("_", "-")
                    .split("-")
                )

                if all(
                    keyword_part in words
                    for keyword_part in keyword_parts
                ):
                    score = max(
                        score,
                        value - 10,
                    )

            # Medium-priority keywords.
            for keyword in cls.MEDIUM_PRIORITY:

                if (
                    keyword in words
                    or keyword in part
                ):
                    score = max(
                        score,
                        45,
                    )

            # Low-priority keywords.
            for keyword in cls.LOW_PRIORITY:

                if (
                    keyword in words
                    or keyword in part
                ):
                    score = max(
                        score,
                        10,
                    )

        return score

    # ---------------------------------------------------------
    # STATIC RESOURCE DETECTION
    # ---------------------------------------------------------

    @classmethod
    def _is_static_resource(
        cls,
        path: str,
    ) -> bool:
        path_lower = path.lower()

        return any(
            path_lower.endswith(extension)
            for extension in cls.STATIC_EXTENSIONS
        )