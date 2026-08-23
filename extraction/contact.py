import re

import phonenumbers
from phonenumbers import NumberParseException

from extraction.html_parser import ParsedPage


class ContactExtractor:
    """Extract contact information from a parsed webpage."""

    EMAIL_PATTERN = re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    )

    def extract(self, page: ParsedPage) -> dict:
        """Extract and return contact information."""

        emails = self._extract_emails(page)
        phone_numbers = self._extract_phone_numbers(page)

        return {
            "emails": emails,
            "phone_numbers": phone_numbers,
            "addresses": [],
        }

    def _extract_emails(self, page: ParsedPage) -> list[str]:
        emails = set()

        for link in page.links:
            if link.link_type == "email":
                email = link.url.replace("mailto:", "").split("?")[0]
                email = email.strip().lower()

                if email:
                    emails.add(email)

        text = " ".join(page.paragraphs)

        for email in self.EMAIL_PATTERN.findall(text):
            emails.add(email.lower())

        return sorted(emails)

    def _extract_phone_numbers(self, page: ParsedPage) -> list[str]:
        phones = set()

        for link in page.links:
            if link.link_type != "phone":
                continue

            raw_phone = link.url.replace("tel:", "").split("?")[0]

            normalized = self._normalize_phone(raw_phone)

            if normalized:
                phones.add(normalized)

        text = " ".join(page.paragraphs)

        for match in re.findall(
            r"(?:\+?\d[\d\s().-]{7,}\d)",
            text,
        ):
            normalized = self._normalize_phone(match)

            if normalized:
                phones.add(normalized)

        return sorted(phones)

    @staticmethod
    def _normalize_phone(value: str) -> str | None:
        """Validate and normalize a phone number."""

        value = value.strip()

        try:
            number = phonenumbers.parse(
                value,
                "IN",
            )
        except NumberParseException:
            return None

        if not phonenumbers.is_valid_number(number):
            return None

        return phonenumbers.format_number(
            number,
            phonenumbers.PhoneNumberFormat.E164,
        )