# Sports Analytics Workbench

Natural-language sports analytics engine that converts freeform questions into validated SQL, executes them against a live PostgreSQL database, and returns structured results with chart recommendations.

**Live demo:** https://shubham-pareek-portfolio.vercel.app/sports-analytics

---

## Overview

```
User query (NL)
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    15-node LangGraph Pipeline                    │
│                                                                  │
│  normalize → extract_intent → detect_ambiguity                   │
│       │                              │                           │
│  [confidence < 0.72]          decide_retrieval                   │
│       └──────► retrieve_context ─────┘                          │
│                      │                                           │
│               build_plan → validate_plan                         │
│                      │                                           │
│              compile_sql → validate_sql → execute_sql            │
│                                               │                  │
│                          post_process → validate_results         │
│                                               │                  │
│                        choose_visualization → generate_summary   │
└─────────────────────────────────────────────────────────────────┘
      │
      ▼
Structured response: summary · chart recommendation · SQL · data rows
```

**Key constraint:** the model never authors SQL. Intent is extracted into a structured object; a deterministic compiler generates SQL from that object. Only `SELECT`/`CTE` against an allowlisted table set is permitted.

---

## Datasets

### FIFA World Cup 2022 — StatsBomb Open Data

| | |
|---|---|
| Athletes | 829 across 32 nations |
| Matches | 64 |
| Sessions | 3,244 |
| GPS rows | 1,996 |
| Source | statsbombpy (free, no credentials required) |

Metrics computed from event data:

| Metric | Derivation |
|--------|-----------|
| `total_distance` | Carry distances + pass lengths + position baseline (m) |
| `sprint_distance` | Carries where Euclidean distance > 5 m |
| `high_intensity_efforts` | Pressures + shots + tackles + dribbles |
| `passes` / `shots` / `pressures` / `carries` / `dribbles` | Raw event counts |

### NFL Big Data Bowl 2021 — GPS Tracking

| | |
|---|---|
| Athletes | 1,303 |
| Week 1 sessions | 602 |
| Tracking frames (sampled) | 10,000 |
| Source | Kaggle — mathurinache/nflbigdatabowl2021-feather-files |

Metrics computed from 10 fps tracking frames (yards → metres via × 0.9144):

| Metric | Derivation |
|--------|-----------|
| `total_distance` | `SUM(dis)` per player per game |
| `sprint_distance` | `SUM(dis)` where speed > 4.88 yd/s |
| `high_intensity_efforts` | Frame count where acceleration > 3.28 yd/s² |
| `avg_speed` / `max_speed` | Mean / max speed in m/s |

---

## Schema

```sql
-- Core (extended from original 4-table seed schema)
athletes(
  athlete_id, name, position, team,
  sport,        -- 'soccer' | 'american_football'
  nationality, birth_date, jersey_no
)

sessions(
  session_id, athlete_id, session_date, duration_minutes, session_type,
  competition,  -- 'FIFA World Cup 2022' | 'NFL 2018 Week N'
  opponent, home_away, data_source, match_id
)

gps_metrics(
  session_id,
  total_distance, sprint_distance, high_intensity_efforts,  -- original
  passes, shots, pressures, carries, dribbles,              -- StatsBomb
  avg_speed, max_speed                                      -- NFL tracking
)

wellness(athlete_id, date, fatigue_score, sleep_score)

-- New
player_tracking(
  tracking_id, athlete_id, session_id, play_id, frame_id,
  x, y, speed, acceleration, direction, event_name, game_clock
)

competitions(competition_id, name, sport, season, country, start_date, end_date)
```

---

## Supported Queries

```
"Top 10 players by total distance in the World Cup"
"Which position had the most pressures in the World Cup?"
"Top 5 NFL wide receivers by sprint distance"
"Average passes per position in soccer"
"Top 5 Argentine players by total distance"
"Which NFL position averages the highest speed?"
"Which nationality scored the most shots?"
"Average sprint distance by sport"
"Top pressers in the World Cup"
"Compare total distance between soccer and american football"
```

### Query capabilities

| Dimension | Supported values |
|-----------|-----------------|
| Metrics | total_distance · sprint_distance · high_intensity_efforts · passes · shots · pressures · carries · dribbles · avg_speed · max_speed · duration_minutes · fatigue_score · sleep_score |
| Groupings | position · team · nationality · sport · competition · opponent · session_date · athlete_name |
| Sport filter | `"nfl"` / `"american football"` → `sport = 'american_football'` |
| Competition filter | `"world cup"` / `"fifa"` → `competition ILIKE '%World Cup%'` |
| Nationality | demonyms supported: "Argentine", "French", "Brazilian", "Dutch", etc. |
| Ranking | top / bottom N |
| Comparison | baseline gap · trend over time |

---

## Project Structure

```
├── app/
│   ├── api/sports-analytics/route.ts   Next.js proxy to the FastAPI backend
│   └── sports-analytics/page.tsx       Workbench page
├── components/sports/
│   └── SportsAnalyticsWorkbench.tsx    Workbench UI
└── python-backend/
    ├── app/
    │   ├── main.py                     FastAPI app
    │   └── sports_analytics/
    │       ├── intent.py               Intent extractor (word-boundary grammar + entity index)
    │       ├── planner.py              Query planner + plan validation
    │       ├── sql.py                  Deterministic SQL compiler
    │       ├── registry.py             Metric + grouping registry (14 metrics)
    │       ├── service.py              LangGraph service (15 nodes)
    │       ├── retrieval.py            Hybrid BM25 + FAISS retrieval
    │       └── repository.py           PostgreSQL executor (+ EXPLAIN validation)
    ├── etl/
    │   ├── schema_migration.sql        Schema extension (run once)
    │   ├── statsbomb_etl.py            FIFA World Cup 2022 ETL
    │   └── nfl_etl.py                  NFL Big Data Bowl 2021 ETL (2018 season data)
    ├── sql/
    │   ├── sports_analytics_schema.sql Base schema
    │   └── sports_analytics_seed.sql   Synthetic seed data
    ├── data/sports_analytics/          Retrieval corpus (JSON)
    ├── eval/                           Golden-question eval harness
    └── tests/                          Intent / SQL / service tests
```

See `PLAN.md` for the audit-driven rebuild roadmap and `CLAUDE.md` for agent
working conventions.

---

## Quick Start

### 1. Start PostgreSQL

```bash
docker compose up -d postgres
```

### 2. Start the backend

```bash
cd python-backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

SPORTS_DATABASE_URL="postgresql://creatorhub:creatorhub_pass@localhost:5433/creatorhub_dev" \
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API docs: http://127.0.0.1:8000/docs

### 3. Load real data (first time)

```bash
cd python-backend

# Run schema migration
docker exec -i <postgres_container> psql -U creatorhub -d creatorhub_dev \
  < etl/schema_migration.sql

# StatsBomb — FIFA World Cup 2022 (free, auto-downloads via statsbombpy)
python etl/statsbomb_etl.py

# NFL Big Data Bowl 2021 (requires Kaggle credentials)
# 1. Download kaggle.json from kaggle.com/settings → API → Create New Token
# 2. Place at ~/.kaggle/kaggle.json  (chmod 600)
# 3. Accept dataset terms at kaggle.com/datasets/mathurinache/nflbigdatabowl2021-feather-files
python etl/nfl_etl.py
```

To load all 17 NFL weeks (full season), update `WEEKS = list(range(1, 18))` in `etl/nfl_etl.py`.

### 4. Start the frontend

```bash
# repo root
cp .env.example .env.local
# set: SPORTS_ANALYTICS_BACKEND_URL=http://127.0.0.1:8000

npm install
npm run dev
```

Open http://localhost:3000/sports-analytics

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service + DB health check |
| `POST` | `/query` | Run a natural-language analytics query |
| `GET` | `/metrics` | Catalog of all supported metrics |
| `GET` | `/schema` | DB schema summary |
| `POST` | `/intent/debug` | Inspect intent extraction for a query |
| `POST` | `/sql/debug` | Inspect compiled SQL for a query |
| `POST` | `/retrieval/debug` | Inspect retrieval results for a query |

### Example

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Top 5 Argentine players by total distance"}'
```

```json
{
  "summary": "The leading athlete is Rodrigo Javier De Paul with 95742.2 m.",
  "intent": { "metric": "total_distance", "filters": [{"field": "nationality", "value": "Argentina"}] },
  "visualization": { "chart_type": "bar", "title": "Top 5 Argentine Players — Total Distance" },
  "data": {
    "columns": ["athlete_name", "position", "metric_value"],
    "rows": [
      {"athlete_name": "Rodrigo Javier De Paul", "position": "midfielder", "metric_value": 95742.2},
      {"athlete_name": "Enzo Fernandez",          "position": "midfielder", "metric_value": 94221.4}
    ],
    "row_count": 5
  },
  "sql": "SELECT a.name AS athlete_name, a.position, ROUND(SUM(g.total_distance)::numeric, 2) ..."
}
```

---

## Production

The Next.js proxy (`app/api/sports-analytics/route.ts`) forwards to
`SPORTS_ANALYTICS_BACKEND_URL` (default `http://127.0.0.1:8000`). If the backend
is unreachable it returns a structured 503 — this standalone repo has **no
embedded demo engine**; a deployed FastAPI backend (see `DEPLOY_BACKEND.md`) is
required for production use.

---

## Tests & Evaluation

```bash
cd python-backend
pytest tests/ -v                      # unit + regression tests
python eval/run_eval.py               # golden-question eval (offline)
python eval/run_eval.py --execute     # + EXPLAIN/execute against the live DB
```

---

## Tech Stack

| | |
|---|---|
| Backend | Python 3.12 · FastAPI · LangGraph · psycopg |
| Retrieval | FAISS · sentence-transformers (all-MiniLM-L6-v2) · rank-bm25 |
| ETL | statsbombpy · pyarrow · pandas · kaggle CLI |
| Frontend | Next.js 14 · TypeScript · Tailwind CSS · Framer Motion |
| Database | PostgreSQL 16 (Docker) |
| Infra | Docker · Vercel |
