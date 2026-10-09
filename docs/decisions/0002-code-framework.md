# ADR-0002: 代码框架、包复用与分层

Status: Accepted
Date: 2026-10-08

## Context

用户要求先搭整体代码框架并写清架构，优先复用现成包，MCP 指定官方 python-sdk，Jev 使用 SDK。本记录限定框架选择，不改变 [ADR-0001](0001-mvp-baseline.md) 的 MVP 决定。下文保留当时决定与验证描述；当前实现 / 实测以 [STATUS](../STATUS.md) 为准，文件导航见 [CODEMAP](../CODEMAP.md)。本次仅规范格式和导航，未变更历史决定。

## Decision

一个 Python 包、一个 PostgreSQL，API 与 Worker 独立进程。domain / application / adapters / interfaces 分层，由 bootstrap 装配。初期不拆微服务，不引入泛化 Repository / CQRS / DI 框架；有具体事务后再增加所需 Repository，避免空类和多层转发。

复用官方 mcp、typesafe-sdk、openai；复用 FastAPI / Pydantic、SQLAlchemy asyncio / psycopg、Alembic。发行包使用 uv.lock 固定，不 vendoring 或直接追 Git main。已核对 mcp 包 metadata 的 Repository 是用户指定的 modelcontextprotocol/python-sdk。

MCP 使用官方 Server 的回调与 StreamableHTTPSessionManager。选择其公开底层 API，是为了直接使用 Pydantic 的平坦输入契约，并集中处理结构化错误；无需自己实现 JSON-RPC、HTTP 会话、协议发现或验证器。未来 OAuth 优先使用同 SDK 的 auth 能力；当前简短身份 Port 边界只做拒绝未验证请求，不声称是 OAuth 实现。

Jev Adapter 仅组织 Request / context / Snapshot evidence、调用 AsyncTypeSafeClient.system_one + Choice、转换返回值。淘汰赛属于 PACE 业务规则，放在 application，不能由 SDK 调用层藏匿。

仅增加 jobs 基础设施表，六张业务表沿用冻结文档。工作提交由调用者事务控制；Worker 使用租约和 SKIP LOCKED，不要求 Redis / Celery。交付是至少一次，业务 Handler 必须幂等；租约不能保证外部服务恰好执行一次。

未实现能力使用 FeatureUnavailable；/readyz 返回 503。测试通过 create_app 注入合成身份 / 命令，不增加生产绕过开关，不接受 Tool 参数中的用户 ID 决定身份。

## Consequences

账号 / OAuth、Ontology 版本切换、连接幂等与业务事务仍待实现。表和 Schema 只是边界，不能替代这些用例。entity_versions 的不可变约定目前尚无数据库 Trigger；由后续只追加的用例控制并测试。

目前不实现 OpenAI events/* webhook 扩展；官方核心 SDK 与该扩展分别验收。需要适配时先检查官方支持，再写最小差异层。

队列租约、重试与幂等有实际 PostgreSQL 验证，业务 Handler 尚未注册。未知 kind 明确失败而非模拟通知。

每个组保留概率与用量；不输出秘密、原始私人文件或外部异常全文。当前 Jev 字节预算是保守输入限制，不是精确 token 计数；不自动截断用户硬约束。
