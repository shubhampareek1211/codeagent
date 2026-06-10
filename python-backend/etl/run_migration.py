#!/usr/bin/env python3
"""Apply the base schema + extension migration to SPORTS_DATABASE_URL.

Usage:
    export SPORTS_DATABASE_URL="postgresql://user:pass@host/db"
    python etl/run_migration.py
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import psycopg

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)

DB_URL = os.environ.get(
    "SPORTS_DATABASE_URL",
    "postgresql://creatorhub:creatorhub_pass@localhost:5433/creatorhub_dev",
)

SQL_FILES = [
    Path(__file__).parent.parent / "sql" / "sports_analytics_schema.sql",
    Path(__file__).parent / "schema_migration.sql",
]


def run() -> None:
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            for sql_file in SQL_FILES:
                log.info(f"Applying {sql_file.name} …")
                cur.execute(sql_file.read_text())
            conn.commit()
    log.info("✅ Migration complete.")

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
            tables = [row[0] for row in cur.fetchall()]
            log.info(f"Tables present: {', '.join(tables)}")


if __name__ == "__main__":
    run()
