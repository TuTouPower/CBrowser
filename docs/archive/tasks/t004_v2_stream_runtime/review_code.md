# Task review t004（reviewer_focus: 代码）

- task：`t004_v2_stream_runtime`
- spec：`docs/tasks/t004_v2_stream_runtime/task.md`
- diff_anchor：`8ff9fd237dcd8e6d1093f3de7503f5b7f599b3e6`
- target：`git -C '/Users/karson/kar/code/CBrowser_t004' diff 8ff9fd237dcd8e6d1093f3de7503f5b7f599b3e6`
- round：Round 1
- reviewed_at：2026-10-29T13:09:11+08:00
- metadata_errata：前稿初始时间戳记录为未校准时间 2026-10-29T12:00:00+08:00，现按真实系统时间勘误。

reviewed_scope: 740fe6627e7735db

## Findings

### t004_code_f001 - tests/e2e/test_stream_runtime_e2e.py 单文件体积达 1553 行，承载多端全链路端到端逻辑

- 严重度：minor
- 锚点：代码维护性与单文件规模启发式
- 位置：`tests/e2e/test_stream_runtime_e2e.py:1`
- 问题：`test_stream_runtime_e2e.py` 物理行数达到 1553 行（超出了测试源码 600 行 minor 建议阈值及 1200 行上限提示）。单用例 `test_stream_runtime_multi_viewer_e2e`（约 1140 行）一次性串联了 Dual Chrome 初始化、WebRTC 媒体解码断言、复制标签页重映射、TURN Relay 轮换、Supervisor 帧率配额与静止/动态检测、多视口几何锁定、原生中文 IME 输入验证、剪贴板不变性探针、音频独立静音、首页面关闭与 Agent 断网重连/容器挂起隔离断言。
- 建议：当前全链路 E2E 具有极高的高保真端到端闭环验证价值，且未发生逻辑分歧或缺陷。后续演进时建议将 Gateway 模拟桩、CDP/WebRTC 脚本采集器与各项子场景断言抽取为独立 helper 或按 AC 拆解独立 scenario，以提升测试维护性与排错效率。

### t004_code_f002 - src/backend/cbrowser/stream_agent/agent.py 物理行数达 910 行

- 严重度：minor
- 锚点：代码维护性与单文件规模启发式
- 位置：`src/backend/cbrowser/stream_agent/agent.py:1`
- 问题：`agent.py` 物理行数达到 910 行，略微超过实现源码 800 行建议上限。该文件同时包含了 StreamAgent 核心协调逻辑、Gateway 双向 WebSocket 隧道中继、上游 Worker/Reader 协程生命周期管理、ICE Restart 编排分发以及 CLI 启动入口与 Selkies 猴子补丁注入。
- 建议：后续架构迭代中可考虑将 CLI 入口 / `selkies` monkey-patching 独立拆分至 `cli.py` 或 `launcher.py`，使 `agent.py` 专职处理 Gateway 隧道与协程生命周期。

## 七视角体检

1. **安全审视**：
    - 源码锚点：`src/backend/cbrowser/stream_agent/boundary.py:17-72`（`verify_stream_runtime_boundaries`）、`config.py:24-140`（Pydantic SecretStr 与 URL/Token 校验）、`agent.py:86-97`（`_sanitize_packet` 过滤 token/secret）、`policy.py:19-42`（`FORBIDDEN_PEER_PREFIXES` 与 `DISALLOWED_SETTINGS_KEYS` 客户端消息脱敏拦截）。
    - 结论：合规。Docker 镜像降权 `1000:1000` 运行且挂载点严格限定于 X11/Pulse/Secret，运行时主动检测并阻断 Docker Socket 及 Profile 数据暴露；Token 使用 SecretStr 并禁止在 URL / 日志中打印明文凭证；客户端控制信令被强行剥离帧率与几何修改指令。
2. **实现正确性**：
    - 源码锚点：`src/backend/cbrowser/stream_agent/ice_transport.py:126-390`（`GenerationIceTransport` 多代状态机与旧连接注销）、`src/backend/cbrowser/stream_agent/policy.py:97-280`（`LiveCapturePolicyAgent.reconcile_capture_state` 状态流转）、`src/backend/cbrowser/stream_agent/x11_keymap.py:33-118`（XKB named spares 动态刷新与 text_room 修正）。
    - 结论：合规。ICE Restart 严格维护 generation 递增并在新连接 commit 后单向 retire 旧连接，旧 socket 不泄漏且不再接受写入；捕获状态机在恢复时严格保证先设 8 FPS 再执行 resume 和 IDR 请求；X11 键盘映射对活跃 Chromium 广播刷新，避免组合字符丢失。
3. **契约·类型·Breaking**：
    - 源码锚点：`src/backend/cbrowser/stream_agent/protocol.py:37-269`（`GatewayTunnelEnvelope`, `GatewayControlEnvelope`, `AgentRegisterPayload`）、`schemas/stream/agent_protocol.json`、`scripts/export_stream_protocol.py`。
    - 结论：合规。全部信令与控制报文通过 Pydantic 显式定义与模式导出，模型配置 `extra="forbid"` 防止未定义字段注入；各字段具备严格的正则或数值范围约束（如 `udp_mux_port` 在 `[30000, 30991]`、fps 在 `[8.0, 30.0]`）。
4. **性能与资源**：
    - 源码锚点：`src/backend/cbrowser/stream_agent/agent.py:38-42`（队列与帧体积阈值 `MAX_PAYLOAD_SIZE`, `QUEUE_MAX_SIZE=100`）、`agent.py:532-618`（上游 worker 队列消费与背压保护）、`policy.py:44`（`MAX_HISTORY_SIZE=500` 环形队列防内存膨胀）。
    - 结论：合规。各 Viewer 独立 worker 协程配合有界队列，队列溢出时主动断开并清理，避免无节制内存占用；静止画面回落 8 FPS，隐藏/全断开时主动暂停采集管道，显著降低宿主 CPU 与 GPU 编码开销。
5. **架构与可维护性**：
    - 源码锚点：`src/backend/cbrowser/stream_agent/agent.py`、`policy.py`、`ice_transport.py`、`x11_keymap.py`、`boundary.py`。
    - 结论：合规（伴随 2 项 minor 提示）。模块按安全边界、信令中继、捕获策略与底层 ICE 传输做清晰分层；`agent.py` 与 `test_stream_runtime_e2e.py` 代码行数偏多已通过 f001、f002 标为 minor 建议，无架构反模式或隐藏循环依赖。
6. **健壮性与可观测**：
    - 源码锚点：`src/backend/cbrowser/stream_agent/agent.py:45-66`（`ISO8601Formatter` 标准化日志时间）、`agent.py:270-300`（Gateway 断线指数退避与无限重连保护）、`agent.py:802-815`（优雅停机与 Viewer 资源 drain）。
    - 结论：合规。StreamAgent 自有业务日志（通过 ISO8601Formatter 配置）使用带时区 ISO 8601 输出；底层 Selkies/GStreamer Native C 库输出保留默认前缀（日志格式统一留待后续 t012 专项处理）；捕获异常均有清晰上下文记录与归因类型；Gateway 连接与内部 WS 通道中断均能安全释放已分配 worker/reader 任务，无未捕获协程泄漏。
7. **测试·文档·规格**：
    - 源码锚点：`docs/blueprint/stream_runtime.md`、`docs/specs/webrtc_remote_display.md`、`docs/findings/d017_native_xkb_named_spares.md`、`tests/unit/test_stream_*.py`（49项通过）、`tests/e2e/test_stream_*.py`。
    - 结论：合规。实现与 blueprint 契约保持完全一致；规格文档已同步更新为共享 8~30 FPS、动态多连接、端口池与 TURN 行为；测试覆盖协议校验、策略状态机、底层 ICE 注入以及真实双页面 E2E 验证。

## 结论

- 前轮 finding 复核：无（Round 1 首轮审阅）
- 本轮新发现：2 条（均为 minor 架构维护性提示，无 blocking finding）
- 未进表的提示：
    - 文件过大提示：
        - `tests/e2e/test_stream_runtime_e2e.py`（1553 行）：测试源码超过 1200 行，已在 f001 记录说明；
        - `src/backend/cbrowser/stream_agent/agent.py`（910 行）：实现源码超过 800 行，已在 f002 记录说明；
        - `src/backend/cbrowser/stream_agent/policy.py`（742 行）：超过 400 行 minor 建议拆分线，但未超 800 行上限，且职责聚焦在 CapturePolicy 与 Selkies WebRTC Service 包装，分支清晰；
        - `src/backend/cbrowser/stream_agent/ice_transport.py`（583 行）：超过 400 行 minor 建议拆分线，但未超 800 行上限，且属于针对 Selkies 2.1.0 ABI 的 GenerationIceTransport 专用底层适配器，内聚完整；
        - `schemas/stream/agent_protocol.json`（319 行）：属编译/导出生成的模式契约文件，按规则排除。
    - 圈复杂度提示：
        - `StreamAgent._handle_gateway_msg` 与 `LiveCapturePolicyAgent.reconcile_capture_state` CC 约在 10~14 之间，主要为协议消息分发与状态机多条件计算，均采用 early return 与清晰的卫语句，未引起可观测行为缺陷。
    - 契约区 drift 复核：`task.md` 契约区 drift 仅涉及 scope 中补全共享音频测试 fixture 说明（`audio_analyzer.py` 便携迁移）与 schema 导出器、以及实施后如实打勾 6 项 AC，无非预期的需求漂移或语义破坏。
- 总体判断：实现严格守住架构不变量与安全沙箱边界，AC 覆盖真实可靠，无 blocking finding。
- 系统性 follow-up：无

## AC 复验方式

- AC-001：`trust_prior`。依赖 `tests/e2e/test_stream_runtime_e2e.py` 执行产物 `active_media_phase.json` 与 Root 验证日志，两真实 Chrome 页面同时连接，视频解码与音频能量持续增长，首页面关闭后次页面不受影响。
- AC-002：`re_verified`。查验 `tests/e2e/test_stream_client_identity_e2e.py` 与 `tests/e2e/test_stream_runtime_e2e.py` 测试断言源码：`window.open` 复制标签页继承 `selkies_tab_id` 时，服务端及 client_shim 正确执行重映射与隔离，未踢出原页面，且视口变更不改变 1920x1080 远端分辨率。
- AC-003：`re_verified`。独立运行 49 项单元测试（含 `tests/unit/test_stream_capture_policy.py` 全部 12 项用例），验证静止降 8 FPS、动态提 30 FPS、后台隐藏不拖累前台、Supervisor 配额硬限以及不可由客户端消息越权修改策略。
- AC-004：`trust_prior`。依赖 `tests/e2e/test_stream_ice_relay_e2e.py`、`tests/fixtures/stream_probe/chrome_relay.py` 与独立的 coturn 4.6.3 relay 测试产物，验证同一 UDP mux 端口下跨 generation 平滑切换与 relay 隔离。
- AC-005：`trust_prior`。依赖 `tests/e2e/test_stream_runtime_e2e.py` 中的 `ime_cases` 8 次提交测试（2 个短文本及 6 组各 20 字批次，共 124 字符组合）、`tests/fixtures/stream_probe/clipboard_oracle.py` 原生 X11 剪贴板校验产物以及端到端测试 `tests/e2e/test_stream_x11_keymap_e2e.py`（真实 Xvfb/Stream 容器测试用例 `test_native_keymap_reuse_preserves_every_binding`），验证非剪贴板注入中文输入与独立静音。
- AC-006：`re_verified`。查验 `config/docker/stream_runtime/Dockerfile`、`entrypoint.sh`、`boundary.py` 与单元测试 `tests/unit/test_stream_transport_hardening.py::test_boundary_security_verification`，容器以 1000:1000 运行、只挂载 `/tmp/.X11-unix/X99`、`/tmp/.Xauthority` 与 `/pulse`，禁止 Docker socket 及浏览器 Profile 目录；查验 E2E 源码中 Docker pause/unpause 及 Agent 重连断言，验证不杀死浏览器进程。

coverage = 3 / 6 (50.0%)
建议合并前人工抽查 trust_prior 项

verdict: PASS
