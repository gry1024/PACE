# 当前实现状态

## Current Snapshot

复核日期：2026-10-09（Asia/Shanghai）。基础框架已在 `8a30c4f` 保存；后续开发位于 `codex/gmail-mvp`。本页描述当前工作区实现。

阶段：**可运行的本地 MVP 业务闭环**。配置数据库后，API 使用持久 `sync_entity` / `connect`；Worker 实际处理 Ontology 与通知任务。Google Gmail OAuth、系统 Gmail 发信、MCP Events 已有实现及离线边界测试。**真人 Google 登录、真实 Gmail 收件和公网 Host 联调尚未验收**；不能据此宣称已上线。

当前环境保留原有 Jev / LLM 配置，未改写用户凭据。没有 Google 登录客户端、Fernet 密钥、系统 Gmail 发件授权及公网部署配置，所以默认 MCP 身份仍不可用，`/readyz` 返回 503 并列出配置缺口。本地捕获模式不会真实发邮件。

## 功能完成度

状态含义：Implemented = 代码与相应验收路径存在；Partial = 有实现但关键外部路径未验收；Planned = 尚无实现。Implemented 不等于生产运行效果或服务商凭据已验证。

| 能力 | 状态 | 证据 / 实际边界 |
| --- | --- | --- |
| 固定两项 MCP Tool、真实官方 transport | Implemented | `interfaces/mcp.py`；SDK 协议测试 |
| 持久同步及回执重放 | Implemented | `BusinessRepository.synchronize`；同键冲突、账号锁、乐观版本 |
| 完整授权来源集 / D/S 显式更新 | Implemented | files 替换、null 不改、[] 清空；不推断 D/S |
| Ontology 提取及只追加完成快照 | Implemented | LLM Adapter + Worker 双检版本；空文件零模型调用；来源未撤销时旧完成快照继续可用 |
| 资格过滤 / 最新完成快照候选 | Implemented | 只用启用、已验证、已同意且 Google sub 绑定的规范 Gmail；排除自己 |
| 四候选淘汰赛 / 明确 No Match | Implemented | Tournament + Jev；概率仅组内；错误不变成 No Match |
| 持久 connect / Match / outbox 原子提交 | Implemented | 同键 advisory 锁、当前授权仍成立时成功重放零模型调用、失败状态可重试 |
| 请求相关联系方式披露 | Implemented | Gmail 来自已验证账号；仅少量命中请求词的原文片段；无伪造模型理由 |
| 任务领取、续租、有限重试与恢复 | Implemented | SKIP LOCKED、lease UUID、错误安全码；Worker 注册三种 Handler |
| 本地私有邮件捕获 | Implemented | 原子落盘、稳定 delivery_id、内容冲突检测；状态 captured |
| 个人 Gmail 身份规范化 / 跨 Host 同账号 | Implemented | Google sub + canonical Gmail 双唯一；跨 Host 和令牌测试 |
| Google 浏览器 OAuth / 注册 / 同意 | Partial | 官方 MCP auth 路由、Google OIDC、cookie/state/nonce/PKCE；缺真实客户端验收 |
| 独立 PACE opaque 凭据 / 轮换 / 撤销 | Implemented | Hash 存储、/mcp resource、client binding、一次性消费、族撤销 |
| 系统 Gmail API 通知 | Partial | 独立 gmail.send 授权、稳定 Message-ID、失败重试；尚未真实发信 |
| MCP Events 订阅与签名投递 | Partial | 持久归属、challenge、secret 加密/轮换、DNS 固定公网 IP、410/413 终止；缺真实 Host 接收验收 |
| Host 授权文件收集及接入包 | Partial | `plugins/pace` 的 manifest、MCP 配置、skill 和有界显式文件 collector；未安装联调 |
| 文档链接 / CODEMAP 覆盖检查 | Implemented | `scripts/check_docs.py`；不维护旧 catalog 指纹 |
| 公网部署、全局限流、生产观测与保留策略 | Planned | 不由本次本地测试证明 |

## 验证记录

当前验收：默认测试50 passed / 17 skipped；全部PostgreSQL测试67 passed。Ruff check / format check、文档检查通过。真实数据库路径对每个测试建立独立随机 schema，执行完整 Alembic 升级，再只清理自身 schema。应用数据库升级至 `0003`，`alembic check` 未发现漂移。

已验收的业务场景：并发同请求只选择一次、同键不同载荷冲突、原回执重放、D/S 不被即时请求修改、模型错误留下 failed 而非 No Match、过时任务零模型调用、D/S 单独更新零 LLM、明确文件清空、通知捕获、跨 Host 身份合并、授权码不可重放、refresh 轮换旧 access 失效、撤销令牌族、订阅刷新 / 轮换 / 归属与停止投递。

**有限真实模型验收**：只运行一次 `scripts/demo_business.py --live`，合成资料、隔离数据库 schema、临时邮件捕获。可满足请求得到 matched；Rust 硬冲突得到 no_match；connect 重放新增调用为 0。LLM 1 次：prompt 289 + completion 237 = 526 tokens；Jev 2 次：911+90、885+62 tokens，合计报告 2,474 tokens。没有实际发邮件，没有真人资料，临时 schema / 捕获目录已清理。两个合成案例只能证明接线，不证明真实匹配质量。

## 运行边界与技术债

- 当前数据库为 PostgreSQL；服务不自动迁移。账号只能经 Google Gmail 验证与明确披露同意建立；合成账号仅用于测试 / demo。
- connect 为避免并发重复模型调用，在总预算内持有数据库事务 / 同键锁。候选上限超出明确报错；尚无跨请求全局限流及全局额度封顶。
- 候选取最新已完成版本，旧完成版本在刷新期间继续可用。模型输出保留来源标签与来源 metadata，但事实正确性没有独立自动评测保证。
- 通知为至少一次执行。Gmail API 没有本实现可依赖的服务商幂等发送键；服务商接受后、DB 确认前崩溃可能重复邮件。稳定 Message-ID 是追踪信息，不是 exactly-once。
- Event ID 跨重试不变；接收端须去重。无历史 replay，订阅过期期间漏掉的事件无法通过 cursor 恢复。投递前重查权限，但网络副作用不能与撤销实现数据库原子性。
- `/readyz` 检查配置与迁移，不远程测试 Google / Gmail / 模型，不证明 Worker 活跃。需要真实身份和公网 Host 的验收后才能对外开放。
- 没有用户自助删除 / 撤回同意工具、完整数据保留清理、生产限流 / 监控、模型质量评测集及密钥轮换运维流程。禁用账号、撤销快照所依赖的文件来源会阻止新的披露和后续通知；不自动删除历史记录。
- Fernet 密钥必须长期私密保存；丢失无法解密既存客户端 / 订阅记录。当前密钥轮换需专门迁移，不要直接换 Key。
- 既有历史 ADR / sources 保留原样；新 Gmail 决策只覆盖对应身份口径。

## Next steps

1. 按 [DEVELOPMENT](DEVELOPMENT.md) 配置 Google Web OAuth、Fernet 与精确 Host redirect allowlist，验收同一个 Gmail 在两个 Host 的登录及撤销。
2. 配置系统 Gmail 发信授权，用明确授权的测试收件 Gmail 验证 provider_accepted 与实际到达；目前 capture 已可用于本地开发。
3. 部署公网 HTTPS API 与独立 Worker，修改私有接入包的 MCP 地址，验收真实 Host 工具及 Events。
4. 在真实用户开放前补限流 / 额度总预算、撤回同意 / 数据删除、保留策略及可观察性；再做来源撤销和模型效果评测。

操作命令在 [DEVELOPMENT](DEVELOPMENT.md)，组件关系在 [ARCHITECTURE](ARCHITECTURE.md)，文件导航在 [CODEMAP](CODEMAP.md)。
