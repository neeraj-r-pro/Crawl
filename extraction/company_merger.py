from models.schemas import Company, ContactInfo


class CompanyMerger:
    """Merge company information extracted from multiple pages."""

    def merge(
        self,
        current: Company | None,
        new: Company,
    ) -> Company:
        """Merge a newly extracted company into the current company."""

        if current is None:
            return new

        return Company(
            name=current.name or new.name,
            website=current.website,
            description=(
                current.description
                or new.description
            ),
            products=self._merge_lists(
                current.products,
                new.products,
            ),
            services=self._merge_lists(
                current.services,
                new.services,
            ),
            solutions=self._merge_lists(
                current.solutions,
                new.solutions,
            ),
            industries=self._merge_lists(
                current.industries,
                new.industries,
            ),
            locations=self._merge_lists(
                current.locations,
                new.locations,
            ),
            contact=ContactInfo(
                emails=self._merge_lists(
                    current.contact.emails,
                    new.contact.emails,
                ),
                phone_numbers=self._merge_lists(
                    current.contact.phone_numbers,
                    new.contact.phone_numbers,
                ),
                addresses=self._merge_lists(
                    current.contact.addresses,
                    new.contact.addresses,
                ),
            ),
            social_profiles=self._merge_social_profiles(
                current,
                new,
            ),
        )

    @staticmethod
    def _merge_lists(
        current: list[str],
        new: list[str],
    ) -> list[str]:
        """Merge string lists while removing duplicates."""

        result = list(current)

        for item in new:
            if item not in result:
                result.append(item)

        return result

    @staticmethod
    def _merge_social_profiles(
        current: Company,
        new: Company,
    ):
        """Merge social profiles while removing duplicates."""

        result = list(current.social_profiles)

        existing_urls = {
            str(profile.url)
            for profile in result
        }

        for profile in new.social_profiles:
            if str(profile.url) not in existing_urls:
                result.append(profile)
                existing_urls.add(str(profile.url))

        return result