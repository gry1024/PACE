# PACE 开发文档 · 本地快照

- 来源：https://app.notion.com/p/3eff7be8670c803db15ee17a8a96ae5e?pvs=204
- 读取日期：2026-10-07（Asia/Shanghai）
- 源页面最后编辑：2026-10-07T08:55:06.027Z
- 状态：开发规范原文快照
- 格式：Notion enhanced Markdown；引用和图片未离线打包。
- 只读证据：变更本地决策请写 ADR，不要改写源文档。

---

Here is the result of "fetch" for the Page with URL https://app.notion.com/p/3eff7be8670c803db15ee17a8a96ae5e as of 2026-10-07T08:55:41.088Z:
<page url="https://app.notion.com/p/3eff7be8670c803db15ee17a8a96ae5e">
<ancestor-path></ancestor-path>
<properties>
{"title":"PACE 开发文档"}
</properties>
<iconMetadata>null</iconMetadata>
<content>
# PACE MVP 开发文档
<callout icon="🧭" color="blue_bg">
	**PACE 是跨平台 Connection Engine。**
	产品面向所有 Personal Agent 与支持 Plugin / MCP / Connector 的 AI 软件。当前开发优先按照 OpenAI 官方体系实现，但 Backend、账号、Entity Network 与 Matching 保持平台无关。
	一次完整连接链：
	**Email Account → File Ingestion → Ontology Build → Demand / Supply → Connection Request → Jev Selection → Match → 双端通知 → Ontology Update**
</callout>
核心开发均参考：[Dots](https://learn.chatgpt.com/docs/dots) · [OpenAI Plugins](https://developers.openai.com/plugins) · typesafe_sdk
---
# 1. Cross-platform Identity
用户通过 **Email** 注册 / 登录，同一用户无论从 Dots、ChatGPT、Codex、WorkBuddy 或其他 Personal Agent 接入，都绑定到同一个 pace_user_id，因此 Ontology、Demand、Supply 与历史 Match 支持跨平台。
注册 Email 同时作为第一版默认 Connection Contact 与 Email Notification 地址，不再额外设置 connection_contact。
---
# 2. Entity
PACE 中每个用户对应：
$$
E_i=(O_i,D_i,S_i)
$$
**Ontology** 是隐性的长期本体，尽可能丰富，包含用户的基本信息。**Demand / Supply** 是用户在发生连接的过程中进入 Connection Network 的显式信息。Demand 不只匹配 Supply；两个 Demand 也可以构成有效连接，例如运动搭子、交友、恋爱。
---
# 3. Ontology Build 与更新
第一次注册后先完成一次完整 Ontology Build。为用户搭建 ontology，方式：**文件读取。**
各 Host 按自身能力设计不同 File Collector：Dots / ChatGPT、Codex、WorkBuddy、未来 Desktop Personal Agent 可以有不同读取方式，但目标相同——在用户授权下读取当前平台可访问的文件、文档、Memory 文件或其他结构化文本资料，将原始内容或文件引用送入 PACE，PACE 用 LLM 提炼出 ontology。
统一链路：
**Platform File Reader → PACE Ingestion → Server LLM → Ontology**
Ontology 的抽取、合并、去重、归纳、版本控制全部由 PACE Server 完成，避免依赖不同 Host Agent 的语言行为。MVP 假设用户已授权 PACE 读取并保存相关信息，不考虑隐私问题。
第一次 Build 可以较慢。后续每次 Connection 使用最新 Snapshot 先完成 Matching，**匹配返回后**再启动 Ontology Refresh：重新读取当前平台可访问的文件，并结合本次 Request、Match 与后续 Outcome 生成新版本。
**Latest Ontology → Match → Read Files Again → New Ontology Version**
---
# 4. Request 与 Demand / Supply
用户向当前 Host 提出自然语言连接意图。Host Agent 需要判断这句话属于**一次即时连接**，还是**长期 Demand / Supply 登记**，并决定调用哪个 Tool。
如果用户是在要求“现在帮我完成一次连接”，调用 **connect**。例如：
> “今晚帮我找个人唱 KTV。”
这类 Request 只作为本次 Selection 输入和历史记录，不自动写入长期 Demand / Supply。Host 可以补充当前时间、位置或其他与本次 Request 直接相关的上下文，但不承担 Ontology Build 和 Matching；PACE 仍以 Server 中最新的 Ontology / Demand / Supply 完成统一 Selection。
如果用户是在表达长期需求或长期供给，调用 **sync_entity**。例如“以后周末都想找羽毛球搭子”属于长期 Demand；“我有一块周六晚上的场地可以出”属于长期 Supply。
如果一句话同时包含即时连接与长期登记，Agent 可以分别调用 connect 和 sync_entity。PACE 不设计 Request 自动转化为 Demand / Supply 的规则。
---
# 5. Matching
当用户对Personal agent说了一句话，发起一个 request，服务器会做match。 <mention-page url="https://app.notion.com/p/3f0f7be8670c80dcb7dff6c5a87d2c12"/> 
**(Request, Requester Entity, Candidates) → Jev Choice → Top-1 / No Match**
每次 Choice 包含 no_match。Request 是唯一主目标，Ontology / Demand / Supply 是 evidence；模型负责从冗余、缺失、跨场景信息中识别真正相关内容，并理解 hard requirement 与 soft preference。
筛选采用 **4-way Tournament**：每次 4 个 Candidate + no_match，每组仅保留 Top-1，逐轮淘汰直到得到唯一 Winner 或全部淘汰（no_match）。
---
# 6. Match 后呢
筛选算法匹配成功后，双端通知。
第一版不做 per-match Accept / Reject，也不做 A2A negotiation。
注册时用户一次性同意：如果自己被 PACE 选为匹配对象，PACE 可以把自己的**注册 Email**提供给对方，并向自己发送完整 Connection Notification。
匹配成功后，需求方立即得到与当前任务相关的 Candidate 信息、Candidate 注册 Email，以及“已向对方发送连接通知”的状态。被匹配方同时收到 PACE 的 MCP Event 与 Email，内容包含 Request 摘要、申请方与本次任务相关的信息以及申请方注册 Email。
因此第一版连接协议就是：
$$
Request
→
Match
→
Return\ Result
+
Notify\ Counterpart
$$
PACE 不等待另一端确认，也不自建聊天。后续是否加入 per-match consent、A2A 或临时 Relay，由真实用户反馈决定。
---
# 7. MCP Tools 与 Events
OpenAI 侧严格按照 [Plugins](https://developers.openai.com/plugins) 与 [Dots](https://learn.chatgpt.com/docs/dots) 开发。Plugin 是安装 / 分发单元，MCP Server 提供实时数据和动作，Dots 可以使用安装后的 Plugin 并监听支持的 Events。
只设计两个 MCP Tool：
<table fit-page-width="true" header-row="true">
<tr>
<td>Tool</td>
<td>职责</td>
</tr>
<tr>
<td>sync_entity</td>
<td>同步首次 Ontology Build、后续 Ontology 更新，以及用户明确表达的长期 Demand / Supply。</td>
</tr>
<tr>
<td>connect</td>
<td>提交一次即时 Connection Request；直接执行 Selection 并返回 Match / No Match，不修改长期 Demand / Supply。</td>
</tr>
</table>
对于被匹配方的场景，定义一个 Event：**connection.matched**。
Event 用于 PACE 在匹配成功后主动通知被匹配方。Event 不是 Tool。Tool 用于 Host 主动调用 PACE；PACE Server 按 MCP Events 协议实现 events/list、events/subscribe、events/unsubscribe。
connection.matched 直接携带本次连接所需的最小完整信息，包括 connection_id、Request、申请方与本次任务相关的信息以及申请方注册 Email，因此第一版不再设计 get_connection。
---
# 8. 最小数据模型
第一版 PostgreSQL 只保留：accounts 保存 pace_user_id + email + host bindings；entities 保存当前 Ontology / Demand / Supply；entity_versions 保存历史 Ontology；connection_requests 保存每次即时 Connection Request；matches 保存匹配结果与双方 Email snapshot；event_subscriptions 保存 MCP Event callback；后续再增加 outcomes。
不建立 Offer、Session、Chat、Graph、Reputation 等对象。
---
# 9. Backend
PACE Backend 保持平台无关：
**Platform File Reader / Plugin / MCP → PACE API → Account + Ontology Store → Jev Tournament → Match Store → MCP Event + Email**
当前开发栈：Python + FastAPI + Official Python MCP SDK + PostgreSQL + TypeSafe Async SDK。服务器端 LLM 负责 Ontology Build / Refresh；后台 Worker 只负责 Ontology Refresh、Event Delivery 与 Email。
不同 Host 只需要实现自己的 **File Reader / Auth Binding / Delivery Adapter**，不复制 Matching 与 Entity Network。
---
# 10. Coding Freeze v2
<callout icon="✅" color="green_bg">
	**身份：Email Account + stable pace_user_id。**
	**Ontology：各平台只负责读取文件；PACE Server 统一用 LLM 构建和更新。**
	**Demand / Supply：只保存用户明确表达的长期需求 / 供给；即时 Request 不自动写入 Entity。**
	**Matching：Jev Choice + no_match + 4-way Tournament。**
	**Connection：Match 即返回对方相关信息与注册 Email，同时通过 MCP Event + Email 通知被匹配方；第一版无 Accept / Reject。**
	**No Match：只表示本次即时 Request 没找到对象；不产生 Pending Demand，也不修改长期 Demand / Supply。**
	**MCP：sync_entity、connect；Event：connection.matched。**
</callout>
</content>
</page>
