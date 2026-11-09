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

## 验证

真实 SQLite + HTTP 集成测试覆盖上述正负例；真实 HTTPS Cookie 属性、跨 Origin 与未授权 Profile 的信令拒绝由 Gateway E2E 在官方 Chrome 中验证。自动化 CDP 代理由单元（Supervisor→UDS）、集成（API→Supervisor→UDS）和真实浏览器 UDS CDP E2E 共同验证。

## 登录回跳约束（t023）

- 登录后的 `next` 回跳只接受站内绝对路径；一切指向登录页本身的变体（大小写、尾斜杠、携带 query/hash）一律拒绝，避免登录后循环；协议相对、反斜杠与绝对 URL 等开放重定向形态继续拒绝。

## 前端出站同源边界与注销处置（t025）

- 前端三个出站入口（ApiClient 请求、SSE 事件流连接、Artifact 下载链接生成）统一按**最终解析 URL** 做同源判定，再决定是否附带凭据与 CSRF：绝对 URL、协议相对、反斜杠及混合变体只要解析到跨源即在发送前拒绝（不调用 fetch、不产生跨源下载链接）；同源目标保持既有凭据/CSRF 语义。
- 客户端不存在可配置的跨源基地址：ApiClient 与 SSE 客户端均无 baseUrl/url 配置项，测试以同源夹具（注入 fetch 转发或同源 origin）访问测试服务器，不为测试开放生产跨源。
- 注销失败处置：登出请求失败时本地会话一律结束——认证状态清除、内存 CSRF token 清除、SSE 停止；各注销调用点（SSE unauthorized 回调、页头登出）显式处置 logout 的 rejection，不产生 unhandled rejection。

## 局域网访问与 Origin 派生规范（t042；LAN 部分按 p053 暂搁：Stream 未接线、生产 root-ca 404，暂不修）

- 网络访问配置权威：API 为唯一权威，区分「待应用配置（`pending_config`）」与「已应用不可变版本（`applied_version`）」。
- Origin 白名单来源单一：API 与 Gateway 的 `allowed_origins` 均由当前已应用的不可变版本确定性派生；本机模式放行 `127.0.0.1` 与 `localhost`，局域网模式追加 `lan_advertised_ip`，两服务读取同一来源。
- 根证书安全边界：`GET /api/v1/network/root-ca` 仅允许下载 Caddy 本地 CA 的公钥根证书（`root.crt`）；API 容器挂载中绝不挂载 `caddy_data` 卷，严禁暴露 `root.key` 私钥。
- 入口变化提示：从局域网来源切换到本机模式前，接口与前端主动返回 `will_disconnect` 警告并给出新的可达地址。
