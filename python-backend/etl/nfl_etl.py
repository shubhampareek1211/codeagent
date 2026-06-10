#!/usr/bin/env python3
"""
NFL Big Data Bowl 2021 ETL  (feather dataset)
──────────────────────────────────────────────
Source: mathurinache/nflbigdatabowl2021-feather-files (Kaggle)

Files used:
  players.feather   → athletes table  (sport = american_football)
  games.feather     → session dates / competition metadata
  week{N}.feather   → player_tracking + gps_metrics aggregation

Tracking columns (week*.feather):
  time, x, y, s (yd/s), a (yd/s²), dis (yd/frame), o, dir, event,
  nflId, displayName, jerseyNumber, position, frameId, team,
  gameId, playId, playDirection, route

GPS metric derivation:
  total_distance   = SUM(dis)*0.9144  per player per game  (yards → m)
  sprint_distance  = SUM(dis where s > 4.88 yd/s = 4.47 m/s)  (yards → m)
  high_int_efforts = count of frames where a > 3.28 yd/s² (= 3 m/s²)
  avg_speed        = MEAN(s)*0.9144  (m/s)
  max_speed        = MAX(s)*0.9144   (m/s)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import psycopg

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
DB_URL   = os.environ.get(
    "SPORTS_DATABASE_URL",
    "postgresql://creatorhub:creatorhub_pass@localhost:5433/creatorhub_dev",
)
DATA_DIR = Path(__file__).parent / "data" / "nfl_big_data_bowl"
WEEKS    = [1]          # start with week 1; add more after initial load
TRACKING_SAMPLE = 10_000   # frame rows to write to player_tracking per week

YARDS_TO_M   = 0.9144
SPRINT_YDS_S = 4.88      # 10 mph in yards/sec sprint threshold
HI_ACC_YDS_S2= 3.28      # 3 m/s² in yards/s² acceleration threshold

NFL_POS_MAP: dict[str, str] = {
    "QB": "quarterback", "WR": "wide_receiver",  "RB": "running_back",
    "TE": "tight_end",   "T":  "lineman",         "G":  "lineman",
    "C":  "lineman",     "DE": "lineman",          "DT": "lineman",
    "NT": "lineman",     "MLB":"linebacker",       "ILB":"linebacker",
    "OLB":"linebacker",  "CB": "cornerback",       "SS": "safety",
    "FS": "safety",      "K":  "kicker",           "P":  "punter",
    "LS": "long_snapper","FB": "fullback",          "DB": "cornerback",
    "LB": "linebacker",  "OT": "lineman",
}


def fmt_date(raw: str) -> str:
    """MM/DD/YYYY in → MM/DD/YYYY out (already correct format in games.feather)."""
    try:
        dt = datetime.strptime(raw.strip(), "%m/%d/%Y")
        return dt.strftime("%m/%d/%Y")
    except ValueError:
        return raw.strip()


def run() -> None:
    # ── load reference files ─────────────────────────────────────────────────
    log.info("Loading players.feather …")
    players_df = pd.read_feather(DATA_DIR / "players.feather")
    log.info("Loading games.feather …")
    games_df   = pd.read_feather(DATA_DIR / "games.feather")

    log.info(f"  players: {len(players_df):,}   games: {len(games_df):,}")

    # ── get max existing IDs to avoid collision with StatsBomb data ───────────
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(athlete_id), 0) FROM athletes")
            max_aid = cur.fetchone()[0]
            cur.execute("SELECT COALESCE(MAX(session_id), 0) FROM sessions")
            max_sid = cur.fetchone()[0]

    log.info(f"  Offset: athlete_id starts at {max_aid+1}, session_id at {max_sid+1}")

    # ── build athletes ────────────────────────────────────────────────────────
    athlete_map: dict[int, int] = {}   # nflId → db_athlete_id
    athletes_rows: list[dict]   = []
    aid = max_aid + 1

    for _, row in players_df.iterrows():
        nfl_id  = int(row["nflId"])
        pos_raw = str(row.get("position", "")).strip()
        pos     = NFL_POS_MAP.get(pos_raw, "unknown")
        name    = str(row.get("displayName", f"Player_{nfl_id}"))
        birth   = str(row["birthDate"]) if pd.notna(row.get("birthDate")) else None

        athlete_map[nfl_id] = aid
        athletes_rows.append({
            "athlete_id":  aid,
            "name":        name,
            "position":    pos,
            "team":        "NFL",        # updated per-game from tracking below
            "sport":       "american_football",
            "nationality": "USA",
            "birth_date":  birth,
            "jersey_no":   None,
        })
        aid += 1

    # ── build game metadata ───────────────────────────────────────────────────
    game_meta: dict[int, dict] = {}
    for _, g in games_df.iterrows():
        gid = int(g["gameId"])
        game_meta[gid] = {
            "date":  fmt_date(str(g["gameDate"])),
            "home":  str(g["homeTeamAbbr"]),
            "away":  str(g["visitorTeamAbbr"]),
            "week":  int(g["week"]),
        }

    # ── process tracking weeks ────────────────────────────────────────────────
    session_map:   dict[tuple, int] = {}  # (gameId, nflId) → db_session_id
    sessions_rows: list[dict]       = []
    gps_rows:      list[dict]       = []
    tracking_rows: list[dict]       = []
    team_by_player: dict[int, str]  = {}
    sid = max_sid + 1

    for week in WEEKS:
        fpath = DATA_DIR / f"week{week}.feather"
        if not fpath.exists():
            log.warning(f"  week{week}.feather not found — skipping")
            continue

        log.info(f"  Loading week{week}.feather ({fpath.stat().st_size // 1_048_576} MB) …")
        track_df = pd.read_feather(fpath)
        log.info(f"    rows: {len(track_df):,}")

        # Exclude football-tracking rows (nflId is NaN for the ball)
        track_df = track_df[track_df["nflId"].notna()].copy()
        track_df["nflId"] = track_df["nflId"].astype(int)

        # Update team mapping
        for nfl_id, team in track_df.groupby("nflId")["team"].first().items():
            team_by_player[int(nfl_id)] = str(team)

        # Precompute metric columns
        track_df["speed_ms"]  = track_df["s"]   * YARDS_TO_M
        track_df["acc_ms2"]   = track_df["a"]   * YARDS_TO_M
        track_df["dis_m"]     = track_df["dis"] * YARDS_TO_M

        # ── aggregate per player per game ─────────────────────────────────────
        agg = (
            track_df.groupby(["gameId", "nflId"])
            .agg(
                total_dist_m = ("dis_m",    "sum"),
                avg_speed_ms = ("speed_ms", "mean"),
                max_speed_ms = ("speed_ms", "max"),
            )
            .reset_index()
        )

        sprint_df = (
            track_df[track_df["s"] > SPRINT_YDS_S]
            .groupby(["gameId", "nflId"])["dis_m"]
            .sum()
            .reset_index(name="sprint_dist_m")
        )

        hi_df = (
            track_df[track_df["a"] > HI_ACC_YDS_S2]
            .groupby(["gameId", "nflId"])
            .size()
            .reset_index(name="hi_efforts")
        )

        agg = (
            agg
            .merge(sprint_df, on=["gameId", "nflId"], how="left")
            .merge(hi_df,     on=["gameId", "nflId"], how="left")
        )
        agg["sprint_dist_m"] = agg["sprint_dist_m"].fillna(0)
        agg["hi_efforts"]    = agg["hi_efforts"].fillna(0).astype(int)

        for _, row in agg.iterrows():
            gid    = int(row["gameId"])
            nfl_id = int(row["nflId"])
            if nfl_id not in athlete_map:
                continue

            db_aid  = athlete_map[nfl_id]
            key     = (gid, nfl_id)
            if key not in session_map:
                meta = game_meta.get(gid, {})
                session_map[key] = sid
                sessions_rows.append({
                    "session_id":       sid,
                    "athlete_id":       db_aid,
                    "session_date":     meta.get("date", "09/01/2018"),
                    "duration_minutes": 60,
                    "session_type":     "match",
                    "competition":      f"NFL 2018 Week {meta.get('week', week)}",
                    "opponent":         meta.get("away", ""),
                    "home_away":        "home",
                    "data_source":      "nfl_big_data_bowl",
                    "match_id":         f"nfl_{gid}",
                })
                sid += 1

            gps_rows.append({
                "session_id":             session_map[key],
                "total_distance":         round(float(row["total_dist_m"]),  1),
                "sprint_distance":        round(float(row["sprint_dist_m"]), 1),
                "high_intensity_efforts": int(row["hi_efforts"]),
                "passes":    0, "shots":    0,
                "pressures": 0, "carries":  0, "dribbles": 0,
                "avg_speed": round(float(row["avg_speed_ms"]), 3),
                "max_speed": round(float(row["max_speed_ms"]), 3),
            })

        # ── sample tracking rows for player_tracking table ───────────────────
        sample = track_df.sample(n=min(TRACKING_SAMPLE, len(track_df)), random_state=42)
        for _, tr in sample.iterrows():
            nfl_id = int(tr["nflId"])
            gid    = int(tr["gameId"])
            if nfl_id not in athlete_map:
                continue
            key = (gid, nfl_id)
            if key not in session_map:
                continue
            tracking_rows.append({
                "athlete_id":   athlete_map[nfl_id],
                "session_id":   session_map[key],
                "play_id":      int(tr["playId"]),
                "frame_id":     int(tr["frameId"]),
                "x":            float(tr["x"]),
                "y":            float(tr["y"]),
                "speed":        float(tr["s"]) * YARDS_TO_M,
                "acceleration": float(tr["a"]) * YARDS_TO_M,
                "direction":    float(tr["dir"]) if pd.notna(tr.get("dir")) else None,
                "event_name":   str(tr["event"]) if pd.notna(tr.get("event")) and str(tr.get("event")) != "None" else None,
                "game_clock":   None,
            })

    # Update athlete teams from tracking
    for row in athletes_rows:
        nfl_id = next((k for k, v in athlete_map.items() if v == row["athlete_id"]), None)
        if nfl_id and nfl_id in team_by_player:
            row["team"] = team_by_player[nfl_id]

    log.info(
        f"Collected  athletes={len(athletes_rows):,}  sessions={len(sessions_rows):,}"
        f"  gps={len(gps_rows):,}  tracking={len(tracking_rows):,}"
    )

    # ── bulk insert ───────────────────────────────────────────────────────────
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:

            log.info(f"Inserting {len(athletes_rows):,} NFL athletes …")
            cur.executemany(
                """
                INSERT INTO athletes
                    (athlete_id, name, position, team, sport,
                     nationality, birth_date, jersey_no)
                VALUES
                    (%(athlete_id)s, %(name)s, %(position)s, %(team)s,
                     %(sport)s, %(nationality)s, %(birth_date)s, %(jersey_no)s)
                ON CONFLICT (athlete_id) DO UPDATE
                    SET team = EXCLUDED.team
                """,
                athletes_rows,
            )

            log.info(f"Inserting {len(sessions_rows):,} sessions …")
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

            log.info(f"Inserting {len(gps_rows):,} gps_metrics rows …")
            cur.executemany(
                """
                INSERT INTO gps_metrics
                    (session_id, total_distance, sprint_distance,
                     high_intensity_efforts, passes, shots, pressures,
                     carries, dribbles, avg_speed, max_speed)
                VALUES
                    (%(session_id)s, %(total_distance)s, %(sprint_distance)s,
                     %(high_intensity_efforts)s, %(passes)s, %(shots)s,
                     %(pressures)s, %(carries)s, %(dribbles)s,
                     %(avg_speed)s, %(max_speed)s)
                ON CONFLICT (session_id) DO NOTHING
                """,
                gps_rows,
            )

            if tracking_rows:
                log.info(f"Inserting {len(tracking_rows):,} player_tracking rows …")
                cur.executemany(
                    """
                    INSERT INTO player_tracking
                        (athlete_id, session_id, play_id, frame_id,
                         x, y, speed, acceleration, direction,
                         event_name, game_clock)
                    VALUES
                        (%(athlete_id)s, %(session_id)s, %(play_id)s, %(frame_id)s,
                         %(x)s, %(y)s, %(speed)s, %(acceleration)s, %(direction)s,
                         %(event_name)s, %(game_clock)s)
                    """,
                    tracking_rows,
                )

            conn.commit()

    log.info("✅ NFL ETL complete.")
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            for tbl in ("athletes", "sessions", "gps_metrics", "player_tracking"):
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                log.info(f"  {tbl}: {cur.fetchone()[0]:,} rows")
            cur.execute(
                "SELECT sport, COUNT(DISTINCT athlete_id) FROM athletes GROUP BY sport"
            )
            log.info("  Athletes by sport:")
            for row in cur.fetchall():
                log.info(f"    {row[0]}: {row[1]:,}")


if __name__ == "__main__":
    run()
