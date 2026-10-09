# AGENTS.md

## Project

PACE 是平台无关的 Personal Agent Connection Backend，通过 MCP 暴露业务契约，应用层组织 Entity 与 Selection。

Python 要求 `>=3.12`，`.python-version` 选择 3.12；依赖由 `uv.lock` 锁定。当前锁定：FastAPI 0.142.2、MCP 2.3.0、TypeSafe SDK 0.7.2、OpenAI SDK 3.26.0、SQLAlchemy 2.1.3、psycopg 3.3.6、Alembic 1.20.0、Pydantic 2.13.5、pydantic-settings 2.15.0、uvicorn 0.54.0；pytest 9.1.1、Ruff 0.16.10。依赖变更时同步此处，以 manifest / lockfile 为准。

## Commands

在 Linux / WSL 仓库根目录执行；Windows 使用 `wsl -d Ubuntu-22.04 --cd /home/groy/pace -- bash -lc '命令'`，避免 UNC cwd 被 shell 丢弃。

```bash
uv sync --locked
uv run uvicorn pace.main:app --host 127.0.0.1 --port 8000
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run ruff format .
# 数据库改动：使用测试数据库，先按 DEVELOPMENT 配置
bash scripts/dev_db.sh start
uv run alembic upgrade head
PACE_TEST_DATABASE=1 uv run pytest -q
uv run alembic check
uv run python scripts/doctor.py --database
```

其他运行、诊断与文档验证命令见 [DEVELOPMENT](docs/DEVELOPMENT.md)。

## Architecture guardrails

- Host / Platform adapter 负责授权文件读取和身份接入；PACE backend 负责 Entity 与 Matching。Worker 只能处理已提交的文本，不能代替远端 Host 收集文件。
- `domain` 不依赖传输、ORM 或 Provider SDK；`application` 通过 Port 请求外部能力；具体 Adapter 在装配入口选择。API 装配在 `bootstrap`，Worker 装配在 `interfaces.worker.run`。
- Selection 通过 `ChoiceProvider`；Tournament 编排留在 application，SDK Adapter 只处理证据和协议转换。错误不得伪装为 No Match；组内概率不能作为全局成功率。
- 业务 MCP surface 保持 `sync_entity` / `connect`；`connection.matched` 是 Event。可信 `Principal` 来自验证器，不能从 Tool 参数的 Email / user ID 推导身份。
- 即时 Request 与长期 D/S 分开；业务数据与任务入队共享调用者事务；外部副作用按至少一次执行设计幂等。

## Workflow

改代码前阅读 [STATUS](docs/STATUS.md)、[ARCHITECTURE](docs/ARCHITECTURE.md) 与相关 [CODEMAP](docs/CODEMAP.md) 条目，核对当前源码；旧文档和测试桩不能证明功能完成。改后运行对应测试；涉及持久化必须验证真实 PostgreSQL 路径。项目自有代码保持准确的中文职责、约束和失败路径注释，避免仅为注释改动协议 docstring / 运行字符串。

每次 coding task 必须判断文档影响并在同一任务更新受到影响的 authoritative docs：

| 变化 | 必须同步 |
| --- | --- |
| 新增 / 删除 / 移动模块 | CODEMAP + STATUS |
| MCP / API / schema 变化 | INTERFACES |
| System boundary / data flow 变化 | ARCHITECTURE；重要新决策新增 ADR |
| 功能完成度变化，包括 Partial → Implemented | STATUS |
| build / test / run 命令变化 | DEVELOPMENT；常用命令或依赖变化同步本文件 |

不得留下描述旧模块、旧接口或旧完成度的文档；不要机械修改未受影响的文档。报告验证范围，区分离线桩、真实服务与 Host 验收。

## Documentation policy

`STATUS` = 当前实现状态唯一真相源；`ARCHITECTURE` = 结构与数据流；`CODEMAP` = 文件 / symbol 导航；`INTERFACES` = 关键接口 reference；`DEVELOPMENT` = 开发操作；`decisions/` = 已接受的重要决策。README 只提供入口。相同信息只在对应文档维护，其他位置链接；中文为主，symbol / 路径保持英文。历史 ADR 不改写决定，新决定以新 ADR supersede；`docs/sources/` 原文快照只读，不能用规划覆盖源码事实。

## Boundaries

禁止提交或输出 secrets、Token、数据库密码和私人原文；`.env*`（除 `.env.example`）、`.venv/`、`.local/`、`.research/` 不提交。不覆盖已有环境文件；只操作明确属于项目的数据库 / 测试 schema。已应用的迁移通过新增 revision 演进，不随意改写历史。不要无故升级依赖锁、修改包元数据 / LICENSE、重构无关模块。真实 Provider 诊断会联网并产生用量；使用合成或授权数据。推送、发布、部署和真实对外通知须处于用户授权范围。
