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

- Stream Agent 凭证由主密钥按 Profile 与 runtime_instance_id 派生（HMAC-SHA256），每个 Stream 只拿到本实例凭证文件。凭证文件位于 `runtime/.secrets/<profile_id>/agent_secret.txt`（0600），只挂给 Stream；Browser 只挂 `runtime/<profile_id>`，看不到 secret 目录。Gateway 另以 API 持久绑定校验实例，过期实例不能覆盖当前注册。
- 所有内部 Bearer/主密钥文件读取统一拒绝 group/other 可读（`mode & 0o077 != 0`），Supervisor、Gateway、Control 在启动或首次读取时失败封闭，不回退环境变量。
- 每 Profile 另有独立的 Selkies master 与 controller token，由 Supervisor 每次启动随机生成（`secrets.token_urlsafe(32)`），只经 0600 文件（`runtime/.secrets/<profile_id>/`，Browser 容器不挂载该目录）挂载给该 Profile 的 Stream 容器。controller token 由 Stream 入口写入 tmpfs 0600 tokens 文件，Agent 在转发上游 `HELLO client` 时代注入，页面不持有任何 Selkies token。master token 仅用于开启 Selkies 安全模式，不进入 Agent 配置、注册/心跳、Gateway 或 API 响应，也不写入日志；直连 Selkies 信令缺 token 或错 token 被 4001 拒绝。
- TURN 采用 REST HMAC-SHA1 短期凭证：客户端与 Stream 分别签发、默认 24 小时有效、每 12 小时生成新代、旧代到期前 6 小时触发 ICE restart；新连接总取当前代。Stream 侧 URL 使用 Supervisor 下发的本 Profile 媒体网络内 coturn 实际地址，客户端使用公开可达地址。
- 日志不记录密码、会话、CSRF、Bearer、TURN credential 或 SDP 全文；Agent 报文日志按字段名脱敏。

## 宿主目录权限与威胁模型

- 受管部署中 Supervisor 以 root 创建 Profile 数据目录后立即 `chown 1000:1000`：`profiles/<id>/profile`、`runtime/<id>`、`runtime-events/<id>`、`artifacts/<id>/downloads`、`artifacts/<id>/uploads`、`runtime/<id>/pulse` 为 0750；`runtime/<id>/x11` 为 1777（X11 socket 需要跨进程连接，保留 sticky 位）。engine-cache/geoip 只读挂载且由宿主维护，不随 Profile 写入。
- Artifact Service 发布的上传/下载子目录与文件同样收敛到 UID/GID 1000：目录 0750、文件 0640；宿主开发环境无法 chown 时回退 0755/0644，保证 Browser 容器 UID 1000 可读。
- Browser/Stream 以 uid/gid 1000 运行，只能访问本 Profile 目录；其他宿主 UID 无读写权。跨 Profile 读取不依赖网络命名空间。
- 宿主直跑 Supervisor（开发/测试）默认跳过 chown 并保留 0777 兼容模式，可用 `CBROWSER_MANAGE_OWNERSHIP=1` 强制受管权限、`CBROWSER_RUNTIME_UID/GID` 指定属主。非 root 宿主进程不会修改用户文件属主。
- 威胁模型假设：能控制本 Profile 网页的进程已处于该 Profile 信任域，可读本 Profile 的 Browser 可写目录；目标是阻止跨 Profile 访问、阻止 Browser 读取 Agent/Selkies 凭证、阻止未受策略保护的沙箱长期运行。事件伪造不改变生命周期权威（见 [Supervisor](supervisor.md) 与 d016）。

## 验证边界

单元与真实 HTTP/WS 集成测试覆盖凭证校验、会话与 CSRF、限速、审计脱敏和 Gateway 控制面；真实 HTTPS、Chrome Cookie 属性与端到端信令由 Gateway E2E 验证。公网 TLS 证书与公网穿透属 USER_WAIVED 范围外，本机以 Caddy 内部 CA 验证。
