# Task review t007（reviewer_focus: 测试）

- task：`t007_v2_frontend_sessions`
- spec：`docs/tasks/t007_v2_frontend_sessions/task.md`
- diff_anchor：`077778fef84f22312e6b18583c547c8b5f418617`
- target：`git -C '/Users/karson/kar/code/CBrowser_t007' diff 077778fef84f22312e6b18583c547c8b5f418617`
- round：1
- reviewed_at：2026-10-31T22:47:49+08:00

## Findings

### t007_test_f001 - AC-004 适配层 activity/resize 拦截单测的断言恒真，无法发现回归

- 严重度：important
- 锚点：AC-004「页面不向 Gateway 上报可见性或活动」「外部窗口 resize 不改变远端」
- 位置：`src/frontend/src/features/browser-session/BrowserSessionView.test.tsx:256-268`；生产实现 `src/frontend/src/features/browser-session/adapter.ts:244-245,286,70-79`
- 问题：测试在 `ws.send` 之后断言 `nativeSendSpy` 未被调用，但 `nativeSendSpy` 挂在 `(ws as any)._nativeSend` 上；适配层 `ws.send` 包装闭包使用的是构造时捕获的局部 `const nativeSend = ws.send.bind(ws)`，全程不读取 `ws._nativeSend`。因此无论 activity 帧是否被丢弃，`nativeSendSpy` 都不会被调用，断言必然通过。紧随其后的 `fakeWindow.RTCDataChannel.prototype.send("r,1920,1080")`（`:268`）没有任何断言，resize 拦截同样零验证。
- 建议：改为断言 `ws.sent` 为空（activity 被拦截）或 `__sentDataChannelMessages` 不含 `r,`，并显式断言底层 native send 未被调用；或直接断言适配层拦截后的可观察输出。

### t007_test_f002 - AC-007 重连/失效连接重建的断言恒真，且 E2E 从未制造失效连接

- 严重度：important
- 锚点：AC-007「页面冻结/恢复后检测失效连接并以原 client_tab_id/resume_key 重建」
- 位置：`src/frontend/src/features/browser-session/BrowserSessionView.test.tsx:138-152,154-169`；E2E `tests/e2e/test_frontend_app_e2e.py:720-742`
- 问题：`reconnect button resets stage and reloads iframe` 点击后只断言 `iframe.src` 含 `profileId`，而该字符串在点击前后恒成立；`triggers reconnection on Page Lifecycle resume...` 派发 `CBROWSER_LIFECYCLE_STALE` 后只断言 `iframe` `toBeDefined()`。两个测试在 `reconnect()` 完全空实现时仍会通过。E2E 冻结/恢复的是健康连接（`Page.setWebLifecycleState frozen→active`），从未让 PC/WS 进入 failed/closed 再触发 stale 分支，因此「检测失效连接并以原身份重建」这一 AC 核心行为没有有效证据。
- 建议：单测断言 `reloadKey`/`_k` 变化或 stage 迁移；补充派发 `CBROWSER_PC_STATE{iceConnectionState:"failed"}` / `CBROWSER_WS_CLOSE` 后触发重连，并在 E2E 中先断开信令/令 PC 失效，再断言重建的 HELLO 携带原 `client_tab_id` 与 `resume_key`。

### t007_test_f003 - AC-005 输入/静音的 E2E 断言为条件跳过与自设标志，且用直接赋值替代产品交互

- 严重度：important
- 锚点：AC-005「两个页面都能真实输入且独立静音」
- 位置：`tests/e2e/test_frontend_session_e2e.py:257-303`；`tests/e2e/test_frontend_app_e2e.py:628-644`
- 问题：`test_frontend_session_independent_input_and_mute` 用 `if muted_in_A:` 包住唯一断言，若 iframe 中找不到 `<audio>` 元素则整段静音断言被跳过；输入部分断言的是脚本自己 `return true` 的 `dispatched_A/dispatched_B`（只要 iframe 存在即为真），并未验证远端收到输入。两处测试都用 `audio.muted = true` 直接改元素，替代了 AC 要求的产品静音控件（真实产品路径在 `test_frontend_media_e2e.py:614-680` 有覆盖，但本文件与 `test_frontend_app_e2e.py` 的对应断言仍是假绿）。
- 建议：静音改为点击 `[data-testid="session-audio-toggle-btn"]` 并断言 `STOP_AUDIO`/`START_AUDIO` 数据通道消息；输入断言远端 `probe_input` 的值（参考 `test_frontend_app_e2e.py:600-624` 的 `remote_value`），移除条件包裹。

### t007_test_f004 - AC-002「新标签页 noopener」完全无测试，resume_key 保留未断言

- 严重度：important
- 锚点：AC-002「新标签页 noopener，不重写官方 HELLO」「刷新和重连保留 resume_key/身份」
- 位置：实现 `src/frontend/src/features/browser-session/adapter.ts:39-60`；测试 `tests/e2e/test_frontend_app_e2e.py:487-492`；全仓 `grep -rn noopener tests src/frontend/src` 无测试命中
- 问题：AC-002 明确要求新标签页带 `noopener`，但没有任何测试验证 `win.open` 追加 `noopener` 或 `_blank` 链接被补 `rel=noopener`。HELLO 部分 E2E 只断言 `client_tab_id`/`resume_key` 字段存在，未断言刷新/重连前后 `resume_key` 一致，也未对比适配层转发的 HELLO 与官方客户端原始 HELLO 一致（「不重写官方 HELLO」）。
- 建议：补单测断言 `win.open(url, "_blank")` 的 features 含 `noopener` 及 click 委托补 `rel`；E2E 记录刷新前后 HELLO 的 `resume_key` 并断言相等。

### t007_test_f005 - AC-007 ICE 失败检测路径无测试，仅测试了注入 initialStage 的渲染

- 严重度：minor
- 锚点：AC-007「ICE 失败分别显示阶段与可执行操作，诊断取自 RTCPeerConnection 状态」
- 位置：`src/frontend/src/features/browser-session/useBrowserSession.ts:160-175`；`src/frontend/src/features/browser-session/BrowserSessionView.test.tsx:80-113`
- 问题：`ice_failed` 用例通过 `initialStage="ice_failed"` 直接注入，绕过了 `CBROWSER_PC_STATE` → `setStage("ice_failed")` 的生产检测逻辑；全仓无测试派发 `CBROWSER_PC_STATE` 断言阶段迁移，检测逻辑回归不会被发现。
- 建议：新增 hook/组件测试派发 `CBROWSER_PC_STATE{iceConnectionState:"failed"}` 并断言 `ice_failed` 与诊断字段。

### t007_test_f006 - 创建 Profile 用例标题声称校验缓存失效，实际只断言 mutation 成功

- 严重度：minor
- 锚点：AC-006「Profile 列表/创建/编辑…通过 /api/v1…完成」
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.test.tsx:117-131`
- 问题：用例名 `creates a profile and invalidates the profiles cache`，但只断言 `create.isSuccess`，未断言 `profileKeys.lists()` 被 invalidate 或缓存内容变化；`useCreateProfileMutation` 的 `invalidateQueries`（`useProfilesQuery.ts:60-68`）无测试保护。
- 建议：断言 mutation 后 list query 重新 fetch 或 `queryClient.getQueryState(profileKeys.lists()).isInvalidated`。

### t007_test_f007 - session E2E 的「查看运行状态」断言依赖测试宿主 hook，不是真实应用行为

- 严重度：minor
- 锚点：AC-007「…可执行操作」
- 位置：`tests/e2e/test_frontend_session_e2e.py:431-437`；`src/frontend/src/features/browser-session/host_entry.tsx:16-20`；真实应用 `src/frontend/src/features/profiles/BrowserSessionPage.tsx:70-73`
- 问题：`FrontendTopologyHarness` 提供的是 `host_builder.py` 生成的 `host_entry.tsx` 最小宿主页（`tests/fixtures/frontend_probe/host_builder.py:52-96`），`__statusBtnClicked` 只由该测试宿主设置；真实应用里该按钮执行 `navigate(/profiles/{id})`，没有测试验证该跳转。断言测的是夹具钩子而非产品行为。
- 建议：在完整应用 E2E 中点击 `session-view-status-btn` 并断言路由跳转到 `/profiles/{id}`。

### t007_test_f008 - AC-004「无 resize 包」断言检查了错误的通道

- 严重度：minor
- 锚点：AC-004「外部窗口 resize 不改变远端」
- 位置：`tests/e2e/test_frontend_app_e2e.py:596-598`
- 问题：`no_resize_packets` 遍历 `wire.frames_sent`（CDP `Network.webSocketFrameSent`，仅 WebSocket 帧），而适配层拦截的 `r,width,height` 走 RTCDataChannel（`adapter.ts:70-79`），该断言无法发现 resize 包；同用例随后对远端 `videoWidth/Height` 的断言才是有效证据。
- 建议：改为读取 iframe `__sentDataChannelMessages` 断言不含 `r,`，或删除该无效断言避免假覆盖。

## 结论

- 改测方向复核：相对 diff_anchor 无既有测试被修改/删除（`git diff --name-status 077778f` 中测试仅新增，唯一修改的测试相关文件是 `tests/fixtures/gateway_probe/caddyfile.py` 的静态路由夹具，无断言变更）；不存在就地迁就实现的改测。
- 本轮新发现：8 条（4 important，4 minor）。
- 未进表的提示：
  - `test_frontend_session_e2e.py` 使用 `host_entry.tsx` 最小宿主页而非完整 Vite 应用，属较低层会话 E2E；完整应用路径由 `test_frontend_app_e2e.py` 覆盖（r3 `frontend_e2e` 21 passed），不单独出 finding。
  - 门禁 r3 `runtime_e2e` 有 1 个已知 Pulse 时序抖动失败，`r3_rerun/runtime_ac006_1.log`、`_2.log` 均 1 passed；与 t007 测试质量无关。
  - 旧 UI 组件与旧测试（`ProfileFiles.test.tsx` 等）仍保留，note 记录延后到 t011；因其被测旧组件仍在仓库且测试仍通过，未判定为 AC-006「旧 UI 测试语义失效」违规。
- 总体判断：AC-001/003/004/005/006/008/009/010 有真实证据，但 AC-002 的 noopener、AC-007 的失效连接重建存在无有效测试/恒真断言，AC-004/005 有多处假绿断言，需修复后重审。

### AC 复验方式

- AC-001：`trust_prior` — 依赖 r3 `frontend_e2e.log`（21 passed）与 `test_frontend_app_e2e.py:290-360` 的双标签页断言；本地仅复跑 Vitest（`router.test.tsx:163-194`）验证 URL 目标隔离。
- AC-002：`trust_prior` — 依赖 r3 frontend E2E 的 tab_id/复制页断言；本轮发现 noopener 无测试（f004）。
- AC-003：`trust_prior` — 依赖 `test_frontend_app_e2e.py:490-520`（关页后容器仍 running）与 r3 日志。
- AC-004：`trust_prior` — 依赖 `test_frontend_media_e2e.py`、`test_frontend_display_apply_e2e.py` 与 r3 日志；适配层单测断言恒真（f001）。
- AC-005：`trust_prior` — 依赖 `test_frontend_media_e2e.py:614-680` 真实产品静音与 `test_frontend_app_e2e.py:600-624` 真实键盘输入；`session_e2e` 对应断言假绿（f003）。
- AC-006：`re_verified` — 本地复跑 `tests/integration/test_api_sse_events.py`、`test_runtime_coordinator_integration.py` 共 7 passed，Vitest 93 passed。
- AC-007：`trust_prior` — 依赖 `test_frontend_app_e2e.py:690-810` 阶段渲染与 r3 日志；失效连接重建无有效证据（f002）。
- AC-008：`trust_prior` — 依赖 `test_stream_selkies_tokens_e2e.py:130-171` 与 r3 `stream_e2e.log`（19 passed）。
- AC-009：`re_verified` — 本地复跑 `tests/integration/test_runtime_coordinator_integration.py`（含 Supervisor 不可达保留意图/恢复收敛）；真实 Supervisor 部分依赖 r3 frontend E2E。
- AC-010：`re_verified` — 本地复跑 `test_stream_selkies_tokens.py`、`test_supervisor_selkies_tokens.py` 等共 33 passed；真实容器 token/日志扫描依赖 r3 `stream_e2e`。
- coverage = 3 / 10
- 建议合并前人工抽查 trust_prior 项（AC-001/002/003/004/005/007/008 的 Docker 真实栈行为）。

- 系统性 follow-up：无（p005 为 t006 遗留 minor，不在本 task 契约内，未重复登记）。

reviewed_scope: 33ff6aed2fc94ea3

verdict: FAIL

## Round 2 (2026-11-01T01:22:47+08:00)

### Findings

#### t007_test_f009 - AC-010/AC-002 的关键 E2E 在当前树必然崩溃：夹具仍按 sec001 之前的路径读 Selkies tokens

- 严重度：important
- 锚点：AC-010「每个 Profile 的 master token 与 controller token 由服务端随机生成…master token 不出现在任何前端可见响应、页面或日志」；同时承担 AC-002「不重写官方 HELLO」的唯一断言
- 位置：`tests/fixtures/frontend_app_probe/harness.py:111-113`；使用点 `tests/e2e/test_frontend_app_e2e.py:455`；生产写入路径 `src/backend/cbrowser/supervisor/path_validator.py:134-137`、`src/backend/cbrowser/supervisor/core.py:499-503`
- 问题：`FrontendAppTopologyHarness.selkies_tokens()` 读 `<data_dir>/runtime/<profile_id>/selkies_tokens.json`，而 t007_master_sec001 修复后 Supervisor 只把凭证写到 `<data_dir>/runtime/.secrets/<profile_id>/selkies_tokens.json`（`get_secret_dir`），`runtime/<profile_id>` 下不再有该文件。因此 `test_ac002_ac003_ac010_identity_copy_close_and_tokens` 在 `tokens = harness.selkies_tokens(profile_id)` 处抛 `FileNotFoundError`，后面的 token 泄漏扫描（DOM/storage/network/WS）与官方 HELLO 字段断言全部不会执行。该失败场景与时序无关：`path_validator.py` mtime 23:04 已改为 `.secrets`，而 `harness.py` 仍读旧路径；r3 门禁（22:40）与 fix_fe 的 16 passed（其 seed.patch 仍是旧 blueprint）都发生在 sec001 之前，当前树没有跑过这组 E2E。
- 影响：AC-010 的端到端证据不可运行，AC-002「不重写官方 HELLO」（`official_hello_keys` 子集断言）也同样失效；`frontend_e2e` 门禁会因此失败。
- 建议：`selkies_tokens()` 改走 `.secrets` 路径（或直接复用 `PathValidator.get_secret_dir` 的语义），并在 sec001 后重跑 `test_frontend_app_e2e.py`。

#### t007_test_f010 - 「独立静音」的 audio 元素断言在无 audio 元素时空真通过

- 严重度：minor
- 锚点：AC-005「两个页面都能真实输入且独立静音」
- 位置：`tests/e2e/test_frontend_app_e2e.py:686-695`；`tests/e2e/test_frontend_session_e2e.py:301-304`
- 问题：`[...document.querySelectorAll('audio')].every(n => n.muted)` 在匹配 0 个元素时返回 `true`，`...some(n => n.muted)` 返回 `false`；若 iframe 内没有 audio 元素，`muted_a is True` / `muted_b is False` 都会空真通过，无法证明「A 被静音且 B 未静音」。该断言属于次要证据：同用例的 `STOP_AUDIO`/`START_AUDIO` DataChannel 消息与 `test_frontend_media_e2e.py:577-686` 的真实音频字节增长仍是有效证据，故不阻断。
- 建议：先断言 audio 元素数量 `> 0`，再判断 muted 状态。

### 结论

- 前轮 finding 复核（对照当前 diff，不采信处置表自述）：
  - `t007_test_f001`：已消除。`BrowserSessionView.test.tsx:399-424` 直接断言底层 `ws.sent` 不含 activity、`nativeDataChannelSend` 未被 `r,` 调用且 `__sentDataChannelMessages` 只有 `k,abc`；断言的正是 `adapter.ts:71-81,245-288` 的生产包装边界，不再是恒真。
  - `t007_test_f002`：已消除。`BrowserSessionView.test.tsx:163-276` 以 `_k`/`data-stage` 断言真实重建，`CBROWSER_LIFECYCLE_STALE` 派发后 `_k=1`；`test_frontend_app_e2e.py:834-877` 真实 `pc.close()` + `resume` 触发 iframe 重建，`test_frontend_ice_failure_e2e.py:144-188` 真实暂停 coturn 进入 `ice_failed`。
  - `t007_test_f003`：已消除。`test_frontend_session_e2e.py:296-331` 点击产品按钮并断言 `STOP_AUDIO`/`START_AUDIO`、B 页未收到；输入断言远端 `probe_input == "12"`，不再有 `if muted_in_A` 条件包裹或脚本自设 `dispatched_*`。
  - `t007_test_f004`：已消除。`BrowserSessionView.test.tsx:426-454` 断言 `open(..., "_blank", "...noopener")` 与 `rel` 补齐；`test_frontend_app_e2e.py:487-535` 断言 HELLO 字段集合为官方子集、无 `client_token`、刷新后 `client_tab_id` 不变且 `resume_key` 变化、连接内重连保留原 `resume_key`。注：该 E2E 当前因 f009 不可运行。
  - `t007_test_f005`：已消除。`BrowserSessionView.test.tsx:174-244` 派发 `CBROWSER_PC_STATE` 验证 `ice_failed` 迁移、诊断字段与 5s 宽限（transient 不误报）。
  - `t007_test_f006`：已消除。`useProfilesQuery.test.tsx:117-137` 断言 `listCallCount >= 2`（真实重取）而非只断言 mutation 成功。
  - `t007_test_f007`：已消除。`test_frontend_app_e2e.py:895-901` 点击 `session-view-status-btn` 后 `wait_for_url(/profiles/{id})`，是产品路由而非夹具 hook。
  - `t007_test_f008`：已消除。`test_frontend_app_e2e.py:640-649` 读 iframe `__sentDataChannelMessages` 并断言无 `r,`。
  - `t007_code_f001`：已消除。本地复跑 `tests/integration/test_sse_epoch_integration.py` 等 8 passed，覆盖跨 epoch `Last-Event-ID` 快照。
  - `t007_code_f002`/`f003`：已消除。`useBrowserSession.ts:174-242` 与 `test_frontend_ice_failure_e2e.py`、`test_runtime_coordinator_stop_paths.py`（本地复跑通过）对应。
  - `t007_code_f004`~`f008`：测试侧证据仍在（Vitest 102 passed；断言的 `t()` 文案、静态 import、origin 校验、侧栏导航均在新增测试内）。
  - `t007_master_sec001`：生产侧已修且 `test_supervisor_selkies_token_isolation.py`、`test_stream_selkies_tokens_e2e.py:424-463` 覆盖「不挂进 Browser、0600、`.secrets`」；但该修复遗留下 f009（前端 E2E 夹具路径未同步），故本条不能算完全闭环。
- 改测方向复核：无「迁就实现」的改测。相对 diff_anchor，既有测试文件均为新增（`git diff --name-status` 中测试仅 A），唯一修改的测试邻近文件 `tests/fixtures/gateway_probe/caddyfile.py` 只修 `handle` 路由与 SPA fallback，未改断言；Round 1 修复把断言改强（检查真实底层 send、`_k`、远端输入值），方向正确。
- 契约区 drift：AC-002/AC-007 措辞变更已在 task.md 上下文区记录（官方 `resume_key` 每次实例化随机的既有事实），diff 中全部 AC 由 `[ ]` 变 `[x]`，属实施完成打勾，非未授权改需求；不另出 finding。
- 本轮新发现：2 条（1 important，1 minor）。
- 未进表的提示：
  - `test_frontend_session_e2e.py:229-235` 对容器状态断言 `status in ("running","created")`，偏宽；同 AC-003 在 `test_frontend_app_e2e.py:576-582` 有严格 `status == "running"`，故不阻断，建议后续收紧。
  - `adapter.ts:278-288` 只拦截包含 `"cbrowser"`+`"activity"` 的帧，未拦 `visibility` 帧；E2E 通过真实 visibilitychange 后 WS 帧扫描证明没有可见性帧上报，行为成立，但单测只覆盖 activity，可后续补 visibility 变体。
- 总体判断：Round 1 的 8 条测试 blocker 已真实修复且无换形式弱化；但 sec001 修复引入夹具路径漂移，导致 AC-010/AC-002 的关键 E2E 在当前树必然失败，故事实上不可 PASS。

### AC 复验方式

- AC-001：`trust_prior` — 双真实 Chrome 标签页与切换隔离仅依赖 r3 `frontend_e2e.log`（21 passed）与 `test_frontend_app_e2e.py:300-430`；本地复跑 Vitest（`router.test.tsx:163-215`）只验证 URL/localStorage 隔离。
- AC-002：`trust_prior` — 依赖 `test_frontend_session_e2e.py:125-240` 与（当前不可运行的）`test_frontend_app_e2e.py:435-596`；noopener 单测已本地复跑通过。
- AC-003：`trust_prior` — 依赖 `test_frontend_session_e2e.py:215-235` 与 `test_frontend_app_e2e.py:576-590`，未复跑 Docker。
- AC-004：`trust_prior` — 依赖 `test_frontend_media_e2e.py:435-575`、`test_frontend_display_apply_e2e.py:170-275` 与 r3 日志；适配层拦截单测已本地复跑。
- AC-005：`trust_prior` — 依赖 `test_frontend_media_e2e.py:577-780`；静音 audio 元素断言见 f010（次要证据）。
- AC-006：`re_verified` — 本地复跑 Vitest 102 passed 与 `tests/integration/test_api_sse_events.py`、`test_sse_epoch_integration.py`（8 passed），SSE 断线/epoch 恢复走真实 HTTP。
- AC-007：`trust_prior` — 依赖 `test_frontend_app_e2e.py:743-955`、`test_frontend_ice_failure_e2e.py` 与 r3 日志；PC 状态迁移单测已本地复跑。
- AC-008：`trust_prior` — 本地复跑 `test_stream_selkies_tokens.py::test_entrypoint_script_ac008_and_ac010_directives`（entrypoint 文本），Selkies 403 行为依赖 `test_stream_selkies_tokens_e2e.py:149-193` 的 Docker 运行。
- AC-009：`re_verified` — 本地复跑 unit 47 passed（含 `test_runtime_coordinator_stop_paths.py`、`test_api_runtime_coordinator.py`）与 integration 8 passed（Supervisor 不可达保留意图/恢复收敛）；「真实容器启停」部分依赖 r3 `frontend_e2e`。
- AC-010：`re_verified` — 本地复跑 `test_stream_selkies_tokens.py`、`test_supervisor_selkies_tokens.py`、`test_supervisor_selkies_token_isolation.py` 全绿；但前端侧 E2E 因 f009 不可运行，真实 Gateway 隧道部分依赖 `test_stream_selkies_tokens_e2e.py:406-560`（Docker）。
- coverage = 3 / 10
- 建议合并前人工抽查 trust_prior 项（AC-001/002/003/004/005/007/008 的 Docker 真实栈行为）；并先修复 f009 再跑 `frontend_e2e`。
- 本轮本地执行命令：`NODE_OPTIONS=--no-experimental-webstorage npm test --prefix src/frontend`（13 files / 102 passed）；`pytest` 选定 `tests/unit` 10 文件（47 passed）与 `tests/integration/test_runtime_coordinator_integration.py test_sse_epoch_integration.py test_api_sse_events.py`（8 passed）。

- 系统性 follow-up：无新增；f009 属本 task 修复范围（一行夹具路径），无需另立 tid。

reviewed_scope: 288d20330554968b

verdict: FAIL

## Round 3 (2026-11-01T03:59:00+08:00)

### Findings

#### t007_test_f011 - SSE 事件后的 runtime 失效重取没有回归测试（t007_code_f009 后半未被验证）

- 严重度：minor
- 锚点：AC-006「后端状态经 SSE 更新，断线恢复无陈旧控制状态」
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts:211`；`src/frontend/src/features/profiles/useProfilesQuery.test.tsx:140-171,174-191`；RED/GREEN `.scratch/t007_master/red_sse_no_fabricated_runtime.log`、`green_sse_no_fabricated_runtime.log`
- 问题：Round 2 处置称「每个事件使 runtime 查询失效重取」，但现有测试只验证两件事：(a) 已缓存 runtime 会被事件字段合并（`:140-171`），(b) 无缓存时不伪造 runtime（`:174-191`）。没有任何断言观察 `invalidateQueries` 触发的重取（`getRuntime` 调用次数、`getQueryState(...).isInvalidated` 或重取后的 `config_version`）。删除 `useProfilesQuery.ts:211` 后两个用例仍全绿；RED 日志也只覆盖「不伪造」这一半。
- 影响：事件不携带 `config_version`/`updated_at`，若失效重取丢失，已加载页面的显示尺寸「待应用」判定会停留在旧版本号，且现有测试无法发现回归。
- 建议：在 SSE 用例内 spy `mockApiClient.profiles.getRuntime`（或断言 runtime 查询的 `isInvalidated`/调用计数增长），与现有合并断言并存。

#### t007_test_f012 - AC-003 session E2E 接受 `created` 状态，弱于「关闭页面不停止真实浏览器」

- 严重度：minor
- 锚点：AC-003「页面切换或关闭仅关闭自身 PeerConnection/信令，不调用 Profile stop…只有明确停止 Profile 才关闭真实浏览器」
- 位置：`tests/e2e/test_frontend_session_e2e.py:232,237`
- 问题：关闭 Page A 后断言 `browser_box.status in ("running", "created")` 与 `stream_box.status in ("running", "created")`。`created` 表示容器已创建但未运行/已重建，关闭一个 viewer 后出现 `created` 同样满足断言，无法证明浏览器仍真实运行。
- 影响：该用例单独看无法区分「未停止」与「被停止后又重新创建」。同一 AC 在完整应用 E2E 有严格断言（`tests/e2e/test_frontend_app_e2e.py:564-567` 断言容器 `=="running"` 且 runtime `observed_state=="running"`），故不阻断本轮，但本用例应收紧以避免未来回归被吞。
- 建议：改为 `== "running"`（必要时轮询等待 `running`），与 `test_frontend_app_e2e.py:564-567` 保持一致。

### 结论

- 前轮 finding 复核（以当前 diff/代码为准，不采信处置表自述）：
  - `t007_test_f009`：已消除。`tests/fixtures/frontend_app_probe/harness.py:111-116` 的 `selkies_tokens()` 已改读 `<data_dir>/runtime/.secrets/<profile>/selkies_tokens.json`，与生产写入路径 `src/backend/cbrowser/supervisor/path_validator.py:126-137` 和 `src/backend/cbrowser/supervisor/core.py:499-503` 完全一致；`--data-root` 就是 harness 的 `data_dir`（`tests/fixtures/frontend_probe/harness.py:298-304`）。静态上不再必然 `FileNotFoundError`。注意：修复后 `test_frontend_app_e2e.py` 在当前树仍未重跑（`.scratch/project_gates/` 下无 r4），运行态证据待门禁补；这是验证时序问题，不是新的静态缺陷。
  - `t007_test_f010`：已消除。`tests/e2e/test_frontend_app_e2e.py:693,701` 与 `tests/e2e/test_frontend_session_e2e.py:306` 都先要求携带远端音频轨道的 `audio,video` 元素数量 `> 0` 再比较 muted，无元素时空真通过的问题消失。官方客户端在 `pipelineControl.audio` 分支确实执行 `b.muted=!enabled`（`src/frontend/public/selkies/assets/selkies-core-BGbb3Bx7.js:1`），断言对象正确。
  - `t007_code_f009`：已消除（不伪造 runtime 部分）。`useProfilesQuery.ts:188-213` 在无缓存时返回 `undefined`，并在事件后失效 runtime/list 查询；`useProfilesQuery.test.tsx:174-191` 有真实 RED/GREEN（`.scratch/t007_master/red_sse_no_fabricated_runtime.log` 失败、`green_sse_no_fabricated_runtime.log` 4 passed）。但「事件后失效重取」仍无断言 → 见 f011。
  - `t007_code_f010`：已消除。`BrowserSessionView.test.tsx:278-301` 覆盖三种分支（persisted+健康不重建、非 persisted 不检查、persisted+失效重建）；`useBrowserSession.ts:371-379` 只在 `event.persisted` 时调用 reactivate。变异日志 `.scratch/t007_master/bfcache_pageshow_mutant.log` 显示去掉 persisted 判断后该用例在 `_k=1` 处失败，绿日志 `.scratch/t007_master/bfcache_pageshow.log` 通过；本轮全量 Vitest 亦通过。
  - p006–p010 处置合理：p006 为 t005/t006 既有的 Browser 可读 `agent_secret.txt`，超出 t007 契约；p007 为 t007 自身残留文案，登记待 t008/t011 收口；p008 为 Agent 未触发官方 RESUMED 的协议优化；p009 为 t004 既有固定 sleep；p010 为生产镜像 vendor 构建布线。均非本轮新阻断项，不重复报告。
- 改测方向复核：无「迁就实现」的改测。本轮增量（01:31 之后）只改强断言：静音断言从空真改为要求元素非空（app/session 两处），harness 改读真实凭证目录，新增「不伪造 runtime」与 bfcache 用例；没有删除、反转或弱化既有断言，也没有测试文件删除。
- 契约区 drift：AC-001~AC-010 由 `[ ]` 变 `[x]` 属实施完成打勾；AC-002/AC-007 的措辞变更已在 task.md 上下文区记录（官方 `resume_key` 每次实例化随机），非未授权改需求，不另出 finding。
- 本轮新发现：2 条（0 blocking，2 minor）。
- 未进表的提示：
  - 当前树无 r4 门禁产物：`frontend_app/session/media/display/ice_failure/auth` 五个 E2E 与 `stream_selkies_tokens_e2e.py` 在 sec001（23:04）与 Round 2 夹具修复之后均未重跑；AC-002/003/010 的 Docker 真实栈证据仍依赖 r3（22:13，修复前）。合并前必须跑 r4 `frontend_e2e` 与 `stream_e2e`。
  - `tests/e2e/test_frontend_adapter_build.py:45-62` 只验证构建产物含 `__cbrowserAdapterSource` 与源路径字符串，不重跑构建；因门禁顺序先 build 后测试、且 p010 已登记生产镜像布线，暂不作为 finding。
- 总体判断：Round 2 的两条 blocker（夹具凭证路径、静音空真断言）与本轮关注的 code f009/f010 均已真实修复且无换形式弱化；本轮无新的 critical/important，仅在补测试覆盖与收紧断言上有 2 条 minor，故 PASS。

### AC 复验方式

- AC-001：`trust_prior` — 双标签页/导航依赖 r3 `frontend_e2e.log`（21 passed）与 `tests/e2e/test_frontend_app_e2e.py:300-430`；本地复跑 Vitest `router.test.tsx` 仅验证 URL/localStorage 隔离。
- AC-002：`trust_prior` — 依赖 `tests/e2e/test_frontend_app_e2e.py:435-597` 与 `tests/e2e/test_frontend_session_e2e.py:122-243`；noopener 单测（`BrowserSessionView.test.tsx:452-470`）本地复跑通过，但夹具修复后的 E2E 未重跑。
- AC-003：`trust_prior` — 依赖 `tests/e2e/test_frontend_app_e2e.py:561-567`（严格 `running`）与 session E2E（`:232,237` 偏宽，见 f012）；未复跑 Docker。
- AC-004：`trust_prior` — 依赖 `tests/e2e/test_frontend_media_e2e.py:435-570`、`test_frontend_display_apply_e2e.py`；适配层拦截单测本地复跑通过。
- AC-005：`trust_prior` — 依赖 `tests/e2e/test_frontend_media_e2e.py:577-780`、`test_frontend_app_e2e.py:650-725`、`test_frontend_session_e2e.py:285-350`。
- AC-006：`re_verified` — 本地 Vitest 13 files / 104 passed；`tests/integration/test_sse_epoch_integration.py`、`test_api_sse_events.py` 3 passed，SSE epoch/断线恢复走真实 HTTP。
- AC-007：`trust_prior` — 依赖 `tests/e2e/test_frontend_app_e2e.py:753-955`、`test_frontend_ice_failure_e2e.py:144-188`；bfcache 单测已本地复跑并有变异日志。
- AC-008：`trust_prior` — 本地复跑 entrypoint/unit 24 passed；Selkies 403 真实行为依赖 `test_stream_selkies_tokens_e2e.py:149-193`（Docker，未复跑）。
- AC-009：`re_verified` — 本地复跑 `tests/integration/test_runtime_coordinator_integration.py` 5 passed（Supervisor 不可达保留意图、恢复收敛）；真实容器启停依赖 r3/r4 E2E。
- AC-010：`re_verified` — 本地复跑 `test_supervisor_selkies_tokens.py`、`test_supervisor_selkies_token_isolation.py`、`test_stream_selkies_tokens.py`、display config 共 24 passed；真实 Gateway 隧道/容器日志扫描依赖 `test_stream_selkies_tokens_e2e.py`（Docker，未复跑）。
- coverage = 3 / 10
- 建议合并前人工抽查 trust_prior 项（AC-001/002/003/004/005/007/008 的 Docker 真实栈行为），并先补跑 r4 `frontend_e2e` 与 `stream_e2e`。
- 本轮本地执行命令：`NODE_OPTIONS=--no-experimental-webstorage npm test --prefix src/frontend`（13 files / 104 passed）；`pytest tests/unit/...` 24 passed；`pytest tests/integration/test_sse_epoch_integration.py tests/integration/test_api_sse_events.py` 3 passed；`pytest tests/integration/test_runtime_coordinator_integration.py` 5 passed；`pytest --collect-only` 收集 16 个前端 E2E。

- 系统性 follow-up：无新增；f011/f012 属本 task 小修，p006–p010 已登记。

reviewed_scope: d89125a5fbd33eae

## Round 4 (2026-11-01T05:24:07+08:00)

### Findings

#### t007_test_f013 - audio_status 单测 `samples()` 丢弃 `totalAudioEnergy`，"静音不判故障"用例输入与名称不符

- 严重度：minor
- 锚点：AC-005「运行/媒体/音频故障分别给出可理解状态」
- 位置：`src/frontend/src/features/browser-session/audio_status.test.ts:8-17`；用例 `:56-63`；生产 `src/frontend/src/features/browser-session/audio_status.ts:24-58`
- 问题：`samples()` 只复制 `at/present/bytesReceived/packetsReceived`，用例传入的 `totalAudioEnergy: 0`（`:58`）被静默丢弃，实际输入与 `:47-54` 的 `normal` 用例等价。当前 `deriveAudioStatus` 不读取 `totalAudioEnergy`，故不影响本轮结论；但该用例无法证明“能量为 0 的静音 Opus/DTX 不判故障”，测试意图与输入不一致。
- 建议：`samples()` 增加 `totalAudioEnergy: value.totalAudioEnergy`，保留该用例；或删除未使用字段与相关注释，避免虚假覆盖。

### 结论

- 前轮 finding 复核（以 diff/代码为准，不采信处置表自述）：
  - `t007_test_f011`：仍按 Round 3 处置为遗留 `p011`。`docs/pending/todo/p011_t007_test_minor_followups.md:5` 与 f011 描述一致；minor，不阻断。
  - `t007_test_f012`：同上，`p011:6` 记录一致；minor，不阻断。
  - Round 3 无 blocker；本轮无新增 blocker。
- 改测方向复核：本轮对 `audio_status.test.ts` 只新增 `keeps reporting normal for healthy audio sampled about once per second`（`:85-104`）；RED `.scratch/t007_master/red_audio_status_flap.log` 显示旧实现 8 tests/1 failed（预热后 11 次全 unknown），GREEN `green_audio_status_flap.log` 8 passed。既有 7 用例在旧/新实现下输出相同（我本地跑 8 passed；`.scratch/t007_review_test/audio_flap_cadence_sim.py` 按 1.05s 采样在样本时刻模拟旧实现恒 unknown、新实现 normal），无「迁就实现」的改测。
- 本轮新发现：1 条（0 blocking，1 minor）。
- 未进表的提示：
  - `audio_status.test.ts:85-104` 在测试内复制了生产 `useBrowserSession.ts:281-283` 的历史裁剪 filter，且 `slice(0,2)` 未断言 index 2；它不触达 hook 的 `setInterval` 轮询路径。修复后的真实浏览器证据仍应依赖 `tests/e2e/test_frontend_media_e2e.py::test_ac005_audio_diagnostics_normal_silence_and_link_failure`（`:877-890`）。r4 `frontend_build`（05:05）早于 audio 修复（05:10），且 r4 当前无 `frontend_e2e.log`；合并前必须重建前端并重跑该 E2E（黑盒 r1 两次复现 `音频状态未知`，`.scratch/lane_evidence/blackbox_r1/logs/frontend_e2e_full.log`）。
  - r4 `sup_lifecycle` rc=1：`tests/e2e/test_supervisor_retry_e2e.py::test_supervisor_real_subprocess_retry_e2e` 在 40s 等待内未创建 inst_2（`.scratch/project_gates/r4/sup_lifecycle.log:373`）；该用例在 r1/r2/r3 均 6 passed。属前端增量之外的既有 supervisor E2E，需主控判定 flake 复跑或回归。
  - `docs/blueprint/testing.md:160-174` 已补 `CBROWSER_GATEWAY_TEST_IMAGE` 与 uvicorn/fastapi/sqlalchemy 等依赖（黑盒 #2 已修）；该代码块仍未像其他章节显式设置 TMPDIR/UV_CACHE_DIR，依赖外层环境，属文档健壮性 minor，未进 finding。
  - `p012` 记录 AC-010 stream tokens E2E 偶发 1006；r4 `stream_e2e` 19 passed 未复现，同意登记为 pending。
- 总体判断：本轮增量修复方向正确、单测可信且 RED/GREEN 可复现；仅 1 条 minor，无未解决 critical/important，PASS。
- 系统性 follow-up：无新增；f011/f012 已在 `p011`，stream tokens 抖动已在 `p012`。

### AC 复验方式

- AC-001：`trust_prior` — 依赖 r3 `frontend_e2e.log` 与 `tests/e2e/test_frontend_app_e2e.py:300-430`；本轮增量未触碰。
- AC-002：`trust_prior` — 依赖 r3 E2E 与 `BrowserSessionView.test.tsx` noopener 单测；本轮增量未触碰。
- AC-003：`trust_prior` — 依赖 r3 E2E；本轮增量未触碰。
- AC-004：`trust_prior` — 依赖 r3 E2E；本轮增量未触碰。
- AC-005：`trust_prior` — 音频诊断函数已本地复跑 `audio_status.test.ts` 8 passed 并用 cadence 模拟验证；真实浏览器 E2E 修复后未重跑，输入/静音/标签同步/延迟仍依赖 r3 `test_frontend_media_e2e.py` 与 `test_frontend_app_e2e.py`。
- AC-006：`re_verified` — 本地 `NODE_OPTIONS=--no-experimental-webstorage npm test --prefix src/frontend` 13 files/105 passed；本地复跑 `tests/integration/test_sse_epoch_integration.py`、`test_api_sse_events.py` 等 36 passed。
- AC-007：`trust_prior` — 依赖 r3 E2E 与 bfcache 单测；本轮增量未触碰。
- AC-008：`trust_prior` — 依赖 r3 `stream_e2e` 与 entrypoint/unit；本轮增量未触碰。
- AC-009：`re_verified` — 本地复跑 `tests/integration/test_runtime_coordinator_integration.py`、`tests/unit/test_api_runtime_coordinator.py`、`test_runtime_coordinator_stop_paths.py`（36 passed 组内），含 Supervisor 不可达保留意图/恢复收敛。
- AC-010：`re_verified` — 本地复跑 `test_supervisor_selkies_tokens.py`、`test_supervisor_selkies_token_isolation.py`、`test_stream_selkies_tokens.py`（36 passed 组内）；真实 Gateway 隧道/容器日志扫描依赖 r4 `stream_e2e` 19 passed（读日志，未亲自跑 Docker）。
- coverage = 3 / 10
- 建议合并前人工抽查 trust_prior 项（AC-001/002/003/004/005/007/008 的 Docker 真实栈行为），并先重建前端重跑 `test_frontend_media_e2e.py::test_ac005_audio_diagnostics_normal_silence_and_link_failure`。
- 本轮本地执行命令：`NODE_OPTIONS=--no-experimental-webstorage npm test --prefix src/frontend`（13 files / 105 passed）；`pytest tests/integration/test_runtime_coordinator_integration.py tests/integration/test_sse_epoch_integration.py tests/integration/test_api_sse_events.py tests/unit/test_api_runtime_coordinator.py tests/unit/test_runtime_coordinator_stop_paths.py tests/unit/test_supervisor_selkies_tokens.py tests/unit/test_supervisor_selkies_token_isolation.py tests/unit/test_stream_selkies_tokens.py`（36 passed）。

reviewed_scope: 9513f639f821e03b

verdict: PASS

## Round 5 (2026-11-01T06:10:48+08:00)

### Findings

无新增 finding（本轮只审 r4 之后的增量：Supervisor 重启凭证文件回归修复及其测试）。

### 结论

- 前轮 finding 复核（以当前 diff/代码为准，不采信处置表自述）：
  - `t007_test_f011`：仍存在，已按 minor 登记 `docs/pending/todo/p011_t007_test_minor_followups.md:5`。`src/frontend/src/features/profiles/useProfilesQuery.test.tsx` 仍只覆盖“合并已缓存 runtime / 无缓存不伪造”（`:140-191`），无 `getRuntime` 调用计数或 runtime 查询 `isInvalidated` 断言；`:134` 的 `listCallCount` 属创建 mutation 后的列表重取，不能替代。
  - `t007_test_f012`：仍存在，`p011:6`。`tests/e2e/test_frontend_session_e2e.py:232,237` 仍接受 `("running", "created")`。
  - `t007_test_f013`：仍存在，`p011:7`。`src/frontend/src/features/browser-session/audio_status.test.ts:8-17` 的 `samples()` 仍不复制 `totalAudioEnergy`。
  - Round 4 无 critical/important；无遗留 blocker 需复核。
- 本轮增量复核（`selkies_tokens.py` / `core.py` / 三个测试文件，mtime 05:54–05:55）：
  - 生产：`src/backend/cbrowser/supervisor/selkies_tokens.py:40-57` 每实例写 `selkies_tokens_<runtime_instance_id>.json` 并删除同目录旧文件；`src/backend/cbrowser/supervisor/core.py:498-505` 调用点传入 `runtime_instance_id`（`core.py:421` 生成 `inst_<12hex>`，匹配 `_INSTANCE_ID`，不会误抛）。
  - 单测：`tests/unit/test_supervisor_selkies_token_instances.py:12-30` 直接调用生产函数，断言两实例路径不同、旧文件已删、目录只剩新文件、0600、controller token 一致；`:32-45` 拒绝路径逃逸且不落文件。非同义反复：若实现改为同名覆盖，`first != second` 与 `not first.exists()` 会同时失败；无 mock。
  - 集成位点：`tests/unit/test_supervisor_selkies_tokens.py::test_supervisor_core_start_profile_provisions_selkies_tokens` 断言生产 `start_profile` 产出的文件名为 `selkies_tokens_{session.runtime_instance_id}.json`，并保留 0600 / 不在 runtime 目录 / 不泄漏 master token。
  - 真实回归：`tests/e2e/test_supervisor_retry_e2e.py::test_supervisor_real_subprocess_retry_e2e` 修复后由主控两次复跑通过——`.scratch/t007_master/token_instance_verify/retry_1.log`、`retry_2.log` 各 `1 passed in 95.9s`，镜像构建于 05:55（修复之后）；该用例正是 r4 失败项（r4 `sup_lifecycle.log` 在 `assert inst_2 is not None` 失败，`retry_debug5/clogs/1793483590841.log:2` 有第二次 Stream 启动的 `Selkies credentials file not found or not a regular file` 原文）。
  - 同批复跑 `.scratch/t007_master/token_instance_verify/rest.log` 为 `14 passed in 410.65s`，其 basetemp 目录覆盖更新后夹具与 token E2E：`test_ac002_ac003_ac010_identit...`、`test_e2e_ac010_gateway_topol...`、`test_ac004_ac005_input_mute...`、`test_ac007_freeze_resume...`、`test_ac009_ui_start_stop...` 等，说明 `frontend_app_probe/harness.py` 改 glob 后前端 E2E 已重跑（本轮无“改完未跑”缺口）。
  - 本地复跑：`tests/unit` 全量 307 passed；`test_supervisor_selkies_token_instances.py`+`test_supervisor_selkies_tokens.py`+`test_supervisor_selkies_token_isolation.py`+`test_supervisor_display_config.py` 15 passed；`tests/integration/test_runtime_coordinator_integration.py test_sse_epoch_integration.py test_api_sse_events.py` 8 passed。
- 改测方向复核（逐处）：
  - `tests/unit/test_supervisor_selkies_tokens.py`：固定 `selkies_tokens.json` 改为 `selkies_tokens_{runtime_instance_id}.json`，随本次修复的契约变化更新期望，且保留 0600、不在 Browser 可见目录、不泄漏 token 的强断言——改的是“断言应有的预期”，非迁就当前实现。
  - `tests/e2e/test_stream_selkies_tokens_e2e.py:427-433`：固定路径改为 `glob("selkies_tokens_*.json")` 并要求恰好 1 个，后续 0600、父目录不在 Browser 挂载、Browser 无法读取等断言未动；等价或更严格。
  - `tests/fixtures/frontend_app_probe/harness.py:111-119`：同样改为 glob 且要求恰好 1 个，否则 `RuntimeError`，无静默吞错。
  - 未见删除/反转/注释断言、`.skip`/`.only`、`type: ignore`、条件跳过或阈值放大；相对 diff_anchor 无测试删除（`git diff --name-status` 中 tests 仅 A/M）。
- 本轮新发现：0 条。
- 未进表的提示：
  - r5 最终门禁在本次评审时仍在运行（截至 06:07 只完成镜像构建），合并前必须等 r5 的 `sup_lifecycle`（含修复后 retry 用例）与 `frontend_e2e` 全绿；本轮已用主控复跑日志确认修复有效，但 r5 产物本身尚在生成。
  - 新交付 `tests/unit/test_supervisor_selkies_token_instances.py` 仍为 untracked（未 `git add -N`）；scope 指纹按 `ls-files --cached --others` 包含未跟踪内容，本报告已覆盖该文件，但只跑 `git diff` 的流程会漏掉它。
  - `test_stream_selkies_tokens_e2e.py:430` 的 glob 不再钉住 instance-id 后缀；如需防“任意文件名”回归可再断言文件名含 `runtime_instance_id`（覆盖扩展，非阻断）。
  - `p012`（同 tab 驱逐偶发 1006）仍待处理，r4 `stream_e2e` 19 passed 未复现，同意维持 pending。
- 总体判断：增量生产修复有单测与真实 Docker 回归双证据，改测方向正确；无未解决 critical/important，本轮 PASS；合并前置条件仍是 r5 门禁全绿。
- 系统性 follow-up：无新增；f011/f012/f013 已在 `p011`，stream tokens 抖动已在 `p012`。

### AC 复验方式

- AC-001：`trust_prior` — 本增量未触碰；依赖 r3/r4 `frontend_e2e` 与 `tests/e2e/test_frontend_app_e2e.py` 双标签页断言。
- AC-002：`trust_prior` — 依赖 `.scratch/t007_master/token_instance_verify/rest.log`（含 `test_ac002_ac003_ac010_identity_copy_close_and_tokens`，14 passed）与 `BrowserSessionView.test.tsx` noopener 单测；未亲自跑 Docker。
- AC-003：`trust_prior` — 同批 `rest.log` 的 `test_ac002_ac003_ac010_*` 覆盖关页不停容器；未复跑 Docker。
- AC-004：`trust_prior` — 未触碰；依赖 r3/r4 `test_frontend_media_e2e.py`、`test_frontend_display_apply_e2e.py`。
- AC-005：`trust_prior` — 未触碰；依赖 r3/r4 `test_frontend_media_e2e.py` 与 r4_final 前端 E2E 22 passed。
- AC-006：`re_verified` — 本轮本地复跑 `tests/integration/test_sse_epoch_integration.py`、`test_api_sse_events.py` 等 8 passed；`tests/unit` 全量 307 passed。
- AC-007：`trust_prior` — 依赖 r4 E2E 与 bfcache 单测；本增量未触碰。
- AC-008：`trust_prior` — 依赖 r4 `stream_e2e` 19 passed 与 entrypoint/unit；本增量未触碰。
- AC-009：`re_verified` — 本地复跑 `tests/integration/test_runtime_coordinator_integration.py`（含 Supervisor 不可达保留意图/恢复收敛）与 `tests/unit` 全量；真实重启恢复由 `retry_1/2.log` 两次 1 passed 佐证（读日志）。
- AC-010：`re_verified` — 本地复跑 4 个 unit 文件 15 passed；真实 Gateway 隧道/容器扫描依赖 `rest.log` 的 `test_e2e_ac010_gateway_topology_*` 与 r4 `stream_e2e` 19 passed（读日志，未亲自跑 Docker）。
- coverage = 3 / 10
- 建议合并前人工抽查 trust_prior 项（AC-001/002/003/004/005/007/008 的 Docker 真实栈行为），并确认 r5 门禁已完成。
- 本轮本地执行命令：`PYTHONPATH=src/backend uv run --no-project ... pytest tests/unit`（307 passed）；`tests/unit/test_supervisor_selkies_token_instances.py tests/unit/test_supervisor_selkies_tokens.py tests/unit/test_supervisor_selkies_token_isolation.py tests/unit/test_supervisor_display_config.py`（15 passed）；`tests/integration/test_runtime_coordinator_integration.py tests/integration/test_sse_epoch_integration.py tests/integration/test_api_sse_events.py`（8 passed）。

reviewed_scope: a006b995998b9c28

verdict: PASS
