from pipeline.crawler import CompanyCrawler


def main():
    crawler = CompanyCrawler()

    url = input("Enter company website URL: ").strip()

    company = crawler.crawl(
        url,
        max_pages=10,
    )

    print(company.model_dump(mode="json"))


if __name__ == "__main__":
    main()