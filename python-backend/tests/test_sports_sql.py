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


def test_explicit_position_grouping_wins_over_ranking() -> None:
    intent = extract_intent("Which NFL position averages the highest speed?")
    plan = build_query_plan(intent)

    assert intent.grouping == "position"
    assert intent.ranking == "top"
    assert plan.dimensions == ["position"]

    compiled = compile_sql(plan)
    assert "GROUP BY a.position" in compiled.sql
    assert "athlete_name" not in compiled.sql
    assert validate_sql(plan, compiled).valid is True


def test_explicit_nationality_grouping_wins_over_ranking() -> None:
    intent = extract_intent("Which nationality scored the most shots?")
    plan = build_query_plan(intent)

    assert intent.grouping == "nationality"
    assert intent.ranking == "top"
    assert plan.dimensions == ["nationality"]

    compiled = compile_sql(plan)
    assert "GROUP BY a.nationality" in compiled.sql
    assert "athlete_name" not in compiled.sql


def test_aggregate_sql_excludes_null_metric_rows() -> None:
    intent = extract_intent("Top players by max speed")
    plan = build_query_plan(intent)

    assert intent.metric == "max_speed"

    compiled = compile_sql(plan)
    assert "g.max_speed IS NOT NULL" in compiled.sql
    assert validate_sql(plan, compiled).valid is True


def test_top_n_limit_is_used_in_plan_and_sql() -> None:
    intent = extract_intent("Top 5 pressers in the World Cup")
    plan = build_query_plan(intent)

    assert intent.requested_limit == 5
    assert plan.limit == 5

    compiled = compile_sql(plan)
    assert "LIMIT %s" in compiled.sql
    assert compiled.params[-1] == 5


def test_requested_limit_is_capped_at_50() -> None:
    intent = extract_intent("Top 99 players by total distance")
    plan = build_query_plan(intent)

    assert intent.requested_limit == 99
    assert plan.limit == 50


# ── Audit regression tests (PLAN.md M0) ─────────────────────────────────────


def test_multi_sport_comparison_compiles_grouped_sql() -> None:
    intent = extract_intent("Compare total distance between soccer and american football")
    plan = build_query_plan(intent)
    compiled = compile_sql(plan)

    assert "GROUP BY a.sport" in compiled.sql
    assert "a.sport = %s" not in compiled.sql
    assert validate_sql(plan, compiled).valid is True


def test_in_filter_compiles_to_any_clause() -> None:
    intent = extract_intent("Total distance for forwards and midfielders")
    plan = build_query_plan(intent)
    compiled = compile_sql(plan)

    assert "a.position = ANY(%s)" in compiled.sql
    assert ["forward", "midfielder"] in compiled.params


def test_wellness_metric_with_competition_filter_is_rejected_before_sql() -> None:
    """'Average fatigue score in the World Cup' must not compile crashing SQL (audit B3)."""
    intent = extract_intent("Average fatigue score in the World Cup")
    plan = build_query_plan(intent)
    validation = validate_query_plan(plan)

    assert validation.valid is False
    assert any("wellness" in message for message in validation.messages)


def test_athlete_name_filter_compiles_to_name_ilike() -> None:
    intent = extract_intent(
        "How many passes did Messi make?",
        athlete_names=["Lionel Andrés Messi Cuccittini"],
    )
    plan = build_query_plan(intent)
    compiled = compile_sql(plan)

    assert "a.name ILIKE %s" in compiled.sql
    assert "Lionel Andrés Messi Cuccittini" in compiled.params
