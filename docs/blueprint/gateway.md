# Stream Gateway

本模块实现 CBrowser v2 独立认证信令 Gateway、RTC 凭证轮换与 Agent 健康状态转存服务（`cbrowser.gateway` 与 `cbrowser.rtc_config`）。网关作为独立 aiohttp 服务运行，对外暴露统一的 `/stream/*` 端点，对内提供 Supervisor 控制 RPC 与 API 鉴权联动。WebRTC 音视频媒体流直接通过 UDP mux 与 coturn 中继传输，绝不经过 Gateway。

## 权限与部署边界

Gateway 运行于非 root、只读文件系统容器沙箱内，不挂载 Docker Socket，不直连 SQLite 业务数据库，不导入 SQLAlchemy ORM。

1. **凭证隔离**：
    - Gateway 与 Supervisor 间控制面 RPC 使用 `CBROWSER_GATEWAY_TOKEN_FILE` 提供的 Bearer 凭证（≥32 字节，常量时间比较）。
    - Gateway 与 Stream Agent 间注册使用 `CBROWSER_AGENT_KEY_FILE` 驱动的 HMAC 实例凭证校验（`AgentCredentials`）。
    - Gateway 与 CBrowser API 间内部授权使用 `CBROWSER_GATEWAY_API_TOKEN_FILE` Bearer 凭证。
    - coturn REST HMAC 认证使用 `CBROWSER_TURN_SECRET_FILE`（≥32 字节）。
2. **进程隔离**：
    - Gateway 重启或异常 SIGKILL 不影响运行中的 Browser Runtime 与 Stream Runtime。
    - Stream Agent 具备自动退避重连机制，网关恢复后自动重注册；外部页面刷新或重连即可恢复信令。

## Agent 主动注册 (`/stream/agent/register`)

每个 Stream Agent 启动后向 Gateway 建立专用 WebSocket 连接：

1. **握手鉴权**：请求携带 `Authorization: Bearer <token>`，首包必须为 `ProtocolEnvelope(action=AgentAction.REGISTER)`，携带 `AgentRegisterPayload`（含 profile_id、runtime_instance_id、selkies_version、runtime_state、udp_port、config_version、turn_host、turn_port）。
2. **实例绑定真相**：Gateway 校验 Agent HMAC 签名，并调 API `GET /api/v1/internal/gateway/profiles/{profile_id}/runtime` 核对 API 当前持久绑定：
    - 若 `runtime_instance_id` 与 API 不一致（过期实例或退役实例），立即发送 Close 1008，且**绝不覆盖或影响当前已注册实例**。
    - 校验通过后回 `GatewayRegisterResponse(status="ok")`，下发当前代 `AgentAction.RTC_CONFIG`（包含用 Agent 上报的实际 turn_host/turn_port 动态组装的 Stream 侧 coturn 凭证与配置）。
3. **心跳与失联**：
    - Agent 注册成功后立即发送首个 `AgentAction.HEARTBEAT`，此后每 10 秒一次；载荷为 `AgentHeartbeatPayload`（`runtime_state`、`viewer_count`、`unpaused_video_consumers`、`capture_running`），载荷不合法时丢弃并记录异常类型，不刷新存活时间与上报值。
    - Gateway 监控注册心跳，若超过 30 秒未收到任何心跳，判定 Agent 失联，移除注册表项并关闭关联的所有 Viewer WebSocket（Code 1001）。
4. **回传包身份核对与会话隔离**：
    - Agent WS 上收到的 tunnel 包与 action 包，`profile_id`、`runtime_instance_id`、`agent_session_id` 必须等于该连接注册时的值，否则丢弃并记录 warning（不含载荷内容）。
    - tunnel 包的 `conn_id` 必须属于本 Profile 且由本 Agent 会话打开的 Viewer，否则丢弃。
    - 某 Agent WS 结束（含被同实例新注册替换）时，关闭所有绑定该 session 的 Viewer（Close 1001），不影响绑定新 session 的 Viewer。

## Viewer 隧道与连接隔离 (`/stream/{profile_id}/signal`)

外部 Chrome 页面建立 WebRTC 信令连接时访问 `GET /stream/{profile_id}/signal`：

1. **升级前三级校验**：
    - **Origin 门禁**：Origin 必须在 `CBROWSER_ALLOWED_ORIGINS` 白名单中，否则返回 HTTP 403。
    - **会话鉴权**：提取 `cbrowser_session` Cookie，调 API `POST /api/v1/internal/gateway/viewer-authorize` 校验登录态与 Profile 授权，未授权返回 HTTP 401/403。
    - **就绪检查**：检查该 Profile 在网关内存中已有活跃 Agent，且 API 查询 `observed_state` 为 `running`（或 `ready`），否则返回 HTTP 503 并说明原因。
2. **握手与首帧**：
    - 生成唯一 `connection_id`，记录其绑定的 `agent_session_id`。
    - 首帧向页面发送 `{"cbrowser": "rtc_config", "generation": N, "rtc_config": {...}}`，客户端配置包含公开可达 TURN URL，`relay-only` 模式下 `iceTransportPolicy="relay"`。
    - 向 Agent 发送 `GatewayTunnelEnvelope(type="open", conn_id=connection_id)`。
3. **控制帧分流与隧道隔离**：
    - 页面发往 Gateway 的文本中，若为 JSON 对象且包含 `"cbrowser"` 键，则按内部控制帧消费，**绝不转发给 Agent**；当前只处理 `ice_restart_answer`，其他类型（含旧 `activity`）直接丢弃；控制帧处理异常记录 warning（仅记录异常类型），控制帧仍不转发。
    - 其余文本原样经 `GatewayTunnelEnvelope(type="msg")` 转发给 Agent；Agent 回包原样发给页面。
    - 每个 Viewer 拥有完全独立的隧道与 connection_id；关闭任一 Viewer 连接不影响同 Profile 下的其他连接。

## 前台状态来源 (AC-007)

计划 9.3（2026-10-30 修订）：页面可见性只走 Selkies 官方每 Peer `STOP_VIDEO`/`START_VIDEO`，Gateway 不采集页面可见性或活动，也不向 Agent 下发可见性更新（协议中已无 `visibility_update`）。

1. **数据来源**：Stream Agent 在健康消息中上报取自 Selkies 的 primary 显示未暂停视频 consumer 数（`video_paused` 为假的 Peer）与捕获是否运行（`is_screen_capturing()`）。
2. **转存**：Gateway 在当前注册记录上保存最近一次合法上报值；新注册（含同 Profile 新实例）从“未上报”开始，不继承旧值。
3. **查询**：Supervisor 的 visibility 端点返回 `has_foreground_viewers = unpaused_video_consumers > 0`，并附 `unpaused_video_consumers` 与 `capture_running`；尚未收到上报时返回 503（未知，不猜测为 False）。值最多滞后一个心跳周期（10 秒）。
4. **边界**：信令心跳只判 Agent 存活，不形成所有权或输入锁；页面卡死而未发 `STOP_VIDEO` 时该 Peer 仍计为 consumer，直到 PeerConnection 断开。

## Supervisor 控制端点

Supervisor 经内部网络调用 Gateway 控制端点（使用 `CBROWSER_GATEWAY_TOKEN_FILE` Bearer 认证）：

|端点|方法|说明|错误码|
|---|---|---|---|
|`/gateway/v1/internal/profiles/{profile_id}/visibility`|GET|返回 Agent 最近上报的前台状态|401（未授权）、503（Agent离线或尚未上报）、409（实例不符）|
|`/gateway/v1/internal/profiles/{profile_id}/quota`|POST|转发帧率配额 `max_fps_cap` 给 Agent|401（未授权）、503（Agent离线）、409（实例不符）|
|`/gateway/v1/internal/profiles/{profile_id}/disconnect`|POST|关闭该 Profile 全部 Viewer 连接并通知 Agent|401（未授权）、503（Agent离线）、409（实例不符）|

`disconnect` 只断开 Viewer 连接，保持 Agent 注册 WebSocket 存活。

## RTC 配置与 TURN 轮换调度 (AC-004)

`RtcConfigService` 与 `RotationCoordinator` 负责管理 coturn REST HMAC 短期凭证与在线 ICE restart：

1. **HMAC 凭证生成**：
    - `username = "<expiry_unix>:<role>-<profile_id>"`，其中角色分为 `client` 和 `stream`。
    - `credential = base64(HMAC-SHA1(secret, username))`。
    - `RtcGeneration` 只保存 Stream 侧凭证（username/credential），下发给 Agent 时用其注册上报的 `turn_host`/`turn_port` 动态组装 `turn:<host>:<port>?transport=udp` 与 `?transport=tcp`（IPv6 带方括号）。客户端配置使用公网可达 URL `CBROWSER_TURN_PUBLIC_URLS`。
2. **代际轮换周期**：
    - 默认参数：凭证有效期 24h（86400s）、生成间隔 12h（43200s）、ICE restart 提前量 6h（21600s）。允许测试环境显式缩短。
    - 生成新 generation（in_progress，即新连接开始使用的配置）时立即向已注册 Agent 发送 `rtc_config`（新一代 Stream 侧配置），保证新建 PeerConnection 与客户端使用同一代。
    - 新建连接总取当前最新有效代。
    - 当到达生成间隔时生成新代代号 `N+1`；在旧代到期前提前量触发该 Profile 现存 Viewer 连接的 ICE restart。
3. **ICE Restart 消息序列**：
    - Gateway -> Agent：`AgentAction.ICE_RESTART`（payload 带 Stream 侧新代配置，force_relay 标志）；Agent 收到后更新其 `active_rtc_config`。
    - Agent -> Gateway：`AgentAction.ICE_RESTART_OFFER`（带 offer SDP）。
    - Gateway -> Viewer：`{"cbrowser": "ice_restart", "generation": N+1, "rtc_config": {...}, "offer": {...}}`。
    - Viewer -> Gateway：`{"cbrowser": "ice_restart_answer", "generation": N+1, "sdp": {...}}`。
    - Gateway -> Agent：`AgentAction.ICE_RESTART_ANSWER`（带 answer SDP）。
    - Agent 只对信令 stable 且 ICE 已连通的 PeerConnection 执行重启；初始协商中的连接回报 `error: peer_not_ready`，由 Gateway 退避重试。
    - Agent -> Gateway：新 ICE 代真实接管、旧代关闭并拒绝发送后发 `AgentAction.ICE_RESTART_COMMITTED`（带 Gateway 代号）；20 秒内未接管或失败发 `AgentAction.ERROR`。Selkies 的 `setRemoteDescription` 在后台任务里做连通性检查，answer 转发完成不等于轮换成功。
    - Gateway 只在收到与目标代号一致的确认后把该连接记为已迁移；Profile 全部连接迁移后才提交本代并记录 `Generation N officially committed for profile`。错误或 30 秒未确认按退避重试。
4. **容错与退避**：
    - 重启过程发生超时或 Agent 返回 `AgentAction.ERROR` 时，Gateway 记录告警并按 2、4、8、16、32、最高 60 秒指数退避重试。
    - 旧凭证到期仍未完成全部迁移时，记录 ERROR 级别告警并保持重试，绝不静默将过期凭证下发给新连接。

## 配置项清单

全部配置必须显式声明，缺失时服务立即失败退出，严禁使用硬编码默认秘密：

|环境变量|类型|默认值|说明|
|---|---|---|---|
|`CBROWSER_GATEWAY_HOST`|string|`0.0.0.0`|Gateway 监听地址|
|`CBROWSER_GATEWAY_PORT`|int|`18080`|Gateway 监听端口|
|`CBROWSER_AGENT_KEY_FILE`|path|-|Agent HMAC 认证主密钥文件（≥32字节）|
|`CBROWSER_GATEWAY_TOKEN_FILE`|path|-|Supervisor 控制 RPC Bearer 凭证文件（≥32字节）|
|`CBROWSER_GATEWAY_API_URL`|url|-|CBrowser API 基础地址（如 `http://api:8000`）|
|`CBROWSER_GATEWAY_API_TOKEN_FILE`|path|-|Gateway 调 API 内部鉴权 Bearer 凭证文件（≥32字节）|
|`CBROWSER_ALLOWED_ORIGINS`|string|-|允许的 WebSocket Origin 列表（逗号分隔）|
|`CBROWSER_TURN_SECRET_FILE`|path|-|coturn static-auth-secret 凭证文件（≥32字节）|
|`CBROWSER_WEBRTC_MODE`|enum|-|WebRTC 模式（`local`、`lan`、`public`、`relay-only`）|
|`CBROWSER_TURN_PUBLIC_URLS`|string|-|客户端可达 TURN URL 列表（逗号分隔）|
|`CBROWSER_RTC_CREDENTIAL_LIFETIME_SEC`|float|`86400.0`|TURN 凭证有效期（默认24小时）|
|`CBROWSER_RTC_GENERATION_INTERVAL_SEC`|float|`43200.0`|新凭证代际生成间隔（默认12小时）|
|`CBROWSER_RTC_ICE_RESTART_LEAD_TIME_SEC`|float|`21600.0`|旧凭证到期前触发 ICE restart 提前量（默认6小时）|
|`CBROWSER_AGENT_HEARTBEAT_TIMEOUT_SEC`|float|`30.0`|Agent 心跳失联判定超时阈值|

## 日志与脱敏

遵循安全与审计规范：

- 严格禁止记录 token、cookie、password、coturn HMAC secret、TURN credential 明文。
- 严格禁止在普通日志中输出 SDP 全文。
- 错误与告警日志仅包含关键事件、profile_id、connection_id 与错误类型。
