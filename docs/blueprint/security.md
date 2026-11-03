# 安全与凭证边界

本文定义 v2 用户鉴权、服务间凭证与秘密管理边界（t006 实施）。网络隔离与 Runtime 沙箱见 [Supervisor](supervisor.md)，Gateway 注册与信令见 [Gateway](gateway.md)。

## 秘密来源

- 所有秘密只来自部署者提供的外部文件，代码、镜像、日志、数据库与测试快照不得包含明文默认值。缺失或长度不足即启动失败，不回退默认口令。
- 服务间 Bearer/HMAC 密钥至少 32 UTF-8 字节：`CBROWSER_SUPERVISOR_TOKEN_FILE`（Supervisor→API）、`CBROWSER_GATEWAY_TOKEN_FILE`（Supervisor→Gateway）、`CBROWSER_GATEWAY_API_TOKEN_FILE`（Gateway→API）、`CBROWSER_AGENT_KEY_FILE`（Stream Agent 实例凭证主密钥，只在 Supervisor/Gateway）。各凭证用途单一，不可互换。
- 管理员密码由 `CBROWSER_ADMIN_PASSWORD_FILE` 提供（至少 12 字节）。库内尚无管理员时以 Argon2id（argon2-cffi 默认参数）哈希入库，已有管理员时忽略该文件且不覆盖。明文不进入日志、异常、响应。测试一律使用每次随机生成的密码。

## 浏览器用户会话

- `POST /api/v1/auth/login` 成功后下发 `cbrowser_session`（`HttpOnly; Secure; SameSite=Strict; Path=/`）与非 HttpOnly 的 `cbrowser_csrf`，响应体返回 `csrf_token`。会话令牌为 32 字节随机值，库内只存 SHA-256，默认 12 小时过期；登出立即失效。失败登录按来源 5 次/分钟限速（429）。
- 除 health、login 与内部服务路由外，`/api/v1` 全部需要有效会话。写方法另需 `X-CSRF-Token` 与会话绑定值一致，且 `Origin`（缺失时取 `Referer` 的 origin）属于 `CBROWSER_ALLOWED_ORIGINS`。该允许列表必须显式配置，为空时 API 启动失败。
- Viewer 信令 WebSocket 在升级前由 Gateway 校验 Origin、经 API `viewer-authorize` 校验会话与 Profile；拒绝时不升级连接。master token 与 Selkies token 永不返回前端。
- Origin 比较全链使用同一规范化（`cbrowser.gateway.endpoint.normalize_origin`，t021）：Gateway 入口归一化后，API 侧 `authorize_viewer` 对入参与允许列表同样归一化再比对，尾斜杠/默认端口/大小写变体不产生假拒绝，畸形 Origin 归为 `invalid_origin`；CSRF 来源校验对畸形 `Referer`（如非法 IPv6 字面量）返回 403 而非 500。
- 内部服务未配置时返回 503 `service_not_configured`（`retryable=false`），与数据库忙的 `database_busy`（`retryable=true`）严格区分（t021）：Supervisor/Gateway/Artifact 三个内部面经同一 `ServiceNotConfiguredError` 通道。OpenAPI 按路径标注真实服务身份：`/internal/supervisor*`（含 Artifact 面）为 `SupervisorServiceBearer`、`/internal/gateway*` 为 `GatewayServiceBearer`，两把令牌互不通用。
- 密码校验（含哑元校验与 bootstrap 哈希）在线程池执行（t021），慢哈希不阻塞事件循环，限速顺序与失败行为不变。

## 自动化凭证

- CDP 自动化使用独立 Bearer 凭证（`cbat_` 前缀，创建时只显示一次），库内只存 SHA-256，绑定可访问的 Profile 列表，可撤销。合法非浏览器客户端可不带 Origin，但必须通过该凭证与 Profile 授权；登录 Cookie 不能当自动化凭证。
- 创建、撤销与授权拒绝写入审计表，审计详情不含令牌明文或哈希。
- 授权审计覆盖全部拒绝类别并带 reason 与来源（t021）：已知令牌的拒绝（吊销/过期/Profile 未授权/Profile 不存在）逐条记录；未知/非法令牌（在线猜测路径）按 `(reason, source)` 聚合为有界计数行，不存令牌或其哈希，重复猜测只增计数不增行。限速失败记录只按时间窗衰减，成功授权不清除任何失败记录。

## 服务间与媒体凭证

- Stream Agent 凭证由主密钥按 Profile 与 runtime_instance_id 派生（HMAC-SHA256），每个 Stream 只拿到本实例凭证文件。凭证文件位于 `runtime/.secrets/<profile_id>/agent_secret.txt`（0600），只挂给 Stream；Browser 只挂 `runtime/<profile_id>`，看不到 secret 目录。Gateway 另以 API 持久绑定校验实例，过期实例不能覆盖当前注册。
- 所有内部 Bearer/主密钥文件读取统一拒绝 group/other 可读（`mode & 0o077 != 0`），Supervisor、Gateway、Control 在启动或首次读取时失败封闭，不回退环境变量。
- 每 Profile 另有独立的 Selkies master 与 controller token，由 Supervisor 每次启动随机生成（`secrets.token_urlsafe(32)`），只经 0600 文件（`runtime/.secrets/<profile_id>/`，Browser 容器不挂载该目录）挂载给该 Profile 的 Stream 容器。controller token 由 Stream 入口写入 tmpfs 0600 tokens 文件，Agent 在转发上游 `HELLO client` 时代注入，页面不持有任何 Selkies token。master token 仅用于开启 Selkies 安全模式，不进入 Agent 配置、注册/心跳、Gateway 或 API 响应，也不写入日志；直连 Selkies 信令缺 token 或错 token 被 4001 拒绝。
- 媒体只走同机 `127.0.0.1` host 候选直连，不存在 TURN 凭证、轮换或中继（ADR 013）。
- 日志不记录密码、会话、CSRF、Bearer 或 SDP 全文；Agent 报文日志按字段名脱敏。

## 宿主目录权限与威胁模型

- 受管部署中 Supervisor 以 root 创建 Profile 数据目录后立即 `chown 1000:1000`：`profiles/<id>/profile`、`runtime/<id>`、`runtime-events/<id>`、`artifacts/<id>/downloads`、`artifacts/<id>/uploads`、`runtime/<id>/pulse` 为 0750；`runtime/<id>/x11` 为 0750（Browser/Stream 同为 uid 1000）。engine-cache/geoip 只读挂载且由宿主维护，不随 Profile 写入。
- Artifact Service 发布的上传/下载子目录与文件同样收敛到 UID/GID 1000：目录 0750、文件 0640；非 root 宿主开发路径保留开发者属主但仍使用精确 mode，不回退到全局可写，chown 失败即报错。
- Browser/Stream 以 uid/gid 1000 运行，只能访问本 Profile 目录；其他宿主 UID 无读写权。跨 Profile 读取不依赖网络命名空间。
- 宿主直跑 Supervisor（开发/测试）在非 root 时不做跨 uid chown，仅使用精确 mode；可用 `CBROWSER_MANAGE_OWNERSHIP=1` 强制受管权限、`CBROWSER_RUNTIME_UID/GID` 指定属主。不存在 0777/0666 回退。
- 威胁模型假设：能控制本 Profile 网页的进程已处于该 Profile 信任域，可读本 Profile 的 Browser 可写目录；目标是阻止跨 Profile 访问、阻止 Browser 读取 Agent/Selkies 凭证、阻止未受策略保护的沙箱长期运行。事件伪造不改变生命周期权威（见 [Supervisor](supervisor.md) 与 d016）。

## 验证边界

单元与真实 HTTP/WS 集成测试覆盖凭证校验、会话与 CSRF、限速、审计脱敏和 Gateway 控制面；真实 HTTPS、Chrome Cookie 属性与端到端信令由 Gateway E2E 验证。公网 TLS 证书与公网穿透属 USER_WAIVED 范围外，本机以 Caddy 内部 CA 验证。
