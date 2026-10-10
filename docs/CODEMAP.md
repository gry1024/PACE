# 代码导航

本页提供当前实现文件与关键 symbol 导航，不承载完成度结论；见 [STATUS](STATUS.md)。具体协议见 [INTERFACES](INTERFACES.md)，数据流见 [ARCHITECTURE](ARCHITECTURE.md)。

## Runtime 与 domain

| 文件 | 关键 symbol / 入口 | 职责与 review 重点 |
| --- | --- | --- |
| [src/pace/config.py](../src/pace/config.py) | Settings、get_settings | 秘密包装、配置/输入预算、HTTPS issuer校验；改配置需重启 |
| [src/pace/main.py](../src/pace/main.py) | create_app、app | ASGI入口；只在测试显式注入身份/命令 |
| [src/pace/bootstrap.py](../src/pace/bootstrap.py) | build_container、Container.close、MissingChoice | 选择真实OAuth/用例/Providers/通知，注册Handlers，全部资源清理 |
| [src/pace/domain/models.py](../src/pace/domain/models.py) | CONSENT_VERSION、Principal、EntitySnapshot、ChoiceDecision、RoundTrace、Selection | 可信账号/client与稳定选择值；无基础设施依赖 |
| [src/pace/domain/gmail.py](../src/pace/domain/gmail.py) | canonical_gmail | 只接受个人Gmail，规范大小写/dot/plus；本函数不验证身份 |
| [src/pace/domain/errors.py](../src/pace/domain/errors.py) | PaceError及子类 | 安全公开码；包括账号/版本/预算/终止交付错误 |

## Application

| 文件 | 关键 symbol / 入口 | 职责与 review 重点 |
| --- | --- | --- |
| [src/pace/application/contracts.py](../src/pace/application/contracts.py) | PROFILE_FORMAT、MAX_PROFILE_BYTES、SyncEntityInput/Result、ConnectInput/Result、ConnectionMatched、payload_hash | 唯一Pydantic契约；完整O/D/S字节预算、版本/时区校验，身份不得由Tool传入 |
| [src/pace/application/ports.py](../src/pace/application/ports.py) | IdentityVerifier、BusinessCommands、ChoiceProvider、EventDelivery、EmailDelivery | 外部能力结构边界，Protocol不自动提供执行 |
| [src/pace/application/services.py](../src/pace/application/services.py) | UnconfiguredIdentity、UnconfiguredCommands | 必要配置缺失时明确失败，无默认假账号/假匹配 |
| [src/pace/application/business.py](../src/pace/application/business.py) | BusinessStore、PersistentCommands | 通过事务Port编排重放/选择/失败提交；即时Request不改D/S |
| [src/pace/application/tournament.py](../src/pace/application/tournament.py) | Tournament.select、resolve_decision | 四候选+no_match，稳定淘汰/并列规则、组内概率验证、失败取消 |

## Adapters

| 文件 | 关键 symbol / 入口 | 职责与 review 重点 |
| --- | --- | --- |
| [src/pace/adapters/db/models.py](../src/pace/adapters/db/models.py) | Account、Entity、EntityVersion、ConnectionRequest、Match、EventSubscription、Job、SyncReceipt、OAuthRecord | ORM/JSONB/唯一键；迁移head与模型同步 |
| [src/pace/adapters/db/session.py](../src/pace/adapters/db/session.py) | Database、database_url | SQLAlchemy asyncio/psycopg Engine与Session；不create_all |
| [src/pace/adapters/db/jobs.py](../src/pace/adapters/db/jobs.py) | enqueue、JobQueue.claim/renew/complete/fail | 调用者事务入队、SKIP LOCKED、leaseguard、有限重试/terminal |
| [src/pace/adapters/db/business.py](../src/pace/adapters/db/business.py) | BusinessRepository、ConnectionUnit、require_account、require_current_snapshot、latest、snapshot、related_information | 账号资格/版本/Match/outbox原子事务；有界候选及最小请求相关披露 |
| [src/pace/adapters/db/handlers.py](../src/pace/adapters/db/handlers.py) | BusinessHandlers.send_email/deliver_event、registry | Worker两种通知；当前快照版本保护、资格重查、独立通知状态 |
| [src/pace/adapters/auth/google.py](../src/pace/adapters/auth/google.py) | GoogleOAuth、allowed_redirect、verified_id_token、key、SCOPES | 官方MCP OAuth provider；Google验证Gmail/sub、持久客户端/码/令牌族、Fernet |
| [src/pace/adapters/providers/jev.py](../src/pace/adapters/providers/jev.py) | JevChoiceProvider.choose/close | 官方TypeSafe SDK，输入预算，结构结果/异常转换；不查询账号 |
| [src/pace/adapters/delivery/capture.py](../src/pace/adapters/delivery/capture.py) | CaptureEmail.deliver | 私有原子捕获、UUID去重、同ID不同内容失败；无真实发信 |
| [src/pace/adapters/delivery/gmail.py](../src/pace/adapters/delivery/gmail.py) | GmailEmail.deliver/_send | 独立系统Gmail授权；稳定Message-ID、真实provider_accepted |
| [src/pace/adapters/delivery/events.py](../src/pace/adapters/delivery/events.py) | EventWebhooks、subscription_id、public_destination、signed_post、CallbackError | 归属/到期/撤销、challenge/签名/secret轮换；固定公网IP+TLS SNI |

## Interfaces

| 文件 | 关键 symbol / 入口 | 职责与 review 重点 |
| --- | --- | --- |
| [src/pace/interfaces/http.py](../src/pace/interfaces/http.py) | build_app、lifespan、healthz、readyz、contracts | API运维，OAuth路由，受保护/mcp；就绪不调用付费服务 |
| [src/pace/interfaces/mcp.py](../src/pace/interfaces/mcp.py) | TOOL_CONTRACTS、tool_definitions、build_server、ProtectedMCP、error_result | 官方SDK两Tool，Bearer与scope，安全结果，隔离Events接入 |
| [src/pace/interfaces/auth.py](../src/pace/interfaces/auth.py) | auth_routes、consent、callback | 官方OAuth端点+浏览器同意/Google回跳；flow cookie、安全header |
| [src/pace/interfaces/events.py](../src/pace/interfaces/events.py) | handle_event_request、event_definitions、discovery_sender | 仅MCP2026 Events扩展、有界输入、capability追加；Tools仍SDK |
| [src/pace/interfaces/worker.py](../src/pace/interfaces/worker.py) | Worker.run_once/_heartbeat、run、main | 独立进程装配生产Handler，续租/取消/安全错误/终止投递 |

## Migrations、scripts 与 Host

| 文件 | 关键 symbol / 入口 | 职责与 review 重点 |
| --- | --- | --- |
| [migrations/env.py](../migrations/env.py) | configure、run_online、target_metadata | Settings私有URL、测试connection注入、线上/离线迁移 |
| [migrations/versions/0001_initial_framework.py](../migrations/versions/0001_initial_framework.py) | upgrade/downgrade、revision=0001 | 初始表结构历史；不重写已应用revision |
| [migrations/versions/0002_business_and_google.py](../migrations/versions/0002_business_and_google.py) | upgrade/downgrade、revision=0002 | Google sub、完整files、SyncReceipt与OAuthRecord |
| [migrations/versions/0003_event_delivery_states.py](../migrations/versions/0003_event_delivery_states.py) | upgrade/downgrade、revision=0003 | 每订阅通知状态；一个成功不能掩盖另一个失败 |
| [scripts/dev_db.sh](../scripts/dev_db.sh) | start/status/stop | 本项目私有PGcluster与.env.local，防覆盖，不迁移 |
| [scripts/doctor.py](../scripts/doctor.py) | main、check_providers | 无参数只输出bool/版本；数据库/付费模型显式开关 |
| [scripts/demo_selection.py](../scripts/demo_selection.py) | FixtureChoice、snapshot、run | 独立离线/真实选择演示，不创建Match |
| [scripts/demo_business.py](../scripts/demo_business.py) | CountedChoice、demo、run | 隔离schema业务闭环；live最多2Jev、后端零LLM、仅capture、finally清理 |
| [scripts/check_docs.py](../scripts/check_docs.py) | check | 本地链接/anchor/fence与CODEMAP实现覆盖；不访问secrets/外部服务 |
| [plugins/pace/plugin.json](../plugins/pace/plugin.json) | portable manifest | 本地Host接入包标识，无实际发布/安装 |
| [plugins/pace/mcp.json](../plugins/pace/mcp.json) | streamable-http endpoint | 当前本地API；部署需在私有副本改真实HTTPS地址 |
| [plugins/pace/skills/connections/SKILL.md](../plugins/pace/skills/connections/SKILL.md) | Host连接工作流 | PA记忆整理、每次连接前全量sync、版本绑定、Request/D/S分离 |
| [plugins/pace/skills/setup/SKILL.md](../plugins/pace/skills/setup/SKILL.md) | 安装引导 | Google Gmail / 持续授权、平台原生事件订阅与刷新；安装时初始化入池 |

## Tests

| 文件 | 关键 symbol / 入口 | 职责与 review 重点 |
| --- | --- | --- |
| [tests/conftest.py](../tests/conftest.py) | isolate_environment | 默认测试不读真实Provider环境；不改写用户.env |
| [tests/test_bootstrap.py](../tests/test_bootstrap.py) | health/config alias tests | mvp存活不等于业务就绪，Key别名优先及repr不泄密 |
| [tests/unit/test_contracts.py](../tests/unit/test_contracts.py) | contract validators | 完整画像UTF8预算、时区、清空与版本与输出分支 |
| [tests/unit/test_tournament.py](../tests/unit/test_tournament.py) | Tournament tests | 四候选分组、多轮/no_match/并列、概率、异常取消 |
| [tests/unit/test_jev_adapter.py](../tests/unit/test_jev_adapter.py) | SDK fake tests | 输入预算、UUIDJSON、Provider异常与无效结果 |
| [tests/unit/test_delivery.py](../tests/unit/test_delivery.py) | capture tests | 私有权限/稳定ID/冲突；不发送邮件 |
| [tests/unit/test_mcp.py](../tests/unit/test_mcp.py) | TestIdentity、TestCommands、headers、request | 真实SDK发现/工具与未配置身份；桩仅用于应用边界 |
| [tests/unit/test_gmail.py](../tests/unit/test_gmail.py) | Gmail/config/callback tests | 个人Gmail规范化、SSRF地址拒绝、发件与登录分离；离线 |
| [tests/integration/conftest.py](../tests/integration/conftest.py) | sessions | 显式PG开关，随机隔离schema，真实完整Alembic迁移，自身清理 |
| [tests/integration/test_jobs.py](../tests/integration/test_jobs.py) | persistent queue/Worker tests | 并发去重、租约恢复/旧持有者、有限重试与heartbeat |
| [tests/integration/test_business.py](../tests/integration/test_business.py) | account、Choice、profile、ready、business tests | 真实事务、并发重放、原子入队、即时发布/无变化/旧授权/版本冲突/清空/撤销快照、失败后重试 |
| [tests/integration/test_oauth_events.py](../tests/integration/test_oauth_events.py) | grant、cross-host/token/subscription/metadata tests | 真实OAuth持久化、SDKmetadata与Token端点PKCE/一次性码验证；Googleclaims/公网receiver离线模拟 |

## 包标记与配置

src/pace 各级 __init__.py 只标记包，未提供隐藏运行入口。pyproject.toml 与 uv.lock 管理依赖；.python-version 选择3.12；.env.example是无秘密配置参考；alembic.ini 与 migrations/script.py.mako 配置迁移。examples/selection_pool.json是合成选择池。docs/decisions记录已接受决策，docs/sources只读保存原文。

## 部署与公开页面

- `deploy/Dockerfile`：Python 3.12 锁定依赖镜像，不包含秘密。
- `deploy/compose.yaml`：独立 API / Worker / PostgreSQL、内网数据库与内存上限。
- `deploy/nginx.conf`：根域名 HTTPS、静态页面与 API 反向代理，关闭访问日志。
- `.dockerignore`：排除环境凭据与私有运行目录。
- `public/index.html`、`public/privacy.html`、`public/terms.html`：邀请测试介绍及真实数据处理边界说明。
