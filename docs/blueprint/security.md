# 安全与凭证边界

本文定义 v2 用户鉴权、服务间凭证与秘密管理边界（t006 实施）。网络隔离与 Runtime 沙箱见 [Supervisor](supervisor.md)，Gateway 注册与信令见 [Gateway](gateway.md)。

## 秘密来源

- 所有秘密只来自部署者提供的外部文件，代码、镜像、日志、数据库与测试快照不得包含明文默认值。缺失或长度不足即启动失败，不回退默认口令。
- 服务间 Bearer/HMAC 密钥至少 32 UTF-8 字节：`CBROWSER_SUPERVISOR_TOKEN_FILE`（Supervisor→API）、`CBROWSER_GATEWAY_TOKEN_FILE`（Supervisor→Gateway）、`CBROWSER_GATEWAY_API_TOKEN_FILE`（Gateway→API）、`CBROWSER_AGENT_KEY_FILE`（Stream Agent 实例凭证主密钥，只在 Supervisor/Gateway）。各凭证用途单一，不可互换。
- 管理员密码由 `CBROWSER_ADMIN_PASSWORD_FILE` 提供（至少 12 字节）。库内尚无管理员时以 Argon2id（argon2-cffi 默认参数）哈希入库，已有管理员时忽略该文件且不覆盖。明文不进入日志、异常、响应。测试一律使用每次随机生成的密码。

## 浏览器用户会话

- `POST /api/v1/auth/login` 成功后下发 `cbrowser_session`（`HttpOnly; Secure; SameSite=Strict; Path=/`）与非 HttpOnly 的 `cbrowser_csrf`，响应体返回 `csrf_token`。会话令牌为 32 字节随机值，库内只存 SHA-256，默认 12 小时过期；登出立即失效。失败登录按来源 5 次/分钟限速（429）。
- 除 health、login 与内部服务路由外，`/api/v1` 全部需要有效会话。写方法另需 `X-CSRF-Token` 与会话绑定值一致，且 `Origin`（缺失时取 `Referer` 的 origin）属于当前已应用网络版本派生的白名单（仅限 `https://`，t042）。API 与 Gateway 读取同一不可变版本源，废弃 `CBROWSER_ALLOWED_ORIGINS` 环境变量；未列出的 Origin 严格返回 403。
- Caddy CA 私钥隔离（t042；下载端按 p053 暂搁，生产部署返回 404）：`GET /api/v1/network/root-ca` 仅公开公钥根证书（`root.crt`）；API 服务容器挂载绝不包含 `caddy_data` 卷，严禁挂载或暴露 CA 私钥 `root.key`。
- Viewer 信令 WebSocket 在升级前由 Gateway 校验 Origin、经 API `viewer-authorize` 校验会话与 Profile；拒绝时不升级连接。master token 与 Selkies token 永不返回前端。
- Origin 比较全链使用同一规范化（`cbrowser.gateway.endpoint.normalize_origin`，t021）：Gateway 入口归一化后，API 侧 `authorize_viewer` 对入参与允许列表同样归一化再比对，尾斜杠/默认端口/大小写变体不产生假拒绝，畸形 Origin 归为 `invalid_origin`；CSRF 来源校验对畸形 `Referer`（如非法 IPv6 字面量）返回 403 而非 500。
- 内部服务未配置时返回 503 `service_not_configured`（`retryable=false`），与数据库忙的 `database_busy`（`retryable=true`）严格区分（t021）：Supervisor/Gateway/Artifact 三个内部面经同一 `ServiceNotConfiguredError` 通道。OpenAPI 按路径标注真实服务身份：`/internal/supervisor*`（含 Artifact 面）为 `SupervisorServiceBearer`、`/internal/gateway*` 为 `GatewayServiceBearer`，两把令牌互不通用。
- 密码校验（含哑元校验与 bootstrap 哈希）在线程池执行（t021），慢哈希不阻塞事件循环，限速顺序与失败行为不变。

## 自动化凭证

- CDP 自动化使用独立 Bearer 凭证（`cbat_` 前缀，创建时只显示一次），库内只存 SHA-256，绑定可访问的 Profile 列表，可撤销。合法非浏览器客户端可不带 Origin，但必须通过该凭证与 Profile 授权；登录 Cookie 不能当自动化凭证。
- 创建、撤销与授权拒绝写入审计表，审计详情不含令牌明文或哈希。
- 授权审计覆盖全部拒绝类别并带 reason 与来源（t021）：已知令牌的拒绝（吊销/过期/Profile 未授权/Profile 不存在）逐条记录；未知/非法令牌（在线猜测路径）按 `(reason, source)` 聚合为有界计数行，不存令牌或其哈希，重复猜测只增计数不增行。限速失败记录只按时间窗衰减，成功授权不清除任何失败记录。

## Agent 执行器凭证与清理权限（t030）

- 执行器凭证与自动化凭证同源（`cbat_` Bearer，见上节）：CLI 只经
    `--token-file`（0600）或 `CBROWSER_AGENT_TOKEN` 传入；故意不设
    `--token` 旗标；输出、日志与账本做 token redact；状态文件（ref 与账本
    元数据）不含凭证、Cookie 或认证头，0600 原子写入。0600 是调用方
    保管约定：权限更宽的 token 文件只触发 stderr 告警、不拒绝运行
    （拒绝并不能收回已暴露的文件，只会拒绝服务）；状态文件带
    （profile，runtime）绑定，绑定不符即整体丢弃。
- `extract`/`evaluate` 的调用方脚本返回值是调用方数据：执行器只透传，
    不承诺只读、不做脱敏、不写入账本；文档中明确该边界。
- 清理权限永不由管理权推导：adopt 只授管理权；仅本会话可证明创建的
    页面（createTarget 记录、popup 三方归属证据）可清理；用户/unknown 页
    在正常、异常、取消与显式清理下全部保留；最后一页 backstop 同时存在
    于账本与隧道两层。
- 隧道拒绝类命令返回稳定错误而不转发；脚本登记与断开清理保证不断开
    不残留；浏览器级破坏性命令的拒绝不依赖调用方自律。

## 真人优先控制权（t031，ADR 019）

- 控制权状态由 API 唯一写入（`profile_controls`）；接管时 API 与
    Supervisor 各自关闭已登记的活动隧道并以单调代次围栏拒旧代次重连
    （转发握手带 `X-CBrowser-Control-Generation`，不高于围栏者 4403 拒绝）。
- Agent UDS 层为本地信任边界（0660 socket + Supervisor 管理的 runtime
    目录）：UDS 直连客户端不在强制范围内（与直接访问 runtime 目录等价）；
    控制强制经 CLI 会话生命周期 + 接管级联（Supervisor 关闭隧道端点 →
    Agent /control `release_attendant`）覆盖。
- Supervisor 直连令牌持有者属于基础设施信任边界：其握手不查 API 状态，
    但转发代次受围栏约束；Supervisor 分区期间的残留窗口如实记录（分区内
    已存在的直连隧道在分区愈合前不受 API 侧关闭约束）。
- 不承诺任意只读 CDP 黑名单保证（evaluate 可跑任意致变脚本）；不承诺
    自动识别全部 CAPTCHA 或代解验证码；不回滚已执行的浏览器动作。
- Stream 输入分类保守取向（宁可误接管、不漏接管）；XTEST 注入结构上
    不走 WebRTC 数据通道，不构成人类输入。
- 常驻 attendant 的应答只经控制面显式请求（CLI 未 attach 时的 peek +
    attendant 会话应答）；attendant 自身永不自动应答。控制面 peek/应答
    要求调用方持有控制权且 token 身份与记录的 Agent 实例一致（R1
    code f001）：user 态或第二 token 一律 409；接管级联的 attendant
    释放纳入 pending 确认（释放失败则 reconcile 重试整条级联）。
- 吊销 automation token 时，该 token 持有控制的 Profile 各执行一次
    `identity_invalid` 交接（R1 code f002）；token 过期在握手时校验，
    已建立隧道在过期后不自动关闭属已知残留（无独立过期清理点）。

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

## 平台字体来源与分发边界（t041）

- 平台专有字体只从官方渠道取得：macOS 取本机 `/System/Library/Fonts`、`/System/Library/Fonts/Supplemental`、`/Library/Fonts` 及 `/System/Library/AssetsV2/` 下的苹方资源；Windows 取微软官方 Windows 11 企业评估版 ISO，经 `7zz` 从 `sources/install.wim` 提取 `Windows/Fonts`。不使用第三方字体站或 GitHub 镜像（授权与文件来源无法校验）。
- 字体只写入宿主 `CBROWSER_FONTS_DIR` 与 `.scratch/`，不进入任何镜像层，不进入 git 仓库；部署与发布脚本不复制字体目录（AC-008）。导入工具把字体固化为按内容寻址的不可变字体集，`manifest.json` 记录来源、来源系统版本与逐文件 sha256，供静态完整性校验（AC-001 / AC-002）。
- 字体集只在运行时由 Supervisor 只读挂载给绑定它的 Profile，其他 Profile 与 Stream 容器不可见；系统不提供字体集删除功能，也不分发或打包字体文件。基础开源字体为镜像内的 Debian 官方包，不含平台专有字体，且绑定平台字体集时不进入指纹 Profile 的 fontconfig 白名单（`font_set_id` 为 null 时作为回退可见并由 runtime 状态标记，ADR 024）。

## 预览隐私与撤销语义（t040）

环境实时缩略图视同 Cookie 级私密数据：`frame_<timestamp_key>_<image_sha256>.jpg` 内容与预览目录路径不进日志、错误响应与 SSE 事件，日志只记 error_type 与计数（AC-006）。文件 0600 原子写，独立挂载进 Browser 容器 `/data/preview`，不进入 user data dir；跨 Profile 读取由 `PathValidator` 归属校验与专属挂载阻断。

`GET /api/v1/profiles/{id}/preview` 需登录会话，返回 `image/jpeg` + `Cache-Control: no-store` + `X-Content-Type-Options: nosniff` + ETag（`captured_at` 经 `json.dumps` 的引用字符串），`If-None-Match` 命中即 304；读侧以 DB `policy_row[0]` 为权威（DB 关闭即 404，不只信文件 `policy.enabled`），无预览、策略已撤销或代次 / 实例不符统一返回 404，错误体不含路径与截图内容。`no-store` 保证私密帧不经浏览器或代理缓存留存。

撤销与清除语义：关闭 `capture_preview` 即时停止采集、删除已有预览、接口随即 404，不需重启或应用配置；采集、落盘、通知、读取四环节以策略代次 + `runtime_instance_id` 围栏，关闭时截图正在进行、旧代次通知迟到、reset 后旧实例回传等迟到写入一律丢弃并清理残留，预览不会重新出现；reset / delete 清除预览目录与 `preview_captured_at`，Profile 停止保留最后一帧，「含浏览器状态」复制不复制预览。

## 验证边界

单元与真实 HTTP/WS 集成测试覆盖凭证校验、会话与 CSRF、限速、审计脱敏和 Gateway 控制面；真实 HTTPS、Chrome Cookie 属性与端到端信令由 Gateway E2E 验证。公网 TLS 证书与公网穿透属 USER_WAIVED 范围外，本机以 Caddy 内部 CA 验证。

## 仓库隐私口径（t060）

- 当前 tracked 树与新提交不得包含开发者家路径或凭据；归档文档也纳入扫描。未跟踪且未忽略的新文本同样在 `test_repo_hygiene.py` 扫描范围内。
- 泄漏统一改写为 `<repo>`、`<home>`、`<container_home>` 等语义占位符；不使用整文件指纹或文件清单豁免。测试负例通过字符串片段组装，避免在测试源中再次泄漏。
- 不改写 Git 历史，保留既有提交引用与审查溯源。历史文件原位脱敏属于归档只追加约定的必要隐私例外。
- 容器固定账号及产品定义的容器路径属于接口常量，按语义判别，不视为开发者家路径；任意开发者路径不能借此获得文件级豁免。
