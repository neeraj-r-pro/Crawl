import pytest
from pydantic import ValidationError

from models.schemas import Company


def test_valid_company():
    company = Company(
        name="Example Corporation",
        website="https://example.com",
        description="Example company",
        products=["Product A"],
        services=["Consulting"],
        locations=["Kochi"],
    )

    assert company.name == "Example Corporation"
    assert str(company.website) == "https://example.com/"
    assert company.products == ["Product A"]
    assert company.services == ["Consulting"]
    assert company.locations == ["Kochi"]


def test_invalid_website():
    with pytest.raises(ValidationError):
        Company(
            name="Example Corporation",
            website="not-a-valid-url",
        )


def test_optional_fields_have_defaults():
    company = Company(
        name="Example Corporation",
        website="https://example.com",
    )

    assert company.description is None
    assert company.products == []
    assert company.services == []
    assert company.solutions == []
    assert company.industries == []
    assert company.locations == []
    assert company.contact.emails == []
    assert company.contact.phone_numbers == []
    assert company.contact.addresses == []
    assert company.social_profiles == []