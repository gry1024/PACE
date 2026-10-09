# 模块说明
# 使用固定合成池观察 Tournament 的轮次和官方 Jev SDK 接线。
#
# 默认FixtureChoice只返回预设答案，不是第二套算法，也不能作模型效果证据。
# --live显式调用真实TypeSafe SDK，会产生API用量；输入仍是仓库中的合成文本。
# 两模式都不写账号、Request、Match、任务或通知，不触发Ontology刷新。

"""Inspect the framework Tournament with synthetic data; not a business connection."""

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from pace.adapters.providers.jev import JevChoiceProvider
from pace.application.contracts import RequestContext
from pace.application.tournament import Tournament
from pace.config import Settings
from pace.domain.errors import PaceError
from pace.domain.models import ChoiceDecision, EntitySnapshot


# 实现说明：FixtureChoice
# 只供演示编排的预设选择Provider。
#
# 组内有指定Winner就选它，否则选no_match，作用是可复现轮次而非判断真实匹配。
class FixtureChoice:
    """Fixed synthetic decisions for demonstrating orchestration, never a quality evaluation."""

    # 实现说明：FixtureChoice.__init__
    # 保存合成样例的人为预设候选ID。
    #
    # 这份答案不能被当作独立人工评测集或算法推断。
    def __init__(self, winner: str):
        self.winner = winner

    # 实现说明：FixtureChoice.choose
    # 为当前组产生合法的一位有效概率分布。
    #
    # 保持ChoiceProvider签名，让离线与真实模式走同一Tournament，便于区分接线与质量。
    async def choose(self, requester, request_text, candidates, context=None):
        keys = [str(c.user_id) for c in candidates] + ["no_match"]
        winner = self.winner if self.winner in keys else "no_match"
        return ChoiceDecision(winner, {key: float(key == winner) for key in keys}, "fixture")


# 实现说明：snapshot
# 将合成JSON描述转换为领域Snapshot。
#
# UUID显式解析，D/S转换为元组，避免演示直接绕过领域数据形状。
def snapshot(data):
    return EntitySnapshot(
        user_id=UUID(data["user_id"]),
        version=data["version"],
        ontology=data["ontology"],
        demands=tuple(data["demands"]),
        supplies=tuple(data["supplies"]),
    )


# 实现说明：run
# 选择离线 /真实Provider并输出可读轮次诊断。
#
# 真实模式必须有配置Key；无Key返回安全错误，不猜测账号或默认模型凭据。
# 输出mode与无业务副作用说明；异常只暴露固定PaceError，finally关闭真实Client。
async def run(live: bool):
    # 读取仓库固定合成池；不扫描用户磁盘或把私人资料送入演示。
    data = json.loads(
        (Path(__file__).resolve().parent.parent / "examples/selection_pool.json").read_text()
    )
    settings = Settings()
    if live and settings.jev_api_key is None:
        print(json.dumps({"error": "missing_jev_key"}))
        return 1
    # 由显式--live开关决定联网；默认执行不会产生模型用量。
    provider = (
        JevChoiceProvider(
            settings.jev_api_key.get_secret_value(),
            settings.jev_model,
            timeout=settings.provider_timeout_seconds,
            input_bytes=settings.jev_input_bytes,
        )
        if live
        else FixtureChoice(data["offline_demo_winner"])
    )
    try:
        # 真实和fixture共用编排逻辑，只有单组选择Provider不同。
        selection = await Tournament(provider, settings.selection_concurrency).select(
            snapshot(data["requester"]),
            data["request"]["text"],
            [snapshot(candidate) for candidate in data["candidates"]],
            RequestContext.model_validate(data["request"]["context"]),
        )
        print(
            json.dumps(
                {
                    "mode": "live_jev_synthetic" if live else "fixture_orchestration_only",
                    "status": "selected" if selection.candidate_id else "no_match",
                    "candidate_id": str(selection.candidate_id) if selection.candidate_id else None,
                    "traces": [asdict(trace) for trace in selection.traces],
                    "note": "No account, Match, notification or ontology update is created.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except PaceError as exc:
        print(json.dumps({"error": exc.code, "message": exc.public_message}))
        return 1
    finally:
        if live:
            await provider.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Call real Jev using synthetic data.")
    raise SystemExit(asyncio.run(run(parser.parse_args().live)))
