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


def test_parses_top_n_requested_limit() -> None:
    intent = extract_intent("Top 5 pressers in the World Cup")

    assert intent.metric == "pressures"
    assert intent.ranking == "top"
    assert intent.requested_limit == 5


def test_parses_bottom_n_requested_limit() -> None:
    intent = extract_intent("Bottom 3 athletes by sleep score")

    assert intent.metric == "sleep_score"
    assert intent.ranking == "bottom"
    assert intent.requested_limit == 3


def test_requested_limit_defaults_to_none_without_number() -> None:
    intent = extract_intent("Top players by max speed")

    assert intent.metric == "max_speed"
    assert intent.ranking == "top"
    assert intent.requested_limit is None


def test_nationality_demonym_maps_to_canonical_country() -> None:
    intent = extract_intent("Total distance covered by Argentine players")

    nationality_filters = [f for f in intent.filters if f.field == "nationality"]
    assert len(nationality_filters) == 1
    assert nationality_filters[0].value == "Argentina"


def test_nfl_keyword_adds_sport_scope_filter() -> None:
    intent = extract_intent("Top 5 NFL wide receivers by sprint distance")

    sport_filters = [f for f in intent.filters if f.field == "sport"]
    assert len(sport_filters) == 1
    assert sport_filters[0].value == "american_football"
    assert intent.requested_limit == 5
    position_filters = [f for f in intent.filters if f.field == "position"]
    assert position_filters and position_filters[0].value == "wide_receiver"


def test_plain_aggregate_query_gets_no_default_time_window() -> None:
    intent = extract_intent("Average passes per position in soccer")

    assert intent.metric == "passes"
    assert intent.grouping == "position"
    assert intent.time_window is None
    sport_filters = [f for f in intent.filters if f.field == "sport"]
    assert sport_filters and sport_filters[0].value == "soccer"
