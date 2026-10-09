# Repository CODEMAP

路径均相对仓库根目录；文件链接可直接定位，symbol 是 review 入口。完成度只在 [STATUS](STATUS.md) 维护，字段只在 [INTERFACES](INTERFACES.md) 维护，操作命令见 [DEVELOPMENT](DEVELOPMENT.md)。空 `__init__.py` 不登记。

## 按问题定位

| 要 review 的逻辑 | 文件与 symbol |
| --- | --- |
| Jev tournament / 并列 / No Match | [application/tournament.py](../src/pace/application/tournament.py)：`Tournament.select`、`resolve_decision` |
| connect MCP Tool | [interfaces/mcp.py](../src/pace/interfaces/mcp.py)：`TOOL_CONTRACTS`、`build_server.call_tool`；命令在 [application/services.py](../src/pace/application/services.py)：`UnconfiguredCommands.connect` |
| Ontology Build | [application/ports.py](../src/pace/application/ports.py)：`OntologyBuilder.build` 只有签名；没有提取实现文件 |
| 数据库 models / migration | [adapters/db/models.py](../src/pace/adapters/db/models.py)：`Base` 与七个模型；[0001](../migrations/versions/0001_initial_framework.py)：`upgrade` |
| Email / Event delivery | [adapters/delivery/capture.py](../src/pace/adapters/delivery/capture.py)：`CaptureEmail.deliver`；[ports.py](../src/pace/application/ports.py)：`EmailDelivery` / `EventDelivery`；Event schema 在 [contracts.py](../src/pace/application/contracts.py)：`ConnectionMatched` |
| 身份来源 / 权限 | [interfaces/mcp.py](../src/pace/interfaces/mcp.py)：`ProtectedMCP.__call__`；[services.py](../src/pace/application/services.py)：`UnconfiguredIdentity.verify` |
| 领取、租约、重启恢复 | [adapters/db/jobs.py](../src/pace/adapters/db/jobs.py)：`JobQueue.claim` / `_update`；[interfaces/worker.py](../src/pace/interfaces/worker.py)：`Worker.run_once` / `_heartbeat` |

## src/pace：runtime 与 domain

| Module / Path | Purpose / Key symbols | Called by / depends on | Important behavior |
| --- | --- | --- | --- |
| [config.py](../src/pace/config.py) | `Settings`、`get_settings`：类型化配置与缓存 | main / doctor / worker / migrations；pydantic-settings | 环境优先级、Key 别名、SecretStr；配置修改需重启已有进程 |
| [main.py](../src/pace/main.py) | `create_app`、`app`：ASGI 入口与测试注入 | uvicorn / tests；bootstrap、HTTP | 全局 app 在导入时装配；生产不注入测试身份 |
| [bootstrap.py](../src/pace/bootstrap.py) | `Container`、`build_container`、`Container.close`：API 资源装配 | main；具体 DB / Jev Adapter | identity / commands 默认为失败实现；配置资源与业务调用分离 |
| [domain/models.py](../src/pace/domain/models.py) | `Principal`、`EntitySnapshot`、`ChoiceDecision`、`RoundTrace`、`Selection` | 契约 Port、Tournament、Jev / demo；标准库 | Selection 不是持久 Match；dataclass frozen 非深度不可变 |
| [domain/errors.py](../src/pace/domain/errors.py) | `PaceError` 及安全错误子类 | identity / Commands / Provider / queue / transports | 固定公开 code / message，保留内部异常链；reference 见 INTERFACES |

## src/pace/application

| Module / Path | Purpose / Key symbols | Called by / depends on | Important behavior |
| --- | --- | --- | --- |
| [contracts.py](../src/pace/application/contracts.py) | `Contract`、`SourceFile`、`EntryUpdate`、`SyncEntityInput/Result`、`RequestContext`、`ConnectInput/Result`、`ConnectionMatched`、`payload_hash` | MCP / HTTP / ports / Jev；Pydantic | extra=forbid；输入 validators 和输出分支；hash 仅规范化载荷，不持久重放 |
| [ports.py](../src/pace/application/ports.py) | `IdentityVerifier`、`BusinessCommands`、`ChoiceProvider`、`OntologyBuilder`、`EventDelivery`、`EmailDelivery` | 传输、装配、Tournament；domain / contracts | Python Protocol 定义结构边界，不自动提供实现 |
| [services.py](../src/pace/application/services.py) | `UnconfiguredIdentity.verify`、`UnconfiguredCommands.sync_entity/connect` | bootstrap 选用，MCP 调用 | 三个方法均直接抛 FeatureUnavailable；未查询 / 写入业务数据 |
| [tournament.py](../src/pace/application/tournament.py) | `resolve_decision`、`Tournament.select` | demo / tests；ChoiceProvider、领域数据 | 稳定分组、并行 choose、概率校验、并列决胜、错误取消；流程见 ARCHITECTURE |

## src/pace/adapters

| Module / Path | Purpose / Key symbols | Called by / depends on | Important behavior |
| --- | --- | --- | --- |
| [db/models.py](../src/pace/adapters/db/models.py) | `Account`、`Entity`、`EntityVersion`、`ConnectionRequest`、`Match`、`EventSubscription`、`Job` | queue、Alembic metadata；SQLAlchemy / PostgreSQL JSONB | 存储结构与 DB 约束，不实施授权、版本发布或投递状态机 |
| [db/session.py](../src/pace/adapters/db/session.py) | `database_url`、`Database.__init__/close` | bootstrap、Worker、migrations / tests | psycopg URL 规范化、异步 Engine / Session；不 create_all |
| [db/jobs.py](../src/pace/adapters/db/jobs.py) | `enqueue`、`JobQueue.claim/renew/complete/fail`、`_update` | Worker / 集成 tests；SQLAlchemy | 去重依赖事务，领取与持有者确认分开；租约 guard 和有限退避 |
| [providers/jev.py](../src/pace/adapters/providers/jev.py) | `JevChoiceProvider.choose/close` | bootstrap 构造；live demo 调用；typesafe-sdk | JSON-normalize UUID，构造 Choice；调用前预算；SDK 结果转领域值 |
| [delivery/capture.py](../src/pace/adapters/delivery/capture.py) | `CaptureEmail.deliver` | 单元 tests；标准库文件系统 | UUID 文件名、独占创建、私有权限、相同内容重放；当前无生产装配 |

## src/pace/interfaces

| Module / Path | Purpose / Key symbols | Called by / depends on | Important behavior |
| --- | --- | --- | --- |
| [http.py](../src/pace/interfaces/http.py) | `build_app`、内嵌 `lifespan/healthz/readyz/contracts` | main；FastAPI、ProtectedMCP、Container | 精确 /mcp ASGI Route；生命周期启动官方管理器并关闭 API 资源 |
| [mcp.py](../src/pace/interfaces/mcp.py) | `TOOL_CONTRACTS`、`tool_definitions`、`build_server.list_tools/call_tool`、`error_result`、`ProtectedMCP` | HTTP；官方 MCP SDK、Pydantic、Container | 两 Tool 同源 schema；先身份再 SDK；Principal 存请求 state；结构化安全错误 |
| [worker.py](../src/pace/interfaces/worker.py) | `Worker.run_once/_heartbeat`、`run`、`main`、`JobHandler` | module CLI / tests；JobQueue、Database | Worker 自己装配 DB；生产 handlers 为空；run_once 的 True 只表示领取过 |

## migrations、scripts、examples 与配置

| Path | Key symbols / Purpose | 依赖与 review 重点 |
| --- | --- | --- |
| [migrations/env.py](../migrations/env.py) | `configure`、`run_online`、`target_metadata` | Settings + Base.metadata；线上异步 NullPool、离线 SQL、测试连接注入 |
| [migrations/versions/0001_initial_framework.py](../migrations/versions/0001_initial_framework.py) | `revision=0001`、`upgrade/downgrade` | 固定建表 / 索引历史；downgrade 删除数据，不是排错步骤 |
| [migrations/script.py.mako](../migrations/script.py.mako)、[alembic.ini](../alembic.ini) | 新 migration 模板与执行路径 | 连接串读取 Settings，不保存在 ini |
| [scripts/dev_db.sh](../scripts/dev_db.sh) | start / stop / status | 项目 `.local` 集群；初始化不覆盖已有环境，端口保存，schema 迁移另行执行 |
| [scripts/doctor.py](../scripts/doctor.py) | `main`、`check_providers` | 包版本 / 配置 bool、SELECT 1、显式真实 Jev / LLM 最小请求；不验证 Ontology |
| [scripts/demo_selection.py](../scripts/demo_selection.py) | `run`、`snapshot`、`FixtureChoice.choose` | 默认 fixture / live SDK 共用 Tournament；无 DB / 通知 / 刷新副作用 |
| [examples/selection_pool.json](../examples/selection_pool.json) | requester、request/context、五名 candidates、offline_demo_winner | 固定合成证据与离线预设 Winner；live 不使用预设答案 |
| [scripts/check_docs.py](../scripts/check_docs.py) | `check` | 当前文档链接 / anchor / 围栏和 CODEMAP 实现覆盖；操作见 DEVELOPMENT |
| [pyproject.toml](../pyproject.toml)、[uv.lock](../uv.lock)、[.python-version](../.python-version) | 包 / 依赖 / 工具 / 解释器约束 | 不手工更新锁文件；实际版本与常用命令见 AGENTS |
| [.env.example](../.env.example)、[.gitignore](../.gitignore) | 无秘密配置示例、运行数据排除规则 | 配置字段 reference 见 DEVELOPMENT；不读取 / 发布真实环境正文 |

## tests

| Path | 关键验证 | 依赖 / 不证明的范围 |
| --- | --- | --- |
| [tests/conftest.py](../tests/conftest.py) | `isolate_environment` | 清 Provider 进程变量；非 integration 清 DB 变量；测试显式禁用 env 文件，导入全局 app 仍须注意实际配置 |
| [tests/test_bootstrap.py](../tests/test_bootstrap.py) | 存活 / 未就绪、官方 / 旧 Key 优先级、空值与 repr | TestClient 与显式 Settings；不调用真实 Provider |
| [tests/unit/test_contracts.py](../tests/unit/test_contracts.py) | hash / 格式 / 时区、明确更新、重复项、身份注入、no_match 形状 | Pydantic；不验证持久化幂等与全部大小边界 |
| [tests/unit/test_tournament.py](../tests/unit/test_tournament.py) | 0/1/4/5/16/17、尾组、全淘汰、并列、非法概率、失败取消、重复 / 自身 | 合成 Provider；不验证模型质量 |
| [tests/unit/test_jev_adapter.py](../tests/unit/test_jev_adapter.py) | context / UUID / no_match、close、调用前预算 | SDKStub；无网络验证，错误映射未专项覆盖 |
| [tests/unit/test_mcp.py](../tests/unit/test_mcp.py) | 真实 SDK discover/list/call、默认 401/503、未配置命令错误 | TestIdentity / TestCommands；无真实 OAuth / Host，未专项测 403 |
| [tests/unit/test_delivery.py](../tests/unit/test_delivery.py) | 捕获状态、文件权限、去重 / 内容冲突 | tmp_path；无 SMTP / Event |
| [tests/integration/conftest.py](../tests/integration/conftest.py) | `sessions`：每例随机 schema，真实 Alembic upgrade | 显式启用真实 DB；finally 只清自建 schema |
| [tests/integration/test_jobs.py](../tests/integration/test_jobs.py) | 入队事务 / 去重 / 回滚、并发 claim、过期接管 / stale ack、耗尽、Handler / 未知 kind | 真实 PostgreSQL；未验证长任务 heartbeat、外部副作用恰好一次 |

## 文档与历史证据边界

当前 review 使用根 README / AGENTS 与五份 uppercase docs。`docs/sources/` 四份原始 Notion 快照保留原文，只作为历史来源：产品与开发规范曾存在不同口径，两个调研页面已归档。快照中的方案、示例、外部链接和“已读”记录不作为当前实现或本次访问外部站点的证据。

| 历史文件 | 用途 |
| --- | --- |
| [product-notion.md](sources/product-notion.md) | 2026-10-07 产品定义与长期设想原文 |
| [development-notion.md](sources/development-notion.md) | 2026-10-07 开发规范 / Coding Freeze v2 原文 |
| [jev-archived-notion.md](sources/jev-archived-notion.md) | 标记 deleted 的历史 Selection 调研；不完整示例不能当运行代码 |
| [personal-agent-archived-notion.md](sources/personal-agent-archived-notion.md) | 标记 deleted 的历史 Host 调研；不证明当前平台权限 / 能力 |

旧 `AGENT.md`、小写文档、code-review 卡片 / catalog、framework specs 已由当前体系取代；没有保留第二份当前状态或接口说明。历史 ADR 保留决定与日期，只规范格式、更新本地导航；新决策不得改写历史。

