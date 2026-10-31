# Task review t006（reviewer_focus: 代码）

- task：`t006_v2_gateway_auth_rtc`
- spec：`docs/tasks/t006_v2_gateway_auth_rtc/task.md`
- diff_anchor：`c33e55f77cb221510396628e792a08b905b2ebe0`
- target：`git -C '/Users/karson/kar/code/CBrowser_t006' diff c33e55f77cb221510396628e792a08b905b2ebe0`
- round：1
- reviewed_at：2026-10-31T13:45:00+08:00

reviewed_scope: 8a0b74f272c14c47

## Findings

### t006_code_f001 - Gateway 与 API 对 CBROWSER_ALLOWED_ORIGINS 的末尾斜杠归一化行为不一致

- 严重度：minor
- 锚点：AC-001 / 安全配置与输入校验
- 位置：`src/backend/cbrowser/gateway/config.py:69` 与 `src/backend/cbrowser/api/app.py:59`
- 问题：`api/app.py` 在解析 `CBROWSER_ALLOWED_ORIGINS` 时使用了 `.rstrip("/")` 去除尾部斜杠，但 `gateway/config.py` 仅做了 `.strip()`。若环境变量传入形如 `https://example.com/`，API 端归一化为 `https://example.com`，而 Gateway 端配置仍保留尾部斜杠。浏览器发起的信令 WebSocket 请求 `Origin` 头按规范不带路径斜杠（如 `Origin: https://example.com`），在 Gateway `handle_viewer_signal` 的 `origin not in config.allowed_origins` 中会被拒绝并返回 403。
- 建议：在 `src/backend/cbrowser/gateway/config.py:69` 对 origin 增加 `.rstrip("/")` 规范化，与 API 端解析逻辑保持一致。

### t006_code_f002 - 轮换准备窗口期新建立的连接未登记已迁移导致触发冗余 ICE 重启

- 严重度：minor
- 锚点：AC-004 / 轮换性能与信令时序
- 位置：`src/backend/cbrowser/gateway/rotation.py:174-206`、`src/backend/cbrowser/gateway/server.py:525-533`
- 问题：当 Profile 存在正在生成的轮换代（`state.in_progress_generation`）时，新连接通过 `rotation.get_effective_generation` 直接获取该新代配置建连。然而 `server.py` 未将该连接登记为已属于新代，`state.migrated_connections` 中无其 `conn_id`。当触发轮换时，`_start_restart_round` 将该新连接判定为 `unmigrated` 并发起一次冗余的 `ICE_RESTART`，待对端连接稳定后重新协商同代凭据。
- 建议：在 `RotationCoordinator` 增加新连接登记机制，若新连接生成时已获取 `in_progress_generation`，直接将其加入 `migrated_connections`，避免冗余的 SDP 重协商。

### t006_code_f003 - Gateway 断连时 StreamAgent 未取消挂起的后台 ICE restart 任务

- 严重度：minor
- 锚点：AC-002 / 资源释放与健壮性
- 位置：`src/backend/cbrowser/stream_agent/agent.py:377-385`
- 问题：`StreamAgent.connect_and_run` 在与 Gateway WebSocket 断开连接进入 `finally` 时，取消了 `_heartbeat_task` 并清理了 viewer workers，但未取消 `self._restart_tasks` 中挂起的 `_handle_ice_restart_answer` 任务。这些任务在 `wait_restart_commit` 中可能继续挂起等待最长 20 秒超时后才自行结束，直到 Agent 显式调用 `stop()` 才会统一取消。
- 建议：在 `connect_and_run` 的 `finally` 块中遍历取消 `self._restart_tasks` 并清空集合，避免断开重连期间悬挂失效的重启等待协程。

### t006_code_f004 - Gateway handle_agent_register 单协程圈复杂度过高（CC=38）

- 严重度：minor
- 锚点：代码质量 / 圈复杂度标准（CC ≥ 15）
- 位置：`src/backend/cbrowser/gateway/server.py:279-472`
- 问题：`handle_agent_register` 单个协程承担了 HMAC 鉴权、首包格式与版本校验、实例绑定 CAS 校验、旧会话冲突清理、ACK/初始 RTC_CONFIG 下发，以及后续全量双向信令（Tunnel 转发/Action 分发/心跳存活/ICE 重启/错误处理）的多层嵌套逻辑，圈复杂度达 38（嵌套深度达 7 层），超出项目 `CC < 15` 的建议阈值。
- 建议：将消息循环内部的报文分发抽取为独立函数（如 `_handle_agent_tunnel_packet` 与 `_handle_agent_action_packet`），降低单协程认知复杂度。

## 结论

- 前轮 finding 复核：无（Round 1 首轮审查）
- 本轮新发现：4 条（minor 4 条，blocking 0 条）
- 未进表的提示：
  1. 文件过大统计与评估（降级规则：未直接引发跨模块状态分叉或可观测缺陷，不进表）：
     - `src/backend/cbrowser/stream_agent/agent.py`: 1142 行（≥ 800 行，网络通信、多代信令与生命周期状态机聚合）
     - `src/backend/cbrowser/supervisor/docker_adapter.py`: 1045 行（≥ 800 行，现有文件净增 57 行，含基础设施网络绑定）
     - `src/backend/cbrowser/stream_agent/policy.py`: 773 行（≥ 400 行，视频流控制与回调挂载）
     - `src/backend/cbrowser/supervisor/core.py`: 763 行（≥ 400 行，现有文件净增 17 行）
     - `src/backend/cbrowser/stream_agent/ice_transport.py`: 667 行（≥ 400 行，多代 ICE Transport 与轮换等待）
     - `src/backend/cbrowser/gateway/server.py`: 664 行（≥ 400 行，新建单文件承载 Gateway 路由与长任务）
     - `src/backend/cbrowser/api/v1/router.py`: 626 行（≥ 400 行，现有文件净增 33 行，增加 CSRF 依赖路由）
     - 测试与测试夹具源码：`tests/integration/test_gateway_signaling.py`（980 行）、`tests/unit/test_stream_agent_lifecycle.py`（924 行）、`tests/integration/test_gateway_rotation.py`（651 行）、`tests/fixtures/gateway_probe/topology.py`（614 行）。注：`tests/fixtures/gateway_probe/selkies_web_sha256.txt`（2007 行）为静态资源哈希清单，属于纯数据 fixture，按规则排除。
     建议在后续迭代中根据关注点分离原则拆分过大文件（如 Gateway 信令拆分与 Agent 生命周期模块化）。
  2. 圈复杂度提示（CC ≥ 10，建议简化）：
     - `src/backend/cbrowser/api/app.py:create_app` (CC=14), `lifespan` (CC=12)
     - `src/backend/cbrowser/auth/dependencies.py:require_csrf_and_origin` (CC=11)
     - `src/backend/cbrowser/gateway/rotation.py:tick` (CC=12)
     - `src/backend/cbrowser/gateway/server.py:handle_supervisor_disconnect` (CC=11)
     - `src/backend/cbrowser/gateway/server.py:handle_viewer_signal` (CC=22)
     - `src/backend/cbrowser/stream_agent/agent.py:connect_and_run` (CC=19)
     - `src/backend/cbrowser/stream_agent/agent.py:_handle_control_packet` (CC=24)
     - `src/backend/cbrowser/stream_agent/config.py:from_env` (CC=19)
     - `src/backend/cbrowser/supervisor/docker_adapter.py:attach_profile_infrastructure` (CC=23)
  3. 业务与范围审视：
     - 页面可见性触发替代方案评估：在无头 Chrome 156 下切换标签或最小化不改变 `document.visibilityState` 亦不派发事件。E2E 测试在页面内覆盖属性并派发 `visibilitychange` 事件，成功驱动官方客户端的 `STOP_VIDEO` 与 `START_VIDEO` 协议帧，进而驱动底层的视频管线启停与 Gateway 端点更新。该替代手段满足无桌面弹窗约束（d023），驱动了完整的端到端业务路径，足以支撑 AC-007 验收。
     - 边界与前置依赖：AC-001 中“master token 不返回前端”因当前 Stream 尚未配置 Selkies 每 Profile token，目前为空满足（已登记 p004）；AC-006 自动化 Bearer Token 凭证管理已在此 task 交付并在内部控制面端点验证，外部统一 CDP 代理入口属于后续 t008 AC-002。
- 总体判断：AC-001 ~ AC-007 验收标准在代码层真实落地，Argon2id 与会话安全控制严格，Gateway 注册表与独立隧道逻辑严密，多代 ICE 轮换与带界等待接管机制可靠，仅发现 4 条 minor 优化项，无 blocking 缺陷，判定通过。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：`re_verified`。reviewer 查验 `auth/service.py`、`auth_router.py`、`internal_gateway.py` 与 `gateway/server.py` 生产逻辑，独立重跑 `test_auth_service.py` 与 `test_auth_api.py` 验证 Argon2id 存储与验证、登录 Cookie 属性（HttpOnly/Secure/SameSite=Strict）、写请求缺 CSRF 报 403、Viewer WS 鉴权负例；核对 `tests/e2e/test_gateway_ac001_auth_e2e.py` 门禁证据 JSON 确认无凭据泄漏。
- AC-002：`re_verified`。reviewer 查验 `stream_agent/protocol.py`、`agent.py` 与 `gateway/server.py`，独立重跑 `test_stream_agent_protocol_v2.py`（注册字段校验）、`test_stream_agent_lifecycle.py`（10s 心跳节奏、1/2/4/8/16/30s 退避计算与实际执行）、`test_gateway_signaling.py`（过期实例注册拒绝且不覆盖当前连接、未就绪 503 拒绝）。
- AC-003：`trust_prior`。双真实 Chrome 页面解码音视频、各自 tab_id、无锁并发键盘输入、关闭一页另一页持续出帧、Gateway SIGKILL 浏览器 PID 保持与重启后重连恢复，依赖主控 round7b 门禁日志与 basetemp 原始 `ac003_media_evidence.json`。
- AC-004：`re_verified`。reviewer 查验 `rtc_config/service.py`、`rotation.py` 与 `agent.py`，独立重跑 `test_rtc_config.py`（HMAC 凭证生成、时间窗口计算）、`test_gateway_rotation.py`（新连接取当前代、Agent 确认接管才提交本代、报错退避重试）；核查真实 Stream SDK 提交用例 `test_stream_ice_commit_e2e.py` 与 `test_stream_rtc_config_e2e.py`。
- AC-005：`trust_prior`。真实无头 Chrome relay-only 双端 WebRTC、一代二代三代两次切换增量证明（视频+音频+字节增量且 remoteUfrag 匹配 offer_ufrag、同一 PC/Track 保持）、凭证损坏负例子进程非零退出，依赖主控 round7b 门禁日志与 basetemp 原始 `ac005_relay_evidence.json`。
- AC-006：`re_verified`。reviewer 查验 `auth/service.py`、`auth_router.py` 与 `internal_gateway.py`，独立重跑 `test_auth_api.py` 与 `test_auth_service.py` 验证自动化独立 Bearer Token、无 Origin 允许、Cookie 不能代替自动化凭证、撤销立即生效、越权拒绝、审计无明文泄漏。
- AC-007：`trust_prior`。真实无头 Chrome 官方客户端 STOP_VIDEO/START_VIDEO 暂停与恢复、前后台帧率表现、捕获暂停与关键帧增量、Gateway 端点准确反映上报值，依赖主控 round7b 门禁日志与 basetemp 原始 `ac007_visibility_evidence.json`。

coverage = 4 / 7 = 57.1%
建议合并前人工抽查 trust_prior 项。

verdict: PASS
