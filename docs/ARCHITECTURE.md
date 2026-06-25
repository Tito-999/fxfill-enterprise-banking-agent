# Architecture — FxFill Enterprise Banking Agent

## System Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Client / API Consumer                │
└─────────────────┬───────────────────────────────────────┘
                  │ HTTPS (Bearer Token or X-User-Id dev)
┌─────────────────▼───────────────────────────────────────┐
│              FastAPI (api.py)                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │  Auth    │ │Telemetry │ │  Rate    │ │    CORS    │  │
│  │Middleware │ │Middleware│ │  Limit   │ │ Middleware │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘  │
│  /live  /ready  /health  /health/deep                   │
│  /agent  /agent/approve  /v1/threads  /v1/audit/events │
└─────────────────┬───────────────────────────────────────┘
                  │ TrustedRequestContext
┌─────────────────▼───────────────────────────────────────┐
│              AgentRuntime (agent.py)                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐            │
│  │  Router  │ │  Model   │ │    Graph     │            │
│  │(13 intents)│ │  Router  │ │ (LangGraph)  │            │
│  └──────────┘ └──────────┘ └──────┬───────┘            │
│  DIRECT / RAG / PLANNER / TRANSFER / REJECT             │
└───────────────────────────────────┬─────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
┌─────────▼──────┐  ┌───────────────▼──────┐  ┌──────────────▼──┐
│  LLM Provider  │  │  Authorization Gateway│  │  Tool Registry  │
│  (DeepSeek)    │  │  RBAC + ABAC + Tenant │  │  (9 tools)      │
└────────┬───────┘  └───────────┬───────────┘  └────────┬─────────┘
         │                      │                        │
         │              ┌───────▼────────┐      ┌────────▼─────────┐
         │              │  HITL (Graph   │      │  MCP Client      │
         │              │  Interrupt)    │      │  Adapter         │
         │              └───────┬────────┘      └────────┬─────────┘
         │                      │                        │
         │              ┌───────▼────────┐      ┌────────▼─────────┐
         │              │  Approval      │      │  Banking         │
         │              │  Executor      │      │  MCPServer       │
         │              └───────┬────────┘      └────────┬─────────┘
         │                      │                        │
         └──────────────────────┼────────────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
    ┌─────────▼──────┐ ┌───────▼──────┐ ┌────────▼─────────┐
    │   PostgreSQL   │ │    Redis     │ │  Core Banking    │
    │ (authoritative)│ │ (coordination)│ │  Adapters       │
    └────────────────┘ └──────────────┘ └──────────────────┘
```

## Key Design Decisions

1. **LLM reasons, code decides.** The model suggests tool calls; deterministic code validates, authorizes, and executes.
2. **Single side-effect path.** All tool execution goes through: validate → authorize → HITL interrupt → execute → verify → resume.
3. **Identity from tokens, never from prompts.** TrustedRequestContext is immutable and populated by auth middleware.
4. **Tenant isolation at every layer.** API, authorization, database queries, and retrieval all enforce tenant scope.
5. **Fail closed.** Unknown outcomes never auto-retry. Missing dependencies refuse startup. Anonymous identity returns 401.

## Trust Boundaries

```
Untrusted:  User input, LLM output, RAG documents, HTTP body fields
Trusted:    Verified JWT claims, Auth middleware context, Config from env
```
