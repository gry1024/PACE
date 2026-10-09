# 模块说明
# 验证本地开发邮件捕获的状态、权限与重放边界。
#
# 使用临时目录和合成收件人，不联系SMTP服务，不保留私人邮件。
# 捕获成功是captured，不能解释成对方收信或已读。

import json
from uuid import uuid4

import pytest

from pace.adapters.delivery.capture import CaptureEmail


# 实现说明：test_capture_is_explicit_private_and_deduplicated
# 相同稳定ID /内容执行两次仅留下一个0600文件。
#
# 校验保存合成收件人和返回captured；同ID换主题必须冲突，禁止覆盖首个内容。
async def test_capture_is_explicit_private_and_deduplicated(tmp_path):
    adapter = CaptureEmail(tmp_path / "mail")
    delivery_id = str(uuid4())
    args = ("synthetic@example.test", "Synthetic subject", "Synthetic body", delivery_id)
    assert await adapter.deliver(*args) == "captured"
    assert await adapter.deliver(*args) == "captured"
    paths = list((tmp_path / "mail").iterdir())
    assert len(paths) == 1
    assert json.loads(paths[0].read_text())["recipient"] == args[0]
    assert paths[0].stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError):
        await adapter.deliver(args[0], "conflicting subject", args[2], delivery_id)
