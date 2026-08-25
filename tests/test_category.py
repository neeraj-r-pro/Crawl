from extraction.category import CategoryExtractor
from extraction.html_parser import HTMLParser


def parse_page(
    html: str,
    url: str = "https://example.com/",
):
    parser = HTMLParser()
    return parser.parse(html, url)


def test_extract_products_from_products_page():
    page = parse_page(
        """
        <html>
        <head>
            <title>Products</title>
        </head>
        <body>
            <h1>Products</h1>
            <p>Cloud Platform</p>
            <p>Analytics Platform</p>
        </body>
        </html>
        """,
        "https://example.com/products",
    )

    extractor = CategoryExtractor()

    result = extractor.extract(page)

    assert result["products"] == [
        "Cloud Platform",
        "Analytics Platform",
    ]


def test_extract_services_from_services_page():
    page = parse_page(
        """
        <html>
        <head>
            <title>Our Services</title>
        </head>
        <body>
            <h1>Services</h1>
            <p>Consulting</p>
            <p>Cloud Migration</p>
        </body>
        </html>
        """,
        "https://example.com/services",
    )

    extractor = CategoryExtractor()

    result = extractor.extract(page)

    assert result["services"] == [
        "Consulting",
        "Cloud Migration",
    ]


def test_extract_solutions_from_heading():
    page = parse_page(
        """
        <html>
        <head>
            <title>What We Do</title>
        </head>
        <body>
            <h1>Solutions</h1>
            <p>Business Automation</p>
            <p>Digital Transformation</p>
        </body>
        </html>
        """,
    )

    extractor = CategoryExtractor()

    result = extractor.extract(page)

    assert result["solutions"] == [
        "Business Automation",
        "Digital Transformation",
    ]


def test_extract_industries():
    page = parse_page(
        """
        <html>
        <body>
            <h1>Industries We Serve</h1>
            <p>Healthcare</p>
            <p>Financial Services</p>
        </body>
        </html>
        """,
        "https://example.com/industries",
    )

    extractor = CategoryExtractor()

    result = extractor.extract(page)

    assert result["industries"] == [
        "Healthcare",
        "Financial Services",
    ]


def test_extract_locations():
    page = parse_page(
        """
        <html>
        <body>
            <h1>Our Locations</h1>
            <p>Kochi</p>
            <p>Bangalore</p>
        </body>
        </html>
        """,
        "https://example.com/locations",
    )

    extractor = CategoryExtractor()

    result = extractor.extract(page)

    assert result["locations"] == [
        "Kochi",
        "Bangalore",
    ]


def test_irrelevant_page_returns_empty_categories():
    page = parse_page(
        """
        <html>
        <head>
            <title>About Us</title>
        </head>
        <body>
            <h1>About Our Company</h1>
            <p>We have been operating since 2010.</p>
        </body>
        </html>
        """,
        "https://example.com/about",
    )

    extractor = CategoryExtractor()

    result = extractor.extract(page)

    assert result == {
        "products": [],
        "services": [],
        "solutions": [],
        "industries": [],
        "locations": [],
    }

def test_extract_service_names_from_headings():
    page = parse_page(
        """
        <html>
        <head>
            <title>Our Services</title>
        </head>
        <body>
            <h1>Services</h1>

            <h2>Installation</h2>
            <h2>Annual Maintenance</h2>
            <h2>Technical Support</h2>
            <h2>System Integration</h2>
        </body>
        </html>
        """,
        "https://example.com/services",
    )

    extractor = CategoryExtractor()

    result = extractor.extract(page)

    assert result["services"] == [
        "Installation",
        "Annual Maintenance",
        "Technical Support",
        "System Integration",
    ]


def test_ignore_contact_and_footer_text_from_services():
    page = parse_page(
        """
        <html>
        <head>
            <title>Services</title>
        </head>
        <body>
            <h1>Services</h1>

            <p>Installation</p>
            <p>Technical Support</p>

            <p>Email: support@example.com</p>
            <p>Phone: +91 9876543210</p>
            <p>Contact Us</p>
            <p>© 2025 Example Company. All rights reserved.</p>
        </body>
        </html>
        """,
        "https://example.com/services",
    )

    extractor = CategoryExtractor()

    result = extractor.extract(page)

    assert result["services"] == [
        "Installation",
        "Technical Support",
    ]


def test_deduplicate_services():
    page = parse_page(
        """
        <html>
        <head>
            <title>Services</title>
        </head>
        <body>
            <h1>Services</h1>

            <h2>Installation</h2>
            <p>Installation</p>
            <p>installation</p>

            <h2>Technical Support</h2>
        </body>
        </html>
        """,
        "https://example.com/services",
    )

    extractor = CategoryExtractor()

    result = extractor.extract(page)

    assert result["services"] == [
        "Installation",
        "Technical Support",
    ]

def test_ignore_non_product_content_from_products_page():
    page = parse_page(
        """
        <html>
        <head>
            <title>Products</title>
        </head>
        <body>
            <h1>Products</h1>

            <p>CCTV</p>
            <p>Remote Gate</p>
            <p>Video Door Phone</p>

            <p>Welcome to NOVACHIP</p>
            <p>Our Mission</p>
            <p>Our Vision</p>
            <p>Our Address</p>
            <p>Contact Info</p>
            <p>No products found.</p>
        </body>
        </html>
        """,
        "https://example.com/products",
    )

    extractor = CategoryExtractor()

    result = extractor.extract(page)

    assert result["products"] == [
        "CCTV",
        "Remote Gate",
        "Video Door Phone",
    ]


def test_ignore_long_product_description():
    page = parse_page(
        """
        <html>
        <head>
            <title>Products</title>
        </head>
        <body>
            <h1>Products</h1>

            <p>CCTV</p>
            <p>
                Experts in office and home automation, we provide
                reliable sales and service of smart automation
                solutions that keep your operations running smoothly.
            </p>
            <p>Automatic Doors</p>
        </body>
        </html>
        """,
        "https://example.com/products",
    )

    extractor = CategoryExtractor()

    result = extractor.extract(page)

    assert result["products"] == [
        "CCTV",
        "Automatic Doors",
    ]