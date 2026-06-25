# FxFill 企业级升级：三大核心改造实施方案

**目标仓库：** `Tito-999/fxfill-enterprise-banking-agent`  
**目标定位：** 从 enterprise-oriented reference implementation 升级为可信的 production-like banking agent prototype  
**实施原则：** 严格按依赖顺序执行；每一步先写失败测试，再改实现；每个阶段通过门禁后再进入下一阶段。

---

## 0. 总体修改顺序

```text
阶段 0：基线冻结与工程约束
  ↓
阶段 1：生产级身份、权限与 HITL 治理
  ↓
阶段 2：PostgreSQL / Redis 权威存储与分布式可靠性
  ↓
阶段 3：AgentOps、可观测性、审计与 CI/CD 门禁
  ↓
阶段 4：文档、发布与最终验收
```

三个核心方面的依赖关系：

```text
身份与权限治理
  └─ 提供可信 subject / tenant / role / scope
      └─ 绑定 HITL、Grant、Idempotency、Audit
          └─ 持久化到 PostgreSQL
              └─ Redis 负责分布式协调
                  └─ OpenTelemetry / Audit / CI 提供可运行证据
```

不得跳过阶段 1 直接做分布式存储，也不得在阶段 2 未完成时宣称 Kubernetes 多副本安全。

---

# 阶段 0：基线冻结与工程约束

## 0.1 创建升级分支

推荐分支：

```bash
git checkout main
git pull
git checkout -b enterprise/core-upgrade
```

也可以拆成三个独立分支：

```text
enterprise/auth-governance
enterprise/distributed-state
enterprise/agentops
```

后一个分支必须基于前一个已通过门禁的提交。

## 0.2 冻结当前基线证据

执行：

```bash
uv sync --group dev
uv run pytest
uv run pytest -q --cov=src --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy src
git diff --check
```

记录到：

```text
docs/execution/TEST_EVIDENCE.md
docs/execution/STATUS.md
```

当前基线应记录：

```text
384 passed, 1 skipped
68% line coverage
Ruff passed
Format check passed
Configured MyPy scope passed
Docker Compose smoke test passed
```

## 0.3 明确环境模式

修改：

```text
src/fxfill_banking_agent/config.py
.env.example
compose.yaml
docs/runtime-setup.md
```

新增或标准化配置：

```text
FXFILL_ENV=development|test|production
FXFILL_ALLOW_DEV_HEADERS=false
OIDC_ISSUER=
OIDC_AUDIENCE=
OIDC_JWKS_URL=
OIDC_JWKS_CACHE_TTL_SECONDS=300
DATABASE_URL=
REDIS_URL=
CORS_ALLOWED_ORIGINS=
REQUEST_TIMEOUT_SECONDS=30
PROVIDER_TIMEOUT_SECONDS=120
MAX_REQUEST_BODY_BYTES=
MAX_PROMPT_CHARS=
```

生产模式必须 fail fast：

```text
缺少 OIDC 配置 → 拒绝启动
缺少 PostgreSQL → 拒绝启动
缺少 Redis → 拒绝启动
启用开发身份 Header → 拒绝启动
使用 SQLite → 拒绝启动
CORS 使用通配符 → 拒绝启动
```

### 完成标准

- [ ] 环境模式只有一个事实源；
- [ ] production 配置缺失时启动失败；
- [ ] `.env.example` 中只有占位符；
- [ ] 当前测试不回退。

### 建议提交

```text
chore(config): define strict runtime environment modes
```

---

# 阶段 1：生产级身份、权限与 HITL 治理

这是优先级最高的阶段。完成之前，不进入数据库分布式迁移。

---

## 1.1 定义统一可信身份模型

### 目标

所有身份和权限信息只能来自经过验证的认证结果，不得来自：

```text
Prompt
HTTP body
LLM tool arguments
客户端自报 approver
默认硬编码 user_id
```

### 修改文件

```text
src/fxfill_banking_agent/security/context.py
src/fxfill_banking_agent/auth_middleware.py
src/fxfill_banking_agent/auth.py
src/fxfill_banking_agent/config.py
```

### 推荐模型

```python
@dataclass(frozen=True)
class TrustedRequestContext:
    subject_id: str
    tenant_id: str
    roles: frozenset[str]
    scopes: frozenset[str]
    auth_session_id: str
    token_id: str
    issuer: str
    request_id: str
    source: str
```

要求：

- `subject_id` 不能为空；
- `tenant_id` 不能为空；
- 不允许通过 LLM 修改；
- 在一次请求内不可变；
- 可序列化，但不能把完整 Token 写入日志或数据库。

### 新增测试

```text
tests/security/test_trusted_context.py
tests/security/test_identity_immutability.py
tests/security/test_body_identity_rejection.py
```

### 完成标准

- [ ] 请求体中的 `user_id`、`tenant_id`、`roles` 无效；
- [ ] LLM 返回的身份字段被丢弃或覆盖；
- [ ] context 为 immutable；
- [ ] 日志不记录 Bearer Token。

### 建议提交

```text
feat(security): define immutable trusted identity context
```

---

## 1.2 实现真实 OIDC / JWT 验证

### 目标

替换当前生产模式中的认证 scaffold。

### 推荐新增文件

```text
src/fxfill_banking_agent/security/oidc.py
src/fxfill_banking_agent/security/jwks_cache.py
src/fxfill_banking_agent/security/token_claims.py
```

### 需要实现

1. 解析 `Authorization: Bearer <token>`；
2. 读取 OIDC discovery 或配置的 JWKS URL；
3. 根据 `kid` 选择公钥；
4. 验证签名；
5. 校验：
   - `iss`
   - `aud`
   - `exp`
   - `nbf`
   - `iat`
6. 提取：
   - `sub`
   - `tenant_id`
   - `roles`
   - `scope`
   - `jti`
   - `sid`
7. JWKS 缓存与轮换；
8. 网络失败时 fail closed；
9. 不向客户端返回 Token 验证内部细节。

### 推荐依赖

选择一种：

```text
PyJWT + cryptography
python-jose
Authlib
```

优先选择维护稳定、支持 JWKS 和严格算法白名单的方案。

### 安全约束

```text
禁止 alg=none
禁止从 Token Header 动态接受任意算法
算法白名单固定为 RS256 / ES256 等
禁止把验证失败原因完整返回客户端
禁止自动信任缺少 tenant 的 Token
```

### 新增测试

```text
tests/security/test_oidc_authentication.py
tests/security/test_jwks_rotation.py
tests/security/test_token_claim_validation.py
```

必须覆盖：

```text
合法 Token
过期 Token
尚未生效 Token
错误 issuer
错误 audience
未知 kid
错误签名
缺少 subject
缺少 tenant
篡改 payload
alg=none
JWKS 临时不可用
```

### 完成标准

- [ ] 伪造 Token 返回 401；
- [ ] 合法 Token 创建正确 TrustedRequestContext；
- [ ] production 不接受 `X-User-Id`；
- [ ] JWKS 轮换测试通过；
- [ ] Token 不进入日志。

### 建议提交

```text
feat(auth): implement verified OIDC JWT authentication
```

---

## 1.3 实现 RBAC + ABAC 多租户授权

### 目标

把当前账户所有权校验升级为统一企业授权模型。

### 修改文件

```text
src/fxfill_banking_agent/auth.py
src/fxfill_banking_agent/security/authorization.py
src/fxfill_banking_agent/banking/repository.py
src/fxfill_banking_agent/tools/registry.py
src/fxfill_banking_agent/graph.py
src/fxfill_banking_agent/agent.py
```

### 推荐授权输入

```text
subject_id
tenant_id
roles
scopes
resource_type
resource_id
action
ownership
tool risk_level
side_effect
approval_policy
```

### 推荐策略层

```python
class AuthorizationPolicy(Protocol):
    async def authorize(
        self,
        context: TrustedRequestContext,
        operation: Operation,
        resource: ResourceAttributes,
    ) -> AuthorizationDecision:
        ...
```

### 数据隔离要求

所有持久化查询必须包含 tenant 范围：

```sql
WHERE tenant_id = :tenant_id
```

不能只依赖 API 层提前检查。

### 新增测试

```text
tests/security/test_rbac_policy.py
tests/security/test_abac_policy.py
tests/security/test_tenant_isolation.py
tests/security/test_cross_thread_isolation.py
tests/security/test_cross_grant_isolation.py
```

### 完成标准

- [ ] customer 不能执行 admin 操作；
- [ ] 没有 scope 的用户不能调用对应工具；
- [ ] tenant A 无法读取 tenant B 的账户、thread、HITL、grant；
- [ ] 所有 repository 查询都带 tenant；
- [ ] 拒绝结果包含稳定 error code，不泄露资源是否存在。

### 建议提交

```text
feat(authz): enforce tenant-scoped RBAC and ABAC policies
```

---

## 1.4 统一 HITL、Grant 与副作用执行主链

### 目标

消除 Graph Resume 与 Approval Executor 的平行执行语义，确保副作用只有一条执行路径。

### 目标主链

```text
LLM proposes action
→ tool schema validation
→ tenant / ownership authorization
→ risk classification
→ durable graph interrupt
→ create HITL session
→ authenticated approver decision
→ exact grant validation
→ idempotency claim
→ tool execution
→ durable result
→ reconciliation if unknown
→ graph resume
→ final model response
```

### 修改文件

```text
src/fxfill_banking_agent/graph.py
src/fxfill_banking_agent/agent.py
src/fxfill_banking_agent/api.py
src/fxfill_banking_agent/hitl_store.py
src/fxfill_banking_agent/grant_repo.py
src/fxfill_banking_agent/approval_executor.py
src/fxfill_banking_agent/resume_service.py
src/fxfill_banking_agent/idempotency_store.py
src/fxfill_banking_agent/actor_resolver.py
```

### 必须删除或替换

```text
user_id="default"
tenant_id="default" 作为生产审批身份
从 HTTP body 信任 approver
审批后绕过 graph 直接调用 MCP
审批参数与最终参数不一致
重复审批再次执行副作用
```

### HITL Session 必须绑定

```text
tenant_id
subject_id
request_id
session_id
thread_id
run_id
tool_call_id
tool_name
canonical_arguments
arguments_digest
idempotency_key
risk_level
required_role
created_at
expires_at
status
```

### Approval Grant 必须绑定

```text
grant_id
tenant_id
requesting_subject_id
approver_subject_id
tool_name
arguments_digest
idempotency_key
issued_at
expires_at
consumed_at
single_use=true
```

### 新增测试

```text
tests/security/test_hitl_identity_binding.py
tests/security/test_exact_operation_grant.py
tests/e2e/test_hitl_graph_resume.py
tests/recovery/test_hitl_crash_recovery.py
tests/concurrency/test_duplicate_approval.py
```

必须覆盖：

```text
审批参数被修改
审批过期
审批被撤销
重复审批
错误 tenant 审批
错误角色审批
服务在审批前重启
服务在执行后、响应前崩溃
未知执行结果
```

### 完成标准

- [ ] 所有副作用都通过同一执行路径；
- [ ] HITL 记录无默认身份；
- [ ] Grant 与 exact operation 绑定；
- [ ] duplicate approval 只执行一次；
- [ ] crash recovery 可恢复原 checkpoint；
- [ ] UNKNOWN 状态不会自动重试。

### 建议提交

```text
refactor(hitl): unify approval and graph resume execution
```

---

## 1.5 阶段 1 安全门禁

运行：

```bash
uv run pytest tests/security -q
uv run pytest tests/e2e/test_hitl_graph_resume.py -q
uv run pytest tests/recovery -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

阶段 1 通过条件：

```text
生产 OIDC/JWT 真实验证完成
开发 Header 在 production 被禁用
跨 tenant 访问为 0
Prompt 身份伪造为 0
HITL 无默认身份
副作用只有一条主链
重复审批执行次数 = 1
```

更新：

```text
docs/execution/STATUS.md
docs/execution/TEST_EVIDENCE.md
docs/execution/DECISIONS.md
```

---

# 阶段 2：PostgreSQL / Redis 权威存储与分布式可靠性

阶段 1 通过后开始。

---

## 2.1 定义存储接口和运行时后端选择

### 目标

业务代码依赖 Protocol，不直接依赖 SQLite 或 PostgreSQL 实现。

### 修改或新增

```text
src/fxfill_banking_agent/storage.py
src/fxfill_banking_agent/postgres_backend.py
src/fxfill_banking_agent/runtime_factory.py
src/fxfill_banking_agent/bootstrap.py
```

推荐新增：

```text
src/fxfill_banking_agent/storage/interfaces.py
src/fxfill_banking_agent/storage/sqlite.py
src/fxfill_banking_agent/storage/postgres.py
src/fxfill_banking_agent/storage/redis.py
```

### 需要统一的接口

```text
CheckpointStore
ConversationStore
HITLStore
GrantStore
IdempotencyStore
EventStore
AuditStore
ReconciliationStore
RateLimitStore
DistributedLock
```

### 环境行为

```text
development → SQLite 可选
test → SQLite / ephemeral PostgreSQL
production → PostgreSQL + Redis 强制
```

### 完成标准

- [ ] 业务层不判断数据库类型；
- [ ] production 无法回退 SQLite；
- [ ] 后端选择由 composition root 控制。

### 建议提交

```text
refactor(storage): define backend-neutral persistence interfaces
```

---

## 2.2 建立 PostgreSQL Schema 与迁移

### 推荐依赖

```text
SQLAlchemy 2 async + asyncpg + Alembic
```

或使用纯 asyncpg，但必须有正式 migration 机制。

### 需要迁移的数据表

```text
tenants
subjects
conversations
threads
checkpoints
hitl_sessions
approval_grants
idempotency_records
tool_executions
events
audit_events
reconciliation_jobs
schema_version
```

### 每张业务表至少包含

```text
id
tenant_id
created_at
updated_at
version
```

关键约束：

```sql
UNIQUE (tenant_id, idempotency_key)
UNIQUE (tenant_id, session_id)
UNIQUE (tenant_id, thread_id)
UNIQUE (tenant_id, grant_id)
```

### 修改文件

```text
src/fxfill_banking_agent/postgres_backend.py
src/fxfill_banking_agent/checkpoint_store.py
src/fxfill_banking_agent/hitl_store.py
src/fxfill_banking_agent/grant_repo.py
src/fxfill_banking_agent/idempotency_store.py
src/fxfill_banking_agent/persistence.py
src/fxfill_banking_agent/conversation_service.py
src/fxfill_banking_agent/bootstrap.py
pyproject.toml
compose.yaml
```

新增：

```text
alembic.ini
migrations/env.py
migrations/versions/*.py
```

### 新增测试

```text
tests/integration/test_postgres_runtime.py
tests/integration/test_postgres_repositories.py
tests/recovery/test_postgres_migrations.py
tests/security/test_postgres_tenant_isolation.py
```

### 完成标准

- [ ] 全新数据库可一键升级；
- [ ] 旧版本数据库可升级；
- [ ] tenant 约束生效；
- [ ] 幂等唯一约束生效；
- [ ] migration 失败不会静默启动；
- [ ] production 主链不再写 SQLite。

### 建议提交

```text
feat(storage): make PostgreSQL the authoritative durable store
```

---

## 2.3 接入 Redis 分布式协调

### Redis 职责

```text
分布式限流
分布式锁
短期缓存
Provider 熔断状态
多实例协调
可选短期 session
```

### 修改文件

```text
src/fxfill_banking_agent/api.py
src/fxfill_banking_agent/reliability.py
src/fxfill_banking_agent/model_router.py
src/fxfill_banking_agent/bootstrap.py
src/fxfill_banking_agent/runtime_factory.py
compose.yaml
pyproject.toml
```

推荐新增：

```text
src/fxfill_banking_agent/redis_backend.py
src/fxfill_banking_agent/rate_limit_store.py
src/fxfill_banking_agent/distributed_lock.py
```

### 限流键

```text
tenant_id + subject_id + endpoint
```

不能只使用 tenant 或 IP。

### 分布式锁键

```text
tenant_id + idempotency_key
```

Redis 锁不能替代 PostgreSQL 唯一约束，只作为降低竞争的协调层。

### 新增测试

```text
tests/integration/test_redis_rate_limit.py
tests/integration/test_redis_lock.py
tests/concurrency/test_multi_instance_locking.py
tests/recovery/test_redis_outage.py
```

### 完成标准

- [ ] 两个 Agent 实例共享限流；
- [ ] 两个实例争抢同一幂等键只允许一个执行；
- [ ] Redis 故障时副作用 fail closed；
- [ ] Redis 恢复后系统可继续工作。

### 建议提交

```text
feat(redis): add distributed rate limiting and coordination
```

---

## 2.4 实现严格幂等状态机

### 状态机

```text
NEW
→ CLAIMED
→ DISPATCHING
→ SUCCEEDED
→ FAILED
→ UNKNOWN
→ RECONCILED
```

### 关键规则

- `SUCCEEDED` 永远不能再次执行；
- `UNKNOWN` 不得自动重试；
- `FAILED` 是否可重试必须由明确错误分类决定；
- 状态迁移必须有 optimistic lock/version；
- 每次迁移写入 audit event；
- tool result 必须与 execution record 同事务或通过 outbox 保证最终一致。

### 推荐新增

```text
src/fxfill_banking_agent/execution_state.py
src/fxfill_banking_agent/reconciliation.py
src/fxfill_banking_agent/outbox.py
```

### 新增测试

```text
tests/concurrency/test_idempotency_race.py
tests/recovery/test_unknown_outcome.py
tests/recovery/test_outbox_delivery.py
tests/recovery/test_reconciliation.py
```

### 完成标准

- [ ] 100 个重复请求只执行一次；
- [ ] 数据库 commit 与 event 发送不丢失；
- [ ] UNKNOWN 有人工或自动 reconciliation；
- [ ] 状态迁移不允许非法跳转。

### 建议提交

```text
feat(reliability): implement durable idempotency state machine
```

---

## 2.5 production composition root 切换

### 修改文件

```text
src/fxfill_banking_agent/bootstrap.py
src/fxfill_banking_agent/runtime_factory.py
src/fxfill_banking_agent/server.py
src/fxfill_banking_agent/config.py
compose.yaml
k8s/deployment.yaml
```

### production 启动检查

```text
PostgreSQL 可连接
Redis 可连接
migration version 正确
OIDC 配置完整
Secret 存在
CORS 非通配
开发身份关闭
SQLite 未启用
```

### 完成标准

- [ ] 生产配置缺失即拒绝启动；
- [ ] 所有 runtime dependency 只有 composition root 创建；
- [ ] shutdown 正确关闭连接池；
- [ ] 不存在隐藏的第二套 runtime。

### 建议提交

```text
refactor(runtime): enforce production dependency composition
```

---

## 2.6 多实例、并发、故障恢复验证

### 本地拓扑

```text
agent-1
agent-2
agent-3
postgres
redis
keycloak
```

### 测试场景

```text
跨实例同 thread
跨实例重复审批
跨实例同 idempotency key
Pod/容器在执行前崩溃
Pod/容器在执行后响应前崩溃
PostgreSQL 短暂不可用
Redis 短暂不可用
Provider 超时 / 429 / 500
```

### 新增测试

```text
tests/concurrency/
tests/chaos/
tests/recovery/
```

### 阶段 2 门禁

```bash
docker compose up -d --build --scale agent=3
uv run pytest tests/integration -q
uv run pytest tests/concurrency -q
uv run pytest tests/recovery -q
uv run pytest tests/chaos -q
```

阶段 2 通过条件：

```text
PostgreSQL 是唯一权威持久化
Redis 是分布式协调层
多实例共享状态
重复副作用率 = 0
UNKNOWN 不被自动重试
重启后 thread / HITL / grant 可恢复
```

更新：

```text
docs/execution/STATUS.md
docs/execution/TEST_EVIDENCE.md
docs/execution/DECISIONS.md
```

---

# 阶段 3：AgentOps、可观测性、审计与 CI/CD

阶段 2 通过后开始。

---

## 3.1 统一结构化事件和 Trace 上下文

### 统一字段

```text
correlation_id
trace_id
span_id
tenant_id
subject_id
session_id
thread_id
run_id
tool_call_id
idempotency_key
approval_id
```

### 修改文件

```text
src/fxfill_banking_agent/telemetry.py
src/fxfill_banking_agent/observability.py
src/fxfill_banking_agent/logging.py
src/fxfill_banking_agent/redacted_logger.py
src/fxfill_banking_agent/metrics.py
src/fxfill_banking_agent/api.py
src/fxfill_banking_agent/agent.py
src/fxfill_banking_agent/graph.py
```

### 必须记录的生命周期

```text
request.received
auth.succeeded / auth.failed
authorization.allowed / denied / pending
llm.request / llm.response / llm.error
tool.proposed
tool.validated / rejected
hitl.created / approved / rejected / expired
idempotency.claimed / conflict
tool.started / succeeded / failed / unknown
reconciliation.started / completed
request.completed / failed
```

### 完成标准

- [ ] 一个请求可通过 correlation_id 追踪全链路；
- [ ] 不记录 Token、完整账户数据和敏感 Prompt；
- [ ] 所有副作用都有审计事件。

### 建议提交

```text
feat(observability): trace full agent and tool lifecycle
```

---

## 3.2 接入 OpenTelemetry、Prometheus 与 Dashboard

### 推荐组件

```text
OpenTelemetry SDK
OTel Collector
Prometheus
Grafana
Jaeger 或 Tempo
```

### 关键指标

```text
http_request_duration_seconds
llm_request_duration_seconds
llm_tokens_total
llm_cost_total
tool_call_duration_seconds
tool_errors_total
authorization_denied_total
hitl_pending_total
hitl_wait_seconds
idempotency_conflicts_total
unknown_outcomes_total
reconciliation_backlog
provider_429_total
provider_5xx_total
```

### 修改

```text
src/fxfill_banking_agent/observability.py
src/fxfill_banking_agent/metrics.py
src/fxfill_banking_agent/telemetry.py
compose.yaml
k8s/deployment.yaml
```

新增：

```text
observability/otel-collector.yaml
observability/prometheus.yml
observability/grafana/dashboards/*.json
observability/alerts/*.yaml
```

### 完成标准

- [ ] Grafana 能看到请求、LLM、Tool、HITL、错误指标；
- [ ] Trace 能跨 API → Agent → LLM → Tool；
- [ ] 告警规则可被测试触发；
- [ ] tenant label 不包含高基数敏感数据。

### 建议提交

```text
feat(agentops): add telemetry, metrics, dashboards, and alerts
```

---

## 3.3 建立不可篡改审计链

### 审计事件字段

```text
event_id
tenant_id
subject_id
actor_type
action
resource_type
resource_id
tool_name
arguments_digest
authorization_decision
approval_id
idempotency_key
result
timestamp
correlation_id
previous_event_hash
event_hash
```

### 修改文件

```text
src/fxfill_banking_agent/audit/models.py
src/fxfill_banking_agent/persistence.py
src/fxfill_banking_agent/data_security.py
```

推荐新增：

```text
src/fxfill_banking_agent/audit/service.py
src/fxfill_banking_agent/audit/hash_chain.py
src/fxfill_banking_agent/audit/export.py
```

### 要求

- append-only；
- 业务代码无 update/delete 审计记录权限；
- hash chain 检测篡改；
- 审计查询有独立 role/scope；
- 支持导出到对象存储/WORM；
- 明确定义 retention。

### 新增测试

```text
tests/security/test_audit_append_only.py
tests/security/test_audit_hash_chain.py
tests/security/test_audit_access_control.py
```

### 完成标准

- [ ] 删除或修改旧审计记录被拒绝；
- [ ] 篡改可被校验发现；
- [ ] 每个敏感操作均有审计记录。

### 建议提交

```text
feat(audit): add append-only tamper-evident audit trail
```

---

## 3.4 拆分健康检查与运行状态

### Endpoint

```text
GET /live
GET /ready
GET /health/deep
```

### `/live`

只检查进程和事件循环。

### `/ready`

检查：

```text
PostgreSQL
Redis
migration version
MCP/tool registry
必要配置
```

### `/health/deep`

运维诊断：

```text
Provider 状态
连接池状态
reconciliation backlog
outbox backlog
```

不得返回：

```text
Token
连接字符串
数据库密码
内部堆栈
```

### 修改文件

```text
src/fxfill_banking_agent/api.py
src/fxfill_banking_agent/server.py
k8s/deployment.yaml
compose.yaml
```

### 完成标准

- [ ] PostgreSQL 不可用时 readiness 失败；
- [ ] Redis 不可用时 readiness 失败；
- [ ] liveness 不因外部 Provider 临时失败而重启进程；
- [ ] Kubernetes probes 使用正确 endpoint。

### 建议提交

```text
feat(ops): separate liveness readiness and deep health checks
```

---

## 3.5 API 与日志安全加固

### 修改文件

```text
src/fxfill_banking_agent/api.py
src/fxfill_banking_agent/errors.py
src/fxfill_banking_agent/redacted_logger.py
src/fxfill_banking_agent/config.py
```

### 必须完成

- CORS 白名单；
- TrustedHost；
- HTTPS redirect（生产）；
- 请求体大小限制；
- Prompt 长度限制；
- timeout；
- 每 tenant/subject 限流；
- 统一 machine-readable error；
- 禁止 `detail=str(exc)`；
- PII/secret redaction；
- 安全 Header；
- OpenAPI Bearer scheme。

### 错误格式

```json
{
  "error_code": "AGENT_EXECUTION_FAILED",
  "message": "The request could not be completed.",
  "correlation_id": "req-..."
}
```

### 完成标准

- [ ] 内部异常不返回客户端；
- [ ] Token、API Key、密码不会出现在日志；
- [ ] CORS 在 production 不能使用 `*`；
- [ ] 超大请求被拒绝。

### 建议提交

```text
fix(security): harden API boundaries and error handling
```

---

## 3.6 强制 CI/CD 与供应链门禁

### 修改文件

```text
.github/workflows/ci.yml
pyproject.toml
```

推荐新增：

```text
.github/workflows/security.yml
.github/workflows/release.yml
.github/CODEOWNERS
.gitleaks.toml
```

### CI 必须包含

```text
Ruff
Format
Strict MyPy
Pytest
Coverage threshold
Security tests
Migration tests
Gitleaks
CodeQL
Dependency audit
Trivy filesystem scan
Trivy container scan
Docker build
SBOM
```

### 覆盖率目标

第一阶段：

```text
overall line coverage >= 80%
```

最终目标：

```text
overall line coverage >= 85%
branch coverage >= 75%
auth / authorization / HITL / idempotency >= 90%
```

### MyPy

逐步删除：

```toml
ignore_errors = true
```

优先顺序：

```text
auth_middleware
approval_executor
grant_repo
banking
providers
mcp
postgres_backend
bootstrap
```

### GitHub 设置

人工配置：

```text
main branch protection
required pull request
required CI checks
required review
dismiss stale review
block force push
CODEOWNERS
```

### 完成标准

- [ ] 所有 GitHub Actions 绿色；
- [ ] main 无法绕过 required checks；
- [ ] secret scan、container scan 无 Critical；
- [ ] coverage 低于阈值自动失败；
- [ ] 生产镜像使用不可变 tag/digest。

### 建议提交

```text
ci: enforce enterprise quality and supply-chain gates
```

---

## 3.7 阶段 3 最终门禁

执行：

```bash
uv run pytest
uv run pytest --cov=src --cov-branch --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy src
docker build -t fxfill-agent:validation .
docker compose up -d
```

必须验证：

```text
Dashboard 有数据
Trace 可查询
Alert 可触发
Audit chain 可校验
Readiness 可反映依赖故障
客户端看不到内部异常
CI 全绿
```

更新：

```text
docs/execution/STATUS.md
docs/execution/TEST_EVIDENCE.md
docs/execution/DECISIONS.md
```

---

# 阶段 4：文档、发布与最终验收

## 4.1 更新文档

必须更新：

```text
README.md
README.zh-CN.md
docs/execution/STATUS.md
docs/execution/TEST_EVIDENCE.md
docs/execution/DECISIONS.md
ROADMAP.md
CHANGELOG.md
```

推荐新增：

```text
docs/ARCHITECTURE.md
docs/THREAT_MODEL.md
docs/AUTHORIZATION_MODEL.md
docs/HITL_AND_IDEMPOTENCY.md
docs/DEPLOYMENT.md
docs/RUNBOOK.md
docs/INCIDENT_RESPONSE.md
docs/DISASTER_RECOVERY.md
docs/SLO_SLA.md
SECURITY.md
```

## 4.2 最终证据包

至少包含：

```text
测试数量与覆盖率
OIDC 负向测试
跨 tenant 测试
重复审批并发测试
多实例恢复测试
PostgreSQL migration 测试
Redis 故障测试
OpenTelemetry trace 截图
Grafana dashboard 截图
审计 hash chain 验证
Docker / Kubernetes 验证
Secret / vulnerability scan
```

## 4.3 发布

```bash
git tag -a v0.2.0 -m "Enterprise core upgrade"
git push origin v0.2.0
```

Release 中必须明确：

```text
已验证能力
已知限制
升级说明
迁移说明
安全声明
不处理真实资金/客户数据
```

---

# 建议 Commit 顺序

```text
1. chore(config): define strict runtime environment modes
2. feat(security): define immutable trusted identity context
3. feat(auth): implement verified OIDC JWT authentication
4. feat(authz): enforce tenant-scoped RBAC and ABAC policies
5. refactor(hitl): unify approval and graph resume execution
6. refactor(storage): define backend-neutral persistence interfaces
7. feat(storage): make PostgreSQL the authoritative durable store
8. feat(redis): add distributed rate limiting and coordination
9. feat(reliability): implement durable idempotency state machine
10. refactor(runtime): enforce production dependency composition
11. feat(observability): trace full agent and tool lifecycle
12. feat(agentops): add telemetry metrics dashboards and alerts
13. feat(audit): add append-only tamper-evident audit trail
14. feat(ops): separate liveness readiness and deep health checks
15. fix(security): harden API boundaries and error handling
16. ci: enforce enterprise quality and supply-chain gates
17. docs: publish enterprise upgrade evidence and runbooks
```

---

# 禁止事项

实施过程中禁止：

```text
为了通过测试而弱化授权
把 LLM 输出当身份或权限
把 approver 身份放在请求 body 并直接信任
生产环境回退 SQLite
只用 Redis 锁而没有数据库唯一约束
UNKNOWN 状态自动重试副作用
把完整 Token、账户信息、Prompt 写入日志
使用 broad type: ignore 或扩大 mypy ignore_errors
一次提交所有阶段
在 CI 未通过时宣称 production-ready
```

---

# 最终完成定义

## 企业级作品集完成

- [ ] README 与证据一致；
- [ ] CI 全绿；
- [ ] Docker 一键启动；
- [ ] 身份、跨账户、Prompt spoof 测试通过；
- [ ] 已知 scaffold 明确标记；
- [ ] 发布正式版本。

## Production-like 原型完成

- [ ] OIDC/JWT 真实验证；
- [ ] RBAC/ABAC 多租户隔离；
- [ ] HITL 唯一主链；
- [ ] PostgreSQL 权威存储；
- [ ] Redis 分布式协调；
- [ ] 幂等与 UNKNOWN/reconciliation；
- [ ] 多实例并发与恢复测试；
- [ ] OpenTelemetry、Dashboard、Alert；
- [ ] 不可篡改审计；
- [ ] 覆盖率与 CI 门禁达标。

## 仍不可直接宣称

即使完成本方案，也不能单独宣称：

```text
已获准处理真实资金
已达到银行合规认证
已通过独立渗透测试
已完成多区域灾备
已满足真实银行 SLA
```

这些还需要组织级安全、合规、法务、风险、生产基础设施和独立审计。
