"""Export a compact real-data demo dataset for the portfolio's embedded analytics engine.

Queries the local PostgreSQL database (FIFA World Cup 2022 + NFL tracking data) and
regenerates `data/sports-analytics/public-demo.json` in the portfolio repo so the
production site (which has no Python backend) can answer demo queries with real
athletes.

Usage:
    .venv/bin/python3 etl/export_demo_dataset.py            # write the JSON
    .venv/bin/python3 etl/export_demo_dataset.py --inspect  # print schema/data diagnostics
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

import psycopg

DATABASE_URL = os.environ.get(
    "DEMO_EXPORT_DATABASE_URL",
    "postgresql://creatorhub:creatorhub_pass@localhost:5433/creatorhub_dev",
)

OUTPUT_PATH = os.environ.get(
    "DEMO_EXPORT_OUTPUT_PATH",
    "/Users/shubhampareek/Desktop/Code Agents/data/sports-analytics/public-demo.json",
)

SOCCER_ATHLETE_LIMIT = 120
NFL_ATHLETE_LIMIT = 80


def inspect(conn: psycopg.Connection) -> None:
    cur = conn.cursor()
    for table in ("athletes", "sessions", "gps_metrics", "wellness"):
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name=%s ORDER BY ordinal_position",
            (table,),
        )
        print(f"{table}:")
        for name, dtype in cur.fetchall():
            print(f"  {name}: {dtype}")
        print()

    cur.execute("SELECT sport, count(*) FROM athletes GROUP BY sport")
    print("athlete counts by sport:", cur.fetchall())

    cur.execute(
        "SELECT sport, position, count(*) FROM athletes GROUP BY sport, position ORDER BY sport, count(*) DESC"
    )
    print("positions:", cur.fetchall())

    cur.execute(
        "SELECT nationality, count(*) FROM athletes WHERE sport='soccer' "
        "GROUP BY nationality ORDER BY count(*) DESC LIMIT 15"
    )
    print("top soccer nationalities:", cur.fetchall())

    cur.execute("SELECT DISTINCT competition FROM sessions ORDER BY competition LIMIT 12")
    print("competitions:", cur.fetchall())

    cur.execute("SELECT DISTINCT session_type FROM sessions")
    print("session types:", cur.fetchall())

    cur.execute("SELECT min(TO_DATE(session_date, 'MM/DD/YYYY')), max(TO_DATE(session_date, 'MM/DD/YYYY')) FROM sessions")
    print("session date range:", cur.fetchone())

    cur.execute(
        """
        SELECT a.name, a.position, a.team, a.nationality, s.session_date, s.competition, s.opponent,
               g.total_distance, g.sprint_distance, g.high_intensity_efforts,
               g.passes, g.shots, g.pressures, g.carries, g.dribbles, g.avg_speed, g.max_speed
        FROM athletes a
        JOIN sessions s ON s.athlete_id = a.athlete_id
        JOIN gps_metrics g ON g.session_id = s.session_id
        WHERE a.sport = 'soccer' AND a.name ILIKE '%%messi%%'
        LIMIT 3
        """
    )
    print("soccer sample (Messi):")
    for row in cur.fetchall():
        print(" ", row)

    cur.execute(
        """
        SELECT a.name, a.position, a.team, a.nationality, s.session_date, s.competition,
               g.total_distance, g.sprint_distance, g.high_intensity_efforts,
               g.passes, g.pressures, g.avg_speed, g.max_speed
        FROM athletes a
        JOIN sessions s ON s.athlete_id = a.athlete_id
        JOIN gps_metrics g ON g.session_id = s.session_id
        WHERE a.sport = 'american_football'
        LIMIT 3
        """
    )
    print("nfl sample:")
    for row in cur.fetchall():
        print(" ", row)

    cur.execute("SELECT count(*) FROM wellness")
    print("wellness rows:", cur.fetchone())


def select_athlete_ids(conn: psycopg.Connection, sport: str, limit: int) -> list[int]:
    """Pick the top athletes for a sport by summed total distance across sessions."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT a.athlete_id
        FROM athletes a
        JOIN sessions s ON s.athlete_id = a.athlete_id
        JOIN gps_metrics g ON g.session_id = s.session_id
        WHERE a.sport = %s AND g.total_distance IS NOT NULL
        GROUP BY a.athlete_id
        ORDER BY SUM(g.total_distance) DESC
        LIMIT %s
        """,
        (sport, limit),
    )
    return [row[0] for row in cur.fetchall()]


def fetch_rows(conn: psycopg.Connection, athlete_ids: list[int]) -> tuple[list[dict], list[dict], list[dict]]:
    cur = conn.cursor()

    cur.execute(
        """
        SELECT athlete_id, name, position, team, sport, nationality
        FROM athletes
        WHERE athlete_id = ANY(%s)
        ORDER BY athlete_id
        """,
        (athlete_ids,),
    )
    athletes = [
        {
            "athlete_id": row[0],
            "name": row[1],
            "position": row[2],
            "team": row[3],
            "sport": row[4],
            "nationality": row[5],
        }
        for row in cur.fetchall()
    ]

    cur.execute(
        """
        SELECT session_id, athlete_id, session_date, duration_minutes, session_type, competition
        FROM sessions
        WHERE athlete_id = ANY(%s)
        ORDER BY session_id
        """,
        (athlete_ids,),
    )
    sessions = [
        {
            "session_id": row[0],
            "athlete_id": row[1],
            "session_date": row[2],
            "duration_minutes": _num(row[3]),
            "session_type": row[4],
            "competition": row[5],
        }
        for row in cur.fetchall()
    ]

    session_ids = [s["session_id"] for s in sessions]
    cur.execute(
        """
        SELECT session_id, total_distance, sprint_distance, high_intensity_efforts,
               passes, shots, pressures, carries, dribbles, avg_speed, max_speed
        FROM gps_metrics
        WHERE session_id = ANY(%s)
        ORDER BY session_id
        """,
        (session_ids,),
    )
    gps_metrics = [
        {
            "session_id": row[0],
            "total_distance": _num(row[1]),
            "sprint_distance": _num(row[2]),
            "high_intensity_efforts": _num(row[3]),
            "passes": _num(row[4]),
            "shots": _num(row[5]),
            "pressures": _num(row[6]),
            "carries": _num(row[7]),
            "dribbles": _num(row[8]),
            "avg_speed": _num(row[9]),
            "max_speed": _num(row[10]),
        }
        for row in cur.fetchall()
    ]

    return athletes, sessions, gps_metrics


def fetch_wellness(conn: psycopg.Connection, athlete_ids: list[int]) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT athlete_id, date, fatigue_score, sleep_score
        FROM wellness
        WHERE athlete_id = ANY(%s)
        ORDER BY athlete_id, date
        """,
        (athlete_ids,),
    )
    return [
        {
            "athlete_id": row[0],
            "date": row[1] if isinstance(row[1], str) else row[1].strftime("%m/%d/%Y"),
            "fatigue_score": _num(row[2]),
            "sleep_score": _num(row[3]),
        }
        for row in cur.fetchall()
    ]


def _num(value):
    """Convert Decimal to float (rounded) while preserving ints and None."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    number = float(value)
    if number.is_integer():
        return int(number)
    return round(number, 2)


def latest_session_date(sessions: list[dict]) -> str:
    """Return the most recent session date as ISO YYYY-MM-DD."""
    best = None
    for session in sessions:
        raw = session["session_date"]
        month, day, year = (int(part) for part in raw.split("/"))
        key = (year, month, day)
        if best is None or key > best:
            best = key
    if best is None:
        return "2022-12-18"
    return f"{best[0]:04d}-{best[1]:02d}-{best[2]:02d}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true", help="print schema/data diagnostics and exit")
    args = parser.parse_args()

    conn = psycopg.connect(DATABASE_URL)
    try:
        if args.inspect:
            inspect(conn)
            return

        soccer_ids = select_athlete_ids(conn, "soccer", SOCCER_ATHLETE_LIMIT)
        nfl_ids = select_athlete_ids(conn, "american_football", NFL_ATHLETE_LIMIT)
        athlete_ids = soccer_ids + nfl_ids

        athletes, sessions, gps_metrics = fetch_rows(conn, athlete_ids)
        wellness = fetch_wellness(conn, athlete_ids)

        dataset = {
            "referenceDate": latest_session_date(sessions),
            "athletes": athletes,
            "sessions": sessions,
            "gps_metrics": gps_metrics,
            "wellness": wellness,
        }

        payload = json.dumps(dataset, separators=(",", ":"), ensure_ascii=False)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as handle:
            handle.write(payload)

        by_sport = defaultdict(int)
        for athlete in athletes:
            by_sport[athlete["sport"]] += 1
        print(f"Wrote {OUTPUT_PATH}")
        print(f"  athletes: {len(athletes)} ({dict(by_sport)})")
        print(f"  sessions: {len(sessions)}")
        print(f"  gps_metrics: {len(gps_metrics)}")
        print(f"  wellness: {len(wellness)}")
        print(f"  referenceDate: {dataset['referenceDate']}")
        print(f"  size: {len(payload.encode('utf-8')) / 1024:.1f} KB")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
