-- ============================================================
-- Sports Analytics Schema Extension
-- Adds StatsBomb (soccer) + NFL Big Data Bowl (american football)
-- columns and tables while preserving existing seed data.
-- ============================================================

-- ── Extend: athletes ─────────────────────────────────────────
ALTER TABLE athletes ADD COLUMN IF NOT EXISTS sport        TEXT    DEFAULT 'soccer';
ALTER TABLE athletes ADD COLUMN IF NOT EXISTS nationality  TEXT;
ALTER TABLE athletes ADD COLUMN IF NOT EXISTS birth_date   TEXT;
ALTER TABLE athletes ADD COLUMN IF NOT EXISTS jersey_no    INT;

-- ── Extend: sessions ─────────────────────────────────────────
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS competition  TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS opponent     TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS home_away    TEXT;    -- 'home' | 'away'
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS data_source  TEXT    DEFAULT 'seed';
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS match_id     TEXT;   -- source match ID

-- Drop the old unique constraint (athlete + date) so the same
-- athlete can have one row per match even on the same date (edge case).
ALTER TABLE sessions DROP CONSTRAINT IF EXISTS sessions_athlete_id_session_date_key;
ALTER TABLE sessions DROP CONSTRAINT IF EXISTS sessions_athlete_match_key;
-- NOTE: must NOT be DEFERRABLE — the ETL relies on ON CONFLICT, which rejects
-- deferrable unique constraints as arbiters.
ALTER TABLE sessions ADD CONSTRAINT sessions_athlete_match_key
    UNIQUE (athlete_id, match_id);

-- ── Extend: gps_metrics ──────────────────────────────────────
ALTER TABLE gps_metrics ADD COLUMN IF NOT EXISTS passes     INTEGER DEFAULT 0;
ALTER TABLE gps_metrics ADD COLUMN IF NOT EXISTS shots      INTEGER DEFAULT 0;
ALTER TABLE gps_metrics ADD COLUMN IF NOT EXISTS pressures  INTEGER DEFAULT 0;
ALTER TABLE gps_metrics ADD COLUMN IF NOT EXISTS carries    INTEGER DEFAULT 0;
ALTER TABLE gps_metrics ADD COLUMN IF NOT EXISTS dribbles   INTEGER DEFAULT 0;
ALTER TABLE gps_metrics ADD COLUMN IF NOT EXISTS avg_speed  NUMERIC;   -- m/s (NFL)
ALTER TABLE gps_metrics ADD COLUMN IF NOT EXISTS max_speed  NUMERIC;   -- m/s (NFL)

-- ── New: competitions ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS competitions (
    competition_id  SERIAL  PRIMARY KEY,
    name            TEXT    NOT NULL,
    sport           TEXT    NOT NULL,   -- 'soccer' | 'american_football'
    season          TEXT,
    country         TEXT,
    start_date      TEXT,
    end_date        TEXT
);

-- ── New: player_tracking (NFL frame-level data) ───────────────
CREATE TABLE IF NOT EXISTS player_tracking (
    tracking_id   BIGSERIAL PRIMARY KEY,
    athlete_id    INTEGER   REFERENCES athletes(athlete_id),
    session_id    INTEGER   REFERENCES sessions(session_id),
    play_id       INTEGER,
    frame_id      INTEGER,
    x             NUMERIC,  -- yards from left endzone
    y             NUMERIC,  -- yards from bottom sideline
    speed         NUMERIC,  -- yards/second
    acceleration  NUMERIC,  -- yards/second²
    direction     NUMERIC,  -- degrees (0=right, 90=up)
    event_name    TEXT,     -- snap, handoff, tackle, etc.
    game_clock    TEXT
);

CREATE INDEX IF NOT EXISTS idx_tracking_athlete  ON player_tracking(athlete_id);
CREATE INDEX IF NOT EXISTS idx_tracking_session  ON player_tracking(session_id);
CREATE INDEX IF NOT EXISTS idx_tracking_play     ON player_tracking(play_id);

-- ── Seed: competitions rows ───────────────────────────────────
INSERT INTO competitions (name, sport, season, country, start_date, end_date)
VALUES
    ('FIFA World Cup',          'soccer',             '2022', 'Qatar',        '11/20/2022', '12/18/2022'),
    ('NFL Big Data Bowl',       'american_football',  '2018', 'United States', '09/06/2018', '02/03/2019')
ON CONFLICT DO NOTHING;

-- ── Indexes for common analytics filters / groupings ─────────
CREATE INDEX IF NOT EXISTS idx_athletes_nationality  ON athletes(nationality);
CREATE INDEX IF NOT EXISTS idx_athletes_sport        ON athletes(sport);
CREATE INDEX IF NOT EXISTS idx_sessions_competition  ON sessions(competition);
