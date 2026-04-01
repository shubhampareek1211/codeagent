CREATE TABLE IF NOT EXISTS athletes (
    athlete_id INT PRIMARY KEY,
    name TEXT NOT NULL,
    position TEXT NOT NULL,
    team TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id INT PRIMARY KEY,
    athlete_id INT NOT NULL REFERENCES athletes (athlete_id),
    session_date TEXT NOT NULL,
    duration_minutes NUMERIC NOT NULL,
    session_type TEXT NOT NULL DEFAULT 'training',
    UNIQUE (athlete_id, session_date)
);

CREATE TABLE IF NOT EXISTS gps_metrics (
    session_id INT PRIMARY KEY REFERENCES sessions (session_id),
    total_distance NUMERIC NOT NULL,
    sprint_distance NUMERIC NOT NULL,
    high_intensity_efforts NUMERIC NOT NULL
);

CREATE TABLE IF NOT EXISTS wellness (
    athlete_id INT NOT NULL REFERENCES athletes (athlete_id),
    date TEXT NOT NULL,
    fatigue_score NUMERIC NOT NULL,
    sleep_score NUMERIC NOT NULL,
    PRIMARY KEY (athlete_id, date)
);

CREATE INDEX IF NOT EXISTS idx_sessions_athlete_date
    ON sessions (athlete_id, session_date);

CREATE INDEX IF NOT EXISTS idx_wellness_athlete_date
    ON wellness (athlete_id, date);
