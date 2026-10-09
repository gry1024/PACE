# Personal Agent · 本地快照

- 来源：https://app.notion.com/p/3edf7be8670c8050ac8acc65c4d59d6f?pvs=204
- 读取日期：2026-10-07（Asia/Shanghai）
- 源页面最后编辑：2026-10-07T05:23:50.318Z
- 状态：源页面已标记 deleted；已读正文，内嵌图片未作证据
- 格式：Notion enhanced Markdown；引用和图片未离线打包。
- 只读证据：变更本地决策请写 ADR，不要改写源文档。

---

Here is the result of "fetch" for the Page with URL https://app.notion.com/p/3edf7be8670c8050ac8acc65c4d59d6f as of 2026-10-07T05:23:50.318Z:
<page url="https://app.notion.com/p/3edf7be8670c8050ac8acc65c4d59d6f" deleted>
<ancestor-path></ancestor-path>
<properties>
{"title":"Personal Agent"}
</properties>
<iconMetadata>null</iconMetadata>
<content>
# 1. 产品地图
[Messaging Agents](https://messagingagents.com/)：一个网站，汇总了广泛的 Personal Agent 产品，并按交互方式、能力与特征进行分类。
# 2. 使用场景
- **Level 0｜信息与轻量事务**：邮件处理、定时任务、备忘提醒、信息检索。
- **Level 1｜单一事务执行**：监控机票价格、购物、预订酒店、退款等。
- **Level 2｜长链路与多平台任务**：接入植物护理工具帮助家庭管理花园；求职流水线，包括寻找新岗位、匹配简历与 JD、填写申请表单等。
> **随着任务复杂，Personal Agent 对外部平台、工具和真实数字环境的连接能力要求上升。**
<empty-block/>
# 3. 产品价值
从底层架构看，Muse、Instinct 等 Personal Agent 与 OpenClaw 并没有本质上的范式差异：核心仍然是 **LLM/VLM + Agent Runtime + Memory + Tools + Browser/Computer Use + Scheduler**。
一个懂技术的人对openclaw、hermes进行专业配置，能完成当前personal agent所宣传的大部分任务。
**基础 Agent Stack 本身很难形成长期护城河**。真正的差异更多来自产品化能力：默认可用的云端运行环境、长期记忆、账号与凭据管理、外部平台连接、稳定性、安全权限，以及面向普通用户的低门槛交互。
Muse与Openclaw的相似性：
![](notion-file-block://3edf7be8-670c-80b5-8bc1-e273705e6a4e/2a90661a-7438-4c93-9dbe-80a8d12ea1d1?space_id=bbef7be8-670c-8157-8a2d-00033ce15e84&name=image.png)
[Meta 承认 Muse 与 OpenClaw 的相似性并非偶然｜TechCrunch](https://techcrunch.com/2026/09/22/meta-admits-muses-likeness-to-openclaw-isnt-a-coincidence/)
![](notion-file-block://3edf7be8-670c-805a-a171-e18693d55910/d99002f0-4635-4258-851f-505630fec3ff?space_id=bbef7be8-670c-8157-8a2d-00033ce15e84&name=e7075e5ef07c3c3475b605519e3c6ca1.jpg)
## 3.1 易用性
**开箱即用、长期在线、低学习成本**。
![](notion-file-block://3edf7be8-670c-80c7-b4d8-df968c229e64/dca1411d-0e7e-4b49-9eeb-09e0f4386b7a?space_id=bbef7be8-670c-8157-8a2d-00033ce15e84&name=image.png)
[我在 Muse 平台上创建的一些实用工具：r/MetaAI --- Useful things I’ve set up with Muse : r/MetaAI](https://www.reddit.com/r/MetaAI/comments/1wk92xe/useful_things_ive_set_up_with_muse/)
![](notion-file-block://3edf7be8-670c-80ec-8f35-fbd79327fb4e/3f329945-9a9a-4167-90ff-7b6e2e94e10f?space_id=bbef7be8-670c-8157-8a2d-00033ce15e84&name=cce2c156135006399cb9205030ec1c70.jpg)
![](notion-file-block://3edf7be8-670c-8094-9adc-f552e875b52e/ee41df6e-506f-48ae-a2ae-9ae8ef9a3d12?space_id=bbef7be8-670c-8157-8a2d-00033ce15e84&name=5595dd2aee6ecb1a3a74631e799a695a.jpg)
<empty-block/>
# 4. Context 与 Memory：长期 Personal Agent 的核心瓶颈
随着交互、任务和外部信息不断累积，系统必须持续判断：什么应该进入长期记忆、什么已经过时、什么只属于当前任务，以及在什么时候检索哪些记忆。处理不好就会出现 context 污染、规则遗忘、旧信息干扰和重复犯错。
> **短任务的关键是模型能力；长期 Personal Agent 的关键之一，是能否稳定维护用户上下文。**
![](notion-file-block://3edf7be8-670c-8056-aa4d-e603853ec5a8/d3199123-0a12-486b-b58d-6697e6c512a7?space_id=bbef7be8-670c-8157-8a2d-00033ce15e84&name=image.png)
![](notion-file-block://3edf7be8-670c-80af-8385-cbc3b9460cbb/486bea1c-e378-47ff-8236-2e2bb743e2ad?space_id=bbef7be8-670c-8157-8a2d-00033ce15e84&name=image.png)
[真实用户反馈：It was great… until it wasn’t｜Reddit](https://www.reddit.com/r/MetaAI/comments/1wpdcdd/it_was_great_until_it_wasnt/)
# 5. 如何“理解用户”
- **Town**：从 Google / Outlook 自动生成并持续更新可编辑 **Profile + Wiki**，沉淀身份、联系人、项目、偏好、写作习惯和工作方式。  
	[Town Profiles](https://www.town.com/docs/features/profiles) · [Town Wiki](https://cf-vercel.town.com/docs/features/wiki)
- **Muse**：从对话和已连接数据中形成长期 **Memory**，记住对用户重要的信息，并在之后的任务中复用。  
	[Introducing Muse](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/)
- **Instinct**：通过 email、messaging、screen、audio、location 等长期个人上下文理解用户；官方未公开具体 User Model 结构。  
	[Instinct](https://instinct.com/)
- **ChatGPT**：通过历史聊天、Memory、文件和连接应用维护长期用户上下文，并在后续对话中调用。  （在User/.codex/MEMORY.md可以看到codex怎么认识你）
	[Memory in ChatGPT](https://help.openai.com/en/articles/8590148-memory-in-chatgpt)
# 6. 外部连接：决定 Personal Agent 的能力上限
**平台连接能力是决定 Personal Agent 实际体验的关键因素。**
和多平台丝滑连接，处理好授权和凭据问题。（不仅仅是gmail、calendar，而包括各种app、网页、小程序…)。服务商愿不愿意开放接口。
对于computer use：低效，长远来看 agent-operatable Web才是合理范式
<empty-block/>
![](notion-file-block://3edf7be8-670c-80a5-87dd-effd3fcc94f1/180679f1-008a-41c8-8d30-cc7077073c4b?space_id=bbef7be8-670c-8157-8a2d-00033ce15e84&name=72bb61e0d103d7ad36819daf36a9df05.jpg)
#
<empty-block/>
<empty-block/>
</content>
</page>
