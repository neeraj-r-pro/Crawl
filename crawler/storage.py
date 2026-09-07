"""
Output writers. JSON is the primary structured format (matches the
assignment's "reusable by another system" requirement with zero setup).
An optional SQLite writer is included to show how this would plug into
a persistent store without pulling in a full DB server for the demo.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import CrawlReport


def write_json(report: CrawlReport, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)


SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    website TEXT UNIQUE,
    company_name TEXT,
    description TEXT,
    headquarters TEXT,
    other_locations TEXT,   -- JSON array
    products TEXT,          -- JSON array
    services TEXT,          -- JSON array
    solutions TEXT,         -- JSON array
    industries TEXT,        -- JSON array
    emails TEXT,             -- JSON array
    phones TEXT,             -- JSON array
    social_links TEXT,       -- JSON object
    crawled_at TEXT
);

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER REFERENCES companies(id),
    url TEXT,
    page_type TEXT,
    title TEXT,
    http_status INTEGER,
    fetched_ok INTEGER,
    extraction_result TEXT,
    error TEXT,
    depth INTEGER,
    rendered_with TEXT,
    discovered_from TEXT,
    UNIQUE(company_id, url)
);
"""


def write_sqlite(report: CrawlReport, db_path: str | Path) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        c = report.company
        cur = conn.execute(
            """INSERT INTO companies
               (website, company_name, description, headquarters, other_locations,
                products, services, solutions, industries, emails, phones,
                social_links, crawled_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(website) DO UPDATE SET
                 company_name=excluded.company_name,
                 description=excluded.description,
                 headquarters=excluded.headquarters,
                 other_locations=excluded.other_locations,
                 products=excluded.products,
                 services=excluded.services,
                 solutions=excluded.solutions,
                 industries=excluded.industries,
                 emails=excluded.emails,
                 phones=excluded.phones,
                 social_links=excluded.social_links,
                 crawled_at=excluded.crawled_at
            """,
            (
                c.website, c.company_name, c.description, c.headquarters,
                json.dumps(c.other_locations), json.dumps(c.products),
                json.dumps(c.services), json.dumps(c.solutions),
                json.dumps(c.industries), json.dumps(c.emails),
                json.dumps(c.phones), json.dumps(c.social_links),
                report.finished_at,
            ),
        )
        company_id = cur.lastrowid or conn.execute(
            "SELECT id FROM companies WHERE website = ?", (c.website,)
        ).fetchone()[0]

        for p in report.pages:
            conn.execute(
                """INSERT OR REPLACE INTO pages
                   (company_id, url, page_type, title, http_status, fetched_ok,
                    extraction_result, error, depth, rendered_with, discovered_from)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    company_id, p.url, p.page_type, p.title, p.http_status,
                    int(p.fetched_ok), p.extraction_result, p.error, p.depth,
                    p.rendered_with, p.discovered_from,
                ),
            )
        conn.commit()
    finally:
        conn.close()
