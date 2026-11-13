# Task review t015（reviewer_focus: 代码）

- task：`t015_v2_media_link_simplification`
- spec：`docs/tasks/t015_v2_media_link_simplification/task.md`
- diff_anchor：`9ee4a1146be8e42bc552f1150beb8063582ab466`
- target：`git -C '<repo>_t015' diff 9ee4a1146be8e42bc552f1150beb8063582ab466`
- round：1
- reviewed_at：2026-11-03T00:01:36+08:00

reviewed_scope: b0ef991a0fb64f9c

## Findings

### t015_code_f001 - Agent 注册拒绝仍在 WebSocket 升级之后，不满足 AC-003

- 严重度：important
- 锚点：AC-003「Gateway 对 Viewer 接入与 Agent 注册的所有拒绝都在升级 WebSocket 与改动注册表之前完成」；对应 A8 修复说明要求拒绝发生在 `ws.prepare` 之前并返回可识别的 503。
- 位置：`src/backend/cbrowser/gateway/server.py:272-300`
- 问题：`handle_agent_register` 在 `server.py:273` 先执行 `await ws.prepare(request)`，之后才读取注册包、校验 HMAC（`:298`）、查询 API 实例绑定（`:303-316`）和校验载荷（`:285-291`）。因此无效 token、过期实例、非法 payload 都会先返回 101 Switching Protocols，再通过 Close 1008 拒绝。集成测试 `tests/integration/test_gateway_signaling.py:61-84` 也按此行为断言 `ws_connect` 成功后才收到 1008，等于把不符合 AC-003 的行为固化。我用现有 `GatewayHarness` 复现：无效 token 的 Agent 连接成功升级，随后收到 close_code 1008。注意 Viewer 路径已经正确前移，缺口只在 Agent 注册路径。
- 建议：在 `ws.prepare` 前完成可前移的校验。例如要求 `profile_id`/`runtime_instance_id` 从查询参数或签名注册票据获得，header token 预先校验后再升级；升级后再读取完整注册载荷并校验与查询参数一致。同步把拒绝测试改为 HTTP 4xx/503，而不是升级后的 1008。

### t015_code_f002 - 非法配额请求的非对象 JSON body 返回 500 而非 400

- 严重度：important
- 锚点：AC-005「非法配额请求返回 400 且不下发」
- 位置：`src/backend/cbrowser/gateway/server.py:155-160`（相同模式在 `:210-216` 的 disconnect 路由）
- 问题：`body = await request.json()` 之后直接调用 `body.get(...)`，未校验顶层是对象。客户端发送合法 JSON 但不是对象（如 `[]`、`"x"`、`null`）时触发 `AttributeError`，aiohttp 返回 500。实测 `POST /gateway/v1/internal/profiles/p1/quota` 带 `json=["not-an-object"]` 得到 500；这正是 AC-005 要求返回 400 的非法配额请求。另有 `runtime_instance_id` 为非字符串时不会走 400，而是被当作实例不匹配返回 409。`handle_supervisor_disconnect` 复用同一结构，也有同类 500。
- 建议：用 Pydantic 请求模型校验整个控制面 body（顶层对象、`runtime_instance_id` 字符串、quota 字段类型），校验失败统一返回 400；再进入 `SupervisorQuotaPayload` 和 registry 查找。disconnect 路由同步处理。

### t015_code_f003 - Web Locks 不可用诊断会被随后的 WS_CLOSE 覆盖为 signaling_failed

- 严重度：important
- 锚点：AC-008「Web Locks 不可用显示专门诊断」
- 位置：`src/frontend/src/features/browser-session/adapter.ts:199-201`、`:217-223`；`src/frontend/src/features/browser-session/useBrowserSession.ts:237-264`
- 问题：Web Locks 失败时 adapter 先 `postToParent({type:"CBROWSER_WEB_LOCKS_UNAVAILABLE"})`，紧接着 `ws.close(1008, "tab_identity_unavailable")`。同一个 adapter 还注册了 close 监听，会再发送 `CBROWSER_WS_CLOSE`（code=1008）；宿主在 `useBrowserSession.ts:240-264` 收到 1008 且 `wasConnectedRef.current` 为 false 时无条件执行 `setStage("signaling_failed")` 和 `setErrorMessage(signalingDisconnected...)`。真实浏览器中 close 事件一定在 postMessage 之后到达，因此专门诊断会被覆盖，最终显示「Signaling Failed」而非 Web Locks 诊断。新增测试只单独派发 `CBROWSER_WEB_LOCKS_UNAVAILABLE`，没有覆盖这条真实消息序列。
- 建议：Web Locks 失败后抑制该连接的 WS_CLOSE 失败处理（例如 set ref 后忽略后续 close），或让 adapter 用 1000 关闭并只依赖专门消息；同时补一条测试，按顺序派发 `CBROWSER_WEB_LOCKS_UNAVAILABLE` 与 `CBROWSER_WS_CLOSE(1008)`，断言最终 stage 仍为 `web_locks_unavailable`。

### t015_code_f004 - AuthorizationThrottle 的键集合在窗口内可无界增长

- 严重度：minor
- 锚点：行为缺陷（未认证请求可造成内存增长）；AC-005 的 Viewer 限流实现。
- 位置：`src/backend/cbrowser/gateway/registry.py:115-150`
- 问题：`AuthorizationThrottle._failures` 以 attacker 可控的 `profile_id` 为键；`record_failure` 只在 `len(self._failures) > 1024` 时清理「最后一次失败早于窗口」的条目。攻击者在 60 秒窗口内使用大量不同 `profile_id` 请求 `/stream/{profile_id}/signal`（Origin/限流检查在失败记录之前，cookie 可以缺失），每个新 profile 都会创建一个键，而窗口内的键都不会被清理，字典可随请求数无界增长。当前 `Bounded` docstring 与实际行为不符。
- 建议：给键空间设硬上限（LRU/定期全量清理），或在每次 `allow`/`record_failure` 时按窗口淘汰过期键；也可在限流键中只使用服务端已知的 profile。该问题不阻断本 task，但建议在本 task 或 follow-up 收口。

### t015_code_f005 - stream_agent 包仍导出已删除的 ProtocolEnvelope，公共导入路径断裂

- 严重度：minor
- 锚点：代码质量/契约清理；AC-006 协议契约完整化后的遗留死代码。
- 位置：`src/backend/cbrowser/stream_agent/__init__.py:18`、`:23`、`:69`；`src/backend/cbrowser/stream_agent/protocol.py:243-245`
- 问题：`ProtocolEnvelope` 已从 `protocol.py` 删除，但包级 `__all__` 和惰性 `__getattr__` 仍把它列为导出；`from cbrowser.stream_agent import ProtocolEnvelope` 实际抛出 `ImportError`（已用 pydantic 环境复现）。此外新加的 `dump_agent_envelope` 在仓库内没有调用方，属于未使用的新增辅助函数。
- 建议：从 `__init__.py` 的 TYPE_CHECKING 导入、`__all__` 与 `__getattr__` 中移除 `ProtocolEnvelope`，补上实际需要的 `AgentRegisterEnvelope`/`AgentHeartbeatEnvelope`（如包导出是公开契约）；删除 `dump_agent_envelope` 或改由生产序列化路径使用。

### t015_code_f006 - blueprint 仍有旧协议名与章节交叉引用

- 严重度：minor
- 锚点：AC-009「blueprint ... 同新架构一致（含 architecture.md 章节编号）」
- 位置：`docs/blueprint/gateway.md:21`；`docs/blueprint/architecture.md:17`
- 问题：`gateway.md` 仍写「首包必须为 `ProtocolEnvelope(action=AgentAction.REGISTER)`」，但实现与 schema 已改为 `AgentRegisterEnvelope(action=register)`；`architecture.md:17` 仍说 Runtime Coordinator「见 5.5」，本 task 已把该节从 5.5 调整为 5.4。两处都会把读者带到旧模型/旧章节。
- 建议：改为 `AgentRegisterEnvelope`；把交叉引用改为 5.4，并顺带检查其它 5.4/5.5 引用。

### t015_code_f007 - runtimeStatusUrl 变成无效公开 prop，且 runtime 状态读取保留 any 兜底

- 严重度：minor
- 锚点：代码质量/类型契约；AC-008 统一 API 客户端改造的收尾。
- 位置：`src/frontend/src/features/browser-session/useBrowserSession.ts:16`、`:134`、`:180`；`src/frontend/src/features/browser-session/types.ts:61`；`src/frontend/src/features/browser-session/BrowserSessionView.tsx:16,35`
- 问题：`runtimeStatusUrl` 仍出现在 options/props 与 effect 依赖中，但读取运行时的 `fetch` 已被 `client.profiles.getRuntime` 替代，调用方传入该 prop 会被静默忽略；同时 `data.observed_state || (data as any).state` 使用 `any` 兜底，而生成的 `ProfileRuntimeResponse` 只有 `observed_state`，该兜底掩盖了类型契约。i18n 的 `runtimeCheckFailed` 也随之失去调用方。
- 建议：删除 `runtimeStatusUrl` prop/依赖（或明确保留并实现），移除 `(data as any).state`，直接用生成类型；清理未使用的 i18n key。

### t015_code_f008 - create_gateway_app 与 AgentCredentials 仍绕过统一密钥读取器

- 严重度：minor
- 锚点：AC-005「所有密钥文件经统一的权限与长度校验读取」；A30 只点名了 GatewayApiClient/RtcConfigService，但该 AC 的字面范围更广。
- 位置：`src/backend/cbrowser/gateway/server.py:56-58`；`src/backend/cbrowser/supervisor/agent_credentials.py:12-16`
- 问题：`create_gateway_app` 仍直接 `read_text` 读 `gateway_token_file`，`AgentCredentials` 仍直接 `read_text` 读 agent key，均未使用 `read_secret_file` 的权限与长度校验。生产入口 `GatewayConfig.from_env` 已对这些同一路径做过一次校验，因此正常启动路径没有可观测绕过；但 `create_gateway_app`/`AgentCredentials` 作为可被测试或嵌入代码直接构造的入口，会接受 group/other 可读或过短的密钥，违背「所有密钥文件经统一读取」的约束。
- 建议：在这两个使用点也调用 `read_secret_file`，并把校验失败转换为启动期错误；或者让配置构造成为唯一写入/校验入口并禁止直接构造这些类。

## 结论

- 前轮 finding 复核：Round 1，无前轮 finding。
- 本轮新发现：8 条（3 important，5 minor）。
- 未进表的提示：
  - 文件过大（按本 task net 增量/新文件判定）：`src/backend/cbrowser/stream_agent/policy.py` 745 行（原 714，净增）、`src/frontend/src/features/browser-session/useBrowserSession.ts` 442 行（原 423，净增）、`docs/spikes/s011_direct_media_validation/code/direct_media_probe.py` 新建 1632 行；均为提示，不单独进 finding。`stream_agent/agent.py`（1080 行，净减 197）与 `gateway/server.py`（656 行，净减 78）虽仍偏大，但本 task 在收缩，不按阈值出 finding。
  - 圈复杂度：`radon cc -n C` 报 `LiveCapturePolicyAgent.reconcile_capture_state` 与 `StreamAgent._viewer_upstream_worker` 为 E 级，但本 task 未增加这两个函数的分支（前者未改，后者仅改 `MAX_STREAM_FRAME_SIZE` 常量名），按规则不单独出 finding；`useBrowserSession` 的消息处理分支仍较密集，后续可考虑拆分。
  - 测试层问题（构建 marker、前端 E2E 探针、E2E 覆盖收缩）已在 `review_test.md` 覆盖，本报告不重复。
- AC 复验方式：

| AC | 类别 | 证据 |
|---|---|---|
| AC-001 | trust_prior | 依赖 `docs/spikes/s011_direct_media_validation/report.md` 与 `docs/findings/d026_direct_media_local_only.md` 的真实 Chrome + OrbStack 证据；本 review 未重跑完整媒体部署 |
| AC-002 | re_verified | grep 全仓确认 `cbrowser.rtc_config`、`gateway/rotation.py`、`stream_agent/ice_transport.py`、TURN 配置项与协议字段已移除；`config/compose` 无 TURN 服务/变量 |
| AC-003 | re_verified（未达成，见 f001） | 重跑 `tests/integration/test_gateway_signaling.py` 与 `test_gateway_control.py` 共 12 passed；另用 GatewayHarness 复现 Agent 无效 token 先 101 后 1008 |
| AC-004 | re_verified | 代码检查心跳/仲裁循环逐次 catch 与 supervised 退避；重跑 `test_stream_agent_lifecycle.py`、`test_stream_runtime.py`、`test_stream_resume.py` 共 24 passed；外层退避测试缺口见 `review_test.md` |
| AC-005 | re_verified（未达成，见 f002/f008） | 重跑 `test_gateway_config.py`、`test_gateway_control.py`、`test_gateway_signaling.py`；独立复现非对象 JSON quota 返回 500 |
| AC-006 | re_verified | 检查 `schemas/stream/agent_protocol.json` 的五个 envelope 联合与按 action 判别；重跑 `test_stream_protocol_schema.py`、`test_stream_agent_protocol_v2.py`，漂移守卫通过 |
| AC-007 | re_verified（代码层） | grep adapter 确认无 DataChannel/WS 报文记录与测试全局写入，保留文档化的 `__getWebRTCStats`；前端 Vitest 30 passed；E2E 探针缺口见 `review_test.md` |
| AC-008 | re_verified（未达成，见 f003） | 重跑 `BrowserSessionView.test.tsx`、`adapter_restart.test.ts` 共 30 passed；检查消息序列发现 Web Locks 诊断被 WS_CLOSE 覆盖 |
| AC-009 | re_verified（有 f006 遗留） | grep 确认 ADR 013、Superseded、计划 §8.4/§19.3 替代标记与 adoption D1 已更新；发现 gateway.md 旧协议名与 architecture.md 旧章节号 |

coverage = 8 / 9

- 总体判断：FAIL。AC-003、AC-005、AC-008 均有已打勾但实现未满足的 blocking 缺口；其余 AC 主要通过代码检查与现有测试复验，AC-001 依赖既有部署证据。
- 系统性 follow-up：建议将 f004 的限流键空间上限作为 `gateway_viewer_throttle_key_bound`（Gateway Viewer 限流键空间上限）收口；其余属于本 task 收口。

verdict: FAIL

## Round 2 (2026-11-03T01:08:00+08:00)

reviewed_scope: 84ba3827ce27180a

### 前轮 finding 复核

- `t015_code_f001` 已消除。`src/backend/cbrowser/gateway/server.py:291-306` 在 `ws.prepare()`（`:308-309`）前完成查询参数身份、HMAC 与 API 实例绑定校验，失败分别返回 400/401/403；`tests/integration/test_gateway_signaling.py:62-111` 已把无效 token 与过期实例断言为握手 401/403，并断言旧 Agent `not ws_valid.closed`。重跑该文件与 `test_gateway_control.py` 共 12 passed，全量 integration 79 passed。升级后仅保留已认证 Agent 的首包格式/身份一致性 1008，属 Round 1 建议中的载荷复核，不再是接入拒绝。
- `t015_code_f002` 已消除。`server.py:179-191` 显式拒绝非对象 body，并用 `_QuotaRequest`/`SupervisorQuotaPayload` 校验；`:232-239` 对 disconnect 同样处理。`tests/integration/test_gateway_control.py:185-209` 覆盖数组、字符串 body 与越界配额，均断言 400；重跑通过。
- `t015_code_f003` 已消除。`useBrowserSession.ts:237-244` 收到 Web Locks 消息后置 ref，后续 WS_CLOSE 直接返回；`BrowserSessionView.test.tsx:126-140` 按真实顺序派发两条消息并断言最终仍是 Web Locks 诊断；前端全量 126 passed。
- `t015_code_f004` 已消除。`registry.py:144-152` 在键数超过 1024 时先清过期键、再按插入顺序淘汰，键空间有硬上限；实现与 `Bounded` docstring 一致。
- `t015_code_f005` 已消除。`stream_agent/__init__.py` 不再导出 `ProtocolEnvelope`，改为新 envelope；全仓 grep 无 `ProtocolEnvelope`/`dump_agent_envelope` 引用，`py_compile` 通过。
- `t015_code_f006` 已消除。`docs/blueprint/gateway.md:21` 已改 `AgentRegisterEnvelope(action=register)`，`docs/blueprint/architecture.md:17` 已指向 5.4；Round 1 两处旧引用均不存在。
- `t015_code_f007` 已消除。全仓 grep 无 `runtimeStatusUrl`/`runtimeCheckFailed`；`types.ts:61` 改为 `apiClient?: ApiClient`，`useBrowserSession.ts:133` 直接使用 `data.observed_state`，无 `(data as any).state`。
- `t015_code_f008` 已消除。`server.py:72-79` 与 `supervisor/agent_credentials.py:14-19` 均改用 `read_secret_file`，失败转为启动期 `ValueError`。

### 本轮新发现

#### t015_code_f009 - gateway.md 的 Agent 拒绝语义与实现不一致

- 严重度：minor
- 锚点：AC-009（blueprint 与实现一致）；同时影响 AC-003/AC-005 的可读契约。
- 位置：`docs/blueprint/gateway.md:23`、`:62-63`
- 问题：`:23` 仍写「runtime_instance_id 与 API 不一致……立即发送 Close 1008」，但 f001 修复后该分支在升级前返回 HTTP 403（`server.py:302-306`），测试也断言 403（`test_gateway_signaling.py:98-110`）。另外 `:62-63` 的 quota/disconnect 错误码表未列 400，而实现与 AC-005 都要求非法 body 返回 400。文档会把读者带回已删除的升级后拒绝模型。
- 建议：将 `:23` 改为升级前 403；在 `:62-63` 错误码栏补 400。

#### t015_code_f010 - 仍有两处密钥文件绕过统一读取器

- 严重度：minor
- 锚点：AC-005「所有密钥文件经统一的权限与长度校验读取」；A30 只点名 GatewayApiClient/RtcConfigService（Round 1 f008 已处理其同类两点）。
- 位置：`src/backend/cbrowser/stream_agent/config.py:199-206`；`src/backend/cbrowser/supervisor/runner.py:81-84`
- 问题：Stream Agent 的 `CBROWSER_AGENT_SECRET_FILE` 与 `run_supervisor` 的 Supervisor API token 仍用 `read_text()`，不校验 group/other 权限也不校验长度。正常部署由 Supervisor 以 0600 生成、core 会再次校验 supervisor token，因此没有已观察到的生产绕过；但与 AC-005 字面要求不一致，属 Round 1 f008 同类遗漏。
- 建议：两处改用 `read_secret_file`（至少 32 字节），或在构造配置前完成同等校验并复用结果。

### AC 复验方式

| AC | 类别 | 证据 |
|---|---|---|
| AC-001 | trust_prior | 依赖 `docs/spikes/s011_direct_media_validation/report.md` 与 `docs/findings/d026_direct_media_local_only.md` 的真实 Chrome + OrbStack 证据；本 review 未重跑完整媒体部署 |
| AC-002 | re_verified | grep 全仓确认 `rtc_config`、`gateway/rotation.py`、`stream_agent/ice_transport.py`、TURN 配置与协议字段已移除；`config/coturn` 目录已删除 |
| AC-003 | re_verified | 检查 `server.py:291-309` 的升级前拒绝顺序；重跑 `test_gateway_signaling.py`/`test_gateway_control.py` 12 passed，全量 integration 79 passed |
| AC-004 | re_verified | 检查心跳与捕获仲裁循环逐次 catch 及监督任务退避；重跑 `test_stream_agent_lifecycle.py`、`test_stream_runtime.py`、`test_stream_resume.py`、`test_stream_transport_hardening.py` 共 36 passed |
| AC-005 | re_verified（有 f010 遗留） | 检查配额/断连 400 校验、Viewer 限流与 WS 帧上限；重跑 integration 通过；两处密钥读取仍直接 `read_text`，见 f010 |
| AC-006 | re_verified | 重跑 `test_stream_protocol_schema.py`、`test_stream_agent_protocol_v2.py` 等 26 passed，schema 漂移守卫通过 |
| AC-007 | re_verified | grep adapter 确认无 DataChannel/WS 报文记录与测试全局写入；前端 Vitest 126 passed |
| AC-008 | re_verified | 检查 `useBrowserSession.ts:237-264` 的诊断覆盖与监听释放；重跑 `BrowserSessionView.test.tsx`、`adapter_restart.test.ts` 共 31 passed |
| AC-009 | re_verified（有 f009 遗留） | grep 确认 ADR 013、Superseded、计划 §8.4/§19.3 替代标记与 adoption D1 已更新；gateway.md 拒绝语义仍过期，见 f009 |

coverage = 8 / 9

### 结论

- 前轮 finding 复核：f001-f008 全部已消除，无遗留 blocker；结论以当前 diff/代码/测试为准，不采信 note 处置表。
- 本轮新发现：2 条（0 blocking，2 minor）。
- 未进表的提示：文件过大（`src/backend/cbrowser/stream_agent/policy.py` 746 行、`src/frontend/src/features/browser-session/useBrowserSession.ts` 446 行、`docs/spikes/s011_direct_media_validation/code/direct_media_probe.py` 1632 行；前两者本 task 净增、spike 为一次性探针，均未达 important 阈值）；`stream_agent/agent.py` 1086 行但本 task 净减；圈复杂度未复测，Round 1 的 `reconcile_capture_state`/`_viewer_upstream_worker` 高复杂度点本 task 未新增分支。无范围外行为。
- 总体判断：PASS。Round 1 的 3 个 blocker 均已在当前 diff/代码/测试中消除；本轮仅有 2 个 minor（文档同步与同类密钥读取收尾），不阻断。
- 系统性 follow-up：无。

verdict: PASS

## Round 3 (2026-11-03T01:23:00+08:00)

reviewed_scope: 2a43b59c73af1220

本轮为 task 归档后的最终范围复核。相对 Round 2 的改动集中在：`docs/blueprint/gateway.md`、`src/backend/cbrowser/stream_agent/config.py`、`src/backend/cbrowser/supervisor/runner.py`、`tests/fixtures/frontend_probe/adapter_probe.py` 及三个 Stream 单测（`test_stream_selkies_tokens.py`、`test_stream_transport_hardening.py`、`test_stream_agent_lifecycle.py`）。

### 前轮 finding 复核

- `t015_code_f001` 仍已消除。`src/backend/cbrowser/gateway/server.py:291-306` 在 `ws.prepare()`（`:308-309`）前完成查询参数身份、HMAC 与 API 绑定校验，失败返回 400/401/403；server.py 在 Round 2 后未改动，本轮重跑 `tests/integration` 79 passed。
- `t015_code_f002` 仍已消除。`server.py:176-191`、`:229-239` 对非对象 body 和非法字段返回 400；`test_gateway_control.py` 通过。
- `t015_code_f003` 仍已消除。`useBrowserSession.ts:237-244` 用 `webLocksUnavailableRef` 抑制后续 `CBROWSER_WS_CLOSE` 覆盖；前端 Vitest 126 passed。
- `t015_code_f004` 仍已消除。`gateway/registry.py:144-152` 对键空间设硬上限。
- `t015_code_f005` 功能上仍已消除（全仓无 `ProtocolEnvelope`、`dump_agent_envelope` 引用），但导出元组遗留格式与重复项，见 f012。
- `t015_code_f006` 仍已消除。`docs/blueprint/gateway.md:21` 为 `AgentRegisterEnvelope`，`docs/blueprint/architecture.md:17` 指向 5.4。
- `t015_code_f007` 仍已消除。无 `runtimeStatusUrl`、无 `(data as any).state`。
- `t015_code_f008` 仍已消除。`gateway/server.py:72-79` 与 `supervisor/agent_credentials.py:14-20` 均经 `read_secret_file`。
- `t015_code_f009` 已消除。`docs/blueprint/gateway.md:21-23` 已改为查询参数身份 + 升级前 HTTP 403，`:62-63` 错误码表已补 400，与 `server.py:288-306`、`:176-191` 及测试一致。
- `t015_code_f010` 调用点层面已消除。`stream_agent/config.py:201-208` 与 `supervisor/runner.py:82-90` 均改用 `read_secret_file`，权限与长度校验生效；但这次修改引入 Stream 镜像启动回归，见 f011。

### 本轮新发现

#### t015_code_f011 - Stream 运行时镜像未复制 cbrowser.secret_files，Stream Agent 启动即失败

- 严重度：critical
- 锚点：行为缺陷（构建后的 Stream 容器启动即 `ModuleNotFoundError`，所有 Profile 无媒体）；同时是 AC-005「统一密钥读取」修复的部署回归，实际破坏 AC-001/AC-002 的构建产物链路。
- 位置：`src/backend/cbrowser/stream_agent/config.py:14`；`config/docker/stream_runtime/Dockerfile:51-52`；`config/docker/stream_runtime/entrypoint.sh:195`。
- 问题：post-Round-2 修复把 Stream Agent 的密钥读取改为 `from cbrowser.secret_files import read_secret_file`（`config.py:14`），但 Stream 镜像只复制 `cbrowser/__init__.py` 与 `cbrowser/stream_agent`（Dockerfile `:51-52`），没有复制 `src/backend/cbrowser/secret_files.py`。Gateway 与 Supervisor 镜像都显式复制了该模块（`gateway_runtime/Dockerfile:17`、`supervisor_runtime/Dockerfile:17`），仅 Stream 镜像遗漏。入口 `python3 -m cbrowser.stream_agent.agent`（`entrypoint.sh:195`）导入 config 时立即失败。我按镜像布局（只放 Dockerfile 列出的路径）复现：`PYTHONPATH=<layout> python -c "from cbrowser.stream_agent.config import StreamAgentConfig"` → `ModuleNotFoundError: No module named 'cbrowser.secret_files'`。现有单测在源树 `PYTHONPATH=src/backend` 下运行，E2E 使用修复前构建的不可变镜像，因此都没有捕获该回归。
- 建议：在 `config/docker/stream_runtime/Dockerfile` 增加 `COPY src/backend/cbrowser/secret_files.py /app/cbrowser/secret_files.py`；同步更新 `docs/guides/stream_runtime_validation.md:8` 的构建上下文清单；增加镜像布局守卫（例如单测解析 Stream Dockerfile 的 COPY 列表，断言 `stream_agent` 的所有 `cbrowser.*` 绝对导入都有对应文件），修复后重建 Stream 镜像重跑 `tests/e2e/test_stream_runtime_e2e.py`。

#### t015_code_f012 - stream_agent 包导出元组缩进错乱且重复

- 严重度：minor
- 锚点：代码质量/可维护性（f005 修复的遗留）。
- 位置：`src/backend/cbrowser/stream_agent/__init__.py:84-99`
- 问题：`if name in (...)` 中 `:87-93` 缩进错位，且 `GatewayTunnelEnvelope`、`GatewayControlEnvelope`、`GatewayRegisterResponse`、`AgentRegisterPayload`、`SupervisorQuotaPayload` 重复出现。功能上元组去重不影响 `in`，但这是 f005 修复留下的明显格式与重复缺陷，后续增删导出项容易漏改一处。
- 建议：规整为单层缩进、去重，并与 `__all__` 名单逐项对齐。

#### t015_code_f013 - Stream Agent secret 的最低长度 8 与其他读取点 32 不一致

- 严重度：minor
- 锚点：AC-005「所有密钥文件经统一的权限与长度校验读取」；行为缺陷：短 secret 通过启动校验但注册必然 401。
- 位置：`src/backend/cbrowser/stream_agent/config.py:204-206`；`src/backend/cbrowser/supervisor/agent_credentials.py:15-17`。
- 问题：同一族 agent 凭证在 `AgentCredentials` 要求 ≥32 字节，Stream Agent 配置只要求 ≥8 字节。生产路径由 Supervisor 写入 64 字符 HMAC token，因此现有部署不触发；但独立/测试环境提供 8-31 字节的 `CBROWSER_AGENT_SECRET_FILE` 会通过启动校验，随后 Gateway 的 HMAC 校验必然返回 401，错误被推迟到注册阶段。现有单测使用 18 字节的 `agent_secret_value`，怀疑是为迁就该夹具而放宽阈值。
- 建议：统一为 ≥32 字节并把单测夹具改为 `secrets.token_urlsafe(32)`；或在启动期明确校验 agent secret 必须是 64 字符 HMAC token。

#### t015_code_f014 - frontend.md 对测试探针注入方式的描述与实现不符

- 严重度：minor
- 锚点：AC-009「blueprint ... 同新架构一致」；文档与实现一致性。
- 位置：`docs/blueprint/frontend.md:25`；`tests/fixtures/frontend_probe/adapter_probe.py:54-64`；`tests/fixtures/frontend_probe/host_builder.py:101`；`tests/fixtures/frontend_app_probe/harness.py:42`。
- 问题：blueprint 写「测试需要的 DataChannel/PeerConnection 探针由测试自身经 Playwright `add_init_script` 注入」，实际实现是把 `adapter_probe.js` 写入复制后的 Selkies 目录，并在 `selkies_adapter.js` 之前插入 `<script>`；E2E 中的 `add_init_script` 用于 sessionStorage tab id 与 MEDIA_FAULT，不是 DataChannel/PC 探针。读者会误以为探针走 Playwright 注入。spec 测试策略里的同一句也随之过时；实现选择 script 注入本身合理（必须保证探针在 adapter 之前执行，f008 的修复正依赖此顺序）。
- 建议：把 blueprint 与 spec 的描述改为「在复制后的 Selkies index 中于 adapter 之前注入探针脚本」，或改为实际使用 `add_init_script` 并重新验证注入顺序。

### AC 复验方式

| AC | 类别 | 证据 |
|---|---|---|
| AC-001 | trust_prior | 依赖 `docs/spikes/s011_direct_media_validation/report.md` 与 `docs/findings/d026_direct_media_local_only.md` 的真实 Chrome + OrbStack 证据；本轮未重跑媒体部署。注意 f011 使当前源码构建的 Stream 镜像无法启动，修复前该证据无法在交付镜像上复现 |
| AC-002 | re_verified（有 f011 部署回归） | grep 确认运行时 TURN/coturn/rtc_config/ICE 代次机制已移除；`tests/unit` 473 passed；但 Stream 镜像缺模块使直连媒体在构建产物上不可用，见 f011 |
| AC-003 | re_verified | `server.py:288-309` 升级前拒绝顺序未变；重跑 `tests/integration` 79 passed |
| AC-004 | re_verified | 重跑 `tests/unit` 473 passed，含心跳/仲裁循环监督与退避重启用例 |
| AC-005 | re_verified（有 f011/f013） | 配额 400、Viewer 限流 429、WS 帧上限、心跳超时启动校验均在位；密钥读取已统一，但 Stream 镜像缺模块（f011）且 Agent secret 最低长度不一致（f013） |
| AC-006 | re_verified | 重跑 `test_stream_protocol_schema.py`、`test_stream_agent_protocol_v2.py` 等，schema 漂移守卫通过 |
| AC-007 | re_verified | 前端 Vitest 126 passed；`test_frontend_adapter_build.py`/`test_frontend_build_wiring.py` 12 passed；探针注入顺序静态核对为 probe → adapter；本轮未启动 Docker 前端 E2E |
| AC-008 | re_verified | 重跑前端 Vitest 126 passed，覆盖 Web Locks 诊断、401、监听释放 |
| AC-009 | re_verified（有 f014） | grep 确认 ADR 013、Superseded、计划 §8.4/§19.3 替代标记与 adoption D1；gateway.md 已与实现一致；frontend.md 探针描述仍不符（f014） |

coverage = 8 / 9

### 结论

- 前轮 finding 复核：f001-f008 仍消除；f009 已消除；f010 的两个调用点已修复，但该修复引入 f011。gateway 文档修复与探针注入顺序修复本身未发现回归。
- 本轮新发现：4 条（1 critical，3 minor）。
- 未进表的提示：按物理行数，`src/backend/cbrowser/stream_agent/policy.py` 746 行（本 task 净增）、`src/frontend/src/features/browser-session/useBrowserSession.ts` 446 行（净增）、新建 `docs/spikes/s011_direct_media_validation/code/direct_media_probe.py` 1632 行（一次性 spike 探针）；`stream_agent/agent.py` 1086 行与 `gateway/server.py` 683 行本 task 净减。radon 复测：`LiveCapturePolicyAgent.reconcile_capture_state` E(31)、`StreamAgent._viewer_upstream_worker` E(34)、`connect_and_run` C(17)，本 task 未给这些函数新增分支（`from_env` 反而从 D(22) 收缩），按规则只提示。无范围外行为。
- 总体判断：FAIL。post-Round-2 的密钥读取统一化遗漏了 Stream 镜像的 `secret_files.py`，Stream Agent 在交付镜像中启动即失败，所有 Profile 无媒体；Round 2 的 PASS 不再成立。
- 系统性 follow-up：建议登记阻塞性 follow-up「修复 Stream 运行时镜像缺失 cbrowser.secret_files」slug `stream_image_secret_files`，并在修复后重建镜像重跑 Stream media E2E；task 已 finish/archive，需用户决定 reopen 或新 task 承接。

verdict: FAIL

## Round 4 (2026-11-03T01:34:52+08:00)

reviewed_scope: 7619ff3a65c45c15

本轮复核 Round 3 的四个修复（Stream 镜像 `secret_files`、导出元组、secret 最低长度、frontend.md 探针描述），并重扫前轮 finding。相对 Round 3 的改动集中在：`config/docker/stream_runtime/Dockerfile`、`src/backend/cbrowser/stream_agent/__init__.py`、`src/backend/cbrowser/stream_agent/config.py`、`docs/blueprint/frontend.md`、`tests/unit/test_stream_selkies_tokens.py`；`git status` 无其他未跟踪交付文件（仅归档 task 目录）。

### 前轮 finding 复核

- `t015_code_f001` 仍已消除。`src/backend/cbrowser/gateway/server.py:291-309` 在 `ws.prepare()` 前完成身份、HMAC 与 API 绑定校验（400/401/403）；本轮重跑 `tests/integration` 79 passed。
- `t015_code_f002` 仍已消除。`server.py:176-191`、`:229-239` 对非对象 body 与非法字段返回 400；`test_gateway_control.py` 通过。
- `t015_code_f003` 仍已消除。`useBrowserSession.ts:237-244` 用 `webLocksUnavailableRef` 抑制后续 `CBROWSER_WS_CLOSE`；前端 Vitest 126 passed。
- `t015_code_f004` 仍已消除。`gateway/registry.py:144-152` 对键空间设硬上限（1024，先清过期再按插入序淘汰）。
- `t015_code_f005` 仍已消除。全仓无 `ProtocolEnvelope`/`dump_agent_envelope` 引用；导出元组修复后重新验证 `cbrowser.stream_agent.__all__` 17 项无重复、经 `__getattr__` 全部可解析。
- `t015_code_f006` 仍已消除。`docs/blueprint/gateway.md:21` 为 `AgentRegisterEnvelope`，`docs/blueprint/architecture.md:17` 指向 5.4。
- `t015_code_f007` 仍已消除。全仓无 `runtimeStatusUrl`、`runtimeCheckFailed` 与 `(data as any).state`。
- `t015_code_f008` 仍已消除。`gateway/server.py:72-79` 与 `supervisor/agent_credentials.py:14-20` 均经 `read_secret_file`。
- `t015_code_f009` 仍已消除。`docs/blueprint/gateway.md:21-23` 与 `:62-63` 的升级前 403、400 错误码同 `server.py:288-306`、`:176-191` 一致。
- `t015_code_f010` 仍已消除。`stream_agent/config.py:201-208` 与 `supervisor/runner.py:82-90` 均经 `read_secret_file`；本轮验证 Stream 镜像已包含该模块（见 f011）。
- `t015_code_f011` 已消除。`config/docker/stream_runtime/Dockerfile:52` 增加 `COPY src/backend/cbrowser/secret_files.py`。我核对重建镜像 `cbrowser-t015-stream:e2e`（`sha256:33b9ab...`，构建时间 01:23:54）内 `secret_files.py`、`stream_agent/config.py`、`stream_agent/__init__.py` 的 sha256 与当前 worktree 完全一致，容器内 `import cbrowser.secret_files, cbrowser.stream_agent.config` 成功。另用该镜像独立重跑 `tests/e2e/test_stream_runtime_e2e.py`（Browser 用 `sha256:b9f740...`，只读引擎缓存）：**1 passed in 69.75s**；产物 `no_turn_topology=true`、`refresh_survived=true`、`visibility` 隐藏页停帧/可见页续帧、`viewer_resume` tab 身份保留、8 组中文 IME、复制标签后 3 viewer 降至 2。
- `t015_code_f012` 已消除。`stream_agent/__init__.py:84-99` 元组为单层缩进且无重复项，与 `__all__` 的协议名单一致。
- `t015_code_f013` 已消除。`stream_agent/config.py:204-206` 与其他凭证读取点统一为 `minimum_bytes=32`（`agent_credentials.py:15-17`）；单测夹具改用 `secrets.token_urlsafe(32)` 且 `chmod(0o600)`；`tests/unit` 473 passed。
- `t015_code_f014` 列出的位置已消除。`docs/blueprint/frontend.md:25` 已改为「测试夹具写入复制后的 Selkies 目录并在 `selkies_adapter.js` 之前插入 `<script>`」，与 `tests/fixtures/frontend_probe/adapter_probe.py:54-64`、`host_builder.py:101`、`frontend_app_probe/harness.py:42` 一致；但 spec 测试策略句未同步，见 f016。

### 本轮新发现

#### t015_code_f015 - Stream 镜像构建上下文文档未同步 secret_files.py

- 严重度：minor
- 锚点：AC-009（媒体相关指南与实现一致）；f011 修复建议中「同步更新 guide 构建上下文清单」未落地。
- 位置：`docs/guides/stream_runtime_validation.md:8`
- 问题：指南仍写「Stream 构建上下文只包含 Dockerfile、entrypoint、cbrowser/__init__.py 和 stream_agent 包」，但当前 `config/docker/stream_runtime/Dockerfile:52` 还复制 `cbrowser/secret_files.py`，且 `stream_agent/config.py:14` 依赖它。按该清单维护构建会再次漏掉运行必需模块，正是 f011 的回归面。
- 建议：把 `secret_files.py` 加入清单，或改为「以 Dockerfile 的 COPY 列表为准」并将该文件列为必需项。

#### t015_code_f016 - spec 测试策略仍写 Playwright add_init_script 注入探针

- 严重度：minor
- 锚点：AC-009（文档/规格与实现一致）；f014 建议中的 spec 同步未完成。
- 位置：`docs/archive/tasks/t015_v2_media_link_simplification/task.md:63`
- 问题：spec 测试策略写「E2E 用 Playwright add_init_script 注入探针」，实际 `tests/fixtures/frontend_probe/adapter_probe.py:54-64` 是把 `adapter_probe.js` 写入复制后的 Selkies 目录并在 `selkies_adapter.js` 前插入 `<script>`；E2E 的 `add_init_script` 只用于 sessionStorage tab id 与 MEDIA_FAULT。blueprint 已按 f014 修正，spec 仍是旧描述。
- 建议：将 spec 改为实际的 script 注入方式，或改为 `add_init_script` 并重新验证探针先于 adapter 的顺序。

### AC 复验方式

| AC | 类别 | 证据 |
|---|---|---|
| AC-001 | re_verified | 用重建的 `cbrowser-t015-stream:e2e`（`sha256:33b9ab...`）独立重跑 `tests/e2e/test_stream_runtime_e2e.py`：1 passed in 69.75s；`media_proof.json` 断言 `no_turn_topology=true`、两页 127.0.0.1 host/udp 候选、1920×1080 帧与音频增长、刷新/复制标签/关闭首 tab、可见性暂停恢复、Viewer 断线 resume、8 组中文 IME；另核对镜像内 `secret_files.py` 与当前源码一致 |
| AC-002 | re_verified | grep 确认 `rtc_config`、`gateway/rotation.py`、`stream_agent/ice_transport.py`、TURN 配置与协议字段已移除；`tests/unit` 473 passed，`tests/integration` 79 passed |
| AC-003 | re_verified | 检查 `server.py:291-309` 的升级前拒绝顺序；重跑 `tests/integration` 79 passed |
| AC-004 | re_verified | 重跑 `tests/unit` 473 passed，含心跳/仲裁循环监督与退避重启用例 |
| AC-005 | re_verified | 配额 400、Viewer 限流 429、WS 帧上限、心跳超时启动校验均在位；Stream 镜像已含 `secret_files.py` 且可导入；Agent secret 最低长度与 `AgentCredentials` 统一为 32 |
| AC-006 | re_verified | 重跑 `test_stream_protocol_schema.py`、`test_stream_agent_protocol_v2.py` 等，schema 漂移守卫通过 |
| AC-007 | re_verified | 前端 Vitest 126 passed；adapter 无报文记录/测试全局；探针注入顺序静态核对为 probe → adapter |
| AC-008 | re_verified | 前端 Vitest 126 passed，覆盖 Web Locks 专门诊断、401、监听释放 |
| AC-009 | re_verified（有 f015/f016 minor） | grep 确认 ADR 013、Superseded、计划 §8.4/§19.3 替代标记与 adoption D1；`frontend.md` 探针描述已正确；guide 构建清单与 spec 测试策略句仍过时 |

coverage = 9 / 9

### 结论

- 前轮 finding 复核：f001-f010 仍消除；f011 已消除并由独立 E2E 复跑确认；f012、f013 已消除；f014 列出的 blueprint/夹具位置已修正，spec 句遗留转为 f016。未采信 note 处置表，结论以当前 diff、代码、镜像与测试结果为准。
- 本轮新发现：2 条（0 blocking，2 minor）。
- 未进表的提示：文件过大与圈复杂度同 Round 3，未因本轮修复变化（`stream_agent/policy.py` 746 行、`useBrowserSession.ts` 446 行、spike `direct_media_probe.py` 1632 行；`reconcile_capture_state`/`_viewer_upstream_worker` 高复杂度点本 task 未新增分支）。另：Round 3 建议的 Stream Dockerfile 布局守卫仍未加入 `tests/unit/test_baseline_runtime_regressions.py`（该文件已覆盖 Supervisor/Gateway/API/fixture 镜像），属测试覆盖建议，交由 `review_test` 判断。无范围外行为。
- 总体判断：PASS。Round 3 的 critical 镜像回归已修复并经重建镜像 + 独立 Stream E2E 复验；无未解决 critical / important，仅 2 个文档同步 minor。
- 系统性 follow-up：无（f015/f016 属本 task 文档收口）。

verdict: PASS

## Round 5 (2026-11-03T01:42:09+08:00)

reviewed_scope: 56bd90480361b993

本轮为 Round 4 两个 minor 修复的收敛复核。相对 Round 4 的改动集中在：`docs/guides/stream_runtime_validation.md`（f015）、`docs/archive/tasks/t015_v2_media_link_simplification/task.md`（f016），以及 review_test 侧的 `docs/blueprint/testing.md`、`tests/fixtures/frontend_probe/adapter_probe.py`、`tests/unit/test_baseline_runtime_regressions.py`。生产代码与 Stream Dockerfile 自 Round 4 起未变；`git status` 仅 `docs/archive/tasks/t015_v2_media_link_simplification/` 未跟踪（流程文件）。

### 前轮 finding 复核

- `t015_code_f015` 已消除。`docs/guides/stream_runtime_validation.md:8` 已把 `cbrowser/secret_files.py` 加入 Stream 构建上下文清单，并补「以 Dockerfile 的 COPY 列表为准」；与 `config/docker/stream_runtime/Dockerfile:52` 的 `COPY src/backend/cbrowser/secret_files.py` 一致。
- `t015_code_f016` 已消除。`docs/archive/tasks/t015_v2_media_link_simplification/task.md:63` 已改为「E2E 由测试夹具在复制后的 Selkies index 中于 adapter 之前注入探针脚本，vitest 用测试内包装」，与 `tests/fixtures/frontend_probe/adapter_probe.py:55-66`、`tests/fixtures/frontend_probe/host_builder.py:101`、`tests/fixtures/frontend_app_probe/harness.py:42` 的实际 script 注入一致；spec 内不再以 `add_init_script` 描述探针。
- `t015_code_f001`-`f014` 仍全部消除（抽查 + 重跑）：`gateway/server.py:283-309` 在 `ws.prepare()` 前完成 400/401/403 拒绝；`server.py:176-191`、`:229-239` 非对象/非法字段 body 返回 400；`useBrowserSession.ts:237-244` 以 ref 抑制 Web Locks 诊断被 WS_CLOSE 覆盖；`gateway/registry.py:144-152` 键空间有硬上限；`stream_agent/__init__.py` 17 项导出无重复且经 `__getattr__` 全部可解析（uv+pydantic 环境）；全仓源码无 `ProtocolEnvelope`/`dump_agent_envelope`/`runtimeStatusUrl`/`runtimeCheckFailed`/`(data as any).state`；`docs/blueprint/gateway.md:21-23`、`:60-63` 与 `architecture.md:17` 同实现一致；四处密钥读取均为 `minimum_bytes=32` 的 `read_secret_file`（`stream_agent/config.py:205`、`supervisor/agent_credentials.py:16`、`supervisor/runner.py:86`、`gateway/server.py:76`）；Stream Dockerfile 含 `secret_files.py`。

### 本轮新发现

无。

### AC 复验方式

| AC | 类别 | 证据 |
|---|---|---|
| AC-001 | trust_prior | 依赖 Round 4 在重建镜像 `cbrowser-t015-stream:e2e` 上重跑 `tests/e2e/test_stream_runtime_e2e.py` 的 1 passed 与 s011/d026 证据；本轮未重跑媒体 E2E，但本轮改动未触及生产代码与 Stream Dockerfile |
| AC-002 | re_verified | 源码/config/schemas/scripts grep 无 `CBROWSER_TURN`/`SELKIES_TURN`/`rtc_config`/`ice_restart`/`TURN_` 引用；`tests/unit` 474 passed，`tests/integration` 79 passed |
| AC-003 | re_verified | `server.py:283-309` 升级前拒绝顺序；`tests/integration` 79 passed |
| AC-004 | re_verified | `tests/unit` 474 passed，含心跳/仲裁循环监督与退避重启用例 |
| AC-005 | re_verified | 配额/断连 400 校验、Viewer 限流、帧上限、统一 `read_secret_file`（minimum_bytes=32）；unit/integration 通过 |
| AC-006 | re_verified | `tests/unit` 474 passed，含 schema 漂移守卫 |
| AC-007 | re_verified | 前端 Vitest 126 passed；`test_frontend_adapter_build.py`/`test_frontend_build_wiring.py` 12 passed；探针注入顺序静态核对为 probe → adapter |
| AC-008 | re_verified | 前端 Vitest 126 passed，覆盖 Web Locks 专门诊断、401、监听释放 |
| AC-009 | re_verified | f015/f016 两处文档已与实现/Dockerfile 对齐；抽查 ADR 013、Superseded、计划 §8.4/§19.3 替代标记与 gateway.md 错误码表 |

coverage = 8 / 9

### 结论

- 前轮 finding 复核：f015、f016 均已消除；f001-f014 仍消除；未采信 note 处置表，结论以当前 diff、代码与测试结果为准。
- 本轮新发现：0 条。
- 未进表的提示：`tests/fixtures/frontend_probe/adapter_probe.py:57` 的 `index = selkies_index` 为无意义别名（纯风格）；`tests/` 下仍有引用已删除模块的 `__pycache__/*.pyc`（构建缓存，非源码）。文件过大与圈复杂度同 Round 4，本轮无变化。无范围外行为。
- 总体判断：PASS。Round 4 的两个 minor 均已按建议修复且与实现一致；本轮改动仅文档与测试夹具/守卫，生产代码未变，unit 474 / integration 79 / 前端 Vitest 126 全绿，无未解决 critical / important。
- 系统性 follow-up：无。

verdict: PASS

## Round 6 (2026-11-03T01:58:00+08:00)

reviewed_scope: 10dbf23b358176db

本轮为 committed execution tip `0b0881e`（first parent = `9ee4a11`）的 evidence-repair 复核。Round 5 记录的 `reviewed_scope: 56bd9048…` 是 01:36 修复前渲染的旧指纹，与当前交付内容不一致，`check_review_status.py` 报 `review_scope=stale`；本报告不沿用 Round 5 的指纹结论，按当前 tip 重扫全量 diff、finding 与门禁。`git status --short` 为空，交付内容全部在 `0b0881e` 中。

### 前轮 finding 复核

- `t015_code_f001` 仍已消除。`src/backend/cbrowser/gateway/server.py:282-309` 在 `ws.prepare()` 前完成查询参数身份、令牌与 API 实例绑定校验，失败返回 400/401/403；本轮重跑 `tests/integration` 79 passed。
- `t015_code_f002` 仍已消除。`server.py:179-191`、`:232-239` 对非对象 body 与非法字段统一返回 400；集成测试覆盖数组、字符串 body 与越界配额。
- `t015_code_f003` 仍已消除。`src/frontend/src/features/browser-session/useBrowserSession.ts:237-244` 用 `webLocksUnavailableRef` 抑制后续 `CBROWSER_WS_CLOSE`；本轮重跑前端 Vitest 126 passed。
- `t015_code_f004` 仍已消除。`src/backend/cbrowser/gateway/registry.py:144-152` 在键数超过 1024 时先清过期键再按插入顺序淘汰，键空间有硬上限。
- `t015_code_f005` 仍已消除。全仓源码无 `ProtocolEnvelope` / `dump_agent_envelope`；本轮以 pydantic+aiohttp 环境验证 `cbrowser.stream_agent.__all__` 为 17 项、无重复、经 `__getattr__` 全部可解析。
- `t015_code_f006` 仍已消除。`docs/blueprint/gateway.md:21-23` 为 `AgentRegisterEnvelope(action=register)` 与升级前 HTTP 403，`docs/blueprint/architecture.md:17` 指向 5.4。
- `t015_code_f007` 仍已消除。全仓无 `runtimeStatusUrl`、`runtimeCheckFailed`、`(data as any).state`。
- `t015_code_f008` 仍已消除。`gateway/server.py:73-79` 与 `supervisor/agent_credentials.py:15-20` 均经 `read_secret_file`。
- `t015_code_f009` 仍已消除。`docs/blueprint/gateway.md:62-63` 的 quota/disconnect 错误码已含 400，与 `server.py:179-191`、`:232-239` 一致。
- `t015_code_f010` 仍已消除。`stream_agent/config.py:204-206` 与 `supervisor/runner.py:85-90` 均经 `read_secret_file(minimum_bytes=32)`。
- `t015_code_f011` 仍已消除（静态复核）。`config/docker/stream_runtime/Dockerfile:52` 含 `COPY src/backend/cbrowser/secret_files.py`，`stream_agent/config.py:14` 的导入有对应文件；本轮未重建 Stream 镜像，Round 4 的重建镜像 + 直连媒体 E2E 证据仍适用。
- `t015_code_f012` 仍已消除。`stream_agent/__init__.py:84-94` 的导出元组单层缩进且无重复项。
- `t015_code_f013` 仍已消除。四处凭证读取均为 `minimum_bytes=32`（`stream_agent/config.py:205`、`supervisor/agent_credentials.py:16`、`supervisor/runner.py:86`、`gateway/server.py:76`）。
- `t015_code_f014` 仍已消除。`docs/blueprint/frontend.md:25` 与实际 script 注入一致。
- `t015_code_f015` 仍已消除。`docs/guides/stream_runtime_validation.md:8` 的构建上下文清单已含 `cbrowser/secret_files.py`。
- `t015_code_f016` 仍已消除。`docs/archive/tasks/t015_v2_media_link_simplification/task.md:63` 已改为复制后的 Selkies index 于 adapter 前注入探针。

### 本轮新发现

#### t015_code_f017 - Selkies credentials 文件在 Stream Agent 侧未走统一密钥读取器

- 严重度：minor
- 锚点：AC-005「所有密钥文件经统一的权限与长度校验读取」；行为缺口：直接构造 `StreamAgentConfig` 时 0644 权限的 credentials 文件被接受。
- 位置：`src/backend/cbrowser/stream_agent/config.py:252-265`
- 问题：`CBROWSER_SELKIES_CREDENTIALS_FILE` 经 `path.read_text()` + `json.loads` 读取，绕过 `read_secret_file` 的 group/other 权限校验；`controller_token` 字段只要求 ≥8 字符，而同族凭证读取统一要求 ≥32。生产挂载路径有 `supervisor/docker_adapter.py:753-756` 在挂载前拒绝非 0600 文件，因此无可观测的生产绕过；但我用 `from_env()` + 0644 credentials + 8 字符 controller token 直接构造配置，启动成功并接受该 token，属 Round 1 f008 / Round 2 f010 同类收尾。
- 建议：先 `read_secret_file(path, label="Selkies credentials", minimum_bytes=32)` 取原文再 `json.loads`（或至少 stat 检查 `st_mode & 0o077`），并把 controller token 最低长度对齐 32。

### AC 复验方式

| AC | 类别 | 证据 |
|---|---|---|
| AC-001 | trust_prior | 依赖 s011/d026 的真实 Chrome + OrbStack 证据；本轮直接核验 `<home>/kar/code/.scratch/s011/basetemp/test_s011_direct_media_matrix0/run_3af865e5/media_proof.json` 的 `no_turn_topology=true`、两页 127.0.0.1 host/udp 候选、帧与音频增长、可见性/复制标签/resume/IME 记录，但未重跑媒体部署 |
| AC-002 | re_verified | 全仓 grep 无 TURN/coturn/rtc_config/ice_transport 引用；`tests/unit` 474 passed，`tests/integration` 79 passed |
| AC-003 | re_verified | `server.py:282-309` 升级前 400/401/403 拒绝；`tests/integration` 79 passed |
| AC-004 | re_verified | 心跳与捕获仲裁逐次隔离异常并由 supervised 循环退避重启；`tests/unit` 474 passed |
| AC-005 | re_verified（有 f017 minor） | 配额/断连 400、Viewer 限流 429、WS 帧上限、心跳超时启动校验均在位；四处密钥读取统一为 32 字节；Selkies credentials JSON 见 f017 |
| AC-006 | re_verified | schema 按 action 判别并覆盖 register/heartbeat/quota/ack/tunnel；`tests/unit` 474 passed（含漂移守卫） |
| AC-007 | re_verified | 前端 Vitest 126 passed；`test_frontend_adapter_build.py`/`test_frontend_build_wiring.py` 12 passed；dist 产物含 `__SELKIES_STREAMING_MODE__`/`__getWebRTCStats` 且无旧测试全局 |
| AC-008 | re_verified | 前端 Vitest 126 passed，覆盖 Web Locks 专门诊断、401、监听释放与重连清理 |
| AC-009 | re_verified | ADR 013、Superseded、计划 §8.4/§19.3 替代标记、adoption D1、gateway.md 错误码与 5.4 引用均复核一致 |

coverage = 8 / 9

### 结论

- 前轮 finding 复核：f001-f016 全部仍消除（f011 为静态复核 + 沿用 Round 4 重建镜像 E2E 证据；其余按当前代码与重跑测试复核）。
- 本轮新发现：1 条（0 blocking，1 minor）。
- 未进表的提示：
  - 文件过大：`src/backend/cbrowser/stream_agent/policy.py` 746 行（本 task 净增）、`src/frontend/src/features/browser-session/useBrowserSession.ts` 446 行（净增）、`docs/spikes/s011_direct_media_validation/code/direct_media_probe.py` 1632 行（一次性 spike 探针）；`stream_agent/agent.py` 1086 行、`gateway/server.py` 683 行本 task 净减，均不单独进表。
  - 圈复杂度：radon 报 `LiveCapturePolicyAgent.reconcile_capture_state` E、`StreamAgent._viewer_upstream_worker` E、`connect_and_run` C 等；本 task 未给这些函数新增分支（`connect_and_run` 仅改注册 URL 与监督包装），按规则只提示。
  - `BrowserSessionView.tsx:31-35` 缩进不一致，属纯风格。
  - `docs/archive/tasks/t015_v2_media_link_simplification/note.md` 与 `handoff.json` 仍写 unit 473，当前实测 474；流程证据滞后，非实现缺陷。
  - `docs/findings/d026_direct_media_local_only.md` 的证据路径 `.scratch/s011/...` 在本 worktree 不可解析，实际文件位于 `<home>/kar/code/.scratch/s011/...`；建议注明相对根或改为可解析路径。
- 总体判断：PASS。当前 tip 无未解决 critical / important；唯一新发现 f017 为非阻断 minor，前轮 16 条 finding 均已消除。
- 系统性 follow-up：无。

verdict: PASS
