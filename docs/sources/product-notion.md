# PACE 产品说明 · 本地快照

- 来源：https://app.notion.com/p/3eff7be8670c8022bc85c2b198a4a952?pvs=204
- 读取日期：2026-10-07（Asia/Shanghai）
- 源页面最后编辑：2026-10-07T11:08:11.953Z
- 状态：产品规范原文快照
- 格式：Notion enhanced Markdown；引用和图片未离线打包。
- 只读证据：变更本地决策请写 ADR，不要改写源文档。

---

Here is the result of "fetch" for the Page with URL https://app.notion.com/p/3eff7be8670c8022bc85c2b198a4a952 as of 2026-10-07T11:08:11.953Z:
<page url="https://app.notion.com/p/3eff7be8670c8022bc85c2b198a4a952">
<ancestor-path></ancestor-path>
<properties>
{"title":"PACE 产品说明"}
</properties>
<iconMetadata>null</iconMetadata>
<content>
# PACE｜Cross-Platform Connect Engine
<callout icon="🌐" color="blue_bg">
	**一句话定义：Personal Agent 负责“理解我、替我行动”，PACE 负责“替我的 Agent 找到正确的人、商品或服务，并建立连接”。**
</callout>
PACE（Personal Agent Connection Engine）是面向 Personal Agent 时代的跨平台连接层。它不做 Coding、办公、PPT 等通用 Agent 能力，而专注于一个更底层的问题：**当 Agent 已经理解用户之后，它如何在全网找到最合适的连接对象？**
我们的核心判断是：未来大量社交、消费和服务需求，本质上都会变成 Agent 发起的“连接请求”。今天的 Personal Agent 仍然需要逐个平台搜索、调用 API、操作网页、与平台或其他 Agent 多轮交互；PACE 希望把这一过程抽象成统一的连接基础设施。
PACE 的四个核心特征是 **Non-human Connection、Non-generative Connection、Cross-platform、Selection Algorithm**。长期目标不是再造一个垂直平台，而是让 Personal Agent 的单次连接边际成本趋近于零，并逐步成为社交、消费、服务领域的连接引擎。
---
# 1. 产品本质
## 1.1 我们解决什么问题
Personal Agent 的核心能力可以拆成两层。
**第一层：Understand & Act。** Agent 理解用户是谁、偏好什么、正在做什么，并代表用户执行任务。Memory、Profile、Wiki、长期上下文、Browser / Computer Use、Tools 都属于这一层。
**第二层：Connect。** 当任务需要“另一个人、一个商品、一个服务提供者、一个商业机构”时，Agent 必须在外部世界寻找合适对象并建立连接。
PACE 只做第二层。
因此，我们不是另一个 Personal Agent，也不是另一个电商、社交或本地生活平台。我们希望成为这些 Agent 共同调用的 **Connection Backend**。
关联调研：<mention-page url="https://app.notion.com/p/3edf7be8670c8050ac8acc65c4d59d6f"/>
## 1.2 三个核心定义
### Non-human Connection
连接的发起者从“人”变成“Agent”。用户表达目标后，Personal Agent 代表用户形成需求、寻找对象、比较、筛选，并在必要时与对方 Agent 建立连接。
最终连接仍然服务于人，但**连接过程本身越来越不需要人类亲自搜索和筛选**。
### Non-generative Connection
PACE 不希望每一次匹配都依赖多个 LLM 在开放互联网中搜索、阅读、对话和反复推理。
我们的思路是：Personal Agent 提供与当前需求有关的用户信息和 Request，PACE 将其结构化，进入 Connection Network，通过召回、约束过滤和排序完成匹配。LLM 可以出现在输入理解、字段抽取等边缘环节，但**核心匹配路径应尽可能是非生成式的检索与筛选系统**。
目标是让连接从“每次重新生成和搜索”变成“在持续积累的网络上快速查询”。
### Cross-platform
PACE 不绑定某一家 Personal Agent。Muse、Instinct、Town、未来的其他 Personal Agent，都可以通过 Plugin / API / Agent-to-Agent Interface 调用同一连接网络。
如果连接网络只能服务一个 Agent，它只是产品功能；只有跨平台，它才可能成为基础设施。
---
# 2. 需求侧分析
## 2.1 需求本质：用户 × 场景 × 动机
PACE 的需求不是抽象的“Agent 要连接”，而是：
**某类用户，在某个具体场景下，因为连接成本过高，希望 Agent 替自己完成寻找和筛选。**
最初的用户是 Personal Agent 用户。最初的场景应该是 **C2C 单任务连接**：两个原本互不认识的人，因为一件具体事情产生一次连接，任务结束后连接可以结束。
这类需求与传统“建立长期社交关系”不同。它更像临时、即时、目标明确的匹配。例如找一个特定的人完成一次交流、协作或线下活动。真正要验证的不是“人有没有社交需求”，而是：
> **是否存在一批连接需求，今天因为搜索、筛选、沟通成本太高而没有发生，但在 Agent 代替人完成这些成本后会被释放出来？**
长期可以从 C2C 延伸到 C2B、B2C、B2B。社交、购物、购买服务，在 PACE 的视角里都可以统一成“从需求方到合适供给方的连接”。
## 2.2 体验上的关键要素
<table fit-page-width="true" header-row="true">
<tr>
<td>关键要素</td>
<td>用户真正感知到的问题</td>
<td>PACE 的突破方向</td>
</tr>
<tr>
<td>匹配质量</td>
<td>不是“能搜到”，而是是否真的适合我当前的具体需求</td>
<td>Ontology / User Model + Request 结构化，多阶段召回、约束过滤和排序</td>
</tr>
<tr>
<td>连接成本</td>
<td>为了一个小需求，不值得自己搜索、浏览、比较、聊天几十分钟</td>
<td>核心匹配非生成式化，让一次连接成为低延迟、低计算成本查询</td>
</tr>
<tr>
<td>跨平台</td>
<td>供给和用户散落在不同 Agent、平台和生态中</td>
<td>统一 Plugin / API / A2A 接口，把不同 Personal Agent 接入同一个 Connection Network</td>
</tr>
<tr>
<td>隐私与控制</td>
<td>用户不愿把完整长期记忆交给陌生第三方</td>
<td>默认不上传完整 Memory，只交换当前匹配所需的最小化结构化信息，并由用户 / Agent 控制授权范围</td>
</tr>
<tr>
<td>信任与安全</td>
<td>匹配成功不等于敢于建立真实连接</td>
<td>身份、信誉、权限、双向同意和连接后的反馈机制</td>
</tr>
<tr>
<td>网络密度</td>
<td>没有足够候选对象，再好的算法也没有意义</td>
<td>从一个窄场景、一个小地理区域做高密度冷启动，而不是一开始覆盖所有连接</td>
</tr>
</table>
## 2.3 竞品与替代方案
### Personal Agent：最重要的合作方，也是潜在竞争者
Muse、Instinct、Town 等 Personal Agent 的核心资产是用户入口、长期上下文和执行能力。它们会不断增强“连接外部世界”的能力，但今天主要仍依赖现有平台、Tools、Browser / Computer Use、第三方 API 等方式完成任务。
PACE 与它们最合理的初始关系不是替代，而是**补全其 Connection 能力**：Agent 负责理解用户，PACE 提供跨平台的候选网络和匹配结果。
真正的长期竞争问题是：Personal Agent 是否会自己建立这样的 Connection Network。PACE 要成为独立赛道，必须让跨平台网络本身的价值大到任何单一 Agent 都更愿意接入，而不是重复建设。
### 传统垂直平台：供给强，但连接被切成孤岛
社交、电商、本地生活、招聘、旅行等平台已经拥有巨大的供给、交易和信誉体系。它们的问题不是“没有供给”，而是每个平台只优化自己的封闭场景，且连接过程仍以人为主要操作对象。
传统平台的替换成本非常高，因此 PACE 初期不应把“摧毁所有平台”作为 GTM 前提。更现实的路线是先证明：**在某些单任务连接中，一个跨平台、Agent-native 的匹配层可以创造传统平台无法提供的体验。**
如果未来供给方愿意直接把产品、服务和可连接信息同步到 PACE，PACE 才可能逐步从“聚合连接层”走向“原生连接网络”。
### 生成式搜索 / Agent 多轮协商：灵活，但成本结构不同
生成式方案的优势是无需预先建立统一数据结构，可以面对开放世界问题临时搜索和推理。但如果大量高频连接都依赖 LLM 搜索、浏览、多轮 Talking 与比较，其延迟、计算成本和稳定性都会成为问题。
PACE 的核心赌注是：**连接是一类足够高频、足够结构化的问题，值得被单独做成一个非生成式基础设施。**
## 2.4 Why NOW：需求侧发生了什么变化
以前，人是互联网连接的主要操作主体。人自己搜索网页、打开 App、筛选商品、浏览商家、发送消息。
Personal Agent 出现后，用户正在逐步把“理解需求 + 执行任务”交给 Agent。随着 Memory、长期 User Model、Tools 和持续在线能力成熟，Agent 会越来越清楚“我要什么”。
这会产生新的瓶颈：
> **当 Agent 已经知道我要什么以后，它能不能低成本地找到全网最合适的另一端？**
任务越复杂，Personal Agent 对外部平台、工具和真实数字环境的连接能力要求越高。连接正在从 Agent 的附属能力，变成决定最终体验上限的关键能力。
因此 PACE 的 Why NOW 不是“LLM 更强了”，而是 **Personal Agent 开始长期存在于用户身边，连接请求开始有机会从 Human-operated 变成 Agent-operated。**
## 2.5 需求大小
可以把潜在市场拆成：
**市场规模 ≈ 需求广度 × 需求强度 × 需求频度**
需求广度非常大，因为“找人、找商品、找服务”覆盖了大量互联网活动；需求强度取决于当前连接摩擦有多大；需求频度则因场景差异极大。
现阶段不应该急于给出一个宏大的 TAM 数字。对 PACE 更重要的第一性验证是：
1. 是否存在高密度的单任务连接需求；
2. 用户是否愿意把这些需求交给 Agent；
3. 非生成式匹配是否能显著降低成本，同时保持匹配质量；
4. 当网络规模扩大时，连接成功率和用户价值是否随网络密度明显提升。
### 它会不会成为独立赛道？
这是 PACE 最重要的战略问题。
如果“连接”只是 Personal Agent 的一个普通 Tool，那么最终会被大 Agent 平台内部化。
如果跨平台 Connection Network 能形成独立的数据网络、匹配网络和供需网络，使得 **接入 PACE 比任何单一 Agent 自建连接网络都更有效**，那么它才可能成为独立基础设施。
因此，PACE 能不能独立存在，最终取决于网络效应，而不是单纯取决于匹配算法。
---
# 3. 供给侧分析
## 3.1 可能形成壁垒的关键要素
**第一，Connection Network 的密度。** 一个场景里可连接的人和供给越多，匹配越容易成功；成功率越高，又越能吸引更多需求和供给。这是最核心的潜在网络效应。
**第二，跨 Personal Agent 的分发与接入。** 如果 PACE 能成为多个 Personal Agent 默认调用的 Connection Layer，就能获得稳定的需求入口。这比单独做一个面向 C 端的新 App 更有战略价值。
**第三，真实连接结果形成的数据飞轮。** “用户最终选了谁、连接是否成功、为什么拒绝、任务是否完成”会比静态 Profile 更有价值。长期排序模型的核心资产应当是 Outcome Data，而不是简单的向量数据库。
**第四，信任、身份与信誉层。** 当连接从信息推荐走向真实的人与商业交易时，谁是真人、谁有资格提供服务、历史连接质量如何，会成为网络基础设施的一部分。
**第五，结构化标准。** 如果 PACE 能逐步形成一套被 Agent 和供给方接受的 Request / Profile / Supply Schema，它会降低所有参与方接入网络的成本。
## 3.2 不构成长期壁垒的要素
LLM 本身、Embedding、Vector Database、普通 RAG、一个 Plugin、一次性的匹配算法实现，都很难单独形成护城河。
这些是构建 PACE 的必要技术组件，但不是公司价值本身。
真正的壁垒应该沉淀在：**网络、分发、连接结果数据、信任体系和标准。**
## 3.3 Why ME
“这个方向成立”和“我们能赢”是两个不同问题。
产品逻辑本身不能证明 Why ME。团队最终必须在以下至少一项上建立明显优势：最早建立某个高密度 C2C 网络；最快拿到多个 Personal Agent 的入口；对非生成式 Matching 有明显算法 / 数据优势；拥有特殊的供给侧资源；或者能定义并推动跨 Agent 的连接标准。
**这一部分目前仍需要结合团队能力、资源和第一批可获得用户进一步补充。**
## 3.4 Why NOW：供给侧发生了什么变化
供给侧最大的变化是，Agent 生态正在把过去只能由大型平台内部完成的能力模块化。
Personal Agent 不需要拥有所有服务本身，它可以调用 Tool、Plugin、API 和其他 Agent。只要跨 Agent 调用逐步标准化，Connection 就有机会被拆成一个独立能力层。
与此同时，Embedding、结构化检索、向量召回、学习排序等技术已经足以支撑低成本 Matching。真正困难的部分从“能不能实现一个匹配算法”，转向“能不能建立一个足够密集、可信、跨平台的连接网络”。
---
# 4. 产品机制
## 4.1 核心链路
**Personal Agent → PACE Adapter（Plugin / API / A2A）→ Request Normalization → Connection Network → Candidate Retrieval → Constraint Filter → Ranking → Consent & Trust → Connection → Outcome Data → 反哺 Ranking。**
这个架构里，**LLM 可以帮助理解自然语言，但不应该成为每次匹配的主要计算路径。**
## 4.2 Ontology 在 PACE 中的角色
Ontology / User Model 是 Personal Agent “懂用户”的基础，但 PACE 不需要复制 Personal Agent 的全部 Memory。
更合理的原则是：
**Personal Agent 保留完整用户上下文；PACE 只接收当前连接所需的最小信息。**
例如一次匹配真正需要的可能只是位置、时间、目的、预算、偏好、约束、可信度要求等。PACE 将这些信息转为标准化 Request，与 Connection Network 中经过授权的候选信息进行匹配。
这样既能利用 Personal Agent 对用户的理解，又避免 PACE 变成一个必须集中存储所有人完整私有 Memory 的系统。
## 4.3 “非生成式”具体意味着什么
PACE 的非生成式不是“完全不用 LLM”，而是：
> **把一次连接最贵、最频繁的核心循环，从 LLM 多轮搜索与协商，变成数据库 / 向量索引 / 约束过滤 / Ranking 的查询问题。**
典型流程是：
**自然语言需求 → 结构化 Request → 候选召回 → 硬约束过滤 → 多目标排序 → 返回 Top-K → 双向确认。**
这使得网络规模扩大后，单次连接的主要成本可以保持很低，而不是随着每一次任务重新进行大规模生成式推理。
---
# 5. Go-to-Market：为什么从 C2C 开始
PACE 的长期愿景很大，但起点必须极窄。
第一阶段只做 **一个 C2C 单任务连接场景 + 一个小地理区域**。不是因为 C2C 是最终市场最大，而是因为这是验证 Connection Engine 是否真正创造新连接的最直接方式。
首个场景应该满足几个条件：当前寻找和筛选成本明显；匹配维度不止一个关键词；用户有明确的即时动机；传统平台体验不够好；在一个局部区域可以快速形成候选密度；任务结束后可以清晰判断连接是否成功。
场景本身目前仍应继续筛选，不宜过早把公司绑定在某个具体社交品类上。
### Phase 1｜C2C：证明连接本身有价值
建立高密度的小网络，验证非生成式 Matching、连接成功率、用户授权与双向确认机制。
### Phase 2｜Cross-platform：成为 Personal Agent 的 Connection Plugin
让不同 Personal Agent 都可以调用 PACE。用户不需要迁移到 PACE App，PACE 在后台成为统一连接层。
### Phase 3｜C2B / B2C：让供给直接进入 Connection Network
商家、服务提供商、机构把产品、服务、可用时间、价格、能力和约束以 Agent-operatable 的形式同步到 PACE。
此时 Personal Agent 不再必须先进入淘宝、京东、携程或某一个垂类平台再寻找供给，而可以直接向 Connection Network 发起需求。
### Phase 4｜B2B：成为通用 Connection Infrastructure
当需求侧 Agent 与供给侧数据都足够丰富后，PACE 才有机会成为跨社交、消费、服务与交易的连接基础设施。
---
# 6. 商业模式
商业模式不应先于网络价值确定，但可以保留三类假设。
**第一类：Connection API / Infrastructure Fee。** Personal Agent 平台向 PACE 购买连接能力，类似基础设施服务。
**第二类：B 端连接价值收费。** 当 PACE 能稳定为商家或服务提供者带来高质量需求，可以按有效 Lead、成交或服务订阅收费。
**第三类：交易基础设施收入。** 如果未来连接进一步覆盖预约、支付、履约，可以在交易层形成收入。
早期最重要的不是最大化单次连接收入，而是验证：**连接量越大，网络价值是否越强，同时单次连接成本是否持续下降。**
---
# 7. 战略定位：改良还是原生网络
现有 Personal Agent 大多通过连接已有互联网平台来增强能力。这是一条非常现实的路线：保留现有平台的供给、交易、信誉和履约体系，只让 Agent 代替人操作。
PACE 更长期的设想是另一层：**不仅让 Agent 更容易操作现有互联网，而是建立一个本身就是为 Agent 连接而设计的供需网络。**
这两条路线在早期并不冲突。PACE 可以先作为现有生态的连接增强层存在；只有当大量人、商家、产品和服务愿意以 Agent-operatable 的形式直接进入 Connection Network 后，才可能逐步形成原生生态。
因此，“革命”是长期结果，不应该成为早期产品成立的前提。
---
# 8. 目前最关键的假设与风险
### 1. Connection 是否真的是一个独立问题？
需要证明 Personal Agent 自己做连接的体验明显不足，而且多个 Agent 愿意共同调用第三方 Connection Layer。
### 2. C2C 冷启动是否能解决？
连接产品的价值高度依赖候选密度。首个场景和首个地理区域的选择，会直接决定产品能否跨过冷启动。
### 3. 用户是否愿意提供足够的信息用于匹配？
如果必须上传完整 Memory 才能获得高质量匹配，隐私阻力可能非常大。因此必须验证“最小必要信息”能否支撑足够好的匹配。
### 4. 非生成式 Matching 的质量是否足够高？
低成本没有意义，如果最终匹配明显差于生成式搜索 / 人工搜索。核心技术验证应同时测 **质量、延迟、成本、成功率**。
### 5. Personal Agent 平台为什么不自己做？
PACE 必须依靠跨平台网络效应建立“接入比自建更划算”的结构性优势。
### 6. 传统平台是否愿意开放？
早期不应把平台开放作为必要条件。PACE 首先要有自己能控制的 C2C 网络，之后再逐步引入 B 端和外部供给。
---
# 9. 当前需要继续回答的问题
## 产品
第一个 C2C 单任务场景到底是什么？它必须同时满足高连接摩擦、高局部密度、可量化成功结果、传统产品解决得不好。
Plugin / API / A2A 的最小接口怎样定义？Personal Agent 到底向 PACE 暴露哪些字段，PACE 又返回什么？
非生成式 Matching 的第一版算法怎样设计？哪些信息做 hard constraint，哪些进入 embedding retrieval，哪些进入 learning-to-rank？
## 网络
第一批用户从哪里来？为什么他们会同时出现在同一个小网络里？
如何设计身份、信誉、双向授权和拒绝机制，避免“高匹配率但低连接意愿”？
## 商业
长期更像面向 Personal Agent 的基础设施公司，还是一个自己掌握供需网络的平台？
当 C2B 开始以后，是按 API、Lead、成交还是 SaaS 收费？
## 战略
PACE 的中立跨平台身份能否成为优势，还是最终会被某个超级 Personal Agent 内置？
哪些数据必须属于 PACE，才能形成不可替代的网络效应？
---
# 10. 30 秒版本
**PACE 是 Personal Agent 时代的 Connection Engine。**
Personal Agent 越来越懂用户，但当用户需要找到另一个人、一个商品或一个服务时，Agent 仍然要在割裂的平台之间搜索、浏览、调用 API，并进行昂贵的生成式交互。
PACE 作为跨平台 Plugin / API 接入不同 Personal Agent，把用户的当前需求转成结构化 Request，在统一的 Connection Network 中通过非生成式召回、过滤和排序找到最合适的另一端。
我们从一个小区域、一个 C2C 单任务场景起步，先建立高密度连接网络；随后开放 B 端供给和更多 Personal Agent 接入，最终希望成为社交、消费和服务领域的跨平台连接基础设施。
> **Personal Agent owns the user. PACE owns the connection.**
</content>
</page>
