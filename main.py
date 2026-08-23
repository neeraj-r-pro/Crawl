from pipeline.crawler import CompanyCrawler


def main():
    crawler = CompanyCrawler()

    url = "https://example.com"

    company = crawler.crawl(url)

    print(company.model_dump(mode="json"))


if __name__ == "__main__":
    main()