# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Natural-language sports analytics engine: freeform questions → validated SQL → PostgreSQL → structured results with chart recommendations. Two datasets: FIFA World Cup 2022 (StatsBomb) and NFL Big Data Bowl 2021 (GPS tracking of the **2018** NFL season — sessions carry `competition = 'NFL 2018 Week N'`).

**Be precise about what this is: the pipeline is currently 100% deterministic — there is no LLM anywhere in it.** "Intent extraction" is a word-boundary keyword grammar (`intent.py`); "confidence" is additive point arithmetic; summaries are f-string templates. An LLM-based intent extractor is planned (PLAN.md M3) behind the same `StructuredIntent` contract. Do not write docs or summaries implying AI capabilities the code doesn't have.

**Core invariant (keep forever): no model or user input is ever executed as SQL.** Intent becomes a structured object; `python-backend/app/sports_analytics/sql.py` deterministically compiles SQL from it, fully parameterized. Only `SELECT`/CTE against the analytics schema is permitted, and compiled SQL is `EXPLAIN`-validated against the live engine before execution when a DB is configured.

**`PLAN.md` is the roadmap.** It maps every audit finding (B1–B5, M1–M10, m1–m10) to milestones with acceptance criteria. Check a task's box only when its acceptance criterion passes.

## Commands

### Frontend (repo root, Next.js 14 + TypeScript)

```bash
npm install
npm run dev          # http://localhost:3000/sports-analytics
npm run build
npm run typecheck    # tsc --noEmit — no lint script exists; use this as the check
```

### Backend (python-backend/, Python 3.12 + FastAPI)

```bash
cd python-backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

SPORTS_DATABASE_URL="postgresql://creatorhub:creatorhub_pass@localhost:5433/creatorhub_dev" \
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# API docs: http://127.0.0.1:8000/docs
```

### Database

```bash
docker compose up -d postgres        # repo root; Postgres 16 on port 5433
# Bootstrap either manually:
psql postgresql://creatorhub:creatorhub_pass@localhost:5433/creatorhub_dev -f sql/sports_analytics_schema.sql
psql postgresql://creatorhub:creatorhub_pass@localhost:5433/creatorhub_dev -f sql/sports_analytics_seed.sql
# ...or set SPORTS_AUTO_BOOTSTRAP=true before starting uvicorn
```

### Tests (from python-backend/, venv active)

```bash
pytest tests/ -v                                   # all tests
pytest tests/test_sports_sql.py -v                 # one file
pytest tests/test_sports_intent.py -k "nationality" -v   # single test by keyword
python eval/run_eval.py                            # golden-question eval (offline)
python eval/run_eval.py --execute                  # + EXPLAIN/execute vs live DB
```

Test files: `test_sports_intent.py` (intent extraction), `test_sports_sql.py` (SQL compiler), `test_sports_service.py` (pipeline). `conftest.py` provides fixtures.

**`eval/golden_questions.json` is the answer-quality regression gate.** Every advertised query and every fixed wrong-answer bug lives there. When you fix an intent/SQL bug or add a query capability, add a golden case in the same change — a fix without a golden case is not done.

### ETL (one-time data loads; from python-backend/)

```bash
python etl/run_migration.py       # base schema + extensions + indexes
python etl/statsbomb_etl.py       # FIFA World Cup 2022 — free, auto-downloads
python etl/nfl_etl.py             # NFL week 1 — needs ~/.kaggle/kaggle.json
python etl/wellness_seed.py       # synthetic wellness scores
```

## Architecture

### Request flow

```
Browser → app/sports-analytics/page.tsx → components/sports/SportsAnalyticsWorkbench.tsx
        → app/api/sports-analytics/route.ts   (Next.js proxy, nodejs runtime)
        → FastAPI backend at SPORTS_ANALYTICS_BACKEND_URL (default http://127.0.0.1:8000)
```

- `lib/env.ts` validates `SPORTS_ANALYTICS_BACKEND_URL` with zod at import time; the proxy has an 8s health / 15s query timeout and returns 503 when the backend is unreachable. This standalone repo has **no embedded fallback engine** — a running FastAPI backend is required for real answers.

### Backend pipeline (python-backend/app/sports_analytics/)

`service.py` builds a 15-node LangGraph `StateGraph`:

```
normalize_query → extract_intent → detect_ambiguity → decide_retrieval
  → [retrieve_context if confidence < 0.72] → build_plan → validate_plan
  → compile_sql → validate_sql → execute_sql → post_process
  → validate_results → choose_visualization → generate_summary → finalize
```

Responsibilities per module:

| Module | Role |
|---|---|
| `intent.py` | NL → `StructuredIntent` via word-boundary keyword grammar; nationality/position vocab + athlete entity matching live here |
| `registry.py` | 14 metrics + grouping aliases + schema catalog. **Add new metrics here first** |
| `planner.py` | StructuredIntent → constrained query plan; rejects invalid metric×filter combos (e.g. wellness metrics can't filter by competition) |
| `sql.py` | Deterministic plan → SQL compiler (the only place SQL strings are built); `_FILTER_COLUMNS` maps filter fields to columns, multi-value filters compile to `= ANY(%s)` |
| `retrieval.py` | Hybrid BM25 + FAISS over `data/sports_analytics/*.json` corpus; degrades gracefully to BM25-only when torch/faiss absent (deploy build). ⚠️ Currently only decorates summaries — refit planned in PLAN.md T3.3 |
| `repository.py` | psycopg executor; also `explain()` (engine validation), `get_max_session_date()` (window anchoring), `list_athlete_names()` (entity index) |
| `models.py` | Pydantic request/response + state models |
| `knowledge.py` | KPI/schema/business-rule corpus loading |

⚠️ **"Single source of truth" is aspirational until PLAN.md T2.1**: adding a *grouping/dimension* still touches `registry.py` (aliases), `sql.py` (`_dimension_expression`, `_FILTER_COLUMNS`), `planner.py` (supported set), and `service.py` (`_GROUP_DIMENSION_LABELS`). Touch all four or the feature half-works.

Pipeline behaviors worth knowing before debugging:
- Relative time windows anchor to `MAX(session_date)` in the DB, **not** `date.today()` — the datasets are historical.
- All keyword matching is word-boundary based (`_term_pattern` in `intent.py`, tolerates plural `s`). Never add a bare-substring match.
- DB errors surface as response warnings, not 500s; `EXPLAIN` runs before execution when a DB is configured.

Debug endpoints expose individual stages: `POST /intent/debug`, `/sql/debug`, `/retrieval/debug` — use these when diagnosing a wrong answer before touching code.

### Schema (6 tables)

`athletes`, `sessions`, `gps_metrics`, `wellness`, `player_tracking`, `competitions` — see `python-backend/etl/schema_migration.sql`. Key semantics: `sport` is `'soccer' | 'american_football'`; `workload` is a proxy metric, not a physical column; date filters use `TO_DATE(..., 'MM/DD/YYYY')`.

### Deployment

- `render.yaml` (root) deploys backend + free Postgres to Render. **Use `requirements-deploy.txt`, never `requirements.txt`, for deploys** — torch OOMs the 512 MB free tier. See `DEPLOY_BACKEND.md` for the full runbook.
- Frontend deploys to Vercel; set `SPORTS_ANALYTICS_BACKEND_URL` there.

---

## Multi-Agent Coordination (Orchestrator Architecture)

When multiple Claude agents work in this repo concurrently, they coordinate through `scratchpad.md` (the shared task board). Read it **before starting any work**.

### Roles

- **Orchestrator** — the main session. Decomposes the user's request into tasks, writes them to `scratchpad.md`, spawns subagents (via the Agent tool or parallel sessions), reviews their results, and marks tasks done. Only the orchestrator creates or reprioritizes tasks.
- **Worker agents** — claim exactly one task at a time, execute it, append results/notes under their own task entry, and set the status. Suggested specializations: *explorer* (read-only research), *implementer* (code changes), *tester* (run pytest/typecheck and report), *reviewer* (diff review).

### Task protocol — non-negotiable rules

1. **Append-only for others' content.** Never edit, rewrite, or delete a task entry created by another agent. You may only change the `Status`/`Owner`/`Result` lines of a task **you have claimed**.
2. **Claim before work.** Set `Owner:` to your agent ID and `Status: in_progress` before touching code. If a task already has an owner, pick a different task — never take over a claimed task unless the orchestrator explicitly reassigns it.
3. **One task, one owner, one scope.** Don't expand a task's scope mid-flight; append a proposed follow-up task to the Backlog instead and let the orchestrator triage it.
4. **Unique task IDs.** IDs are `T-<n>`, monotonically increasing. Before adding a task, read the file and use max existing ID + 1. New tasks are appended to the *end* of the Backlog section — never inserted between existing entries (prevents merge collisions).
5. **Record outcomes.** On completion set `Status: done` (or `blocked` with a reason) and fill `Result:` with what changed (files touched, test results). Failures are reported honestly — a failing test is a `blocked`/`done-with-findings` result, not a reason to leave the entry stale.
6. **File-conflict avoidance.** A task entry lists the files it expects to touch (`Touches:`). Two in-progress tasks must not share a file; if yours would, wait or ask the orchestrator to sequence them. For genuinely parallel code edits, workers should use worktree isolation.

### Task entry format (used in scratchpad.md)

```markdown
### T-3 · Add max_speed to metric registry
- Status: backlog | in_progress | blocked | done
- Owner: — | <agent-id>
- Created-by: orchestrator
- Touches: python-backend/app/sports_analytics/registry.py, tests/test_sports_sql.py
- Task: <what to do, acceptance criteria>
- Result: <filled in by owner on completion — files changed, tests run, findings>
```
