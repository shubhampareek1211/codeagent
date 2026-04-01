from __future__ import annotations

import re
from typing import Any

from app.sports_analytics.models import CompiledSql, QueryFilter, QueryPlan, ValidationOutcome
from app.sports_analytics.registry import METRIC_REGISTRY


TABLE_ALIASES = {
    "athletes": "a",
    "sessions": "s",
    "gps_metrics": "g",
    "wellness": "w",
}

DATE_FORMAT = "MM/DD/YYYY"


def compile_sql(plan: QueryPlan) -> CompiledSql:
    metric = METRIC_REGISTRY[plan.metric]
    if plan.query_kind == "baseline_gap":
        return _compile_baseline_gap(plan)
    if plan.metric == "workload":
        return _compile_workload_proxy(plan)
    return _compile_aggregate(plan, metric)


def validate_sql(plan: QueryPlan, compiled_sql: CompiledSql) -> ValidationOutcome:
    sql_upper = compiled_sql.sql.strip().upper()
    sql_lower = compiled_sql.sql.lower()
    messages: list[str] = []
    if not sql_upper.startswith("SELECT") and not sql_upper.startswith("WITH"):
        messages.append("Only SELECT/CTE queries are allowed.")

    prohibited = (" INSERT ", " UPDATE ", " DELETE ", " DROP ", " ALTER ", " TRUNCATE ", " CREATE ")
    for token in prohibited:
        if token in f" {sql_upper} ":
            messages.append(f"Prohibited SQL token detected: {token.strip().lower()}")

    referenced_tables = set(
        re.findall(r"\b(?:FROM|JOIN)\s+(?:public\.)?([a-z_]+)", compiled_sql.sql, flags=re.IGNORECASE)
    )
    allowed_references = {
        "athletes",
        "sessions",
        "gps_metrics",
        "wellness",
        "session_output",
        "metric_points",
        "baseline",
        "recent",
    }
    if not referenced_tables.issubset(allowed_references):
        messages.append("The SQL references tables outside the approved analytics schema.")

    if plan.metric == "workload":
        required_tokens = ("total_distance", "sprint_distance", "high_intensity_efforts", "duration_minutes")
        missing = [token for token in required_tokens if token not in sql_lower]
        if missing:
            messages.append("Compiled workload SQL is missing required proxy workload components.")
    else:
        metric_column = METRIC_REGISTRY[plan.metric].column.lower()
        if metric_column not in sql_lower:
            messages.append("Compiled SQL does not reference the requested metric as expected.")

    return ValidationOutcome(valid=not messages, messages=messages)


def _compile_aggregate(plan: QueryPlan, metric: Any) -> CompiledSql:
    metric_alias = TABLE_ALIASES[metric.table]
    params: list[Any] = []
    select_parts: list[str] = []
    group_by_parts: list[str] = []
    selected_fields: list[str] = []

    for dimension in plan.dimensions:
        expression, label = _dimension_expression(dimension, metric.table)
        select_parts.append(f"{expression} AS {label}")
        group_by_parts.append(expression)
        selected_fields.append(label)

    aggregation = plan.aggregations["metric_value"].upper()
    select_parts.append(f"ROUND({aggregation}({metric_alias}.{metric.column})::numeric, 2) AS metric_value")
    selected_fields.append("metric_value")

    joins = _join_clauses(plan.source_tables, metric.table)
    where_sql, where_params = _build_where_clause(plan.filters, metric.table, plan.time_window)
    params.extend(where_params)

    sql_parts = [
        "SELECT",
        "  " + ",\n  ".join(select_parts),
        f"FROM {metric.table} {metric_alias}",
        *joins,
    ]
    if where_sql:
        sql_parts.append(f"WHERE {where_sql}")
    if group_by_parts:
        sql_parts.append("GROUP BY " + ", ".join(group_by_parts))
    if plan.order_by:
        order = plan.order_by[0]
        sql_parts.append(f"ORDER BY {order.field} {order.direction.upper()}")
    if plan.limit:
        sql_parts.append("LIMIT %s")
        params.append(plan.limit)

    return CompiledSql(sql="\n".join(sql_parts), params=params, selected_fields=selected_fields)


def _compile_workload_proxy(plan: QueryPlan) -> CompiledSql:
    params: list[Any] = []
    select_parts: list[str] = []
    group_by_parts: list[str] = []
    selected_fields: list[str] = []

    for dimension in plan.dimensions:
        expression, label = _dimension_expression(dimension, "gps_metrics")
        select_parts.append(f"{expression} AS {label}")
        group_by_parts.append(expression)
        selected_fields.append(label)

    metric_selects = [
        ("metric_value", "ROUND(SUM(g.total_distance)::numeric, 2)"),
        ("total_distance", "ROUND(SUM(g.total_distance)::numeric, 2)"),
        ("total_sprint_distance", "ROUND(SUM(g.sprint_distance)::numeric, 2)"),
        ("total_hie", "ROUND(SUM(g.high_intensity_efforts)::numeric, 2)"),
        ("total_duration_minutes", "ROUND(SUM(s.duration_minutes)::numeric, 2)"),
    ]
    for label, expression in metric_selects:
        select_parts.append(f"{expression} AS {label}")
        selected_fields.append(label)

    joins = _join_clauses(plan.source_tables, "gps_metrics")
    where_sql, where_params = _build_where_clause(plan.filters, "gps_metrics", plan.time_window)
    params.extend(where_params)

    sql_parts = [
        "SELECT",
        "  " + ",\n  ".join(select_parts),
        "FROM gps_metrics g",
        *joins,
    ]
    if where_sql:
        sql_parts.append(f"WHERE {where_sql}")
    if group_by_parts:
        sql_parts.append("GROUP BY " + ", ".join(group_by_parts))
    if plan.order_by:
        order = plan.order_by[0]
        sql_parts.append(f"ORDER BY {order.field} {order.direction.upper()}")
    if plan.limit:
        sql_parts.append("LIMIT %s")
        params.append(plan.limit)

    return CompiledSql(sql="\n".join(sql_parts), params=params, selected_fields=selected_fields)


def _compile_baseline_gap(plan: QueryPlan) -> CompiledSql:
    if plan.metric == "workload":
        return _compile_workload_baseline(plan)
    return _compile_metric_baseline(plan)


def _compile_workload_baseline(plan: QueryPlan) -> CompiledSql:
    if plan.time_window is None or plan.time_window.start_date is None or plan.time_window.end_date is None:
        raise ValueError("Baseline queries require a concrete time window.")

    filter_sql, filter_params = _build_filter_clause(plan.filters)
    params: list[Any] = list(filter_params)
    params.extend([plan.time_window.start_date, plan.time_window.start_date, plan.time_window.end_date])

    session_output_where = f"\n  WHERE {filter_sql}" if filter_sql else ""
    sql = f"""
WITH session_output AS (
  SELECT
    a.athlete_id,
    a.name AS athlete_name,
    a.position,
    a.team,
    TO_DATE(s.session_date, '{DATE_FORMAT}') AS session_date,
    g.total_distance,
    g.sprint_distance,
    g.high_intensity_efforts,
    s.duration_minutes
  FROM athletes a
  JOIN sessions s ON s.athlete_id = a.athlete_id
  JOIN gps_metrics g ON g.session_id = s.session_id{session_output_where}
),
baseline AS (
  SELECT
    athlete_id,
    AVG(total_distance) AS baseline_distance,
    AVG(sprint_distance) AS baseline_sprint,
    AVG(high_intensity_efforts) AS baseline_hie,
    AVG(duration_minutes) AS baseline_duration_minutes
  FROM session_output
  WHERE session_date < %s
  GROUP BY athlete_id
),
recent AS (
  SELECT
    athlete_id,
    AVG(total_distance) AS recent_distance,
    AVG(sprint_distance) AS recent_sprint,
    AVG(high_intensity_efforts) AS recent_hie,
    AVG(duration_minutes) AS recent_duration_minutes
  FROM session_output
  WHERE session_date BETWEEN %s AND %s
  GROUP BY athlete_id
)
SELECT
  so.athlete_id AS athlete_id,
  so.athlete_name AS athlete_name,
  so.position AS position,
  ROUND(b.baseline_distance::numeric, 2) AS baseline_distance,
  ROUND(r.recent_distance::numeric, 2) AS recent_distance,
  ROUND(b.baseline_sprint::numeric, 2) AS baseline_sprint,
  ROUND(r.recent_sprint::numeric, 2) AS recent_sprint,
  ROUND(b.baseline_hie::numeric, 2) AS baseline_hie,
  ROUND(r.recent_hie::numeric, 2) AS recent_hie,
  ROUND(b.baseline_duration_minutes::numeric, 2) AS baseline_duration_minutes,
  ROUND(r.recent_duration_minutes::numeric, 2) AS recent_duration_minutes,
  ROUND((r.recent_distance - b.baseline_distance)::numeric, 2) AS baseline_delta,
  ROUND((((r.recent_distance - b.baseline_distance) / NULLIF(b.baseline_distance, 0)) * 100)::numeric, 1) AS baseline_gap_pct
FROM (
  SELECT DISTINCT athlete_id, athlete_name, position
  FROM session_output
) so
JOIN baseline b ON b.athlete_id = so.athlete_id
JOIN recent r ON r.athlete_id = so.athlete_id
WHERE r.recent_distance < b.baseline_distance
ORDER BY baseline_gap_pct ASC, athlete_name ASC
LIMIT %s
""".strip()
    params.append(plan.limit)

    return CompiledSql(
        sql=sql,
        params=params,
        selected_fields=[
            "athlete_id",
            "athlete_name",
            "position",
            "baseline_distance",
            "recent_distance",
            "baseline_sprint",
            "recent_sprint",
            "baseline_hie",
            "recent_hie",
            "baseline_duration_minutes",
            "recent_duration_minutes",
            "baseline_delta",
            "baseline_gap_pct",
        ],
    )


def _compile_metric_baseline(plan: QueryPlan) -> CompiledSql:
    if plan.time_window is None or plan.time_window.start_date is None or plan.time_window.end_date is None:
        raise ValueError("Baseline queries require a concrete time window.")

    metric = METRIC_REGISTRY[plan.metric]
    metric_alias = TABLE_ALIASES[metric.table]
    date_expression = _date_expression(metric.table)
    joins = _join_clauses(plan.source_tables, metric.table)
    filter_sql, filter_params = _build_filter_clause(plan.filters)
    base_where = f"\n  WHERE {filter_sql}" if filter_sql else ""
    params: list[Any] = []
    params.extend(filter_params)
    params.extend([plan.time_window.start_date, plan.time_window.start_date, plan.time_window.end_date, plan.limit])

    sql = f"""
WITH metric_points AS (
  SELECT
    a.athlete_id,
    a.name AS athlete_name,
    a.position,
    {date_expression} AS session_date,
    {metric_alias}.{metric.column} AS metric_value
  FROM {metric.table} {metric_alias}
  {' '.join(joins)}{base_where}
),
baseline AS (
  SELECT athlete_id, AVG(metric_value) AS baseline_value
  FROM metric_points
  WHERE session_date < %s
  GROUP BY athlete_id
),
recent AS (
  SELECT athlete_id, AVG(metric_value) AS recent_value
  FROM metric_points
  WHERE session_date BETWEEN %s AND %s
  GROUP BY athlete_id
)
SELECT
  mp.athlete_id AS athlete_id,
  mp.athlete_name AS athlete_name,
  mp.position AS position,
  ROUND(b.baseline_value::numeric, 2) AS baseline_value,
  ROUND(r.recent_value::numeric, 2) AS recent_value,
  ROUND((r.recent_value - b.baseline_value)::numeric, 2) AS baseline_delta,
  ROUND((((r.recent_value - b.baseline_value) / NULLIF(b.baseline_value, 0)) * 100)::numeric, 1) AS baseline_gap_pct
FROM (
  SELECT DISTINCT athlete_id, athlete_name, position
  FROM metric_points
) mp
JOIN baseline b ON b.athlete_id = mp.athlete_id
JOIN recent r ON r.athlete_id = mp.athlete_id
WHERE r.recent_value < b.baseline_value
ORDER BY baseline_gap_pct ASC, athlete_name ASC
LIMIT %s
""".strip()

    return CompiledSql(
        sql=sql,
        params=params,
        selected_fields=[
            "athlete_id",
            "athlete_name",
            "position",
            "baseline_value",
            "recent_value",
            "baseline_delta",
            "baseline_gap_pct",
        ],
    )


def _join_clauses(source_tables: list[str], metric_table: str) -> list[str]:
    joins: list[str] = []
    if metric_table == "gps_metrics":
        joins.append("JOIN sessions s ON s.session_id = g.session_id")
        joins.append("JOIN athletes a ON a.athlete_id = s.athlete_id")
    elif metric_table == "sessions":
        joins.append("JOIN athletes a ON a.athlete_id = s.athlete_id")
    elif metric_table == "wellness":
        joins.append("JOIN athletes a ON a.athlete_id = w.athlete_id")
    else:
        raise ValueError(f"Unsupported metric table: {metric_table}")

    if "sessions" in source_tables and metric_table == "wellness":
        joins.append("JOIN sessions s ON s.athlete_id = a.athlete_id")
    return joins


def _dimension_expression(dimension: str, metric_table: str) -> tuple[str, str]:
    if dimension == "athlete_id":
        return "a.athlete_id", "athlete_id"
    if dimension == "athlete_name":
        return "a.name", "athlete_name"
    if dimension == "position":
        return "a.position", "position"
    if dimension == "team":
        return "a.team", "team"
    if dimension == "session_type":
        return "s.session_type", "session_type"
    if dimension == "session_date":
        return _date_expression(metric_table), "session_date"
    raise ValueError(f"Unsupported dimension: {dimension}")


def _date_expression(metric_table: str) -> str:
    if metric_table in {"gps_metrics", "sessions"}:
        return f"TO_DATE(s.session_date, '{DATE_FORMAT}')"
    if metric_table == "wellness":
        return f"TO_DATE(w.date, '{DATE_FORMAT}')"
    raise ValueError(f"Unsupported metric table: {metric_table}")


def _build_where_clause(
    filters: list[QueryFilter],
    metric_table: str,
    time_window: Any,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if time_window and time_window.start_date and time_window.end_date:
        clauses.append(f"{_date_expression(metric_table)} BETWEEN %s AND %s")
        params.extend([time_window.start_date, time_window.end_date])

    filter_sql, filter_params = _build_filter_clause(filters)
    if filter_sql:
        clauses.append(filter_sql)
        params.extend(filter_params)

    return (" AND ".join(clauses) if clauses else "1=1"), params


def _build_filter_clause(filters: list[QueryFilter]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for query_filter in filters:
        if query_filter.field == "position":
            clauses.append("a.position = %s")
            params.append(query_filter.value)
        elif query_filter.field == "team":
            clauses.append("a.team = %s")
            params.append(query_filter.value)
        elif query_filter.field == "session_type":
            clauses.append("s.session_type = %s")
            params.append(query_filter.value)
    return " AND ".join(clauses), params
