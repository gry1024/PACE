# 模块说明
# 验证框架存活状态与配置别名，不调用真实模型或邮件。
#
# 这些测试确保healthz不会把框架说成业务就绪，Key映射不会意外暴露秘密。
# 测试用字符串都是合成占位符，不能复制真实凭据进版本库。

from fastapi.testclient import TestClient

from pace.config import Settings
from pace.main import create_app


# 实现说明：test_liveness_does_not_claim_business_readiness
# 验证存活200 /mvp与未配置业务就绪503可以同时成立。
#
# 使用TestClient上下文触发生命周期，确保退出释放测试应用资源。
def test_liveness_does_not_claim_business_readiness():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "pace", "stage": "mvp"}
        assert client.get("/readyz").status_code == 503


# 实现说明：test_existing_jev_key_is_supported_without_leaking
# 验证旧JEV_API_KEY兼容映射，并确认默认repr不展开秘密。
#
# 先清官方别名避免环境优先级影响此用例；不请求真实SDK网络。
def test_existing_jev_key_is_supported_without_leaking(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("JEV_API_KEY", "test-secret")
    settings = Settings(_env_file=None)
    assert settings.jev_api_key.get_secret_value() == "test-secret"
    assert "test-secret" not in repr(settings)


# 实现说明：test_official_key_takes_precedence
# 同时设置两种合成Key，验证官方TYPESAFE_API_KEY优先。
#
# 防止迁移配置后仍静默使用旧凭据。
def test_official_key_takes_precedence(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "legacy-test")
    monkeypatch.setenv("TYPESAFE_API_KEY", "official-test")
    assert Settings(_env_file=None).jev_api_key.get_secret_value() == "official-test"


# 实现说明：test_blank_official_key_does_not_hide_configured_legacy_key
# 验证空官方变量不会遮蔽可用旧Key。
#
# 对应env_ignore_empty行为，避免复制.env.example的空字段令旧配置失效。
def test_blank_official_key_does_not_hide_configured_legacy_key(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "")
    monkeypatch.setenv("JEV_API_KEY", "synthetic-legacy")
    assert Settings(_env_file=None).jev_api_key.get_secret_value() == "synthetic-legacy"
