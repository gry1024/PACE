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
| OPENAI_API_KEY | 未配置 | Ontology 提取与显式诊断 |
| OPENAI_BASE_URL | https://api.openai.com/v1 | OpenAI 兼容服务地址 |
| OPENAI_MODEL_NAME | 未配置 | Ontology 需要 Key + model |
| PROVIDER_TIMEOUT_SECONDS | 20，>0 | Jev Adapter 单请求超时 |
| JEV_INPUT_BYTES | 24000，1000–24000 | Jev 输入 JSON 保守预算 |
| SELECTION_CONCURRENCY | 4，1–16 | connect / demo 单次 Tournament 的并发上限 |
| WORKER_LEASE_SECONDS | 300，≥3 | 领取租约，heartbeat 每三分之一周期续租 |
| WORKER_POLL_SECONDS | 2，>0 | Worker 空队列休眠秒数 |
| CONNECT_TIMEOUT_SECONDS / MAX_CANDIDATES | 60秒 / 128，分别≤300 / ≤1000 | 单次连接总选择预算；超限报错 |
| ONTOLOGY_INPUT_BYTES / ONTOLOGY_MAX_OUTPUT_TOKENS | 48000 / 800 | 输入整体预算及输出上限；失败不截断资料 |
| PUBLIC_BASE_URL | http://127.0.0.1:8000 | HTTPS origin，HTTP仅loopback；固定issuer与/mcp resource |
| GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET | 未配置 | Google Web OAuth，仅openid/email |
| ENCRYPTION_KEY | 未配置 | 长期Fernet密钥；clientsecret/verifier/webhooksecret密文 |
| OAUTH_REDIRECT_ALLOWLIST | []，JSON精确URI列表 | 受信任Host回跳；开发环境另允许HTTP loopback |
| OAUTH_ACCESS_SECONDS / OAUTH_REFRESH_SECONDS | 3600 / 2592000 | access与refresh有效期，轮换旧族立即失效 |
| EMAIL_DELIVERY_MODE / CAPTURE_DIRECTORY | capture / .local/mail | 本地捕获或gmail；不接受其它模式 |
| GMAIL_SENDER | 未配置，个人Gmail | 独立系统发件账号 |
| GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / GMAIL_REFRESH_TOKEN | 未配置 | 发件账号独立gmail.send OAuth授权 |

配置 Key + model 时装配 Ontology Adapter；实际调用由 Worker 触发，启动不自动消耗额度。`doctor --database` 使用 psycopg 原始连接参数，建议环境采用普通 `postgresql://` URL；不要向它提供 SQLAlchemy 专用 `postgresql+psycopg://` URL。

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

缺 Gmail 配置时 readyz=503；具体响应与 MCP 认证行为见 [INTERFACES](INTERFACES.md#httpapi)。FastAPI UI 在 `http://127.0.0.1:8000/docs`。Ctrl+C 关闭 API；Worker 是单独进程，需数据库和已迁移 schema：

```bash
uv run python -m pace.interfaces.worker --once
uv run python -m pace.interfaces.worker
```

生产注册表包含 ontology.build / email.send / event.deliver；API 和 Worker 需要相同配置。默认邮件 capture，只有明确配置 gmail 才真实发送；空队列 --once 正常退出不能证明 Worker 已处理业务。

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
uv run python scripts/demo_business.py
# 有限真实闭环：最多1次LLM + 2次Jev，仅合成资料与本地捕获
uv run python scripts/demo_business.py --live
```

默认 demo = fixture_orchestration_only；答案来自 offline_demo_winner，不是模型判断。live = live_jev_synthetic，使用 Jev Adapter，不创建业务数据。doctor 无参数只输出包版本和配置 bool；--database 做 SELECT 1；--providers 并行 Jev / LLM 最小诊断，仅输出状态 / 类型 / 耗时，不证明 Ontology 或模型效果。

demo_business 使用独立随机 pace_demo_* schema，执行完整迁移和持久用例、Worker、通知capture，finally只删除自身schema与临时捕获目录。需要数据库CREATE SCHEMA权限；不向真人发送邮件。默认两个选择是离线桩，不证明效果；--live调用实际Provider且不自动扩大预算。避免为了重复检查接线不断运行付费命令。

## Gmail 身份与发件配置

保留现有 `.env` 与 `.env.local`；只在私有配置中补充 `.env.example` 展示的字段。API与Worker使用相同持久Key，禁止把Fernet Key放日志、聊天、Git或公开终端历史。

1. 在Google Cloud配置Web OAuth客户端，注册精确redirect：`PUBLIC_BASE_URL/auth/google/callback`，设置相应同意屏幕与测试用户。PACE只申请openid/email，不接受非个人@gmail.com。
2. 私有配置填GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET及稳定Fernet ENCRYPTION_KEY。Key可用cryptography的Fernet.generate_key生成，并直接安全保存；不要把实际Key当作调试输出。
3. 为目标Host将其实际OAuth回跳URI加入OAUTH_REDIRECT_ALLOWLIST（JSON列表）。只允许可信精确地址；生产设置APP_ENV=production；PUBLIC_BASE_URL是origin且生产为HTTPS，不能带path/query。
4. 迁移至head，同时启动API与Worker。使用Host OAuth授权，检查同意页、Google Gmail登录、同账号跨Host关联、401/过期/撤销行为。字段存在与离线模拟不能代替真人Google验收。
5. 真实发件使用独立系统Gmail，在Google启用Gmail API，按[Google服务器端OAuth流程](https://developers.google.com/identity/protocols/oauth2/web-server)获取系统发件账号的refresh token，授权范围gmail.send。设置GMAIL_SENDER、GMAIL_CLIENT_ID、GMAIL_CLIENT_SECRET、GMAIL_REFRESH_TOKEN，明确将EMAIL_DELIVERY_MODE改为gmail后重启Worker。
6. 用明确授权的测试收件Gmail验收邮件内容、服务商接受和实际到达。只有provider_accepted不保证收件；异常重试可能重复发送。登录用户不需要授权PACE读自己的邮箱。

缺Google配置时不会有身份绕过；不要在生产注入TestIdentity或seed假账号。`/readyz`只检查配置与DBrevision，不发送测试邮件、不调用模型，也不探测Worker存活。具体返回见[INTERFACES](INTERFACES.md)。

## Host 接入包与授权收集

接入包源码在[plugins/pace](../plugins/pace/plugin.json)，配置在[mcp.json](../plugins/pace/mcp.json)，流程见[连接skill](../plugins/pace/skills/connections/SKILL.md)。当前MCP地址指向本地API；部署时在私有打包副本改为实际公网HTTPS地址，不把Token放进manifest。包未自动安装到当前Host，也未发布。

本地collector只接受已授权根目录和明确相对文件列表，不扫描其它文件、不联网。示例（先由用户授权相应文件上传到PACE）：

```bash
uv run python plugins/pace/scripts/collect.py --root /absolute/authorized/root --file profile.md --file notes.txt --output .local/sync-input.json
```

拒绝输出覆盖；重新收集使用新文件/请求ID，重试原操作保留原载荷与ID。远端connector由Host按其权限读取，计算提交文本hash。files为完整当前授权集合，不是增量补丁；[]会撤销所有来源。模型输入预算可能小于契约上传上限，超出时缩小授权集合后以新请求ID提交。

在Host连接实际/mcp后验收发现、两项Tool、Google授权、首次sync/build/connect及返回后的再次收集sync。MCP Events需要Host提供callback和secret，不能编造；使用公网HTTPS后验收challenge、订阅刷新、签名、过期、撤销与410/413。官方支持边界见[MCP Events](https://developers.openai.com/plugins/build/mcp-events)及[插件打包](https://developers.openai.com/plugins/build/plugins)。

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
