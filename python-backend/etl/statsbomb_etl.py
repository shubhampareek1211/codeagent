#!/usr/bin/env python3
"""
StatsBomb FIFA World Cup 2022 ETL
──────────────────────────────────
Loads event data from the StatsBomb Open Data repo (via statsbombpy)
into the extended sports analytics schema.

Metrics approximated from event data (no GPS tracker in open data):
  total_distance   = carry distances (m) + pass lengths (m) + position baseline
  sprint_distance  = carries where Euclidean distance > 5 m
  high_int_efforts = pressures + shots + tackles + dribbles attempted
  passes           = pass events count
  shots            = shot events count
  pressures        = pressure events count
  carries          = carry events count
  dribbles         = dribble events count

Dates stored as MM/DD/YYYY to match existing schema convention.
"""

from __future__ import annotations

import logging
import math
import os
import warnings
from datetime import datetime

import pandas as pd
import psycopg

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
DB_URL       = os.environ.get(
    "SPORTS_DATABASE_URL",
    "postgresql://creatorhub:creatorhub_pass@localhost:5433/creatorhub_dev",
)
COMPETITION  = 43   # FIFA World Cup
SEASON       = 106  # 2022

# Position normalisation (StatsBomb → schema)
POS_MAP: dict[str, str] = {
    "Goalkeeper":                  "goalkeeper",
    "Right Back":                  "defender",
    "Left Back":                   "defender",
    "Center Back":                 "defender",
    "Right Center Back":           "defender",
    "Left Center Back":            "defender",
    "Right Wing Back":             "defender",
    "Left Wing Back":              "defender",
    "Defensive Midfield":          "midfielder",
    "Central Midfield":            "midfielder",
    "Center Defensive Midfield":   "midfielder",
    "Left Defensive Midfield":     "midfielder",
    "Right Defensive Midfield":    "midfielder",
    "Right Midfield":              "midfielder",
    "Left Midfield":               "midfielder",
    "Left Center Midfield":        "midfielder",
    "Right Center Midfield":       "midfielder",
    "Center Attacking Midfield":   "midfielder",
    "Left Attacking Midfield":     "midfielder",
    "Right Attacking Midfield":    "midfielder",
    "Attacking Midfield":          "midfielder",
    "Left Wing":                   "forward",
    "Right Wing":                  "forward",
    "Center Forward":              "forward",
    "Left Center Forward":         "forward",
    "Right Center Forward":        "forward",
    "Secondary Striker":           "forward",
}

# Position distance baselines (m) — calibrated to real match GPS averages
POS_BASELINE: dict[str, float] = {
    "goalkeeper": 5_500,
    "defender":   10_500,
    "midfielder": 12_000,
    "forward":    10_000,
}

YARDS_TO_M = 0.9144  # 1 yard = 0.9144 metres


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_date(d: str) -> str:
    """Convert YYYY-MM-DD → MM/DD/YYYY."""
    return datetime.strptime(d, "%Y-%m-%d").strftime("%m/%d/%Y")


def carry_distance_m(row: pd.Series) -> float:
    """Euclidean distance in metres for a single carry event."""
    loc  = row.get("location")
    eloc = row.get("carry_end_location")
    if not (isinstance(loc, list) and isinstance(eloc, list)):
        return 0.0
    dx = eloc[0] - loc[0]
    dy = eloc[1] - loc[1]
    return math.sqrt(dx * dx + dy * dy) * YARDS_TO_M


def compute_player_metrics(
    player_events: pd.DataFrame,
    position: str,
) -> dict:
    """Aggregate event data into GPS-proxy metrics for one player in one match."""
    evt_type = player_events["type"].str.lower() if "type" in player_events.columns else pd.Series(dtype=str)

    # Event counts
    passes    = int((evt_type == "pass").sum())
    shots     = int((evt_type == "shot").sum())
    pressures = int((evt_type == "pressure").sum())
    carries   = int((evt_type == "carry").sum())
    dribbles  = int((evt_type == "dribble").sum())
    tackles   = int((evt_type == "duel").sum())

    # Distance from carries (Euclidean)
    carry_rows  = player_events[evt_type == "carry"]
    carry_dists = carry_rows.apply(carry_distance_m, axis=1)
    carry_total = carry_dists.sum()
    sprint_dist = float(carry_dists[carry_dists > 5.0].sum())

    # Distance from passes (pass_length column, yards → m)
    pass_rows    = player_events[evt_type == "pass"]
    pass_lengths = pass_rows.get("pass_length", pd.Series(dtype=float)).fillna(0) * YARDS_TO_M
    pass_total   = float(pass_lengths.sum())

    # Total distance = carry + pass contributions + position baseline
    baseline     = POS_BASELINE.get(position, 10_000)
    total_dist   = baseline + carry_total + pass_total

    # High intensity efforts
    hi_efforts = pressures + shots + tackles + dribbles

    return {
        "total_distance":       round(total_dist, 1),
        "sprint_distance":      round(sprint_dist, 1),
        "high_intensity_efforts": hi_efforts,
        "passes":               passes,
        "shots":                shots,
        "pressures":            pressures,
        "carries":              carries,
        "dribbles":             dribbles,
    }


# ── ETL ───────────────────────────────────────────────────────────────────────

def run() -> None:
    from statsbombpy import sb   # import here so module stays importable without package

    log.info("Fetching FIFA World Cup 2022 matches …")
    matches_df = sb.matches(competition_id=COMPETITION, season_id=SEASON)
    log.info(f"  → {len(matches_df)} matches found")

    # ── phase 1: collect all data ─────────────────────────────────────────────
    athlete_map:  dict[int, int]   = {}     # sb_player_id → db_athlete_id
    athlete_pos:  dict[int, str]   = {}     # sb_player_id → position
    session_map:  dict[tuple, int] = {}     # (sb_match_id, sb_player_id) → db_session_id

    athletes_rows: list[dict] = []
    sessions_rows: list[dict] = []
    gps_rows:      list[dict] = []

    athlete_seq = 1
    session_seq = 1

    for _, match in matches_df.iterrows():
        mid         = int(match["match_id"])
        match_date  = fmt_date(str(match["match_date"]))
        home_team   = str(match["home_team"])
        away_team   = str(match["away_team"])
        log.info(f"  match {mid}: {home_team} vs {away_team}  ({match_date})")

        # ── lineups ──────────────────────────────────────────────────────────
        try:
            lineups = sb.lineups(match_id=mid)
        except Exception as exc:
            log.warning(f"    lineups failed: {exc}")
            continue

        match_players: dict[int, dict] = {}   # sb_player_id → {name, position, team, home_away}

        for team_name, lineup_df in lineups.items():
            is_home  = team_name == home_team
            opponent = away_team if is_home else home_team

            for _, player in lineup_df.iterrows():
                pid  = int(player["player_id"])
                name = str(player["player_name"])

                positions = player.get("positions", [])
                if isinstance(positions, list) and positions:
                    pos_label = positions[0].get("position", "Central Midfield")
                else:
                    pos_label = "Central Midfield"
                pos = POS_MAP.get(pos_label, "midfielder")

                country = None
                if isinstance(player.get("country"), dict):
                    country = player["country"].get("name")

                jersey = int(player["jersey_number"]) if pd.notna(player.get("jersey_number")) else None

                match_players[pid] = {
                    "name":      name,
                    "position":  pos,
                    "team":      team_name,
                    "home_away": "home" if is_home else "away",
                    "opponent":  opponent,
                    "country":   country,
                    "jersey":    jersey,
                }

                # register athlete (once per unique player)
                if pid not in athlete_map:
                    athlete_map[pid]  = athlete_seq
                    athlete_pos[pid]  = pos
                    athletes_rows.append({
                        "athlete_id":  athlete_seq,
                        "name":        name,
                        "position":    pos,
                        "team":        team_name,
                        "sport":       "soccer",
                        "nationality": country,
                        "jersey_no":   jersey,
                    })
                    athlete_seq += 1

                # register session
                key = (mid, pid)
                if key not in session_map:
                    session_map[key] = session_seq
                    sessions_rows.append({
                        "session_id":    session_seq,
                        "athlete_id":    athlete_map[pid],
                        "session_date":  match_date,
                        "duration_minutes": 90,
                        "session_type":  "match",
                        "competition":   "FIFA World Cup 2022",
                        "opponent":      match_players[pid]["opponent"],
                        "home_away":     match_players[pid]["home_away"],
                        "data_source":   "statsbomb",
                        "match_id":      str(mid),
                    })
                    session_seq += 1

        # ── events → per-player metrics ──────────────────────────────────────
        try:
            events_df = sb.events(match_id=mid)
        except Exception as exc:
            log.warning(f"    events failed: {exc}")
            continue

        if "player_id" not in events_df.columns:
            # statsbombpy ≥0.9 may not flatten player_id; try player column
            if "player" in events_df.columns:
                # player column is str (name) in some versions — skip id-based grouping
                log.warning("    player_id not in events — skipping GPS metrics for this match")
                continue
            else:
                continue

        for pid, grp in events_df.groupby("player_id"):
            pid = int(pid)
            if pid not in athlete_map:
                continue
            key = (mid, pid)
            if key not in session_map:
                continue

            pos     = athlete_pos.get(pid, "midfielder")
            metrics = compute_player_metrics(grp, pos)
            gps_rows.append({
                "session_id": session_map[key],
                **metrics,
            })

    log.info(
        f"Collected  athletes={len(athletes_rows)}  "
        f"sessions={len(sessions_rows)}  "
        f"gps={len(gps_rows)}"
    )

    # ── phase 2: bulk insert ──────────────────────────────────────────────────
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            # Clear existing seed data
            log.info("Clearing existing seed data …")
            cur.execute("TRUNCATE gps_metrics, wellness, sessions, athletes RESTART IDENTITY CASCADE")

            # Athletes
            log.info(f"Inserting {len(athletes_rows)} athletes …")
            cur.executemany(
                """
                INSERT INTO athletes
                    (athlete_id, name, position, team, sport, nationality, jersey_no)
                VALUES
                    (%(athlete_id)s, %(name)s, %(position)s, %(team)s,
                     %(sport)s, %(nationality)s, %(jersey_no)s)
                ON CONFLICT (athlete_id) DO NOTHING
                """,
                athletes_rows,
            )

            # Sessions
            log.info(f"Inserting {len(sessions_rows)} sessions …")
            cur.executemany(
                """
                INSERT INTO sessions
                    (session_id, athlete_id, session_date, duration_minutes,
                     session_type, competition, opponent, home_away,
                     data_source, match_id)
                VALUES
                    (%(session_id)s, %(athlete_id)s, %(session_date)s,
                     %(duration_minutes)s, %(session_type)s, %(competition)s,
                     %(opponent)s, %(home_away)s, %(data_source)s, %(match_id)s)
                ON CONFLICT DO NOTHING
                """,
                sessions_rows,
            )

            # GPS metrics
            log.info(f"Inserting {len(gps_rows)} gps_metrics rows …")
            cur.executemany(
                """
                INSERT INTO gps_metrics
                    (session_id, total_distance, sprint_distance,
                     high_intensity_efforts, passes, shots, pressures,
                     carries, dribbles)
                VALUES
                    (%(session_id)s, %(total_distance)s, %(sprint_distance)s,
                     %(high_intensity_efforts)s, %(passes)s, %(shots)s,
                     %(pressures)s, %(carries)s, %(dribbles)s)
                ON CONFLICT (session_id) DO NOTHING
                """,
                gps_rows,
            )

            conn.commit()

    log.info("✅ StatsBomb ETL complete.")
    _print_summary(DB_URL)


def _print_summary(db_url: str) -> None:
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            for tbl in ("athletes", "sessions", "gps_metrics"):
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                count = cur.fetchone()[0]
                log.info(f"  {tbl}: {count:,} rows")
            cur.execute(
                "SELECT position, COUNT(DISTINCT athlete_id) "
                "FROM athletes GROUP BY position ORDER BY position"
            )
            log.info("  Position breakdown:")
            for row in cur.fetchall():
                log.info(f"    {row[0]}: {row[1]}")


if __name__ == "__main__":
    run()
