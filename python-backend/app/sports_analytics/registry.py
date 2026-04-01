from __future__ import annotations

from dataclasses import dataclass

from app.sports_analytics.models import MetricSummary, SchemaColumn, SchemaResponse, SchemaTable


SPORTS_SCHEMA = "public"


@dataclass(frozen=True)
class MetricMeta:
    key: str
    display_name: str
    table: str
    column: str
    date_field: str
    default_aggregation: str
    unit: str
    description: str
    aliases: tuple[str, ...]
    higher_is_better: bool = True


METRIC_REGISTRY: dict[str, MetricMeta] = {
    "workload": MetricMeta(
        key="workload",
        display_name="Workload Proxy",
        table="gps_metrics",
        column="total_distance",
        date_field="session_date",
        default_aggregation="sum",
        unit="m",
        description=(
            "Proxy workload view ranked by summed total distance and returned with sprint distance, "
            "high intensity efforts, and duration components because the schema has no workload column."
        ),
        aliases=("workload", "load", "external load"),
    ),
    "total_distance": MetricMeta(
        key="total_distance",
        display_name="Total Distance",
        table="gps_metrics",
        column="total_distance",
        date_field="session_date",
        default_aggregation="sum",
        unit="m",
        description="Total distance covered in meters across joined sessions.",
        aliases=("total distance", "distance covered"),
    ),
    "sprint_distance": MetricMeta(
        key="sprint_distance",
        display_name="Sprint Distance",
        table="gps_metrics",
        column="sprint_distance",
        date_field="session_date",
        default_aggregation="sum",
        unit="m",
        description="Sprint distance accumulated per session.",
        aliases=("sprint distance", "sprint metres", "sprinting"),
    ),
    "high_intensity_efforts": MetricMeta(
        key="high_intensity_efforts",
        display_name="High Intensity Efforts",
        table="gps_metrics",
        column="high_intensity_efforts",
        date_field="session_date",
        default_aggregation="sum",
        unit="count",
        description="Repeated high intensity efforts recorded by GPS.",
        aliases=("high intensity efforts", "hie", "efforts"),
    ),
    "duration_minutes": MetricMeta(
        key="duration_minutes",
        display_name="Session Duration",
        table="sessions",
        column="duration_minutes",
        date_field="session_date",
        default_aggregation="avg",
        unit="min",
        description="Session duration in minutes.",
        aliases=("duration", "duration minutes", "session duration"),
    ),
    "fatigue_score": MetricMeta(
        key="fatigue_score",
        display_name="Fatigue Score",
        table="wellness",
        column="fatigue_score",
        date_field="date",
        default_aggregation="avg",
        unit="score",
        description="Average fatigue score recorded in wellness check-ins.",
        aliases=("fatigue", "fatigue score"),
        higher_is_better=False,
    ),
    "sleep_score": MetricMeta(
        key="sleep_score",
        display_name="Sleep Score",
        table="wellness",
        column="sleep_score",
        date_field="date",
        default_aggregation="avg",
        unit="score",
        description="Average sleep score recorded in wellness check-ins.",
        aliases=("sleep", "sleep score"),
    ),
}

GROUPING_ALIASES = {
    "position": ("by position", "per position", "position"),
    "team": ("by team", "per team", "team"),
    "session_type": ("by session type", "per session type", "session type"),
    "athlete_name": ("by athlete", "per athlete", "athlete", "player"),
    "session_date": ("over time", "by day", "daily", "trend", "trending"),
}

SUPPORTED_POSITIONS = ("forward", "midfielder", "defender", "goalkeeper")
SUPPORTED_TEAMS: tuple[str, ...] = ()

BUSINESS_TERM_ALIASES = {
    "baseline": ("baseline", "baseline performance", "below baseline"),
    "performance": ("performance", "output"),
}

RETRIEVAL_TRIGGER_TERMS = {
    "baseline",
    "baseline performance",
    "underperforming",
    "trending below baseline",
    "workload",
}

TABLE_DESCRIPTIONS = {
    "athletes": "Athlete master data for name, position, and team.",
    "sessions": "Training or match sessions linked to athletes, stored with text dates.",
    "gps_metrics": "Per-session distance, sprint, and high-intensity metrics keyed by session_id.",
    "wellness": "Daily athlete self-report wellness measures keyed by athlete_id and text date.",
}

SCHEMA_COLUMNS = {
    "athletes": [
        SchemaColumn(name="athlete_id", type="int", description="Primary key."),
        SchemaColumn(name="name", type="text", description="Athlete display name."),
        SchemaColumn(name="position", type="text", description="Primary on-field position."),
        SchemaColumn(name="team", type="text", description="Team assignment."),
    ],
    "sessions": [
        SchemaColumn(name="session_id", type="int", description="Primary key."),
        SchemaColumn(name="athlete_id", type="int", description="Athlete foreign key."),
        SchemaColumn(name="session_date", type="text", description="Session date stored as text."),
        SchemaColumn(name="duration_minutes", type="numeric", description="Session duration in minutes."),
        SchemaColumn(name="session_type", type="text", description="Training, recovery, or match."),
    ],
    "gps_metrics": [
        SchemaColumn(name="session_id", type="int", description="Session foreign key."),
        SchemaColumn(name="total_distance", type="numeric", description="Meters covered."),
        SchemaColumn(name="sprint_distance", type="numeric", description="Sprint meters covered."),
        SchemaColumn(name="high_intensity_efforts", type="numeric", description="High intensity effort count."),
    ],
    "wellness": [
        SchemaColumn(name="athlete_id", type="int", description="Athlete foreign key."),
        SchemaColumn(name="date", type="text", description="Check-in date stored as text."),
        SchemaColumn(name="fatigue_score", type="numeric", description="Fatigue score."),
        SchemaColumn(name="sleep_score", type="numeric", description="Sleep quality score."),
    ],
}


def build_schema_response() -> SchemaResponse:
    return SchemaResponse(
        schema_name=SPORTS_SCHEMA,
        tables=[
            SchemaTable(name=name, description=TABLE_DESCRIPTIONS[name], columns=SCHEMA_COLUMNS[name])
            for name in ("athletes", "sessions", "gps_metrics", "wellness")
        ],
        relationships=[
            "sessions.athlete_id -> athletes.athlete_id",
            "gps_metrics.session_id -> sessions.session_id",
            "wellness.athlete_id -> athletes.athlete_id",
        ],
    )


def build_metric_summaries() -> list[MetricSummary]:
    return [
        MetricSummary(
            key=metric.key,
            display_name=metric.display_name,
            unit=metric.unit,
            table=metric.table,
            default_aggregation=metric.default_aggregation,
            description=metric.description,
        )
        for metric in METRIC_REGISTRY.values()
    ]
