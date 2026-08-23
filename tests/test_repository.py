from pathlib import Path

from models.schemas import Company, ContactInfo, SocialProfile
from storage.database import Base, engine
from storage.repository import CompanyRepository


def setup_function():
    """Reset the database before each test."""

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def create_company() -> Company:
    return Company(
        name="Acme Technologies",
        website="https://acme.com/",
        description="Enterprise software company.",
        products=["Cloud Platform"],
        services=["Consulting"],
        solutions=["Business Automation"],
        industries=["Technology"],
        locations=["Kochi", "Bangalore"],
        contact=ContactInfo(
            emails=["sales@acme.com"],
            phone_numbers=["+919876543210"],
            addresses=["Kochi, Kerala"],
        ),
        social_profiles=[
            SocialProfile(
                platform="linkedin",
                url="https://linkedin.com/company/acme",
            )
        ],
    )


def test_save_company():
    repository = CompanyRepository()

    company = create_company()

    record = repository.save(company)

    assert record.id is not None
    assert record.name == "Acme Technologies"
    assert record.website == "https://acme.com/"
    assert record.description == "Enterprise software company."


def test_get_company_by_website():
    repository = CompanyRepository()

    company = create_company()

    repository.save(company)

    record = repository.get_by_website(
        "https://acme.com/"
    )

    assert record is not None
    assert record.name == "Acme Technologies"


def test_save_updates_existing_company():
    repository = CompanyRepository()

    company = create_company()

    first_record = repository.save(company)

    updated_company = create_company()

    updated_company.description = (
        "Updated enterprise software company."
    )

    second_record = repository.save(updated_company)

    assert first_record.id == second_record.id

    assert second_record.description == (
        "Updated enterprise software company."
    )


def test_get_unknown_company_returns_none():
    repository = CompanyRepository()

    result = repository.get_by_website(
        "https://does-not-exist.example/"
    )

    assert result is None