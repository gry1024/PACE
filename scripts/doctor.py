# 模块说明
# 开发环境和服务连通性检查，不是MVP业务验收。
#
# 无参数只输出版本和配置存在布尔值；--database执行SELECT 1。
# --providers发送极少合成文本，调用官方TypeSafe /OpenAI兼容SDK，可能产生费用。
# 输出状态、观测耗时和异常类型，不输出Key、数据库连接串或完整模型响应。

"""Check the bootstrap. --providers sends synthetic text only and may incur API usage."""

import argparse
import asyncio
import importlib.metadata
import json
import platform
import time

import psycopg
from openai import APIError, AsyncOpenAI
from typesafe_sdk import AsyncTypeSafeClient, Choice, RetryPolicy, TypeSafeError

from pace.config import Settings


# 实现说明：check_providers
# 并行运行彼此独立的Jev和LLM合成连通性检查。
#
# 单次可访问不能证明模型质量、Ontology正确或真实用户连接价值。
async def check_providers(settings: Settings) -> dict:
    results = {}

    # 实现说明：check_providers.jev
    # 使用官方TypeSafe Choice检查配置Key /模型是否能完成合成选择。
    #
    # 超时20秒、自动重试0；固定期待badminton以区分访问成功与异常回答。
    # SDK通过async with关闭；失败只输出error_type，不公开异常正文。
    async def jev():
        if not settings.jev_api_key or not settings.jev_api_key.get_secret_value():
            return {"status": "missing", "field": "JEV_API_KEY or TYPESAFE_API_KEY"}
        started = time.perf_counter()
        try:
            async with AsyncTypeSafeClient(
                api_key=settings.jev_api_key.get_secret_value(),
                model=settings.jev_model,
                timeout=20,
                retry=RetryPolicy(max_retries=0),
            ) as client:
                response = await client.system_one(
                    state={"request": "Find a badminton partner.", "synthetic": True},
                    questions={
                        "match": Choice(
                            instructions="Choose the badminton candidate, otherwise no_match.",
                            criteria={
                                "badminton": "Available to play badminton.",
                                "chess": "Only available to play chess.",
                                "no_match": "No suitable candidate.",
                            },
                        )
                    },
                )
            answer = response.choices["match"]
            return {
                "status": "ok" if answer.choice == "badminton" else "unexpected_selection",
                "model": response.model,
                "choice": answer.choice,
                "latency_ms": round((time.perf_counter() - started) * 1000),
            }
        except (TypeSafeError, APIError, psycopg.Error, ValueError) as exc:
            return {"status": "error", "error_type": type(exc).__name__}

    # 实现说明：check_providers.llm
    # 使用配置中的OpenAI兼容服务请求极短合成回答。
    #
    # 要求Key和model同时存在；单次非空回应只证明接口能用，不是Ontology抽取。
    # 超时30秒、重试0、输出上限16；不回显正文或私人配置。
    async def llm():
        if (
            not settings.openai_api_key
            or not settings.openai_api_key.get_secret_value()
            or not settings.openai_model_name
        ):
            return {"status": "missing", "field": "OPENAI_API_KEY / OPENAI_MODEL_NAME"}
        started = time.perf_counter()
        try:
            async with AsyncOpenAI(
                api_key=settings.openai_api_key.get_secret_value(),
                base_url=settings.openai_base_url,
                timeout=30,
                max_retries=0,
            ) as client:
                response = await client.chat.completions.create(
                    model=settings.openai_model_name,
                    messages=[{"role": "user", "content": "Reply with the single word OK."}],
                    max_completion_tokens=16,
                )
            content = response.choices[0].message.content
            return {
                "status": "ok" if content and content.strip() else "empty_response",
                "latency_ms": round((time.perf_counter() - started) * 1000),
            }
        except (TypeSafeError, APIError, psycopg.Error, ValueError) as exc:
            return {"status": "error", "error_type": type(exc).__name__}

    # 两项网络检查相互独立，因此并行减少等待，不能合并成业务成功结论。
    results["jev"], results["llm"] = await asyncio.gather(jev(), llm())
    return results


# 实现说明：main
# 解析检查范围，输出结构化状态并以退出码表示失败。
#
# 仅显式选择的DB /Provider检查会执行网络操作；配置存在以bool表达。
# SELECT 1使用短连接超时，异常只按类别报告，避免连接串泄密。
async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", action="store_true", help="Run SELECT 1 in configured PostgreSQL"
    )
    parser.add_argument(
        "--providers", action="store_true", help="Call Jev and LLM with synthetic text"
    )
    args = parser.parse_args()
    settings = Settings()
    # 只输出依赖版本与是否配置，不打印秘密值。
    result = {
        "python": platform.python_version(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("fastapi", "mcp", "typesafe-sdk", "openai", "psycopg", "pytest", "ruff")
        },
        "configured": {
            "jev_key": bool(settings.jev_api_key and settings.jev_api_key.get_secret_value()),
            "llm_key": bool(settings.openai_api_key and settings.openai_api_key.get_secret_value()),
            "llm_model": bool(settings.openai_model_name),
            "database": bool(settings.database_url),
        },
    }
    failed = False
    if args.database:
        try:
            if not settings.database_url:
                raise ValueError("Database configuration missing")
            # 连接串只交驱动使用；诊断日志不输出URL中的密码。
            async with await psycopg.AsyncConnection.connect(
                settings.database_url.get_secret_value(), connect_timeout=5
            ) as connection:
                cursor = await connection.execute("SELECT 1")
                assert await cursor.fetchone() == (1,)
            result["database"] = {"status": "ok"}
        except (TypeSafeError, APIError, psycopg.Error, ValueError) as exc:
            result["database"] = {"status": "error", "error_type": type(exc).__name__}
            failed = True
    if args.providers:
        result["providers"] = await check_providers(settings)
        failed |= any(item["status"] != "ok" for item in result["providers"].values())
    # 检查输出可被脚本阅读，成功退出码仍不代表完整MVP完成。
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
