from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models import HealthResponse
from app.sports_analytics.models import (
    IntentDebugResponse,
    MetricsResponse,
    QueryResponse,
    RetrievalDebugResponse,
    SchemaResponse,
    SportsQueryRequest,
    SqlDebugResponse,
)
from app.sports_analytics.repository import SportsAnalyticsRepository
from app.sports_analytics.retrieval import SportsRetrievalService
from app.sports_analytics.service import SportsAnalyticsService

app = FastAPI(title="Sports Analytics Backend", version="0.1.0")

origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

analytics_service: Optional[SportsAnalyticsService] = None


def build_analytics_service() -> SportsAnalyticsService:
    repository = SportsAnalyticsRepository(settings.database_url or settings.sports_database_url)
    if settings.sports_auto_bootstrap:
        repository.bootstrap(settings.sports_schema_sql_path, settings.sports_seed_sql_path)

    retrieval_service = SportsRetrievalService(
        knowledge_dir=settings.sports_knowledge_dir,
        model_name=settings.embedding_model,
    )
    return SportsAnalyticsService(
        repository=repository,
        retrieval_service=retrieval_service,
        default_limit=settings.sports_default_limit,
    )


@app.on_event("startup")
def startup_event() -> None:
    global analytics_service
    analytics_service = build_analytics_service()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    if analytics_service is None:
        return HealthResponse(
            status="initializing",
            documents=0,
            embedding_model=settings.embedding_model,
            sports_analytics={"status": "initializing"},
        )

    return HealthResponse(
        status="ok",
        documents=len(analytics_service.retrieval_service.documents),
        embedding_model=settings.embedding_model,
        sports_analytics=analytics_service.health_summary(),
    )


@app.post("/query", response_model=QueryResponse)
def query(payload: SportsQueryRequest) -> QueryResponse:
    if analytics_service is None:
        raise HTTPException(status_code=503, detail="Sports analytics service is not ready yet.")
    return analytics_service.query(payload)


@app.get("/metrics", response_model=MetricsResponse)
def metrics() -> MetricsResponse:
    if analytics_service is None:
        raise HTTPException(status_code=503, detail="Sports analytics service is not ready yet.")
    return analytics_service.metrics_catalog()


@app.get("/schema", response_model=SchemaResponse)
def schema() -> SchemaResponse:
    if analytics_service is None:
        raise HTTPException(status_code=503, detail="Sports analytics service is not ready yet.")
    return analytics_service.schema_summary()


@app.post("/retrieval/debug", response_model=RetrievalDebugResponse)
def retrieval_debug(payload: SportsQueryRequest) -> RetrievalDebugResponse:
    if analytics_service is None:
        raise HTTPException(status_code=503, detail="Sports analytics service is not ready yet.")
    return analytics_service.debug_retrieval(payload)


@app.post("/intent/debug", response_model=IntentDebugResponse)
def intent_debug(payload: SportsQueryRequest) -> IntentDebugResponse:
    if analytics_service is None:
        raise HTTPException(status_code=503, detail="Sports analytics service is not ready yet.")
    return analytics_service.debug_intent(payload)


@app.post("/sql/debug", response_model=SqlDebugResponse)
def sql_debug(payload: SportsQueryRequest) -> SqlDebugResponse:
    if analytics_service is None:
        raise HTTPException(status_code=503, detail="Sports analytics service is not ready yet.")
    return analytics_service.debug_sql(payload)
