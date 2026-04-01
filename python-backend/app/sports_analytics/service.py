from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.sports_analytics.intent import extract_intent, normalize_query
from app.sports_analytics.models import (
    CompiledSql,
    IntentDebugResponse,
    MetricsResponse,
    QueryData,
    QueryPlan,
    QueryResponse,
    RetrievalDebugResponse,
    SchemaResponse,
    SportsQueryRequest,
    SqlDebugResponse,
    StructuredIntent,
    ValidationOutcome,
    VisualizationSpec,
)
from app.sports_analytics.planner import build_query_plan, validate_query_plan
from app.sports_analytics.registry import METRIC_REGISTRY, build_metric_summaries, build_schema_response
from app.sports_analytics.repository import SportsAnalyticsRepository
from app.sports_analytics.sql import compile_sql, validate_sql


class AnalyticsState(TypedDict, total=False):
    request: SportsQueryRequest
    normalized_query: str
    intent: StructuredIntent
    needs_clarification: bool
    clarification_prompt: str | None
    retrieval_needed: bool
    retrieved_context: list[dict[str, Any]]
    plan: QueryPlan
    plan_validation: ValidationOutcome
    sql: CompiledSql
    sql_validation: ValidationOutcome
    data: QueryData
    result_validation: ValidationOutcome
    visualization: VisualizationSpec
    summary: str
    warnings: list[str]
    response: QueryResponse


class RetrievalBackend(Protocol):
    documents: list[Any]

    def should_retrieve(self, intent: StructuredIntent) -> bool:
        ...

    def search(self, query: str, top_k: int = 4) -> list[Any]:
        ...


class SportsAnalyticsService:
    def __init__(
        self,
        repository: SportsAnalyticsRepository,
        retrieval_service: RetrievalBackend,
        default_limit: int = 10,
    ) -> None:
        self.repository = repository
        self.retrieval_service = retrieval_service
        self.default_limit = default_limit
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AnalyticsState)
        graph.add_node("normalize_query", self._normalize_query)
        graph.add_node("extract_intent", self._extract_intent)
        graph.add_node("detect_ambiguity", self._detect_ambiguity)
        graph.add_node("decide_retrieval", self._decide_retrieval)
        graph.add_node("retrieve_context", self._retrieve_context)
        graph.add_node("build_plan", self._build_plan)
        graph.add_node("validate_plan", self._validate_plan)
        graph.add_node("compile_sql", self._compile_sql)
        graph.add_node("validate_sql", self._validate_sql)
        graph.add_node("execute_sql", self._execute_sql)
        graph.add_node("post_process", self._post_process)
        graph.add_node("validate_results", self._validate_results)
        graph.add_node("choose_visualization", self._choose_visualization)
        graph.add_node("generate_summary", self._generate_summary)
        graph.add_node("finalize", self._finalize)

        graph.add_edge(START, "normalize_query")
        graph.add_edge("normalize_query", "extract_intent")
        graph.add_edge("extract_intent", "detect_ambiguity")
        graph.add_conditional_edges(
            "detect_ambiguity",
            self._route_after_ambiguity,
            {"clarify": "finalize", "continue": "decide_retrieval"},
        )
        graph.add_conditional_edges(
            "decide_retrieval",
            self._route_retrieval,
            {"retrieve": "retrieve_context", "skip": "build_plan"},
        )
        graph.add_edge("retrieve_context", "build_plan")
        graph.add_edge("build_plan", "validate_plan")
        graph.add_conditional_edges(
            "validate_plan",
            self._route_plan_validation,
            {"continue": "compile_sql", "stop": "finalize"},
        )
        graph.add_edge("compile_sql", "validate_sql")
        graph.add_conditional_edges(
            "validate_sql",
            self._route_sql_validation,
            {"continue": "execute_sql", "stop": "finalize"},
        )
        graph.add_edge("execute_sql", "post_process")
        graph.add_edge("post_process", "validate_results")
        graph.add_conditional_edges(
            "validate_results",
            self._route_result_validation,
            {"visualize": "choose_visualization", "summarize": "generate_summary"},
        )
        graph.add_edge("choose_visualization", "generate_summary")
        graph.add_edge("generate_summary", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile()

    def query(self, request: SportsQueryRequest) -> QueryResponse:
        result = self.graph.invoke({"request": request, "warnings": []})
        return result["response"]

    def debug_intent(self, request: SportsQueryRequest) -> IntentDebugResponse:
        intent = extract_intent(request.query)
        return IntentDebugResponse(intent=intent)

    def debug_retrieval(self, request: SportsQueryRequest) -> RetrievalDebugResponse:
        intent = extract_intent(request.query)
        retrieval_needed = self.retrieval_service.should_retrieve(intent)
        results = self.retrieval_service.search(request.query, top_k=request.top_k) if retrieval_needed else []
        return RetrievalDebugResponse(intent=intent, retrieval_needed=retrieval_needed, results=results)

    def debug_sql(self, request: SportsQueryRequest) -> SqlDebugResponse:
        intent = extract_intent(request.query)
        if intent.metric is None:
            invalid = ValidationOutcome(valid=False, messages=["A supported metric could not be identified."])
            return SqlDebugResponse(intent=intent, plan_validation=invalid, sql_validation=invalid)

        plan = build_query_plan(intent)
        plan.limit = self.default_limit
        plan_validation = validate_query_plan(plan)
        compiled = compile_sql(plan) if plan_validation.valid else None
        sql_validation = validate_sql(plan, compiled) if compiled else ValidationOutcome(valid=False, messages=["SQL was not compiled."])
        return SqlDebugResponse(
            intent=intent,
            plan=plan,
            plan_validation=plan_validation,
            sql=compiled,
            sql_validation=sql_validation,
        )

    def metrics_catalog(self) -> MetricsResponse:
        return MetricsResponse(metrics=build_metric_summaries())

    def schema_summary(self) -> SchemaResponse:
        return build_schema_response()

    def health_summary(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "knowledge_documents": len(self.retrieval_service.documents),
            "database": self.repository.health_summary(),
        }

    def _normalize_query(self, state: AnalyticsState) -> AnalyticsState:
        request = state["request"]
        return {"normalized_query": normalize_query(request.query)}

    def _extract_intent(self, state: AnalyticsState) -> AnalyticsState:
        request = state["request"]
        intent = extract_intent(request.query)
        return {"intent": intent}

    def _detect_ambiguity(self, state: AnalyticsState) -> AnalyticsState:
        intent = state["intent"]
        needs_clarification = intent.metric is None or intent.confidence < 0.5
        clarification_prompt = None
        if needs_clarification:
            clarification_prompt = (
                "Name a concrete metric such as workload, total distance, sprint distance, high intensity efforts, sleep score, or fatigue score."
            )
        return {
            "needs_clarification": needs_clarification,
            "clarification_prompt": clarification_prompt,
        }

    def _decide_retrieval(self, state: AnalyticsState) -> AnalyticsState:
        intent = state["intent"]
        return {"retrieval_needed": self.retrieval_service.should_retrieve(intent)}

    def _retrieve_context(self, state: AnalyticsState) -> AnalyticsState:
        request = state["request"]
        documents = self.retrieval_service.search(request.query, top_k=request.top_k)
        return {"retrieved_context": documents}

    def _build_plan(self, state: AnalyticsState) -> AnalyticsState:
        plan = build_query_plan(state["intent"])
        plan.limit = self.default_limit if plan.query_kind != "timeseries" else plan.limit
        return {"plan": plan}

    def _validate_plan(self, state: AnalyticsState) -> AnalyticsState:
        validation = validate_query_plan(state["plan"])
        warnings = list(state.get("warnings", []))
        warnings.extend(validation.messages)
        return {"plan_validation": validation, "warnings": warnings}

    def _compile_sql(self, state: AnalyticsState) -> AnalyticsState:
        return {"sql": compile_sql(state["plan"])}

    def _validate_sql(self, state: AnalyticsState) -> AnalyticsState:
        validation = validate_sql(state["plan"], state["sql"])
        warnings = list(state.get("warnings", []))
        warnings.extend(validation.messages)
        return {"sql_validation": validation, "warnings": warnings}

    def _execute_sql(self, state: AnalyticsState) -> AnalyticsState:
        rows = self.repository.execute_select(state["sql"].sql, state["sql"].params)
        return {"data": QueryData(columns=list(rows[0].keys()) if rows else [], rows=rows, row_count=len(rows))}

    def _post_process(self, state: AnalyticsState) -> AnalyticsState:
        data = state["data"]
        cleaned_rows: list[dict[str, Any]] = []
        for row in data.rows:
            cleaned_rows.append(
                {
                    key: self._normalize_output_value(value)
                    for key, value in row.items()
                }
            )
        return {"data": QueryData(columns=data.columns, rows=cleaned_rows, row_count=len(cleaned_rows))}

    def _validate_results(self, state: AnalyticsState) -> AnalyticsState:
        data = state["data"]
        messages: list[str] = []
        if data.row_count == 0:
            messages.append("No rows matched the requested filters and time window.")
        if data.row_count > 200:
            messages.append("Result set is larger than the expected MVP window.")
        warnings = list(state.get("warnings", []))
        warnings.extend(messages)
        return {
            "result_validation": ValidationOutcome(valid=not messages, messages=messages),
            "warnings": warnings,
        }

    def _choose_visualization(self, state: AnalyticsState) -> AnalyticsState:
        intent = state["intent"]
        data = state["data"]
        plan = state["plan"]
        visualization = VisualizationSpec(
            chart_type="table",
            title="Result Table",
            reason="Structured data is available but chart eligibility was not established.",
            data=data.rows,
        )

        if data.row_count == 0:
            visualization = VisualizationSpec(
                chart_type="none",
                title="No chart available",
                reason="The query returned no rows.",
                data=[],
            )
        elif plan.query_kind == "timeseries":
            visualization = VisualizationSpec(
                chart_type="line",
                title=f"{METRIC_REGISTRY[intent.metric].display_name} over time",
                reason="Time-series queries are best represented as line charts.",
                x_field="session_date",
                y_fields=["metric_value"],
                data=data.rows,
            )
        elif plan.query_kind == "baseline_gap":
            visualization = VisualizationSpec(
                chart_type="bar",
                title="Athletes below baseline",
                reason="Comparing athletes against baseline is best represented as a ranked bar chart.",
                x_field="athlete_name",
                y_fields=["baseline_gap_pct"],
                data=data.rows,
            )
        elif intent.grouping is not None or intent.ranking != "none":
            x_field = "athlete_name" if "athlete_name" in data.columns else (plan.dimensions[0] if plan.dimensions else "athlete_name")
            visualization = VisualizationSpec(
                chart_type="bar",
                title=f"{METRIC_REGISTRY[intent.metric].display_name} comparison",
                reason="Grouped or ranked comparisons are best represented as bar charts.",
                x_field=x_field,
                y_fields=["metric_value"],
                data=data.rows,
            )
        elif data.row_count == 1:
            visualization = VisualizationSpec(
                chart_type="metric_card",
                title=METRIC_REGISTRY[intent.metric].display_name,
                reason="Single aggregated values fit a metric card.",
                y_fields=["metric_value"],
                data=data.rows,
            )

        return {"visualization": visualization}

    def _generate_summary(self, state: AnalyticsState) -> AnalyticsState:
        intent = state["intent"]
        data = state.get("data", QueryData())
        metric = METRIC_REGISTRY[intent.metric] if intent.metric else None
        retrieved_context = state.get("retrieved_context", [])

        if state.get("needs_clarification"):
            summary = "The request needs clarification before SQL execution."
            return {"summary": summary}

        if data.row_count == 0:
            summary = "No results matched the current filters and time window."
            return {"summary": summary}

        if state["plan"].query_kind == "baseline_gap":
            lead = data.rows[0]
            summary = (
                f"{data.row_count} athletes are below their historical baseline. "
                f"{lead['athlete_name']} is furthest below at {lead['baseline_gap_pct']}% versus baseline."
            )
        elif state["plan"].query_kind == "timeseries":
            peak = max(data.rows, key=lambda row: row["metric_value"])
            summary = (
                f"{metric.display_name} is available across {data.row_count} time points. "
                f"The peak was {peak['metric_value']} {metric.unit} on {peak['session_date']}."
            )
        elif intent.grouping is not None or intent.ranking != "none":
            lead = data.rows[0]
            dimension = "athlete_name" if "athlete_name" in data.columns else (state["plan"].dimensions[0] if state["plan"].dimensions else "athlete_name")
            dimension_label = "athlete" if dimension == "athlete_name" else dimension.replace("_", " ")
            if intent.metric == "workload":
                summary = (
                    f"Using total distance as the workload proxy, the leading {dimension_label} is {lead[dimension]} "
                    f"with {lead['total_distance']} m, plus {lead['total_sprint_distance']} m sprint distance "
                    f"and {lead['total_hie']} high intensity efforts."
                )
            else:
                summary = (
                    f"The leading {dimension_label} is {lead[dimension]} "
                    f"with {lead['metric_value']} {metric.unit}."
                )
        else:
            value = data.rows[0]["metric_value"]
            summary = f"The aggregate {metric.display_name.lower()} for the selected window is {value} {metric.unit}."

        if retrieved_context:
            top_context = retrieved_context[0]
            summary += f" Context was grounded with '{top_context.title}'."

        return {"summary": summary}

    def _finalize(self, state: AnalyticsState) -> AnalyticsState:
        intent = state.get("intent")
        response = QueryResponse(
            normalized_query=state.get("normalized_query", ""),
            intent=intent
            if intent is not None
            else StructuredIntent(raw_query="", normalized_query="", confidence=0.0),
            plan=state.get("plan"),
            sql=state.get("sql"),
            data=state.get("data", QueryData()),
            visualization=state.get(
                "visualization",
                VisualizationSpec(title="No chart", reason="No chart available."),
            ),
            summary=state.get("summary", "No response was generated."),
            warnings=state.get("warnings", []),
            needs_clarification=state.get("needs_clarification", False),
            clarification_prompt=state.get("clarification_prompt"),
            retrieved_context=state.get("retrieved_context", []),
        )
        return {"response": response}

    @staticmethod
    def _route_after_ambiguity(state: AnalyticsState) -> str:
        return "clarify" if state.get("needs_clarification") else "continue"

    @staticmethod
    def _route_retrieval(state: AnalyticsState) -> str:
        return "retrieve" if state.get("retrieval_needed") else "skip"

    @staticmethod
    def _route_plan_validation(state: AnalyticsState) -> str:
        return "continue" if state["plan_validation"].valid else "stop"

    @staticmethod
    def _route_sql_validation(state: AnalyticsState) -> str:
        return "continue" if state["sql_validation"].valid else "stop"

    @staticmethod
    def _route_result_validation(state: AnalyticsState) -> str:
        return "visualize" if state["result_validation"].valid else "summarize"

    @staticmethod
    def _normalize_output_value(value: Any) -> Any:
        if isinstance(value, Decimal):
            return round(float(value), 2)
        if isinstance(value, float):
            return round(value, 2)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return value
