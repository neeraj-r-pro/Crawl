from crawler import page_classifier


def test_classify_home():
    assert page_classifier.classify_from_url("https://example.com/") == "home"


def test_classify_about():
    assert page_classifier.classify_from_url("https://example.com/about-us") == "about"


def test_classify_contact_beats_generic_company_word():
    # "contact" should win even if "company" appears elsewhere in path
    assert page_classifier.classify_from_url("https://example.com/company/contact") == "contact"


def test_classify_products():
    assert page_classifier.classify_from_url("https://example.com/products/pumps") == "products"


def test_classify_unknown_defaults_to_other():
    assert page_classifier.classify_from_url("https://example.com/random-page-xyz") == "other"


def test_classify_uses_anchor_text_when_url_uninformative():
    result = page_classifier.classify_from_url("https://example.com/p/12", anchor_text="Contact Us")
    assert result == "contact"


def test_classify_from_content_overrides_weak_url_guess():
    result = page_classifier.classify_from_content(
        "https://example.com/p/12", title="About Our Company", h1="", current_guess="other"
    )
    assert result == "about"


def test_is_worth_crawling_rejects_pdf():
    assert not page_classifier.is_worth_crawling("https://example.com/brochure.pdf")


def test_is_worth_crawling_rejects_login():
    assert not page_classifier.is_worth_crawling("https://example.com/login")


def test_is_worth_crawling_accepts_normal_page():
    assert page_classifier.is_worth_crawling("https://example.com/about")


def test_priority_score_favors_priority_categories_then_shallow_depth():
    home_shallow = page_classifier.priority_score("home", 0)
    other_shallow = page_classifier.priority_score("other", 0)
    about_deep = page_classifier.priority_score("about", 2)
    assert home_shallow < other_shallow
    assert home_shallow < about_deep


def test_nested_industry_segment_wins_over_broader_solutions_match():
    # Reproduces the exact GitHub bug: /solutions/industry/healthcare
    # contains the substring "solution" (which would otherwise match
    # first) AND the more specific "/industry/" segment -- the more
    # specific signal must win so industry pages are actually classified
    # (and therefore extracted) as industries, not lumped into solutions.
    assert page_classifier.classify_from_url(
        "https://github.com/solutions/industry/healthcare"
    ) == "industries"
    assert page_classifier.classify_from_url(
        "https://github.com/solutions/industry/financial-services"
    ) == "industries"
    assert page_classifier.classify_from_url(
        "https://github.com/solutions/industry"
    ) == "industries"


def test_plain_solutions_path_without_industry_segment_still_classified_as_solutions():
    assert page_classifier.classify_from_url(
        "https://acme.example/solutions/data-migration"
    ) == "solutions"


def test_blog_article_with_incidental_keyword_substring_not_misclassified():
    # Reproduces a real false positive found on a live BONC Network
    # crawl: an article slug containing "...shaping-industry-2026..."
    # was misclassified as an industries-taxonomy page via a loose
    # substring match on "industr", purely because "blog_news" was
    # checked last. blog/news URL conventions now take priority.
    assert page_classifier.classify_from_url(
        "https://www.boncnetwork.com/articles/generative-ai-shaping-industry-2026-89b22570"
    ) == "blog_news"


def test_genuine_industries_page_still_classified_correctly_after_reorder():
    assert page_classifier.classify_from_url("https://acme.example/industries") == "industries"
    assert page_classifier.classify_from_url(
        "https://acme.example/solutions/industry/healthcare"
    ) == "industries"
