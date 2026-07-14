from decimal import Decimal

from app.sports_analytics.models import RetrievedDocument, SportsQueryRequest
from app.sports_analytics.service import SportsAnalyticsService


class FakeRepository:
    def execute_select(self, sql: str, params: list[object]) -> list[dict[str, object]]:
        if "baseline_gap_pct" in sql:
            return [
                {
                    "athlete_id": 2,
                    "athlete_name": "Liam Johnson",
                    "position": "Midfielder",
                    "baseline_distance": 4120.0,
                    "recent_distance": 3810.0,
                    "baseline_sprint": 520.0,
                    "recent_sprint": 470.0,
                    "baseline_hie": 18.0,
                    "recent_hie": 15.0,
                    "baseline_duration_minutes": 82.0,
                    "recent_duration_minutes": 77.0,
                    "baseline_delta": -310.0,
                    "baseline_gap_pct": -7.5,
                },
            ]

        return [
            {
                "athlete_id": 4,
                "athlete_name": "Oliver Brown",
                "position": "Forward",
                "metric_value": Decimal("21100.00"),
                "total_distance": Decimal("21100.00"),
                "total_sprint_distance": Decimal("2800.00"),
                "total_hie": Decimal("109.00"),
                "total_duration_minutes": Decimal("170.00"),
            },
        ]

    def health_summary(self) -> dict[str, str]:
        return {"status": "ok"}


class FakeRetrieval:
    def __init__(self) -> None:
        self.documents = [object()]

    def should_retrieve(self, intent) -> bool:  # type: ignore[no-untyped-def]
        return intent.comparison_type == "baseline"

    def search(self, query: str, top_k: int = 4) -> list[RetrievedDocument]:
        return [
            RetrievedDocument(
                id="rule-baseline-performance",
                title="Baseline Performance Rule",
                content="Baseline means comparing the recent 7 day average to the athlete's historical average before that window.",
                source_type="business_rule",
                score=0.98,
                metadata={"topic": "baseline"},
            )
        ]


def test_graph_returns_ranked_response() -> None:
    service = SportsAnalyticsService(
        repository=FakeRepository(),
        retrieval_service=FakeRetrieval(),
        default_limit=5,
    )

    response = service.query(SportsQueryRequest(query="Which athletes had the highest workload last week?"))

    assert response.needs_clarification is False
    assert response.plan is not None
    assert response.plan.query_kind == "aggregate"
    assert response.visualization.chart_type == "bar"
    assert response.data.row_count == 1
    assert response.data.rows[0]["metric_value"] == 21100.0
    assert response.summary == (
        "Using total distance as the workload proxy, the leading athlete is Oliver Brown "
        "with 21100.0 m, plus 2800.0 m sprint distance and 109.0 high intensity efforts."
    )


class FakeGroupedRepository(FakeRepository):
    def execute_select(self, sql: str, params: list[object]) -> list[dict[str, object]]:
        return [
            {"position": "wide_receiver", "metric_value": Decimal("6.21")},
            {"position": "cornerback", "metric_value": Decimal("6.05")},
        ]


def test_grouped_ranking_summary_uses_grouping_label() -> None:
    service = SportsAnalyticsService(
        repository=FakeGroupedRepository(),
        retrieval_service=FakeRetrieval(),
        default_limit=5,
    )

    response = service.query(SportsQueryRequest(query="Which NFL position averages the highest speed?"))

    assert response.plan is not None
    assert response.plan.dimensions == ["position"]
    assert response.data.rows[0]["position"] == "wide_receiver"
    assert "athlete_name" not in response.data.columns
    assert response.summary.startswith("The leading position is wide_receiver")


def test_graph_returns_baseline_response_with_grounding() -> None:
    service = SportsAnalyticsService(
        repository=FakeRepository(),
        retrieval_service=FakeRetrieval(),
        default_limit=5,
    )

    response = service.query(SportsQueryRequest(query="Who is trending below their baseline performance?"))

    assert response.plan is not None
    assert response.plan.query_kind == "baseline_gap"
    assert response.visualization.chart_type == "bar"
    assert response.retrieved_context
    assert "historical baseline" in response.summary.lower()


# ── Audit regression tests (PLAN.md M0 / T4.1) ──────────────────────────────


class FakeAnchoredRepository(FakeRepository):
    """Repository exposing dataset date bounds + entity index + explain."""

    def __init__(self) -> None:
        self.explained: list[str] = []

    def get_max_session_date(self):
        from datetime import date

        return date(2022, 12, 18)

    def list_athlete_names(self) -> list[str]:
        return ["Lionel Andrés Messi Cuccittini"]

    def explain(self, sql: str, params: list[object]) -> str | None:
        self.explained.append(sql)
        return None


def test_relative_windows_anchor_to_dataset_max_date() -> None:
    """'last week' anchors to the data's latest date, not the wall clock (audit B5)."""
    service = SportsAnalyticsService(
        repository=FakeAnchoredRepository(),
        retrieval_service=FakeRetrieval(),
        default_limit=5,
    )

    response = service.query(SportsQueryRequest(query="Which athletes had the highest workload last week?"))

    assert response.intent.time_window is not None
    assert str(response.intent.time_window.end_date) == "2022-12-18"


def test_compiled_sql_is_engine_validated_via_explain() -> None:
    repository = FakeAnchoredRepository()
    service = SportsAnalyticsService(
        repository=repository,
        retrieval_service=FakeRetrieval(),
        default_limit=5,
    )

    service.query(SportsQueryRequest(query="Top 5 players by total distance"))

    assert repository.explained  # EXPLAIN ran before execution


class FailingExplainRepository(FakeAnchoredRepository):
    def explain(self, sql: str, params: list[object]) -> str | None:
        return 'missing FROM-clause entry for table "s"'

    def execute_select(self, sql: str, params: list[object]) -> list[dict[str, object]]:
        raise AssertionError("execution must not run when engine validation fails")


def test_engine_validation_failure_stops_execution_gracefully() -> None:
    service = SportsAnalyticsService(
        repository=FailingExplainRepository(),
        retrieval_service=FakeRetrieval(),
        default_limit=5,
    )

    response = service.query(SportsQueryRequest(query="Top 5 players by total distance"))

    assert response.data.row_count == 0
    assert any("engine validation" in warning for warning in response.warnings)


class BrokenRepository(FakeAnchoredRepository):
    def explain(self, sql: str, params: list[object]) -> str | None:
        return None

    def execute_select(self, sql: str, params: list[object]) -> list[dict[str, object]]:
        raise RuntimeError("connection refused")


def test_db_failure_returns_graceful_response_not_500() -> None:
    """DB errors surface as warnings, never unhandled exceptions (audit M4)."""
    service = SportsAnalyticsService(
        repository=BrokenRepository(),
        retrieval_service=FakeRetrieval(),
        default_limit=5,
    )

    response = service.query(SportsQueryRequest(query="Top 5 players by total distance"))

    assert response.data.row_count == 0
    assert any("Query execution failed" in warning for warning in response.warnings)
    assert "could not be executed" in response.summary
