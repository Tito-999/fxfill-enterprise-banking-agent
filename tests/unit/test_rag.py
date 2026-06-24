"""Unit tests for RAG models and retriever."""

from __future__ import annotations

from fxfill_banking_agent.rag.models import (
    Citation,
    DocumentChunk,
    KnowledgeDomain,
    RetrievalResult,
)
from fxfill_banking_agent.rag.retriever import InMemoryRetriever


class TestDocumentChunk:
    def test_chunk_creation(self) -> None:
        chunk = DocumentChunk(
            chunk_id="c1",
            document_id="doc-1",
            version="1.0",
            title="Wire Transfer Fees",
            content="Domestic wire transfers cost $25. International wires cost $45.",
            source_uri="https://bank.example.com/fees",
            domain=KnowledgeDomain.PRODUCTS_FEES,
        )
        assert chunk.is_effective
        assert chunk.title == "Wire Transfer Fees"

    def test_expired_chunk(self) -> None:
        past_date = "2020-01-01T00:00:00+00:00"
        chunk = DocumentChunk(
            chunk_id="c1",
            document_id="doc-1",
            version="1.0",
            effective_to=past_date,
        )
        assert not chunk.is_effective


class TestCitation:
    def test_citation_format(self) -> None:
        c = Citation(
            document_id="doc-1",
            title="Fee Schedule",
            version="2.0",
            section_path="section 3.1",
            source_uri="https://bank.example.com/fees",
        )
        text = c.to_text()
        assert "Fee Schedule" in text
        assert "v2.0" in text
        assert "section 3.1" in text


class TestRetrievalResult:
    def test_empty_result(self) -> None:
        result = RetrievalResult(query="test query")
        assert result.total_hits == 0
        assert result.citations == []

    def test_citations_from_chunks(self) -> None:
        chunks = [
            DocumentChunk(chunk_id="c1", document_id="doc-1", version="1.0", title="Doc One"),
            DocumentChunk(chunk_id="c2", document_id="doc-2", version="2.0", title="Doc Two"),
        ]
        result = RetrievalResult(query="test", chunks=chunks, total_hits=2)
        assert len(result.citations) == 2
        assert result.citations[0].title == "Doc One"


class TestInMemoryRetriever:
    def _make_chunks(self) -> list[DocumentChunk]:
        return [
            DocumentChunk(
                chunk_id="c1",
                document_id="doc-1",
                version="1.0",
                title="Wire Transfer Fees",
                content="Domestic wire transfers cost $25 per transaction.",
                domain=KnowledgeDomain.PRODUCTS_FEES,
            ),
            DocumentChunk(
                chunk_id="c2",
                document_id="doc-2",
                version="1.0",
                title="Account Opening",
                content="New accounts require government ID and proof of address.",
                domain=KnowledgeDomain.PRODUCTS_FEES,
            ),
            DocumentChunk(
                chunk_id="c3",
                document_id="doc-3",
                version="1.0",
                title="KYC Requirements",
                content="All customers must complete KYC verification.",
                domain=KnowledgeDomain.KYC_AML,
            ),
        ]

    def test_retrieve_by_keyword(self) -> None:
        retriever = InMemoryRetriever()
        retriever.index(self._make_chunks())
        result = retriever.retrieve("wire transfer fees")
        assert result.total_hits > 0
        assert any("wire" in c.content.lower() for c in result.chunks)

    def test_retrieve_by_domain(self) -> None:
        retriever = InMemoryRetriever()
        retriever.index(self._make_chunks())
        result = retriever.retrieve("requirements", domain=KnowledgeDomain.KYC_AML)
        assert result.total_hits == 1
        assert result.chunks[0].document_id == "doc-3"

    def test_empty_retriever(self) -> None:
        retriever = InMemoryRetriever()
        result = retriever.retrieve("anything")
        assert result.total_hits == 0
        assert result.chunks == []

    def test_tenant_isolation(self) -> None:
        retriever = InMemoryRetriever()
        chunks = [
            DocumentChunk(
                chunk_id="c1", document_id="d1", version="1.0", content="t1 doc", tenant_id="t1"
            ),
            DocumentChunk(
                chunk_id="c2", document_id="d2", version="1.0", content="t2 doc", tenant_id="t2"
            ),
        ]
        retriever.index(chunks)
        result = retriever.retrieve("doc", tenant_id="t1")
        assert result.total_hits == 1
        assert result.chunks[0].tenant_id == "t1"

    def test_get_citations(self) -> None:
        retriever = InMemoryRetriever()
        retriever.index(self._make_chunks())
        citations = retriever.get_citations("wire fees")
        assert len(citations) > 0
        assert all(isinstance(c, Citation) for c in citations)
