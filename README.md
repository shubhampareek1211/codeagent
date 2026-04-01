# Sports Analytics Workbench

Standalone natural-language sports analytics demo consisting of:

- a Next.js frontend workbench
- a FastAPI + LangGraph backend in `python-backend`
- deterministic intent extraction, query planning, SQL compilation, SQL validation, execution, and chart recommendation

## Repo Scope

This repo intentionally contains only the sports analytics slice:

- frontend page and proxy route for the workbench
- supporting frontend UI components and env helpers
- the Python analytics backend
- SQL bootstrap files, retrieval corpus, and backend tests

It does not include the rest of the portfolio, creator dashboard, or recruiter-chat application code.

## Project Structure

- `app/sports-analytics/page.tsx` frontend page
- `app/api/sports-analytics/route.ts` frontend proxy to the backend
- `components/sports/SportsAnalyticsWorkbench.tsx` workbench UI
- `python-backend/app/sports_analytics/*` analytics engine
- `python-backend/sql/*` schema and seed SQL
- `python-backend/data/sports_analytics/*` retrieval corpus

## Frontend Run

```bash
npm install
cp .env.example .env.local
npm run dev
```

Frontend URL:

- `http://localhost:3000/sports-analytics`

The frontend proxies requests to the backend URL in `SPORTS_ANALYTICS_BACKEND_URL`, which defaults to `http://127.0.0.1:8000`.

## Backend Run

```bash
cd python-backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export SPORTS_DATABASE_URL="postgresql://creatorhub:creatorhub_pass@localhost:5433/creatorhub_dev"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Backend docs:

- `http://127.0.0.1:8000/docs`

## Database

Start PostgreSQL:

```bash
docker compose up -d postgres
```

If you want the local demo dataset created automatically, set:

```bash
export SPORTS_AUTO_BOOTSTRAP=true
```

Current schema assumptions:

- `athletes(athlete_id, name, position, team)`
- `sessions(session_id, athlete_id, session_date, duration_minutes, session_type)`
- `gps_metrics(session_id, total_distance, sprint_distance, high_intensity_efforts)`
- `wellness(athlete_id, date, fatigue_score, sleep_score)`

Implementation notes:

- `workload` is a proxy metric derived from total distance, sprint distance, high intensity efforts, and duration
- dates are stored as text and converted with `TO_DATE(..., 'MM/DD/YYYY')`
- retrieval provides business-rule grounding only
- SQL is compiled from a constrained internal plan rather than executed directly from model output

## Backend Tests

```bash
cd python-backend
pytest tests/test_sports_intent.py tests/test_sports_sql.py tests/test_sports_service.py
```
