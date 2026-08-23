from extraction.company_name import CompanyNameExtractor
from extraction.contact import ContactExtractor
from extraction.description import DescriptionExtractor
from extraction.html_parser import ParsedPage
from models.schemas import Company, ContactInfo


class CompanyExtractor:
    """Build a Company model from a parsed webpage."""

    def __init__(self):
        self.name_extractor = CompanyNameExtractor()
        self.contact_extractor = ContactExtractor()
        self.description_extractor = DescriptionExtractor()

    def extract(self, page: ParsedPage) -> Company:
        name = self.name_extractor.extract(page)

        description = self.description_extractor.extract(page)

        contact_data = self.contact_extractor.extract(page)

        return Company(
            name=name or "Unknown Company",
            website=page.url,
            description=description,
            products=[],
            services=[],
            solutions=[],
            industries=[],
            locations=[],
            contact=ContactInfo(
                emails=contact_data["emails"],
                phone_numbers=contact_data["phone_numbers"],
                addresses=contact_data["addresses"],
            ),
            social_profiles=[],
        )