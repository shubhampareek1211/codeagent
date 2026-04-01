INSERT INTO athletes (athlete_id, name, position, team)
VALUES
    (1, 'James Smith', 'Forward', 'North'),
    (2, 'Liam Johnson', 'Midfielder', 'North'),
    (3, 'Noah Williams', 'Defender', 'North'),
    (4, 'Oliver Brown', 'Forward', 'South'),
    (5, 'Elijah Jones', 'Midfielder', 'South'),
    (6, 'William Garcia', 'Defender', 'South')
ON CONFLICT (athlete_id) DO UPDATE
SET
    name = EXCLUDED.name,
    position = EXCLUDED.position,
    team = EXCLUDED.team;

WITH seeded_sessions AS (
    SELECT
        (a.athlete_id * 1000 + EXTRACT(DOY FROM calendar.session_date)::INT) AS session_id,
        a.athlete_id,
        calendar.session_date,
        CASE a.position
            WHEN 'Forward' THEN 84 + ((EXTRACT(DAY FROM calendar.session_date)::INT + a.athlete_id) % 7)
            WHEN 'Midfielder' THEN 80 + ((EXTRACT(DAY FROM calendar.session_date)::INT + a.athlete_id) % 6)
            ELSE 76 + ((EXTRACT(DAY FROM calendar.session_date)::INT + a.athlete_id) % 5)
        END::NUMERIC AS duration_minutes,
        CASE
            WHEN EXTRACT(ISODOW FROM calendar.session_date) IN (6, 7) THEN 'match'
            WHEN EXTRACT(ISODOW FROM calendar.session_date) = 3 THEN 'recovery'
            ELSE 'training'
        END AS session_type
    FROM athletes a
    CROSS JOIN LATERAL (
        SELECT generate_series(CURRENT_DATE - INTERVAL '20 days', CURRENT_DATE, INTERVAL '1 day')::DATE AS session_date
    ) calendar
)
INSERT INTO sessions (session_id, athlete_id, session_date, duration_minutes, session_type)
SELECT
    session_id,
    athlete_id,
    TO_CHAR(session_date, 'FMMM/FMDD/YYYY'),
    duration_minutes,
    session_type
FROM seeded_sessions
ON CONFLICT (session_id) DO UPDATE
SET
    athlete_id = EXCLUDED.athlete_id,
    session_date = EXCLUDED.session_date,
    duration_minutes = EXCLUDED.duration_minutes,
    session_type = EXCLUDED.session_type;

INSERT INTO gps_metrics (session_id, total_distance, sprint_distance, high_intensity_efforts)
SELECT
    s.session_id,
    ROUND(
        (
            CASE s.athlete_id
                WHEN 4 THEN 4200
                WHEN 1 THEN 4090
                WHEN 5 THEN 3850
                WHEN 2 THEN 3780
                WHEN 6 THEN 3640
                ELSE 3570
            END
            + ((EXTRACT(DAY FROM TO_DATE(s.session_date, 'MM/DD/YYYY'))::INT + s.athlete_id) % 140)
        )::NUMERIC,
        2
    ) AS total_distance,
    ROUND(
        (
            CASE s.athlete_id
                WHEN 4 THEN 560
                WHEN 1 THEN 540
                WHEN 5 THEN 455
                WHEN 2 THEN 440
                WHEN 6 THEN 370
                ELSE 360
            END
            + ((EXTRACT(DAY FROM TO_DATE(s.session_date, 'MM/DD/YYYY'))::INT + s.athlete_id) % 40)
        )::NUMERIC,
        2
    ) AS sprint_distance,
    ROUND(
        (
            CASE s.athlete_id
                WHEN 4 THEN 22
                WHEN 1 THEN 21
                WHEN 5 THEN 19
                WHEN 2 THEN 18
                WHEN 6 THEN 16
                ELSE 15
            END
            + ((EXTRACT(DAY FROM TO_DATE(s.session_date, 'MM/DD/YYYY'))::INT + s.athlete_id) % 4)
        )::NUMERIC,
        2
    ) AS high_intensity_efforts
FROM sessions s
ON CONFLICT (session_id) DO UPDATE
SET
    total_distance = EXCLUDED.total_distance,
    sprint_distance = EXCLUDED.sprint_distance,
    high_intensity_efforts = EXCLUDED.high_intensity_efforts;

WITH wellness_calendar AS (
    SELECT generate_series(CURRENT_DATE - INTERVAL '20 days', CURRENT_DATE, INTERVAL '1 day')::DATE AS metric_date
)
INSERT INTO wellness (athlete_id, date, fatigue_score, sleep_score)
SELECT
    a.athlete_id,
    TO_CHAR(wc.metric_date, 'FMMM/FMDD/YYYY') AS date,
    ROUND(
        (
            CASE a.position
                WHEN 'Forward' THEN 4.9
                WHEN 'Midfielder' THEN 4.5
                ELSE 4.2
            END
            + (((EXTRACT(DAY FROM wc.metric_date)::INT + a.athlete_id) % 5) * 0.2)
        )::NUMERIC,
        2
    ) AS fatigue_score,
    ROUND(
        (
            CASE a.position
                WHEN 'Forward' THEN 7.0
                WHEN 'Midfielder' THEN 7.2
                ELSE 7.4
            END
            - (((EXTRACT(DAY FROM wc.metric_date)::INT + a.athlete_id) % 4) * 0.15)
        )::NUMERIC,
        2
    ) AS sleep_score
FROM athletes a
CROSS JOIN wellness_calendar wc
ON CONFLICT (athlete_id, date) DO UPDATE
SET
    fatigue_score = EXCLUDED.fatigue_score,
    sleep_score = EXCLUDED.sleep_score;
