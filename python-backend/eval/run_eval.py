#!/usr/bin/env python3
"""Golden-question eval harness (PLAN.md M1).

Runs every question in golden_questions.json through the offline pipeline
(intent → plan → SQL compile) and scores expectations. This is the regression
gate for answer quality: every audit bug lives here permanently, alongside the
README's advertised queries.

Usage (from python-backend/):
    python eval/run_eval.py               # offline: intent/plan/SQL assertions
    python eval/run_eval.py --execute     # also EXPLAIN + execute against
                                          # SPORTS_DATABASE_URL and require rows

Exits non-zero on any failure so it can gate CI.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sports_analytics.intent import extract_intent  # noqa: E402
from app.sports_analytics.planner import build_query_plan, validate_query_plan  # noqa: E402
from app.sports_analytics.sql import compile_sql, validate_sql  # noqa: E402

GOLDEN_PATH = Path(__file__).with_name("golden_questions.json")

# Deterministic offline context: dataset anchor date + a tiny entity index.
# With --execute, the real DB provides both instead.
ANCHOR_DATE = date(2022, 12, 18)
ATHLETE_INDEX = ["Lionel Andrés Messi Cuccittini", "Kylian Mbappé Lottin"]


def check_case(case: dict, anchor: date, athlete_names: list[str]) -> list[str]:
    expect = case["expect"]
    failures: list[str] = []

    intent = extract_intent(case["query"], today=anchor, athlete_names=athlete_names)

    def expect_eq(label: str, actual, wanted) -> None:
        if actual != wanted:
            failures.append(f"{label}: expected {wanted!r}, got {actual!r}")

    if "metric" in expect:
        expect_eq("metric", intent.metric, expect["metric"])
    if "grouping" in expect:
        expect_eq("grouping", intent.grouping, expect["grouping"])
    if "ranking" in expect:
        expect_eq("ranking", intent.ranking, expect["ranking"])
    if "aggregation" in expect:
        expect_eq("aggregation", intent.aggregation, expect["aggregation"])
    if "comparison_type" in expect:
        expect_eq("comparison_type", intent.comparison_type, expect["comparison_type"])
    if "requested_limit" in expect:
        expect_eq("requested_limit", intent.requested_limit, expect["requested_limit"])
    if expect.get("no_time_window"):
        expect_eq("time_window", intent.time_window, None)
    if "window_end" in expect:
        actual = str(intent.time_window.end_date) if intent.time_window else None
        expect_eq("window_end", actual, expect["window_end"])

    filter_fields = {f.field for f in intent.filters}
    for field in expect.get("filter_fields", []):
        if field not in filter_fields:
            failures.append(f"missing expected filter on '{field}' (have: {sorted(filter_fields)})")
    for field in expect.get("forbidden_filter_fields", []):
        if field in filter_fields:
            failures.append(f"forbidden filter on '{field}' present")
    if "filter_value" in expect:
        want = expect["filter_value"]
        hits = [f for f in intent.filters if f.field == want["field"]]
        if not hits:
            failures.append(f"missing filter on '{want['field']}'")
        elif not any(f.value == want["value"] or (isinstance(f.value, list) and want["value"] in f.value) for f in hits):
            failures.append(f"filter {want['field']}: expected value {want['value']!r}, got {[f.value for f in hits]!r}")
    if "filter_operator" in expect:
        want = expect["filter_operator"]
        hits = [f for f in intent.filters if f.field == want["field"]]
        if not any(f.operator == want["operator"] for f in hits):
            failures.append(f"filter {want['field']}: expected operator {want['operator']!r}, got {[f.operator for f in hits]!r}")

    if intent.metric is None:
        if "metric" in expect and expect["metric"] is None:
            return failures  # expected clarification case
        failures.append("no metric extracted; cannot plan")
        return failures

    plan = build_query_plan(intent)
    plan_validation = validate_query_plan(plan)
    if expect.get("plan_invalid"):
        if plan_validation.valid:
            failures.append("expected plan validation to reject this query, but it passed")
        return failures
    if not plan_validation.valid:
        failures.append(f"plan validation failed: {plan_validation.messages}")
        return failures

    compiled = compile_sql(plan)
    sql_validation = validate_sql(plan, compiled)
    if not sql_validation.valid:
        failures.append(f"sql validation failed: {sql_validation.messages}")

    for fragment in expect.get("sql_contains", []):
        if fragment not in compiled.sql:
            failures.append(f"SQL missing fragment: {fragment!r}")
    for fragment in expect.get("sql_not_contains", []):
        if fragment in compiled.sql:
            failures.append(f"SQL contains forbidden fragment: {fragment!r}")

    if "execute" in case:  # populated by --execute mode
        repository = case["execute"]
        engine_error = repository.explain(compiled.sql, compiled.params)
        if engine_error:
            failures.append(f"EXPLAIN failed: {engine_error}")
        else:
            rows = repository.execute_select(compiled.sql, compiled.params)
            if not rows and not expect.get("allow_empty", False):
                failures.append("query executed but returned 0 rows")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="also EXPLAIN + execute against SPORTS_DATABASE_URL")
    args = parser.parse_args()

    cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    anchor, athlete_names, repository = ANCHOR_DATE, ATHLETE_INDEX, None
    if args.execute:
        from app.sports_analytics.repository import SportsAnalyticsRepository

        database_url = os.environ.get("SPORTS_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not database_url:
            print("--execute requires SPORTS_DATABASE_URL", file=sys.stderr)
            return 2
        repository = SportsAnalyticsRepository(database_url)
        anchor = repository.get_max_session_date() or ANCHOR_DATE
        athlete_names = repository.list_athlete_names() or ATHLETE_INDEX

    passed = failed = 0
    for case in cases:
        if repository is not None:
            case["execute"] = repository
        failures = check_case(case, anchor, athlete_names)
        tag = f"[{case['expect'].get('audit_issue', '—')}]".ljust(6)
        if failures:
            failed += 1
            print(f"FAIL {tag} {case['id']}")
            for failure in failures:
                print(f"       - {failure}")
        else:
            passed += 1
            print(f"ok   {tag} {case['id']}")

    print(f"\n{passed}/{passed + failed} golden questions passed" + (" (executed against live DB)" if args.execute else " (offline)"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
