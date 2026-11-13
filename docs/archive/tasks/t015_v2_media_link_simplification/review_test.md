# Task review t015（reviewer_focus: 测试）

- task：`t015_v2_media_link_simplification`
- spec：`docs/tasks/t015_v2_media_link_simplification/task.md`
- diff_anchor：`9ee4a1146be8e42bc552f1150beb8063582ab466`
- target：`git -C '<repo>_t015' diff 9ee4a1146be8e42bc552f1150beb8063582ab466`
- round：1
- reviewed_at：2026-11-02T23:50:52+08:00

reviewed_scope: b0ef991a0fb64f9c

## Findings

### t015_test_f001 - 生产 adapter 构建守卫仍断言已删除的测试全局，测试实际失败

- 严重度：important
- 锚点：AC-007（生产 adapter 不暴露测试全局；E2E/单测应验证生产契约）
- 位置：`tests/e2e/test_frontend_adapter_build.py:55`、`tests/e2e/test_frontend_adapter_build.py:62`
- 问题：本任务已删除 `adapter.ts` 中的 `__cbrowserAdapterSource` 与 `__cbrowserShimInstalled`，构建产物同样不含这两个字符串；`scripts/verify_frontend_dist.py:23` 的 marker 也已改为 `("__SELKIES_STREAMING_MODE__", "__getWebRTCStats")`，但该测试只把第 54 行改成检查 `__getWebRTCStats`，第 55/62 行仍检查旧 marker。实际复跑 `pytest tests/e2e/test_frontend_adapter_build.py -q` 得到 `1 failed, 3 passed`，失败在 `adapter.ts` 路径断言，随后 `__cbrowserShimInstalled` 断言也不可能通过。该测试当前既无法验证构建产物，又与 AC-007 的“不暴露测试全局”相反。
- 建议：将第 55 行改为检查生产契约 marker（例如 `__getWebRTCStats` 与 `__SELKIES_STREAMING_MODE__`，或 `scripts/verify_frontend_dist.py` 的同一组 marker），删除第 62 行旧全局断言；若仍需验证构建来源，用构建配置或 source map 元数据代替已删除的运行时全局。

### t015_test_f002 - Gateway auth E2E 仍读取已删除的 `harness.keys["turn"]`，启动后会 KeyError

- 严重度：important
- 锚点：AC-002（对应测试与夹具同步移除 TURN），以及 AC-001 的认证 E2E 可运行性
- 位置：`tests/e2e/test_gateway_ac001_auth_e2e.py:84`；`tests/fixtures/gateway_probe/topology.py:145-151`
- 问题：`GatewayTopologyHarness._init_dirs_and_secrets` 现在只写入 `supervisor`、`agent`、`gateway`、`gateway_api` 四个 key，`harness.keys` 中不再有 `turn`。`test_ac001_https_login_cookie_flags_csrf_and_viewer_ws_gates` 在完成登录后仍执行 `assert harness.keys["turn"] not in login_json_str`，该测试一旦启动拓扑就会因 `KeyError: 'turn'` 中断；这也是 `docs/blueprint/testing.md` 的 Gateway 验证命令会直接拉起的测试。
- 建议：删除该断言，或改成明确验证新语义 `assert "turn" not in harness.keys`；同时以该测试为入口检查其他仍引用 TURN 夹具的 e2e 文件。

### t015_test_f003 - 前端 E2E 仍依赖 adapter 已删除的测试全局，没有按测试策略注入探针

- 严重度：important
- 锚点：AC-007（E2E 与单元测试通过测试自身注入的探针获得同等证据）；spec 测试策略“adapter 测试钩子迁移：E2E 用 Playwright add_init_script 注入探针”
- 位置：
  - `tests/e2e/test_frontend_app_e2e.py:196`、`:665`、`:725`（`__sentDataChannelMessages`）、`:876`（`__last_ws`）、`:905`（`__activePC`）
  - `tests/e2e/test_frontend_session_e2e.py:91`、`:311`（`__sentDataChannelMessages`）
  - `tests/e2e/test_frontend_media_e2e.py:187`（`__sentDataChannelMessages`）
- 问题：这些全局原本由 `adapter.ts` 写入；本任务已删除写入逻辑，`adapter.ts:27-36` 只保留 `installedWindows` 与 `__SELKIES_STREAMING_MODE__`，公开契约仅剩 `__getWebRTCStats`（`adapter.ts:232`）。前端 e2e 使用 `prepare_frontend_app` / `prepare_frontend_host` 时直接复制生产 `dist`（`tests/fixtures/frontend_app_probe/harness.py:21-51`、`tests/fixtures/frontend_probe/host_builder.py:33-96`），没有注入探针；`gateway_probe/selkies_assets.py` 里的同名 shim 只用于 Gateway 拓扑，不会进入这些前端拓扑。因此：
  - `test_frontend_app_e2e.py:876` 的 socket 切断不会发生，等待新 HELLO 超时；`:905` 的 `__activePC` 为空，`iframe_eval` 返回 false 导致断言失败；`:665` 因 `|| []` 变成空列表，只会空泛地通过“没有 resize 报文”，没有真实证据。
  - `test_frontend_session_e2e.py` 与 `test_frontend_media_e2e.py` 等待 `STOP_VIDEO`/`STOP_AUDIO` 等报文时，`__sentDataChannelMessages` 不存在，等待会超时；`test_frontend_session_e2e.py:311` 的“B 未收到 A 的 STOP_AUDIO”也会因为恒为空列表而变成假阴性。
- 建议：按 spec 测试策略在 Playwright 层统一注入探针（例如在 harness 的 `add_init_script` 中包装原生 `RTCDataChannel.send`、`WebSocket`、`RTCPeerConnection`，提供 `__sentDataChannelMessages`、`__last_ws`、`__activePC`），或把这些断言改为使用 `__getWebRTCStats` 等生产契约；不要保留对已删除生产全局的读取。修好后应重跑 `test_frontend_app_e2e.py`、`test_frontend_session_e2e.py`、`test_frontend_media_e2e.py`。

### t015_test_f004 - AC-002 的测试与文档仍残留 TURN 配置引用

- 严重度：minor
- 锚点：AC-002（对应配置项、夹具、测试与文档同步移除）
- 位置：`tests/unit/test_stream_display_config.py:20-21`、`tests/unit/test_stream_agent_lifecycle.py:136-137`、`docs/blueprint/testing.md:93`
- 问题：运行时配置已删除 `SELKIES_TURN_HOST`/`SELKIES_TURN_PORT`，但两个单元测试仍以这两项构造环境；`testing.md` 的专项验证表仍保留 s008 的 `coturn` TURN 探针行。它们不会导致当前测试失败，但与 AC-002 的“测试与文档同步移除”不一致，也容易让后续维护误以为 TURN 仍是有效配置。
- 建议：删除测试中的 TURN 环境变量，保留明确验证“不存在 TURN 字段”的负向断言；`testing.md` 的旧探针行标注历史或移入 archive。

### t015_test_f005 - AC-004 的“循环意外退出后告警并按退避重启”没有测试

- 严重度：minor
- 锚点：AC-004（循环任务意外退出时告警并按退避重启）
- 位置：`src/backend/cbrowser/stream_agent/policy.py:300-324`、`src/backend/cbrowser/stream_agent/agent.py:358-377`；对应测试 `tests/unit/test_stream_agent_lifecycle.py:311-355`、`tests/unit/test_stream_runtime.py:168-193`
- 问题：新增测试只验证 `_heartbeat_loop` 与 `_reconciliation_loop` 内部单次异常后继续（inner loop catch），没有验证外层 `_start_supervised_loop` / heartbeat `supervised()` 在循环任务意外退出时记录错误并以 1/2/4...30 秒退避重启。当前 AC-004 已打勾，但该子句没有任何测试证据；监督层若写错（例如异常后直接返回）现有测试仍全绿。
- 建议：新增单测直接驱动外层 supervised 包装：让 loop factory 第一次抛异常、之后返回/抛出，注入可控 `sleep`，断言错误日志出现、重试次数和 backoff 序列；不要只测内层 loop 的 catch。

### t015_test_f006 - AC-008 的 401 跳转与监听器释放只有弱证据

- 严重度：minor
- 锚点：AC-008（会话过期跳转登录；所有事件监听在完成与超时路径上都被释放）
- 位置：`src/frontend/src/features/browser-session/BrowserSessionView.test.tsx:100-110`；`src/frontend/src/features/browser-session/useBrowserSession.ts:407-415`
- 问题：`AC-008: expired session is left to the auth layer` 注入的是伪造 `ApiClient` 对象，直接让 `getRuntime` 抛出 `ApiError(401)`，只断言页面不显示 `session-stage-title` / `session-error-message`，没有验证统一客户端的 `onUnauthorized` 回调、登录路由跳转或 `next` 参数；这只能证明组件“不显示错误”，不能证明“跳转登录”。另外测试没有任何断言检查 `useBrowserSession` 的 `message`/`resume`/`pageshow` 监听器在完成和超时路径被移除，AC-008 的“所有事件监听被释放”没有测试证据。现有 `auth_guard.test.tsx` 覆盖的是 App 层的 mutation 401，不是本会话页的 `getRuntime` 路径。
- 建议：用真实的 `ApiClient`（或至少验证其 `onUnauthorized` 被调用）测试 `getRuntime` 401 后的 auth 层行为；为 `useBrowserSession` 增加 unmount/超时测试，断言 `removeEventListener` 对应监听器被调用，或加一个 E2E 断言会话页离开后监听器不再响应。

### t015_test_f007 - 重构删除的 E2E 覆盖没有等价补回

- 严重度：minor
- 锚点：refactor 型 task 的覆盖保持；AC-002 只要求移除 TURN，不应连带删除非 TURN 覆盖
- 位置：删除的 `tests/e2e/test_supervisor_infrastructure_network_e2e.py`（整文件）；`tests/e2e/test_stream_runtime_e2e.py` 删除的 `control_proof` 块（旧文件约 `:1187-1333`）
- 问题：`test_supervisor_infrastructure_network_e2e.py` 的 `test_attach_profile_infra_authoritative_gateway_port_and_isolation_e2e` 与 `test_network_cleanup_lifecycle_and_unknown_endpoint_rejection_e2e` 包含 Gateway 动态加入媒体网络、跨 Profile 网络负向隔离、运行时容器仍附着时清理拒绝、未知端点清理拒绝；这些在删除 coturn 后仍有意义。`test_stream_runtime_e2e.py` 删除的 `control_proof` 块覆盖 Supervisor quota 下发到真实 Stream、客户端不能越过 FPS cap、布局尺寸不变、motion/static FPS 切换和 Stream CPU policy。现有单元测试覆盖了部分策略/协议，但没有等价的高层集成证据，属于覆盖收缩。
- 建议：将上述测试改写为无 coturn 的直接拓扑并保留（尤其 Gateway 动态网络加入、隔离负向、清理拒绝、quota/帧率端到端）；如确认属于 t016/t018 范围，在 task/note 明确写明转交并给出 tid，不要只删除不补充。

## 结论

- 前轮 finding 复核：本轮为 Round 1，无前轮 finding。
- 改测方向复核：无把旧断言预期改成当前实现输出的系统性改测；TURN/schema/直连相关修改属于 spec 变更。但 `test_frontend_adapter_build.py:54-62` 只改了一半 marker，导致测试本身失败，属于改测不完整。
- 本轮新发现：7 条（3 important，4 minor）。
- 未进表的提示：`pytest tests/unit -q` 471 passed；`pytest tests/integration/test_gateway_signaling.py tests/integration/test_gateway_control.py tests/integration/test_gateway_fixtures.py -q` 12 passed；`npx vitest run src/features/browser-session/BrowserSessionView.test.tsx src/features/browser-session/adapter_restart.test.ts` 30 passed；`pytest tests/e2e/test_frontend_adapter_build.py -q` 1 failed。前端 e2e 未在当前环境实际启动 Docker 拓扑，f003 通过源码/夹具静态核对判定；建议实施方在修后至少运行 `test_frontend_app_e2e.py`、`test_frontend_session_e2e.py`、`test_frontend_media_e2e.py`。
- 总体判断：FAIL。f001 使现有构建守卫失败，f003 使前端 mute/resume/reconnect E2E 读取已删除的测试全局并假绿或超时，f002 使 Gateway 认证 E2E 启动后 KeyError；AC-007 的测试策略未闭环。
- 系统性 follow-up：无新增；测试体系整体整改已有 t018，本报告的 f003/f007 属于本 task 必须收口的前端测试迁移与覆盖收缩，不重复登记到 t018。

### AC 复验方式

| AC | 类别 | 证据 |
|---|---|---|
| AC-001 | trust_prior | 依赖 s011/d026 的真实 Chrome + OrbStack 证据与 `docs/spikes/s011_direct_media_validation/report.md`；本机未重跑完整媒体拓扑 |
| AC-002 | re_verified | grep 检查运行时配置/协议/夹具/测试；`test_gateway_config.py` 删除字段断言通过；但仍有 f004 残留测试引用 |
| AC-003 | re_verified | 重跑 `test_gateway_signaling.py` 的拒绝、隔离与替换用例，12 passed |
| AC-004 | re_verified（有缺口 f005） | 重跑 `test_stream_agent_lifecycle.py`、`test_stream_runtime.py`，仅覆盖 inner loop 单次异常 |
| AC-005 | re_verified | 重跑 `test_gateway_control.py`、`test_gateway_config.py` 及 `test_gateway_signaling.py` 的 quota/限流/超限帧用例 |
| AC-006 | re_verified | 重跑 `test_stream_protocol_schema.py`、`test_stream_agent_protocol_v2.py`；schema 漂移守卫通过 |
| AC-007 | re_verified（未达成） | 重跑 adapter 单测通过；但 `test_frontend_adapter_build.py` 失败，前端 E2E 仍读已删除全局（f001/f003） |
| AC-008 | re_verified（有缺口 f006） | 重跑 `BrowserSessionView.test.tsx`；401 跳转与监听器释放仍无有效断言 |
| AC-009 | re_verified | grep 确认 ADR 013、Superseded、计划替代标记与 adoption D1 已更新 |

coverage = 8 / 9

verdict: FAIL

## Round 2 (2026-11-03T01:03:21+08:00)

reviewed_scope: 84ba3827ce27180a

### 前轮 finding 复核

- t015_test_f001 已消除：`tests/e2e/test_frontend_adapter_build.py:53-55` 已改为断言 `__getWebRTCStats` 与 `__SELKIES_STREAMING_MODE__`，旧全局断言已删除；实测 `pytest tests/e2e/test_frontend_adapter_build.py -q` 为 `4 passed`。
- t015_test_f002 已消除（静态复核，未启动 Docker E2E）：`tests/e2e/test_gateway_ac001_auth_e2e.py:84` 已改为 `assert "turn" not in harness.keys`；`tests/fixtures/gateway_probe/topology.py:145` 只创建 `supervisor`、`agent`、`gateway`、`gateway_api` 四个 key，测试中已无 `harness.keys["turn"]` 读取，原 KeyError 路径消失。
- t015_test_f003 已消除（静态复核 + 单元测试）：新增 `tests/fixtures/frontend_probe/adapter_probe.py:9-65` 测试探针，`tests/fixtures/frontend_probe/host_builder.py:101` 与 `tests/fixtures/frontend_app_probe/harness.py:42` 均向复制后的 Selkies index 注入；`__sentDataChannelMessages`、`__last_ws`、`__activePC` 不再来自生产 adapter，前端 E2E 引用已能对应测试侧探针。`npm test --prefix src/frontend -- --run` 为 `126 passed`；本机无 Docker E2E 镜像/缓存，未实际启动该拓扑。
- t015_test_f004 已消除：`tests/unit/test_stream_display_config.py:13-20` 已删除 `SELKIES_TURN_*` 环境变量；`test_stream_agent_lifecycle.py:164-179` 改为负向断言 `turn_host`/`turn_port` 不存在；`docs/blueprint/testing.md:72,120` 已改为“无 coturn/TURN”。
- t015_test_f005 已按主体消除：`tests/unit/test_stream_agent_lifecycle.py:603` 与 `tests/unit/test_stream_runtime.py:197` 新增受控 `sleep` 的外层 supervised 重启测试，覆盖循环意外退出后再次执行；仍未断言错误日志与 2/4/8 秒退避递增，属 minor 残余。
- t015_test_f006 已按主体消除：`BrowserSessionView.test.tsx:97-114` 改用真实 `ApiClient` 并断言 `onUnauthorized`，`:116-124` 增加 unmount 监听器释放断言；timeout 完成路径的监听器释放仍未单独断言，属 minor 残余。
- t015_test_f007 仍为遗留 minor：`docs/pending/todo/p016_restore_supervisor_network_and_quota_e2e.md` 已登记恢复 Supervisor 网络隔离与 Stream 配额 E2E，未在本 task 内补回，符合“转交并给出 tid”的收口方式。

### 本轮新发现

#### t015_test_f008 - 前端 E2E 探针在 adapter 过滤前记录 DataChannel 报文，resize 断言不再验证真实发送边界

- 严重度：minor
- 锚点：AC-007（E2E 通过测试自身注入的探针获得同等证据）；AC-001 的分辨率不变行为（辅助证据）
- 位置：`tests/fixtures/frontend_probe/adapter_probe.py:39-48`、`tests/fixtures/frontend_probe/adapter_probe.py:64`、`tests/e2e/test_frontend_app_e2e.py:663-671`
- 问题：`inject_adapter_probe` 把探针插在 `selkies_adapter.js` 之后，探针包裹的是 adapter 已经替换过的 `RTCDataChannel.prototype.send`。探针先 `push` 再调用 adapter 的 send，因此 `__sentDataChannelMessages` 记录的是客户端发送尝试，包含已经被 adapter 丢弃的 `r,` 报文；而 `test_frontend_app_e2e.py:665-671` 把“无 `r,`”当作 resize 过滤证据。结果是：若官方 Selkies 客户端在视口变化时尝试发送 resize 包，即使 adapter 正确丢弃，该 E2E 也会误报失败；若客户端不尝试，该断言又不验证 adapter 的真实过滤边界。实际边界目前由 `adapter_restart.test.ts` 的 `blocks client resize packets...` 单测覆盖，故不构成 AC 未覆盖，但该 E2E 证据不等价于旧行为。
- 建议：把探针注入到 `selkies_adapter.js` 之前（让 adapter 包裹探针而非相反），或在探针中只记录实际到达原生 send 的报文，并保留 adapter 边界单测作为主证据。

### 结论

- 前轮 finding 复核：f001、f002、f003、f004 已消除；f005、f006 主体已修，仍有 minor 残余；f007 已转 p016。
- 改测方向复核：无“迁就实现”的改测。TURN/ICE 相关测试删除对应 AC-002/ADR 013 的规格变更，旧语义测试未就地改为新实现输出；前端测试全局删除后由测试侧探针与生产契约替代。
- 本轮新发现：1 条（minor）。
- 未进表的提示：AC-001 的真实 Docker/Chrome 媒体矩阵仍依赖 s011/d026 与 E2E 手工运行，本机未启动完整拓扑；`pytest tests/e2e/test_frontend_adapter_build.py`、`npm test`、`pytest tests/unit`（473 passed）、`pytest tests/integration`（79 passed）均通过。
- 总体判断：前轮 blocking 均已消除，当前无未解决的 critical / important；仅剩 f005/f006 的 minor 残余与 f008 新 minor，可通过。
- 系统性 follow-up：无新增；f007 仍由 p016 跟踪。

### AC 复验方式

| AC | 类别 | 证据 |
|---|---|---|
| AC-001 | trust_prior | 依赖 s011/d026 的真实 Chrome + OrbStack 证据；本机未启动 Docker 媒体拓扑，新增 E2E 仅做静态核对 |
| AC-002 | re_verified | grep 无运行时 TURN/coturn 引用；`tests/unit` 全量通过；负向断言覆盖配置与协议字段移除 |
| AC-003 | re_verified | `pytest tests/integration` 79 passed，含握手拒绝、隔离、替换用例 |
| AC-004 | re_verified（有 minor 提示） | 重跑新增 heartbeat/policy supervised 重启测试通过；未断言告警日志与完整退避序列 |
| AC-005 | re_verified | `test_gateway_config.py`、`test_gateway_control.py`、`test_gateway_signaling.py` 全量通过 |
| AC-006 | re_verified | `test_stream_protocol_schema.py`、`test_stream_agent_protocol_v2.py` 通过；schema 漂移守卫通过 |
| AC-007 | re_verified | adapter build `4 passed`、前端单测 `126 passed`；测试侧探针已注入，E2E 未启动 |
| AC-008 | re_verified | `BrowserSessionView.test.tsx` 覆盖 401 `onUnauthorized`、错误原因、Web Locks 诊断与 unmount 监听释放 |
| AC-009 | re_verified | grep 确认 ADR 013、Superseded 标记、计划替代标记与 adoption D1 已更新 |

coverage = 8 / 9

verdict: PASS

## Round 3 (2026-11-03T01:37:00+08:00)

reviewed_scope: 7619ff3a65c45c15

### 前轮 finding 复核

- t015_test_f001 已消除：`tests/e2e/test_frontend_adapter_build.py:53-55` 仍只断言生产 marker；本轮重跑 `pytest tests/e2e/test_frontend_adapter_build.py -q` 为 `4 passed`。
- t015_test_f002 已消除（静态复核，未启动 Docker E2E）：`tests/e2e/test_gateway_ac001_auth_e2e.py:84` 为 `assert "turn" not in harness.keys`；`tests/fixtures/gateway_probe/topology.py:145` 只创建四个非 TURN key，原 KeyError 路径消失。
- t015_test_f003 已消除（静态复核 + 前端单测，未启动 Docker 前端 E2E）：`tests/fixtures/frontend_probe/adapter_probe.py:54-65` 的 `inject_adapter_probe` 由 `tests/fixtures/frontend_app_probe/harness.py:42` 与 `tests/fixtures/frontend_probe/host_builder.py:101` 注入到复制后的 Selkies index；生产 adapter 不再写测试全局；`npm test --prefix src/frontend -- --run` 为 `126 passed`。
- t015_test_f004 已消除：`rg 'SELKIES_TURN|turn_secret|turn_host|turn_port'` 在 `tests`、`src/backend/cbrowser/gateway`、`src/backend/cbrowser/stream_agent` 只剩负向断言（`test_stream_agent_lifecycle.py:180-181`、`test_gateway_config.py:40`、`test_stream_agent_protocol_v2.py:57`），无 TURN 环境变量残留。
- t015_test_f005 minor 残余仍在：`test_supervised_heartbeat_task_restarts_after_fatal_exit`（`tests/unit/test_stream_agent_lifecycle.py:605-646`）与 `test_supervised_policy_loop_restarts_after_fatal_exit`（`tests/unit/test_stream_runtime.py:197-237`）只断言重启发生且首次退避为 `[1.0]`，未断言错误日志与 2/4/8 秒递增退避；不影响本轮 verdict。
- t015_test_f006 minor 残余仍在：`BrowserSessionView.test.tsx:116-124` 只覆盖 unmount 监听释放，未覆盖 timeout 完成路径；不影响本轮 verdict。
- t015_test_f007 已转 p016：`docs/pending/todo/p016_restore_supervisor_network_and_quota_e2e.md` 仍在，本 task 内未补回。
- t015_test_f008 已消除：`tests/fixtures/frontend_probe/adapter_probe.py:60-64` 将 `PROBE_TAG` 插到 `selkies_adapter.js` 之前；`PROBE_JS:39-49` 先包原生 `RTCDataChannel.prototype.send`，adapter 随后包探针，因此 `r,` 报文在到达探针前被 adapter 丢弃，`__sentDataChannelMessages` 只记录实际进入原生 send 的报文。本轮用临时副本回放注入得到 `probe_before_adapter=True`，并用 Node 模拟 adapter 后续包装，发送 `r,800,600` 与 `STOP_AUDIO` 后探针只记录 `["STOP_AUDIO"]`。E2E 拓扑未实跑。

### 本轮新发现

#### t015_test_f009 - testing.md 两个门禁命令仍引用本 task 已删除的测试文件

- 严重度：minor
- 锚点：AC-009（blueprint 与新测试布局一致）；可观测失败：按文档执行 Supervisor/前端门禁时 pytest 因文件不存在直接退出，剩余文件也不会运行
- 位置：`docs/blueprint/testing.md:141`（`tests/e2e/test_supervisor_infrastructure_network_e2e.py`）、`docs/blueprint/testing.md:170`（`tests/e2e/test_frontend_ice_failure_e2e.py`）
- 问题：本 task 删除了这两个测试文件（`git status` 中均为 `D`），但 `docs/blueprint/testing.md` 的两条门禁命令仍把它们列入参数。实际执行会得到 `ERROR: file or directory not found`，Supervisor 与 t007 前端门禁命令在跑任何用例前即失败；p016 只记录了覆盖恢复，不解决当前命令失效。
- 建议：从两条命令中移除已删除文件；若对应覆盖由 p016 恢复，在该 commands 附近注明恢复后加回，而不是保留不存在的路径。

#### t015_test_f010 - frontend 探针每次新建 PeerConnection 都重置 `__pcs`，与 gateway 探针语义不一致

- 严重度：minor
- 锚点：AC-007（E2E 通过测试自身注入的探针获得同等证据）；当前无测试读取 `__pcs`，不影响本轮 AC 证据
- 位置：`tests/fixtures/frontend_probe/adapter_probe.py:26`
- 问题：探针在每次 `RTCPeerConnection` 构造时执行 `window.__pcs = [pc]`，覆盖历史列表；`tests/fixtures/gateway_probe/selkies_assets.py:77-78` 的同类探针则是 `window.__pcs = window.__pcs || []; window.__pcs.push(pc)`。当前前端 E2E 只读 `__activePC` / `__last_ws` / `__sentDataChannelMessages`，所以未产生假绿；但一旦后续测试用 `__pcs` 断言多连接或重连后的 PeerConnection 数量，会只看到最后一个 PC，得到错误证据。
- 建议：改为首次初始化后 `push`，或删除未使用的 `__pcs`/`__inputChannel` 记录，避免留下语义不一致的探针接口。

#### t015_test_f011 - Stream 镜像缺 `secret_files.py` 的回归没有单元守卫

- 严重度：minor
- 锚点：AC-005（所有密钥文件经统一权限与长度校验读取）；同类打包回归
- 位置：`tests/unit/test_baseline_runtime_regressions.py:20-96`（只检查 supervisor/gateway/API fixture Dockerfile）、`config/docker/stream_runtime/Dockerfile:52`
- 问题：Round 3 代码审查发现 Stream 镜像漏 `COPY src/backend/cbrowser/secret_files.py`（t015_code_f011，critical），当前 Dockerfile 已补上；但 `test_baseline_runtime_regressions.py` 虽然以 “Packaging and Dockerfile integrity” 为职责，并为 supervisor/gateway/API fixture 断言同一行，没有对 `config/docker/stream_runtime/Dockerfile` 做对应断言。若该 COPY 再次丢失，473 条单元测试仍全绿，只能靠需重建镜像的 Stream E2E 暴露。
- 建议：新增 stream runtime packaging 测试，断言 pinned `FROM`、`COPY .../__init__.py`、`COPY .../secret_files.py`（以及 `stream_agent` 包），与其余三处 Dockerfile 守卫对齐。

### 结论

- 前轮 finding 复核：f001、f002、f003、f004、f008 已消除；f005、f006 主体已修，minor 残余仍在；f007 已转 p016。
- 改测方向复核：无。本轮只看到测试夹具为适配 `read_secret_file` 的 32 字节/0600 约束而更新了 secret 文件内容与权限，未把既有断言改成迁就实现的输出；探针顺序修改是把测试证据放回正确的系统边界，不是弱化断言。
- 本轮新发现：3 条（均为 minor）。
- 未进表的提示：本机未启动 Docker 前端/媒体 E2E，f002/f003/f008 的拓扑行为为静态复核 + 探针回放；AC-001 的真实 Chrome/OrbStack 矩阵仍依赖 s011/d026。`git status` 的未跟踪项只有已归档 task 工作区，属于流程文件，实现交付文件均已在 diff 中可见。重跑 `pytest tests/unit` 473 passed、`pytest tests/integration` 79 passed、`pytest tests/e2e/test_frontend_adapter_build.py` 4 passed、前端 Vitest 126 passed，secret 相关定向用例 29 passed；另手工验证 Stream Agent 会拒绝 18 字节 secret（`at least 32 bytes`）与 0644 secret（`group or others`）。
- 总体判断：前轮 blocking 均已消除；本轮只有 minor（测试文档失效命令、探针 `__pcs` 语义、Stream 打包守卫缺口），测试轴可通过。
- 系统性 follow-up：无新增；f007 仍由 p016 跟踪，f009/f011 建议本 task 收口时修正。

### AC 复验方式

| AC | 类别 | 证据 |
|---|---|---|
| AC-001 | trust_prior | 依赖 s011/d026 的真实 Chrome + OrbStack 无 coturn 直连证据；本机未启动 Docker 媒体拓扑 |
| AC-002 | re_verified | grep 无运行时 TURN/coturn 引用；unit 473 passed、integration 79 passed；负向断言覆盖配置与协议字段移除 |
| AC-003 | re_verified | `pytest tests/integration` 79 passed，含握手拒绝、注册表隔离与替换用例 |
| AC-004 | re_verified（有 minor 提示） | supervised heartbeat/policy 重启测试通过；未断言错误日志与完整退避序列（f005 残余） |
| AC-005 | re_verified | `test_gateway_config.py`、`test_gateway_control.py`、`test_gateway_signaling.py`、`test_secret_file_permissions.py` 通过；手工验证 Stream Agent 拒绝短 secret 与 0644 secret |
| AC-006 | re_verified | `test_stream_protocol_schema.py`、`test_stream_agent_protocol_v2.py` 通过；schema 漂移守卫通过 |
| AC-007 | re_verified（E2E 未实跑） | adapter build 4 passed、前端 Vitest 126 passed；探针注入顺序用临时副本与 Node 回放验证，`__sentDataChannelMessages` 只记录 adapter 放行报文 |
| AC-008 | re_verified（有 minor 提示） | `BrowserSessionView.test.tsx` 覆盖 401 `onUnauthorized`、runtime_not_ready、Web Locks 诊断与 unmount 监听释放；timeout 路径未单独断言（f006 残余） |
| AC-009 | re_verified（有 minor 提示） | ADR 013、Superseded、计划替代标记与 adoption D1 已更新；testing.md 两条命令仍引用已删除测试文件（f009） |

coverage = 8 / 9

verdict: PASS

## Round 4 (2026-11-03T01:42:30+08:00)

reviewed_scope: 56bd90480361b993

### 前轮 finding 复核

- t015_test_f009 已消除：`docs/blueprint/testing.md:141` 的 Supervisor 命令已移除 `tests/e2e/test_supervisor_infrastructure_network_e2e.py`；`:168` 的前端命令已移除 `tests/e2e/test_frontend_ice_failure_e2e.py`；`:76` 的 Stream 命令同步移除了已删除的 ICE/relay 用例并加入实际存在的 `test_stream_selkies_tokens_e2e.py`。用脚本抽取 `testing.md` 中全部 `tests/...` 路径并逐一 `test -f`，无缺失项。
- t015_test_f010 已消除：`tests/fixtures/frontend_probe/adapter_probe.py:26-27` 已改为 `window.__pcs = window.__pcs || []; window.__pcs.push(pc);`，与 `tests/fixtures/gateway_probe/selkies_assets.py:77-78` 语义一致；临时目录回放 `inject_adapter_probe` 确认探针仍在 `selkies_adapter.js` 之前注入，且探针 JS 含 `push` 语义。
- t015_test_f011 已消除：`tests/unit/test_baseline_runtime_regressions.py:54-65` 新增 `test_stream_runtime_packaging_integrity`，断言 pinned `FROM` 与 `__init__.py`、`secret_files.py`、`stream_agent`、`entrypoint.sh` 四个 COPY；`config/docker/stream_runtime/Dockerfile:52` 已包含 `secret_files.py`，且 `stream_agent/config.py:14` 确实 import 该模块。重跑该文件 `9 passed`。
- t015_test_f001～f004、f008 复核未见回归：`pytest tests/e2e/test_frontend_adapter_build.py -q` 4 passed；`tests/e2e/test_gateway_ac001_auth_e2e.py:84` 仍为 `assert "turn" not in harness.keys`；探针注入点与前端 E2E 引用保持一致；`rg 'SELKIES_TURN|turn_secret|turn_host|turn_port'` 仍只命中负向断言。
- t015_test_f005、f006 仍为既有 minor 残余，未扩大：`test_supervised_heartbeat_task_restarts_after_fatal_exit`（`tests/unit/test_stream_agent_lifecycle.py:605-646`）与 `test_supervised_policy_loop_restarts_after_fatal_exit`（`tests/unit/test_stream_runtime.py:197-237`）仍只断言首次退避 `[1.0]`，未覆盖告警日志与后续递增退避；`BrowserSessionView.test.tsx:116-124` 仍只覆盖 unmount 监听释放。二者不影响本轮 verdict。
- t015_test_f007 仍由 p016 跟踪，未在本 task 内补回。

### 本轮新发现

- 无。本轮改动仅涉及上述三个 minor 修复及配套指南更新，未新增或弱化任何测试断言。

### 结论

- 前轮 finding 复核：f009、f010、f011 已消除；f001～f004、f008 未见回归；f005、f006 的 minor 残余保持原状；f007 已转 p016。
- 改测方向复核：无。新增的 Stream 打包守卫是新增覆盖而非迁就实现；探针 `__pcs` 改动恢复与既有探针一致的语义；testing.md 只删除不存在路径。
- 本轮新发现：0 条。
- 未进表的提示：`pytest tests/unit` 474 passed、`pytest tests/integration` 79 passed、`pytest tests/e2e/test_frontend_adapter_build.py` 4 passed、前端 Vitest 126 passed、前端 E2E 三个文件 `--collect-only` 12 collected。Docker 媒体/前端 E2E 拓扑未在本机实跑，AC-001 仍依赖 s011/d026。testing.md 删除 Supervisor 网络 E2E 后未就近注明 p016 恢复项，属可选文档提示。
- 总体判断：前轮 blocker 均已消除，本轮无新 blocker；仅存在既有 minor 残余，测试轴可通过。
- 系统性 follow-up：无新增；f007 由 p016 跟踪。

### AC 复验方式

| AC | 类别 | 证据 |
|---|---|---|
| AC-001 | trust_prior | 依赖 s011/d026 的真实 Chrome + OrbStack 无 coturn 直连证据；本机未启动 Docker 媒体拓扑 |
| AC-002 | re_verified | grep 无运行时 TURN/coturn 引用；unit 474 passed、integration 79 passed；负向断言覆盖配置与协议字段移除 |
| AC-003 | re_verified | `pytest tests/integration` 79 passed，含握手拒绝、注册表隔离与替换用例 |
| AC-004 | re_verified（有 minor 提示） | supervised heartbeat/policy 重启测试通过；未断言错误日志与完整退避序列（f005 残余） |
| AC-005 | re_verified | gateway config/control/signaling 与 secret 权限用例通过；新增 Stream 镜像 `secret_files.py` 打包守卫并重跑通过 |
| AC-006 | re_verified | `test_stream_protocol_schema.py`、`test_stream_agent_protocol_v2.py` 通过；schema 漂移守卫通过 |
| AC-007 | re_verified（E2E 未实跑） | adapter build 4 passed、前端 Vitest 126 passed；探针注入顺序与 `__pcs` 语义回放验证通过 |
| AC-008 | re_verified（有 minor 提示） | `BrowserSessionView.test.tsx` 覆盖 401 `onUnauthorized`、runtime_not_ready、Web Locks 诊断与 unmount 监听释放；timeout 路径未单独断言（f006 残余） |
| AC-009 | re_verified | ADR 013、Superseded、计划替代标记与 adoption D1 已更新；testing.md 全部测试路径逐一存在性校验通过（f009 已修） |

coverage = 8 / 9

verdict: PASS

## Round 5 (2026-11-03T01:55:34+08:00)

reviewed_scope: 10dbf23b358176db

本轮对 committed tip `0b0881e` 复核 Round 4 的 evidence 修复，并重扫测试改动面。工作区 `git status` 干净；`reviewed_scope` 与当前 worktree / HEAD 指纹一致。

### 前轮 finding 复核

- t015_test_f001 已消除：`tests/e2e/test_frontend_adapter_build.py:53-55` 只断言生产 marker；本轮重跑 `pytest tests/e2e/test_frontend_adapter_build.py -q` 为 `4 passed`。
- t015_test_f002 已消除（静态复核，未启动 Docker E2E）：`tests/e2e/test_gateway_ac001_auth_e2e.py:84` 为 `assert "turn" not in harness.keys`；`tests/fixtures/gateway_probe/topology.py:145` 只创建四个非 TURN key，原 `harness.keys["turn"]` KeyError 路径消失。
- t015_test_f003 已消除（静态 + 单元 + Node 回放，未启动 Docker 前端 E2E）：`tests/fixtures/frontend_probe/adapter_probe.py:55-66` 由 `tests/fixtures/frontend_app_probe/harness.py:42` 与 `tests/fixtures/frontend_probe/host_builder.py:101` 注入复制后的 Selkies index；生产 adapter 不再写测试全局。`npm test --prefix src/frontend -- --run` 为 `126 passed`。
- t015_test_f004 已消除：`rg 'SELKIES_TURN|turn_secret|turn_host|turn_port'` 在活跃 `tests` 中只剩负向断言（如 `tests/unit/test_stream_agent_lifecycle.py:180-181`、`tests/unit/test_gateway_config.py:39-45`、`tests/unit/test_stream_agent_protocol_v2.py:57`）；`docs/blueprint/testing.md` 已无旧 coturn 探针行。
- t015_test_f005 minor 残余仍在：`test_supervised_heartbeat_task_restarts_after_fatal_exit`（`tests/unit/test_stream_agent_lifecycle.py:605-646`）与 `test_supervised_policy_loop_restarts_after_fatal_exit`（`tests/unit/test_stream_runtime.py:197-237`）只断言重启发生且首次退避为 `[1.0]`，未断言错误日志与 2/4/8 秒递增退避；不影响本轮 verdict。
- t015_test_f006 minor 残余仍在：`BrowserSessionView.test.tsx:116-124` 只覆盖 unmount 监听释放，未覆盖 timeout 完成路径；不影响本轮 verdict。
- t015_test_f007 已转 p016：`docs/pending/todo/p016_restore_supervisor_network_and_quota_e2e.md` 仍在，本 task 内未补回。
- t015_test_f008 已消除：`tests/fixtures/frontend_probe/adapter_probe.py:60-64` 将 `PROBE_TAG` 插到 `selkies_adapter.js` 之前；临时副本回放确认 `probe_before_adapter=True`，并用 Node 模拟 adapter 包装后发送 `r,800,600`、`STOP_AUDIO`、`k,abc`，探针只记录 `["STOP_AUDIO","k,abc"]`。
- t015_test_f009 已消除：脚本抽取 `docs/blueprint/testing.md` 中全部 `tests/...` 路径并逐一 `test -f`，28 个路径无缺失。
- t015_test_f010 已消除：`tests/fixtures/frontend_probe/adapter_probe.py:26-27` 为 `window.__pcs = window.__pcs || []; window.__pcs.push(pc);`，与 `tests/fixtures/gateway_probe/selkies_assets.py:77-78` 语义一致。
- t015_test_f011 已消除：`tests/unit/test_baseline_runtime_regressions.py:54-65` 新增 `test_stream_runtime_packaging_integrity`，断言 pinned `FROM` 与 `__init__.py`、`secret_files.py`、`stream_agent`、`entrypoint.sh` 四个 COPY；`config/docker/stream_runtime/Dockerfile:52` 含 `secret_files.py`；该文件本轮通过。

### 本轮新发现

#### t015_test_f012 - Agent 替换测试重写时删除了 close code 1001 与下行/存活断言

- 严重度：minor
- 锚点：refactor 型 task 的覆盖保持；旧测试标注 AC-003（`git show 9ee4a11:tests/integration/test_gateway_signaling.py:833-875`）
- 位置：`tests/integration/test_gateway_signaling.py:437-498`（现测试）；旧断言位于 base 文件 `:836`、`:849`、`:861-875`
- 问题：`test_agent_replacement_closes_old_viewers` 重写为新 envelope 后只保留“旧 Viewer 收到 CLOSE、新 Viewer 可上行发送”，删除了旧测试的 `close_v1.data == 1001`、`conn_id_2 != conn_id_1`、Agent 2 下行 `REPLY_FROM_A2` 到 Viewer 2、以及 `not ws_viewer_2.closed` 四个断言。用 `.scratch` 临时脚本按同一状态驱动当前生产 Gateway 复核，结果为 `close msg type 8 data 1001`、`open2 ... different True`、`viewer2 in TEXT REPLY_FROM_A2 closed False`，说明这些断言在修复后仍成立，删除不是规格变化导致。主行为仍被断言（旧关闭、新可上行），未构成假绿；按 blocking 硬阈值无 AC 完全缺测且无可观测行为缺陷，故列 minor 覆盖收缩。
- 建议：恢复 `close_v1.data == 1001`、`conn_id_2 != conn_id_1`、Agent 2 下行回复与 Viewer 2 存活断言；这是 blueprint `gateway.md:31` 已写明的替换契约。

#### t015_test_f013 - 删除的 Supervisor 中途失败原子回滚 E2E 未转入 p016

- 严重度：minor
- 锚点：refactor 型 task 覆盖保持；`attach_profile_infrastructure` 的 rollback 仍存在
- 位置：删除文件 `tests/e2e/test_supervisor_infrastructure_network_e2e.py:465-524`（base `test_midway_failure_atomic_rollback_and_error_propagation_e2e`）；生产 `src/backend/cbrowser/supervisor/docker_adapter.py:535-548`；`docs/pending/todo/p016_restore_supervisor_network_and_quota_e2e.md`
- 问题：整文件删除时 p016 只登记 Gateway 动态加入媒体网络、跨 Profile 隔离、清理拒绝、未知端点拒绝与 Stream `control_proof`；同一文件的 `test_midway_failure_atomic_rollback_and_error_propagation_e2e` 验证第二个基础设施连接失败时回滚新 endpoint、保留旧 endpoint，该行为与 TURN 无关，当前生产仍有 `newly_connected` rollback 分支，但删除后无等价测试，p016 也未覆盖。
- 建议：把该用例补入 p016；或改写为仅注入 Gateway 连接失败（删除 coturn 后单目标仍可测）。

### 结论

- 前轮 finding 复核：f001～f004、f008～f011 已消除；f005、f006 主体已修仍存 minor 残余；f007 由 p016 跟踪。未采信 note 处置表，结论以 committed diff、代码与测试结果为准。
- 改测方向复核：无把旧断言预期改成当前实现输出的“迁就实现”改测；TURN/ICE 相关删除属 spec 变更。f012 是重写时删补充断言，主断言未改变，已在 finding 中单列。
- 本轮新发现：2 条（均 minor）。
- 未进表的提示：`tests/e2e/test_gateway_ac001_auth_e2e.py:84` 的 `assert "turn" not in harness.keys` 只验证 fixture 键集合，不验证 login response（AC-002 的 TURN 移除另由 grep 与协议负向断言兜底）；`tests/e2e/test_frontend_app_e2e.py:665` 的 `|| []` 在探针缺失时会让 resize 负向断言空转（同测试的 STOP_AUDIO 等待会兜底）；`tests/unit/test_baseline_runtime_regressions.py:54-65` 为 Dockerfile 文本守卫，不替代镜像构建。前端 E2E 最近实跑 `.scratch/t015_frontend_e2e`（00:46）早于 01:36 的探针顺序修复，本轮未启动 Docker 前端拓扑，AC-007 的探针证据为静态 + 单元 + Node 回放。
- 总体判断：Round 4 的 evidence 修复已全部落地且无 blocking 回归；仅新增 2 条 minor 覆盖残余，测试轴可通过。
- 系统性 follow-up：f013 建议补 p016；f012 属本 task 收口时补断言，不需新 task。

### AC 复验方式

| AC | 类别 | 证据 |
|---|---|---|
| AC-001 | trust_prior | 复核 `docs/spikes/s011_direct_media_validation/report.md`、`docs/findings/d026_direct_media_local_only.md` 与 `<home>/kar/code/.scratch/s011/.../media_proof.json`、`<home>/kar/code/.scratch/t015_stream_e2e/basetemp2/.../media_proof.json`：127.0.0.1 host 候选、音频/视频增长、可见性、resume、IME 证据均存在；未在本轮重跑真实 Chrome 部署 |
| AC-002 | re_verified | 活跃源码/config/schemas/scripts grep 无运行时 TURN/coturn/rtc_config/ice_restart；`tests/unit` 491 passed、`tests/integration` 85 passed |
| AC-003 | re_verified（有 minor 提示） | `tests/integration` 85 passed，含握手拒绝、身份隔离与替换用例；替换测试丢补充断言见 f012 |
| AC-004 | re_verified（有 minor 提示） | 重跑 supervised heartbeat/policy 重启测试通过；未断言错误日志与完整退避序列（f005 残余） |
| AC-005 | re_verified | `test_gateway_config.py`、`test_gateway_control.py`、`test_gateway_signaling.py` 与 secret 权限用例通过；Stream Dockerfile 打包守卫通过 |
| AC-006 | re_verified | `test_stream_protocol_schema.py`、`test_stream_agent_protocol_v2.py` 通过；schema 漂移守卫通过 |
| AC-007 | re_verified（E2E 未实跑） | adapter build `4 passed`、前端 Vitest `126 passed`；探针注入顺序与报文记录边界用临时副本和 Node 回放验证 |
| AC-008 | re_verified（有 minor 提示） | `BrowserSessionView.test.tsx` 覆盖 401 `onUnauthorized`、runtime_not_ready、Web Locks 诊断与 unmount 监听释放；timeout 路径未单独断言（f006 残余） |
| AC-009 | re_verified | ADR 013、Superseded、计划替代标记与 adoption D1 已更新；testing.md 全部测试路径存在性校验通过（f009 已修） |

coverage = 8 / 9

verdict: PASS
