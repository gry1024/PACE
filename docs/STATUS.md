# 当前实现状态

## Current Snapshot

复核日期：2026-10-08（Asia/Shanghai）。HEAD：`f871a26`（Initial commit）。**下表评估的是本地未提交工作区，不是该提交中的实现**：扫描时 Git 仅跟踪 LICENSE / README，其余框架与旧文档为 untracked，README 已修改。

开发阶段：基础框架和独立 Selection / 任务基础设施可运行，两项业务用例未接线。**完整 MVP 不能端到端运行**；默认身份验证器与命令均抛 `FeatureUnavailable`，`/readyz` 固定 503。

本次实测：`uv sync --locked` 通过；默认测试 **34 passed / 5 skipped**；启用真实 PostgreSQL 测试 **39 passed**；Ruff check / format check 通过。数据库最初未运行，项目脚本启动后 `doctor --database` 通过；数据库 revision 为 `0001`，`alembic check` 无漂移。显式 `alembic upgrade head` 与空队列 Worker --once 正常退出；离线 Selection 为两轮三次调用。实际 uvicorn 监听验证六个运维端点及 MCP 三种 HTTP 方法的默认身份拒绝。新体系 9 份文档 / ADR 的链接、anchor、围栏检查通过；53 份源码、配置与历史快照 SHA-256 保持不变。2026-10-09 已适配文档检查器到当前结构。验证进程已停止，本地数据库恢复最初的停止状态。未运行真实 Provider / Host / Email 验证；旧文档的模型成功与耗时记录不计入本次证据。执行命令见 [DEVELOPMENT](DEVELOPMENT.md)。

## Module status

Status 只表示下表所定义模块的完成度；Implemented 的基础设施不代表业务用例完成。Tests 列是验证入口，不是全覆盖声明。

| Module | Status | Implementation | Entry points | Tests | Notes |
| --- | --- | --- | --- | --- | --- |
| 配置、API 装配与运维 | Implemented | `src/pace/config.py`、`src/pace/bootstrap.py`、`src/pace/main.py`、`src/pace/interfaces/http.py` | `Settings`、`create_app`、`build_container`、`/healthz`、`/contracts` | `tests/test_bootstrap.py` | 存活不检测依赖；资源关闭有下述限制 |
| 输入输出契约与领域值 | Implemented | `src/pace/application/contracts.py`、`src/pace/application/ports.py`；`src/pace/domain/models.py`、`src/pace/domain/errors.py` | `SourceFile`、`SyncEntityInput`、`ConnectInput`、`ConnectResult`、`Principal` | `tests/unit/test_contracts.py` | 结构校验不保证持久化 / 授权；大小边界未全测 |
| 核心 MCP transport 与分发 | Implemented | `src/pace/interfaces/mcp.py`、`src/pace/interfaces/http.py` | `ProtectedMCP`、`build_server`、`tool_definitions` | `tests/unit/test_mcp.py` | 官方 SDK 实际运行；成功调用由测试 Port 注入，不证明生产业务 |
| Account / identity / OAuth | Not implemented | `src/pace/application/services.py`（拒绝占位）；`src/pace/application/ports.py`（接口）；`src/pace/adapters/db/models.py`（表） | `UnconfiguredIdentity.verify`、`IdentityVerifier`、`Account` | `tests/unit/test_mcp.py` 仅验证默认拒绝 | 无 Email 验证、Token 验证、注册授权、跨 Host 绑定流程 |
| 文件 ingestion / Ontology Build / Refresh | Partial | `src/pace/application/contracts.py`、`src/pace/application/ports.py`；`src/pace/adapters/db/models.py` | `SourceFile.validate_content`、`OntologyBuilder.build`、`EntityVersion` | `tests/unit/test_contracts.py` 仅验证输入 | 文件 hash / 限额已校验；无收集器、提取 Adapter、文件持久化或 Build Handler |
| Entity / 长期 D/S 同步 | Partial | `src/pace/application/contracts.py`、`src/pace/application/services.py`；`src/pace/adapters/db/models.py` | `SyncEntityInput`、`UnconfiguredCommands.sync_entity`、`Entity` | `tests/unit/test_contracts.py`、`tests/unit/test_mcp.py` | 只有模型 / 契约；无更新、乐观锁、sync 幂等或版本发布事务 |
| 即时 Request / connect / Match | Partial | `src/pace/application/contracts.py`、`src/pace/application/services.py`；`src/pace/adapters/db/models.py` | `ConnectInput`、`UnconfiguredCommands.connect`、`ConnectionRequest`、`Match` | `tests/unit/test_contracts.py`、`tests/unit/test_mcp.py` | 无候选查询、Request 写入、持久重放、Match / 通知原子提交 |
| Selection / Jev Adapter | Implemented | `src/pace/application/tournament.py`；`src/pace/adapters/providers/jev.py` | `Tournament.select`、`resolve_decision`、`JevChoiceProvider.choose` | `tests/unit/test_tournament.py`、`tests/unit/test_jev_adapter.py` | 独立入口；真实模型质量、整体成本 / 延迟未验收 |
| PostgreSQL schema / session / migration | Implemented | `src/pace/adapters/db/models.py`、`src/pace/adapters/db/session.py`；`migrations/env.py`、`migrations/versions/0001_initial_framework.py` | `Base`、`Database`、`upgrade` | `tests/integration/conftest.py`、`tests/integration/test_jobs.py` | 七张表；业务表主要只验建表，未验业务事务 |
| 持久任务队列 / 通用 Worker | Implemented | `src/pace/adapters/db/jobs.py`；`src/pace/interfaces/worker.py` | `enqueue`、`JobQueue`、`Worker.run_once` | `tests/integration/test_jobs.py` | 至少一次执行；生产 `handlers={}`；持续 heartbeat / 丢租约路径未专项验收 |
| Ontology / Email / Event 业务 Handler | Not implemented | `src/pace/interfaces/worker.py`（空注册表） | `run` | 无真实业务 Handler 测试 | 未注册 kind 进入有限重试 / 失败 |
| 本地邮件捕获 | Implemented | `src/pace/adapters/delivery/capture.py` | `CaptureEmail.deliver` | `tests/unit/test_delivery.py` | 只返回 captured；不装配到生产命令 |
| 真实 Email / MCP Events | Not implemented | `src/pace/application/contracts.py`、`src/pace/application/ports.py`；`src/pace/adapters/db/models.py`（预留结构） | `ConnectionMatched`、`EventDelivery`、`EmailDelivery`、`EventSubscription` | 无真实投递 / 订阅测试 | 无 event 触发、events/* 方法、challenge、签名、加密器或 SMTP Adapter |
| Host / Plugin / Platform adapters | Not implemented | 无实现文件 | 无 | 无 | 无安装包、授权文件 Reader 或真实 Host 联调 |
| 开发数据库 / doctor / demo | Implemented | `scripts/dev_db.sh`、`scripts/doctor.py`、`scripts/demo_selection.py`；`examples/selection_pool.json` | `start/stop/status`、`main`、`run` | 无脚本专用测试；本次实际运行 | fixture 固定答案；不写业务数据 |
| 文档自动检查 | Implemented | `scripts/check_docs.py` | `check` | 实际执行通过 | 本地链接 / anchor / 围栏、CODEMAP 实现覆盖；不证明语义正确 |

## Working end-to-end flows

| 当前能跑通的链 | 证据与边界 |
| --- | --- |
| 环境 → ASGI 启动 → 运维响应 / 默认 MCP 拒绝 | `test_bootstrap.py`、`test_mcp.py`；真实监听探测验证 HTTP；有 Token 也不能完成生产业务 |
| 注入测试身份 / 命令 → 官方 SDK discover / list / call → structured result | `test_real_sdk_discover_list_and_call_with_injected_test_ports`；仅应用边界为合成桩 |
| 合成 JSON → EntitySnapshot → Tournament → FixtureChoice → Selection / traces | `demo_selection.py` 默认模式；候选 2、两轮三调用，不创建 Account / Match / 通知 |
| 隔离 schema 迁移 → enqueue → claim / recover → 合成 Handler → complete | `tests/integration/test_jobs.py`；真实 PostgreSQL，Handler 无外部副作用 |
| 合成邮件 → CaptureEmail → 私有 JSON → 同键重放 / 冲突检测 | `test_delivery.py`；本地捕获，不是对方收信 |

## Known gaps

MVP 阻塞链为：可信 Account / Principal → 已完成 Entity Snapshot → 合格候选查询 → connect 持久化与 Selection 接线 → Match 和通知任务提交 → 实际投递。每一业务环节均缺实现，配置数据库 / Key 不会补齐。`OntologyBuilder` 无实现，OpenAI SDK 目前仅用于 doctor；没有从数据库 JSONB 转领域 Snapshot 的生产转换。Host 收集与返回后刷新也没有执行者。

默认 MCP 不可能发现 / 调用成功：缺 Bearer 在入口被拒绝，有 Bearer 到未配置验证器仍被拒绝。当前没有可通过环境配置启用的生产认证方案；测试注入不得当作运行步骤。

## Current technical debt

| 源码位置 | 当前问题与影响 |
| --- | --- |
| `src/pace/bootstrap.py: Container.close` | 顺序关闭 Jev 再关闭数据库；前者抛异常时后者未由 finally 保证释放 |
| `src/pace/interfaces/worker.py: Worker.run_once` | 忽略 `complete` / `fail` 的 False；返回 True 只表示领到任务，未提供确认失败的单独可观察状态 |
| `src/pace/adapters/db/models.py` | Snapshot 外键不保证账号归属，历史版本无不可变约束；`updated_at` 无 onupdate；JSONB 无 MutableDict，原地修改不会自动追踪 |
| `src/pace/adapters/delivery/capture.py` | 独占创建后直接写入，崩溃可留半写文件；重放会冲突；已有目录权限不会收紧 |
| `src/pace/application/tournament.py`、`domain/models.py` | 并发只限制单次 select；无整体 timeout / 成本限额；trace 缺候选版本、Prompt 版本与耗时；frozen 数据对象中的 dict 仍可变 |
| `src/pace/interfaces/mcp.py` | 入口要求两个 scope 同时存在；缺少 403 专项测试；未知异常交 SDK 处理，未建立统一安全业务包装 |

以上是源码可见限制和验证缺口，本次仅记录，未修改代码。

