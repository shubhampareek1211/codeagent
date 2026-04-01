from __future__ import annotations

from app.sports_analytics.models import JoinSpec, QueryPlan, SortSpec, StructuredIntent, ValidationOutcome
from app.sports_analytics.registry import GROUPING_ALIASES, METRIC_REGISTRY


def build_query_plan(intent: StructuredIntent) -> QueryPlan:
    if intent.metric is None:
        raise ValueError("A supported metric is required before a query plan can be built.")

    metric = METRIC_REGISTRY[intent.metric]
    source_tables, joins = _source_tables_for_metric(metric.table)
    dimensions = _dimensions_for_intent(intent)
    notes = list(intent.interpretation_notes)

    if intent.metric == "workload":
        notes.append(
            "Workload is compiled as a proxy view: total distance is the ranking metric and sprint distance, "
            "high intensity efforts, and duration are returned as supporting components."
        )

    if intent.comparison_type == "baseline":
        order_by = [SortSpec(field="baseline_gap_pct", direction="asc")]
        notes.append("Baseline compares the recent window against the athlete's historical average before that window.")
        return QueryPlan(
            query_kind="baseline_gap",
            metric=intent.metric,
            metric_table=metric.table,
            source_tables=source_tables,
            joins=joins,
            dimensions=["athlete_id", "athlete_name", "position"],
            aggregations={"recent_average": "avg", "baseline_average": "avg", "baseline_gap_pct": "derived"},
            filters=intent.filters,
            time_window=intent.time_window,
            order_by=order_by,
            limit=10,
            output_type=intent.output_type,
            comparison_type=intent.comparison_type,
            notes=notes,
        )

    query_kind = "timeseries" if intent.grouping == "session_date" else "aggregate"
    order_direction = "asc" if query_kind == "timeseries" else ("asc" if intent.ranking == "bottom" else "desc")
    limit = intent.time_window.lookback_days if query_kind == "timeseries" and intent.time_window else 10

    return QueryPlan(
        query_kind=query_kind,
        metric=intent.metric,
        metric_table=metric.table,
        source_tables=source_tables,
        joins=joins,
        dimensions=dimensions,
        aggregations={"metric_value": intent.aggregation or metric.default_aggregation},
        filters=intent.filters,
        time_window=intent.time_window,
        order_by=[SortSpec(field="metric_value" if query_kind != "timeseries" else "session_date", direction=order_direction)],
        limit=limit,
        output_type=intent.output_type,
        comparison_type=intent.comparison_type,
        notes=notes,
    )


def validate_query_plan(plan: QueryPlan) -> ValidationOutcome:
    messages: list[str] = []
    if plan.metric not in METRIC_REGISTRY:
        messages.append(f"Unsupported metric: {plan.metric}")
    if plan.query_kind not in {"aggregate", "timeseries", "baseline_gap"}:
        messages.append(f"Unsupported query kind: {plan.query_kind}")
    if plan.metric_table not in {"gps_metrics", "wellness", "sessions"}:
        messages.append(f"Unsupported metric table: {plan.metric_table}")

    supported_groupings = set(GROUPING_ALIASES.keys()) | {"athlete_id", "athlete_name", "position", "team"}
    for dimension in plan.dimensions:
        if dimension not in supported_groupings:
            messages.append(f"Unsupported dimension: {dimension}")
        if dimension == "session_type" and "sessions" not in plan.source_tables:
            messages.append("Session type grouping requires the sessions table.")

    if plan.query_kind == "baseline_gap" and not plan.time_window:
        messages.append("Baseline queries require a recent time window.")

    return ValidationOutcome(valid=not messages, messages=messages)


def _source_tables_for_metric(metric_table: str) -> tuple[list[str], list[JoinSpec]]:
    if metric_table == "gps_metrics":
        return (
            ["gps_metrics", "sessions", "athletes"],
            [
                JoinSpec(table="sessions", on="sessions.session_id = gps_metrics.session_id"),
                JoinSpec(table="athletes", on="athletes.athlete_id = sessions.athlete_id"),
            ],
        )
    if metric_table == "sessions":
        return (
            ["sessions", "athletes"],
            [JoinSpec(table="athletes", on="athletes.athlete_id = sessions.athlete_id")],
        )
    if metric_table == "wellness":
        return (
            ["wellness", "athletes"],
            [JoinSpec(table="athletes", on="athletes.athlete_id = wellness.athlete_id")],
        )
    raise ValueError(f"Unsupported metric table: {metric_table}")


def _dimensions_for_intent(intent: StructuredIntent) -> list[str]:
    if intent.grouping == "athlete_name" or intent.ranking != "none" or intent.comparison_type == "baseline":
        return ["athlete_id", "athlete_name", "position"]
    if intent.grouping:
        return [intent.grouping]
    return []
