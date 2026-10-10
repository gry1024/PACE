# 模块说明
# 与平台、数据库、模型 SDK 无关的领域数据值。
#
# Snapshot 表示某一版本的 O / D / S，Selection 表示选择结果而非已提交 Match。
# 所有 dataclass 冻结属性，避免在淘汰赛过程中重新赋值；其中 dict 仍可原地修改，非深度不可变。
# 这些对象不负责资格过滤、Email 验证、持久化或通知。

"""Immutable values; no SQLAlchemy, MCP or provider dependencies."""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

# 持续授权的范围升级需要重新完成同意页；旧授权不能自动扩大。
CONSENT_VERSION = "pa-connections-v2"


# 实现说明：Principal
# 经传输层验证的访问者身份。
#
# user_id 是稳定 UUID；scopes 为已验证凭据授予的权限集合。
# 不能用 Tool arguments 中的用户 ID / Email 构造可信 Principal。
@dataclass(frozen=True)
class Principal:
    user_id: UUID
    scopes: frozenset[str]
    client_id: str = ""


# 实现说明：EntitySnapshot
# 单次选择使用的已完成实体快照。
#
# ontology 是抽象文本，demands / supplies 是长期意图元组；即时 Request 单独传递。
# 同一 Tournament 轮次间沿用同一个 requester Snapshot，避免中途刷新改变判断基底。
@dataclass(frozen=True)
class EntitySnapshot:
    user_id: UUID
    version: int
    ontology: str
    demands: tuple[str, ...] = ()
    supplies: tuple[str, ...] = ()


# 实现说明：ChoiceDecision
# 单个候选组的模型选择及诊断信息。
#
# probabilities 只在该组内有效，不能跨组比较或解释为现实成功率。
# model / usage / confidence 用于审查 Provider 返回；概率合法性由 Tournament 校验。
@dataclass(frozen=True)
class ChoiceDecision:
    choice: str
    probabilities: dict[str, float]
    model: str
    confidence: float | None = None
    usage: dict[str, Any] = field(default_factory=dict)


# 实现说明：RoundTrace
# 记录一轮中某个分组的输入 ID、最终 Winner 和原始选择。
#
# winner 可能因并列规则与原始 choice 不同；decision 保留原诊断信息便于解释。
# 当前没有耗时、Prompt 版本或候选 Snapshot 版本，尚非完整可重放日志。
@dataclass(frozen=True)
class RoundTrace:
    round_number: int
    group_number: int
    candidate_ids: tuple[str, ...]
    winner: str
    decision: ChoiceDecision


# 实现说明：Selection
# Tournament 的最终结果。
#
# candidate_id=None 表示有效 No Match；traces 可为空（例如零候选）。
# 这不是数据库 Match，也不会自行披露 Email 或入队通知。
@dataclass(frozen=True)
class Selection:
    candidate_id: UUID | None
    traces: tuple[RoundTrace, ...]
