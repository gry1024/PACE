# ADR-0001: MVP 基线与初期实现选择

Status: Accepted
Date: 2026-10-07

## Context

用户授权自行选择适合初期跑通并能看到效果的方式，强调 docs / README 的 review 价值。本记录为当时已接受的 MVP 设计基线，包含尚待实现的决定；不构成当前完成度声明。实际状态见 [STATUS](../STATUS.md)，历史原文见 [产品快照](../sources/product-notion.md) 与 [开发快照](../sources/development-notion.md)。本次仅规范记录格式和导航，保留决定与日期。

## Decision

产品文档定义长期方向；开发文档有明确 Coding Freeze v2，因此 MVP 的具体行为以 Freeze 为准。原文快照保留差异，不直接重写远端 Notion。

| 差异 | 决策 | 代价 / 重新考虑条件 |
| --- | --- | --- |
| 最小信息 vs 丰富 Ontology | 导入用户授权文件，由 Server 构建 O；返回仅任务相关信息 | 本轮不做复杂隐私产品；公开推广前重审授权、存储和导出边界 |
| 多阶段检索排序 vs Jev | 先全量小池 + Choice Tournament | 分组依赖、中文和冗余上下文质量必须测；扩大池规模后评估召回 |
| 双向确认 vs 注册一次授权 | 实现注册授权；Match 即披露 Email 并通知 | 连接意愿与错误披露影响要收集；真实反馈决定是否增加逐次确认 |
| 候选中的 Demand | Demand ↔ Demand 合法 | 评测必须覆盖相互参与活动意愿，不能仅查 Supply |
| “匹配后重新读文件” | Host 重新读取，再调用 sync_entity；Server Worker 负责处理新输入 | Host 不在线时 Refresh 可延迟，不能谎称后台已重新读取 |

## 实现选择

1. **小网络先跑通**：校园羽毛球为首个试用入口，通用 Entity 和选择规则；补充跨场景回归，防止硬编码。
2. **可复现环境**：Python 3.12 + uv；官方 MCP Python SDK；FastAPI、PostgreSQL、SQLAlchemy / Alembic、TypeSafe Async SDK。
3. **固定模型基线**：Jev 使用 jev-1.13.0，记录模型版本、轮次和用量。服务端 Ontology LLM 由环境配置，不复制 Host 的模型策略。
4. **异步可靠交付**：使用 PostgreSQL 持久化工作任务与事务提交，Worker 执行 Ontology、Event、Email。初期不额外引入 Redis / Celery。
5. **最小基础设施扩展**：保留开发文档六类业务存储。可靠任务与登录 / OAuth 所需存储属于基础设施；允许附加 jobs、短期身份验证和 Token 状态，须在迁移与架构中标明。内存队列无法满足重启后恢复。
6. **身份**：默认选 Email 一次性验证码 / 登录链接 + MCP OAuth 授权码、PKCE。使用成熟库与官方 SDK 验证流程；部署时可替换为兼容 OIDC 的托管 IdP。不会让 Host 在业务 Tool 中传 Email 冒充身份。
7. **文件输入**：先 TXT / Markdown，由 Host 显式送入文本和 provenance；外链必须确认可访问，Server 不直接接受任意内网 URL。
8. **Refresh**：MCP 结果与 Plugin 指引提示 Host 在 connect 返回后重新收集并 sync；Server 处理和版本切换异步完成，失败不影响已有连接。
9. **交付语义**：匹配事务提交后返回 queued / not_subscribed 等真实状态。Worker 更新 accepted_by_receiver / provider_accepted / failed；没有证据不写“已向对方发送成功”。
10. **评测**：离线桩用于逻辑测试；真实模型合成集用于效果测量；真实 Host 联调用于协议验收；真人试用用于产品假设。四者分别报告。

## Tournament 的补足规则

开发文档确定四候选一组和每组 no_match，但未定义全部边界。默认工程规则：

- 以持久化候选 ID 的稳定顺序分组，可在评测时改变顺序。
- 每组 1–4 个真实候选加 no_match；最后不足四个直接使用实际候选数。
- 一个候选也须与 no_match 对比，不能不经判断直接匹配。
- 一个组选择 no_match 时仅淘汰该组；仍有其他组 Winner 时继续。
- 概率并列包含 no_match 时选择 no_match；候选间并列按稳定 ID 决定。
- 不跨组比较概率、不累乘为全局成功率；保留本轮概率与 confidence 作为诊断。
- 零候选直接 No Match；失败和上下文超限返回明确错误，不返回伪造 No Match。
- 首版不添加未经校准的 confidence 门槛或场景预过滤；如效果不达标，新增 ADR 说明调整。

## Consequences

Jev 无法达到硬冲突质量门槛、Tournament 对分组高度敏感、候选池扩大导致延迟 / 成本无法接受、Email 披露影响连接意愿、Host 无法支持预期文件或通知能力时，更新设计与验收，不在代码中悄悄引入另一套产品协议。
