# PACE

PACE（Personal Agent Connection Engine）是通过 MCP 接入 Personal Agent 的平台无关连接后端，以即时 Request 和 Entity 的 Ontology / Demand / Supply 证据选择连接对象。

当前 MVP 的核心能力边界是文件同步、即时连接与匹配通知；**当前交付为基础框架，完整业务闭环不能运行**。可单独运行的能力包括官方 MCP transport、输入输出契约、Jev 四候选淘汰赛、PostgreSQL 迁移、持久任务队列和本地邮件捕获。模块完成度与本次实测结果以 [STATUS](docs/STATUS.md) 为准。

## Tech Stack

Python 3.12 + uv；FastAPI / Pydantic；官方 MCP Python SDK；TypeSafe Async SDK（Jev）；SQLAlchemy asyncio / psycopg / PostgreSQL；Alembic；pytest / Ruff。版本以 [pyproject.toml](pyproject.toml) 与 [uv.lock](uv.lock) 为准。

## Quick Start

在 Linux / WSL 仓库根目录执行，最短启动路径不需要数据库或模型 Key：

```bash
uv sync --locked
uv run uvicorn pace.main:app --host 127.0.0.1 --port 8000
```

另一个终端执行 `curl -fsS http://127.0.0.1:8000/healthz` 检查存活，访问 [contracts](http://127.0.0.1:8000/contracts) 查看契约。配置合法即可启动；已有环境文件会被读取。数据库、Worker、测试及配置操作见 [DEVELOPMENT](docs/DEVELOPMENT.md)。独立观察选择编排：

```bash
uv run python scripts/demo_selection.py
```

默认演示使用预设合成答案，不证明模型匹配质量。

## Repository Structure

| 一级目录 | 内容 |
| --- | --- |
| `src/` | PACE 领域、应用、Adapter、协议与进程入口 |
| `tests/` | 离线单元测试、官方 MCP transport 测试、PostgreSQL 集成测试 |
| `migrations/` | Alembic 迁移历史与执行环境 |
| `scripts/` | 本地数据库、诊断、Selection 演示与旧文档检查工具 |
| `examples/` | 合成候选池 |
| `docs/` | 当前代码 review 文档、ADR 与只读历史来源 |

## Documentation Index

| 文档 | 回答的问题 |
| --- | --- |
| [STATUS](docs/STATUS.md) | 实现到了哪里、哪些流程可跑、哪些缺口阻塞 MVP？ |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | 当前组件如何协作、对象与数据流如何组织？ |
| [CODEMAP](docs/CODEMAP.md) | 模块、文件、关键 symbol 和测试在哪里？ |
| [INTERFACES](docs/INTERFACES.md) | Tool / Event / HTTP / Database / Provider 的真实契约是什么？ |
| [DEVELOPMENT](docs/DEVELOPMENT.md) | 如何安装、配置、运行与验证？ |
| [decisions](docs/decisions/0002-code-framework.md) | 已接受的重要架构取舍；ADR 为历史记录 |
| [AGENTS.md](AGENTS.md) | Coding agent 的长期操作约定 |

当前最重要的限制：账号 / OAuth 和两项业务命令未实现；Selection 尚未接入候选查询与 Match 事务；Ontology、真实 Email / Event 和 Host 联调均未实现。详细边界只在 [STATUS](docs/STATUS.md) 维护。
