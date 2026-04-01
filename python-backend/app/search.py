from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np

try:
    import faiss
except Exception:  # pragma: no cover - environment dependent.
    faiss = None

try:
    from rank_bm25 import BM25Okapi
except Exception:  # pragma: no cover - environment dependent.
    BM25Okapi = None

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - environment dependent.
    SentenceTransformer = None


@dataclass
class SearchItem:
    id: str
    title: str
    content: str
    sourceType: str
    score: float
    metadata: Dict[str, Any]


class HybridSearchEngine:
    def __init__(self, documents: List[Dict[str, Any]], model_name: str) -> None:
        self.documents = documents
        corpus = [f"{doc['title']}\n{doc['content']}" for doc in documents]
        self.corpus_tokens = [self._tokenize(text) for text in corpus]
        self.model = None
        self.embeddings = None
        self.index = None
        self.dense_available = False

        if SentenceTransformer is not None:
            try:
                self.model = SentenceTransformer(model_name)
            except Exception:  # pragma: no cover - environment dependent.
                self.model = None

        if self.model is not None and faiss is not None and corpus:
            try:
                embeddings = self.model.encode(corpus, convert_to_numpy=True, normalize_embeddings=True)
                self.embeddings = embeddings.astype(np.float32)

                self.index = faiss.IndexFlatIP(self.embeddings.shape[1])
                self.index.add(self.embeddings)
                self.dense_available = True
            except Exception:  # pragma: no cover - environment dependent.
                self.model = None
                self.embeddings = None
                self.index = None
                self.dense_available = False

        self.bm25 = BM25Okapi(self.corpus_tokens) if BM25Okapi is not None else None

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [token for token in ''.join(ch if ch.isalnum() else ' ' for ch in text.lower()).split() if len(token) > 1]

    @staticmethod
    def _normalize(scores: np.ndarray) -> np.ndarray:
        if scores.size == 0:
            return scores

        min_score = float(np.min(scores))
        max_score = float(np.max(scores))
        if max_score - min_score < 1e-9:
            return np.ones_like(scores)

        return (scores - min_score) / (max_score - min_score)

    def search(self, query: str, top_k: int = 5) -> List[SearchItem]:
        dense_scores = np.array([], dtype=np.float32)
        dense_indices = np.array([], dtype=np.int32)
        if self.model is not None and self.index is not None and self.dense_available:
            try:
                query_embedding = self.model.encode([query], convert_to_numpy=True, normalize_embeddings=True).astype(np.float32)
                dense_scores, dense_indices = self.index.search(query_embedding, min(top_k * 3, len(self.documents)))
                dense_scores = dense_scores[0]
                dense_indices = dense_indices[0]
            except Exception:  # pragma: no cover - environment dependent.
                self.model = None
                self.index = None
                self.dense_available = False
                dense_scores = np.array([], dtype=np.float32)
                dense_indices = np.array([], dtype=np.int32)

        if self.bm25 is not None:
            bm25_scores = np.array(self.bm25.get_scores(self._tokenize(query)), dtype=np.float32)
            normalized_bm25 = self._normalize(bm25_scores)
        else:
            tokenized_query = set(self._tokenize(query))
            bm25_scores = np.array(
                [float(len(tokenized_query.intersection(tokens))) for tokens in self.corpus_tokens],
                dtype=np.float32,
            )
            normalized_bm25 = self._normalize(bm25_scores)

        candidate_scores: Dict[int, float] = {}
        for rank, doc_index in enumerate(dense_indices):
            if doc_index < 0:
                continue
            dense_component = float(dense_scores[rank])
            sparse_component = float(normalized_bm25[doc_index])
            candidate_scores[doc_index] = max(candidate_scores.get(doc_index, 0.0), 0.7 * dense_component + 0.3 * sparse_component)

        if not candidate_scores:
            fallback_indices = np.argsort(-bm25_scores)[: max(top_k, 3)]
            for doc_index in fallback_indices:
                candidate_scores[int(doc_index)] = float(normalized_bm25[int(doc_index)])

        ranked = sorted(candidate_scores.items(), key=lambda item: item[1], reverse=True)[:top_k]

        results: List[SearchItem] = []
        for doc_index, score in ranked:
            document = self.documents[doc_index]
            results.append(
                SearchItem(
                    id=document['id'],
                    title=document['title'],
                    content=document['content'],
                    sourceType=document['sourceType'],
                    score=round(float(score), 4),
                    metadata=document.get('metadata', {}),
                )
            )

        return results
