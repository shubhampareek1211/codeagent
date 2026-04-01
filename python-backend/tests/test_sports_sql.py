from app.sports_analytics.intent import extract_intent
from app.sports_analytics.planner import build_query_plan, validate_query_plan
from app.sports_analytics.sql import compile_sql, validate_sql


def test_compile_grouped_query_sql() -> None:
    intent = extract_intent("Show average sprint distance by position over the last 30 days")
    plan = build_query_plan(intent)

    assert validate_query_plan(plan).valid is True

    compiled = compile_sql(plan)
    assert "GROUP BY a.position" in compiled.sql
    assert "AVG(g.sprint_distance)" in compiled.sql
    assert "TO_DATE(s.session_date, 'MM/DD/YYYY')" in compiled.sql
    assert validate_sql(plan, compiled).valid is True


def test_compile_baseline_query_sql() -> None:
    intent = extract_intent("Who is trending below their baseline performance?")
    plan = build_query_plan(intent)
    compiled = compile_sql(plan)

    assert plan.query_kind == "baseline_gap"
    assert "baseline_gap_pct" in compiled.sql
    assert "AVG(total_distance) AS baseline_distance" in compiled.sql
    assert "WHERE session_date < %s" in compiled.sql
    assert validate_sql(plan, compiled).valid is True
