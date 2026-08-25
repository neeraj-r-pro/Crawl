import re

import phonenumbers
from phonenumbers import NumberParseException

from extraction.html_parser import ParsedPage


class ContactExtractor:
    """Extract contact information from a parsed webpage."""

    EMAIL_PATTERN = re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    )

    # Specific placeholder addresses that should not be treated
    # as real company contact information.
    PLACEHOLDER_EMAILS = {
        "example@email.com",
    }

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
        """Extract valid email addresses from the page."""

        emails = set()

        # Extract emails from mailto links.
        for link in page.links:
            if link.link_type != "email":
                continue

            email = (
                link.url
                .replace("mailto:", "")
                .split("?")[0]
                .strip()
                .lower()
            )

            if email and not self._is_placeholder_email(email):
                emails.add(email)

        # Extract emails from visible page text.
        text = " ".join(page.paragraphs)

        for email in self.EMAIL_PATTERN.findall(text):
            email = email.lower()

            if not self._is_placeholder_email(email):
                emails.add(email)

        return sorted(emails)

    @classmethod
    def _is_placeholder_email(cls, email: str) -> bool:
        """Return True when the email is a known placeholder."""

        return email.strip().lower() in cls.PLACEHOLDER_EMAILS

    def _extract_phone_numbers(
        self,
        page: ParsedPage,
    ) -> list[str]:
        """Extract and normalize phone numbers."""

        phones = set()

        # Extract phone numbers from tel links.
        for link in page.links:
            if link.link_type != "phone":
                continue

            raw_phone = (
                link.url
                .replace("tel:", "")
                .split("?")[0]
            )

            normalized = self._normalize_phone(raw_phone)

            if normalized:
                phones.add(normalized)

        # Extract phone numbers from visible page text.
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