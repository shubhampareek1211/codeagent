# PLAN.md — Structured Rebuild Plan

Derived from the 4-phase audit (2026-07-13). Issue IDs (B1–B5, M1–M10, m1–m10) refer to the
Phase 2 findings; references are Phase 3 sources:

- **[CA]** Snowflake Cortex Analyst — [Behind the Scenes](https://www.snowflake.com/en/blog/engineering/snowflake-cortex-analyst-behind-the-scenes/), [Evaluating Text-to-SQL Accuracy](https://www.snowflake.com/en/blog/engineering/cortex-analyst-text-to-sql-accuracy-bi/)
- **[QG]** Uber — [QueryGPT: NL to SQL](https://www.uber.com/us/en/blog/query-gpt/)
- **[PIC]** [PICARD: Constrained Auto-Regressive Decoding](https://aclanthology.org/2021.emnlp-main.779/) (EMNLP 2021)

**Strategy: no big-bang rewrite.** The deterministic plan→SQL compiler skeleton is right ([PIC]
vindicates constraint-based generation); the brittle layers around it are replaced milestone by
milestone. The app stays runnable after every task.

## Keep / Refactor / Discard

| Code | Decision | Rationale |
|---|---|---|
| `sql.py` compiler (3 query shapes, parameterized) | **Keep** (small fixes) | Sound closed-grammar design [PIC] |
| `planner.py` | **Keep** (add combo validation) | Correct constrained-plan abstraction |
| LangGraph `service.py` graph shape | **Keep** | Harmless; becomes justified once M3 adds real branching |
| `registry.py` | **Refactor** (M2) | Becomes the actual single-source semantic model [CA] |
| `intent.py` substring grammar | **Refactor now, replace at M3** | Root cause of most wrong answers; word-boundary + grounding fixes first, LLM extraction later |
| `retrieval.py` / `search.py` | **Refactor at M3** | Retrieval must feed intent extraction, not decorate summaries [CA][QG] |
| TEXT `MM/DD/YYYY` dates | **Discard at M5** | Migrate to native `DATE` |
| `app/knowledge.py` (portfolio loader) | **Discard now** | Dead, crashes if called |
| `validate_sql` string blocklist | **Demote** | Keep as cheap sanity check; real validation = engine `EXPLAIN` (M4) [CA] |
| Frontend workbench | **Keep** (honesty fixes) | Fine as a demo shell |

---

## Milestone 0 — Stop the bleeding (fix wrong-answer/crash bugs)
*Fixes: B1, B2, B3, B5, M1, M2, M3, M4. References: [CA] "trust over capability".*

- [x] **T0.1 Word-boundary matching in intent extraction** — all alias/keyword matching uses
  `\b`-bounded regex (with optional plural `s`), killing "min"⊂"minutes", "top"⊂"stop",
  "date"⊂anything. *Accept: `test_sports_intent.py` regression tests for minutes/aggregation pass.*
- [x] **T0.2 Same-field multi-value filters** — multiple positions/nationalities collapse into one
  `IN` filter; two sports with no grouping become `grouping=sport` (comparison semantics).
  *Accept: "Compare total distance between soccer and american football" (README query) returns
  grouped rows, not zero.*
- [x] **T0.3 Fix "american"→nationality misfire + canonical mismatch** — "american football" is
  masked before nationality matching; "United States" expands to `('United States','USA')` to match
  ETL-written values (real fix = M2 literal grounding). *Accept: "Top 5 american football players by
  sprint distance" carries sport filter only.*
- [x] **T0.4 Reject invalid metric×filter combos** — planner validation refuses wellness metrics
  with sessions-table filters/dimensions (competition/opponent/session_type) instead of compiling
  SQL that crashes. *Accept: "Average fatigue score in the World Cup" returns a clear validation
  message, not a 500.*
- [x] **T0.5 Anchor default time windows to the dataset, not `date.today()`** — service resolves
  `MAX(session_date)` once and passes it as the anchor for "last week"/baseline defaults.
  *Accept: baseline sample query works against historical data regardless of wall-clock date.*
- [x] **T0.6 Error handling on the execution path** — `execute_sql` node catches DB errors into a
  graceful response with a warning; repository gets connect timeouts. *Accept: DB down ⇒ structured
  answer with warning, not a 500 stack trace.*
- [x] **T0.7 Sport-scope precedence** — explicit "nfl"/"big data bowl" wins, then "world cup"/"fifa",
  then "american football"; the ambiguous bare "football player" heuristic is dropped.
- [x] **T0.8 Athlete-name entity filter (grounded)** — service loads athlete names from the DB at
  startup (graceful if absent) and intent matches them into an `athlete_name` filter, so "How many
  passes did Messi make?" answers about Messi. *Accept: intent test with injected name index.*

## Milestone 1 — Golden eval set (the real asset)
*Fixes: M9. References: [CA] accuracy benchmarking, [QG] evaluation harness.*

- [x] **T1.1 `eval/golden_questions.json`** — curated Q→expected-intent/SQL-property pairs, seeded
  with every Phase 2 bug query plus the README's advertised queries.
- [x] **T1.2 `eval/run_eval.py`** — runs each question through intent→plan→SQL offline (no DB),
  scores expectations, exits non-zero on regression; optional `--execute` mode against a live DB.
  *Accept: `python eval/run_eval.py` green; wired into the test docs.*

## Milestone 2 — Semantic model consolidation + literal grounding
*Fixes: M8, B2 (root), m9. References: [CA] semantic model + database literals.*

- [ ] **T2.1** Move ALL vocabulary (metric aliases, grouping aliases, nationality demonyms,
  competition names, position lists, dimension→SQL expressions, summary labels) into
  `registry.py` (or a `semantic_model.yaml`) so adding a dimension touches one file.
  *Accept: grep shows `intent.py`/`sql.py`/`service.py` contain no hardcoded vocab tables.*
- [ ] **T2.2** Entity index loaded from DB at startup (athletes ✅ done in T0.8; extend to distinct
  nationalities/teams/competitions) — filter values are validated against real stored values before
  compiling; unknown values ⇒ clarification, not empty result. *Accept: filter on a value absent
  from the DB returns a clarification listing close matches.*
- [ ] **T2.3** Use `approved_queries.json` as verified-query examples surfaced in `/query` responses
  and (at M3) as few-shot examples [CA]. *Accept: corpus is referenced by the pipeline, or deleted.*

## Milestone 3 — Real language understanding behind the compiler
*Fixes: B4-class paraphrase brittleness, M7. References: [CA], [QG], [PIC].*
*Requires: `ANTHROPIC_API_KEY` (owner decision on cost/model).*

- [ ] **T3.1** `IntentExtractor` seam: LLM-based extractor that outputs `StructuredIntent` as
  constrained JSON (schema-validated, retry on mismatch), prompted with the semantic model,
  entity-index literals, and verified queries. Deterministic grammar remains as offline fallback.
  *Accept: eval-set accuracy ≥ grammar baseline on all questions, and passes a new paraphrase
  section ("How far did Mbappé run in the final?") the grammar cannot.*
- [ ] **T3.2** Rejection gate [CA]: unknown entities, contradictory filters, or low-confidence
  extraction ⇒ refuse with suggested answerable questions (surface `needs_clarification` properly).
  *Accept: nonsense/out-of-scope queries never reach SQL execution.*
- [ ] **T3.3** Retrieval refit: hybrid search feeds the extractor's context (schema notes, business
  rules, verified queries); delete the summary-decoration path; drop torch/FAISS if BM25-only
  suffices at this corpus size. *Accept: `requirements-deploy.txt` = `requirements.txt` or the
  difference is justified in one sentence.*

## Milestone 4 — Engine-side validation & robustness
*Fixes: M4, M5, M10, m6. References: [CA] error-correction via SQL compiler.*

- [x] **T4.1** `EXPLAIN`-based SQL validation: compiled SQL is explained against the live DB before
  execution when available; failures surface as validation messages. *(Shipped early with M0.)*
- [ ] **T4.2** Connection pool (`psycopg_pool`), statement timeout, FastAPI lifespan handler
  (replaces deprecated `on_event`), readiness vs liveness split in `/health`.
- [ ] **T4.3** Unify `debug_sql` with the graph's plan-defaulting logic (single code path).

## Milestone 5 — Date type migration
*Fixes: M6, m4. Requires: running Postgres; coordinated ETL rerun.*

- [ ] **T5.1** Migration: `session_date`/`wellness.date`/competition dates → native `DATE`;
  update ETLs to write dates; update `sql.py` to drop `TO_DATE` (single `DATE_EXPRESSION` seam,
  already isolated); add date indexes. *Accept: full ETL + eval `--execute` green on migrated DB;
  `EXPLAIN` shows index scans on date-filtered queries.*

## Milestone 6 — Honesty pass: frontend + docs
*Fixes: m2, m5, m7, m8; doc-drift items from Phase 1(c).*

- [x] **T6.1** Frontend: dataset-appropriate sample queries, clarification UI, chart respects
  `chart_type`, local-only FastAPI docs link. *Accept: `npm run typecheck` green.*
- [x] **T6.2** Delete dead portfolio code (`app/knowledge.py`, stale config defaults).
- [x] **T6.3** Rewrite `python-backend/README.md` (6 tables, actual pipeline); fix naming
  inconsistencies (Big Data Bowl 2021); CLAUDE.md corrected to describe the system that exists.
- [x] **T6.4** Root README: remove phantom `demo-engine.ts` references, sync claims with reality.

---

## First task and why

**T1.2 — the golden eval harness — is the first task of any session continuing this plan** (it was
built alongside M0 here for exactly this reason): every other change in this plan is a claim about
answer quality, and without a scored question set those claims are unverifiable. Both references
converge on this — Snowflake treats benchmark accuracy as the product and Uber gates releases on
their evaluation harness. It is also the cheapest task with the highest leverage: it turns every
Phase 2 bug into a permanent regression guard before anything else moves.

## Status legend

- [x] = implemented in the 2026-07-13 rebuild commit (M0, M1, T4.1, most of M6)
- [ ] = open; M3 blocked on `ANTHROPIC_API_KEY` decision, M5 blocked on a running Postgres
