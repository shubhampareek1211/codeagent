from pydantic import BaseModel, Field
from typing import Any, Dict, List


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2)
    top_k: int = Field(default=5, ge=1, le=12)


class SearchResult(BaseModel):
    id: str
    title: str
    content: str
    sourceType: str
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    results: List[SearchResult]


class HealthResponse(BaseModel):
    status: str
    documents: int
    embedding_model: str
    sports_analytics: Dict[str, Any] = Field(default_factory=dict)
