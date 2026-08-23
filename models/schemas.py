from pydantic import BaseModel, Field, HttpUrl


class ContactInfo(BaseModel):
    emails: list[str] = Field(default_factory=list)
    phone_numbers: list[str] = Field(default_factory=list)
    addresses: list[str] = Field(default_factory=list)


class SocialProfile(BaseModel):
    platform: str
    url: HttpUrl


class Company(BaseModel):
    name: str
    website: HttpUrl

    description: str | None = None

    products: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    solutions: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)

    locations: list[str] = Field(default_factory=list)

    contact: ContactInfo = Field(default_factory=ContactInfo)

    social_profiles: list[SocialProfile] = Field(default_factory=list)