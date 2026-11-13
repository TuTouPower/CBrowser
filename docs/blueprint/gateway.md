# Stream Gateway

本模块实现 CBrowser 独立认证信令 Gateway 与 Agent 健康状态转存服务（`cbrowser.gateway`）。网关作为独立 aiohttp 服务运行，对外暴露统一的 `/stream/*` 端点，对内提供 Supervisor 控制 RPC 与 API 鉴权联动。WebRTC 音视频媒体流经 host 候选直连（本机模式 `127.0.0.1`，局域网模式 `0.0.0.0`），无 TURN/coturn，绝不经过 Gateway（ADR 026 修订 ADR 013）。Origin 白名单由当前已应用的网络配置确定性派生。

## 权限与部署边界

Gateway 运行于非 root、只读文件系统容器沙箱内，不挂载 Docker Socket，不直连 SQLite 业务数据库，不导入 SQLAlchemy ORM。

1. **凭证隔离**：
    - Gateway 与 Supervisor 间控制面 RPC 使用 `CBROWSER_GATEWAY_TOKEN_FILE` 提供的 Bearer 凭证（≥32 字节，常量时间比较）。
    - Gateway 与 Stream Agent 间注册使用 `CBROWSER_AGENT_KEY_FILE` 驱动的 HMAC 实例凭证校验（`AgentCredentials`）。
    - Gateway 与 CBrowser API 间内部授权使用 `CBROWSER_GATEWAY_API_TOKEN_FILE` Bearer 凭证。
2. **进程隔离**：
    - Gateway 重启或异常 SIGKILL 不影响运行中的 Browser Runtime 与 Stream Runtime。
    - Stream Agent 具备自动退避重连机制，网关恢复后自动重注册；外部页面刷新或重连即可恢复信令。

## Agent 主动注册 (`/stream/agent/register`)

每个 Stream Agent 启动后向 Gateway 建立专用 WebSocket 连接：

1. **握手鉴权**：请求在查询参数携带 `profile_id`、`runtime_instance_id` 并在 `Authorization: Bearer <token>` 中携带实例凭证；Gateway 在升级 WebSocket 前完成凭证与 API 绑定校验。升级后首包必须为 `AgentRegisterEnvelope(action=register)`，其载荷字段与查询参数一致（含 profile_id、runtime_instance_id、selkies_version、runtime_state、udp_port、config_version）。
2. **实例绑定真相**：Gateway 校验 Agent HMAC 签名，并调 API `GET /api/v1/internal/gateway/profiles/{profile_id}/runtime` 核对 API 当前持久绑定：
    - 若 `runtime_instance_id` 与 API 不一致（过期实例或退役实例），在 WebSocket 升级前返回 HTTP 403，且**绝不覆盖或影响当前已注册实例**。
    - 校验通过后回 `GatewayRegisterResponse(status="ok")`。不再下发 RTC/TURN 配置。
3. **心跳与失联**：
    - Agent 注册成功后立即发送首个 `AgentAction.HEARTBEAT`，此后每 10 秒一次；载荷为 `AgentHeartbeatPayload`（`runtime_state`、`viewer_count`、`unpaused_video_consumers`、`capture_running`），载荷不合法时丢弃并记录异常类型，不刷新存活时间与上报值。
    - Gateway 监控注册心跳，若超过 30 秒未收到任何心跳，判定 Agent 失联，移除注册表项并关闭关联的所有 Viewer WebSocket（Code 1001）。
4. **回传包身份核对与会话隔离**：
    - Agent WS 上收到的 tunnel 包与 action 包，`profile_id`、`runtime_instance_id`、`agent_session_id` 必须等于该连接注册时的值，否则丢弃并记录 warning（不含载荷内容）。
    - tunnel 包的 `conn_id` 必须属于本 Profile 且由本 Agent 会话打开的 Viewer，否则丢弃。
    - 某 Agent WS 结束（含被同实例新注册替换）时，关闭所有绑定该 session 的 Viewer（Close 1001），不影响绑定新 session 的 Viewer。

注册节流为双预算（t022）：在途握手预留（上限 4，按来源）与失败窗口（20 次/60 秒）分离，成功不消耗失败额度也不清除既有失败记录，超时/取消/失败等全部退出路径释放预留；预算耗尽返回 429。Agent 重连退避带可注入 jitter（缩放至 [50%,100%]，不超上限），避免多 Agent 同步重试。心跳同步更新 registry 的 `runtime_state`（仅已注册会话）。消息预算三层单一权威（stream 协议）：原始 data 1MiB、序列化 envelope 2MiB+64KiB、WS 帧 6MiB+64KiB；超限按 1009 受控关闭单个连接，不影响其他连接。

结构化拒绝（t026）：注册载荷可携带 Agent 的 `build_id`；成功 ACK 回 Gateway 的 `gateway_build_id`（均来自 `CBROWSER_BUILD_ID`，缺省 `dev`）。WS 建立后的拒绝（载荷非法、协议版本不支持、身份不一致）先下发 `GatewayRegisterResponse(status="error", rejection={code, message, gateway_build_id, agent_build_id})` 再关闭，并按 Profile 记录最近一次拒绝（凭证拒绝、实例未绑定等升级前拒绝同样记录），成功注册清除记录。Supervisor 经控制端点读取注册状态与拒绝原因，据此区分可修复与不可修复：版本/凭证/身份/载荷/实例未绑定类拒绝不触发 Stream 替换。

## Viewer 隧道与连接隔离 (`/stream/{profile_id}/signal`)

外部 Chrome 页面建立 WebRTC 信令连接时访问 `GET /stream/{profile_id}/signal`：

1. **升级前三级校验**：
    - **Origin 门禁**：Origin 必须在由部署端口确定性派生的白名单中（纯 https，`derive_origin_whitelist(CBROWSER_HTTPS_PORT)`，默认端口 `56661`；API 与 Gateway 在启动时从同一部署输入派生，运行期无更新通道），否则返回 HTTP 403。
    - **会话鉴权**：提取 `cbrowser_session` Cookie，调 API `POST /api/v1/internal/gateway/viewer-authorize` 校验登录态与 Profile 授权，未授权返回 HTTP 401/403。
    - **就绪检查**：检查该 Profile 在网关内存中已有活跃 Agent，且 API 查询 `observed_state` 为 `running`（或 `ready`），否则返回 HTTP 503 并说明原因。
2. **握手**：生成唯一 `connection_id`，记录其绑定的 `agent_session_id`，向 Agent 发送 `GatewayTunnelEnvelope(type="open", conn_id=connection_id)`；不再向页面下发任何 RTC/TURN 首帧。
3. **拒绝顺序**：Origin、会话鉴权、Agent 就绪与 API 观测状态全部在 `ws.prepare()` 与 viewer 注册之前完成；拒绝时返回 HTTP 403/401/503，网关内不残留 viewer 条目。Viewer 授权失败按来源与 Profile 限流，超限返回 429。
4. **隧道隔离**：页面发往 Gateway 的文本中，含 `"cbrowser"` 控制键的帧直接丢弃，绝不转发给 Agent；其余文本原样经 `GatewayTunnelEnvelope(type="msg")` 转发。每个 Viewer 拥有完全独立的隧道与 connection_id；关闭任一 Viewer 连接不影响同 Profile 下的其他连接。
5. **帧上限**：Agent 与 Viewer 两侧 WebSocket 均设置 6 MiB + 64 KiB 的 `max_msg_size`，超限帧在传输层被拒绝。

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
|`/gateway/v1/internal/profiles/{profile_id}/registration`|GET|返回注册状态、Agent/Gateway build 标识与最近一次结构化拒绝（t026）|401（未授权）|
|`/gateway/v1/internal/profiles/{profile_id}/quota`|POST|转发帧率配额 `max_fps_cap` 给 Agent|400（body/配额非法）、401（未授权）、503（Agent离线）、409（实例不符）|
|`/gateway/v1/internal/profiles/{profile_id}/disconnect`|POST|关闭该 Profile 全部 Viewer 连接并通知 Agent|400（body 非法）、401（未授权）、503（Agent离线）、409（实例不符）|

`disconnect` 只断开 Viewer 连接，保持 Agent 注册 WebSocket 存活。 断开按目标逐个隔离处理：单个 Viewer 关闭失败不跳过其余目标，Agent 通知失败在全部目标处理完后明确返回 503；`quota` 向 Agent 发送失败同样明确 503，不再冒泡未处理 500。三条控制端点的可用性与实例围栏共用同一判定（`supervisor_fence_failure`）。

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
|`CBROWSER_NETWORK_STATE_DIR`|path|`/data/network`|已应用网络版本与 Origin 白名单共享目录（只读挂载）|
|`CBROWSER_AGENT_HEARTBEAT_TIMEOUT_SEC`|float|`30.0`|Agent 心跳失联判定超时阈值|

## 日志与脱敏

遵循安全与审计规范：

- 严格禁止记录 token、cookie、password 与任何凭证明文。
- 严格禁止在普通日志中输出 SDP 全文。
- 错误与告警日志仅包含关键事件、profile_id、connection_id 与错误类型。

## 公共 API 面边界

公开 OpenAPI（`schemas/openapi/cbrowser_v1.json`）与前端生成类型只包含 `/api/v1` 用户面路由。`/api/v1/internal/supervisor/*` 与 `/api/v1/internal/gateway/*` 使用 `include_in_schema=False`，仅供持有独立 Bearer 凭证的 Supervisor/Gateway 服务调用，不进入公共契约。Runtime Agent UDS 协议由 `scripts/export_runtime_agent_protocol.py` 生成 `schemas/runtime/agent_protocol.json`，与 Supervisor 协议导出脚本保持同一逐字节校验模式；禁止手改生成文件。

## 中立模块归属（t062）

Gateway 的端点/Origin 归一、Agent 凭证校验与客户端 IP 解析均来自中立包 `cbrowser/shared/`（`endpoints`、`agent_credentials`、`client_ip`）；Gateway 不 import Supervisor 包、不携带 ORM 与 domain，镜像只打包 gateway 包、shared 整包与 stream_agent 的协议两文件。Origin 白名单由部署期 `network_config.derive_origin_whitelist` 以同一 `normalize_origin` 生成，与请求侧校验天然一致。
