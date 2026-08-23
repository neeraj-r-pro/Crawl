from extraction.company_name import CompanyNameExtractor
from extraction.html_parser import HTMLParser


def create_page(html: str):
    parser = HTMLParser()

    return parser.parse(
        html,
        "https://example.com",
    )


def test_uses_og_site_name_first():
    html = """
    <html>
        <head>
            <title>Wrong Title | Something</title>
            <meta
                property="og:site_name"
                content="Acme Technologies"
            >
        </head>
        <body>
            <h1>Enterprise Software</h1>
        </body>
    </html>
    """

    page = create_page(html)

    extractor = CompanyNameExtractor()

    assert extractor.extract(page) == "Acme Technologies"


def test_uses_application_name_when_site_name_missing():
    html = """
    <html>
        <head>
            <meta
                name="application-name"
                content="Acme Technologies"
            >
        </head>
        <body>
            <h1>Enterprise Software</h1>
        </body>
    </html>
    """

    page = create_page(html)

    extractor = CompanyNameExtractor()

    assert extractor.extract(page) == "Acme Technologies"


def test_extracts_name_from_title():
    html = """
    <html>
        <head>
            <title>Acme Technologies | Enterprise Software</title>
        </head>
    </html>
    """

    page = create_page(html)

    extractor = CompanyNameExtractor()

    assert extractor.extract(page) == "Acme Technologies"


def test_uses_first_heading_as_fallback():
    html = """
    <html>
        <body>
            <h1>Acme Technologies</h1>
        </body>
    </html>
    """

    page = create_page(html)

    extractor = CompanyNameExtractor()

    assert extractor.extract(page) == "Acme Technologies"


def test_returns_none_when_no_name_found():
    html = """
    <html>
        <body>
            <p>Welcome to our website.</p>
        </body>
    </html>
    """

    page = create_page(html)

    extractor = CompanyNameExtractor()

    assert extractor.extract(page) is None