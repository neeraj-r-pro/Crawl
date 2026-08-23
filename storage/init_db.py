from storage.database import Base, engine
from storage.models import CompanyRecord


def initialize_database() -> None:
    """Create all database tables."""

    Base.metadata.create_all(engine)


if __name__ == "__main__":
    initialize_database()
    print("Database initialized successfully.")