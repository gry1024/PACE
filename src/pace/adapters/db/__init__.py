# 模块说明
# PostgreSQL持久化与任务基础设施包入口。
#
# 包含ORM、异步Session和租约队列；表由Alembic显式迁移，不在包导入时建表。

"""Persistence and durable work queue."""
