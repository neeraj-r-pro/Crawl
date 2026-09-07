#!/usr/bin/env python3
"""
Simple interactive entry point.

Run:
    python main.py

You'll be prompted for a company website URL, then the crawler runs with
sensible defaults and writes the result to output/<hostname>.json.

For scripted use, batch runs, or custom settings (max pages, depth,
disabling dynamic rendering, SQLite output, etc.), use the full CLI
instead:
    python -m crawler.main --help
"""
from __future__ import annotations

import sys
from urllib.parse import urlparse

from crawler import config, storage
from crawler.crawler import Crawler


def _prompt_url() -> str:
    while True:
        url = input("Enter company website URL to crawl: ").strip()
        if not url:
            print("Please enter a URL, e.g. https://example-company.com\n")
            continue
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url


def _prompt_yes_no(question: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{question} {suffix}: ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def main() -> int:
    print("=" * 60)
    print("Company Website Crawler")
    print("=" * 60)
    print("Discovers company pages, extracts structured info, writes JSON.")
    print("(Press Ctrl+C at any time to cancel.)\n")

    url = _prompt_url()
    use_dynamic = _prompt_yes_no(
        "Enable JavaScript rendering for dynamic pages? (slower, more thorough)",
        default=True,
    )

    crawler = Crawler(
        max_pages=config.MAX_PAGES_DEFAULT,
        max_depth=config.MAX_DEPTH_DEFAULT,
        use_dynamic_rendering=use_dynamic,
        respect_robots=True,
        crawl_delay=config.CRAWL_DELAY_DEFAULT,
        time_budget_seconds=180,
        verbose=True,
    )

    print(f"\nCrawling {url} ...\n")
    try:
        report = crawler.crawl(url)
    except Exception as e:
        print(f"\nCrawl failed: {type(e).__name__}: {e}")
        return 1

    host = urlparse(url).netloc.replace(":", "_") or "output"
    output_path = f"output/{host}.json"
    storage.write_json(report, output_path)

    print(f"\nWrote structured output -> {output_path}")
    print(
        f"Summary: {report.pages_fetched_ok}/{report.pages_discovered} pages fetched OK, "
        f"stop_reason={report.stop_reason}"
    )
    print(f"\nCompany name detected: {report.company.company_name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(130)
