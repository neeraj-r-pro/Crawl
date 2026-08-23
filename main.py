from models.schemas import Company


company = Company(
    name="Example Corporation",
    website="https://example.com",
    description="Example company description",
    products=["Product A", "Product B"],
    services=["Consulting"],
    locations=["Kochi", "Bangalore"],
)

print(company)
print()
print(company.model_dump())