"""Enterprise RAG — knowledge retrieval with versioning, permissions, and citations.

Documents are ingested with metadata (version, jurisdiction, ACL, content hash).
Retrieval respects tenant/user permissions. Every answer cites its sources
or explicitly states "no basis in knowledge base."

Anti-injection: Retrieved document text is always treated as untrusted data.
It never overrides system policy and never authorizes tool execution.
"""

from fxfill_banking_agent.rag.models import (
    Citation,
    DocumentChunk,
    KnowledgeDomain,
    RetrievalResult,
)

__all__ = [
    "DocumentChunk",
    "RetrievalResult",
    "Citation",
    "KnowledgeDomain",
]
