from pathlib import Path

from bs4 import BeautifulSoup

from crawler import extractor
from crawler.dynamic_fetcher import looks_like_js_shell

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_company_name_from_og_site_name():
    html = load("home.html")
    result = extractor.extract(html, "https://acmepumps.com/")
    assert result.company_name_guess == "Acme Pumps Pvt Ltd"


def test_meta_description_extracted():
    html = load("home.html")
    result = extractor.extract(html, "https://acmepumps.com/")
    assert "industrial pumps" in result.meta_description.lower()


def test_emails_extracted_and_deduped():
    html = load("about.html")
    result = extractor.extract(html, "https://acmepumps.com/about")
    assert "sales@acmepumps.com" in result.emails


def test_email_in_footer_extracted():
    html = load("home.html")
    result = extractor.extract(html, "https://acmepumps.com/")
    assert "info@acmepumps.com" in result.emails


def test_phones_extracted_with_international_format():
    html = load("about.html")
    result = extractor.extract(html, "https://acmepumps.com/about")
    assert len(result.phones) >= 1
    # at least one candidate should contain the country code digits
    assert any("91" in p or "971" in p for p in result.phones)


def test_social_links_extracted():
    html = load("home.html")
    result = extractor.extract(html, "https://acmepumps.com/")
    assert result.social_links.get("linkedin") == "https://www.linkedin.com/company/acme-pumps"
    assert result.social_links.get("twitter") == "https://twitter.com/acmepumps"


def test_address_candidates_found():
    html = load("about.html")
    result = extractor.extract(html, "https://acmepumps.com/about")
    assert any("Coimbatore" in a for a in result.address_candidates)


def test_heading_items_captured_for_products_page():
    html = load("products.html")
    result = extractor.extract(html, "https://acmepumps.com/products")
    assert "Centrifugal Pumps" in result.heading_list_items


def test_thin_content_flagged_for_spa_shell():
    html = load("spa_shell.html")
    result = extractor.extract(html, "https://spa-example.com/")
    assert result.is_thin_content is True


def test_full_page_not_flagged_as_thin():
    html = load("about.html")
    result = extractor.extract(html, "https://acmepumps.com/about")
    assert result.is_thin_content is False


def test_js_shell_detection_true_for_spa():
    html = load("spa_shell.html")
    assert looks_like_js_shell(html) is True


def test_js_shell_detection_false_for_real_content():
    html = load("about.html")
    assert looks_like_js_shell(html) is False


def test_invalid_email_filtered_out():
    # example.com is a reserved placeholder domain (RFC 2606) commonly left
    # over in templates/boilerplate -- filtered out as noise, not a real
    # contact. icon@site.png is an image filename mis-caught by a naive
    # regex -- also filtered.
    html = "<html><body>Contact webmaster@realcompany.io or icon@site.png</body></html>"
    result = extractor.extract(html, "https://x.com/")
    assert "webmaster@realcompany.io" in result.emails
    assert not any(e.endswith(".png") for e in result.emails)


def test_placeholder_example_domain_filtered_out():
    html = "<html><body>Contact test@example.com</body></html>"
    result = extractor.extract(html, "https://x.com/")
    assert "test@example.com" not in result.emails


def test_company_name_falls_back_to_domain_when_nothing_else_found():
    html = "<html><head></head><body>No title, no meta.</body></html>"
    result = extractor.extract(html, "https://www.brightsolutions.io/")
    assert result.company_name_guess == "Brightsolutions"


def test_placeholder_you_at_company_email_filtered_out():
    html = "<html><body>e.g. mailto snippet: you@company.com or your@domain.com</body></html>"
    result = extractor.extract(html, "https://x.com/")
    assert "you@company.com" not in result.emails
    assert "your@domain.com" not in result.emails


def test_social_link_to_own_domain_not_misdetected():
    # crawling github.com itself: an internal link to github.com/features
    # must NOT be reported as a "github" social profile link.
    html = '<html><body><a href="https://github.com/features/actions">Actions</a></body></html>'
    result = extractor.extract(html, "https://github.com/")
    assert "github" not in result.social_links


def test_social_link_to_other_org_github_profile_still_detected():
    html = '<html><body><a href="https://github.com/octocat">Follow us</a></body></html>'
    result = extractor.extract(html, "https://acmepumps.com/")
    assert result.social_links.get("github") == "https://github.com/octocat"


def test_footer_boilerplate_excluded_from_product_headings():
    html = """
    <html><body>
      <nav><h2>Support</h2><h2>Company</h2></nav>
      <main><h2>Centrifugal Pumps</h2></main>
      <footer><h2>Careers</h2><ul><li><a href="/x">Site-wide Links</a></li></ul></footer>
    </body></html>
    """
    result = extractor.extract(html, "https://acmepumps.com/products")
    assert "Centrifugal Pumps" in result.heading_list_items
    assert "Support" not in result.heading_list_items
    assert "Careers" not in result.heading_list_items


def test_b2b_directory_profile_template_boilerplate_excluded():
    # Reproduces a real false-positive: a single-page "company profile"
    # template (common for Indian B2B directory listings) where About Us,
    # credentials (GST/PAN), and the real product list are all siblings
    # in the same <main> content -- not separated into nav/footer at all.
    html = """
    <html><head><title>ALFA AQUA SOLUTION CHEM INDUSTRY</title></head>
    <body>
      <main>
        <h1>ALFA AQUA SOLUTION CHEM INDUSTRY</h1>
        <h2>About Us</h2>
        <h2>Description</h2>
        <h2>Vision</h2>
        <h2>Why Choose Us</h2>
        <h2>GST</h2>
        <h2>PAN Number</h2>
        <h2>Explore by Industry</h2>
        <ul>
          <li><a href="/i/chemicals">Chemicals</a></li>
          <li><a href="/i/textiles">Textiles</a></li>
        </ul>
        <h2>Water Treatment Chemicals</h2>
        <h2>Industrial Detergents</h2>
      </main>
    </body></html>
    """
    result = extractor.extract(html, "https://alfaaqua.example/")
    items_lower = [i.lower() for i in result.heading_list_items]

    # real offerings should survive
    assert "water treatment chemicals" in items_lower
    assert "industrial detergents" in items_lower
    assert "chemicals" in items_lower
    assert "textiles" in items_lower

    # template noise should all be filtered
    for noise in ("about us", "description", "vision", "why choose us",
                  "gst", "pan number", "explore by industry",
                  "alfa aqua solution chem industry"):
        assert noise not in items_lower, f"{noise!r} should have been filtered out"


# ---------------------------------------------------------------------------
# Listing/marketplace-aware extraction (extract_listing_items):
# real products vs company names, CTA text, metadata; services vs prose;
# industries vs business listings; solutions vs company names containing
# "solution"; phone extraction (visible text + tel: links); headquarters/
# address extraction; duplicate entities; generic non-marketplace sites.
# ---------------------------------------------------------------------------

def test_products_extracted_from_card_grid_marketplace_page():
    # A repeated card grid is the generic structural signal used to find
    # product names on marketplace/listing-style pages, WITHOUT keyword
    # matching on the word "product" anywhere.
    html = """
    <html><body>
      <div class="results">
        <div class="product-card">
          <h3>Centrifugal Water Pump</h3>
          <span class="badge">GST Verified</span>
          <a href="/quote">Ask for Quote</a>
        </div>
        <div class="product-card">
          <h3>Submersible Dewatering Pump</h3>
          <span class="badge">Verified Supplier</span>
          <a href="/quote">Ask for Quote</a>
        </div>
        <div class="product-card">
          <h3>Industrial Diaphragm Pump</h3>
          <span class="badge">Trusted Seller</span>
          <a href="/quote">Get Best Price</a>
        </div>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = extractor.extract_listing_items(soup, "products")
    items_lower = [i.lower() for i in items]

    assert "centrifugal water pump" in items_lower
    assert "submersible dewatering pump" in items_lower
    assert "industrial diaphragm pump" in items_lower
    for noise in ("gst verified", "verified supplier", "trusted seller",
                  "ask for quote", "get best price"):
        assert noise not in items_lower


def test_company_names_excluded_from_product_cards():
    # Reproduces the exact reported bug: a marketplace/directory page
    # whose "product" cards actually list SUPPLIER BUSINESSES, not the
    # crawled site's own products -- those business names must not leak
    # into the products list.
    html = """
    <html><body>
      <div class="listing">
        <div class="card">
          <h3>ALFA AQUA SOLUTION CHEM INDUSTRY</h3>
          <p>Mumbai, Maharashtra</p>
          <a href="/business/alfa">View Profile</a>
        </div>
        <div class="card">
          <h3>SHREE BALAJI TRADING CO</h3>
          <p>Pune, Maharashtra</p>
          <a href="/business/shree-balaji">View Profile</a>
        </div>
        <div class="card">
          <h3>Water Treatment Chemicals</h3>
          <p>Bulk supply available</p>
          <a href="/products/water-treatment-chemicals">Know More</a>
        </div>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = extractor.extract_listing_items(soup, "products")
    items_lower = [i.lower() for i in items]

    assert "water treatment chemicals" in items_lower
    assert "alfa aqua solution chem industry" not in items_lower
    assert "shree balaji trading co" not in items_lower
    assert "mumbai, maharashtra" not in items_lower
    assert "view profile" not in items_lower


def test_products_vs_cta_and_metadata_text():
    html = """
    <html><body>
      <div class="grid">
        <div class="tile"><h4>Stainless Steel Ball Valve</h4><span>MOQ: 100 units</span><a href="/x">Send Inquiry</a></div>
        <div class="tile"><h4>Brass Gate Valve</h4><span>Established 1998</span><a href="/y">Contact Supplier</a></div>
        <div class="tile"><h4>PVC Check Valve</h4><span>4.5 out of 5</span><a href="/z">Call Now</a></div>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = [i.lower() for i in extractor.extract_listing_items(soup, "products")]
    assert "stainless steel ball valve" in items
    assert "brass gate valve" in items
    assert "pvc check valve" in items
    for noise in ("moq: 100 units", "established 1998", "4.5 out of 5",
                  "send inquiry", "contact supplier", "call now"):
        assert noise not in items


def test_services_extracted_from_feature_tiles():
    # Services rendered as icon+title feature tiles (no headings at all
    # on the page otherwise) -- same repeated-card mechanism as products,
    # confirming service detection isn't hardcoded to any specific site.
    html = """
    <html><body>
      <div class="features">
        <div class="feature-tile"><h3>AMC & Maintenance Support</h3></div>
        <div class="feature-tile"><h3>On-site Installation</h3></div>
        <div class="feature-tile"><h3>24x7 Technical Helpdesk</h3></div>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = [i.lower() for i in extractor.extract_listing_items(soup, "services")]
    assert "amc & maintenance support" in items
    assert "on-site installation" in items
    assert "24x7 technical helpdesk" in items


def test_services_not_polluted_by_ordinary_paragraphs():
    html = """
    <html><body>
      <main>
        <h2>Our Services</h2>
        <p>We have been proudly serving customers across India since 2005,
        building long-term relationships based on trust and quality.</p>
        <div class="tile"><h3>Custom Fabrication</h3></div>
        <div class="tile"><h3>Equipment Repair</h3></div>
        <div class="tile"><h3>Onsite Consulting</h3></div>
      </main>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = [i.lower() for i in extractor.extract_listing_items(soup, "services")]
    assert "custom fabrication" in items
    assert "equipment repair" in items
    assert "onsite consulting" in items
    assert not any("proudly serving customers" in i for i in items)


def test_industries_from_taxonomy_links_excludes_business_listing_names():
    # Reproduces the "Eveout" false positive: a taxonomy/category widget
    # (links to a categories/industries filter) sits above a RESULTS
    # section listing individual businesses -- only the taxonomy links
    # should be treated as industries.
    html = """
    <html><body>
      <div class="category-widget">
        <a href="/industries?filter=textiles">Textiles</a>
        <a href="/industries?filter=chemicals">Chemicals</a>
        <a href="/industries?filter=electronics">Electronics</a>
      </div>
      <div class="results">
        <div class="card"><a href="/business/eveout">Eveout</a></div>
        <div class="card"><a href="/business/acme-textiles">Acme Textiles Pvt Ltd</a></div>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = [i.lower() for i in extractor.extract_listing_items(soup, "industries")]
    assert "textiles" in items
    assert "chemicals" in items
    assert "electronics" in items
    assert "eveout" not in items
    assert "acme textiles pvt ltd" not in items


def test_solutions_excludes_company_name_containing_solution_word():
    # A company whose own name literally contains "Solution" must not be
    # extracted as one of ITS OWN offerings just because the containing
    # page is classified as "solutions".
    html = """
    <html><body>
      <div class="grid">
        <div class="card"><h3>ALFA AQUA SOLUTION CHEM INDUSTRY</h3><a href="/business/alfa">View Profile</a></div>
        <div class="card"><h3>Water Purification Solution</h3><a href="/solutions/water-purification">Learn More</a></div>
        <div class="card"><h3>Industrial Cooling Solution</h3><a href="/solutions/cooling">Learn More</a></div>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = [i.lower() for i in extractor.extract_listing_items(soup, "solutions")]
    assert "water purification solution" in items
    assert "industrial cooling solution" in items
    assert "alfa aqua solution chem industry" not in items


def test_phone_extraction_from_visible_text():
    html = "<html><body><p>Call us at +91 422 2345678 for enquiries.</p></body></html>"
    result = extractor.extract(html, "https://acme.example/contact")
    assert any("422" in p for p in result.phones)


def test_phone_extraction_from_tel_link_with_no_visible_digits():
    # The number is only present as a tel: href behind an icon button --
    # no visible text contains it at all, so only the tel:-link path can
    # recover it.
    html = '<html><body><a href="tel:+911234567890" aria-label="Call"><svg></svg></a></body></html>'
    result = extractor.extract(html, "https://acme.example/contact")
    assert any("1234567890" in p for p in result.phones)


def test_headquarters_extraction_from_registered_office_label():
    html = """
    <html><body>
      <div>Registered Office: Plot 12, MG Road, Pune, Maharashtra 411001</div>
      <div>Branch Office: 5th Cross, Whitefield, Bengaluru, Karnataka</div>
    </body></html>
    """
    result = extractor.extract(html, "https://acme.example/contact")
    assert any("MG Road" in h for h in result.headquarters_candidates)
    assert any("Whitefield" in o for o in result.other_location_candidates)


def test_duplicate_entities_deduped_case_insensitively():
    html = """
    <html><body>
      <div class="grid">
        <div class="card"><h3>Centrifugal Pump</h3></div>
        <div class="card"><h3>centrifugal pump</h3></div>
        <div class="card"><h3>Submersible Pump</h3></div>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items_lower = [i.lower() for i in extractor.extract_listing_items(soup, "products")]
    assert items_lower.count("centrifugal pump") == 1
    assert "submersible pump" in items_lower


def test_generic_site_without_listing_structure_falls_back_gracefully():
    # A simple company site with no card grid and no taxonomy links at
    # all -- extract_listing_items should return empty so the caller
    # falls back to the plain heading scan, not silently break.
    html = """
    <html><body>
      <main>
        <h1>About Acme Engineering</h1>
        <p>We are a family-run engineering firm founded in 1985.</p>
      </main>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = extractor.extract_listing_items(soup, "products")
    assert items == []


def test_metric_stat_callouts_excluded_from_listing_items():
    html = """
    <html><body>
      <div class="grid">
        <div class="card"><h3>70% less time spent on migration efforts</h3></div>
        <div class="card"><h3>500k+ lines of code changed within weeks</h3></div>
        <div class="card"><h3>Cloud Migration Toolkit</h3></div>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = [i.lower() for i in extractor.extract_listing_items(soup, "solutions")]
    assert "cloud migration toolkit" in items
    assert not any("less time spent" in i for i in items)
    assert not any("lines of code" in i for i in items)


def test_self_duplicated_card_caption_artifact_excluded():
    # A common rendering artifact: a customer-logo card's image alt text
    # and adjacent caption both say the same brand name, concatenated by
    # get_text() into "3M 3M" / "Ernst and Young Ernst and Young".
    html = """
    <html><body>
      <div class="grid">
        <div class="card"><h4>3M 3M</h4></div>
        <div class="card"><h4>Ernst and Young Ernst and Young</h4></div>
        <div class="card"><h4>Managed Database Hosting</h4></div>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = [i.lower() for i in extractor.extract_listing_items(soup, "solutions")]
    assert "managed database hosting" in items
    assert "3m 3m" not in items
    assert "ernst and young ernst and young" not in items


def test_long_testimonial_sentence_excluded_from_card_titles():
    html = """
    <html><body>
      <div class="grid">
        <div class="card"><h3>Read how Acme Corp tripled their releases and cut development time by more than half.</h3></div>
        <div class="card"><h3>Automated Release Pipeline</h3></div>
        <div class="card"><h3>Continuous Integration Suite</h3></div>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = [i.lower() for i in extractor.extract_listing_items(soup, "services")]
    assert "automated release pipeline" in items
    assert "continuous integration suite" in items
    assert not any("tripled their releases" in i for i in items)


# ---------------------------------------------------------------------------
# Second-round fixes: listing-metadata contamination (locations,
# availability dates, bare counts, business-role/age labels, placeholder
# duplication), form-field/dropdown stripping, phone range-list rejection,
# URL-derived taxonomy names.
# ---------------------------------------------------------------------------

def test_listing_metadata_chips_excluded_from_products():
    # Reproduces the exact reported BONC false positives: attribute chips
    # (location, availability, a bare count) sitting in their own
    # repeated group, structurally identical to a real card grid.
    html = """
    <html><body>
      <div class="meta-row"><span class="chip">Location KOLKATA</span></div>
      <div class="meta-row"><span class="chip">Available from Jan 2026</span></div>
      <div class="meta-row"><span class="chip">130</span></div>
      <div class="meta-row"><span class="chip">Location NEW DELHI</span></div>
      <div class="meta-row"><span class="chip">Available from Jun 2026</span></div>
      <div class="meta-row"><span class="chip">Location DHANBAD</span></div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    assert extractor.extract_listing_items(soup, "products") == []


def test_business_attribute_chips_excluded_from_solutions():
    html = """
    <html><body>
      <div class="attr-row"><span>Manufacturer</span></div>
      <div class="attr-row"><span>Located in Faridabad , India</span></div>
      <div class="attr-row"><span>Established Since 2017 - 9 years old</span></div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    assert extractor.extract_listing_items(soup, "solutions") == []


def test_bare_category_word_and_placeholder_duplication_excluded_from_industries():
    html = """
    <html><body>
      <div class="card"><h3>Electronics & Electrical this is Electronics & Electrical description</h3></div>
      <div class="card"><h3>Services</h3></div>
      <div class="card"><h3>Located in GURUGRAM , India</h3></div>
      <div class="card"><h3>Established Since 2023 - 3 years old</h3></div>
      <div class="card"><h3>Textiles</h3></div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = extractor.extract_listing_items(soup, "industries")
    assert items == ["Textiles"]


def test_third_party_business_listing_urls_detected():
    from crawler import url_utils
    assert url_utils.is_third_party_listing_url(
        "https://www.boncnetwork.com/business/eveout-business-planning-12345"
    )
    assert url_utils.is_third_party_listing_url(
        "https://www.boncnetwork.com/business/alamdar-international"
    )
    assert not url_utils.is_third_party_listing_url("https://www.boncnetwork.com/about-us")
    assert not url_utils.is_third_party_listing_url("https://www.boncnetwork.com/industries")
    assert not url_utils.is_third_party_listing_url("https://www.boncnetwork.com/business/register")


def test_form_fields_and_dropdown_options_excluded_from_products():
    # Reproduces the GitHub contact-form false positives: required-field
    # labels and a full country dropdown, both inside <form>.
    html = """
    <html><body>
      <div class="grid">
        <div class="card"><h3>Managed Database Hosting</h3></div>
        <div class="card"><h3>Cloud Migration Toolkit</h3></div>
        <div class="card"><h3>Automated Backup Service</h3></div>
      </div>
      <form>
        <label>First name *</label><input>
        <label>Last name *</label><input>
        <label>Work email *</label><input>
        <label>Job title *</label><input>
        <label>Company *</label><input>
        <select>
          <option>Afghanistan</option>
          <option>Albania</option>
          <option>Algeria</option>
        </select>
      </form>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = extractor.extract_listing_items(soup, "products")
    assert "Managed Database Hosting" in items
    assert "Cloud Migration Toolkit" in items
    for noise in ("First name *", "Last name *", "Work email *", "Company *",
                  "Afghanistan", "Albania", "Algeria"):
        assert noise not in items


def test_share_button_text_excluded():
    html = """
    <html><body>
      <div class="grid">
        <div class="card"><h3>Share on Facebook Facebook</h3></div>
        <div class="card"><h3>Share on X X (formerly Twitter)</h3></div>
        <div class="card"><h3>Share on LinkedIn LinkedIn</h3></div>
        <div class="card"><h3>Automated Release Pipeline</h3></div>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = [i.lower() for i in extractor.extract_listing_items(soup, "services")]
    assert "automated release pipeline" in items
    assert not any("share on" in i for i in items)


def test_marketing_imperative_taglines_excluded_from_solutions():
    # Reproduces the exact GitHub tagline false positives.
    html = """
    <html><body>
      <div class="grid">
        <div class="card"><h3>Increase visibility and widen impact</h3></div>
        <div class="card"><h3>Stay in control</h3></div>
        <div class="card"><h3>Modernize at scale</h3></div>
        <div class="card"><h3>Increase collaboration</h3></div>
        <div class="card"><h3>Cloud Backup Solution</h3></div>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = [i.lower() for i in extractor.extract_listing_items(soup, "solutions")]
    assert "cloud backup solution" in items
    for noise in ("increase visibility and widen impact", "stay in control",
                  "modernize at scale", "increase collaboration"):
        assert noise not in items


def test_phone_rejects_employee_count_range_table():
    # Reproduces the exact reported false positive.
    text = "Company size: 10 10-99 100-499 500+ employees"
    assert extractor.extract_phones(text) == []


def test_phone_still_accepts_real_numbers_alongside_range_text():
    text = "Company size 10-99. Call us at +91 422 234 5678 for support."
    phones = extractor.extract_phones(text)
    assert any("422" in p for p in phones)


def test_industry_name_derived_from_url_path():
    assert extractor.derive_taxonomy_name_from_url(
        "https://github.com/solutions/industry/healthcare", "industries"
    ) == "Healthcare"
    assert extractor.derive_taxonomy_name_from_url(
        "https://github.com/solutions/industry/financial-services", "industries"
    ) == "Financial Services"


def test_solution_name_derived_from_url_does_not_leak_industry_segment():
    # /solutions/industry/healthcare must NOT yield "Industry" as a bogus
    # solution name via the solutions-pattern matcher.
    assert extractor.derive_taxonomy_name_from_url(
        "https://github.com/solutions/industry/healthcare", "solutions"
    ) is None
    assert extractor.derive_taxonomy_name_from_url(
        "https://acme.example/solutions/data-migration", "solutions"
    ) == "Data Migration"
