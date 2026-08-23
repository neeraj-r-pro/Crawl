import pytest

from crawler.url_manager import URLManager


def test_normalize_root_url():
    result = URLManager.normalize("HTTPS://EXAMPLE.COM")

    assert result == "https://example.com/"


def test_normalize_trailing_slash():
    result = URLManager.normalize("https://example.com/about/")

    assert result == "https://example.com/about"


def test_remove_fragment():
    result = URLManager.normalize("https://example.com/about#team")

    assert result == "https://example.com/about"


def test_remove_default_https_port():
    result = URLManager.normalize("https://example.com:443/about")

    assert result == "https://example.com/about"


def test_preserve_non_default_port():
    result = URLManager.normalize("https://example.com:8443/about")

    assert result == "https://example.com:8443/about"


def test_preserve_query_string():
    result = URLManager.normalize(
        "https://example.com/products?id=123"
    )

    assert result == "https://example.com/products?id=123"


def test_reject_invalid_scheme():
    with pytest.raises(ValueError):
        URLManager.normalize("ftp://example.com")


def test_reject_empty_url():
    with pytest.raises(ValueError):
        URLManager.normalize("")


def test_same_domain():
    assert URLManager.is_same_domain(
        "https://example.com/about",
        "https://example.com",
    )


def test_different_domain():
    assert not URLManager.is_same_domain(
        "https://other.com/about",
        "https://example.com",
    )