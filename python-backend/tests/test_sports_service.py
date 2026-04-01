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
