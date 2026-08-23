from models.schemas import Company, ContactInfo, SocialProfile
from extraction.company_merger import CompanyMerger


def create_company(
    description=None,
    products=None,
    services=None,
    emails=None,
):
    return Company(
        name="Acme Technologies",
        website="https://acme.com/",
        description=description,
        products=products or [],
        services=services or [],
        solutions=[],
        industries=[],
        locations=[],
        contact=ContactInfo(
            emails=emails or [],
            phone_numbers=[],
            addresses=[],
        ),
        social_profiles=[],
    )


def test_first_company_is_returned():
    merger = CompanyMerger()

    company = create_company(
        description="Enterprise software company."
    )

    result = merger.merge(None, company)

    assert result is company


def test_description_is_preserved():
    merger = CompanyMerger()

    current = create_company(
        description="Original description."
    )

    new = create_company(
        description="New description."
    )

    result = merger.merge(current, new)

    assert result.description == "Original description."


def test_new_description_fills_missing_description():
    merger = CompanyMerger()

    current = create_company()

    new = create_company(
        description="Enterprise software company."
    )

    result = merger.merge(current, new)

    assert result.description == (
        "Enterprise software company."
    )


def test_products_are_merged():
    merger = CompanyMerger()

    current = create_company(
        products=["Cloud Platform"]
    )

    new = create_company(
        products=["AI Platform", "Cloud Platform"]
    )

    result = merger.merge(current, new)

    assert result.products == [
        "Cloud Platform",
        "AI Platform",
    ]


def test_services_are_merged():
    merger = CompanyMerger()

    current = create_company(
        services=["Consulting"]
    )

    new = create_company(
        services=["Cloud Migration"]
    )

    result = merger.merge(current, new)

    assert result.services == [
        "Consulting",
        "Cloud Migration",
    ]


def test_contacts_are_merged():
    merger = CompanyMerger()

    current = create_company(
        emails=["sales@acme.com"]
    )

    new = create_company(
        emails=[
            "info@acme.com",
            "sales@acme.com",
        ]
    )

    result = merger.merge(current, new)

    assert result.contact.emails == [
        "sales@acme.com",
        "info@acme.com",
    ]