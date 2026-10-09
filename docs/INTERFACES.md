# 接口 reference

只记录源码已有的接口、数据结构与默认行为。契约存在不代表业务执行已实现，完成度见 [STATUS](STATUS.md)。源码权威入口：[contracts.py](../src/pace/application/contracts.py)、[mcp.py](../src/pace/interfaces/mcp.py)、[models.py](../src/pace/adapters/db/models.py)。JSON Schema 可从 `GET /contracts` 或模型的 `model_json_schema()` 获取，不维护第二套完整 schema。

## MCP Tools

共同实现位置：`src/pace/interfaces/mcp.py` 的 `TOOL_CONTRACTS`、`tool_definitions`、`build_server.call_tool`。输入 / 输出全部来自 `src/pace/application/contracts.py` 的 Pydantic 模型。所有 Contract `extra=forbid`，输入不能传 `email` / `pace_user_id` 等身份字段。回调从服务端 `request.scope.state.pace_principal` 取得 Principal。

| name | input / output | 命令入口 | side effects / errors |
| --- | --- | --- | --- |
| `sync_entity` | `SyncEntityInput` → `SyncEntityResult` | `BusinessCommands.sync_entity(principal, data)`；默认 `UnconfiguredCommands.sync_entity` | 当前无业务副作用，默认抛 FeatureUnavailable；输入校验可返回 invalid_input |
| `connect` | `ConnectInput` → `ConnectResult` | `BusinessCommands.connect(principal, data)`；默认 `UnconfiguredCommands.connect` | 当前无业务副作用，默认抛 FeatureUnavailable；不调用 DB / Tournament / Delivery |

Tool annotations：两者 `readOnlyHint=false`、`idempotentHint=true`、`openWorldHint=true`；`destructiveHint` 仅 sync_entity 为 true。这些是描述性提示，不能当作真实幂等重放或外部调用的证明。

### sync_entity 输入

| 字段 | 类型 / 默认值 | 当前校验 |
| --- | --- | --- |
| `request_id` | UUID，必填 | 结构校验；当前无持久 sync 幂等实现 |
| `files` | `list[SourceFile] \| null`，默认 null | 最多 20 个；source_id 不重复；总 UTF-8 文本 ≤8 MiB；null 与 [] 保持不同值 |
| `demand_updates` / `supply_updates` | `list[EntryUpdate]`，默认 [] | 各列表内部 entry_id 不重复，D 与 S 之间可以重复；没有数量上限 |
| `expected_entity_version` | `int \| null`，默认 null | ≥0；尚不做事务版本判断 |

至少一种明确更新：files 不能是 null 且两类 updates 同时空；显式 `files=[]` 合法。未实现替换 / 合并、空文件集业务处理、来源持久化或版本切换，不能从这一 validator 推导它们。

`SourceFile` 字段：source_id（1–200 字符）、name（1–255）、text（str）、content_hash（64 位小写十六进制）、observed_at（AwareDatetime）。文件名大小写无关且只以 `.txt` / `.md` 结尾；单文件 UTF-8 文本 ≤1 MiB；content_hash 必须等于原样 text 的 SHA-256；文本没有非空限制，时间必须带时区。校验 hash 不证明 Host 已授权或内容可信。

`EntryUpdate` 按 operation 区分：`upsert` = operation + UUID entry_id + text（1–10000 字符）；`remove` = operation + UUID entry_id。upsert text 没有专门的全空白拒绝，只有长度检查。

`SyncEntityResult`：必填 status 固定 accepted、entity_version（int）、entity_status（building / ready / refreshing）、accepted_updates（list[str]）；job_id 为 UUID 或 null，默认 null。输出 entity_version 没有非负校验；accepted 仅为 schema 分支，默认命令不会产生它。

### connect 输入输出

| 输入字段 | 当前规则 |
| --- | --- |
| `request_id` | UUID，必填 |
| `request_text` | str，1–10000 字符且不能全为空白；保留原文本 |
| `context.observed_at` | AwareDatetime，必填 |
| `context.timezone` | 必填 str，需被 `ZoneInfo` 识别为 IANA 时区 |
| `context.location_description` | str 或 null，默认 null，最多 2000 字符 |

`ConnectResult` 必填 status（matched / no_match）、request_id、entity_version；可选 connection_id、candidate、notification 默认 null；ontology_refresh 固定 `host_collection_required`。matched 必须同时含 connection_id / candidate / notification；no_match 三者必须全 null。结果模型只验证形状，不证明实体版本、Match 或任务存在。

| 结果对象 | 字段 |
| --- | --- |
| `CandidateResult` | pace_user_id（UUID）、relevant_information（str）、email（str；没有 Email 格式 / 验证校验） |
| `NotificationState` | event、email 均为 DeliveryState；两个通道都必须提供 |
| `DeliveryState` | queued / not_subscribed / captured / accepted_by_receiver / provider_accepted / failed；共享枚举没有按通道进一步限制 |

只有 CaptureEmail 当前能生成真实 captured 结果。queued、accepted_by_receiver、provider_accepted 等值是契约允许值，不代表存在对应执行路径；接收与服务商接受也不表示用户阅读。

### Transport、成功与错误边界

`ProtectedMCP` 包围 GET / POST / DELETE `/mcp`，先检查 Bearer，再调用 IdentityVerifier.verify。缺凭据返回 HTTP 401 与 `WWW-Authenticate: Bearer`；默认验证器返回 HTTP 503；验证结果需同时具有 `pace:connect`、`pace:sync`，缺任一为 HTTP 403 / insufficient_scope，发现请求也受保护。

通过后使用官方 `StreamableHTTPSessionManager(stateless=True, json_response=True)`；body 上限 10 MiB（JSON 开销可能先于文件文本限额触发）。SDK负责协议错误，不与业务错误合并。`tests/unit/test_mcp.py` 验证的协议版本为 `2026-07-28`，请求包含 MCP-Protocol-Version / MCP-Method，tools/call 另带 MCP-Name；params._meta 包含 `io.modelcontextprotocol/protocolVersion` 与 `io.modelcontextprotocol/clientCapabilities`。这是锁定 SDK 的实测请求形式，不是对其他 Host 支持性的声明。

回调成功：结果的 JSON 同时放入文本 content 和 structuredContent。PACE 回调错误：`isError=true`，文本和 structuredContent 均为 `{"error":{"code":"...","message":"..."}}`。ValidationError 被转换为固定 invalid_input，不回显私密正文；未知 Tool 可返回 unknown_tool，SDK 也可能先拒绝不符合协议 / schema 的请求。未知内部异常由 SDK 处理。

| 错误类 / code | 声明 HTTP status | 当前触发位置 |
| --- | --- | --- |
| `PaceError` / internal_error | 500 | 基类；并非通用异常自动包装 |
| `AuthenticationRequired` / authentication_required | 401 | ProtectedMCP 无有效 Bearer |
| `FeatureUnavailable` / feature_unavailable | 503 | 默认 Identity / Commands；database_url 缺配置 |
| `ProviderUnavailable` / provider_unavailable | 502 | Jev Adapter 捕获 TypeSafeError |
| `InvalidSelection` / invalid_selection | 502 | Adapter 响应形状错误或 Tournament 决策校验失败 |
| `InputTooLarge` / input_too_large | 413 | Jev SDK 调用前预算检查 |
| `IdempotencyConflict` / idempotency_conflict | 409 | enqueue 同键不同 kind / payload |
| invalid_input / unknown_tool | 无对应 PaceError 类 | build_server.call_tool 分支 |

HTTP status 列来自 `src/pace/domain/errors.py`，只在 HTTP 层捕获使用；Tool 内 PaceError 变成 MCP isError，不据此改变 transport HTTP status。重复候选 / 自身是 Tournament 的 ValueError；Capture 冲突是 ValueError；没有 `entity_not_ready` 等旧设计中预想的错误类。

## MCP Events

已有唯一载荷模型 `src/pace/application/contracts.py: ConnectionMatched`：

| 字段 | 类型 / 规则 |
| --- | --- |
| event_id | UUID，必填 |
| type | Literal connection.matched，默认该值 |
| occurred_at | AwareDatetime，必填 |
| connection_id | UUID，必填 |
| request_summary | str，必填 |
| requester | CandidateResult，必填，包含申请方相关信息与 email |

**触发位置：无。** 未注册 events/list、events/subscribe、events/unsubscribe，没有 Match 后生成事件、callback challenge、Webhook 签名或 Delivery Adapter。`EventSubscription` 表存在不能当作订阅 API 已实现；本节载荷没有已执行的 side effects / delivery errors。

## HTTP/API

实现位置 `src/pace/interfaces/http.py: build_app`；HTTP 无业务 REST 旁路。

| method / path | 当前 response / 行为 |
| --- | --- |
| GET `/healthz` | 200：`{"status":"ok","service":"pace","stage":"framework"}`；不探测依赖 |
| GET `/readyz` | 固定 503：status=not_ready、stage=framework、pending=[email_oauth, entity_transactions, connection_delivery] |
| GET `/contracts` | 200：version=0.1.0、business_tools，按两项契约返回 input / output JSON Schema；不包含 Event schema |
| GET / POST / DELETE `/mcp` | 先身份保护，再官方 Streamable HTTP；POST 发现 / 调用经过 SDK 测试；三种方法默认 401 / 503 均经实际监听验证 |
| GET `/docs`、`/redoc`、`/openapi.json` | FastAPI 默认文档；MCP 的 ASGI Route 不等同 REST 业务 schema |

这些端点没有上传 / 登录 / Email 验证 API。公开端点不返回凭据或用户数据。

## Database

权威源码：`src/pace/adapters/db/models.py`；初始迁移 `migrations/versions/0001_initial_framework.py`，revision=0001。六张业务表加 jobs；alembic_version 由工具维护。无 ORM relationship、无自动 create_all。

| model / table | 主要字段与意义 | 关系 / 硬约束 |
| --- | --- | --- |
| Account / accounts | id 稳定账号键；email；email_verified_at；consent_version / consented_at；enabled 默认 false；host_bindings JSONB | email 唯一；无 Email 规范化或 bindings 内容校验 |
| Entity / entities | account_id 当前实体键；version；status；ontology JSONB、demands / supplies JSONB；updated_at | account_id 同时 PK / accounts FK；version≥0；status=building / ready / refreshing / failed |
| EntityVersion / entity_versions | id；account_id；version；snapshot JSONB；sources；model / prompt_version | account_id → accounts；(account_id, version) 唯一，version>0；无历史不可变 Trigger |
| ConnectionRequest / connection_requests | id 内部键；account_id；request_id 客户端键；payload_hash / payload；snapshot_id；status / result / selection_trace / error_code | account_id → accounts，snapshot_id → entity_versions；(account_id, request_id) 唯一；status=pending / matched / no_match / failed |
| Match / matches | id；request_id 内部 Request 键；requester_id / candidate_id；candidate_snapshot_id；contact_snapshot；event_status / email_status | request_id → connection_requests 且唯一；双方 → accounts 且不同；candidate_snapshot_id → entity_versions；通道状态是未加 Check 的字符串 |
| EventSubscription / event_subscriptions | id / account_id；client_id / subscription_key；event_type；callback_url；signing_secret_ciphertext；expires_at / verified_at / revoked_at | account_id → accounts；(account_id, client_id, subscription_key) 唯一；无 callback 验证 / secret 加密实现 |
| Job / jobs | id；kind；dedupe_key；payload；status / attempts / max_attempts；available_at；lease_id / lease_until；error_code / completed_at | dedupe_key 全表唯一；status=queued / running / completed / failed；attempts≥0，max_attempts>0；(status, available_at) poll 索引，无业务 FK |

全部模型含 created_at，数据库 `now()` 默认；updated_at 仅插入默认，不自动随更新变化。UUID / JSON 默认多数为 ORM Python default，直接 SQL 插入不能依赖这些 server defaults。JSONB 内部内容与 Snapshot 归属、请求所有者和 Match requester 一致性没有 DB 约束。

### JobQueue 内部持久接口

实现 `src/pace/adapters/db/jobs.py`；执行者 `src/pace/interfaces/worker.py`。

| symbol | 输入 / 输出 | side effects / errors |
| --- | --- | --- |
| `enqueue(session, kind, dedupe_key, payload, max_attempts=3)` | AsyncSession + str / dict → UUID | 不 commit；同键同 kind / payload 返回旧 ID，不重置任务；不同则 IdempotencyConflict；max_attempts 不参与冲突检查 |
| `JobQueue.claim()` | 无 → Job 或 None | 事务内终止耗尽租约，领取 eligible Job；attempts +1，新 lease UUID / deadline；数据库错误向上传播 |
| `renew(job)` | Job → bool | 仅 id + running + 同 lease + 未过期才延长；False 表示失去占有权 |
| `complete(job)` | Job → bool | 同条件，置 completed / completed_at，清租约 |
| `fail(job, error_code)` | Job + code → bool | 有尝试剩余置 queued，否则 failed；code 截到 100 字符；清租约，延后 available_at |
| `Worker.run_once()` | 无 → bool | None 返回 False；领过返回 True；未知 kind=handler_not_configured，Handler 异常=handler_failed；不表示投递完成 |

claim 按 available_at / id 排序，用 SKIP LOCKED。租约到期且耗尽任务记录 lease_exhausted。fail 退避为 `min(300, 2 ** min(attempts, 8))` 秒；按当前整数表达式实际最大为 256 秒。续租周期为 lease_seconds / 3；完整租约与副作用边界见 [ARCHITECTURE](ARCHITECTURE.md#队列与通用-worker)。

## 内部能力 Port

定义于 `src/pace/application/ports.py`，Protocol 不执行持久化或网络。

| Port / method | 输入 → 输出 | 具体实现 / 调用者 |
| --- | --- | --- |
| IdentityVerifier.verify | bearer_token → Principal | 默认 UnconfiguredIdentity；ProtectedMCP 调用 |
| BusinessCommands.sync_entity / connect | Principal + 对应 input → 对应 result | 默认 UnconfiguredCommands；MCP 回调调用 |
| ChoiceProvider.choose | requester Snapshot、request_text、Sequence[Snapshot]、可选 context → ChoiceDecision | JevChoiceProvider、合成 fixture；Tournament 调用 |
| OntologyBuilder.build | Sequence[SourceFile]、previous Snapshot 或 None → str | 无 Adapter / 生产调用者 |
| EventDelivery.deliver | callback_url、ConnectionMatched → str | 无实现 / 调用者 |
| EmailDelivery.deliver | recipient、subject、body、delivery_id → str | CaptureEmail；当前仅测试调用 |

## External services

| service / 调用位置 | 用途与输入输出边界 | timeout / retry / error behavior |
| --- | --- | --- |
| TypeSafe / Jev：`src/pace/adapters/providers/jev.py: JevChoiceProvider` | `AsyncTypeSafeClient.system_one(state, questions={match: Choice})`；state 含 request / requester / candidates，criteria=各 UUID + no_match；输出 choice / probabilities / confidence / model / usage | timeout 来自配置（默认20秒），RetryPolicy(max_retries=0)；默认 24000 字节 JSON 预算，超限 InputTooLarge；TypeSafeError → ProviderUnavailable；KeyError / TypeError / AttributeError / ValueError → InvalidSelection；概率合法性由 Tournament 校验 |
| TypeSafe / Jev：`scripts/doctor.py: check_providers.jev` | 固定合成 badminton / chess / no_match，输出状态、choice、model 和观测耗时 | 固定20秒、重试0；预期 badminton，否则 unexpected_selection；捕获列出的 SDK / API / DB / ValueError 类并只公开类型 |
| OpenAI 兼容服务：`scripts/doctor.py: check_providers.llm` | `AsyncOpenAI.chat.completions.create`；合成单词请求、max_completion_tokens=16；仅检查非空回答 | 固定30秒、max_retries=0；需 Key 与 model；错误输出类型；没有 Ontology Prompt / Adapter |
| PostgreSQL：`src/pace/adapters/db/session.py`、`migrations/env.py` | SQLAlchemy asyncio / psycopg；Engine pool_pre_ping，迁移使用 NullPool | 应用未配置自定义 DB timeout / retry；SQL 错误一般向上传播；doctor 单独 connect_timeout=5 |
| Email provider / Webhook receiver | 无调用位置 | 无真实 timeout / retry / 签名 / error 策略 |

Jev 的预算计数使用默认 json.dumps（包含 ASCII 转义），统计 state + criteria + instructions 的 UTF-8 字节，不是精确 token 计数或最终 HTTP body 上限。默认模型来自 Settings 的 `jev-1.13.0`。API 只构造可选 Client，实际业务命令目前不调用它；live demo 才走真实选择请求。

`CaptureEmail.deliver` 不访问外部服务，使用调用者目录下 `<UUID>.json`；新目录 0700、新文件 0600；同 ID 内容一致返回 captured，不一致抛 ValueError，其他文件 IO 错误向上传播。
