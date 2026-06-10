#!/usr/bin/env python3
"""
Wellness Seed
─────────────
The StatsBomb ETL truncates the wellness table and nothing repopulates it,
so fatigue/sleep queries return no rows. This script generates plausible
synthetic wellness check-ins:

  * one wellness row per (athlete, session date) for every athlete that has
    sessions — the date keeps the existing MM/DD/YYYY text convention
  * fatigue_score: uniform 3.0–9.0, one decimal
  * sleep_score:   uniform 4.0–9.5, one decimal
  * fixed random seed so reruns are reproducible
  * INSERT ... ON CONFLICT DO NOTHING (PK is (athlete_id, date))

Usage:
    .venv/bin/python3 etl/wellness_seed.py
"""

from __future__ import annotations

import logging
import os
import random

import psycopg

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)

DB_URL = os.environ.get(
    "SPORTS_DATABASE_URL",
    "postgresql://creatorhub:creatorhub_pass@localhost:5433/creatorhub_dev",
)

RANDOM_SEED = 20221218  # fixed seed for reproducibility


def build_wellness_rows(athlete_session_dates: list[tuple[int, str]]) -> list[tuple[int, str, float, float]]:
    """Generate one synthetic wellness row per (athlete_id, session date)."""
    rng = random.Random(RANDOM_SEED)
    rows: list[tuple[int, str, float, float]] = []
    for athlete_id, session_date in athlete_session_dates:
        fatigue_score = round(rng.uniform(3.0, 9.0), 1)
        sleep_score = round(rng.uniform(4.0, 9.5), 1)
        rows.append((athlete_id, session_date, fatigue_score, sleep_score))
    return rows


def main() -> None:
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            # Deterministic ordering so the fixed seed maps to the same rows on rerun.
            cur.execute(
                """
                SELECT DISTINCT s.athlete_id, s.session_date
                FROM sessions s
                ORDER BY s.athlete_id, s.session_date
                """
            )
            athlete_session_dates = [(int(row[0]), str(row[1])) for row in cur.fetchall()]
            log.info("Found %d (athlete, session date) pairs.", len(athlete_session_dates))

            rows = build_wellness_rows(athlete_session_dates)
            cur.executemany(
                """
                INSERT INTO wellness (athlete_id, date, fatigue_score, sleep_score)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (athlete_id, date) DO NOTHING
                """,
                rows,
            )
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM wellness")
            total = cur.fetchone()[0]
    log.info("Wellness seed complete — wellness table now holds %d rows.", total)


if __name__ == "__main__":
    main()
