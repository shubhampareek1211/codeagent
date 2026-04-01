from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from app.sports_analytics.models import QueryFilter, StructuredIntent, TimeWindow
from app.sports_analytics.registry import (
    BUSINESS_TERM_ALIASES,
    GROUPING_ALIASES,
    METRIC_REGISTRY,
    SUPPORTED_POSITIONS,
    SUPPORTED_TEAMS,
)


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip().lower())


def extract_intent(query: str, today: date | None = None) -> StructuredIntent:
    current_day = today or date.today()
    normalized = normalize_query(query)
    metric_matches = _match_metrics(normalized)
    primary_metric = metric_matches[0] if metric_matches else None
    grouping = _match_grouping(normalized)
    time_window = _parse_time_window(normalized, current_day)
    comparison_type = _match_comparison_type(normalized)
    ranking = _match_ranking(normalized)
    aggregation = _match_aggregation(normalized, primary_metric, grouping, comparison_type)
    filters = _match_filters(normalized)
    ambiguity_flags: list[str] = []
    interpretation_notes: list[str] = []

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

    if time_window is None:
        default_days = 7 if comparison_type == "baseline" else 30
        time_window = TimeWindow(
            label=f"last {default_days} days",
            start_date=current_day - timedelta(days=default_days - 1),
            end_date=current_day,
            lookback_days=default_days,
        )
        interpretation_notes.append(f"Applied the default {default_days}-day window for this query.")

    output_type = _infer_output_type(grouping, ranking, comparison_type)
    chart_requested = any(term in normalized for term in ("chart", "plot", "graph", "visualize"))
    chart_eligible = grouping is not None or ranking != "none" or comparison_type in {"trend", "baseline"}
    confidence = _score_confidence(
        primary_metric=primary_metric,
        grouping=grouping,
        ambiguity_flags=ambiguity_flags,
        comparison_type=comparison_type,
    )

    if "performance" in normalized and primary_metric is None:
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
        output_type=output_type,
        chart_requested=chart_requested,
        chart_eligible=chart_eligible,
        confidence=confidence,
        ambiguity_flags=sorted(set(ambiguity_flags)),
        interpretation_notes=interpretation_notes,
    )


def _match_metrics(normalized_query: str) -> list[str]:
    matches: list[str] = []
    for metric_key, meta in METRIC_REGISTRY.items():
        if any(alias in normalized_query for alias in meta.aliases):
            matches.append(metric_key)
    return matches


def _match_grouping(normalized_query: str) -> str | None:
    for grouping, aliases in GROUPING_ALIASES.items():
        if any(alias in normalized_query for alias in aliases):
            return grouping
    return None


def _match_comparison_type(normalized_query: str) -> str:
    if any(alias in normalized_query for alias in BUSINESS_TERM_ALIASES["baseline"]) or "underperform" in normalized_query:
        return "baseline"
    if "trend" in normalized_query or "trending" in normalized_query or "over time" in normalized_query:
        return "trend"
    return "none"


def _match_ranking(normalized_query: str) -> str:
    if any(term in normalized_query for term in ("highest", "top", "most", "best")):
        return "top"
    if any(term in normalized_query for term in ("lowest", "bottom", "least", "worst", "below")):
        return "bottom"
    return "none"


def _match_aggregation(
    normalized_query: str,
    primary_metric: str | None,
    grouping: str | None,
    comparison_type: str,
) -> str | None:
    if "average" in normalized_query or "avg" in normalized_query or "mean" in normalized_query:
        return "avg"
    if "maximum" in normalized_query or "max" in normalized_query or "fastest" in normalized_query:
        return "max"
    if "minimum" in normalized_query or "min" in normalized_query:
        return "min"
    if comparison_type == "baseline":
        return "avg"
    if primary_metric is None:
        return None
    if grouping == "session_date":
        return METRIC_REGISTRY[primary_metric].default_aggregation
    return METRIC_REGISTRY[primary_metric].default_aggregation


def _match_filters(normalized_query: str) -> list[QueryFilter]:
    filters: list[QueryFilter] = []
    for position in SUPPORTED_POSITIONS:
        if position in normalized_query:
            filters.append(QueryFilter(field="position", operator="=", value=position.title()))
    for team in SUPPORTED_TEAMS:
        if team in normalized_query:
            filters.append(QueryFilter(field="team", operator="=", value=team.title()))
    return filters


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
