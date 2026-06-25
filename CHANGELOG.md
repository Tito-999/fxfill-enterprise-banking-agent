# Changelog

## v0.2.0 — Enterprise Core Upgrade (2026-06-25)

### Added
- **OIDC JWT verification** (`security/oidc.py`): JWKS fetch, kid lookup, signature validation, claim extraction
- **RBAC + ABAC authorization** (`security/authorization.py`): tenant-scoped policy, role-based access, composite policies
- **Environment modes** (`config.py`): Production safety guards, `validate_production()`
- **Health probes**: `/live`, `/ready`, `/health/deep`
- **Intent Router** (`routing/`): 13 intent categories, keyword classifier
- **Planner–Executor–Verifier** (`orchestration/`): structured plans, cycle-detection validator
- **RAG models** (`rag/`): versioned DocumentChunk, InMemoryRetriever, citations
- **Memory models** (`memory/`): ConversationSummary, UserPreference, InMemoryMemoryStore
- **Prompt Registry** (`prompt_registry.py`): versioned, hashed prompt templates
- **Model Router** (`model_router.py`): lightweight/standard/reasoning tiers
- **IAM** (`iam.py`): 7 roles, 15 permissions, Maker-Checker
- **Audit** (`audit/`): hash-chained events, evidence bundles
- **Governance** (`governance/`): AssetVersion, AgentReleaseManifest
- **AgentOps** (`agentops.py`): TrafficPolicy, WriteKillSwitch, DriftThreshold
- **AI Security** (`ai_security.py`): 8 attack categories, 8 red-team cases
- **Reliability** (`reliability.py`): SLOs, CircuitBreaker, reconciliation
- **CI/CD**: Security workflow (Gitleaks, CodeQL, SBOM), coverage threshold

### Changed
- **DeepSeek provider**: Switched from Anthropic to OpenAI-compatible API format
- **HITL**: Graph-level interrupt/resume replaces bypass-executor
- **Identity**: user_id server-injected from TrustedRequestContext, never from LLM
- **API**: Machine-readable error codes, no `detail=str(exc)`, prompt length validation
- **Checkpointer**: JsonPlusSerializer for LangChain messages, v6 migration

### Fixed
- Provider protocol mismatch (Anthropic request / OpenAI response)
- Checkpointer not bound to LangGraph compile
- HITL approval bypassing graph for execution
- user_id hardcoded as `"default"` in API and HITL sessions
- Live provider smoke test (DeepSeek v4 reasoning_content handling)

## v0.1.0 — Initial Release
- LangGraph ReAct agent with FastAPI
- Synthetic banking tools via MCP boundary
- SQLite-backed HITL, idempotency, events
- Deterministic authorization gateway
