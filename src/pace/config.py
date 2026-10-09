# 模块说明
# 集中管理 PACE 配置与秘密字段。
#
# pydantic-settings 负责环境解析和类型校验；本模块只定义配置，不调用数据库或模型。
# 读取顺序为 .env、.env.local、进程环境，后者覆盖前者；空配置值被忽略。
# 真实 Key / 连接串使用 SecretStr 包装，默认 repr 不展开；Adapter 调用时才显式取明文。

"""Typed local configuration; credentials are never returned by API endpoints."""

from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


# 实现说明：Settings
# 应用运行配置与边界限制。
#
# 字段默认值用于本地框架，不代表已完成生产限流或效果校准。
# 数据库 / 模型配置可缺省，进程仍可提供存活检查；业务就绪由实际接线决定。
# TYPESAFE_API_KEY 为官方名称，优先于兼容旧项目的 JEV_API_KEY。
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    app_env: str = "development"
    # 单次 Provider 网络请求超时，不是完整 connect 的总耗时上限。
    provider_timeout_seconds: float = Field(default=20, gt=0)
    # 保守 JSON 输入字节预算；允许缩小，不允许超过当前验证的上限。
    jev_input_bytes: int = Field(default=24000, ge=1000, le=24000)
    # 每次 Tournament 的同轮并发；多个请求仍会叠加，不是全局限流。
    selection_concurrency: int = Field(default=4, ge=1, le=16)
    # Worker 的任务占有有效期；执行中以该值的三分之一周期续租。
    worker_lease_seconds: int = Field(default=300, ge=3)
    # 空队列时的轮询间隔，避免不断查询数据库形成忙循环。
    worker_poll_seconds: float = Field(default=2, gt=0)
    # 连接串可能包含密码，不能进入响应、日志或公共文档。
    database_url: SecretStr | None = None
    # 通过别名显式兼容旧 Key；仅 SDK Adapter 可以为调用取得明文。
    jev_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("TYPESAFE_API_KEY", "JEV_API_KEY")
    )
    jev_model: str = "jev-1.13.0"
    openai_api_key: SecretStr | None = None
    # 允许配置 OpenAI 兼容服务；配置存在不意味着 Ontology 已实现。
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model_name: str | None = None


# 实现说明：get_settings
# 获取进程内缓存的配置实例。
#
# lru_cache 避免每次请求重新读取环境文件，也使同一进程的依赖配置稳定。
# 运行期间修改 .env 不会更新已有缓存 / Client；实际切换配置需重启。
# 测试应传显式 Settings，或有意识地清缓存，避免依赖真实凭据。
@lru_cache
def get_settings() -> Settings:
    return Settings()
