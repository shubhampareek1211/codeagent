from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class QueryFilter(BaseModel):
    field: str
    operator: Literal["=", "!=", ">", ">=", "<", "<=", "in", "between"]
    value: Any


class TimeWindow(BaseModel):
    label: str
    start_date: date | None = None
    end_date: date | None = None
    lookback_days: int | None = None


class SportsQueryRequest(BaseModel):
    query: str = Field(..., min_length=3)
    top_k: int = Field(default=4, ge=1, le=10)
    include_debug: bool = False


class RetrievedDocument(BaseModel):
    id: str
    title: str
    content: str
    source_type: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class StructuredIntent(BaseModel):
    raw_query: str
    normalized_query: str
    metric: str | None = None
    metrics: list[str] = Field(default_factory=list)
    entity: str = "athlete"
    grouping: str | None = None
    aggregation: str | None = None
    filters: list[QueryFilter] = Field(default_factory=list)
    time_window: TimeWindow | None = None
    comparison_type: Literal["none", "trend", "baseline"] = "none"
    ranking: Literal["top", "bottom", "none"] = "none"
    output_type: Literal["kpi", "table", "ranked_list", "grouped_output", "trend"] = "table"
    chart_requested: bool = False
    chart_eligible: bool = False
    confidence: float = 0.0
    ambiguity_flags: list[str] = Field(default_factory=list)
    interpretation_notes: list[str] = Field(default_factory=list)


class JoinSpec(BaseModel):
    table: str
    on: str


class SortSpec(BaseModel):
    field: str
    direction: Literal["asc", "desc"] = "desc"


class QueryPlan(BaseModel):
    query_kind: Literal["aggregate", "timeseries", "baseline_gap"]
    metric: str
    metric_table: str
    source_tables: list[str]
    joins: list[JoinSpec] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    aggregations: dict[str, str] = Field(default_factory=dict)
    filters: list[QueryFilter] = Field(default_factory=list)
    time_window: TimeWindow | None = None
    order_by: list[SortSpec] = Field(default_factory=list)
    limit: int = 10
    output_type: str = "table"
    comparison_type: str = "none"
    notes: list[str] = Field(default_factory=list)


class ValidationOutcome(BaseModel):
    valid: bool
    messages: list[str] = Field(default_factory=list)


class CompiledSql(BaseModel):
    sql: str
    params: list[Any] = Field(default_factory=list)
    selected_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QueryData(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0


class VisualizationSpec(BaseModel):
    chart_type: Literal["none", "metric_card", "bar", "line", "table"] = "none"
    title: str
    reason: str
    x_field: str | None = None
    y_fields: list[str] = Field(default_factory=list)
    data: list[dict[str, Any]] = Field(default_factory=list)


class QueryResponse(BaseModel):
    normalized_query: str
    intent: StructuredIntent
    plan: QueryPlan | None = None
    sql: CompiledSql | None = None
    data: QueryData = Field(default_factory=QueryData)
    visualization: VisualizationSpec = Field(
        default_factory=lambda: VisualizationSpec(title="No chart", reason="No chart available.")
    )
    summary: str
    warnings: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_prompt: str | None = None
    retrieved_context: list[RetrievedDocument] = Field(default_factory=list)


class RetrievalDebugResponse(BaseModel):
    intent: StructuredIntent
    retrieval_needed: bool
    results: list[RetrievedDocument] = Field(default_factory=list)


class IntentDebugResponse(BaseModel):
    intent: StructuredIntent


class SqlDebugResponse(BaseModel):
    intent: StructuredIntent
    plan: QueryPlan | None = None
    plan_validation: ValidationOutcome
    sql: CompiledSql | None = None
    sql_validation: ValidationOutcome


class SchemaColumn(BaseModel):
    name: str
    type: str
    description: str


class SchemaTable(BaseModel):
    name: str
    description: str
    columns: list[SchemaColumn]


class SchemaResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(alias="schema")
    tables: list[SchemaTable]
    relationships: list[str]


class MetricSummary(BaseModel):
    key: str
    display_name: str
    unit: str
    table: str
    default_aggregation: str
    description: str


class MetricsResponse(BaseModel):
    metrics: list[MetricSummary]
