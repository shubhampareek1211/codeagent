from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

CONNECT_TIMEOUT_SECONDS = 5


class SportsAnalyticsRepository:
    def __init__(self, database_url: str | None) -> None:
        self.database_url = database_url

    def _connect(self, **kwargs: Any):
        try:
            import psycopg
        except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent.
            raise RuntimeError("psycopg is required to execute sports analytics queries.") from exc
        return psycopg.connect(self.database_url, connect_timeout=CONNECT_TIMEOUT_SECONDS, **kwargs)

    def bootstrap(self, schema_sql_path: str, seed_sql_path: str) -> None:
        if not self.database_url:
            return

        schema_sql = Path(schema_sql_path).read_text(encoding="utf-8")
        seed_sql = Path(seed_sql_path).read_text(encoding="utf-8")

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(schema_sql)
                cursor.execute(seed_sql)
            connection.commit()

    def execute_select(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        if not self.database_url:
            raise RuntimeError("SPORTS_DATABASE_URL or DATABASE_URL is required to execute analytics queries.")

        from psycopg.rows import dict_row

        with self._connect(row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]

    def explain(self, sql: str, params: list[Any]) -> str | None:
        """Validate compiled SQL against the live engine without executing it.

        Returns None when the SQL is valid (or no DB is configured, in which
        case validation is skipped), otherwise the engine's error message.
        """
        if not self.database_url:
            return None
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(f"EXPLAIN {sql}", params)
            return None
        except Exception as exc:
            message = str(exc).strip().splitlines()
            return message[0] if message else "SQL failed engine validation."

    def get_max_session_date(self) -> date | None:
        """Latest session date in the dataset — anchors relative time windows."""
        if not self.database_url:
            return None
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT MAX(TO_DATE(session_date, 'MM/DD/YYYY')) FROM sessions")
                    row = cursor.fetchone()
            return row[0] if row else None
        except Exception:  # pragma: no cover - runtime environment dependent.
            return None

    def list_athlete_names(self) -> list[str]:
        """Athlete names for entity grounding in intent extraction."""
        if not self.database_url:
            return []
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT name FROM athletes ORDER BY name")
                    return [row[0] for row in cursor.fetchall() if row[0]]
        except Exception:  # pragma: no cover - runtime environment dependent.
            return []

    def health_summary(self) -> dict[str, Any]:
        if not self.database_url:
            return {"status": "missing_database_url"}

        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
            return {"status": "ok"}
        except Exception as exc:  # pragma: no cover - exercised in runtime health only.
            return {"status": "error", "detail": str(exc)}
