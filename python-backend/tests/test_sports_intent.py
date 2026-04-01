from app.sports_analytics.intent import extract_intent


def test_extracts_ranked_workload_query() -> None:
    intent = extract_intent("Which athletes had the highest workload last week?")

    assert intent.metric == "workload"
    assert intent.ranking == "top"
    assert intent.time_window is not None
    assert intent.time_window.lookback_days == 7
    assert intent.output_type == "ranked_list"


def test_extracts_grouped_sprint_distance_query() -> None:
    intent = extract_intent("Show average sprint distance by position over the last 30 days")

    assert intent.metric == "sprint_distance"
    assert intent.grouping == "position"
    assert intent.aggregation == "avg"
    assert intent.time_window is not None
    assert intent.time_window.lookback_days == 30
    assert intent.chart_eligible is True


def test_extracts_explicit_date_range_query() -> None:
    intent = extract_intent("Which athletes had the highest workload from 1/1/2026 to 1/5/2026?")

    assert intent.metric == "workload"
    assert intent.ranking == "top"
    assert intent.time_window is not None
    assert str(intent.time_window.start_date) == "2026-01-01"
    assert str(intent.time_window.end_date) == "2026-01-05"
    assert intent.time_window.lookback_days == 5


def test_maps_baseline_business_term_to_supported_metric() -> None:
    intent = extract_intent("Who is trending below their baseline performance?")

    assert intent.metric == "workload"
    assert intent.comparison_type == "baseline"
    assert intent.grouping is None
    assert intent.output_type == "ranked_list"
    assert "business_term" in intent.ambiguity_flags
    assert "workload proxy" in intent.interpretation_notes[0].lower()
