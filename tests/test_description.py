from extraction.description import DescriptionExtractor
from extraction.html_parser import HTMLParser


def create_page(html: str):
    parser = HTMLParser()

    return parser.parse(
        html,
        "https://example.com",
    )


def test_uses_og_description_first():
    html = """
    <html>
        <head>
            <meta
                name="description"
                content="Standard meta description."
            >

            <meta
                property="og:description"
                content="Open Graph description."
            >
        </head>
        <body>
            <p>
                This is a visible paragraph that is long enough.
            </p>
        </body>
    </html>
    """

    page = create_page(html)

    extractor = DescriptionExtractor()

    assert extractor.extract(page) == (
        "Open Graph description."
    )


def test_uses_meta_description_when_og_missing():
    html = """
    <html>
        <head>
            <meta
                name="description"
                content="Standard meta description."
            >
        </head>
        <body>
            <p>
                This is a visible paragraph that is long enough.
            </p>
        </body>
    </html>
    """

    page = create_page(html)

    extractor = DescriptionExtractor()

    assert extractor.extract(page) == (
        "Standard meta description."
    )


def test_uses_first_meaningful_paragraph_as_fallback():
    html = """
    <html>
        <body>
            <p>Welcome</p>

            <p>
                Acme Technologies provides enterprise
                software solutions for modern businesses.
            </p>
        </body>
    </html>
    """

    page = create_page(html)

    extractor = DescriptionExtractor()

    assert extractor.extract(page) == (
        "Acme Technologies provides enterprise "
        "software solutions for modern businesses."
    )


def test_returns_none_when_no_description_exists():
    html = """
    <html>
        <body>
            <p>Welcome</p>
            <p>Learn more</p>
        </body>
    </html>
    """

    page = create_page(html)

    extractor = DescriptionExtractor()

    assert extractor.extract(page) is None