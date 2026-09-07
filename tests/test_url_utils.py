from crawler import url_utils


def test_relative_url_resolution():
    assert url_utils.normalize_url("/about", base="https://example.com/") == "https://example.com/about"


def test_fragment_is_stripped_for_dedup():
    a = url_utils.normalize_url("https://example.com/about#team")
    b = url_utils.normalize_url("https://example.com/about")
    assert a == b


def test_trailing_slash_root_normalizes():
    a = url_utils.normalize_url("https://example.com")
    b = url_utils.normalize_url("https://example.com/")
    assert a == b == "https://example.com/"


def test_tracking_params_stripped():
    a = url_utils.normalize_url("https://example.com/products?utm_source=fb&utm_medium=cpc")
    b = url_utils.normalize_url("https://example.com/products")
    assert a == b


def test_meaningful_query_params_preserved():
    a = url_utils.normalize_url("https://example.com/products?category=pumps")
    b = url_utils.normalize_url("https://example.com/products")
    assert a != b


def test_query_param_order_normalized():
    a = url_utils.normalize_url("https://example.com/p?b=2&a=1")
    b = url_utils.normalize_url("https://example.com/p?a=1&b=2")
    assert a == b


def test_mailto_and_tel_rejected():
    assert url_utils.normalize_url("mailto:info@example.com") is None
    assert url_utils.normalize_url("tel:+911234567890") is None
    assert url_utils.normalize_url("javascript:void(0)") is None
    assert url_utils.normalize_url("#top") is None


def test_non_http_scheme_rejected():
    assert url_utils.normalize_url("ftp://example.com/file") is None


def test_case_insensitive_scheme_and_host():
    a = url_utils.normalize_url("HTTPS://Example.COM/About")
    assert a == "https://example.com/About"  # host lowercased, path case preserved


def test_is_same_site_handles_www():
    assert url_utils.is_same_site("https://www.example.com/x", "https://example.com/")
    assert url_utils.is_same_site("https://example.com/x", "https://www.example.com/")


def test_is_same_site_rejects_unrelated_subdomain():
    assert not url_utils.is_same_site("https://blog.example.com/x", "https://example.com/")


def test_is_same_site_rejects_other_domain():
    assert not url_utils.is_same_site("https://other.com/x", "https://example.com/")


def test_non_html_extension_detected():
    assert url_utils.has_non_html_extension("https://example.com/brochure.pdf")
    assert url_utils.has_non_html_extension("https://example.com/logo.PNG")
    assert not url_utils.has_non_html_extension("https://example.com/about")


def test_skip_path_keywords_detected():
    assert url_utils.looks_like_skip_path("https://example.com/login")
    assert url_utils.looks_like_skip_path("https://example.com/blog/tag/news")
    assert not url_utils.looks_like_skip_path("https://example.com/about")
