"""RAG data models — documents, chunks, retrieval results, citations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class KnowledgeDomain(str, Enum):
    """Knowledge domains for RAG retrieval."""

    PRODUCTS_FEES = "products_fees"
    TRANSFER_RULES = "transfer_rules"
    KYC_AML = "kyc_aml"
    OPERATIONS_SOP = "operations_sop"
    FORM_GUIDANCE = "form_guidance"
    EXCEPTIONS = "exceptions"


@dataclass(frozen=True)
class DocumentChunk:
    """A chunk of a versioned knowledge document.

    Every chunk carries full metadata for citation and access control.
    """

    chunk_id: str
    document_id: str
    version: str
    title: str = ""
    content: str = ""
    source_uri: str = ""
    effective_from: str = ""
    effective_to: str = ""  # Empty = currently effective
    jurisdiction: str = ""
    product: str = ""
    access_roles: list[str] = field(default_factory=list)
    tenant_id: str = "default"
    classification: str = "internal"
    section_path: str = ""
    content_hash: str = ""
    domain: KnowledgeDomain = KnowledgeDomain.PRODUCTS_FEES

    @property
    def is_effective(self) -> bool:
        """True when this document version is currently in effect."""
        from datetime import datetime, timezone

        if self.effective_to:
            try:
                expiry = datetime.fromisoformat(self.effective_to)
                return datetime.now(timezone.utc) < expiry
            except ValueError:
                return True
        return True


@dataclass(frozen=True)
class Citation:
    """A citation linking a claim to a specific document chunk."""

    document_id: str
    title: str
    version: str
    section_path: str = ""
    source_uri: str = ""
    chunk_id: str = ""

    def to_text(self) -> str:
        """Format as a human-readable citation."""
        src = f" (source: {self.source_uri})" if self.source_uri else ""
        section = f", section {self.section_path}" if self.section_path else ""
        return f"[{self.title} v{self.version}{section}{src}]"


@dataclass(frozen=True)
class RetrievalResult:
    """Result of a RAG retrieval query.

    Attributes:
        query: The original search query.
        chunks: Retrieved document chunks, ranked by relevance.
        total_hits: Total number of matching documents.
        latency_ms: Retrieval latency.
    """

    query: str
    chunks: list[DocumentChunk] = field(default_factory=list)
    total_hits: int = 0
    latency_ms: float = 0.0

    @property
    def citations(self) -> list[Citation]:
        """Generate citations for all retrieved chunks."""
        return [
            Citation(
                document_id=c.document_id,
                title=c.title,
                version=c.version,
                section_path=c.section_path,
                source_uri=c.source_uri,
                chunk_id=c.chunk_id,
            )
            for c in self.chunks
        ]
