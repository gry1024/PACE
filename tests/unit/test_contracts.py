# 模块说明：直接 PA 完整画像契约；校验预算、全量替换与可信身份边界。
from uuid import UUID

import pytest
from pydantic import ValidationError

from pace.application.contracts import ConnectInput, ConnectResult, SyncEntityInput, payload_hash

REQUEST = str(UUID(int=1))


def profile(**overrides):
    """合成 O/D/S；测试不使用用户记忆或真实个人资料。"""
    return dict(request_id=REQUEST, ontology="Python teacher", demands=[], supplies=[], **overrides)


def test_sync_requires_all_profile_fields_and_accepts_explicit_clear():
    for field in ("ontology", "demands", "supplies"):
        data = profile()
        del data[field]
        with pytest.raises(ValidationError):
            SyncEntityInput.model_validate(data)
    assert SyncEntityInput(request_id=REQUEST, ontology="", demands=[], supplies=[]).ontology == ""


@pytest.mark.parametrize(
    "change",
    [
        {"demands": [" "]},
        {"supplies": ["same", "same"]},
        {"ontology": " "},
        {"ontology": "汉" * 1334},
        {"ontology": "x" * 3999, "supplies": ["xx"]},
        {"files": []},
        {"pace_user_id": REQUEST},
    ],
)
def test_invalid_profile_or_extra_identity_is_rejected(change):
    with pytest.raises(ValidationError):
        SyncEntityInput.model_validate({**profile(), **change})


def test_connect_requires_sync_version_and_has_no_long_term_updates():
    data = dict(
        request_id=REQUEST,
        entity_version=1,
        request_text="Find a partner",
        context={"observed_at": "2026-10-10T12:00:00Z", "timezone": "Asia/Shanghai"},
    )
    assert ConnectInput.model_validate(data).entity_version == 1
    for change in (
        {"entity_version": 0},
        {"demands": []},
        {"context": {"observed_at": "2026-10-10T12:00:00", "timezone": "invalid"}},
    ):
        with pytest.raises(ValidationError):
            ConnectInput.model_validate({**data, **change})
    del data["entity_version"]
    with pytest.raises(ValidationError):
        ConnectInput.model_validate(data)


def test_no_match_cannot_expose_contact_or_connection():
    with pytest.raises(ValidationError):
        ConnectResult(
            status="no_match", request_id=REQUEST, entity_version=1, connection_id=REQUEST
        )


def test_payload_hash_is_stable_and_detects_changed_input():
    first = SyncEntityInput.model_validate(profile())
    second = SyncEntityInput.model_validate({**profile(), "ontology": "Changed"})
    assert payload_hash(first) == payload_hash(SyncEntityInput.model_validate(first.model_dump()))
    assert payload_hash(first) != payload_hash(second)
