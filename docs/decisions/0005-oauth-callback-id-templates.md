# ADR 0005：OAuth 回跳白名单支持受限连接 ID 模板

状态：Accepted，2026-10-10。

## 背景

ChatGPT 在服务器未声明授权响应 issuer 标识时，使用 `https://chatgpt.com/connector/oauth/{callback_id}` 作为连接回跳。连接 ID 在创建连接时生成；仅支持提前配置精确 URI 的白名单会阻断动态客户端注册，公网实测返回 invalid_redirect_uri。

## 决定

保留精确 URI 白名单，另允许运营者显式配置以 `/{callback_id}` 结尾的模板。模板只匹配一个 1–128 字符的 ASCII 字母 / 数字 / 下划线 / 连字符段；完整前缀必须相同，不允许域名通配、任意路径、编码路径、额外段、query、fragment 或 userinfo 绕过。

服务器配置可信的 ChatGPT 官方模板与官方固定回跳地址；不默认信任任意 HTTPS URI。其他 Host 仍需显式配置可信精确 URI 或同样受限模板。

DCR 保存的是客户端实际提交的精确 URI；后续授权由官方 SDK 校验该客户端的精确 redirect，模板不会允许已注册客户端更换回跳。Google 登录回调与系统发件 OAuth 回调保持原约定。

## 验证

真实 PostgreSQL 集成测试覆盖动态 URI 注册 / 精确持久化及恶意域名、附加路径、query、编码、fragment、userinfo、HTTP 和生产 loopback 拒绝。公网 DCR 验收仍需与实际插件创建结果区分。

依据：[OpenAI OAuth 回跳与 DCR 文档](https://developers.openai.com/plugins/build/auth)。
