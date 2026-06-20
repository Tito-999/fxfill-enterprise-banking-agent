# Current Phase

Phase 0 — Project Contract and Reproducible Foundation

## Allowed Work

- Project specification and roadmap
- Architecture decision records
- Upstream commit verification
- Minimal Python package structure
- Configuration and evidence schemas
- Phase 0 unit tests
- Local development documentation

## Forbidden Work

- LangGraph runtime
- Real LLM calls
- MCP servers
- PostgreSQL or Redis
- Human approval workflow
- FastAPI or frontend
- Full benchmark execution
- Reading benchmark task answers or evaluation criteria
- Modifying the upstream repository

## Exit Criteria

Phase 0 is complete only when:

- pinned upstream verification passes;
- Phase 0 tests pass;
- Ruff passes;
- mypy passes;
- evaluation-integrity boundaries are documented;
- evidence is stored under reports/phases/phase-0/.
