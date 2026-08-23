from extraction.html_parser import HTMLParser


HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Acme Technologies</title>

    <meta
        name="description"
        content="Acme provides software solutions."
    >

    <meta
        property="og:title"
        content="Acme Technologies | Enterprise Software"
    >

    <meta
        property="og:site_name"
        content="Acme Technologies"
    >

    <meta
        property="og:description"
        content="Enterprise software for modern businesses."
    >

    <meta
        name="application-name"
        content="Acme Portal"
    >
</head>

<body>

    <h1>Our Products</h1>
    <h2>Cloud Platform</h2>

    <p>We build enterprise software.</p>
    <p>We serve businesses worldwide.</p>

    <a href="/about">About Us</a>
    <a href="https://example.com/contact">Contact</a>

</body>
</html>
"""


def test_parse_title():
    parser = HTMLParser()

    result = parser.parse(
        HTML,
        "https://example.com",
    )

    assert result.title == "Acme Technologies"


def test_parse_headings():
    parser = HTMLParser()

    result = parser.parse(
        HTML,
        "https://example.com",
    )

    assert result.headings == [
        "Our Products",
        "Cloud Platform",
    ]


def test_parse_paragraphs():
    parser = HTMLParser()

    result = parser.parse(
        HTML,
        "https://example.com",
    )

    assert result.paragraphs == [
        "We build enterprise software.",
        "We serve businesses worldwide.",
    ]


def test_convert_relative_links_to_absolute():
    parser = HTMLParser()

    result = parser.parse(
        HTML,
        "https://example.com",
    )

    assert result.links[0].url == "https://example.com/about"
    assert result.links[0].link_type == "page"

    assert result.links[1].url == "https://example.com/contact"
    assert result.links[1].link_type == "page"


def test_parse_meta_description():
    parser = HTMLParser()

    result = parser.parse(
        HTML,
        "https://example.com",
    )

    assert result.meta_description == (
        "Acme provides software solutions."
    )


def test_classify_special_links():
    html = """
    <html>
        <body>
            <a href="mailto:sales@example.com">Email</a>
            <a href="tel:+919876543210">Call</a>
            <a href="https://linkedin.com/company/example">
                LinkedIn
            </a>
            <a href="javascript:void(0)">Action</a>
            <a href="/about">About</a>
        </body>
    </html>
    """

    parser = HTMLParser()

    result = parser.parse(
        html,
        "https://example.com",
    )

    assert result.links[0].url == "mailto:sales@example.com"
    assert result.links[0].link_type == "email"

    assert result.links[1].url == "tel:+919876543210"
    assert result.links[1].link_type == "phone"

    assert result.links[2].link_type == "social"

    assert result.links[3].link_type == "other"

    assert result.links[4].url == "https://example.com/about"
    assert result.links[4].link_type == "page"


def test_parse_social_metadata():
    parser = HTMLParser()

    result = parser.parse(
        HTML,
        "https://example.com",
    )

    assert result.og_title == (
        "Acme Technologies | Enterprise Software"
    )

    assert result.og_site_name == "Acme Technologies"

    assert result.og_description == (
        "Enterprise software for modern businesses."
    )

    assert result.application_name == "Acme Portal"