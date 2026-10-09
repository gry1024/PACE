# 开发操作

所有 Bash 命令在 Linux / WSL 仓库根目录执行。完成度与验证结果只在 [STATUS](STATUS.md) 维护；本页提供可复现操作。

## Prerequisites 与 uv

Python `>=3.12`，`.python-version` 选择 3.12；uv；数据库操作另需可用 PostgreSQL。`scripts/dev_db.sh` 默认使用 `/usr/lib/postgresql/14/bin`，可用 PG_BIN 指向已安装二进制；实际测试环境为 Ubuntu 22.04 WSL。无需 Node / Docker。

```bash
uv sync --locked
uv run python --version
uv run python scripts/doctor.py
# 新机器没有 .env 时才复制；不覆盖原有配置
if [ ! -e .env ]; then cp .env.example .env; fi
```

uv 不在 PATH 时，本机可用 `/home/groy/.local/bin/uv`。Windows 示例：

```powershell
wsl -d Ubuntu-22.04 --cd /home/groy/pace -- bash -lc 'uv sync --locked'
```

避免对 UNC cwd 运行相对 shell 命令；cmd.exe 可能回退到 Windows 目录。

## Environment variables

权威定义：[src/pace/config.py](../src/pace/config.py)，无秘密示例：[.env.example](../.env.example)。`.env` → `.env.local` → 进程环境覆盖同名字段，空环境值忽略，额外字段忽略；`get_settings` 有进程缓存，改配置后重启 API / Worker。不要打印真实连接串或 Key。

| 变量 | 默认 / 约束 | 用途 |
| --- | --- | --- |
| APP_ENV | development | 环境标签，非就绪开关 |
| DATABASE_URL | 未配置 | DB / Worker / migration；postgresql:// 自动转 psycopg URL，或直接用 postgresql+psycopg://；不接受 SQLite |
| TYPESAFE_API_KEY / JEV_API_KEY | 未配置，官方名优先，兼容旧名 | Jev Client |
| JEV_MODEL | jev-1.13.0 | 固定选择模型基线 |
| OPENAI_API_KEY | 未配置 | 仅 doctor LLM 诊断 |
| OPENAI_BASE_URL | https://api.openai.com/v1 | OpenAI 兼容服务地址 |
| OPENAI_MODEL_NAME | 未配置 | LLM 诊断需要 Key + model |
| PROVIDER_TIMEOUT_SECONDS | 20，>0 | Jev Adapter 单请求超时 |
| JEV_INPUT_BYTES | 24000，1000–24000 | Jev 输入 JSON 保守预算 |
| SELECTION_CONCURRENCY | 4，1–16 | demo 传入 Tournament 的单次并发上限 |
| WORKER_LEASE_SECONDS | 300，≥3 | 领取租约，heartbeat 每三分之一周期续租 |
| WORKER_POLL_SECONDS | 2，>0 | Worker 空队列休眠秒数 |

OpenAI 配置存在不启用 Ontology。没有 Email provider / OAuth / 公网部署配置项。`doctor --database` 使用 psycopg 原始连接参数，建议环境采用普通 `postgresql://` URL；不要向它提供 SQLAlchemy 专用 `postgresql+psycopg://` URL。

## Database setup

```bash
bash scripts/dev_db.sh start
bash scripts/dev_db.sh status
uv run alembic upgrade head
uv run alembic current
uv run alembic check
uv run python scripts/doctor.py --database
# 用完仅停止本项目集群
bash scripts/dev_db.sh stop
```

首次 start 在 `.local/postgres` 初始化，生成私有密码并写入 `.env.local`，默认只监听 `127.0.0.1:54329`。已有集群不会重置数据 / 密码；已有 `.env.local` 而无集群时拒绝覆盖。Unix socket 使用本地 trust，TCP 使用 SCRAM；脚本用于开发。start 只创建数据库，迁移另行显式执行。

首次可设置 `PACE_PG_PORT=54330 bash scripts/dev_db.sh start`；后续按 `.local/postgres.port` 保存端口运行，冲突覆盖会被拒绝。PG_BIN 只影响脚本，不影响 SQLAlchemy。使用已有测试 PostgreSQL 时在私有配置或进程环境设置 DATABASE_URL，确认 `.env.local` 不会覆盖预期值，不必运行 dev_db.sh。

## Run

```bash
uv run uvicorn pace.main:app --host 127.0.0.1 --port 8000
```

另一终端：

```bash
curl -fsS http://127.0.0.1:8000/healthz
curl -fsS http://127.0.0.1:8000/contracts
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/readyz
```

预期 readyz=503；具体响应与 MCP 认证行为见 [INTERFACES](INTERFACES.md#httpapi)。FastAPI UI 在 `http://127.0.0.1:8000/docs`。Ctrl+C 关闭 API；Worker 是单独进程，需数据库和已迁移 schema：

```bash
uv run python -m pace.interfaces.worker --once
uv run python -m pace.interfaces.worker
```

生产 Handler 注册表为空，空队列 --once 正常退出不能证明业务执行。不要向应用队列写真实通知；当前未知 kind 会消耗有限尝试。

## Test、lint 与 format

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
# 实际格式化，仅在代码任务需要时运行
uv run ruff format .
# 使用具有 CREATE SCHEMA 权限的测试数据库
PACE_TEST_DATABASE=1 uv run pytest -q
# 聚焦相关模块
uv run pytest -q tests/unit/test_tournament.py tests/unit/test_jev_adapter.py
PACE_TEST_DATABASE=1 uv run pytest -q tests/integration/test_jobs.py
```

默认数据库用例跳过；开启后每例新建随机 `pace_test_*` schema，以 search_path 注入实际 Alembic 迁移，finally 删除自身 schema，不清空 public。测试不调用真实 Provider；单元测试使用显式禁用环境文件的 Settings。测试风险映射见 [CODEMAP](CODEMAP.md#tests)，当前结果见 STATUS。

## Migrations

```bash
uv run alembic upgrade head
uv run alembic current
uv run alembic check
# 仅在 schema 变更任务中生成后人工 review
uv run alembic revision --autogenerate -m 'describe_schema_change'
```

`migrations/env.py` 从 Settings 读取私有 URL，用 Base.metadata 比对类型；服务不自动迁移。迁移已应用到共享环境后新增 revision，不重写旧 migration。downgrade 会删表 / 数据，不能当普通恢复命令。集成测试验证隔离 schema 的真实 upgrade；本次没有在应用数据库执行破坏性回滚。

## 调试与独立 Selection

```bash
uv run python scripts/demo_selection.py
# 显式联网：仓库合成文本，可能产生 API 用量
uv run python scripts/demo_selection.py --live
uv run python scripts/doctor.py --providers
```

默认 demo = fixture_orchestration_only；答案来自 offline_demo_winner，不是模型判断。live = live_jev_synthetic，使用 Jev Adapter，不创建业务数据。doctor 无参数只输出包版本和配置 bool；--database 做 SELECT 1；--providers 并行 Jev / LLM 最小诊断，仅输出状态 / 类型 / 耗时，不证明 Ontology 或模型效果。

| 现象 | 直接检查 |
| --- | --- |
| 数据库连接失败 | dev_db.sh status；检查配置覆盖；项目日志在 `.local/postgres.log`，勿公开凭据 / 私人数据 |
| pg_ctl 不存在 | 安装 PostgreSQL 或设置 PG_BIN |
| 端口冲突 | 查看项目日志、选择首次初始化端口；不要停止未知服务 |
| /mcp 401 / 503 | INTERFACES 默认身份边界；不能编造 Token 绕过 |
| 输入过长 | Jev 预算与文件文本 / HTTP body 的独立限额；缩小输入，不静默截断硬约束 |
| migration 漂移 | 核对 ORM 与 migration；运行 alembic check，不用 create_all 掩盖 |
| 修改环境后未生效 | 重启进程，区分文件配置与环境覆盖 |

## Documentation validation

```bash
uv run python scripts/check_docs.py
```

检查当前 README / AGENTS / docs 的本地链接、anchor、围栏，并要求 CODEMAP 覆盖项目 Python 实现文件。历史 sources 原样保留，不检查其 Notion 内部链接。检查不访问外部服务、不维护旧指纹 catalog；语义、完成度与 symbol 仍须人工对照。
