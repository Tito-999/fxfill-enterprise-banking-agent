"""RAG retriever — lightweight hybrid retrieval for development.

Production should use pgvector + BM25 (Elasticsearch/OpenSearch).
This in-memory implementation supports local development and testing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fxfill_banking_agent.rag.models import (
    Citation,
    DocumentChunk,
    KnowledgeDomain,
    RetrievalResult,
)


@dataclass
class InMemoryRetriever:
    """In-memory keyword + simple vector retriever for development.

    Args:
        chunks: Pre-loaded document chunks.
    """

    _chunks: list[DocumentChunk] = field(default_factory=list)

    def index(self, chunks: list[DocumentChunk]) -> None:
        """Load chunks into the retriever."""
        self._chunks = list(chunks)

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        domain: KnowledgeDomain | None = None,
        tenant_id: str = "default",
        roles: list[str] | None = None,
    ) -> RetrievalResult:
        """Retrieve relevant chunks for a query.

        Uses keyword overlap scoring (TF-IDF-like). Production should
        use embedding similarity + BM25 hybrid.
        """
        import time

        t0 = time.monotonic()

        query_terms = set(query.lower().split())

        # Filter by domain, tenant, and access control
        candidates = [
            c
            for c in self._chunks
            if (domain is None or c.domain == domain)
            and c.tenant_id == tenant_id
            and c.is_effective
        ]

        # Score by keyword overlap
        scored: list[tuple[float, DocumentChunk]] = []
        for chunk in candidates:
            content_terms = set(chunk.content.lower().split())
            if not query_terms or not content_terms:
                score = 0.0
            else:
                overlap = query_terms & content_terms
                score = len(overlap) / len(query_terms)
            scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_chunks = [c for _, c in scored[:top_k]]

        return RetrievalResult(
            query=query,
            chunks=top_chunks,
            total_hits=len(scored),
            latency_ms=(time.monotonic() - t0) * 1000,
        )

    def get_citations(self, query: str, top_k: int = 5) -> list[Citation]:
        """Retrieve and return formatted citations."""
        result = self.retrieve(query, top_k=top_k)
        return result.citations
