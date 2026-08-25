from crawler.page_priority import PagePriority


def test_root_page_has_lowest_normal_priority():
    assert PagePriority.score(
        "https://example.com/"
    ) == 0


def test_products_page_has_high_priority():
    assert PagePriority.score(
        "https://example.com/products"
    ) > PagePriority.score(
        "https://example.com/random-page"
    )


def test_services_page_has_high_priority():
    assert PagePriority.score(
        "https://example.com/services"
    ) > PagePriority.score(
        "https://example.com/random-page"
    )


def test_about_and_contact_are_prioritized():
    assert PagePriority.score(
        "https://example.com/about"
    ) > PagePriority.score(
        "https://example.com/random"
    )

    assert PagePriority.score(
        "https://example.com/contact"
    ) > PagePriority.score(
        "https://example.com/random"
    )


def test_low_value_pages_have_lower_priority():
    assert PagePriority.score(
        "https://example.com/products"
    ) > PagePriority.score(
        "https://example.com/blog"
    )


def test_static_resources_are_not_prioritized():
    assert PagePriority.score(
        "https://example.com/assets/company-logo.png"
    ) < 0


def test_nested_business_pages_are_prioritized():
    assert PagePriority.score(
        "https://example.com/products/office-furniture"
    ) > PagePriority.score(
        "https://example.com/random-page"
    )


def test_business_categories_are_prioritized():
    assert PagePriority.score(
        "https://example.com/categories/furniture"
    ) > PagePriority.score(
        "https://example.com/random-page"
    )


def test_case_and_separator_variations():
    assert PagePriority.score(
        "https://example.com/Product-Catalog"
    ) > PagePriority.score(
        "https://example.com/random-page"
    )