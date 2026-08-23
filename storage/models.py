from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from storage.database import Base


class CompanyRecord(Base):
    """Database representation of an extracted company."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    website: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        unique=True,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    products: Mapped[list] = mapped_column(
        JSON,
        default=list,
    )

    services: Mapped[list] = mapped_column(
        JSON,
        default=list,
    )

    solutions: Mapped[list] = mapped_column(
        JSON,
        default=list,
    )

    industries: Mapped[list] = mapped_column(
        JSON,
        default=list,
    )

    locations: Mapped[list] = mapped_column(
        JSON,
        default=list,
    )

    contact: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
    )

    social_profiles: Mapped[list] = mapped_column(
        JSON,
        default=list,
    )