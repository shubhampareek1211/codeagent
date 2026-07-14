# Agent Scratchpad — Shared Task Board

> Coordination file for all agents working in this repo. The protocol lives in
> `CLAUDE.md` → "Multi-Agent Coordination". Summary of the hard rules:
>
> 1. **Never edit or delete another agent's entries.** Append-only, except the
>    `Status` / `Owner` / `Result` lines of a task *you* have claimed.
> 2. **Claim before work**: set `Owner:` + `Status: in_progress` first.
>    A task with an owner is off-limits to everyone else.
> 3. **New tasks go at the END of the Backlog** with ID = max existing ID + 1.
> 4. **No two in-progress tasks may touch the same file** (`Touches:` line).
> 5. Done tasks get moved by *their owner only* to the Done section, with
>    `Result:` filled in.

---

## Backlog

<!-- Orchestrator appends new tasks here. Template:

### T-<n> · <short title>
- Status: backlog
- Owner: —
- Created-by: <agent-id>
- Touches: <files this task is expected to modify>
- Task: <description + acceptance criteria>
- Result: —
-->

### T-1 · M2: Semantic model consolidation (PLAN.md T2.1–T2.3)
- Status: backlog
- Owner: —
- Created-by: orchestrator
- Touches: python-backend/app/sports_analytics/registry.py, intent.py, sql.py, planner.py, service.py
- Task: Single semantic-model artifact drives all vocab/dimensions; extend DB entity index to nationalities/teams/competitions; wire or delete approved_queries.json. Accept: adding a dimension touches one file.
- Result: —

### T-2 · M3: LLM intent extraction + rejection gate (PLAN.md T3.1–T3.3)
- Status: blocked
- Owner: —
- Created-by: orchestrator
- Touches: python-backend/app/sports_analytics/ (new intent_llm.py), retrieval.py, config.py
- Task: LLM extractor emitting StructuredIntent (constrained JSON), grammar as fallback; rejection gate for unknown entities/low confidence; retrieval feeds extraction. Accept: eval-set ≥ grammar baseline + paraphrase section passes.
- Result: — (blocked: needs ANTHROPIC_API_KEY / model-cost decision from owner)

### T-3 · M4 remainder: pooling, statement timeout, debug-path unification (PLAN.md T4.2–T4.3)
- Status: backlog
- Owner: —
- Created-by: orchestrator
- Touches: python-backend/app/sports_analytics/repository.py, service.py, main.py, requirements.txt
- Task: psycopg_pool, statement_timeout, readiness/liveness split; unify debug_sql limit logic with graph path.
- Result: —

### T-4 · M5: TEXT→DATE migration (PLAN.md T5.1)
- Status: blocked
- Owner: —
- Created-by: orchestrator
- Touches: python-backend/etl/, sql/, app/sports_analytics/sql.py
- Task: Migrate session_date/wellness.date to native DATE, update ETLs + compiler, add indexes. Accept: eval --execute green on migrated DB.
- Result: — (blocked: needs a running Postgres + coordinated ETL rerun)

## In Progress

_(owners move their claimed task entry here when starting)_

## Blocked

_(tasks whose owner hit a blocker — keep the entry, state the blocker in Result)_

## Done

### T-0 · Audit + M0/M1/T4.1/M6 rebuild (PLAN.md)
- Status: done
- Owner: orchestrator
- Created-by: orchestrator
- Touches: python-backend/app/**, tests/**, eval/** (new), etl/schema_migration.sql, components/sports/SportsAnalyticsWorkbench.tsx, README.md, python-backend/README.md, CLAUDE.md, PLAN.md
- Task: 4-phase audit → fix all blocker/major wrong-answer bugs (B1–B5, M1–M4), build golden eval harness, EXPLAIN validation, docs honesty pass.
- Result: 38/38 pytest, 17/17 golden questions offline, `npm run typecheck` green, `import app.main` OK. Deleted dead `app/knowledge.py` + portfolio config defaults. Live `eval --execute` NOT yet run (Docker daemon down) — run it once Postgres is up.

---

## Agent Notes (append-only log)

<!-- Freeform findings worth sharing across agents: gotchas discovered,
     decisions made, environment quirks. One bullet per note, prefixed with
     agent id and date. Never modify existing notes. -->

- `[orchestrator 2026-07-13]` Board initialized. Known repo gotchas already documented in CLAUDE.md: README mentions `demo-engine.ts`/`public-demo.json` which don't exist in this standalone repo; deploys must use `requirements-deploy.txt` (torch OOMs Render free tier); Postgres runs on port **5433**, not 5432.
- `[orchestrator 2026-07-13]` Audit + M0 rebuild landed. Gotchas for future agents: (1) NFL data is the **2018 season** (BDB 2021 dataset) with `nationality='USA'` while StatsBomb writes `'United States'` — intent expands US to both values until literal grounding (T2.2); (2) relative windows anchor to `MAX(session_date)`, so tests must pass `today=`; (3) all intent matching must stay word-boundary (`_term_pattern`) — bare `in` substring checks caused audit bugs M1/m1; (4) any wrong-answer fix must add a case to `eval/golden_questions.json`; (5) an already-loaded DB has the old competitions seed row (season '2022') — harmless metadata, corrected in migration for fresh loads.
