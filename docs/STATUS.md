# 当前实现状态

## Current Snapshot

复核日期：2026-10-10（Asia/Shanghai）。本页描述当前工作区实现，当前产品决策见 [ADR 0004](decisions/0004-pa-profiles-and-event-hosts.md)。

阶段：**初期公网基础设施已部署；Google 用户登录与真实 Host 闭环尚未验收**。PA 直接整理完整 O/D/S，安装初始化一次，此后只在每次连接前同步；同步立即 ready，connect 绑定版本，后端仅用 Jev Matching。Worker 只投递 MCP Events 和 Gmail；无后端 Ontology LLM、定时画像同步、A-to-A 或不支持事件平台适配。

目标为 ChatGPT Work 网页 / 桌面 Cloud 与 dots 的原生事件能力。Google Gmail OAuth、系统 Gmail、MCP Events 已有代码和离线边界验证；**真人 Google 登录、真实 Gmail 收件、平台 Events 实际触发 PA、插件安装仍未验收；公网首页 / 健康检查及独立数据库迁移已验收**。安装引导存在不代表平台任务已自动创建，一次授权无逐次确认的体验仍受 Host 权限限制。

原私有 env / 凭据保留，后端忽略旧 OPENAI_* / ONTOLOGY_*。本地数据库可用；系统 Gmail 发件凭据已写入私有配置并通过本地读取校验；Google 用户登录客户端已配置，公网 origin 为 https://clawcrony.com；真人登录与 Host 回跳仍待验收，见 [人工清单](MVP_SETUP_CHECKLIST.md)。当前 EMAIL_DELIVERY_MODE=capture，不会真实发送邮件。

## 功能完成度

Implemented = 实现与相应本地验证路径存在；Partial = 实现存在但关键外部路径未验收；Planned = 尚无实现。Implemented 不等于生产运行效果或服务商凭据已验证。

| 能力 | 状态 | 证据 / 实际边界 |
| --- | --- | --- |
| 固定两项 MCP Tool、官方 transport | Implemented | 官方 SDK 发现 / sync / connect / scope 测试；Events 扩展没有增加业务 Tool |
| PA 完整 O/D/S 直接发布 | Implemented | 全量替换、空值清除、UTF-8 预算；不推断或提炼；无构建任务 |
| 幂等同步、内容无变化 / 乐观版本 | Implemented | 同账号锁、同键载荷冲突、原回执重放、不变不增加版本 |
| 连接前版本绑定与候选资格 | Implemented | connect.entity_version；当前非空 PA 快照 / 当前同意 / 验证 Gmail / 有效事件订阅 |
| 四候选淘汰赛与 No Match | Implemented | Tournament + Jev Adapter；概率仅组内；错误不变成 No Match |
| 持久 connect / Match / 双通道 outbox | Implemented | 同键 advisory 锁、提交前重查双方 / 订阅、原子入队、模型失败留 failed |
| 请求相关联系方式披露 | Implemented | Gmail 来自账号，相关信息最多少量请求词命中片段；不附全画像或虚构模型理由 |
| 完整替换后阻止旧披露 | Implemented | 旧 matched 回执 / 待通知重查当前双方版本；原样同步不撤销 |
| 队列租约 / 重试与独立通知状态 | Implemented | SKIP LOCKED / lease UUID；仅两个 Handler；事件失败仍可捕获邮件 |
| 本地邮件捕获 | Implemented | 稳定 delivery_id、原子私有落盘、内容冲突检测 |
| 个人 Gmail / 跨 Host 同 Account | Implemented | canonical Gmail + Google sub 双唯一；离线验证账号 / 令牌持久逻辑 |
| 浏览器 Google OAuth 与持续同意 | Partial | cookie / state / nonce / PKCE；pa-connections-v2，旧同意拒绝并须重新授权；真人流程未验收 |
| PACE opaque 凭据 / 轮换 / 撤销 | Implemented | Hash / resource / client binding；一次性授权码、refresh 轮换、族撤销 |
| 系统 Gmail API 通知 | Partial | 独立 gmail.send 授权；稳定 Message-ID，真实发信 / 收件未验收 |
| MCP Events 回调与订阅 | Partial | challenge、Standard Webhooks、归属、加密 / 轮换、DNS 安全、官方复合参数退订、过期 / 410 / 413；真实 Host 接收与 PA 运行未验收 |
| 插件安装引导 / PA 连接 skill | Partial | portable manifest、DCR / scopes、onboarding skill、初始记忆整理 / 原生监控；未实际安装 |
| 文档链接 / CODEMAP 检查 | Implemented | check_docs.py；当前源码导航、文档和唯一私有人工操作表已同步 |
| 初期公网部署 | Partial | HTTPS 页面 / healthz、API / Worker / 独立 PG 已运行，迁移 0003 与 alembic check 通过；登录 / Host / 双通知待验收 |
| 全局限流 / 费用 / 观测 / 删除保留 | Planned | 尚需配置和实现，初期部署不证明生产运营就绪 |

## 验证记录

本轮默认测试 **51 passed / 20 skipped**，启用真实 PostgreSQL 后 **71 passed**。数据库用例各自建立随机 pace_test_* schema，执行完整 Alembic 升级，只清理自身 schema；Provider、Google claims 与公网接收器仍使用离线桩。真实数据库 `alembic check` 无漂移，schema head 保持 0003。Ruff check / format、git diff --check 与文档检查通过。

覆盖：完整画像即时发布、并发同键同步、内容不变、明确清空、旧格式 / 旧同意排除、stale connect 零 Provider 调用、同请求并发选择一次、幂等冲突、失败后重试、即时 Request 不写 D/S、撤销 / 旧快照阻止披露、有无 / 过期事件订阅过滤、多订阅失败不被成功掩盖、事件失败仍投递邮件、跨 Host 同账号、PKCE / 授权码重放保护、凭据轮换 / 撤销、官方退订参数。

`demo_business.py` 在独立随机 PostgreSQL schema 用合成 PA 画像直接 sync → connect → 重放 → Worker：matched 与硬冲突 no_match 均通过，重放额外调用 0；两次离线 Jev 桩调用、后端 LLM 0、真实邮件 / webhook 0。订阅与 Events 接收使用离线桩，邮件为本地 capture，临时 schema / 文件已清理；不证明真实匹配质量。

历史记录：2026-10-09 曾在旧文件 / 后端构建协议下做有限真实模型合成闭环（1 LLM + 2 Jev）。该路径已移除，不能作为当前 PA 直接输入或真实 Host 的验收。本轮没有新调用付费 Provider、发送真实通知、发布或部署。

## 配置与外部验收进度日志

### 2026-10-10：Google 系统发件授权

- 用户已创建 PACE Google Cloud 项目，设置品牌名称、支持 / 联系邮箱，选择 External + Testing，并加入两个测试 Gmail。
- 已创建独立 Web OAuth 客户端 PACE Gmail Sender，回调使用 OAuth Playground；用户完成 gmail.send 授权，Google 换取令牌返回 HTTP 200。
- 发件邮箱、客户端 ID / secret、refresh token 已保存到被 Git 忽略的私有配置及唯一人工表；本地 Settings 校验四项读取成功。公开文档不记录凭据或令牌。
- Google 返回 refresh_token_expires_in=604799，当前测试令牌约于 2026-10-17 到期。用户选择暂缓品牌公开页面与生产状态切换；到期后如仍在 Testing，需要重新授权。正式配置应补齐真实首页 / 隐私政策等信息，处理适用审核要求，再获取新令牌；不把每周手动授权作为正式运行方案。
- 当前仍为 capture；未启动真实发件验收，不证明 Gmail API 投递或收件成功。Google 登录客户端此后已配置（见下方接入日志），注册登录仍未验收。
- 私有表已提供初期阿里云服务器信息及 Work 插件入口说明；已通过 SSH 只读核对服务器：Docker / Compose / Nginx 可用，系统 Python 为 3.10（PACE 要求 >=3.12），约有 24GB 磁盘可用；80/443 与现有数据库已有其他服务使用，sudo 需要密码。未修改服务器、未部署 PACE，平台原生 Events 与 PA 运行未验收。部署须使用独立目录 / 数据库与兼容 Python 的运行环境；公网域名及 HTTPS 路由待确定。用户已明确授权本轮最多 2 次 Jev 调用、1 封真实邮件，收件人为私有表中测试用户2；本次授权尚未使用，超额停止。

### 2026-10-10：初期服务器部署

- 用户授权复用 clawcrony.com 与现有服务器，使用独立 `/home/dev/pace` 目录，并允许停止旧 Clawcrony 进程。已验证根域名解析及现有 HTTPS 证书；证书覆盖根域名 / www，2026-12-30 到期，续期仍需运维安排。
- 已停止并禁用两个明确属于 Clawcrony 的搜索 sidecar；旧文件与数据保留。归属未明确的 service-catalog 容器及 MySQL 保留，未擅自停止。
- Nginx 原站点备份到远端 PACE 私有目录，配置检查通过后 reload。根域名提供 PACE 首页 / privacy / terms，三页真实 HTTPS 可访问；www 重定向根域名，OAuth 查询参数不写访问日志。
- 新增 Docker / Compose 部署模板，独立 PACE PostgreSQL 已 healthy；后端镜像构建完成，API / Worker 均运行，真实数据库迁移至 0003，alembic check 无漂移。公网 healthz 返回 200 / ok，未认证 mcp 返回 401；readyz 返回 503，明确报告缺 Google 登录客户端及当前 capture 发件模式。服务器网络下载缓慢，初次镜像采用本机 uv.lock 离线安装的63个运行包，通过私有 BuildKit context 转移并校正环境路径；镜像实际导入验证通过，未含 dev 依赖或秘密。生产私有配置生成独立数据库凭据与持久 Fernet Key，已有发件 / Jev 凭据安全传入，未输出或加入镜像。
- Google 用户登录客户端此后已提供并配置，回调固定为 https://clawcrony.com/auth/google/callback；Host 实际回跳白名单仍待平台确认。邮件保持 capture；本轮真实 Jev 0 次、真实邮件 0 封，双通知与真人登录未验收。

### 2026-10-10：Google 用户登录客户端接入

- 用户已创建独立 PACE Gmail Login 客户端。凭据写入本机私有配置、唯一人工表与服务器 `.env`，仅更新登录两项，不覆盖其他配置；API / Worker 已重建并稳定运行。
- 真实公网 healthz=200，OAuth discovery 正确声明 HTTPS issuer / authorize / token / register 与 PKCE；缺失浏览器 flow 的 Google callback=400，未绕过登录保护。
- readyz=503，当前仅报告 gmail_notification_configuration（邮件仍 capture），不再报告 Google OAuth 配置缺失。凭据配置及路由检查不证明 Google 已接受实际回调，也不证明真人登录通过。
- 下一步核对 Host 回跳、实际安装 / OAuth 登录与原生事件。仍无真实 Jev 调用或邮件发送，授权额度未消耗。

### 2026-10-10：ChatGPT 插件创建验证排查

- 用户确认填写公网 /mcp、选择 OAuth，未填 Google 客户端到插件表单。公网 TLS 链及指定 protected-resource / OAuth metadata 可读取；未认证 MCP=401 属于正常授权挑战。
- 重现确定阻塞：DCR 向官方 ChatGPT 回跳注册返回 400 invalid_redirect_uri，因为部署回跳白名单为空。新增显式受限 callback_id 模板（[ADR 0005](decisions/0005-oauth-callback-id-templates.md)），注册仍保存精确 URI，禁止域名 / 任意路径通配。
- 相关真实 PostgreSQL 集成测试 6 passed，包含动态注册持久化及危险回跳拒绝；Google / Host 真实登录尚未验收。修复已部署，API / Worker 已重建；公网可信 ChatGPT 动态格式注册=201，伪装域名注册=400，healthz=200。实际平台重试结果待确认，不能把此阻塞的修复当成插件验证已全部通过。

### 2026-10-10：插件创建成功后的 Google 登录排查

- 用户确认自定义 MCP 插件已创建成功，但点击使用 Google 继续立即返回 gmail_authorization_failed，尚未进入 Google。
- 公网诊断用独立合成 DCR / PKCE / cookie 浏览器会话检查：注册201、authorize302、同意页200且 cookie存在、同意提交303至 accounts.google.com；不涉及真人身份或真实 Google Token 交换。
- 同意页 CSP 原仅允许 self，可能阻止浏览器表单跳转 Google；已限制性放行 accounts.google.com 并部署，保留 cookie / state 校验。部署后公网合成会话确认同意页200、提交303至 Google。新增不含私人原文的失败分类日志。相关真实 PostgreSQL 测试7 passed，覆盖流程、CSP与日志不泄漏；浏览器实际问题仍需重试确认。
- 另发现服务器访问 Google token、签名证书及账号接口均连接超时（HTTP 000）；与上述浏览器前置失败区分，属于后续真实 Token 交换 / Gmail 发件的网络阻塞。未尝试绕过签名或身份验证，也未发送邮件 / 调用 Jev。
- 用户没有海外服务器或常驻代理，要求最简单方案。建议独立新加坡服务器整体迁移并继续使用原域名；尚未购买、迁移或修改 DNS。旧服务器页面 / API仍运行，完整登录与双通知未验收。

### 2026-10-10：本地与服务器项目文件同步

- 本地已有 Git 仓库，origin 指向 https://github.com/gry1024/PACE.git；同步时工作区含未提交修改，远程仓库尚未包含当前实现快照；随后用户确认开发结束并要求提交、推送，见下方收尾记录。
- 服务器 `/home/dev/pace` 是部署副本，无 `.git` 目录。同步本地现存的 Git 跟踪文件及新增公开项目文件，逐文件 SHA-256 校验；本地已删除的旧模块在服务器对应项目路径删除。
- 私有 `.env*`、`.local/`、运行依赖、数据库、日志和个人编辑器配置分别保留，不参与源码同步。同步不等于重新构建运行镜像；运行与外部验收状态仍以上方记录为准。

### 2026-10-10：开发收尾与版本保存

- GitHub 仓库当前为 Public。用户确认今日开发结束，授权提交并推送今天的代码 / 文档到现有 `codex/gmail-mvp` 分支，不改变仓库可见性或合并到 main。
- 后续每次开发结束经用户确认后执行验证、秘密排除、commit / push；约定保存在 AGENTS.md。服务器保留部署副本，不要求安装 Git；私有配置与数据库不进入版本库。
- 收尾验证：真实 PostgreSQL 测试73 passed，Ruff check / format、文档13份及 diff 空白检查通过；Google / Provider / 事件接收仍为离线桩。
- Google 出网阻塞仍待新服务器解决；本次收尾不购买服务器，不增加真实 Provider 调用或通知，不表示外部闭环已验收。

## 数据与运行边界

- 当前业务数据存 PostgreSQL：Account、当前 O/D/S、只追加版本、即时 Request、Match、订阅、OAuth 状态、回执与通知队列。O/D/S 用 JSONB 中的文本 / 列表，无向量库 / 图数据库。
- 仓库 [selection_pool.json](../examples/selection_pool.json) 是合成选择演示；集成测试 / demo 合成画像在隔离 schema 中生成并清理。没有自动导入真人数据集或填充应用匹配池，质量评测集与真人试用仍待完成。
- 旧 files / sources / model 列、历史回执 / 画像仍保留；新画像为 pa-entity-v1，不读取旧原文、自动迁移或清理。旧构建任务无 Handler，有限失败，绝不调用 LLM。已应用迁移未重写。
- 安装初始化后被动候选只在发起新连接时刷新，可能长期不更新；首版没有画像自动过期。PA 应记录已知日期 / 不确定性，匹配质量需真人验证。
- connect 在总时间预算内持事务 / 同键锁，避免重复费用但占 DB 连接；候选有上限，尚无跨请求限流或总费用硬封顶。
- 完整画像有变化即使只是新增事实，也会终止旧快照的后续 matched 重放 / 待通知；历史不删除。无变化同步保持版本，不影响旧通知。
- 至少一次通知仍可能重复。Gmail Message-ID 仅追踪；Events 接收端按 eventId 去重，2xx 不证明 PA 运行。无 replay，订阅过期期间事件不可恢复；平台要自动刷新订阅。新候选必须有有效订阅，业务不做 Gmail-only 降级。
- /readyz 仅检查配置和迁移，不调用模型 / 发信、不证明 Worker / 外部凭据可用。Host 的记忆 / 工具 / 监控授权仍由平台控制。
- 没有用户自助删除 / 撤回同意界面、完整保留清理或密钥轮换流程。禁用 / 旧同意 / 旧快照阻止新披露，不删除历史。持久 Fernet Key 丢失后旧凭据 / 订阅无法解密。

## Next steps

1. 填写私有 `.local/MVP_HANDOFF.md`；Google Web OAuth、稳定密钥、系统 Gmail 授权与公网 origin 已配置；继续核对目标 Host 实际 redirect。所有具体人工步骤与填写格都在该文件的一张表中；系统发件第6–7行已完成，继续核对 Work 运行入口与第8行联调额度，第5行登录客户端及公网部署现已完成基础接入；[入口说明](MVP_SETUP_CHECKLIST.md) 不再含公开空表。
2. 已启动 HTTPS API / Worker / PostgreSQL；补齐 Host 精确回跳白名单，再验收首个 Work Cloud 用户的注册 / 持续授权、安装初始画像、事件监控、连接前同步与 Jev 匹配。
3. 在明确额度内验收 Events 实际触发被匹配者 PA 通知本人，且 Gmail 实际到达；再在 dots 验证同契约 / 跨 Host 同 Gmail。缺平台权限不算完整闭环，不扩建不支持平台的适配。
4. 面向真人开放前完成全局费用 / 限流、数据删除 / 保留、观测 / 运维与匹配评测；公开分发再核对 Google / Host 审核与政策页面。

操作见 [DEVELOPMENT](DEVELOPMENT.md)，结构见 [ARCHITECTURE](ARCHITECTURE.md)，导航见 [CODEMAP](CODEMAP.md)，契约见 [INTERFACES](INTERFACES.md)。
