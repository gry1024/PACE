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
| PROVIDER_TIMEOUT_SECONDS | 20，>0 | Jev Adapter 单请求超时 |
| JEV_INPUT_BYTES | 24000，1000–24000 | Jev 输入 JSON 保守预算 |
| SELECTION_CONCURRENCY | 4，1–16 | connect / demo 单次 Tournament 的并发上限 |
| WORKER_LEASE_SECONDS | 300，≥3 | 领取租约，heartbeat 每三分之一周期续租 |
| WORKER_POLL_SECONDS | 2，>0 | Worker 空队列休眠秒数 |
| CONNECT_TIMEOUT_SECONDS / MAX_CANDIDATES | 60秒 / 128，分别≤300 / ≤1000 | 单次连接总选择预算；超限报错 |
| PUBLIC_BASE_URL | http://127.0.0.1:8000 | HTTPS origin，HTTP仅loopback；固定issuer与/mcp resource |
| GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET | 未配置 | Google Web OAuth，仅openid/email |
| ENCRYPTION_KEY | 未配置 | 长期Fernet密钥；clientsecret/verifier/webhooksecret密文 |
| OAUTH_REDIRECT_ALLOWLIST | []，JSON精确URI / 受限callback_id模板列表 | 受信任Host精确回跳或受限callback_id模板；开发环境另允许HTTP loopback |
| OAUTH_ACCESS_SECONDS / OAUTH_REFRESH_SECONDS | 3600 / 2592000 | access与refresh有效期，轮换旧族立即失效 |
| EMAIL_DELIVERY_MODE / CAPTURE_DIRECTORY | capture / .local/mail | 本地捕获或gmail；不接受其它模式 |
| GMAIL_SENDER | 未配置，个人Gmail | 独立系统发件账号 |
| GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / GMAIL_REFRESH_TOKEN | 未配置 | 发件账号独立gmail.send OAuth授权 |

后端不构建 Ontology，旧 OPENAI_* / ONTOLOGY_* 字段被忽略，已有私有 env 不需删除或改写。Jev 只在 connect / 显式诊断调用，启动不自动消耗额度。`doctor --database` 使用 psycopg 原始连接参数，建议环境采用普通 `postgresql://` URL；不要向它提供 SQLAlchemy 专用 `postgresql+psycopg://` URL。

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

生产注册表只包含 email.send / event.deliver；API 和 Worker 需要相同配置。默认邮件 capture，只有明确配置 gmail 才真实发送；空队列 --once 正常退出不能证明 Worker 已处理业务。

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
# 有限真实闭环：最多2次Jev，后端零LLM，仅合成资料与本地捕获
uv run python scripts/demo_business.py --live
```

默认 demo = fixture_orchestration_only；答案来自 offline_demo_winner，不是模型判断。live = live_jev_synthetic，使用 Jev Adapter，不创建业务数据。doctor 无参数只输出包版本和配置 bool；--database 做 SELECT 1；--providers 仅 Jev 最小诊断，仅输出状态 / 类型 / 耗时，不证明 PA 画像或模型效果。

demo_business 使用独立随机 pace_demo_* schema，执行完整迁移和持久用例、Worker、通知capture，finally只删除自身schema与临时捕获目录。需要数据库CREATE SCHEMA权限；不向真人发送邮件。默认两个选择是离线桩，不证明效果；--live调用实际Provider且不自动扩大预算。避免为了重复检查接线不断运行付费命令。

## Gmail 身份与发件配置

人工操作只有一个入口：`.local/MVP_HANDOFF.md` 内的一张顺序表，具体点击步骤与填写格在同一行。按表中状态继续；公开 [入口说明](MVP_SETUP_CHECKLIST.md) 不含待填模板。旧表仅在 `.local/backups/` 留档，不填写备份或 docs。

保留现有 `.env` 与 `.env.local`；只在私有配置中补充 `.env.example` 展示的字段。API与Worker使用相同持久Key，禁止把Fernet Key放日志、聊天、Git或公开终端历史。

1. 在Google Cloud配置Web OAuth客户端，注册精确redirect：`PUBLIC_BASE_URL/auth/google/callback`，设置相应同意屏幕与测试用户。PACE只申请openid/email，不接受非个人@gmail.com。
2. 私有配置填GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET及稳定Fernet ENCRYPTION_KEY。Key可用cryptography的Fernet.generate_key生成，并直接安全保存；不要把实际Key当作调试输出。
3. 为目标Host将其实际OAuth回跳URI加入OAUTH_REDIRECT_ALLOWLIST（JSON列表）。只允许可信精确地址，或显式配置 `https://chatgpt.com/connector/oauth/{callback_id}` 这样的单段 ID 模板；不是任意 URL 通配。当前 ChatGPT 也允许精确固定 URI `https://chatgpt.com/connector_platform_oauth_redirect`，依据官方回跳模式使用。生产设置APP_ENV=production；PUBLIC_BASE_URL是origin且生产为HTTPS，不能带path/query。
4. 迁移至head，同时启动API与Worker。使用Host OAuth授权，检查同意页、Google Gmail登录、同账号跨Host关联、401/过期/撤销行为。字段存在与离线模拟不能代替真人Google验收。
5. 真实发件使用独立系统Gmail，在Google启用Gmail API，按[Google服务器端OAuth流程](https://developers.google.com/identity/protocols/oauth2/web-server)获取系统发件账号的refresh token，授权范围gmail.send。设置GMAIL_SENDER、GMAIL_CLIENT_ID、GMAIL_CLIENT_SECRET、GMAIL_REFRESH_TOKEN，明确将EMAIL_DELIVERY_MODE改为gmail后重启Worker。 External + Testing 的 gmail.send refresh token 通常只有7天有效；正式运行前补齐真实品牌网页、切换生产状态并按适用要求处理审核，再重新授权获取令牌。Access token 可自动刷新，但不能延长测试 refresh token 的固定期限；当前实际配置 / 验收进度见 [STATUS](STATUS.md#配置与外部验收进度日志)。
6. 用明确授权的测试收件Gmail验收邮件内容、服务商接受和实际到达。只有provider_accepted不保证收件；异常重试可能重复发送。登录用户不需要授权PACE读自己的邮箱。

缺Google配置时不会有身份绕过；不要在生产注入TestIdentity或seed假账号。`/readyz`只检查配置与DBrevision，不发送测试邮件、不调用模型，也不探测Worker存活。具体返回见[INTERFACES](INTERFACES.md)。

### Google 登录网络诊断

浏览器能打开 Google 不代表后端能访问 Google。API 必须能访问 oauth2.googleapis.com/token 与 Google 签名证书接口；Worker 发件还需要 gmail.googleapis.com。先用不带凭据的请求检查连通性，HTTP 400/404 等说明已经连通，000 / timeout 则需修复网络。不要重复使用已消费的登录回跳；重新从插件发起完整授权。

```bash
curl -s -o /dev/null --connect-timeout 5 --max-time 12 -w '%{http_code}\n' https://oauth2.googleapis.com/token
curl -s -o /dev/null --connect-timeout 5 --max-time 12 -w '%{http_code}\n' https://www.googleapis.com/oauth2/v1/certs
```

`gmail_authorization_failed` 的详细诊断只看受限私有日志中的 reason：invalid_browser_flow 是 cookie / state / 同意输入未通过，expired_or_consumed_flow 需重新授权；Google 调用异常只记录异常类名。禁止打印回调完整 URL、原始异常或完整环境配置。CSP 放行 Google 并不证明浏览器实际跳转或 Google 回跳已验收。

## Host 接入包与连接前同步

接入包在 [plugins/pace](../plugins/pace/plugin.json)，OAuth / scopes 声明在 [mcp.json](../plugins/pace/mcp.json)，安装阶段执行 [setup skill](../plugins/pace/skills/setup/SKILL.md)，日常请求执行 [连接 skill](../plugins/pace/skills/connections/SKILL.md)。本地 MCP 地址只用于开发，部署在私有副本改公网 HTTPS URL；没有自动安装或发布。

初期验收 ChatGPT Work 网页 / 桌面 Cloud 及 dots，实际账号需开放事件触发任务。仅做原生 MCP Events 回调，不适配不接收事件 / 不能运行 PA 的平台。Host 提供 callback 和 secret，PACE 验证并持久化；不要人工编造 env。验收 OAuth、订阅 / challenge / 刷新、连接匹配、签名事件、PA 实际通知用户及 Gmail 到达。插件安装不代表已建立监控，参考 [官方 Events](https://developers.openai.com/plugins/build/mcp-events) 和 [插件打包](https://developers.openai.com/plugins/build/plugins)。

安装阶段先 sync 初始化，让用户无需先发起连接也能被匹配。首次 Google 登录创建 Account 并取得持续上传 / 披露同意，无独立注册站点；旧同意版本需重新完成浏览器流程。PACE 不逐次要求人确认上传，但 Host 工具与监控权限仍必须设置。每个新 connect 前 PA 直接从记忆生成完整 O/D/S，sync 立即 ready，再把返回的 entity_version 带入 connect。内容未变不增加版本；三字段空值明确清除。连接后、事件接收时和定时不更新，不需要本地 collector 或文件输入。

完整契约和字节预算见 [INTERFACES](INTERFACES.md)。Worker 仅投递通知，订阅到期刷新由 Host 维护，不是定时同步。旧 ontology.build 任务不会执行构建，按未知任务有限失败；升级后的旧 LLM 画像需 PA 首次同步才重新进入候选。

| 现象 | 直接检查 |
| --- | --- |
| 数据库连接失败 | dev_db.sh status；检查配置覆盖；项目日志在 `.local/postgres.log`，勿公开凭据 / 私人数据 |
| pg_ctl 不存在 | 安装 PostgreSQL 或设置 PG_BIN |
| 端口冲突 | 查看项目日志、选择首次初始化端口；不要停止未知服务 |
| /mcp 401 / 503 | INTERFACES 默认身份边界；不能编造 Token 绕过 |
| 输入过长 | O/D/S 4000 UTF-8 bytes 与 Jev 整体输入 / HTTP body 的独立限额；缩小输入，不静默截断硬约束 |
| migration 漂移 | 核对 ORM 与 migration；运行 alembic check，不用 create_all 掩盖 |
| 修改环境后未生效 | 重启进程，区分文件配置与环境覆盖 |

## 独立服务器部署

部署文件在 `deploy/`：Dockerfile 使用 Python 3.12 与 uv.lock；compose 分开 API、Worker、PostgreSQL，数据库不发布宿主机端口，API 仅绑定 127.0.0.1:8010。远端工作目录为 `/home/dev/pace`；私有 `.env` 需要 PACE_DB_PASSWORD、独立 DATABASE_URL、稳定 ENCRYPTION_KEY、PUBLIC_BASE_URL 及已有 Provider / Gmail 配置。不得复制本机开发数据库连接串或把秘密加入镜像。

在远端工作目录运行：

```bash
docker compose --env-file .env -f deploy/compose.yaml build api
docker compose --env-file .env -f deploy/compose.yaml up -d db
docker compose --env-file .env -f deploy/compose.yaml run --rm api alembic upgrade head
docker compose --env-file .env -f deploy/compose.yaml up -d api worker
docker compose --env-file .env -f deploy/compose.yaml ps
```

`public/` 是邀请测试首页、隐私说明与条款；安装到 `/var/www/pace`。Nginx 模板复用 clawcrony.com 的现有证书，以根域名为 origin，www 跳转根域名；安装前备份原站点，`nginx -t` 成功后 reload，失败恢复备份。关闭访问日志，避免 OAuth 查询参数进入日志。证书续期不由 Compose 管理，需单独维护。

首轮服务器网络下载缓慢，实际使用私有 `.local/Dockerfile.offline` 与 `.local/compose.offline.yaml` 构建：先在本机独立项目副本执行 `uv sync --offline --locked --no-dev --no-editable`，仅传输生成的运行虚拟环境，通过 BuildKit additional_contexts 安装，并修正 Python / 命令入口的绝对路径。镜像导入与真实迁移校验必须通过；不可直接把含开发依赖或凭据的本机环境当生产制品。网络恢复后可用上面的标准锁文件构建流程。

数据库迁移独立执行，服务启动不会自动迁移。不要使用 `down -v`，该命令会删除 PACE 数据卷；旧应用目录、数据库和凭据保留。停止旧服务须核对归属与用户授权，不能把所有数据库或容器都视作旧应用。当前服务器部署 / 公网验收结果见 [STATUS](STATUS.md)。

## Documentation validation

```bash
uv run python scripts/check_docs.py
```

检查当前 README / AGENTS / docs 的本地链接、anchor、围栏，并要求 CODEMAP 覆盖项目 Python 实现文件。历史 sources 原样保留，不检查其 Notion 内部链接。检查不访问外部服务、不维护旧指纹 catalog；语义、完成度与 symbol 仍须人工对照。
