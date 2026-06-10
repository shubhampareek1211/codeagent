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
    # ── original metrics ─────────────────────────────────────────────────────
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
        aliases=("total distance", "distance covered", "distance"),
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
        aliases=("sprint distance", "sprint metres", "sprinting", "sprint"),
    ),
    "high_intensity_efforts": MetricMeta(
        key="high_intensity_efforts",
        display_name="High Intensity Efforts",
        table="gps_metrics",
        column="high_intensity_efforts",
        date_field="session_date",
        default_aggregation="sum",
        unit="count",
        description="Repeated high intensity efforts recorded by GPS or derived from event data.",
        aliases=("high intensity efforts", "hie", "efforts", "high intensity"),
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
        aliases=("duration", "duration minutes", "session duration", "minutes played"),
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

    # ── StatsBomb event-derived metrics ───────────────────────────────────────
    "passes": MetricMeta(
        key="passes",
        display_name="Passes",
        table="gps_metrics",
        column="passes",
        date_field="session_date",
        default_aggregation="sum",
        unit="count",
        description="Total pass attempts per session derived from StatsBomb event data.",
        aliases=("passes", "pass count", "passing volume", "number of passes"),
    ),
    "shots": MetricMeta(
        key="shots",
        display_name="Shots",
        table="gps_metrics",
        column="shots",
        date_field="session_date",
        default_aggregation="sum",
        unit="count",
        description="Total shot attempts per session derived from StatsBomb event data.",
        aliases=("shots", "shot count", "shots taken", "shooting"),
    ),
    "pressures": MetricMeta(
        key="pressures",
        display_name="Pressures",
        table="gps_metrics",
        column="pressures",
        date_field="session_date",
        default_aggregation="sum",
        unit="count",
        description="Total defensive pressure actions per session (StatsBomb).",
        aliases=("pressures", "pressing actions", "press count", "pressing", "pressers", "most pressure"),
    ),
    "carries": MetricMeta(
        key="carries",
        display_name="Ball Carries",
        table="gps_metrics",
        column="carries",
        date_field="session_date",
        default_aggregation="sum",
        unit="count",
        description="Total ball carry events per session (StatsBomb).",
        aliases=("carries", "ball carries", "dribble carries", "carry count"),
    ),
    "dribbles": MetricMeta(
        key="dribbles",
        display_name="Dribbles",
        table="gps_metrics",
        column="dribbles",
        date_field="session_date",
        default_aggregation="sum",
        unit="count",
        description="Total dribble attempts per session (StatsBomb).",
        aliases=("dribbles", "dribble count", "take-ons"),
    ),

    # ── NFL Big Data Bowl tracking metrics ───────────────────────────────────
    "avg_speed": MetricMeta(
        key="avg_speed",
        display_name="Average Speed",
        table="gps_metrics",
        column="avg_speed",
        date_field="session_date",
        default_aggregation="avg",
        unit="m/s",
        description="Average speed in metres per second derived from NFL player tracking frames.",
        aliases=("average speed", "avg speed", "mean speed", "speed"),
    ),
    "max_speed": MetricMeta(
        key="max_speed",
        display_name="Max Speed",
        table="gps_metrics",
        column="max_speed",
        date_field="session_date",
        default_aggregation="max",
        unit="m/s",
        description="Peak speed in metres per second derived from NFL player tracking frames.",
        aliases=("max speed", "top speed", "peak speed", "fastest speed"),
    ),
}

GROUPING_ALIASES = {
    "position":    ("by position", "per position", "position", "positions"),
    "team":        ("by team", "per team", "team", "teams", "country"),
    "session_type": ("by session type", "per session type", "session type"),
    "athlete_name": ("by athlete", "per athlete", "athlete", "player", "players", "by player"),
    "session_date": ("over time", "by day", "daily", "trend", "trending", "by date", "date"),
    "competition":  ("by competition", "per competition", "competition", "tournament", "by tournament"),
    "nationality":  ("by nationality", "per nationality", "nationality", "by country of origin"),
    "sport":        ("by sport", "per sport", "sport", "across sports"),
    "opponent":     ("by opponent", "per opponent", "opponent", "opposing team", "vs"),
}

SUPPORTED_POSITIONS = (
    # Soccer
    "forward", "midfielder", "defender", "goalkeeper",
    # NFL
    "quarterback", "wide_receiver", "running_back", "tight_end",
    "lineman", "linebacker", "cornerback", "safety",
    "kicker", "punter",
)

SUPPORTED_SPORTS = ("soccer", "american_football")

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
    "statsbomb",
    "world cup",
    "nfl",
    "big data bowl",
}

TABLE_DESCRIPTIONS = {
    "athletes":        "Athlete master data — name, position, team, sport (soccer / american_football), nationality.",
    "sessions":        "Match/training sessions per athlete with date, duration, competition name, opponent, home/away.",
    "gps_metrics":     "Per-session distance, sprint, high-intensity, pass, shot, pressure, carry, dribble, and speed metrics.",
    "wellness":        "Daily athlete self-report wellness measures — fatigue and sleep scores.",
    "player_tracking": "Frame-level NFL player tracking — x/y position, speed, acceleration, direction per play.",
    "competitions":    "Competition metadata — name, sport, season, country, dates.",
}

SCHEMA_COLUMNS = {
    "athletes": [
        SchemaColumn(name="athlete_id",  type="int",  description="Primary key."),
        SchemaColumn(name="name",        type="text", description="Athlete display name."),
        SchemaColumn(name="position",    type="text", description="Primary on-field position."),
        SchemaColumn(name="team",        type="text", description="Team assignment."),
        SchemaColumn(name="sport",       type="text", description="Sport: soccer or american_football."),
        SchemaColumn(name="nationality", type="text", description="Athlete nationality / country."),
    ],
    "sessions": [
        SchemaColumn(name="session_id",       type="int",     description="Primary key."),
        SchemaColumn(name="athlete_id",       type="int",     description="Athlete foreign key."),
        SchemaColumn(name="session_date",     type="text",    description="Session date stored as MM/DD/YYYY."),
        SchemaColumn(name="duration_minutes", type="numeric", description="Session duration in minutes."),
        SchemaColumn(name="session_type",     type="text",    description="Training, recovery, or match."),
        SchemaColumn(name="competition",      type="text",    description="Competition name e.g. FIFA World Cup 2022."),
        SchemaColumn(name="opponent",         type="text",    description="Opposing team name."),
        SchemaColumn(name="home_away",        type="text",    description="Whether the athlete played home or away."),
    ],
    "gps_metrics": [
        SchemaColumn(name="session_id",           type="int",     description="Session foreign key."),
        SchemaColumn(name="total_distance",        type="numeric", description="Meters covered (GPS or event-derived)."),
        SchemaColumn(name="sprint_distance",       type="numeric", description="Sprint metres covered."),
        SchemaColumn(name="high_intensity_efforts",type="numeric", description="High intensity effort count."),
        SchemaColumn(name="passes",                type="int",     description="Pass attempt count (StatsBomb)."),
        SchemaColumn(name="shots",                 type="int",     description="Shot attempt count (StatsBomb)."),
        SchemaColumn(name="pressures",             type="int",     description="Pressure action count (StatsBomb)."),
        SchemaColumn(name="carries",               type="int",     description="Ball carry count (StatsBomb)."),
        SchemaColumn(name="dribbles",              type="int",     description="Dribble attempt count (StatsBomb)."),
        SchemaColumn(name="avg_speed",             type="numeric", description="Average speed in m/s (NFL tracking)."),
        SchemaColumn(name="max_speed",             type="numeric", description="Peak speed in m/s (NFL tracking)."),
    ],
    "wellness": [
        SchemaColumn(name="athlete_id",   type="int",     description="Athlete foreign key."),
        SchemaColumn(name="date",         type="text",    description="Check-in date stored as MM/DD/YYYY."),
        SchemaColumn(name="fatigue_score",type="numeric", description="Fatigue score."),
        SchemaColumn(name="sleep_score",  type="numeric", description="Sleep quality score."),
    ],
    "player_tracking": [
        SchemaColumn(name="tracking_id",  type="bigint",  description="Primary key."),
        SchemaColumn(name="athlete_id",   type="int",     description="Athlete foreign key."),
        SchemaColumn(name="session_id",   type="int",     description="Session foreign key."),
        SchemaColumn(name="play_id",      type="int",     description="NFL play identifier."),
        SchemaColumn(name="frame_id",     type="int",     description="Frame number within play (10 fps)."),
        SchemaColumn(name="x",            type="numeric", description="Field x-coordinate in yards."),
        SchemaColumn(name="y",            type="numeric", description="Field y-coordinate in yards."),
        SchemaColumn(name="speed",        type="numeric", description="Speed in m/s."),
        SchemaColumn(name="acceleration", type="numeric", description="Acceleration in m/s²."),
        SchemaColumn(name="event_name",   type="text",    description="Tracking event label (snap, tackle, etc.)."),
    ],
}


def build_schema_response() -> SchemaResponse:
    return SchemaResponse(
        schema_name=SPORTS_SCHEMA,
        tables=[
            SchemaTable(name=name, description=TABLE_DESCRIPTIONS[name], columns=SCHEMA_COLUMNS[name])
            for name in ("athletes", "sessions", "gps_metrics", "wellness", "player_tracking")
        ],
        relationships=[
            "sessions.athlete_id -> athletes.athlete_id",
            "gps_metrics.session_id -> sessions.session_id",
            "wellness.athlete_id -> athletes.athlete_id",
            "player_tracking.athlete_id -> athletes.athlete_id",
            "player_tracking.session_id -> sessions.session_id",
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
