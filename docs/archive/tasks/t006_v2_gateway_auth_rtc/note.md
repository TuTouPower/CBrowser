---
tid: "t006"
slug: "v2_gateway_auth_rtc"
title: "实现认证信令 Gateway 与独立 RTC 凭证轮换"
status: "done"
branch: "t006_v2_gateway_auth_rtc"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "c33e55f77cb221510396628e792a08b905b2ebe0"
depends_on: "t005"
conflicts_with: ""
note: ""
---

# Task 过程总账

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

#### 2026-10-30T10:23:55+08:00 开工、lane 拆分与整合

- 时间更正：原标题误记 21:10，按 dispatch ledger 的 start/reserve 时间更正。

- identity：attempt1 / execution_id=79fa47d2f34e42f8b31f43ceb8cb52a9 / owner_id=claude_v2_14b38abc09f2；base/diff_anchor=c33e55f（t005 合入后 main）。UNVERIFIED-SPIKE 改写为已验证结论（前置协议与 d003/d007/d008/d009/d010/d012/d018/d019、argon2id 实测），strict preflight PASS。

- 主控预置协议（先 RED 后 GREEN）：AgentAction.RTC_CONFIG、注册字段 selkies_version/runtime_state/config_version、AgentHeartbeatPayload、IceServer/RtcConfigPayload（凭证 SecretStr）；重新导出 schemas/stream/agent_protocol.json。

- 实现 lane（OpenCode cpa/gemini-3.8-flash --variant high，各自独立 worktree，增量经 patch 合入）：auth（API 鉴权/CSRF/Origin/自动化凭证/Gateway 内部授权/0002 迁移，现有 12 个启动 API 的测试仅加登录夹具、断言未改）；gateway（aiohttp Gateway、注册表、每 Viewer 隧道、活动聚合、Supervisor 控制端点、rtc_config 与轮换）；agent（注册字段、10 秒健康、1/2/4/8/16/30 退避、rtc_config 应用）；gwfix（主控审查后追加）。

- 主控审查与修正：

    - agent lane 把 schema 测试的 jsonschema 导入改成 importorskip（缺依赖会静默跳过），已恢复原样；`resolve_selkies_version` 原允许环境变量覆盖并吞异常，改为只读安装元数据（RED：环境变量 9.9.9 被接受）；补心跳默认 10 秒断言。
    - 新 Stream 入口要求 `CBROWSER_CONFIG_VERSION`，Supervisor 未传：新 Stream 镜像下容器图真实 RED「Runtime start failed」，Supervisor 改为从 Browser config-version 标签下发后 GREEN。
    - gateway 审查发现 4 项并派 gwfix 修正（均先 RED 后 GREEN）：Stream 侧 TURN 原用全局 `turn:coturn` 默认值，改为 Agent 注册上报 Supervisor 下发的 coturn 实际地址（ADR 010）；Agent 回传 tunnel/action 包核对 Profile/实例/session 与 Viewer 归属，阻断跨 Profile 投递；同实例重注册关闭旧 session 的 Viewer；新代凭证生成时同步给 Agent，ICE restart 载荷更新 Agent active 配置；控制帧异常改为记录 warning。
    - auth：未配置 `CBROWSER_ALLOWED_ORIGINS` 原为空列表静默 403，改为启动失败（先 RED 后 GREEN）。

- 环境事件：约 13:00–19:46 OrbStack Docker 引擎无响应、主机负载 100–135（kkmail 容器与宿主进程），期间 SQLite busy_timeout 计时用例两个方向均失败；负载恢复后合并态全套通过，判定为环境抖动。用户授权重启 OrbStack，但引擎已自行恢复，未执行。

- 合并态验证（Docker E2E 前）：unit+integration 294 passed、contract 169、legacy 384、Ruff 无新增问题、diff --check 通过。

#### 2026-10-30T20:46:00+08:00 计划修订 9.3：AC-007 改写，活动聚合待移除

- 用户批准按开源调研复核修订计划：可见性只走 Selkies 原生每 Peer STOP_VIDEO/START_VIDEO（源码 webrtc_mode.py handle_video_consumer_active），Gateway 不采集页面可见性/活动。AC-007 已就地改写为新语义；范围同步。
- `docs/v2_architecture_plan.md` 按用户要求从 main 原样同步进本 WT（与 main 修订提交内容逐字节一致，integrate 时双方同改无冲突），使实施与 review 以修订后 9.3 为准。
- E2E lane 已 retire（worktree 干净、无交付；证据备份 `.scratch/v2_orchestration/retired_worktrees/CBrowser_t006_e2e/`）。
- 恢复实施时待办（尚未改代码）：删除 `gateway/activity.py` 与页面 `cbrowser: activity` 控制帧、Gateway→Agent `VISIBILITY_UPDATE` 下发与 Agent 处理分支、`AgentAction.VISIBILITY_UPDATE` 及 schema 重导出、`test_gateway_activity.py` 整项删除并说明；AgentHeartbeatPayload 增加未暂停视频 consumer 数与捕获状态；Gateway 内部 visibility 端点改读 Agent 最近上报值（Supervisor gateway_client 契约不变）；同步改写 `docs/blueprint/gateway.md`「连接活动表与聚合需求」、`docs/specs/webrtc_remote_display.md` 第23行、`docs/blueprint/stream_runtime.md`「共享策略由认证 Gateway 消息驱动」。先 RED 后 GREEN。

#### 2026-10-30T21:02:22+08:00 会话接管与计划修订 9.3 实施

- 接管：原主控会话（owner claude_v2_14b38abc09f2）已被用户中断并清空，无存活子 agent；`attempt claim --replace-owner claude_v2_14b38abc09f2 --confirm-stopped` 后 owner_id=claude_v2_6e1f7a8e7a46（20:50:19）。WT diff 与 20:46 快照 sha256 一致（8a6605a7…）。
- 9.3 实施（先 RED 8 项失败、后 GREEN；`.scratch/t006_93/red.log`、`green_unit_integration.log` 294 passed）：
    - 删除 `gateway/activity.py`、页面 `cbrowser: activity` 处理、Gateway→Agent `VISIBILITY_UPDATE` 下发与空闲修剪、Agent 对应分支、`AgentAction.VISIBILITY_UPDATE` 与 `VisibilityUpdatePayload`；重导出 `schemas/stream/agent_protocol.json`。Gateway 的 Profile 连接列表改为从 viewer 表派生（轮换与 disconnect 使用）。
    - `AgentHeartbeatPayload` 新增必填 `unpaused_video_consumers`、`capture_running`（StrictBool）；值由仲裁器 `selkies_video_state()` 读取 Selkies `_display_consumers("primary")` 的 `video_paused` 与 pipeline `is_screen_capturing()`。Agent 注册后立即发首个心跳再每 10 秒一次——Supervisor 启动就绪以 visibility 端点 15 秒内由 503 转可用为准，不能等满一个周期。
    - Gateway 校验心跳载荷后才刷新存活并保存上报值；visibility 端点返回 `has_foreground_viewers=unpaused>0` 及两个原值，未上报返回 503（未知不猜 False），新注册不继承旧值；Supervisor gateway_client 契约不变。
- 测试处置（旧语义失效，整项删除并另写新测试）：
    - `tests/unit/test_gateway_activity.py` 整个文件：测 Gateway 15 秒活动超时聚合，机制已废弃。
    - t004 遗留 `test_stream_protocol_schema.py::test_stream_schema_accepts_registration_ack_and_tunnel`、`test_stream_transport_hardening.py::test_protocol_strict_wire_envelopes`：样例与断言依赖已删的 `visibility_update` / `VisibilityUpdatePayload`；新测试保留其余断言并断言 visibility_update 被 schema/模型拒绝。`test_real_ws_gateway_and_worker_generation` 的伪造 visibility 包负例语义仍成立，原样保留（仅删除模块级失效 import）。
    - t004 遗留 `tests/e2e/test_stream_runtime_e2e.py` 中经测试 Gateway 发 `visibility_update` 的可见性段整段删除（原文备份 `.scratch/t006_93/removed_stream_e2e_visibility_block.txt`）：该刺激在生产中已不存在；新语义由 t006 Gateway E2E 以真实 Chrome 页面隐藏→官方 STOP_VIDEO 覆盖（AC-007）。
    - t006 自写未提交用例：`test_supervisor_control_authentication_and_errors`（无上报即 False）、`test_foreground_aggregation_with_freezing_background_viewer`、`test_heartbeat_payload_is_strict`、`test_viewer_control_frame_error_logs_warning_and_not_forwarded`（monkeypatch ActivityTracker）整项删除；新增上报值/503/409/篡改心跳/新实例不继承、页面帧不改变状态且不产生控制包、restart answer 异常只记类型、协议拒绝 visibility_update、首个心跳即时且随 Selkies 暂停状态变化等用例。
- 主控审查顺带修正 auth lane 遗留：`test_supervisor_recovery_e2e.py` 两个用例引用未定义的 `stack`（运行即 NameError，Ruff F821；此前未跑 Docker E2E 未暴露）改为 `real_api_and_sup`，并恢复被误改的注释；`test_supervisor_core_e2e.py` 登录夹具加载块移到 import 之后（E402）；两文件 ruff format。Ruff E,F,W,I 回到 main 基线 16 项。

#### 2026-10-30T21:16:31+08:00 主控审查：ICE restart 提交须经 Agent 确认

- 缺陷：Gateway 把“answer 已转发给 Agent”当作该连接迁移成功并提交本代（日志 `Generation N officially committed for profile`），而 Selkies `setRemoteDescription` 以 `ensure_future(__connect())` 在后台做连通性检查，新代失败时 Gateway 无从得知，AC-004“已验证 ICE restart、失败显式记录并重试”不成立。
- RED：`tests/integration/test_gateway_rotation.py` 新增 2 项（未确认即提交；answer 后 Agent 报错未按本代重试，实际转去下一代），`.scratch/t006_commit/red_gateway.log` 2 failed；真实 SDK 新测试 `tests/e2e/test_stream_ice_commit_e2e.py` 在修复前源码构建的 Stream 镜像 sha256:34ec1651… 上 ImportError（`red_sdk.log`）。
- GREEN：`ice_transport.wait_restart_commit()` 按 transport 的 restart_pending/committed_generation/state 有界等待（主 transport 定位抽成 `_main_transport` 复用）；Agent 设置 answer 后在后台任务中等待最长 20 秒，成功发新动作 `ice_restart_committed`（带 Gateway 代号），失败发 `error`，并在 offer 生成失败时也回报 error；Gateway 收到同代确认才记迁移，错误或 30 秒未确认退避重试。unit+integration 296 passed（`green_unit_integration.log`）；修复后 Stream 镜像 sha256:a624db24… 上真实 SDK 提交测试与 t004 ICE 失败回归 8 项通过；直接运行探针原始 JSON：健康代 2 提交，错误 ice-pwd 的代 3 `ICE failed` 后等待抛 ConnectionError、提交代保持 2。
- 夹具教训：失败注入不能关闭对端 PC（SCTP/DTLS 连带关闭本端），改为篡改 answer 的 ice-pwd。

#### 2026-10-31T06:16:13+08:00 E2E lane 揭示：Gateway 下发的 Stream 侧 TURN 从未进入 Selkies

- 缺陷（E2E lane relay-only 实测发现，主控核对 Selkies 2.1.0 源码确认）：`StreamAgent.apply_rtc_config` 以 `update_rtc_config(wire_servers)` 单参数、dict 列表调用，而 `selkies.webrtc_engine.RTCApp.update_rtc_config(stun_servers, turn_servers)` 需要两组 URL 字符串（TURN 为 `turn://user:pass@host:port?query`），TypeError 被 `except Exception` 吞成 warning；另外 `rtc_app` 在 `WebRTCService.initialize_components()` 才创建，早到的 RTC_CONFIG 会因 `rtc_app` 为 None 被静默跳过。结果 relay-only 下新 PeerConnection 无 Stream 侧 TURN，初始连接卡在 checking。主机无 Selkies，单元/集成测试未覆盖。
- RED：真实 SDK 测试 `tests/e2e/test_stream_rtc_config_e2e.py`（Stream 镜像内真实 `RTCApp`，无 mock）在修复前镜像 sha256:a624db24… 上失败（`.scratch/t006_rtcfix/red_sdk.log`）。lane 写的 Mock RTCApp 复现用例不采纳，合入时删除。
- GREEN：`RtcConfigPayload.selkies_server_urls()` 生成 Selkies 期望的 STUN/TURN URL（凭证百分号编码）；Agent 以正确签名推送，去掉吞异常（RTC_CONFIG 处理分离“载荷非法”与“应用失败”两类日志）；Policy 服务子类在 `initialize_components()` 后调用 Agent 绑定的 `rtc_ready_hook` 补推。修复后镜像 sha256:e3bb980a… 上真实 SDK 2 passed，原始 JSON 显示 `get_rtc_config()` 含 `turn:10.0.0.5:3478?transport=udp`、带冒号用户名与含 `/=` 凭证；unit+integration 296 passed（`.scratch/t006_rtcfix/green_unit_integration.log`）。

#### 2026-10-31T07:23:17+08:00 主控审查：未建立的 PeerConnection 不得执行 ICE restart

- 风险：Gateway 按代到期对 Profile 全部 Viewer 发起重启；Viewer 恰在初始协商中（服务端 offer 尚未得到 answer，或首轮 ICE 未连通）时，Agent 会在该 PC 上再生成 restart offer，替换掉初始协商，初始连接失败。E2E lane 在短轮换参数下观察到初始 relay 连接偶发失败且同期 Gateway 已发起重启，与此吻合。
- RED→GREEN：`tests/unit/test_stream_agent_lifecycle.py::test_ice_restart_on_unconnected_peer_is_refused_for_retry`（RED：当前会尝试生成 offer，回报 `ice_restart_offer_failed`；`.scratch/t006_restart_guard/red.log`）。修复：`_trigger_ice_restart` 仅在 `signalingState == "stable"` 且 `iceConnectionState` 为 connected/completed 时执行，否则向 Gateway 回报 `error: peer_not_ready`，由 Gateway 退避重试。unit+integration 297 passed。真实 Chrome 路径由 Gateway E2E AC-005 复跑验证。

#### 2026-10-31T07:58:06+08:00 E2E lane 合入与主控加强

- E2E lane `t006_e2e2`（session ses_e73140c3bffezl2ty40n3Td8YL，r1–r6）交付 `tests/e2e/test_gateway_ac00{1,3,5,7}_*_e2e.py` 与 `tests/fixtures/gateway_probe/`；lane 已 retire，证据备份 `.scratch/v2_orchestration/retired_worktrees/CBrowser_t006_e2e2/`。lane 自报全部通过，主控不采信，以门禁复跑为准。
- 用户 2026-10-31 要求测试不得弹出浏览器窗口：全部 Gateway E2E 为无头官方 Chrome。无头 Chrome 156 切标签/最小化不改变 `document.visibilityState`（主控实测），AC-007 改为页面内覆盖可见性并派发 `visibilitychange`，由官方客户端发 STOP_VIDEO/START_VIDEO；“浏览器真实标签切换发出事件”不在本 task 重证（沿用 d013/s005 headful 实证）。
- AC-005 负例改为新代客户端 TURN 凭证在测试页内置坏，coturn 401 拒绝、旧代继续出帧，新代不得提交（原计划的 coturn total-quota 方案未采用）；`test_ac005_negative_turn_failure_exit_code` 以子进程运行负例并断言非零退出。
- 主控加强（合入后）：AC-007 的 STOP/START 钩子与恢复日志只取动作之后的新增日志并要求精确行，恢复必须 `keyFramesDecoded` 增加；AC-005 coturn 拒绝证据只认 401，新代音频能量增量须 > 0；正式 Gateway 镜像改由 `CBROWSER_GATEWAY_IMAGE` 提供（与 Supervisor 用 Gateway 夹具镜像区分）；修 Ruff。Gateway/coturn 测试容器保留 `com.cbrowser.managed-by=supervisor` 标签，这是 Supervisor 基础设施容器校验（`_validate_infra_container`）的契约要求，与 t005 容器图测试一致。
- testing.md 新增「Gateway 阶段验证」章节。

#### 2026-10-31T08:27:44+08:00 门禁 round1–5 与修正

- 环境：本机 BuildKit 解析 Docker Hub（`docker/dockerfile:1.4` 前端、`debian:bookworm-slim` 元数据）直连 IPv6 失败（round1–4 构建失败），守护进程 `docker pull` 走 OrbStack 代理可用；预拉前端与基础镜像后构建恢复，门禁脚本 build 加有限退避重试。python:3.12-slim-bookworm 因此更新到 e697c818…，Browser/Stream 全量重建。
- round5（全部当前源镜像）：contract 169、legacy 384、unit 251、integration 46、runtime_e2e 13、启动恢复 2、容器图等 8、网络策略 5、资源 5、Ruff/format/md/diff 通过；失败与处置：
    - stream_e2e 1 failed：t004 多页 E2E 启动 Stream 未传 t006 新增的必需环境（`CBROWSER_CONFIG_VERSION`、`SELKIES_TURN_HOST/PORT`），Agent 配置校验失败不注册。只补三项启动输入、断言不变。
    - sup_lifecycle 6 failed：t006 起 Stream 必须有 coturn 地址，而 Supervisor 只在 gateway+coturn 成对配置时下发，t005 生命周期测试不配基础设施容器；另一用例漏加登录头（401）。派 Gemini lane `t006_supfix` 修复（coturn 必需、gateway 基础设施可选、缺 coturn 启动前显式失败；测试提供真实 coturn 容器）。
    - gateway_e2e 5 failed：资源校验清单含随 Python 补丁版本变化的 `__pycache__/*.pyc`，且夹具以绝对路径引用被 gitignore 的 scratch 清单。清单（排除字节码，2007 项）移入 `tests/fixtures/gateway_probe/selkies_web_sha256.txt`，缺失文件改为失败；离线提取复核全部一致。
    - schema_openapi：导出命令缺 `argon2-cffi`。补依赖（testing.md 与门禁）后真实导出与入库文件一致。主控在 Docker 门禁前做的“OpenAPI 无漂移”预检因同一原因导出失败、输出被丢弃而无效，以本次为准。

#### 2026-10-31T11:12:19+08:00 supfix lane 合入（Supervisor 生命周期回归）

- Gemini lane `t006_supfix`（session ses_e70a63f01ffeR7qLMV1A8vV5Pl，已 retire，证据 `.scratch/v2_orchestration/retired_worktrees/CBrowser_t006_supfix/`）：`SupervisorCore` 去掉 gateway/coturn 成对约束，coturn 为启动 Runtime 的必需基础设施，未配置时在分配端口、建网络之前抛 `DockerSandboxError` 并走既有失败上报；`attach_profile_infrastructure` 允许仅 coturn（Stream 仍用配置的 gateway_url）。RED 4 failed → GREEN 4 passed（`tests/unit/test_supervisor_infrastructure_config.py`）；t005 生命周期 E2E 补真实 coturn 容器与漏掉的登录头，未改任何断言；`SupervisorGatewayFixture` 改为在独立线程事件循环中运行，避免子进程同步等待阻塞夹具。lane 自报 unit+integration 301、生命周期 6 passed，以主控门禁复跑为准。
- 主控复核：回退 lane 把 `disconnect_viewers` 捕获范围由 `TransportError` 放宽为 `RequestError` 的计划外改动（超时本已属 TransportError）；格式化 3 个文件。各测试文件内 coturn 启动代码重复（minor，留评审）。

#### 2026-10-31T13:04:33+08:00 relay lane 合入（relay-only 初始连接双端 relay）

- 主控核对门禁 round6 原始证据发现：relay-only 下第 1 代初始连接选中对为 prflx↔srflx（192.168.172.4:30000），只有重启后的新代 relay↔relay；lane 测试初始判据只要求“连通且出帧”而掩盖。原因：Stream 侧 rtc_config 不携带仅 relay 意图；`SELKIES_TURN_HOST` 也被 Selkies 自身读取并启动其 RTC 配置/监控；测试页适配层未在官方 `setConfiguration` 后保持 Gateway 策略。
- Gemini lane `t006_relay`（已 retire，证据 `.scratch/v2_orchestration/retired_worktrees/CBrowser_t006_relay/`）：`RtcGeneration/RtcConfigPayload.relay_only`（relay-only 模式下 Gateway 首发与每代下发均置真）；`ice_transport.set_relay_only` 使此后新建 PeerConnection 只收集/使用 relay 候选，无 relay 候选显式失败；真实 SDK `test_gateway_rtc_config_relay_only_restricts_candidates`；测试页包装 `setConfiguration` 保持 Gateway 配置；AC-005 初始判据恢复双端 relay；证据目录改为 pytest 临时目录。RED 6 failed → GREEN。lane 自报 Gateway E2E 5 passed、第 1 代 relay↔relay。
- 主控复核清理：lane 在 agent.py 三处（含吞异常的 `mon_hmac_turn.stop()`）关闭 Selkies 自带 RTC 监控，改为 Policy 服务子类在 `initialize_components()` 末尾清空 `monitoring_utils_used` 并覆盖 `mon_rtc_config` 忽略监控回写；去掉 `getattr(TransportPolicy, "RELAY", "relay")` 与 `inspect.isawaitable` 兼容写法；还原被 `ruff format` 误改的 `tests/fixtures/supervisor_recovery_probe/gateway_contract.md`。整项删除 lane 新写的 `tests/unit/test_stream_ice_transport.py::test_generation_ice_transport_relay_only_initial_pc`：它以 MagicMock 代替 SDK 构造 `GenerationIceTransport`，并迫使生产代码保留兼容占位写法；同一行为由 Stream 镜像内真实 SDK 测试 `tests/e2e/test_stream_rtc_config_e2e.py::test_gateway_rtc_config_relay_only_restricts_candidates` 证明。

#### 2026-10-31T13:32:31+08:00 门禁 round7 与 AC 实证打勾

- round7（`.scratch/t006_gates/round7/`，全部当前源镜像，`images.env` 记录 ID）：contract 169、legacy 384、unit+integration、runtime_e2e 13、stream_e2e（含真实 SDK 提交/RTC 配置/relay-only 候选）、生命周期 6、启动恢复 2、容器图等 8、网络策略 5、资源 5、schema（openapi/stream/supervisor 导出一致）、Ruff（E,F,W,I 仍为 main 基线 16 项）/format/md/diff 通过；gateway_e2e 4 passed、1 failed：负例子进程用例写死已退役 relay lane 的 basetemp 路径。修正为 `tmp_path`，并去掉 `topology.py` 指向主仓 scratch 的缓存路径默认值（改为必须由环境提供）；删除测试在仓库外重建的游离目录。生产代码未变，沿用 round7 镜像复跑 Gateway E2E：5 passed（`.scratch/t006_gates/round7b/gateway_e2e.log`）。unit+integration 305 passed。
- AC 证据（主控亲自核对原始 JSON / 日志）：
    - AC-001：`tests/e2e/test_gateway_ac001_auth_e2e.py`（Caddy HTTPS + 无头 Chrome 真实登录：`cbrowser_session` HttpOnly/Secure/SameSite=Strict；缺 CSRF 写请求 403；未登录 401、错误 Origin 403、未知 Profile 403 均握手失败）；`tests/integration/test_auth_api.py`、`tests/unit/test_auth_service.py`（Argon2id 引导、限速、会话与 CSRF）。“master token 不返回前端”：当前 Stream 未配置任何 Selkies token，属空满足，见 p004（t007 前定案）。
    - AC-002：`tests/unit/test_stream_agent_lifecycle.py`（注册字段、注册后即时首个心跳与 10 秒节奏、1/2/4/8/16/30 退避）；`tests/integration/test_gateway_signaling.py`（过期实例不覆盖、未就绪拒绝、心跳超时驱逐）；AC-003 E2E 中 Gateway SIGKILL 后 Stream 日志 1s/2s 退避重注册。
    - AC-003：`tests/e2e/test_gateway_ac003_media_e2e.py`（round6 证据：两页 client_tab_id 不同、各 +45 帧/2s 与非零音频、并发输入远端 "12"、关页 A 后页 B +60 帧、Gateway SIGKILL 后 Browser PID 40/start_ticks 不变、重连后再解码；选中对远端为 Stream UDP mux 127.0.0.1:30000，非 Gateway）。
    - AC-004：`tests/unit/test_rtc_config.py`；`tests/integration/test_gateway_rotation.py`（新连接取当前代、Agent 确认接管才提交、answer 后报错按本代退避重试）；真实 SDK `test_stream_ice_commit_e2e.py`、`test_stream_rtc_config_e2e.py`；AC-005 E2E 两次轮换。
    - AC-005：`tests/e2e/test_gateway_ac005_relay_e2e.py`（round7b：第 1 代 relay↔relay 127.0.0.1:50028；第 2、3 代 offer ufrag 与选中对一致、relay↔relay、同一 PC/Track、+60 帧、音频增量 0.0203/0.0204；负例子进程：新代客户端凭证 coturn 401、Gateway 未提交该代且退避、旧代仍出帧，子进程非零退出）。
    - AC-006：`tests/integration/test_auth_api.py`（自动化 token 需登录+CSRF 创建、明文只返回一次、内部授权无 Origin、会话 Cookie 不能冒充、撤销立即失效、越权 Profile 拒绝、审计不含明文）。真实 CDP 代理入口属 t008 AC-002，本 task 交付凭证层。
    - AC-007：`tests/e2e/test_gateway_ac007_visibility_e2e.py`（一前台一后台：后台 0 帧、前台 60 帧/2s，端点 unpaused=1/capture=true；全部后台：两页 0 帧，端点 0/false；恢复：关键帧增加、`set_framerate(8.0) first, then resume`、端点恢复；注入 activity 帧端点不变、日志无 visibility_update）；`tests/integration/test_gateway_control.py`、单元心跳测试。可见性在无头 Chrome 中以页面内覆盖触发（用户要求不弹窗），真实标签切换发出事件沿用 d013/s005。
- 豁免：公网 WebRTC/TURN 穿透与原生 Linux x86_64 为 NOT_RUN / USER_WAIVED。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-10-31T13:40:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t006_code_f001|minor|遗留|Gateway 解析允许 Origin 未去尾斜杠，仅在配置带尾斜杠时误拒；改动交付会使已完成评审与黑盒失效|p005|
|t006_code_f002|minor|遗留|轮换窗口期新连接多一次冗余 ICE restart，功能正确|p005|
|t006_code_f003|minor|遗留|断连时提交等待任务最长 20 秒后自行结束，stop 时统一取消|p005|
|t006_code_f004|minor|遗留|handle_agent_register 复杂度高，拆分属重构|p005|
|t006_test_f001|minor|遗留|四个 Supervisor E2E 内联重复 coturn 启动代码|p005|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（AC-001 的 master token 条款为空满足，见 p004；AC-006 的真实 CDP 代理入口属 t008 AC-002）
- 测试：主控门禁 round7（`.scratch/t006_gates/round7/`）+ round7b Gateway E2E 复跑全部通过：contract 169、legacy 384、unit+integration 305、runtime 13、stream 14（含真实 SDK 提交/RTC 配置/relay-only）、Supervisor 生命周期 6、启动恢复 2、容器图等 8、网络策略 5、资源 5、Gateway E2E 5；schema 导出一致；Ruff 保持 main 基线 16 项。
- 黑盒：独立 Gemini 黑盒（session 见 `.scratch/v2_orchestration/t006_blackbox_r1.jsonl`），在逐字节等同候选（98 文件 SHA 一致）的验证 worktree 自建全部镜像，文档门禁同数通过，7 条 AC 均有自写探针正负例（含 Gateway SIGKILL 退避 1.0/2.0 秒、过期实例 1008、未就绪 503 对照、提交顺序、自动化凭证撤销/越权/审计），无残留资源；报告备份 `.scratch/v2_orchestration/retired_worktrees/CBrowser_t006_blackbox/`。
- review：Full Round 1 code/test 两路 PASS（reviewed_scope 8a0b74f272c14c47），5 个 minor 遗留 p005，零 blocking。
- AC 判定：见 `task.md` 行内打勾；证据清单见本文件「门禁 round7 与 AC 实证打勾」。

### 结果摘要

- 交付认证信令 Gateway（Agent 注册表、每 Viewer 隧道、Supervisor 控制端点、按 API 绑定判定实例）、用户鉴权（Argon2id、HttpOnly/Secure/SameSite=Strict 会话、CSRF、Origin）、自动化凭证基础、独立 RTC 配置与 TURN 轮换（Agent 确认接管才提交、失败退避）、计划修订 9.3（Gateway 不采集可见性，Agent 心跳上报 Selkies 视频状态）、relay-only 初始连接双端 relay。
- 审查发现并修复的生产缺陷：answer 转发即提交（d021）、Stream 侧 TURN 从未进入 Selkies 且被吞异常（d022）、对未建立 PC 发起重启、relay-only 初始连接非 relay、Supervisor 缺 coturn 时启动必然退出的 Stream。
- 遗留：p003（API→Supervisor 启停协调）、p004（Selkies 每 Profile token）、p005（评审 minor）。豁免：公网 WebRTC/TURN 与原生 Linux x86_64 为 NOT_RUN / USER_WAIVED；容量/P95/8 小时/1000 次输入属 t009。
- 用户要求：测试不得弹出浏览器窗口（全部无头，见 d023）；实现交 Gemini 子代理，主控派发与复核。

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
