from extraction.contact import ContactExtractor
from extraction.html_parser import HTMLParser


def create_page(html: str):
    parser = HTMLParser()

    return parser.parse(
        html,
        "https://example.com",
    )


def test_extract_email_from_mailto_link():
    html = """
    <html>
        <body>
            <a href="mailto:sales@example.com">
                Email us
            </a>
        </body>
    </html>
    """

    page = create_page(html)

    extractor = ContactExtractor()

    result = extractor.extract(page)

    assert result["emails"] == [
        "sales@example.com"
    ]


def test_extract_email_from_text():
    html = """
    <html>
        <body>
            <p>
                Contact us at sales@example.com
            </p>
        </body>
    </html>
    """

    page = create_page(html)

    extractor = ContactExtractor()

    result = extractor.extract(page)

    assert result["emails"] == [
        "sales@example.com"
    ]


def test_deduplicate_emails():
    html = """
    <html>
        <body>
            <a href="mailto:sales@example.com">
                Email
            </a>

            <p>
                sales@example.com
            </p>
        </body>
    </html>
    """

    page = create_page(html)

    extractor = ContactExtractor()

    result = extractor.extract(page)

    assert result["emails"] == [
        "sales@example.com"
    ]


def test_extract_phone_from_tel_link():
    html = """
    <html>
        <body>
            <a href="tel:+919876543210">
                Call us
            </a>
        </body>
    </html>
    """

    page = create_page(html)

    extractor = ContactExtractor()

    result = extractor.extract(page)

    assert result["phone_numbers"] == [
        "+919876543210"
    ]


def test_extract_phone_from_text():
    html = """
    <html>
        <body>
            <p>
                Call us at +91 98765 43210
            </p>
        </body>
    </html>
    """

    page = create_page(html)

    extractor = ContactExtractor()

    result = extractor.extract(page)

    assert result["phone_numbers"] == [
        "+919876543210"
    ]


def test_invalid_phone_is_ignored():
    html = """
    <html>
        <body>
            <p>
                Call 12345
            </p>
        </body>
    </html>
    """

    page = create_page(html)

    extractor = ContactExtractor()

    result = extractor.extract(page)

    assert result["phone_numbers"] == []


def test_contact_result_contains_addresses():
    html = """
    <html>
        <body>
            <p>
                Contact us today.
            </p>
        </body>
    </html>
    """

    page = create_page(html)

    extractor = ContactExtractor()

    result = extractor.extract(page)

    assert result["addresses"] == []