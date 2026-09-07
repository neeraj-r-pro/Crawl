"""
Command-line entry point.

Usage:
    python -m crawler.main --url https://example-company.com
    python -m crawler.main --url https://example-company.com --max-pages 50 --no-dynamic
    python -m crawler.main --url https://example-company.com --output output/example.json --sqlite output/companies.db
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config, storage
from .crawler import Crawler


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Discover and extract structured company info from a website.")
    p.add_argument("--url", required=True, help="Company website to crawl, e.g. https://example.com")
    p.add_argument("--max-pages", type=int, default=config.MAX_PAGES_DEFAULT)
    p.add_argument("--max-depth", type=int, default=config.MAX_DEPTH_DEFAULT)
    p.add_argument("--delay", type=float, default=config.CRAWL_DELAY_DEFAULT, help="Seconds between requests to the same host")
    p.add_argument("--time-budget", type=int, default=180, help="Max wall-clock seconds for the crawl")
    p.add_argument("--no-dynamic", action="store_true", help="Disable Playwright fallback for JS-rendered pages")
    p.add_argument("--no-robots", action="store_true", help="Ignore robots.txt (not recommended)")
    p.add_argument("--output", default=None, help="Path to write JSON output (default: output/<host>.json)")
    p.add_argument("--sqlite", default=None, help="Optional path to also write results into a SQLite DB")
    p.add_argument("--quiet", action="store_true", help="Suppress per-page progress logging")
    return p


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)

    crawler = Crawler(
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        use_dynamic_rendering=not args.no_dynamic,
        respect_robots=not args.no_robots,
        crawl_delay=args.delay,
        time_budget_seconds=args.time_budget,
        verbose=not args.quiet,
    )

    report = crawler.crawl(args.url)

    from urllib.parse import urlparse
    host = urlparse(args.url).netloc.replace(":", "_")
    output_path = args.output or f"output/{host}.json"
    storage.write_json(report, output_path)
    print(f"\nWrote structured output -> {output_path}")

    if args.sqlite:
        storage.write_sqlite(report, args.sqlite)
        print(f"Wrote SQLite output    -> {args.sqlite}")

    print(
        f"\nSummary: {report.pages_fetched_ok}/{report.pages_discovered} pages fetched OK, "
        f"stop_reason={report.stop_reason}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
