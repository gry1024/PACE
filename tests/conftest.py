# 模块说明
# 所有测试共用的环境隔离fixture。
#
# 清除真实Provider环境变量，避免离线测试因为开发者设置了Key而意外调用服务。
# 单元测试显式Settings(_env_file=None)，不读取真实.env；DB集成fixture则明确启用实际数据库。
# 集成测试保留DATABASE_URL覆盖，便于本地 /CI指定测试数据库。

"""Unit tests never load real credentials or call real providers."""

import pytest


# 实现说明：isolate_environment
# 在每个测试执行前隔离可能泄密或改变结果的环境。
#
# 非integration路径清除DATABASE_URL；所有测试清除模型Key /URL /model变量。
# monkeypatch在测试结束恢复环境，不修改用户真实.env文件。
@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch, request):
    if "integration" not in request.node.path.parts:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    for name in (
        "TYPESAFE_API_KEY",
        "JEV_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL_NAME",
    ):
        monkeypatch.delenv(name, raising=False)
