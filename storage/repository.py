from sqlalchemy import select
from sqlalchemy.orm import Session

from models.schemas import Company
from storage.database import engine
from storage.models import CompanyRecord


class CompanyRepository:
    """Persist Company objects using SQLAlchemy."""

    def save(self, company: Company) -> CompanyRecord:
        with Session(engine) as session:
            existing = session.scalar(
                select(CompanyRecord).where(
                    CompanyRecord.website == str(company.website)
                )
            )

            # Convert Pydantic models and HttpUrl values
            # into JSON-compatible Python types.
            social_profiles = [
                profile.model_dump(mode="json")
                for profile in company.social_profiles
            ]

            contact = company.contact.model_dump(mode="json")

            if existing:
                record = existing

                record.name = company.name
                record.description = company.description
                record.products = company.products
                record.services = company.services
                record.solutions = company.solutions
                record.industries = company.industries
                record.locations = company.locations
                record.contact = contact
                record.social_profiles = social_profiles

            else:
                record = CompanyRecord(
                    name=company.name,
                    website=str(company.website),
                    description=company.description,
                    products=company.products,
                    services=company.services,
                    solutions=company.solutions,
                    industries=company.industries,
                    locations=company.locations,
                    contact=contact,
                    social_profiles=social_profiles,
                )

                session.add(record)

            session.commit()
            session.refresh(record)

            return record

    def get_by_website(
        self,
        website: str,
    ) -> CompanyRecord | None:
        with Session(engine) as session:
            return session.scalar(
                select(CompanyRecord).where(
                    CompanyRecord.website == website
                )
            )