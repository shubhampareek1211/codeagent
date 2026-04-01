from __future__ import annotations

from pathlib import Path
from typing import Any


class SportsAnalyticsRepository:
    def __init__(self, database_url: str | None) -> None:
        self.database_url = database_url

    def bootstrap(self, schema_sql_path: str, seed_sql_path: str) -> None:
        if not self.database_url:
            return

        try:
            import psycopg
        except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent.
            raise RuntimeError("psycopg is required to bootstrap the sports analytics database.") from exc

        schema_sql = Path(schema_sql_path).read_text(encoding="utf-8")
        seed_sql = Path(seed_sql_path).read_text(encoding="utf-8")

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(schema_sql)
                cursor.execute(seed_sql)
            connection.commit()

    def execute_select(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        if not self.database_url:
            raise RuntimeError("SPORTS_DATABASE_URL or DATABASE_URL is required to execute analytics queries.")

        try:
            import psycopg
            from psycopg.rows import dict_row
        except ModuleNotFoundError as exc:
            raise RuntimeError("psycopg is required to execute sports analytics queries.") from exc

        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]

    def health_summary(self) -> dict[str, Any]:
        if not self.database_url:
            return {"status": "missing_database_url"}

        try:
            import psycopg

            with psycopg.connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
            return {"status": "ok"}
        except Exception as exc:  # pragma: no cover - exercised in runtime health only.
            return {"status": "error", "detail": str(exc)}
