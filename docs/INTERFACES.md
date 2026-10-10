# 接口 reference

权威定义：[contracts.py](../src/pace/application/contracts.py)、[mcp.py](../src/pace/interfaces/mcp.py)、[models.py](../src/pace/adapters/db/models.py)。完整 JSON Schema 由 GET /contracts 生成；本页只解释接口语义，完成度见 [STATUS](STATUS.md)。

## MCP Tools

只有 sync_entity、connect。输入 Contract extra=forbid，可信身份从服务端 Principal 取得，不能传 email / user_id。Tools 改变状态，annotations 为 readOnlyHint=false、idempotentHint=true、openWorldHint=true；sync_entity destructiveHint=true。

### sync_entity

| 字段 | 类型 / 规则 |
| --- | --- |
| request_id | 必填 UUID，同账号内稳定操作键；原载荷重试用原键 |
| ontology | 必填 string，空字符串清除 O；非空不能只有空白 |
| demands / supplies | 必填 string[]，各最多20项，条目非空白、不重复；[] 清除对应集合 |
| expected_entity_version | 可选 null 或 ≥0 int；提供时必须等于当前 Entity 版本 |

三个 O/D/S 字段全量替换，没有 null 保留、增量 entry_id 或文件上传。文本合计 ≤4000 UTF-8 bytes（JSON 包装不计）；后端原样保存，不总结、不推断。全空画像可保存，但不能作为请求者或候选参与匹配。版本格式为 pa-entity-v1；旧 LLM 历史格式不参与选择。

结果 SyncEntityResult = status:accepted、entity_version、entity_status:ready、changed:boolean。事务提交即发布完成快照，无 job_id、构建等待或后端 LLM。内容变化追加版本，原样内容不增加版本；新操作更新最近同步时间。相同 request_id 原载荷重放原回执，先于 expected 版本判断，不覆盖之后的内容。重试要保留原 ID / 载荷。

### connect

输入 = request_id UUID、entity_version（必填≥1，来自连接前同步回执）、request_text（1–10000，非全空白）、context。context 必填 observed_at（时区时间）、timezone（有效 IANA 时区）；location_description 可选 ≤2000 字符。即时请求不更新长期 D/S。新 connect 前先 sync，版本不同在模型调用前报 version_conflict；安装时先同步初始化，连接后和定时均不更新。

输出 ConnectResult = status:matched/no_match、request_id、entity_version。matched 必须含 connection_id、candidate、notification；no_match 这三者为 null，不入队通知。

候选必须有已验证、未过期且未撤销的 connection.matched 订阅；提交前再次检查。新 matched 的 event / email 均 queued，不降级为仅邮件；not_subscribed 仅保留历史 / 所有订阅终止后的状态。

candidate = pace_user_id、email（来自已验证规范 Gmail）、relevant_information（最多四段命中请求词的原文、总≤2000字符；无命中明确说明）。通知 event/email 独立：queued、not_subscribed、captured、accepted_by_receiver、provider_accepted、failed。queued 是实际 outbox 已提交，capture 不是真实邮件。原成功回执在双方资格有效且快照仍是当前版本时重放，不追踪后续交付状态；撤销后原历史仍保存但新的披露读取被拒绝。

### Transport 与错误

GET/POST/DELETE /mcp 都受 Bearer 验证；至少需一项相关scope；sync_entity需要pace:sync，connect及Events需要pace:connect。未带/失效凭据 HTTP401，WWW-Authenticate 带 protected resource metadata URL；缺配置 HTTP503；scope 不足 HTTP403。官方 StreamableHTTPSessionManager 为 stateless=True、json_response=True，body ≤10 MiB。

协议为锁定 SDK 的 2026-07-28。MCP-Protocol-Version / MCP-Method 必填，tools/call 带 MCP-Name；params._meta 携带 io.modelcontextprotocol/protocolVersion 与 io.modelcontextprotocol/clientCapabilities。协议错误由 SDK处理，Host/Origin保护启用；生产只接受PUBLIC_BASE_URL，开发另接受loopback。

Tool 成功同时返回文本 content 与 structuredContent；业务错误为 isError=true，内容均为 {"error":{"code":"...","message":"..."}}。输入详情、SQL、原始 Provider 异常不回显。HTTP status 只用于认证等 HTTP 边界；Tool 内错误不会按此改变 transport status。

| code | HTTP 声明 | 含义 |
| --- | --- | --- |
| authentication_required | 401 | 无有效 PACE bearer |
| account_unavailable | 403 | 非 Gmail、未验证 / 未接受当前同意 / 禁用账号 |
| feature_unavailable | 503 | 必要能力缺配置 |
| entity_not_ready | 409 | 请求者没有当前非空 PA 快照，或旧披露快照已被替换 |
| version_conflict | 409 | 当前 Entity 版本变化 |
| idempotency_conflict | 409 | 同键不同有效载荷 |
| input_too_large | 413 | Provider 输入预算超限 |
| selection_limit | 503 | 候选 / 总耗时预算不足 |
| provider_unavailable / invalid_selection | 502 | Provider 故障 / 选择无效，不是 No Match |
| delivery_unavailable / delivery_terminal | 502 | 通知失败 / 不再重试 |
| invalid_input / unknown_tool | Tool 错误 | 契约或名称不合法 |
| internal_error | 500 / Tool 错误 | 未分类内部故障，安全固定消息 |

## Gmail OAuth

当数据库、GOOGLE_CLIENT_ID、GOOGLE_CLIENT_SECRET、ENCRYPTION_KEY 都配置时挂载。SDK处理 OAuth 协议；Google callback 才创建账号，没有匿名 email 注册入口。

| 路径 | 方法 / 作用 |
| --- | --- |
| /.well-known/oauth-authorization-server | GET，PACE issuer/端点/scope metadata |
| /.well-known/oauth-protected-resource/mcp | GET，/mcp 的资源 metadata |
| /register | POST，动态客户端注册；精确 redirect / 受限 callback_id 模板白名单，开发 loopback 例外 |
| /authorize | GET/POST，SDK验证客户端、redirect、scope、PKCE；跳 PACE 同意页 |
| /token | POST，授权码 / refresh 交换，绑定客户端；原子一次性消费 / 轮换 |
| /revoke | POST，撤销相关 token family |
| /auth/consent | GET/POST，持续 PA 上传、匹配披露与平台事件 / Gmail 通知同意；flow cookie 防跨流程提交 |
| /auth/google/callback | GET，Google code/state 回跳；验证 Gmail 与 sub，签发 PACE code 回 Host |

Google 只申请 openid/email，不读邮件；同意版本 pa-connections-v2；旧账号需要重新同意，不能自动扩大旧授权。只支持 @gmail.com，dot/plus 规范化，签名 sub 双唯一。拒绝其它域、未验证邮箱、冲突身份或禁用账号。Google token 不能用于 /mcp；PACE access/refresh 是 opaque 值，Hash 持久化，resource 固定 issuer/mcp。access 默认1小时，refresh默认30天；码2分钟，flow10分钟。refresh轮换后旧access也失效。请求 nonce、issuer/audience/expiry 验证与 Cookie 绑定不省略。

浏览器同意页的 CSP form-action 仅允许本站与 https://accounts.google.com，以免浏览器拦截 Google 跳转；cookie / state / 一次性 flow 校验保持不变。登录失败仍返回 gmail_authorization_failed；私有日志仅记录固定流程分类或异常类型，不记录异常正文、flow、授权码或令牌。

注册允许 none/client_secret_basic/client_secret_post；client secret 加密保存。生产 OAuth redirect URI 由 OAUTH_REDIRECT_ALLOWLIST 配置，不默认信任任意 HTTPS。允许精确 URI，或显式配置以 /{callback_id} 结尾的单段 ID 模板（1–128 个 ASCII 字母、数字、下划线或连字符）；客户端注册后仍保存 / 校验精确 URI，见 [ADR 0005](decisions/0005-oauth-callback-id-templates.md)。客户端要使用完整两项业务应申请 pace:sync pace:connect；refresh可缩减scope，不能提升权限。

## MCP Events

当数据库与 Fernet Key 配置时启用，受同一 MCP身份边界保护。目标 Work Cloud / dots 的实际账号需完成原生监控；PACE 回调由 Host 触发 PA，只通知用户，不做 Agent 对话；不支持平台不适配。只有 connection.matched，空 arguments schema，无 replay。发现 capabilities.events={}；扩展层不增加业务 Tool。

| method | 主要 params | 结果 |
| --- | --- | --- |
| events/list | params._meta；无过滤 | events 列表含 name/description/delivery/inputSchema/payloadSchema |
| events/subscribe | name:connection.matched、arguments:{}、delivery:{mode:webhook,url,secret}、cursor:null、可选 ttlMs | id、refreshBefore、cursor:null、truncated:false |
| events/unsubscribe | 原 name、arguments:{}、delivery:{mode:webhook,url}（不需 secret） | {}；只操作当前 account/client，重复停止幂等 |

secret 必须 whsec_ 加合法 base64，解码24–64 bytes。callback 仅公网 HTTPS443、无凭据/fragment，DNS 校验每次连接执行，固定已验证IP并保留TLS hostname，禁重定向。challenge 验证后才激活。同身份/目标/事件/参数稳定ID刷新；默认及最长期限24小时，ttlMs=null仍授予有限期限。有效且相同secret的challenge最多缓存5分钟，换secret重新验证；旧/新secret双签5分钟。

验证 body = {"type":"verification","challenge":"..."}；响应必须2xx并回显相同challenge。错误为 JSON-RPC -32015 CallbackEndpointError，data.reason 分类，不带url/secret详情；参数错误 -32602。订阅输入上限16KiB，必须当前协议及匹配MCP-Method；带Origin时只允许服务origin。

实际投递 envelope：
```json
{
  "eventId": "stable UUID",
  "name": "connection.matched",
  "timestamp": "timezone-aware occurrence time",
  "data": {
    "connection_id": "UUID",
    "request_summary": "instant request summary",
    "requester": {
      "pace_user_id": "UUID",
      "email": "verified@gmail.com",
      "relevant_information": "limited relevant excerpt"
    }
  },
  "cursor": null
}
```

webhook-id 与 eventId 一致，webhook-timestamp / webhook-signature 使用 Standard Webhooks，另有 X-MCP-Subscription-Id。完整body≤256KiB，响应≤8KiB，网络10秒；2xx表示接收端接受而非用户阅读；410/413撤销/终止、不重试，其它错误有限退避。事件发生时间/ID重试不变，签名时间更新。

## HTTP/API

| method/path | 响应 |
| --- | --- |
| GET /healthz | 200，status:ok、service:pace、stage:mvp；仅进程存活 |
| GET /readyz | 配置/DB revision不足503，否则200；stage:mvp、email_delivery_mode、pending；不测试付费模型/真实邮件/Worker心跳 |
| GET /contracts | 公开两个Tool的Pydantic input/output Schema |
| /docs、/redoc、/openapi.json | FastAPI 运维文档，不是另一个业务接口 |
| /mcp | 认证后官方Tools或隔离Events扩展 |
| OAuth 路径 | 见上一节；缺配置不挂载 |

## Database 与内部能力

迁移 head=0003；不自动create_all，ORM无relationships。JSON内部关联仍由业务用例验证，无历史不可变Trigger。

| table | 关键约束 / 用途 |
| --- | --- |
| accounts | id UUID、canonical email唯一、google_subject唯一、verified/consent/enabled/host_bindings |
| entities | account_id PK/FK、version≥0、building/ready/refreshing/failed、O/D/S、最近新同步时间；files 仅保留历史兼容列 |
| entity_versions | 账号/version唯一且>0；完成 O/D/S snapshot、pa-entity-v1 格式 / 创建时间；sources/model 保留历史列 |
| sync_receipts | account/request_id唯一；payload_hash+原结果 |
| connection_requests | account/request_id唯一；完成snapshot引用、原请求、trace、结果/失败码 |
| matches | request唯一，双方不同；联系人快照、两个通道状态、每订阅event_deliveries |
| event_subscriptions | account/client/subscription_key唯一；回调、密文secret、期限/验证/撤销 |
| oauth_records | Hash/prefix key；kind、payload、可选账号/期限；clientsecret/verifier在sealed密文 |
| jobs | dedupe_key唯一；queued/running/completed/failed、attempts/限额、lease UUID/截止、错误/完成时间 |

内部 Ports 在 application/ports.py；PersistentCommands通过BusinessStore访问事务；Tournament只依赖ChoiceProvider。Worker注入EmailDelivery和EventDelivery，具体服务由bootstrap装配。

enqueue 不提交；同键同kind/payload重放，否则冲突。claim 原子 SKIP LOCKED；renew/complete/fail 仅当前未过期lease有效。fail 支持terminal=True；否则有限重试，退避 min(300,2**min(attempts,8)) 秒。未知kind错误handler_not_configured；未知Handler异常handler_failed；已分类错误保存安全业务code。run_once 返回领过任务与否，不代表完成。

## 外部服务

| Adapter | timeout / budget / 状态 |
| --- | --- |
| JevChoiceProvider | 官方TypeSafe SDK，单调用默认20秒、自动重试0、输入24000字节；Provider故障与无效选择分别报错 |
| GoogleOAuth | Authlib token交换15秒；Google官方ID Token验证器，证书抓取10秒；只验证Gmail |
| GmailEmail | 独立gmail.send授权；refresh15秒/最多一次刷新，send20秒；provider_accepted不保证实际到达，崩溃重试可重复 |
| EventWebhooks | DNS5秒、请求10秒、无环境代理/重定向、固定公网IP+SNI；签名/挑战/轮换 |
| CaptureEmail | 私有目录0700、文件0600、UUIDdelivery_id、原子独占落盘；同ID不同内容ValueError |
| PostgreSQL | SQLAlchemy asyncio/psycopg，pool_pre_ping；业务/租约事务；连接/查询失败不伪装成功 |

新画像 sources=[] / model=null，不读取或转换旧 files / LLM 快照；旧数据不自动清理。数据库结构未改变，历史迁移不改写。后端没有 Ontology Provider 或定时画像任务，OPENAI_* / ONTOLOGY_* 旧环境字段被忽略。

配置与实际运行命令见 [DEVELOPMENT](DEVELOPMENT.md)。
