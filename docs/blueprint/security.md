# 安全与凭证边界

本文定义用户鉴权、服务间凭证与秘密管理边界（t006 实施）。网络隔离与 Runtime 沙箱见 [Supervisor](supervisor.md)，Gateway 注册与信令见 [Gateway](gateway.md)。

## 秘密来源

- 所有秘密只来自部署者提供的外部文件，代码、镜像、日志、数据库与测试快照不得包含明文默认值。缺失或长度不足即启动失败，不回退默认口令。
- 服务间 Bearer/HMAC 密钥至少 32 UTF-8 字节：`CBROWSER_SUPERVISOR_TOKEN_FILE`（Supervisor→API）、`CBROWSER_GATEWAY_TOKEN_FILE`（Supervisor→Gateway）、`CBROWSER_GATEWAY_API_TOKEN_FILE`（Gateway→API）、`CBROWSER_AGENT_KEY_FILE`（Stream Agent 实例凭证主密钥，只在 Supervisor/Gateway）。各凭证用途单一，不可互换。
- viewer 边缘授权另有两把不共用的秘密（t064）：`edge_proof_key` 只供 Caddy 经进程环境呈现给 API 校验，API 以秘密文件读取，Gateway 与 Supervisor 均不持有；`viewer_grant_key` 只由 API（签发）与 Gateway（验签）以秘密文件共享。Caddyfile、release env 与日志只允许出现边缘证明的环境变量占位符，不出现秘密值。
- 管理员密码由 `CBROWSER_ADMIN_PASSWORD_FILE` 提供（至少 12 字节）。库内尚无管理员时以 Argon2id（argon2-cffi 默认参数）哈希入库，已有管理员时忽略该文件且不覆盖。明文不进入日志、异常、响应。测试一律使用每次随机生成的密码。

## 浏览器用户会话

- `POST /api/v1/auth/login` 成功后下发 `cbrowser_session`（`HttpOnly; Secure; SameSite=Strict; Path=/`）与非 HttpOnly 的 `cbrowser_csrf`，响应体返回 `csrf_token`。会话令牌为 32 字节随机值，库内只存 SHA-256，默认 12 小时过期；登出立即失效。失败登录按来源 5 次/分钟限速（429）。
- 除 health、login 与内部服务路由外，`/api/v1` 全部需要有效会话。写方法另需 `X-CSRF-Token` 与会话绑定值一致，且 `Origin`（缺失时取 `Referer` 的 origin）属于由部署端口确定性派生的白名单（仅限 `https://`，t054）。API 与 Gateway 在启动时从同一 `CBROWSER_HTTPS_PORT` 派生，废弃 `CBROWSER_ALLOWED_ORIGINS` 环境变量；未列出的 Origin 严格返回 403。
- Caddy CA 私钥隔离：API 服务容器挂载绝不包含 `caddy_data` 卷，严禁挂载或暴露 CA 私钥 `root.key`；根证书下载端点 `GET /api/v1/network/root-ca` 已随 t054 删除（局域网访问彻底不做，无需向浏览器分发根证书）。
- Viewer 信令 WebSocket 只对 `/stream/{profileId}/signal` 在 Caddy 边缘授权：Caddy 删除客户端伪造的 authorized Profile 与 grant 头，以边缘证明调用 API 内部解析端点；API 经 `AuthService.authorize_viewer` 校验会话、Origin 与 Profile 后签发 60 秒、单 Profile、无会话标识的 HMAC grant。Caddy 删除待代理请求的 Cookie 后，Gateway 在升级前再验 Origin、grant 签名/到期/Profile 绑定与两个 API 回注头的一致性；拒绝时不升级连接。Gateway 不接收、记录或解析 `cbrowser_session`，直连 Gateway 时没有有效 grant 即拒绝。master token 与 Selkies token 永不返回前端。
- Origin 比较全链使用同一规范化（`cbrowser.shared.endpoints.normalize_origin`，t021/t062）：API 边缘解析与 Gateway 升级前校验都对入参与允许列表同样归一化再比对，尾斜杠/默认端口/大小写变体不产生假拒绝，畸形 Origin 归为 `invalid_origin`；CSRF 来源校验对畸形 `Referer`（如非法 IPv6 字面量）返回 403 而非 500。
- 内部服务未配置时返回 503 `service_not_configured`（`retryable=false`），与数据库忙的 `database_busy`（`retryable=true`）严格区分（t021）：Supervisor/Gateway/Artifact 三个内部面经同一 `ServiceNotConfiguredError` 通道。OpenAPI 按路径标注真实服务身份：`/internal/supervisor*`（含 Artifact 面）为 `SupervisorServiceBearer`、`/internal/gateway*` 为 `GatewayServiceBearer`，两把令牌互不通用；`/internal/edge/viewer-authorize` 是明确例外，只接受 Caddy 的边缘证明与浏览器会话，且外部 listener 对全部 `/api/v1/internal/*` 返回 404。
- 密码校验（含哑元校验与 bootstrap 哈希）在线程池执行（t021），慢哈希不阻塞事件循环，限速顺序与失败行为不变。

## 自动化凭证

- CDP 自动化使用独立 Bearer 凭证（`cbat_` 前缀，创建时只显示一次），库内只存 SHA-256，绑定可访问的 Profile 列表，可撤销。合法非浏览器客户端可不带 Origin，但必须通过该凭证与 Profile 授权；登录 Cookie 不能当自动化凭证。
- Browser 的 CDP 本体只监听容器回环的临时端口，端口不发布、不进入普通 Profile detail/list 响应；`cdp_ws_path` 只出现在经管理会话访问的专用 Automation 状态响应中，它本身不是凭据，真正的连接仍须 automation token 与控制权围栏。真实引擎须拒绝域名 Host 的回环发现请求（DNS rebinding 的可观察形态）与跨 Origin CDP WebSocket，同时保留合法回环与认证自动化通道。
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

## 代理链接录入与探测凭据外送防护（t052）

- 代理链接是代理端点唯一的录入表示：完整链接（含密码）只在用户输入与提交请求体内出现一次；响应一律返回脱敏链接（`ProxyEndpoint.redacted_link()`，不含密码），`ProxyResponse` 不含 password 字段。前端链接输入框失焦时显示脱敏链接，聚焦编辑时才显示完整链接；已存密码永不写入表单 state、DOM、react-query 缓存、URL 与日志。

- 密码只以只写秘密存在于值对象中：`ProxyEndpoint` 的 `__repr__` / `__str__`、指纹（sha256 的 scheme/host/port/username，不含密码）、日志与观测记录均不含密码。凭据只经三条内部路径流转：API → Supervisor 的内部端点 `GET /api/v1/internal/supervisor/proxies/{id}/credentials`（service-plane Bearer，不进 OpenAPI）；Supervisor → 转发器的 0600 凭证文件（只读挂载，secret 目录，容器内路径 `/run/cbrowser/proxy_credentials.json`，除转发器外无容器挂载）；Supervisor → Browser 的无凭据端点文件 `proxy_forwarder.json`（scheme http、转发器容器名、端口 18080、冻结修订号，无秘密）。Browser 的 `--proxy-server` 不再含 userinfo；出口探测 helper 仍是唯一例外——它是一次性短生命周期容器，直接收凭据执行探测（见 t052 节）。

- 探测接口 `POST /api/v1/proxies/{id}/probe` 只接受代理 ID：任何非空请求体（除 `{}` 外）返回 422；服务端加载已存端点与凭据执行，调用方无法指定 host、port、scheme 或 username，因而无法把已存密码发往另一主机（SSRF + 凭据外送的负向路径由集成测试覆盖）。探测 helper 只向 stdout 打印一行 JSON（出口 IP 与国家，或错误码），密码不打印、不记日志。

- 出口 IP 回显只发一次 HTTPS GET 取自身出口 IP（复用 cloakbrowser SDK 的 `api.ipify.org` / `checkip.amazonaws.com` / `ifconfig.me/ip`），不带凭据与身份信息；国家判定只用本机 GeoLite2 数据库，出口 IP 不发往第三方地理库。探测的 HTTP 客户端显式 `trust_env=False`，宿主环境变量中的代理不得劫持探测路径。

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

单元与真实 HTTP/WS 集成测试覆盖凭证校验、会话与 CSRF、限速、审计脱敏和 Gateway 控制面；t064 另以 Caddyfile 渲染契约、API 边缘解析集成、Gateway grant 集成分别守住 Cookie 剥离、伪造头、跨 Profile、登出撤销与外部解析端点 404。真实 HTTPS、Chrome Cookie 属性、真实 Caddy 边缘链、首帧/重连与真实引擎 CDP Host/Origin 负向例由 Docker E2E 验证，不能以 mock 或渲染契约替代。公网 TLS 证书与公网穿透属 USER_WAIVED 范围外，本机以 Caddy 内部 CA 验证。

## 恢复点与凭据前提（t066）

- 环境恢复点（`scripts/restore_point.py`）只含控制面 DB 与 Profile 用户数据目录；**凭据永不进恢复点**：manifest 的 `credential_prerequisites` 只记 secrets 目录内文件名与大小，恢复站点必须另行提供同名凭据文件，缺失时环境恢复后相关服务按缺失凭据失败封闭，不由恢复点兜底。
- 恢复点完整性即信任边界：manifest 逐文件 SHA-256 + DB `integrity_check` + schema stamp 三重校验在任何活数据被触碰前完成；校验失败、stamp 跨代、空间不足一律拒绝，活数据不被未校验内容覆盖。
- 备份的写者门禁与 delete 共用实际写者判定 `_runtime_has_writer`（两档判定见 domain.md t066 节）：DB 记录有实际写者时拒绝取恢复点；取点在目录复制完成后按同一判定与配置版本再复查一次，备份窗口内出现写者或配置漂移即弃点，保证 DB 与目录来自同一静默时刻。

## 仓库隐私口径（t060）

- 当前 tracked 树与新提交不得包含开发者家路径或凭据；归档文档也纳入扫描。未跟踪且未忽略的新文本同样在 `test_repo_hygiene.py` 扫描范围内。
- 泄漏统一改写为 `<repo>`、`<home>`、`<container_home>` 等语义占位符；不使用整文件指纹或文件清单豁免。测试负例通过字符串片段组装，避免在测试源中再次泄漏。
- 不改写 Git 历史，保留既有提交引用与审查溯源。历史文件原位脱敏属于归档只追加约定的必要隐私例外。
- 容器固定账号及产品定义的容器路径属于接口常量，按语义判别，不视为开发者家路径；任意开发者路径不能借此获得文件级豁免。

## 引擎制品信任边界（t068）

- `cloakbrowser==0.6.4`（ADR 021）只对下载压缩包的 `SHA256SUMS` + 分离
    `SHA256SUMS.sig` 做 Ed25519 验签（包内硬编码公钥），解压后目录无上游签名；
    因此 CBrowser 不宣称对解压引擎文件有 Ed25519 覆盖，信任根如实拆为
    「下载层 Ed25519 签名 + 仓库 per-file SHA-256 清单」。
- `ensure_binary()` 命中已有可执行 `chrome` 即跳过完整性校验；故
    `cbrowser.engine_artifacts.verify_extracted_engine_cache` 在
    `deploy.sh` / Supervisor `cache_init` / `BrowserRunner` 三处独立复验
    15 个文件 SHA-256、ELF machine 与 `--version`，不信任缓存命中或
    `.cbrowser-cache-generation.json` 指纹（该 sidecar 只做路径/树变更探测）。
- 强制 `CLOAKBROWSER_AUTO_UPDATE=false`；拒绝 `CLOAKBROWSER_DOWNLOAD_URL`
    （关闭验签）、`CLOAKBROWSER_SKIP_CHECKSUM=true`（跳过校验）、
    `CLOAKBROWSER_LICENSE_KEY`（free tier 丢弃版本 pin）、`latest_version*`
    自动更新 marker 与未批准 `engine_build`，任一命中即 fail-closed。
- 报告不得含运行元数据（临时路径、时间戳）作为指纹样本；证据只记录可复现
    观测值，避免两次独立测量产生虚假漂移。

## 部署归属与输入严格拒绝（t069）

- 部署资源（容器、网络、孤儿 helper）的认领与删除只依据一个证据：`com.cbrowser.instance-id` 标签与 Supervisor 配置的部署实例 ID 相等。标签缺失、配置缺失或 ID 不匹配一律不认领、不删除；不存在按名称/前缀/compose project 的回退认领，deploy.sh 的前缀冲突检查也不再豁免「标签缺失但 project 匹配」的存量容器。
- 部署身份是启动前提：Supervisor 启动入口对缺失/空的部署实例 ID 直接失败，先于任何 Docker 客户端构造与资源变更；运行期不存在「未配置即全认领」的降级模式。
- 持久化输入在加载边界严格拒绝：Profile 存量 `launch_args` 不在白名单内时，加载即报错并指名 Profile，要求先修复数据再启动；任何层都不得静默过滤、截断或改写存量输入。
- viewer 身份只有一个文档化来源（宿主页 `?profileId=`）：URL 的其他参数名与全局变量注入都不是身份来源，出现即拒绝，防止 iframe 内页面自带身份越权到其他 Profile。
