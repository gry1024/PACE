#!/usr/bin/env bash
# 开发数据库辅助：只管理仓库.local中的独立PostgreSQL集群。
# 启动不创建业务表；业务迁移由alembic upgrade head显式完成。
# Project-local PostgreSQL cluster. Never touches the system cluster.
# 严格模式：命令失败、未定义变量或管道失败立即停止，避免半初始化继续。
set -euo pipefail
# 以脚本所在目录定位仓库，不依赖调用者cwd；所有数据限制在项目.local。
cd "$(dirname "$0")/.."
ROOT="$(pwd -P)"
# 允许指定已安装PostgreSQL二进制目录；不下载或替换系统数据库。
PG_BIN="${PG_BIN:-/usr/lib/postgresql/14/bin}"
# 项目独立集群目录，绝不指向软件包默认系统集群。
DATA="$ROOT/.local/postgres"
# 仅本项目使用的本地Unix socket；这是开发隔离，不是生产认证方案。
SOCKET="$ROOT/.local/pgsocket"
# 记录初始化端口，重启不能悄悄改到另一端口并误判数据位置。
PORT_FILE="$ROOT/.local/postgres.port"
# 首次初始化默认54329，也可显式覆盖；已有集群以保存值为准。
PORT="${PACE_PG_PORT:-54329}"
# 默认start；仅支持start /stop /status，不提供递归删除或重置操作。
ACTION="${1:-start}"
# 先检查pg_ctl存在，缺失时报错退出而不是用未知命令继续。
if [[ ! -x "$PG_BIN/pg_ctl" ]]; then
  echo "PostgreSQL binaries missing. Install postgresql-14 or set PG_BIN." >&2
  exit 1
fi
# 新建密码、配置、日志默认仅当前用户可读，避免开发凭据泄漏。
umask 077
mkdir -p "$ROOT/.local" "$SOCKET"
# 重启复用既有端口；拒绝冲突覆盖，不能为了启动停止未知服务。
if [[ -f "$PORT_FILE" ]]; then
  SAVED_PORT="$(cat "$PORT_FILE")"
  if [[ -n "${PACE_PG_PORT:-}" && "$PACE_PG_PORT" != "$SAVED_PORT" ]]; then
    echo "Existing cluster uses port $SAVED_PORT; refusing a conflicting override." >&2
    exit 1
  fi
  PORT="$SAVED_PORT"
fi
# 严格校验端口值域后才用于命令，避免无效端口 /低权限端口。
if [[ ! "$PORT" =~ ^[0-9]+$ ]] || ((PORT < 1024 || PORT > 65535)); then
  echo "PACE_PG_PORT must be an integer between 1024 and 65535." >&2
  exit 1
fi
case "$ACTION" in
  # 首次初始化与日常启动分开：已有数据不重建、不重置密码。
  start)
    # PG_VERSION表示已初始化集群；只有缺失时才允许initdb。
    if [[ ! -f "$DATA/PG_VERSION" ]]; then
      # 用户已有配置时拒绝覆盖；需明确配置数据库，不猜测或替换凭据。
      if [[ -e "$ROOT/.env.local" ]]; then
        echo ".env.local exists; refusing to replace it. Configure the database manually." >&2
        exit 1
      fi
      # 生成随机开发密码写私有文件，不把密码输出到终端或公共文档。
      python3 -c 'import secrets; print(secrets.token_hex(24))' > "$ROOT/.local/postgres.password"
      # 初始化仅本项目集群；本地socket trust /host SCRAM是开发配置。
      "$PG_BIN/initdb" -D "$DATA" -U pace --encoding=UTF8 --locale=C.UTF-8 \
        --auth-local=trust --auth-host=scram-sha-256 \
        --pwfile="$ROOT/.local/postgres.password" > "$ROOT/.local/initdb.log"
      # 连接串写被Git忽略的.env.local；禁止提交或在诊断中打印。
      printf "DATABASE_URL=postgresql://pace:%s@127.0.0.1:%s/pace\n" \
        "$(cat "$ROOT/.local/postgres.password")" "$PORT" > "$ROOT/.env.local"
      printf "%s\n" "$PORT" > "$PORT_FILE"
    fi
    # 仅当本项目集群未运行时启动；重复start保持已有数据和运行状态。
    if ! "$PG_BIN/pg_ctl" -D "$DATA" status > /dev/null 2>&1; then
      "$PG_BIN/pg_ctl" -D "$DATA" -l "$ROOT/.local/postgres.log" \
        -o "-h 127.0.0.1 -p $PORT -k $SOCKET" -w start
    fi
    # 检查pace数据库是否存在，再创建；不删除其他数据库或业务Schema。
    if ! "$PG_BIN/psql" -h "$SOCKET" -p "$PORT" -U pace -d postgres -tAc \
      "SELECT 1 FROM pg_database WHERE datname = 'pace'" | grep -qx 1; then
      "$PG_BIN/createdb" -h "$SOCKET" -p "$PORT" -U pace pace
    fi
    echo "PACE PostgreSQL ready on 127.0.0.1:$PORT (credentials in .env.local)"
    ;;
  # fast模式只停止指定项目集群；不是停止系统或其他用户PostgreSQL。
  stop) "$PG_BIN/pg_ctl" -D "$DATA" -m fast -w stop ;;
  # 查询本项目集群状态；不把进程存活当成Schema /MVP就绪。
  status) "$PG_BIN/pg_ctl" -D "$DATA" status ;;
  *) echo "Usage: bash scripts/dev_db.sh [start|stop|status]" >&2; exit 2 ;;
esac
