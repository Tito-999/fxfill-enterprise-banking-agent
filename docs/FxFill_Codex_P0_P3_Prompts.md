# FxFill：Codex 执行 P0–P3 的提示词与实施流程

**目标仓库：** `Tito-999/fxfill-enterprise-banking-agent`  
**配套方案：** `docs/ENTERPRISE_AGENT_P0_P1_P2_PLAN.md`  
**建议新增：** `docs/ENTERPRISE_AGENT_P3_PLAN.md`  
**用途：** 直接复制给 Codex CLI、Codex App 或 VS Code Codex 执行。

---

# 1. 先说明 P3 的定义

原修改方案只有 P0、P1、P2。为了形成 P0–P3 的完整工程路线，本文件将 P3 定义为：

> **P3：AgentOps、持续评测、渐进式发布、成本治理、漂移监控和生产运营闭环。**

四个阶段的边界如下：

| 阶段 | 核心目标 |
|---|---|
| P0 | 主链正确：真实 Function Calling、持久化多轮、HITL 恢复、可信身份、事件/幂等/指标接通 |
| P1 | Agent 能力完整：Intent Router、Planner–Executor–Verifier、记忆、RAG、Prompt Registry、模型路由、评测 |
| P2 | 金融级生产化：PostgreSQL/Redis、IAM、多租户、真实 Adapter、Kubernetes、安全、审计、灾备、治理 |
| P3 | 生产运营闭环：在线评测、灰度发布、自动回滚、漂移监控、成本优化、持续红队与合规证据 |

**禁止把四个阶段放在一个 Codex 线程中一次性实施。**  
正确方式是：一个总规划线程，P0/P1/P2/P3 各一个独立 worktree 或分支；每个阶段内部再按子任务拆分提交。

---

# 2. 仓库中必须准备的文件

在启动 Codex 前，把以下文件放入仓库：

```text
AGENTS.md
docs/ENTERPRISE_AGENT_P0_P1_P2_PLAN.md
docs/ENTERPRISE_AGENT_P3_PLAN.md
docs/execution/
```

其中：

- `AGENTS.md`：永久工程规则；
- `ENTERPRISE_AGENT_P0_P1_P2_PLAN.md`：详细需求；
- `ENTERPRISE_AGENT_P3_PLAN.md`：P3 需求；
- `docs/execution/STATUS.md`：Codex 持续更新的任务状态；
- `docs/execution/DECISIONS.md`：架构决策和偏差；
- `docs/execution/TEST_EVIDENCE.md`：测试命令与结果。

---

# 3. 建议的 AGENTS.md

把下面内容保存到仓库根目录 `AGENTS.md`。

```markdown
# AGENTS.md — FxFill Engineering Rules

## Mission

Evolve this repository from a synthetic banking-agent reference implementation into a verifiable enterprise-oriented agent architecture, following:

- docs/ENTERPRISE_AGENT_P0_P1_P2_PLAN.md
- docs/ENTERPRISE_AGENT_P3_PLAN.md
- docs/execution/STATUS.md

The implementation must remain honest about what is local, synthetic, mocked, scaffolded, or actually verified.

## Repository constraints

- Python version: >=3.12,<3.14.
- Use `uv` for dependency management.
- Preserve existing package layout unless an approved refactor is necessary.
- Do not modify the pinned upstream tau benchmark repository.
- Do not inspect benchmark gold answers, private graders, reward internals, or evaluator implementation.
- Never commit API keys, access tokens, passwords, real banking data, customer PII, or production credentials.
- All banking data in this repository must remain synthetic unless an explicit secure adapter interface is being defined.
- Do not claim external deployment, certification, compliance approval, penetration testing, or benchmark success unless evidence exists.

## Security invariants

- LLM output is always untrusted.
- Prompt text is never an authorization mechanism.
- `user_id`, `tenant_id`, roles, account ownership, approval identity, and permissions must come from trusted request context, never model-generated tool arguments.
- Every side-effecting tool call must pass deterministic validation, authorization, exact-operation approval, idempotency, audit, and failure handling.
- Unknown or uncertain write outcomes fail closed and require reconciliation.
- Tool risk classification must come from explicit metadata, not tool-name substring matching.
- The approver must not be trusted from an HTTP body field.
- Do not weaken tests or security controls to make checks pass.

## Engineering rules

- Before editing, inspect the current implementation and tests.
- Prefer focused changes and backward-compatible migrations.
- Add or update tests with every behavior change.
- Use typed domain models and structured errors.
- Do not add broad `type: ignore`, disable strict checking globally, or suppress exceptions without justification.
- Do not silently replace real behavior with mocks.
- Live-provider tests may be opt-in, but the request construction and parser must have deterministic contract tests.
- Update documentation when public behavior, configuration, storage schema, API contracts, or architecture changes.
- Record significant design decisions in `docs/execution/DECISIONS.md`.

## Required checks

Run the relevant focused tests during development, then run all gates before completing a phase:

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Where Docker or infrastructure assets are added, also run their available validation commands.

## Execution discipline

- Work in the dependency order P0 -> P1 -> P2 -> P3.
- Do not begin the next phase until the current phase Definition of Done passes.
- Implement one numbered subtask at a time.
- After each subtask:
  1. run focused tests;
  2. inspect the diff;
  3. update `docs/execution/STATUS.md`;
  4. commit with a narrow message.
- Do not run two agents against the same files in parallel.
- When blocked by missing external credentials or services, implement an interface, local test double, configuration validation, and documentation. Mark the external validation as blocked; never fabricate a successful result.

## Completion report

At the end of every task, report:

1. files changed;
2. architecture decisions;
3. tests added;
4. commands run and exact outcomes;
5. unresolved risks;
6. next unchecked task;
7. whether the phase gate passes.
```

---

# 4. 第一个提示词：只做基线审计和执行计划

在新的 Codex 线程中先使用 `/plan`，然后粘贴：

```text
你现在是本仓库的 Principal Agent Engineer、金融系统安全工程师和测试负责人。

目标：
在不修改生产代码的前提下，对当前仓库进行完整基线审计，并形成 P0–P3 的可执行计划。不要直接开始实现。

必须读取：
- AGENTS.md
- README.md
- README.zh-CN.md
- SPEC.md
- ROADMAP.md
- AUDIT_REPORT.md
- reports/audit/known-gaps.json
- docs/ENTERPRISE_AGENT_P0_P1_P2_PLAN.md
- docs/ENTERPRISE_AGENT_P3_PLAN.md
- src/fxfill_banking_agent/
- tests/
- pyproject.toml

特别核验这些已知风险，不要默认文档描述正确：
1. Provider 是否真的把工具 schema 发送给真实模型；
2. Provider 请求协议和响应解析协议是否一致；
3. LangGraph compile 是否真正绑定 checkpointer；
4. 相同 thread_id 是否能跨 HTTP 请求和跨进程恢复历史；
5. bootstrap 创建的 checkpoint/event/idempotency/metrics 是否全部注入 AgentRuntime；
6. HITL 审批后是否恢复原图，而不是绕过图直接执行工具；
7. user_id、tenant_id、account ownership、approver identity 是否来自可信上下文；
8. 工具风险是否仍使用名称字符串猜测；
9. per-step metrics 是否实际记录；
10. benchmark runner 是否仍为 placeholder；
11. 当前测试是否用 Fake Provider 伪造了关键能力；
12. README 的每一项核心声明是否有自动测试证据。

你必须执行：
- 查看 git status 和当前分支；
- 运行当前基线测试、Ruff、format check、MyPy；
- 不要修改源码；
- 允许新增或更新以下规划文件：
  - docs/execution/BASELINE_AUDIT.md
  - docs/execution/P0_P3_EXECUTION_PLAN.md
  - docs/execution/STATUS.md
  - docs/execution/DECISIONS.md
  - docs/execution/TEST_EVIDENCE.md

执行计划必须为每个 P0/P1/P2/P3 子任务列出：
- 当前状态：absent / partial / wired-but-unused / implemented / externally-blocked；
- 证据文件和函数；
- 目标行为；
- 精确修改文件；
- 新增测试；
- 数据迁移；
- 安全风险；
- 向后兼容风险；
- 完成标准；
- 依赖关系；
- 建议 commit；
- 可否与其他任务并行。

约束：
- 不允许把“存在类或测试”直接判断为“主链已接通”；
- 不允许伪造测试结果；
- 不允许修改 upstream benchmark；
- 不允许在本任务中写实现代码；
- 发现计划与当前代码冲突时，记录在 DECISIONS.md；
- 如果发现比计划更严重的问题，将其列为 P0 blocker。

完成条件：
- 基线命令及结果已记录；
- P0–P3 依赖 DAG 已完成；
- 每个子任务都有可验证的 Definition of Done；
- 给出建议的分支/worktree 和 PR 拆分；
- 最后停止，不进入实现。
```

审计完成后，人工检查 `BASELINE_AUDIT.md`。只有审计可信时才执行 P0。

---

# 5. P0 实施提示词：主链正确性

新建分支或 worktree：

```text
codex/p0-runtime-correctness
```

新开一个 Codex 线程，粘贴：

```text
执行 P0：修复 FxFill Agent 主链正确性和真实可验证性。

必须先读取：
- AGENTS.md
- docs/ENTERPRISE_AGENT_P0_P1_P2_PLAN.md 的全部 P0 内容
- docs/execution/BASELINE_AUDIT.md
- docs/execution/P0_P3_EXECUTION_PLAN.md
- docs/execution/STATUS.md
- 当前相关源码和测试

工作范围：
P0-01 真实 Function Calling 主链
P0-02 LangGraph checkpointer 与持久化多轮会话
P0-03 Composition Root 和依赖注入
P0-04 Durable HITL interrupt/resume
P0-05 Trusted Identity Context
P0-06 显式 Tool Metadata 和风险分类
P0-07 Event、Metrics、Structured Error 主链接线
P0-08 类型检查、测试可信度和文档声明校正

执行方式：
1. 先核验当前 STATUS，跳过有充分证据且真正完成的项目；
2. 严格按 P0-01 到 P0-08 顺序；
3. 每次只实施一个编号项目；
4. 每个项目先写或修复能够暴露问题的测试，再修改实现；
5. 每个项目完成后运行 focused tests、ruff、mypy；
6. 更新 STATUS.md、DECISIONS.md、TEST_EVIDENCE.md；
7. 创建独立 commit，禁止把全部 P0 压成一个大提交；
8. 当前项目未通过前，不进入下一个项目；
9. 不进入 P1。

不可破坏的安全约束：
- 模型不得生成或覆盖可信 user_id、tenant_id、role、account ownership；
- 未知工具、非法参数、越权参数和 uncertain write outcome 必须 fail closed；
- Prompt 不能授权副作用；
- 工具参数必须经过 allowlist 和 schema validation；
- write tool 必须具有 durable idempotency；
- HITL grant 必须绑定 exact session/thread/user/tool/arguments/idempotency key；
- approver 不得来自不可信请求 body；
- 不得为了通过测试切回 AutoApprove；
- 不得通过扩大 mypy ignore 或删除测试掩盖问题。

P0-01 验收：
- Provider invoke 接口接受 typed tools；
- MCP tool definitions 被转换为准确的 Provider tools 格式；
- tools 确实存在于构造的请求体；
- 请求和响应适配器不混用不兼容协议；
- tool call name 和 args 有严格校验；
- 有 opt-in live tool-call smoke test；
- Fake transport 测试只证明协议，不作为真实模型能力证据。

P0-02 验收：
- graph compile 绑定实际 checkpointer；
- conversation_id、thread_id、run_id、session_id 语义清晰；
- 相同 thread_id 的第二轮只提交增量 HumanMessage；
- 新进程能恢复旧消息、step state 和 pending interrupt；
- 不同用户/tenant 不可读取他人 thread；
- 有真正跨 Runtime/跨进程恢复测试。

P0-03 验收：
- bootstrap 创建的 checkpointer、event store、idempotency store、metrics 和 auth context 全部注入唯一 Runtime；
- 不允许 API 隐式创建一个缺少持久化依赖的第二 Runtime；
- production_mode 对缺失依赖 fail fast；
- 生命周期负责关闭资源。

P0-04 验收：
- 使用 LangGraph durable interrupt/resume 或等价可证明机制；
- approve 后从原 checkpoint 继续；
- ToolMessage 回填原会话；
- 模型生成最终解释；
- reject、expired、duplicate approve、crash before/after dispatch、unknown outcome 都有测试；
- 不允许 approval endpoint 绕过 graph 形成第二套执行语义。

P0-05 验收：
- 定义 TrustedRequestContext；
- 身份来自认证中间件或开发环境签名 resolver；
- 模型工具 schema 不暴露可伪造的 trusted identity 字段；
- 工具执行前由服务端注入身份；
- 跨用户、跨账户、跨 tenant 测试通过。

P0-06 验收：
- ToolDefinition 显式包含 side_effect、risk_level、permissions、approval mode、timeout；
- 删除按工具名 substring 猜风险的生产路径；
- registry 是授权和 Provider schema 的单一事实源。

P0-07 验收：
- 每个 LLM step 和 tool step 有 duration、tokens、tool count、error kind；
- event store 实际收到 run lifecycle、tool lifecycle、approval lifecycle；
- API 返回稳定 machine-readable error code，不泄露内部异常或秘密；
- correlation_id/trace_id 贯穿请求。

P0-08 验收：
- 不得保留大范围 ignore_errors；
- 关键安全模块通过严格类型检查；
- 真实主链 E2E 测试存在；
- README 只保留有证据的声明；
- benchmark placeholder 被明确标记，不能宣称完成 benchmark。

P0 最终门禁：
```bash
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

最终输出：
- P0-01 至 P0-08 完成状态；
- commit 列表；
- 修改文件；
- 数据迁移；
- 测试证据；
- live provider 尚未运行时必须明确标记；
- 未解决 blocker；
- 判断 P0 gate 是 PASS 或 FAIL。

只有 P0 gate 为 PASS 时停止并建议进入 P1；不要自动开始 P1。
```

---

# 6. P0 独立复核提示词

P0 实施线程结束后，另开一个只做 review 的线程：

```text
对当前分支执行独立 P0 安全与正确性审查。不要默认实施线程的结论可信。

基准：
- AGENTS.md
- docs/ENTERPRISE_AGENT_P0_P1_P2_PLAN.md 的 P0
- docs/execution/BASELINE_AUDIT.md
- P0 分支相对 main 的完整 diff

重点寻找：
1. 类已创建但没有主链调用；
2. checkpointer 存在但 graph 未使用；
3. event/idempotency/metrics 存在但依赖未注入；
4. approve 后绕过 graph；
5. 模型仍可伪造身份字段；
6. schema validation 只写了类型但未执行；
7. async 并发竞态；
8. optimistic lock 版本错误；
9. duplicate side effect；
10. Fake 测试掩盖真实协议；
11. exception detail 泄漏；
12. README 过度宣传；
13. mypy ignore 扩大；
14. tests 只断言“不崩溃”而未断言正确行为。

执行：
- 运行全部测试和静态检查；
- 增加必要的 adversarial/regression tests；
- 对发现的缺陷直接修复；
- 更新 TEST_EVIDENCE.md；
- 输出 findings，按 Critical/High/Medium/Low 分类；
- 只有不存在 Critical/High 且全部门禁通过才给 PASS。
```

---

# 7. P1 实施提示词：完整 Agent 能力

分支或 worktree：

```text
codex/p1-agent-capabilities
```

前提：P0 已合并且 P0 gate 为 PASS。

```text
执行 P1：在已经通过 P0 的主链上增加企业级 Agent 应用能力。

必须读取：
- AGENTS.md
- docs/ENTERPRISE_AGENT_P0_P1_P2_PLAN.md 的 P1
- docs/execution/STATUS.md
- docs/execution/DECISIONS.md
- P0 测试和主链实现

工作范围：
P1-01 Intent Router 与 deterministic fast path
P1-02 Planner–Executor–Verifier
P1-03 Working/Summary/Semantic/Episodic Memory
P1-04 Enterprise RAG
P1-05 Prompt Registry
P1-06 Model Routing、Cache、Context/Cost Efficiency
P1-07 PostgreSQL、Redis 和并发控制
P1-08 OpenTelemetry、Evaluation Harness 和 CI Quality Gates

总体原则：
- 简单余额查询、状态查询等不得无条件走复杂 Planner；
- 写操作优先使用确定性 workflow，禁止自由 Agent 随意探索；
- Planner 只能提出 plan，不能授予权限；
- Verifier 不能用自然语言覆盖工具的确定性失败；
- memory 和 RAG 文本全部视为不可信数据；
- 不得把未经验证的检索文本当系统指令；
- 每个回答引用的知识必须可追踪到 document/version/chunk；
- 不存储不必要的 PII 或秘密；
- RAG 和长期记忆必须做 tenant/user permission filter；
- cache key 必须包含 tenant、permission scope、model/prompt/tool/knowledge version；
- 不允许用 Redis cache 绕过实时余额和交易状态工具。

P1-01：
- 定义 intent taxonomy；
- 实现规则/轻量模型路由接口；
- simple read 走 deterministic tool workflow；
- knowledge query 走 RAG；
- complex task 才走 Planner；
- high-risk intent 直接进入 policy validation；
- 路由可解释且有 confusion-matrix 测试集。

P1-02：
- AgentState 增加 typed plan、current step、dependencies、budget、retry/replan count；
- Planner 输出结构化 plan；
- Plan Validator 检查工具存在性、权限、数据依赖和禁止步骤；
- Executor 一次只执行一个批准步骤；
- Verifier 基于 typed result 和 invariants 判定；
- 限制最大 plan steps、replans、tool calls、tokens 和 wall time；
- 有 partial failure、compensation、timeout、dependency failure 测试。

P1-03：
- working memory 使用 checkpoint；
- conversation summary 有版本和覆盖范围；
- semantic memory 只保存允许持久化的信息；
- episodic memory 保存任务事件而非模型私有推理；
- 实现 TTL、删除、用户隔离、tenant 隔离、去重和数据最小化；
- 构建长对话压缩测试以及“删除后无法召回”测试。

P1-04：
- 建立 ingestion、chunking、embedding、metadata、retrieval、reranking、citation；
- 支持文档版本、生效日期、tenant、ACL、source URI、content hash；
- hybrid retrieval；
- retrieval output 只能放在明确的不可信上下文区；
- 防止 indirect prompt injection；
- 回答必须有 citation 或明确表示无依据；
- 构建 retrieval recall、groundedness、citation correctness、stale-policy 测试；
- 本地开发可用轻量向量实现，生产接口必须支持 pgvector 或可替换后端。

P1-05：
- Prompt 不散落在 Python 字符串；
- Prompt registry 包含 name、version、owner、purpose、input schema、output schema、hash；
- 运行事件记录 prompt version；
- 系统、安全、Planner、Verifier、RAG、Tool repair 分层；
- 有 snapshot/contract tests；
- Prompt 更新不得隐式改变授权语义。

P1-06：
- 按 intent/risk/complexity 做模型路由；
- small model/规则承担分类和抽取；
- stronger model 只用于复杂 plan/reasoning；
- http client 连接池复用；
- 并行仅用于无依赖且只读的工具；
- context compaction、token budget、semantic cache、tool cache 有明确安全边界；
- 输出 P50/P95 latency、token/task、cost/success 指标。

P1-07：
- 引入 storage abstractions；
- SQLite 保留为本地开发；
- PostgreSQL 迁移包含 Alembic 或等价机制；
- Redis 用于明确的短期协调，不作为金融事实源；
- 解决 concurrent approval、double dispatch、lease expiry、outbox、retry；
- 用数据库唯一约束保证幂等；
- Docker Compose 提供本地 PostgreSQL/Redis；
- 并发和迁移测试通过。

P1-08：
- 接入 OpenTelemetry trace/metrics/log correlation；
- span 覆盖 API、LLM、retrieval、planner、tool、authorization、HITL；
- secrets/PII redaction；
- 构建离线 eval dataset 和可重复 runner；
- 指标至少包括 task success、tool selection、arg accuracy、hallucinated tool、unauthorized action、duplicate side effect、groundedness、latency、tokens；
- benchmark 规则保持隔离；
- CI 对 pytest、ruff、format、mypy、migration、security/eval smoke 设置门禁。

实施纪律：
- 一次完成一个 P1 编号；
- 每项独立 commit；
- 当前编号测试通过后再继续；
- 不得把外部云服务“配置文件存在”写成“已上线”；
- 缺少 Provider/embedding/cloud credentials 时，完成 adapter、契约测试和本地替代，并标记 externally-blocked；
- 不进入 P2。

P1 完成条件：
- P0 全部回归测试通过；
- P1 新测试通过；
- 至少一条 complex multi-step task 被 Planner–Executor–Verifier 正确完成；
- 至少一条简单任务证明没有进入 Planner；
- 多轮记忆、权限过滤和删除测试通过；
- RAG 有引用并抵抗恶意文档指令；
- PostgreSQL/Redis 本地集成测试通过；
- telemetry 能看到完整 trace；
- eval runner 产生机器可读报告；
- 全部质量门禁通过。

结束时输出 P1 gate PASS/FAIL，不自动开始 P2。
```

---

# 8. P2 实施提示词：金融级生产化

分支或 worktree：

```text
codex/p2-financial-production
```

前提：P1 gate 为 PASS。

```text
执行 P2：把通过 P1 的 Agent 架构推进为可审查的金融级生产化代码库和部署资产。

注意：
Codex 可以实现代码、接口、配置、测试、IaC 和运行手册，但不能伪造：
- 已部署到真实云环境；
- 已通过银行安全审批；
- 已通过 SOC 2、PCI DSS、ISO 27001 或监管认证；
- 已接入真实核心银行；
- 已完成第三方渗透测试；
- 已达到真实生产 SLO。

所有外部依赖必须标记为 implemented-locally、integration-ready 或 externally-blocked。

必须读取：
- AGENTS.md
- docs/ENTERPRISE_AGENT_P0_P1_P2_PLAN.md 的 P2
- P0/P1 architecture decisions、status、test evidence
- 当前 deployment/storage/auth/tool adapter 实现

工作范围：
P2-01 服务边界、容器化和 Kubernetes
P2-02 OIDC/JWT、RBAC/ABAC、Maker-Checker、多租户
P2-03 真实 Core Banking/Compliance Adapter 接口
P2-04 数据安全、隐私、加密和最小化
P2-05 不可篡改审计和合规证据
P2-06 SLO、HA、DR、reconciliation 和 chaos tests
P2-07 AI 安全、Prompt Injection 和红队
P2-08 Model/Prompt/Knowledge/Agent Governance
P2-09 CI/CD、供应链安全和发布控制

P2-01：
- 明确 API、Agent Runtime、Tool Gateway、Approval、Knowledge、Worker 的服务边界；
- 避免为展示而过度拆微服务；
- 提供 production Dockerfile、non-root user、health/readiness、graceful shutdown；
- Kubernetes manifests 或 Helm chart 包含 resource requests/limits、PDB、HPA、NetworkPolicy、Secret references；
- 配置与 secret 分离；
- 本地和 CI 做 manifest lint、container scan 和 smoke tests。

P2-02：
- 实现 OIDC/JWT verification 抽象和本地测试 issuer；
- claims 映射到 TrustedRequestContext；
- RBAC + ABAC policy decision；
- tenant isolation 在 API、DB、cache、retrieval、audit 全链路强制；
- Maker-Checker：发起者不能审批自己的高风险操作；
- critical operation 可要求双人审批；
- token replay、expired token、wrong audience、cross-tenant、role escalation 测试。

P2-03：
- 定义 CoreBankingPort、PaymentsPort、AMLPort、SanctionsPort 等；
- Adapter 使用明确 timeout、retry、circuit breaker、idempotency、correlation ID；
- 不把外部 API error 转成成功；
- 支持 sandbox adapter 和 contract tests；
- secret 只从 secret provider；
- 没有真实 endpoint 时不得声称完成真实接入。

P2-04：
- 数据分类：public/internal/confidential/restricted；
- 字段级 redaction；
- encryption in transit/at rest 的配置接口和文档；
- secret manager adapter；
- audit 中不记录 raw token、完整账号、敏感 Prompt；
- retention、deletion、export、legal hold 接口；
- memory/RAG/trace 的 PII policy；
- 测试日志和错误响应不泄密。

P2-05：
- append-only audit event schema；
- hash chaining 或签名接口；
- actor、tenant、policy version、prompt/model/tool/knowledge version 全部记录；
- audit 查询有权限控制；
- approval 和 tool dispatch 形成完整 evidence chain；
- 生成 compliance evidence bundle；
- 明确哪些控制需要外部审计确认。

P2-06：
- 定义可测 SLI/SLO；
- health/readiness 不只返回进程存活；
- database/provider/tool outage 的 circuit breaker 和 degraded mode；
- backup/restore runbook；
- reconciliation worker；
- chaos tests：LLM timeout、DB disconnect、Redis loss、crash before/after write、duplicate message、approval race；
- RTO/RPO 仅在实际演练后才能声明。

P2-07：
- 构建攻击语料和 red-team harness；
- 覆盖 direct/indirect injection、tool exfiltration、identity spoofing、approval bypass、RAG poisoning、memory poisoning、DoS/loop；
- security policy deterministic；
- unsafe tool args 在模型外拦截；
- 产生机器可读安全评测报告和 regression threshold。

P2-08：
- registry 管理 model、prompt、tool、knowledge、policy、eval dataset；
- 每次 run 记录版本与 hash；
- 变更审批和 rollback；
- model fallback 不能降低安全策略；
- fine-tuning 只作为离线可选模块，不能取代实时工具、权限或 RAG；
- 提供 model card、prompt card、knowledge card、agent release manifest。

P2-09：
- GitHub Actions 或等价 CI；
- dependency pinning、SBOM、secret scan、SAST、dependency/container scan；
- migration check、IaC lint、unit/integration/security/eval gates；
- signed release/provenance 接口；
- branch protection 文档；
- canary/rollback pipeline scaffold；
- 禁止 CI 访问真实客户数据。

完成条件：
- 所有 P0/P1 回归通过；
- 本地 production-like stack 可启动；
- OIDC local issuer 和 tenant isolation 测试通过；
- sandbox banking adapter contract tests 通过；
- container/IaC/security scans 产生证据；
- chaos/recovery/security eval 通过门槛；
- governance manifest 能重建一次运行的版本组合；
- 外部验证项明确列出，不能伪造 PASS；
- P2 gate 输出 PASS/FAIL。

不要自动进入 P3。
```

---

# 9. P3 方案文件内容

把以下内容保存为 `docs/ENTERPRISE_AGENT_P3_PLAN.md`：

```markdown
# P3 — AgentOps and Continuous Production Improvement

## Goal

Build an evidence-driven operating loop for safe gradual rollout, online quality monitoring, cost control, drift detection, incident response, and continuous compliance.

## P3-01 AgentOps control plane

- Runtime configuration registry.
- Feature flags and kill switches.
- Tenant-specific safe configuration.
- Release manifest and immutable version bundle.
- Operator APIs must be authenticated and audited.
- No operator setting may bypass deterministic authorization.

## P3-02 Shadow, canary and staged rollout

- Offline -> shadow -> internal pilot -> limited canary -> broader rollout.
- Traffic allocation abstraction.
- Synthetic or consented traffic only in this repository.
- Compare candidate and baseline without executing candidate side effects.
- Automatic promotion is prohibited for high-risk policy changes.

## P3-03 Online evaluation and feedback

- Sample production-like traces with redaction.
- Human feedback taxonomy.
- Outcome-based task success signals.
- Groundedness and tool correctness monitors.
- Feedback data must be versioned, permissioned and removable.
- Do not train directly from raw feedback without review.

## P3-04 Drift and regression monitoring

- Intent distribution drift.
- Tool selection and argument error drift.
- Retrieval quality and knowledge freshness drift.
- Model/provider behavior drift.
- Policy rejection and HITL escalation drift.
- Thresholds trigger alert or rollback, not silent adaptation.

## P3-05 Cost, latency and capacity governance

- Cost per successful task.
- P50/P95/P99 end-to-end and component latency.
- Token budgets and tool budgets.
- Cache safety and hit rates.
- Capacity/load tests.
- Per-tenant quotas and rate limits.
- Cost optimization must not weaken security or factual freshness.

## P3-06 Incident response and automated rollback

- Incident severity taxonomy.
- Kill switch for write tools.
- Safe read-only degraded mode.
- Roll back model/prompt/tool/knowledge/policy version bundle.
- Reconciliation queue for uncertain writes.
- Incident evidence bundle and postmortem template.

## P3-07 Continuous red-team and compliance evidence

- Scheduled adversarial regression suite.
- New prompt/tool/knowledge/model version cannot release without security gates.
- Periodic access review evidence.
- Data retention/deletion evidence.
- No claim of compliance certification without external auditor confirmation.

## Definition of Done

- A candidate version can run in shadow mode without executing writes.
- Canary configuration and rollback are tested locally.
- Drift and quality thresholds produce alerts.
- A simulated incident activates write kill switch and rollback.
- Cost and latency dashboards use actual trace data.
- Red-team and compliance evidence bundles are generated automatically.
- External deployment and certification remain explicitly marked as external.
```

---

# 10. P3 实施提示词：AgentOps 和持续运营

分支或 worktree：

```text
codex/p3-agentops
```

前提：P2 gate 为 PASS。

```text
执行 P3：建立 AgentOps、持续评测、渐进式发布和生产运营闭环。

必须读取：
- AGENTS.md
- docs/ENTERPRISE_AGENT_P3_PLAN.md
- docs/execution/STATUS.md
- P0–P2 architecture decisions 和 test evidence

工作范围：
P3-01 AgentOps Control Plane
P3-02 Shadow/Canary/Staged Rollout
P3-03 Online Evaluation and Feedback
P3-04 Drift and Regression Monitoring
P3-05 Cost/Latency/Capacity Governance
P3-06 Incident Response and Automated Rollback
P3-07 Continuous Red-Team and Compliance Evidence

实施原则：
- 本仓库只使用 synthetic、sandbox 或明确允许的数据；
- shadow candidate 绝不能执行副作用；
- feature flag、operator API 和 kill switch 必须认证、授权和审计；
- 自动优化不得更改授权、身份、金额、工具风险或审批规则；
- high-risk policy/model release 需要人工 gate；
- 在线反馈不直接进入训练；
- drift 触发 alert、freeze、rollback 或人工检查，不允许静默自适应；
- 不伪造生产流量、云部署、监管批准或真实成本数据。

P3-01：
- 定义 immutable AgentReleaseManifest；
- 绑定 model、prompt、tool、knowledge、policy、retrieval、config、eval thresholds；
- 实现 authenticated operator control interface；
- feature flags 分 tenant 且有审计；
- global write kill switch 和 tenant write kill switch；
- 配置变更 optimistic concurrency 和 rollback。

P3-02：
- traffic policy abstraction；
- baseline/candidate；
- shadow path 屏蔽所有 writes；
- canary allocation 和 tenant allowlist；
- promotion checklist；
- 回滚到完整 version bundle；
- 测试 candidate 无法产生 side effect。

P3-03：
- 定义 feedback taxonomy 和 schema；
- trace sampling、redaction 和 consent/retention hooks；
- 在线指标：task outcome、tool correctness、argument validity、groundedness、approval rate；
- feedback review queue；
- data export/delete；
- 生成 evaluation dataset candidate，但必须人工审核后发布。

P3-04：
- 分布基线和时间窗口；
- intent/tool/error/retrieval/model/policy drift；
- knowledge freshness；
- threshold 和 alert routing；
- drift 不能修改生产模型；
- 构建 synthetic drift injection tests。

P3-05：
- per-component latency 和 cost attribution；
- cost per success；
- budget enforcement；
- per-tenant quota/rate limit；
- load test scenario；
- capacity report；
- cache 不能用于实时金融事实；
- 优化前后必须比较 task success 和 security regression。

P3-06：
- incident severity、owner、timeline、evidence；
- read-only degraded mode；
- write kill switch；
- release rollback；
- uncertain outcome reconciliation；
- simulated provider outage、DB outage、bad prompt release、RAG poisoning；
- postmortem template 和 automated evidence bundle。

P3-07：
- scheduled security/eval workflow；
- release gate 对 prompt/tool/model/knowledge/policy 变更生效；
- access review、retention、deletion、audit integrity evidence；
- 生成 control evidence index；
- 明确 external auditor required 项。

完成条件：
- 所有 P0–P2 回归通过；
- shadow candidate 不产生任何 write；
- canary 和 rollback 在本地集成环境演练通过；
- 模拟 drift 能触发预期 alert；
- 模拟事故能触发 write kill switch 和 rollback；
- cost/latency 指标来自真实测试 trace，不是硬编码；
- continuous red-team workflow 能阻止一个故意引入的安全回归；
- P3 gate PASS/FAIL；
- 输出仍需真实企业环境完成的外部项目。

不要声明系统已经在银行生产环境上线。
```

---

# 11. 长任务中断后的继续提示词

当 Codex 上下文压缩、线程中断或重新启动时，不要重新粘贴所有需求。使用：

```text
继续当前阶段的实施。

先读取：
- AGENTS.md
- docs/execution/STATUS.md
- docs/execution/DECISIONS.md
- docs/execution/TEST_EVIDENCE.md
- 当前分支最近 15 个 commits
- git status 和未提交 diff

规则：
- 不重复已完成且有测试证据的任务；
- 找到当前阶段第一个未完成或失败的编号；
- 检查前一编号的门禁确实通过；
- 从该编号继续；
- 一次只完成一个编号；
- 更新 STATUS、DECISIONS、TEST_EVIDENCE；
- 运行 focused tests 和阶段门禁；
- 不进入下一阶段。
```

---

# 12. 失败修复提示词

```text
当前阶段门禁失败。不要绕过、删除或弱化检查。

请：
1. 读取完整失败输出；
2. 区分 implementation defect、test defect、environment defect、external dependency；
3. 找到最小根因；
4. 增加能稳定复现根因的回归测试；
5. 修复实现；
6. 运行失败测试、相关测试和全量门禁；
7. 检查修复是否削弱授权、幂等、tenant isolation、HITL 或审计；
8. 更新 TEST_EVIDENCE.md；
9. 输出根因、修复、测试证据和残余风险。

禁止：
- 删除失败测试；
- 改宽断言；
- 增加 sleep 掩盖竞态；
- 全局关闭 mypy；
- 使用 broad exception swallow；
- 把真实 integration test 替换成 mock；
- 声称未运行的测试成功。
```

---

# 13. 最终 P0–P3 验收提示词

在全部阶段完成后，新开独立 review 线程：

```text
对 FxFill 执行最终 P0–P3 独立验收。以代码和可重复测试为证据，不以 README、STATUS 或此前 Agent 的自我报告为证据。

读取：
- AGENTS.md
- P0/P1/P2/P3 计划
- 全部 architecture decisions 和 test evidence
- main 到当前分支的完整 diff
- migrations、deployment、CI、eval 和 security assets

验收任务：
1. 建立 requirement-to-code-to-test traceability matrix；
2. 对每个子任务标记 PASS / PARTIAL / FAIL / EXTERNALLY_BLOCKED；
3. 运行所有可运行门禁；
4. 随机抽取关键声明，通过代码路径证明主链已接通；
5. 执行 adversarial tests；
6. 验证没有 mock-only success；
7. 验证 README 不超过实际能力；
8. 验证 secret、PII、tenant、auth、approval、idempotency 和 audit invariants；
9. 验证 migration rollback 和 clean install；
10. 验证 shadow candidate 无副作用、kill switch 和 rollback；
11. 生成 docs/execution/FINAL_ACCEPTANCE.md。

最终结论只能是：
- P0 PASS / PARTIAL / FAIL
- P1 PASS / PARTIAL / FAIL
- P2 PASS / PARTIAL / FAIL
- P3 PASS / PARTIAL / FAIL

单独列出：
- 可由仓库代码证明的能力；
- 需要 live provider 凭证验证的能力；
- 需要云环境验证的能力；
- 需要真实银行 sandbox 验证的能力；
- 需要第三方安全/合规审查的能力。

禁止使用“enterprise-ready”“production-ready”“bank-grade”作为无条件结论，除非所有对应证据真实存在。
```

---

# 14. 推荐运行方式

## Codex App / VS Code

1. 打开仓库根目录；
2. 确认 `AGENTS.md` 存在；
3. P0、P1、P2、P3 分别创建独立 thread 和 worktree；
4. 复杂阶段先使用 Plan mode；
5. 每个阶段结束后另开 review thread。

## Codex CLI

交互式、安全性较平衡的启动方式：

```bash
codex -C /path/to/fxfill-enterprise-banking-agent \
  -s workspace-write \
  -a on-request
```

在外部已经严格隔离、确认不含真实凭证和真实银行数据的自动化环境中，才考虑 `-a never`。不要使用 `--yolo` 或绕过 sandbox 的模式处理含凭证、真实数据或可访问生产系统的工作区。

验证 Codex 读取了仓库规则：

```bash
codex -C /path/to/fxfill-enterprise-banking-agent \
  -s read-only \
  -a never \
  "Summarize the active AGENTS.md instructions and list the required quality gates. Do not edit files."
```

---

# 15. 最重要的控制规则

1. **不要说“完成 P0–P3”，而要让 Codex 用测试逐项证明。**
2. **一个阶段一个 worktree；一个子任务一个 commit。**
3. **P0 不通过，绝对不要进入 P1。**
4. **真实 Function Calling 不能由 Fake JSON 证明。**
5. **持久化类存在，不代表 LangGraph 已使用它。**
6. **HITL 记录存在，不代表审批后恢复了原图。**
7. **部署清单存在，不代表已经部署。**
8. **合规控制代码存在，不代表已经通过合规认证。**
9. **让独立 Codex 线程审查实施线程。**
10. **外部阻塞必须明确标记，不能伪造成功。**
