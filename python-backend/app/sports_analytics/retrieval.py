from __future__ import annotations

from app.search import HybridSearchEngine
from app.sports_analytics.knowledge import load_sports_documents, to_retrieval_records
from app.sports_analytics.models import RetrievedDocument, StructuredIntent
from app.sports_analytics.registry import RETRIEVAL_TRIGGER_TERMS


class SportsRetrievalService:
    def __init__(self, knowledge_dir: str, model_name: str) -> None:
        self.documents = load_sports_documents(knowledge_dir)
        records = to_retrieval_records(self.documents)
        self.engine = HybridSearchEngine(records, model_name=model_name)

    def should_retrieve(self, intent: StructuredIntent) -> bool:
        terms = set(intent.ambiguity_flags)
        normalized = intent.normalized_query
        has_trigger = any(term in normalized for term in RETRIEVAL_TRIGGER_TERMS)
        return has_trigger or "business_term" in terms or intent.confidence < 0.72

    def search(self, query: str, top_k: int = 4) -> list[RetrievedDocument]:
        results = self.engine.search(query, top_k=top_k)
        return [
            RetrievedDocument(
                id=result.id,
                title=result.title,
                content=result.content,
                source_type=result.sourceType,
                score=result.score,
                metadata=result.metadata,
            )
            for result in results
        ]
