from pydantic import BaseModel, Field
from typing import Any, Dict


class HealthResponse(BaseModel):
    status: str
    documents: int
    embedding_model: str
    sports_analytics: Dict[str, Any] = Field(default_factory=dict)
