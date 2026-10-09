# ADR 0003：Gmail 身份、跨平台同账号与通知

- 状态：Accepted
- 日期：2026-10-09
- 决策来源：用户明确要求身份认定、用户注册、跨平台同用户辨别及通知只使用 Gmail。
- 覆盖范围：替代先前 ADR 中泛化 email 身份的部分；其它业务边界继续沿用。

## 决定

只支持个人 `@gmail.com`，不支持 Workspace 自定义域、其它邮箱或由客户端直接声明的 email 身份。用 Google 官方 OIDC 验证签名、issuer、audience、时效、nonce、email_verified 与稳定 sub 后关联账号。规范 Gmail（小写、去 local 点号与 plus alias）与 Google sub 双唯一；冲突不自动合并。相同 Gmail / sub 在不同 Host 仍使用同一个 PACE Account UUID。

MCP 客户端通过 PACE 自己的 OAuth 授权码 / PKCE 流程获取资源绑定 opaque 凭据；Google token 不直接用于 PACE。账号注册明确取得联系方式及请求相关资料披露、Gmail 连接通知同意。Host 文件上传授权独立处理，不由注册同意扩大范围。

登录只申请 openid/email，通知通过独立系统 Gmail 的 gmail.send 授权。未配置时使用明确标记的本地 capture，不能宣称真实邮件成功。MCP Event 是可选 Host 通道，联系方式仍使用已验证 Gmail。

## 后果

已有非 Gmail / 没有 Google sub 的历史账号不能进入候选池；不能只根据相同邮箱强行绑定新的 Google sub。外部 Google 客户端、发件授权、Fernet 密钥和公网部署须独立配置及验收。

至少一次通知保留外部副作用重复风险；Gmail 稳定 Message-ID 不保证 exactly-once。必须继续建设撤回同意、数据保留与删除、密钥轮换和生产限流；本 ADR 不声称这些已经完成。

## 依据与实现

- [Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect)
- [Gmail 点号规则](https://support.google.com/mail/answer/7436150?hl=en)
- [Gmail messages.send](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send)
- [GoogleOAuth](../../src/pace/adapters/auth/google.py)、[GmailEmail](../../src/pace/adapters/delivery/gmail.py)
- 当前验收与限制见 [STATUS](../STATUS.md)，流程见 [ARCHITECTURE](../ARCHITECTURE.md)。
