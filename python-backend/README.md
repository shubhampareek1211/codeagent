# Python Backend

FastAPI service that answers natural-language sports analytics questions against
PostgreSQL. The pipeline is **fully deterministic** (no LLM yet — see PLAN.md M3):
a constrained intent grammar feeds a query planner and a deterministic SQL
compiler; only `SELECT`/CTE against the analytics schema is ever executed.

Endpoints:

- `GET /health`
- `POST /query`
- `GET /metrics`
- `GET /schema`
- `POST /retrieval/debug`
- `POST /intent/debug`
- `POST /sql/debug`

## Pipeline (15-node LangGraph)

1. normalize query
2. extract structured intent (word-boundary grammar + DB-grounded athlete index)
3. detect ambiguity → clarify instead of guessing
4. decide whether retrieval is needed
5. retrieve KPI/schema/business context when needed
6. build a constrained query plan
7. validate the plan (rejects invalid metric×filter combos, e.g. wellness × competition)
8. deterministically compile SQL
9. validate SQL statically **and via engine `EXPLAIN`** when a DB is configured
10. execute SQL (errors surface as warnings, never 500s)
11. post-process results
12. validate results
13. choose a chart recommendation
14. generate a grounded summary
15. finalize response

Relative time windows ("last week", baseline defaults) are anchored to the
dataset's `MAX(session_date)`, not the wall clock — the datasets are historical.

## Data Model

Six tables (see `etl/schema_migration.sql` for the full definitions):

- `athletes(athlete_id, name, position, team, sport, nationality, birth_date, jersey_no)`
- `sessions(session_id, athlete_id, session_date, duration_minutes, session_type, competition, opponent, home_away, data_source, match_id)`
- `gps_metrics(session_id, total_distance, sprint_distance, high_intensity_efforts, passes, shots, pressures, carries, dribbles, avg_speed, max_speed)`
- `wellness(athlete_id, date, fatigue_score, sleep_score)`
- `player_tracking(tracking_id, athlete_id, session_id, play_id, frame_id, x, y, speed, acceleration, direction, event_name, game_clock)`
- `competitions(competition_id, name, sport, season, country, start_date, end_date)`

Implementation notes:

- `workload` is a proxy metric, not a physical column
- dates are stored as `MM/DD/YYYY` text and converted with `TO_DATE(...)` at
  query time (native `DATE` migration is PLAN.md M5)
- NFL sessions carry `competition = 'NFL 2018 Week N'` (the Big Data Bowl 2021
  dataset covers the 2018 season); soccer sessions carry `'FIFA World Cup 2022'`
- retrieval supports business-term grounding, but numeric answers always come
  from SQL execution; the backend never executes model-authored SQL

## Local Run

```bash
cd python-backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export SPORTS_DATABASE_URL="postgresql://creatorhub:creatorhub_pass@localhost:5433/creatorhub_dev"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Bootstrap

Start PostgreSQL from the repo root:

```bash
docker compose up -d postgres
```

Then either bootstrap manually:

```bash
psql postgresql://creatorhub:creatorhub_pass@localhost:5433/creatorhub_dev -f sql/sports_analytics_schema.sql
psql postgresql://creatorhub:creatorhub_pass@localhost:5433/creatorhub_dev -f sql/sports_analytics_seed.sql
```

Or set:

```bash
export SPORTS_AUTO_BOOTSTRAP=true
```

To load the real datasets, see `etl/` and the root README.

## Tests & Evaluation

```bash
cd python-backend
pytest tests/ -v                      # unit + regression tests
python eval/run_eval.py               # golden-question eval (offline)
python eval/run_eval.py --execute     # + EXPLAIN/execute against the live DB
```

`eval/golden_questions.json` is the answer-quality regression gate: it contains
every README-advertised query plus a case per audit bug (see PLAN.md). Extend it
whenever a new query shape is supported or a new bug is fixed.
