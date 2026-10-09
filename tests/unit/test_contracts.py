# 模块说明
# 验证正式Tool输入与结果形状，不触发业务持久化。
#
# 合成文件的SHA-256由测试计算，分别改变类型 /hash /时间模拟无效输入。
# 测试覆盖显式更新、身份注入、No Match披露与规范化hash，非所有大小边界或并发规则。

import hashlib
from uuid import UUID

import pytest
from pydantic import ValidationError

from pace.application.contracts import ConnectInput, ConnectResult, SyncEntityInput, payload_hash

REQUEST = str(UUID(int=1))


# 实现说明：file_payload
# 构造自洽的合成Markdown来源对象。
#
# hash始终由传入文本UTF-8计算，观察时间含时区；各负例再明确破坏一个条件。
def file_payload(text="synthetic facts"):
    return {
        "source_id": "profile",
        "name": "profile.md",
        "text": text,
        "content_hash": hashlib.sha256(text.encode()).hexdigest(),
        "observed_at": "2026-10-07T12:00:00+08:00",
    }


# 实现说明：test_sync_requires_explicit_update_but_accepts_explicit_empty_files
# 验证无任何更新应拒绝，而显式files=[]应保留为空集合。
#
# 此测试固定None与[]的契约区别，不决定后续文件合并业务。
def test_sync_requires_explicit_update_but_accepts_explicit_empty_files():
    with pytest.raises(ValidationError):
        SyncEntityInput(request_id=REQUEST)
    assert SyncEntityInput(request_id=REQUEST, files=[]).files == []


# 实现说明：test_files_require_verified_hash_text_type_and_aware_timestamp
# 参数化破坏hash、文件扩展名或时间时区，均必须校验失败。
#
# 每例只改变一个条件，方便定位被验证的边界。
@pytest.mark.parametrize(
    "change",
    [{"content_hash": "0" * 64}, {"name": "profile.pdf"}, {"observed_at": "2026-10-07T12:00:00"}],
)
def test_files_require_verified_hash_text_type_and_aware_timestamp(change):
    payload = file_payload()
    payload.update(change)
    with pytest.raises(ValidationError):
        SyncEntityInput(request_id=REQUEST, files=[payload])


# 实现说明：test_duplicate_files_and_updates_are_rejected
# 拒绝同次调用重复来源ID和同类长期项ID。
#
# 防止更新执行顺序决定结果，而不是用户明确输入决定结果。
def test_duplicate_files_and_updates_are_rejected():
    with pytest.raises(ValidationError):
        SyncEntityInput(request_id=REQUEST, files=[file_payload(), file_payload()])
    update = {"operation": "remove", "entry_id": REQUEST}
    with pytest.raises(ValidationError):
        SyncEntityInput(request_id=REQUEST, demand_updates=[update, update])


# 实现说明：test_identity_cannot_be_injected_into_tool_input
# extra=forbid必须挡住额外pace_user_id。
#
# 可信身份应由传输层提供，不能让模型借参数改用户。
def test_identity_cannot_be_injected_into_tool_input():
    with pytest.raises(ValidationError):
        SyncEntityInput(request_id=REQUEST, files=[], pace_user_id=REQUEST)


# 实现说明：test_connect_has_no_implicit_long_term_updates_and_requires_timezone
# connect可表达即时请求，但不能接收demand_updates额外字段。
#
# 同时检查有效IANA时区与无效时区拒绝，不默认猜时区。
def test_connect_has_no_implicit_long_term_updates_and_requires_timezone():
    data = {
        "request_id": REQUEST,
        "request_text": "Find a partner",
        "context": {"observed_at": "2026-10-07T12:00:00Z", "timezone": "Asia/Shanghai"},
    }
    assert ConnectInput.model_validate(data).request_text == "Find a partner"
    with pytest.raises(ValidationError):
        ConnectInput.model_validate({**data, "demand_updates": []})
    data["context"]["timezone"] = "invalid-zone"
    with pytest.raises(ValidationError):
        ConnectInput.model_validate(data)


# 实现说明：test_no_match_cannot_expose_contact_or_connection
# No Match若带连接ID应校验失败。
#
# 该分支不能形成隐含匹配或通知；真实事务规则还需后续用例测试。
def test_no_match_cannot_expose_contact_or_connection():
    with pytest.raises(ValidationError):
        ConnectResult(
            status="no_match", request_id=REQUEST, entity_version=1, connection_id=REQUEST
        )


# 实现说明：test_payload_hash_is_stable_and_detects_changed_input
# 验证同一规范输入重建后hash一致，而改变文件输入后hash不同。
#
# 不把此工具测试宣称为完整持久幂等重放。
def test_payload_hash_is_stable_and_detects_changed_input():
    first = SyncEntityInput(request_id=REQUEST, files=[])
    second = SyncEntityInput(request_id=REQUEST, files=[file_payload()])
    assert payload_hash(first) == payload_hash(SyncEntityInput.model_validate(first.model_dump()))
    assert payload_hash(first) != payload_hash(second)
