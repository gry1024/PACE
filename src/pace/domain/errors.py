# 模块说明
# 稳定的业务错误码与可安全公开的错误消息。
#
# HTTP 身份边界使用 status_code；MCP Tool 调用使用 code / public_message 生成 isError。
# 异常不接收外部响应正文，避免 Provider URL、凭据或私人文件被直接暴露。
# 错误与有效 No Match 必须区分，调用失败不能伪装成没有合适候选。

"""Stable, safe errors shared by application and transports."""


# 实现说明：PaceError
# 所有可公开业务错误的基类。
#
# 子类通过固定 code / status_code / public_message 描述类别，不携带原始私人输入。
class PaceError(Exception):
    code = "internal_error"
    status_code = 500
    public_message = "PACE could not complete the operation."

    # 实现说明：PaceError.__init__
    # 只把固定公开消息写入异常文本。
    #
    # 内部异常可通过 raise ... from ... 保留诊断链，但对外只使用公开字段。
    def __init__(self):
        super().__init__(self.public_message)


# 实现说明：FeatureUnavailable
# 框架已有接口但具体能力未接线。
#
# 使用 503 表示暂不可用；默认身份与命令都走此错误，而非伪造 accepted / matched。
class FeatureUnavailable(PaceError):
    code = "feature_unavailable"
    status_code = 503
    public_message = "This capability requires additional PACE configuration."


# 实现说明：AuthenticationRequired
# 缺少可校验的 Bearer 凭据，HTTP 状态为 401。
#
# 身份校验发生在发现和调用前，不能依赖模型自行声称登录。
class AuthenticationRequired(PaceError):
    code = "authentication_required"
    status_code = 401
    public_message = "A verified access token is required."


# 实现说明：ProviderUnavailable
# 真实选择 Provider 调用失败，HTTP 对应 502。
#
# 不把网络失败或服务端错误改写为 No Match。
class ProviderUnavailable(PaceError):
    code = "provider_unavailable"
    status_code = 502
    public_message = "The selection provider is unavailable."


# 实现说明：InvalidSelection
# Provider 返回不满足选择契约。
#
# 包括无效候选 ID、概率分布或响应字段；应失败并保留诊断，不默选候选。
class InvalidSelection(PaceError):
    code = "invalid_selection"
    status_code = 502
    public_message = "The selection provider returned an invalid decision."


# 实现说明：InputTooLarge
# 输入超过保守预算，对应 413。
#
# 用户必须缩小输入；系统不静默截掉时间、地点等硬约束。
class InputTooLarge(PaceError):
    code = "input_too_large"
    status_code = 413
    public_message = "Input exceeds the configured budget; reduce the input."


# 实现说明：IdempotencyConflict
# 同一稳定请求 / 任务键用于不同有效载荷，对应 409。
#
# 冲突不能重置原任务或重复创建连接。
class IdempotencyConflict(PaceError):
    code = "idempotency_conflict"
    status_code = 409
    public_message = "This request key has already been used with different input."


class AccountUnavailable(PaceError):
    """账号未完成 Gmail 验证 / 披露同意或被禁用。"""

    code = "account_unavailable"
    status_code = 403
    public_message = "A verified, enabled Gmail account with connection consent is required."


class EntityNotReady(PaceError):
    """缺少已完成快照，不能使用 building 数据选择。"""

    code = "entity_not_ready"
    status_code = 409
    public_message = "Complete an entity build before connecting."


class VersionConflict(PaceError):
    """乐观版本与当前接受版本不符。"""

    code = "version_conflict"
    status_code = 409
    public_message = "The entity changed; retry with its current version."


class SelectionLimit(PaceError):
    """整体选择预算不足；不可静默截候选造成伪 No Match。"""

    code = "selection_limit"
    status_code = 503
    public_message = "Selection exceeded its configured time or candidate budget."


class DeliveryUnavailable(PaceError):
    """通知通道缺配置或服务失败，保留任务以供有限重试。"""

    code = "delivery_unavailable"
    status_code = 502
    public_message = "The notification delivery could not be completed."


class PermanentDeliveryError(DeliveryUnavailable):
    """已终止或过大 webhook 不应继续重试。"""

    code = "delivery_terminal"
