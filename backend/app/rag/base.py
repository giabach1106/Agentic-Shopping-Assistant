from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class RetrievalDocument:
    doc_id: str
    source: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class Retriever(Protocol):
    async def search(self, query: str, top_k: int) -> list[RetrievalDocument]:
        """Return the most relevant documents for a query."""

