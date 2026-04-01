# Python Backend

This FastAPI service is the sports analytics backend for the workbench frontend.

Endpoints:

- `GET /health`
- `POST /query`
- `GET /metrics`
- `GET /schema`
- `POST /retrieval/debug`
- `POST /intent/debug`
- `POST /sql/debug`

## Pipeline

The backend runs a constrained analytics pipeline:

1. normalize query
2. extract structured intent
3. detect ambiguity
4. decide whether retrieval is needed
5. retrieve KPI/schema/business context when needed
6. build a constrained query plan
7. validate the plan
8. deterministically compile SQL
9. validate SQL
10. execute SQL against PostgreSQL
11. post-process results
12. choose a chart recommendation
13. generate a grounded summary

## Data Model

The backend targets this DataGrip-style schema:

- `athletes(athlete_id, name, position, team)`
- `sessions(session_id, athlete_id, session_date, duration_minutes, session_type)`
- `gps_metrics(session_id, total_distance, sprint_distance, high_intensity_efforts)`
- `wellness(athlete_id, date, fatigue_score, sleep_score)`

Implementation notes:

- `workload` is a proxy metric, not a physical column
- date filters convert `session_date` and `date` with `TO_DATE(..., 'MM/DD/YYYY')`
- retrieval supports business-term grounding, but numeric answers always come from SQL execution
- the backend never executes arbitrary model-authored SQL

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

## Tests

```bash
cd python-backend
pytest tests/test_sports_intent.py tests/test_sports_sql.py tests/test_sports_service.py
```
