from __future__ import annotations

import json
from pathlib import Path

from langchain_core.documents import Document


def load_sports_documents(knowledge_dir: str) -> list[Document]:
    base = Path(knowledge_dir).resolve()
    documents: list[Document] = []

    for path in sorted(base.glob("*.json")):
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        for item in payload:
            documents.append(
                Document(
                    page_content=item["content"],
                    metadata={
                        "id": item["id"],
                        "title": item["title"],
                        "sourceType": item.get("sourceType", path.stem),
                        **item.get("metadata", {}),
                    },
                )
            )

    return documents


def to_retrieval_records(documents: list[Document]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for document in documents:
        records.append(
            {
                "id": str(document.metadata["id"]),
                "title": str(document.metadata["title"]),
                "content": document.page_content,
                "sourceType": str(document.metadata.get("sourceType", "knowledge")),
                "metadata": dict(document.metadata),
            }
        )
    return records
