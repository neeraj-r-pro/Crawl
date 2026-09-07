from crawler.crawler import aggregate_company_info
from crawler.extractor import ExtractedPage


def make_page(**kwargs) -> ExtractedPage:
    defaults = dict(
        title=None, h1=None, meta_description=None, visible_text_sample=None,
        emails=[], phones=[], social_links={}, address_candidates=[],
        heading_list_items=[], company_name_guess=None, is_thin_content=False,
    )
    defaults.update(kwargs)
    return ExtractedPage(**defaults)


def test_company_name_prefers_about_over_other_pages():
    pages = [
        ("other", make_page(company_name_guess="Random Blog Title")),
        ("about", make_page(company_name_guess="Acme Pumps Pvt Ltd")),
    ]
    company = aggregate_company_info("https://acmepumps.com/", pages)
    assert company.company_name == "Acme Pumps Pvt Ltd"


def test_description_prefers_about_page():
    pages = [
        ("home", make_page(meta_description="Home page tagline.")),
        ("about", make_page(meta_description="Full company description here.")),
    ]
    company = aggregate_company_info("https://acmepumps.com/", pages)
    assert company.description == "Full company description here."


def test_headquarters_from_contact_or_about_first():
    pages = [
        ("about", make_page(address_candidates=["Coimbatore HQ address"])),
        ("contact", make_page(address_candidates=["Dubai branch address"])),
    ]
    company = aggregate_company_info("https://acmepumps.com/", pages)
    assert company.headquarters == "Coimbatore HQ address"
    assert "Dubai branch address" in company.other_locations


def test_products_deduped_case_insensitively_across_pages():
    pages = [
        ("products", make_page(heading_list_items=["Centrifugal Pumps", "Submersible Pumps"])),
        ("products", make_page(heading_list_items=["centrifugal pumps", "Pressure Valves"])),
    ]
    company = aggregate_company_info("https://acmepumps.com/", pages)
    names_lower = [p.lower() for p in company.products]
    assert names_lower.count("centrifugal pumps") == 1
    assert "submersible pumps" in names_lower
    assert "pressure valves" in names_lower


def test_emails_and_phones_merged_across_pages():
    pages = [
        ("home", make_page(emails=["info@acme.com"], phones=["+91 422 2345678"])),
        ("contact", make_page(emails=["sales@acme.com", "info@acme.com"], phones=["+971 4 123 4567"])),
    ]
    company = aggregate_company_info("https://acmepumps.com/", pages)
    assert set(company.emails) == {"info@acme.com", "sales@acme.com"}
    assert len(company.phones) == 2


def test_emails_from_untrusted_page_types_excluded():
    # A /products/<item> or /project/<name> page can legitimately contain
    # a THIRD PARTY email (e.g. a package maintainer's personal address on
    # a registry listing) -- that must not be attributed to the company.
    pages = [
        ("home", make_page(emails=["info@acme.com"])),
        ("products", make_page(emails=["random.maintainer@personalmail.com"])),
        ("projects", make_page(emails=["client-contact@othercompany.com"])),
    ]
    company = aggregate_company_info("https://acmepumps.com/", pages)
    assert company.emails == ["info@acme.com"]
    assert "random.maintainer@personalmail.com" not in company.emails
    assert "client-contact@othercompany.com" not in company.emails


def test_social_links_first_seen_wins():
    pages = [
        ("home", make_page(social_links={"linkedin": "https://linkedin.com/company/acme"})),
        ("about", make_page(social_links={"linkedin": "https://linkedin.com/company/acme-duplicate"})),
    ]
    company = aggregate_company_info("https://acmepumps.com/", pages)
    assert company.social_links["linkedin"] == "https://linkedin.com/company/acme"


def test_missing_fields_default_sensibly():
    company = aggregate_company_info("https://acmepumps.com/", [])
    assert company.company_name is None
    assert company.headquarters is None
    assert company.products == []
    assert company.website == "https://acmepumps.com/"
