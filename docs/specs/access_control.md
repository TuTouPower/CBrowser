# 需求规范：访问控制与自动化凭证

本文描述 t006 交付的用户鉴权、Viewer 授权与自动化凭证行为。前端登录界面与登录守卫由 t007 交付（见 profile_management），CDP 代理入口由 t008 对接；生效状态以 specs_index 为准。

## 管理员与会话

- 首次启动从外部文件读取管理员密码并以 Argon2id 保存；已有管理员时不覆盖。文件缺失、过短且库内无管理员时拒绝启动。
- 登录成功设置 HttpOnly、Secure、SameSite=Strict 会话 Cookie 与 CSRF Cookie；错误密码 401，同一来源每分钟超过 5 次失败返回 429。登出与过期会话立即失效。
- 未登录访问受保护 `/api/v1` 接口返回 401；写请求缺少或错误 CSRF、Origin 不在允许列表返回 403。允许 Origin 列表必须显式配置。

## Viewer 信令授权

- 打开 `/stream/{profileId}/signal` 前依次校验 Origin、登录会话与 Profile 存在性，再确认对应 Stream Agent 已注册且运行状态为 running；任一失败返回明确 HTTP 状态且不建立 WebSocket。
- 前端可见响应、页面与日志不含 Selkies master/controller token 或任何服务间凭证；页面经认证隧道以 controller 接入，token 由 Stream Agent 代注入（d024）。

## 自动化凭证

- 登录用户可创建、列出、撤销自动化凭证；明文只在创建响应出现一次，列表不含明文。凭证限定 Profile 范围，撤销后立即失效。
- 自动化授权允许无 Origin 的非浏览器客户端，但必须持有效凭证且 Profile 在授权范围内；登录 Cookie 不被接受。拒绝与生命周期事件写入审计，审计不泄漏秘密。

## 自动化 CDP 入口

- 新入口为 `WS /api/v1/automation/profiles/{profileId}/cdp`，要求 `Authorization: Bearer cbat_...`；无效、撤销或越权 Profile 关闭 4401。
- 旧 `WS /api/profiles/{profileId}/cdp` 只薄转发新代理，使用同一凭证，不发布旧 CDP TCP 端口，不出现在 OpenAPI。
- API 校验通过后经内部 Supervisor token 建立到 Supervisor 的 WebSocket，由 Supervisor 再经 Agent UDS 转发到浏览器 loopback CDP；所有转发均为双向原样透传。
- `GET /api/v1/profiles/{profileId}/automation` 返回授权端点路径、运行状态与 Supervisor 配置状态，不返回明文凭证。

## 内部服务身份、Origin 与审计（t021）

- 内部三面未配置统一返回 503 `service_not_configured`（`retryable=false`），与 503 `database_busy`（`retryable=true`）区分；OpenAPI 按路径标注 `SupervisorServiceBearer`（含 Artifact 面）/`GatewayServiceBearer`，两令牌互不通用。
- Origin 全链统一 `normalize_origin`：Viewer 授权对入参与允许列表都先归一化再比对（尾斜杠/默认端口变体等价），畸形 Origin 返回 `invalid_origin`、畸形 Referer 返回 403，不抛 500。
- 内部 Gateway 的 `automation-authorize` 面已删除（无生产消费者）；自动化授权只经 v1 入口的 `AuthService`。
- 授权审计覆盖全部拒绝类别并带 reason 与来源：已知令牌逐条记录；未知/非法令牌按 `(reason, source)` 聚合计数，不存令牌/哈希；成功授权不清除限速失败记录。
- 密码哈希/校验（含哑元）在线程池执行，不阻塞事件循环。

## Viewer 边缘授权与 CDP 边界（t064）

- `/stream/{profileId}/signal` 的会话判定移到 Caddy 边缘：Caddy 删除客户端伪造的 `X-CBrowser-Authorized-Profile` 与 `X-CBrowser-Viewer-Grant`，以独立边缘证明调用 API `GET /api/v1/internal/edge/viewer-authorize`；API 复用 `AuthService.authorize_viewer` 判定会话、Origin 与 Profile 后，签发 60 秒、仅绑定该 Profile 且不含会话标识的 HMAC viewer grant。
- Caddy 只复制 API 回注的授权上下文，并删除待代理请求的 Cookie；Gateway 先验 Origin，再在本地验 grant 的签名、到期、Profile 绑定与 authorized Profile 头一致性，最后验 Agent 和 runtime 就绪。Gateway 不接收或解析 `cbrowser_session`；每次新握手重新走边缘解析，登出与撤销在下一次握手生效。原 Gateway 中转的 `POST /api/v1/internal/gateway/viewer-authorize` 已删除。
- 外部 listener 对 `/api/v1/internal/*` 一律 404。直连 Gateway、伪造授权头、跨 Profile grant 与非法 Origin 均不能建立 viewer 连接。`/stream/agent/register` 不套 viewer 授权，继续使用独立 Agent 凭证。
- 管理会话 Cookie 保持 `Path=/`，不改为 signal 路径 Cookie。普通 Profile detail/list 不含 `cdp_ws_path` 或 automation token；`cdp_ws_path` 只由专用 `GET /api/v1/profiles/{profileId}/automation` 返回，实际 CDP 连接仍要求 automation token 与控制权围栏。Browser CDP 只监听容器回环临时端口；真实引擎拒绝域名 Host 的回环发现请求与跨 Origin CDP WebSocket。

## 验证

真实 SQLite + HTTP 集成测试覆盖上述正负例；真实 HTTPS Cookie 属性、跨 Origin 与未授权 Profile 的信令拒绝由 Gateway E2E 在官方 Chrome 中验证。自动化 CDP 代理由单元（Supervisor→UDS）、集成（API→Supervisor→UDS）和真实浏览器 UDS CDP E2E 共同验证。

## 登录回跳约束（t023）

- 登录后的 `next` 回跳只接受站内绝对路径；一切指向登录页本身的变体（大小写、尾斜杠、携带 query/hash）一律拒绝，避免登录后循环；协议相对、反斜杠与绝对 URL 等开放重定向形态继续拒绝。

## 前端出站同源边界与注销处置（t025）

- 前端三个出站入口（ApiClient 请求、SSE 事件流连接、Artifact 下载链接生成）统一按**最终解析 URL** 做同源判定，再决定是否附带凭据与 CSRF：绝对 URL、协议相对、反斜杠及混合变体只要解析到跨源即在发送前拒绝（不调用 fetch、不产生跨源下载链接）；同源目标保持既有凭据/CSRF 语义。
- 客户端不存在可配置的跨源基地址：ApiClient 与 SSE 客户端均无 baseUrl/url 配置项，测试以同源夹具（注入 fetch 转发或同源 origin）访问测试服务器，不为测试开放生产跨源。
- 注销失败处置：登出请求失败时本地会话一律结束——认证状态清除、内存 CSRF token 清除、SSE 停止；各注销调用点（SSE unauthorized 回调、页头登出）显式处置 logout 的 rejection，不产生 unhandled rejection。

## 网络访问与 Origin 派生规范（t042；t054 重写：局域网彻底删除）

- 网络配置只在部署期存在：部署时渲染 Caddyfile，端口只从部署输入 `CBROWSER_HTTPS_PORT` 来；运行期不存在网络设置写端点、应用操作、待应用/已应用双态，也不存在断开预检与入口变化提示。
- Origin 白名单来源单一：API 与 Gateway 的 `allowed_origins` 均由部署端口确定性派生（`derive_origin_whitelist`，`127.0.0.1` 与 `localhost` + 端口，纯 https）；两服务在启动时读取同一部署输入。
- 局域网彻底不做：`lan_access_enabled` / `lan_advertised_ip` 字段与校验、LAN 媒体策略分支、Stream 绑定参数、root-ca 下载端点（`GET /api/v1/network/root-ca`）全部删除；Caddy 与 Stream 固定绑定 `127.0.0.1`。
- 根证书安全边界：API 容器挂载中绝不挂载 `caddy_data` 卷，严禁暴露 Caddy CA 私钥 `root.key`。

## 数据库瞬时故障的可重试错误与登录友好提示（t051）

- 数据库瞬时错误分级：`SQLITE_BUSY` / `SQLITE_LOCKED` / `SQLITE_IOERR`（含扩展码，按扩展码 & 0xFF 取主码判定）为瞬时错误，API 返回 503（BUSY/LOCKED → `database_busy`，IOERR → `database_unavailable`）、`retryable=true`、`Retry-After: 1`；`IntegrityError` 等确定性错误响应不变（409 / 500 `database_error` / `retryable=false`）。
- 登录建会话遇到有限次瞬时数据库故障后恢复时登录成功；故障持续超过重试上限（3 次、有界退避）时返回上述可重试 503，不返回 500。重试整方法重跑、每次新会话；速率限制在数据库访问前判定，重试不重复计数。
- 数据库错误日志包含 SQLite 错误码名（`sqlite_errorcode` / `sqlite_errorname`）、请求方法与路径，不包含 SQL 文本、绑定参数值、密码或会话 token（`str(exc.orig)` 含 SQL 与绑定参数，禁止记入日志；traceback 行同样会带 SQL，故不用 `logger.exception`）。
- 登录页收到 `database_busy` / `database_unavailable` 时显示当前界面语言的本地化文案（`loginDatabaseUnavailable`），不显示后端英文原文；其它错误保持原有透传。
