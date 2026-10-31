# 安全与凭证边界

本文定义 v2 用户鉴权、服务间凭证与秘密管理边界（t006 实施）。网络隔离与 Runtime 沙箱见 [Supervisor](supervisor.md)，Gateway 注册与信令见 [Gateway](gateway.md)。

## 秘密来源

- 所有秘密只来自部署者提供的外部文件，代码、镜像、日志、数据库与测试快照不得包含明文默认值。缺失或长度不足即启动失败，不回退默认口令。
- 服务间 Bearer/HMAC 密钥至少 32 UTF-8 字节：`CBROWSER_SUPERVISOR_TOKEN_FILE`（Supervisor→API）、`CBROWSER_GATEWAY_TOKEN_FILE`（Supervisor→Gateway）、`CBROWSER_GATEWAY_API_TOKEN_FILE`（Gateway→API）、`CBROWSER_AGENT_KEY_FILE`（Stream Agent 实例凭证主密钥，只在 Supervisor/Gateway）、`CBROWSER_TURN_SECRET_FILE`（coturn REST HMAC）。各凭证用途单一，不可互换。
- 管理员密码由 `CBROWSER_ADMIN_PASSWORD_FILE` 提供（至少 12 字节）。库内尚无管理员时以 Argon2id（argon2-cffi 默认参数）哈希入库，已有管理员时忽略该文件且不覆盖。明文不进入日志、异常、响应。测试一律使用每次随机生成的密码。

## 浏览器用户会话

- `POST /api/v1/auth/login` 成功后下发 `cbrowser_session`（`HttpOnly; Secure; SameSite=Strict; Path=/`）与非 HttpOnly 的 `cbrowser_csrf`，响应体返回 `csrf_token`。会话令牌为 32 字节随机值，库内只存 SHA-256，默认 12 小时过期；登出立即失效。失败登录按来源 5 次/分钟限速（429）。
- 除 health、login 与内部服务路由外，`/api/v1` 全部需要有效会话。写方法另需 `X-CSRF-Token` 与会话绑定值一致，且 `Origin`（缺失时取 `Referer` 的 origin）属于 `CBROWSER_ALLOWED_ORIGINS`。该允许列表必须显式配置，为空时 API 启动失败。
- Viewer 信令 WebSocket 在升级前由 Gateway 校验 Origin、经 API `viewer-authorize` 校验会话与 Profile；拒绝时不升级连接。master token 与 Selkies token 永不返回前端。

## 自动化凭证

- CDP 自动化使用独立 Bearer 凭证（`cbat_` 前缀，创建时只显示一次），库内只存 SHA-256，绑定可访问的 Profile 列表，可撤销。合法非浏览器客户端可不带 Origin，但必须通过该凭证与 Profile 授权；登录 Cookie 不能当自动化凭证。
- 创建、撤销与授权拒绝写入审计表，审计详情不含令牌明文或哈希。

## 服务间与媒体凭证

- Stream Agent 凭证由主密钥按 Profile 与 runtime_instance_id 派生（HMAC-SHA256），每个 Stream 只拿到本实例凭证文件。Gateway 另以 API 持久绑定校验实例，过期实例不能覆盖当前注册。
- TURN 采用 REST HMAC-SHA1 短期凭证：客户端与 Stream 分别签发、默认 24 小时有效、每 12 小时生成新代、旧代到期前 6 小时触发 ICE restart；新连接总取当前代。Stream 侧 URL 使用 Supervisor 下发的本 Profile 媒体网络内 coturn 实际地址，客户端使用公开可达地址。
- 日志不记录密码、会话、CSRF、Bearer、TURN credential 或 SDP 全文；Agent 报文日志按字段名脱敏。

## 验证边界

单元与真实 HTTP/WS 集成测试覆盖凭证校验、会话与 CSRF、限速、审计脱敏和 Gateway 控制面；真实 HTTPS、Chrome Cookie 属性与端到端信令由 Gateway E2E 验证。公网 TLS 证书与公网穿透属 USER_WAIVED 范围外，本机以 Caddy 内部 CA 验证。
