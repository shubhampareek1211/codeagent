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


# ── Audit regression tests (PLAN.md M0) ─────────────────────────────────────


def test_minutes_does_not_trigger_min_aggregation() -> None:
    """'min' must not substring-match inside 'minutes' (audit M1)."""
    intent = extract_intent("Session duration minutes by position")

    assert intent.metric == "duration_minutes"
    assert intent.aggregation == "avg"  # registry default, not "min"


def test_multi_sport_comparison_becomes_sport_grouping() -> None:
    """README-advertised query must not compile contradictory filters (audit B1)."""
    intent = extract_intent("Compare total distance between soccer and american football")

    sport_filters = [f for f in intent.filters if f.field == "sport"]
    assert sport_filters == []
    assert intent.grouping == "sport"


def test_multiple_positions_become_in_filter() -> None:
    intent = extract_intent("Total distance for forwards and midfielders")

    position_filters = [f for f in intent.filters if f.field == "position"]
    assert len(position_filters) == 1
    assert position_filters[0].operator == "in"
    assert set(position_filters[0].value) == {"forward", "midfielder"}


def test_american_football_does_not_add_us_nationality_filter() -> None:
    """'american football' is a sport, not a nationality (audit B2)."""
    intent = extract_intent("Top 5 american football players by sprint distance")

    assert [f for f in intent.filters if f.field == "nationality"] == []
    sport_filters = [f for f in intent.filters if f.field == "sport"]
    assert sport_filters and sport_filters[0].value == "american_football"


def test_us_nationality_matches_both_db_spellings() -> None:
    """NFL ETL stores 'USA', StatsBomb 'United States' — match both (audit B2)."""
    intent = extract_intent("Total distance covered by american players")

    nationality_filters = [f for f in intent.filters if f.field == "nationality"]
    assert len(nationality_filters) == 1
    assert nationality_filters[0].operator == "in"
    assert set(nationality_filters[0].value) == {"United States", "USA"}


def test_world_cup_wins_over_football_player_phrasing() -> None:
    """'football players' phrasing must not hijack World Cup queries to the NFL (audit M2)."""
    intent = extract_intent("Which world cup football players covered the most distance?")

    assert [f for f in intent.filters if f.field == "sport"] == []
    competition_filters = [f for f in intent.filters if f.field == "competition"]
    assert competition_filters and competition_filters[0].value == "World Cup"


def test_multiple_nationalities_become_in_filter() -> None:
    """Multi-country comparisons must not silently drop countries (audit M3)."""
    intent = extract_intent("Compare total distance between France and Argentina")

    nationality_filters = [f for f in intent.filters if f.field == "nationality"]
    assert len(nationality_filters) == 1
    assert nationality_filters[0].operator == "in"
    assert set(nationality_filters[0].value) == {"France", "Argentina"}


def test_athlete_name_filter_from_entity_index() -> None:
    """Player questions must filter to the player (audit B4)."""
    names = ["Lionel Andrés Messi Cuccittini", "Kylian Mbappé Lottin"]
    intent = extract_intent("How many passes did Messi make?", athlete_names=names)

    assert intent.metric == "passes"
    athlete_filters = [f for f in intent.filters if f.field == "athlete_name"]
    assert len(athlete_filters) == 1
    assert athlete_filters[0].value == "Lionel Andrés Messi Cuccittini"


def test_relative_window_anchors_to_provided_today() -> None:
    """Windows anchor to the dataset date, not the wall clock (audit B5)."""
    from datetime import date

    intent = extract_intent("Highest workload last week", today=date(2022, 12, 18))

    assert intent.time_window is not None
    assert str(intent.time_window.end_date) == "2022-12-18"
    assert str(intent.time_window.start_date) == "2022-12-12"


def test_top_does_not_match_inside_other_words() -> None:
    intent = extract_intent("Did anyone stop sprinting in matches?")

    assert intent.ranking == "none"
