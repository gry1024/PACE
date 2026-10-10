# ADR-0004: PA 直接画像、连接前同步与原生事件平台

Status: Accepted
Date: 2026-10-10
Supersedes: [ADR 0001](0001-mvp-baseline.md) 与 [ADR 0002](0002-code-framework.md) 中服务端构建 Ontology、文件输入、连接后刷新及 Worker 构建部分。身份继续遵循 [ADR 0003](0003-gmail-identity.md)。历史原文不重写。

## Context

用户要求最小 MVP、短且模块化的代码：用户在安装时完成 Google Gmail 注册和持续授权，PA 使用自身记忆为简短请求补充足够画像。PACE 只做 Jev Matching。通知必须同时面向 PA 与人类，不做 Agent 间对话，不适配无法接收事件 / 运行 PA 的平台。用户明确暂不做定时同步，只在每次连接前同步。

## Decision

1. 保持 sync_entity / connect 两个 Tool。PA 提交完整 ontology / demands / supplies，PACE 原样结构校验与保存，不用后端 LLM。D/S 仅来自已知明确意图，即时 Request 不自动成为长期 Demand。
2. 安装授权与订阅后先 sync 初始化入池，无需先发起连接；每次新连接前重新整理并同步，连接后与定时都不更新。内容变化新增版本，不变保持版本；同步立即 ready，connect 显式绑定 entity_version。远端是否重新读取记忆由 skill / Host 保证，版本检查只防止使用已过期的提交。
3. 全量替换比增量合并更简单，空值明确清除。O/D/S 共享 4000 UTF-8 bytes 预算，限制小池 Tournament 中的输入，长期列表各≤20条；Jev 总预算独立，超限显式报错。PA 在预算内保留尽量多的有用证据和硬约束，不由后端再压缩。
4. 持续同意覆盖自动同步、原文存储 / Jev 匹配、相关资料 / Gmail 披露和两种通知。升级同意版本，旧用户需重新同意；PACE 不加每次人审，但不能覆盖 Host 的记忆、工具、监控权限。一次安装目标需真实 Host 验证，不能用 skill 保证平台自动授权。
5. 使用官方 MCP Events webhook、持久订阅、challenge / Standard Webhooks 与独立系统 Gmail。Host 接收后按监控指令运行自己的 PA，只通知本人。优先 Work 网页 / 桌面 Cloud 和 dots；不支持平台不做适配，无轮询 / inbox / 自建调度 / A-to-A。候选必须有有效已验证订阅，提交前再查，失效不降级成仅邮件。
6. 安装 setup skill 指引 OAuth + 原生监控；平台须提供 callback / secret 并在期限前刷新。刷新订阅不是同步画像，也不意味着 PACE 安装即自动创建平台任务。
7. Worker 仅保留 email.send / event.deliver。不改写历史迁移，JSONB 与旧 files / sources / model 列保留；新版本标记 pa-entity-v1，旧构建格式不自动迁移、旧任务不会再调用模型。依赖锁暂不作无关升级或裁剪。
8. 为防止更新删除的资料继续披露，任何变化均使旧 matched 回执 / 待发送通知失去当前快照资格，即使只是新增事实。未变化同步不影响通知。历史不自动删除；后续保留 / 删除另行实现。

## Consequences

画像质量取决于 PA 可见的记忆与整理能力，后端不弥补；4000 bytes 预算需用真实场景评估。只在用户发起连接时刷新，被动候选可能长期不更新，日期与不确定性由 PA 记录，首版不设自动过期或定时任务。Webhook 接受不证明 PA 已运行；订阅过期没有 replay，平台执行、Google 登录和真实 Gmail 都需分别验收。完整替换可能停止尚未送达的旧通知，这换取简单且保守的披露边界。

当前实现与验证在 [STATUS](../STATUS.md)，具体契约 / 存储在 [INTERFACES](../INTERFACES.md)，人工准备在 [MVP 清单](../MVP_SETUP_CHECKLIST.md)。
