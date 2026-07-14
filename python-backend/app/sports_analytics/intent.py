from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Sequence

from app.sports_analytics.models import QueryFilter, StructuredIntent, TimeWindow
from app.sports_analytics.registry import (
    BUSINESS_TERM_ALIASES,
    GROUPING_ALIASES,
    METRIC_REGISTRY,
    SUPPORTED_POSITIONS,
    SUPPORTED_SPORTS,
    SUPPORTED_TEAMS,
)

# Known nationalities / country names + demonyms that appear in the dataset.
# Tuple: (query_keyword, canonical_db_value)
KNOWN_NATIONALITIES: tuple[tuple[str, str], ...] = (
    ("argentina", "Argentina"), ("argentine", "Argentina"), ("argentinian", "Argentina"),
    ("france", "France"), ("french", "France"),
    ("england", "England"), ("english", "England"),
    ("brazil", "Brazil"), ("brazilian", "Brazil"),
    ("portugal", "Portugal"), ("portuguese", "Portugal"),
    ("spain", "Spain"), ("spanish", "Spain"),
    ("germany", "Germany"), ("german", "Germany"),
    ("netherlands", "Netherlands"), ("dutch", "Netherlands"),
    ("morocco", "Morocco"), ("moroccan", "Morocco"),
    ("croatia", "Croatia"), ("croatian", "Croatia"),
    ("united states", "United States"), ("usa", "United States"), ("american", "United States"),
    ("senegal", "Senegal"), ("senegalese", "Senegal"),
    ("japan", "Japan"), ("japanese", "Japan"),
    ("south korea", "South Korea"), ("korean", "South Korea"),
    ("australia", "Australia"), ("australian", "Australia"),
    ("switzerland", "Switzerland"), ("swiss", "Switzerland"),
    ("belgium", "Belgium"), ("belgian", "Belgium"),
    ("denmark", "Denmark"), ("danish", "Denmark"),
    ("poland", "Poland"), ("polish", "Poland"),
    ("mexico", "Mexico"), ("mexican", "Mexico"),
    ("ghana", "Ghana"), ("ghanaian", "Ghana"),
    ("cameroon", "Cameroon"), ("cameroonian", "Cameroon"),
    ("ecuador", "Ecuador"), ("ecuadorian", "Ecuador"),
    ("iran", "Iran"), ("iranian", "Iran"),
    ("canada", "Canada"), ("canadian", "Canada"),
    ("wales", "Wales"), ("welsh", "Wales"),
    ("qatar", "Qatar"), ("qatari", "Qatar"),
    ("saudi arabia", "Saudi Arabia"), ("saudi", "Saudi Arabia"),
    ("uruguay", "Uruguay"), ("uruguayan", "Uruguay"),
    ("serbia", "Serbia"), ("serbian", "Serbia"),
    ("costa rica", "Costa Rica"), ("costa rican", "Costa Rica"),
    ("tunisia", "Tunisia"), ("tunisian", "Tunisia"),
)

# The NFL ETL writes nationality='USA'; StatsBomb writes 'United States'.
# Until literal grounding (PLAN.md T2.2) unifies values, match both.
NATIONALITY_DB_VALUES: dict[str, list[str]] = {
    "United States": ["United States", "USA"],
}


@lru_cache(maxsize=1024)
def _term_pattern(term: str) -> re.Pattern[str]:
    """Word-boundary pattern for a keyword/alias, tolerating a plural 's'.

    Prevents the substring-matching bugs where 'min' matched inside 'minutes',
    'top' inside 'stop', or 'date' inside unrelated words, while still letting
    'wide receiver' match 'wide receivers'.
    """
    return re.compile(rf"\b{re.escape(term)}s?\b")


def _has_term(normalized_query: str, term: str) -> bool:
    return _term_pattern(term).search(normalized_query) is not None


def _has_any_term(normalized_query: str, terms: Sequence[str]) -> bool:
    return any(_has_term(normalized_query, term) for term in terms)


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip().lower())


def extract_intent(
    query: str,
    today: date | None = None,
    athlete_names: Sequence[str] | None = None,
) -> StructuredIntent:
    """Extract a StructuredIntent from a natural-language query.

    `today` anchors relative time windows ("last week"); the service passes the
    dataset's max session date so historical datasets stay reachable.
    `athlete_names` is the DB-grounded entity index used for player filters.
    """
    current_day = today or date.today()
    normalized = normalize_query(query)
    metric_matches = _match_metrics(normalized)
    primary_metric = metric_matches[0] if metric_matches else None
    grouping = _match_grouping(normalized)
    time_window = _parse_time_window(normalized, current_day)
    comparison_type = _match_comparison_type(normalized)
    ranking = _match_ranking(normalized)
    requested_limit = _match_requested_limit(normalized)
    aggregation = _match_aggregation(normalized, primary_metric, grouping, comparison_type)
    filters, filter_notes = _match_filters(normalized, athlete_names)
    ambiguity_flags: list[str] = []
    interpretation_notes: list[str] = list(filter_notes)

    if comparison_type == "baseline" and primary_metric is None:
        primary_metric = "workload"
        metric_matches = ["workload"]
        interpretation_notes.append(
            "Mapped baseline performance to the workload proxy because the schema does not include a dedicated workload column."
        )
        ambiguity_flags.append("business_term")

    if primary_metric is None:
        ambiguity_flags.append("metric_unspecified")

    if len(metric_matches) > 1:
        ambiguity_flags.append("multiple_metrics_detected")
        interpretation_notes.append(
            f"Primary metric set to {metric_matches[0]} while retaining {len(metric_matches)} matched metrics."
        )

    if grouping is None and comparison_type == "trend":
        grouping = "session_date"
        interpretation_notes.append("Interpreted the request as a trend and grouped results by session date.")

    if comparison_type == "baseline" and grouping == "session_date":
        grouping = None
        interpretation_notes.append(
            "Ignored trend-style date grouping because baseline questions are answered as athlete comparisons."
        )

    # ── multi-sport queries are comparisons across sports, not contradictions ──
    sport_filters = [f for f in filters if f.field == "sport"]
    if len(sport_filters) > 1:
        filters = [f for f in filters if f.field != "sport"]
        if grouping is None:
            grouping = "sport"
        interpretation_notes.append(
            "Multiple sports mentioned — comparing across sports instead of filtering to an impossible intersection."
        )

    # ── sport / competition scope filters (needs grouping to be resolved first) ──
    has_sport_filter = any(f.field == "sport" for f in filters)
    if not has_sport_filter and grouping != "sport":
        # Precedence: explicit NFL naming, then explicit World Cup naming, then
        # the sport names themselves. The old bare "football player" heuristic is
        # gone — "football player" is soccer phrasing in most of the world.
        if _has_any_term(normalized, ("nfl", "big data bowl")):
            filters.append(QueryFilter(field="sport", operator="=", value="american_football"))
        elif _has_any_term(normalized, ("world cup", "fifa")):
            filters.append(QueryFilter(field="competition", operator="ILIKE", value="World Cup"))
        elif _has_term(normalized, "american football"):
            filters.append(QueryFilter(field="sport", operator="=", value="american_football"))
        elif _has_term(normalized, "soccer"):
            filters.append(QueryFilter(field="sport", operator="=", value="soccer"))

    if time_window is None:
        # For baseline / trend queries, apply a default window so the comparison is meaningful.
        # For plain aggregation queries with no explicit time context, skip the window so
        # historical datasets (World Cup 2022, NFL 2021) are not excluded by a rolling default.
        has_competition_filter = any(f.field == "competition" for f in filters)
        needs_default_window = comparison_type in ("baseline", "trend") and not has_competition_filter
        if needs_default_window:
            default_days = 7 if comparison_type == "baseline" else 30
            time_window = TimeWindow(
                label=f"last {default_days} days",
                start_date=current_day - timedelta(days=default_days - 1),
                end_date=current_day,
                lookback_days=default_days,
            )
            interpretation_notes.append(
                f"Applied the default {default_days}-day window anchored to the latest data date ({current_day.isoformat()})."
            )
        else:
            # No time constraint — query will return all available data.
            interpretation_notes.append("No time window applied — returning all available data.")

    output_type = _infer_output_type(grouping, ranking, comparison_type)
    chart_requested = _has_any_term(normalized, ("chart", "plot", "graph", "visualize"))
    chart_eligible = grouping is not None or ranking != "none" or comparison_type in {"trend", "baseline"}
    confidence = _score_confidence(
        primary_metric=primary_metric,
        grouping=grouping,
        ambiguity_flags=ambiguity_flags,
        comparison_type=comparison_type,
    )

    if _has_term(normalized, "performance") and primary_metric is None:
        ambiguity_flags.append("performance_term_unspecified")
        interpretation_notes.append(
            "The query uses the term performance without naming a direct metric."
        )

    return StructuredIntent(
        raw_query=query,
        normalized_query=normalized,
        metric=primary_metric,
        metrics=metric_matches,
        entity="athlete",
        grouping=grouping,
        aggregation=aggregation,
        filters=filters,
        time_window=time_window,
        comparison_type=comparison_type,
        ranking=ranking,
        requested_limit=requested_limit,
        output_type=output_type,
        chart_requested=chart_requested,
        chart_eligible=chart_eligible,
        confidence=confidence,
        ambiguity_flags=sorted(set(ambiguity_flags)),
        interpretation_notes=interpretation_notes,
    )


def _match_metrics(normalized_query: str) -> list[str]:
    # Rank matches by the longest alias that hit so the most specific metric wins
    # (e.g. "sprint distance" beats total_distance's generic "distance" alias and
    # "max speed" beats avg_speed's generic "speed" alias). Ties keep registry order.
    scored: list[tuple[int, str]] = []
    for metric_key, meta in METRIC_REGISTRY.items():
        matched_lengths = [len(alias) for alias in meta.aliases if _has_term(normalized_query, alias)]
        if matched_lengths:
            scored.append((max(matched_lengths), metric_key))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [metric_key for _, metric_key in scored]


def _match_grouping(normalized_query: str) -> str | None:
    for grouping, aliases in GROUPING_ALIASES.items():
        if _has_any_term(normalized_query, aliases):
            return grouping
    return None


def _match_comparison_type(normalized_query: str) -> str:
    if _has_any_term(normalized_query, BUSINESS_TERM_ALIASES["baseline"]) or _has_term(normalized_query, "underperform"):
        return "baseline"
    if _has_any_term(normalized_query, ("trend", "trending", "over time")):
        return "trend"
    return "none"


def _match_requested_limit(normalized_query: str) -> int | None:
    match = re.search(r"\b(?:top|bottom|first)\s+(\d{1,2})\b", normalized_query)
    if match:
        return int(match.group(1))
    return None


def _match_ranking(normalized_query: str) -> str:
    if _has_any_term(normalized_query, ("highest", "top", "most", "best")):
        return "top"
    if _has_any_term(normalized_query, ("lowest", "bottom", "least", "worst", "below")):
        return "bottom"
    return "none"


def _match_aggregation(
    normalized_query: str,
    primary_metric: str | None,
    grouping: str | None,
    comparison_type: str,
) -> str | None:
    if _has_any_term(normalized_query, ("average", "avg", "mean")):
        return "avg"
    if _has_any_term(normalized_query, ("maximum", "max", "fastest")):
        return "max"
    if _has_any_term(normalized_query, ("minimum", "min")):
        return "min"
    if comparison_type == "baseline":
        return "avg"
    if primary_metric is None:
        return None
    return METRIC_REGISTRY[primary_metric].default_aggregation


def _match_filters(
    normalized_query: str,
    athlete_names: Sequence[str] | None = None,
) -> tuple[list[QueryFilter], list[str]]:
    filters: list[QueryFilter] = []
    notes: list[str] = []

    # Position filters — multiple positions become one IN filter, never
    # contradictory ANDed equality clauses.
    matched_positions: list[str] = []
    for position in SUPPORTED_POSITIONS:
        display = position.replace("_", " ")
        if _has_term(normalized_query, display) or _has_term(normalized_query, position):
            matched_positions.append(position)
    if len(matched_positions) == 1:
        filters.append(QueryFilter(field="position", operator="=", value=matched_positions[0]))
    elif matched_positions:
        filters.append(QueryFilter(field="position", operator="in", value=matched_positions))
        notes.append(f"Matching any of the positions: {', '.join(matched_positions)}.")

    # Team filters
    for team in SUPPORTED_TEAMS:
        if _has_term(normalized_query, team.lower()):
            filters.append(QueryFilter(field="team", operator="=", value=team))

    # Sport filters — collected individually; extract_intent converts multi-sport
    # matches into a sport grouping (comparison) instead of an empty intersection.
    for sport in SUPPORTED_SPORTS:
        sport_display = sport.replace("_", " ")
        if _has_term(normalized_query, sport_display) or _has_term(normalized_query, sport):
            filters.append(QueryFilter(field="sport", operator="=", value=sport))

    # Nationality filters. Mask "american football" first so the sport phrase
    # never misfires into nationality='United States'.
    nationality_scope = _term_pattern("american football").sub(" ", normalized_query)
    matched_nat: list[str] = []
    for keyword, canonical in sorted(KNOWN_NATIONALITIES, key=lambda t: len(t[0]), reverse=True):
        if canonical not in matched_nat and _has_term(nationality_scope, keyword):
            matched_nat.append(canonical)
    if matched_nat:
        db_values: list[str] = []
        for canonical in matched_nat:
            db_values.extend(NATIONALITY_DB_VALUES.get(canonical, [canonical]))
        if len(db_values) == 1:
            filters.append(QueryFilter(field="nationality", operator="=", value=db_values[0]))
        else:
            filters.append(QueryFilter(field="nationality", operator="in", value=db_values))
        if len(matched_nat) > 1:
            notes.append(f"Matching any of the nationalities: {', '.join(matched_nat)}.")

    # Athlete-name filters, grounded against the DB entity index (PLAN.md T0.8).
    if athlete_names:
        matched_athletes = _match_athlete_names(normalized_query, athlete_names)
        if len(matched_athletes) == 1:
            filters.append(QueryFilter(field="athlete_name", operator="ILIKE", value=matched_athletes[0]))
            notes.append(f"Filtered to athlete '{matched_athletes[0]}'.")
        elif matched_athletes:
            filters.append(QueryFilter(field="athlete_name", operator="in", value=matched_athletes))
            notes.append(f"Matching any of the athletes: {', '.join(matched_athletes)}.")

    return filters, notes


def _strip_accents(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def _match_athlete_names(normalized_query: str, athlete_names: Sequence[str]) -> list[str]:
    """Match known athlete names in the query, accent-insensitively.

    Full-name matches win; otherwise any name token that is ≥4 chars and unique
    across the roster matches (so "Messi" resolves although the registered name
    is "Lionel Andrés Messi Cuccittini").
    """
    folded_query = _strip_accents(normalized_query)
    query_tokens = set(re.findall(r"[a-z0-9']+", folded_query))

    matched: list[str] = []
    for name in athlete_names:
        if _strip_accents(name.lower()) in folded_query:
            matched.append(name)
    if matched:
        return matched

    token_index: dict[str, list[str]] = {}
    for name in athlete_names:
        for token in set(re.findall(r"[a-z0-9']+", _strip_accents(name.lower()))):
            if len(token) >= 4:
                token_index.setdefault(token, []).append(name)

    for token, names in token_index.items():
        if len(names) == 1 and token in query_tokens and names[0] not in matched:
            matched.append(names[0])

    return matched


def _parse_time_window(normalized_query: str, current_day: date) -> TimeWindow | None:
    explicit_range = _parse_explicit_date_range(normalized_query)
    if explicit_range is not None:
        return explicit_range

    match = re.search(r"last (\d+) days?", normalized_query)
    if match:
        lookback_days = int(match.group(1))
        return TimeWindow(
            label=f"last {lookback_days} days",
            start_date=current_day - timedelta(days=lookback_days - 1),
            end_date=current_day,
            lookback_days=lookback_days,
        )

    if "last week" in normalized_query:
        return TimeWindow(
            label="last week",
            start_date=current_day - timedelta(days=6),
            end_date=current_day,
            lookback_days=7,
        )

    if "last month" in normalized_query:
        return TimeWindow(
            label="last month",
            start_date=current_day - timedelta(days=29),
            end_date=current_day,
            lookback_days=30,
        )

    if "yesterday" in normalized_query:
        return TimeWindow(label="yesterday", start_date=current_day - timedelta(days=1), end_date=current_day - timedelta(days=1), lookback_days=1)

    if "today" in normalized_query:
        return TimeWindow(label="today", start_date=current_day, end_date=current_day, lookback_days=1)

    return None


def _parse_explicit_date_range(normalized_query: str) -> TimeWindow | None:
    match = re.search(
        r"(?:from|between)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(?:to|and|through)\s+(\d{1,2}/\d{1,2}/\d{4})",
        normalized_query,
    )
    if match is None:
        return None

    start_date = _parse_mmddyyyy(match.group(1))
    end_date = _parse_mmddyyyy(match.group(2))
    if start_date is None or end_date is None:
        return None
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    return TimeWindow(
        label=f"{start_date.month}/{start_date.day}/{start_date.year} to {end_date.month}/{end_date.day}/{end_date.year}",
        start_date=start_date,
        end_date=end_date,
        lookback_days=(end_date - start_date).days + 1,
    )


def _parse_mmddyyyy(raw_value: str) -> date | None:
    try:
        return datetime.strptime(raw_value, "%m/%d/%Y").date()
    except ValueError:
        return None


def _infer_output_type(grouping: str | None, ranking: str, comparison_type: str) -> str:
    if comparison_type == "trend" or grouping == "session_date":
        return "trend"
    if comparison_type == "baseline" or ranking != "none":
        return "ranked_list"
    if grouping is not None:
        return "grouped_output"
    return "kpi"


def _score_confidence(
    primary_metric: str | None,
    grouping: str | None,
    ambiguity_flags: list[str],
    comparison_type: str,
) -> float:
    confidence = 0.35
    if primary_metric:
        confidence += 0.28
    if grouping:
        confidence += 0.1
    if comparison_type != "none":
        confidence += 0.1
    confidence -= 0.08 * len(set(ambiguity_flags))
    return max(0.05, min(round(confidence, 2), 0.98))
