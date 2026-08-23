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

    assert result.links == [
        "https://example.com/about",
        "https://example.com/contact",
    ]


def test_parse_meta_description():
    parser = HTMLParser()

    result = parser.parse(
        HTML,
        "https://example.com",
    )

    assert result.meta_description == (
        "Acme provides software solutions."
    )