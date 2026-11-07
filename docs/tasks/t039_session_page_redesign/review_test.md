# Task review t039（reviewer_focus: 测试）

- task：`t039_session_page_redesign`
- spec：`docs/tasks/t039_session_page_redesign/task.md`
- diff_anchor：`90293b4ae3fc74d39de7449f2a419b471628f431`
- target：`git -C '<repo_root>' diff 90293b4ae3fc74d39de7449f2a419b471628f431`
- round：1
- reviewed_at：2026-11-07T21:18:00+08:00

reviewed_scope: ccca6d13972b1388

## Findings

### t039_test_f001 - 音频诊断 E2E 把「连接状态」精确值断言放宽为子串包含，属迁就实现的改测

- 严重度：important
- 锚点：AC-004（诊断浮层按设计系统重建、行为语义不变）、AC-001（会话阶段与恢复语义）；命中「改测方向复核：让断言迁就当前实现」与危险模式「弱化断言」（`==` → `in`）
- 位置：`tests/e2e/test_frontend_media_e2e.py:882-883`、`:924-926`（`test_ac005_audio_diagnostics_normal_silence_and_link_failure`）；另 `:837-848`（`read_audio_status`）
- 问题：旧断言读具体 `diag-conn-state` 元素并 `assert conn_state == "connected"`（精确值）。本次改为读整个 `sess-diag-overlay` 的 inner_text 并 `assert "连接状态" in conn_state and "connected" in conn_state`。精确比较退化为子串包含：`"disconnected"` 本身含 `"connected"`，且 overlay 内 ice/signaling 等其它行的 `"connected"` 也会让断言通过。即连接状态变为 `disconnected` / `failed`、或该行值缺失时，这条「音频链路失败后连接仍 connected」的 E2E 断言仍绿，掩盖连接异常回归。`read_audio_status` 同时从具体 `diag-audio-status` 元素退化为整块 overlay 文本。D16 删除旧 testid 有归因，但并非必须放宽预期：可给诊断值加新 `sess-diag-*` testid（符合「data-testid 按新组件结构命名」），或以 label→dd 精确定位后恢复精确值比较。实际把预期改成迁就「新 `DiagnosticsOverlay`（`SessionPage.tsx:115-124`）未给每个值加 testid」的实现，与 TDD 顺序相反。
- 建议：在 `DiagnosticsOverlay` 的 `<dd>` 上加稳定 `sess-diag-conn-state` / `sess-diag-audio-status` testid，E2E 恢复对 connectionState 值的精确相等断言；`read_audio_status` 改回读具体值元素。

### t039_test_f002 - D16 承诺的「五态标签/en 文案」被纯函数与自反恒真断言替代，组件渲染覆盖丢失

- 严重度：minor
- 锚点：AC-004（音频状态、诊断浮层行为语义不变）；`docs/tasks/t039_session_page_redesign/progress.md:125-126` 的 D16 测试处置清单承诺
- 位置：`src/frontend/src/features/browser-session/session_audio_control.test.tsx:168-256`（`covers all five AudioStatus values and their labels via deriveAudioStatus`、`:258-278`）
- 问题：D16 清单把删除的 `media_controls.test.tsx` 的「renders every audio status label」「renders localized labels in English when the locale is en」映射到本文件「五态标签」「en 文案」。实际新用例只调 `deriveAudioStatus` 纯函数与 `useI18n` 字典，断言 `expect(en[labelKey]).toBe(label)`（`label` 本身即 `en[labelKey]`，恒真自反）、`expect(label.length).toBeGreaterThan(0)`，未渲染任何组件。产品 `DiagnosticsOverlay` 的 `audioLabels` 映射（`SessionPage.tsx:81-95`）与 `SessionPage.test.tsx:489-498` 的浮层指标断言都不覆盖 5 个音频状态文案。旧组件渲染级覆盖丢失，且含凑数的恒真断言；核心 `expect(derive()).toBe(status)` 真实，故不制造 AC 假绿，定为覆盖退化。
- 建议：补一条渲染 `DiagnosticsOverlay`/`SessionPage` 诊断浮层、遍历 5 种 `audioStatus` 验证 en/zh UI 文案的用例；删除 `en[labelKey] === label` 自反断言。

### t039_test_f003 - 「每个值可复制」只验首个值，「最近错误」无非空展示断言

- 严重度：minor
- 锚点：AC-005（面板中的值与 API 响应一致、每个值可复制）
- 位置：`src/frontend/src/features/browser-session/SessionDetailsPanel.test.tsx:207-214`（`copies each value through the clipboard and confirms`）、`:165-189`
- 问题：用例名为「copies each value」，实际只点 `buttons[0]` 断言 `writeText("Alpha")`，配 `expect(buttons.length).toBeGreaterThan(0)` 存在性断言；未验证其余每个值的复制按钮各自写入正确值。AC-005 明确列出的「最近错误」`last_coordinator_error` 在 `renders all four sections` 用例里 fixture 为 `null`，无非空展示断言。属「覆盖可更广」，不阻断，但用例名与断言强度不符。
- 建议：遍历 `getAllByTestId(SESS_COPY_VALUE)` 逐值断言写入内容；补 `runtime({ last_coordinator_error: "..." })` 的非空展示用例。

### t039_test_f004 - host E2E fixture 退化为 test-only 平行实现壳，部分 UI 断言不再触达产品 SessionPage

- 严重度：minor
- 锚点：AC-008（真实栈会话 E2E）；测试可信维度「生产逻辑可达」（测试基础设施缺口，不用平行实现冒充覆盖）
- 位置：`tests/fixtures/frontend_probe/host_entry.tsx:18-70`；`tests/e2e/test_frontend_session_e2e.py:592-624`
- 问题：host fixture 从挂载产品 `BrowserSessionView` 改为手写 `HostSessionView`，自行拼出 `sess-iframe` / `sess-diag-overlay` / `sess-audio-toggle`，3 个真实栈 E2E 用例不再触达产品 `SessionPage`。其中 `sess-diag-overlay` 在壳里无条件渲染（`host_entry.tsx:40-55`），使 `test_frontend_session_freeze_resume_and_diagnostics:598-604` 的「诊断浮层必须可见」不再验证任何产品行为；`sess-audio-toggle` 为手写 button。已独立核实产品级承接：`FrontendAppTopologyHarness.prepare_static` 服务完整 Vite dist（`tests/fixtures/frontend_app_probe/harness.py:21-52`），`test_frontend_app_e2e.py:507-643`（同 Profile 多页面、复制标签页身份重映射）、`test_frontend_media_e2e.py:435-525`（可见性暂停与恢复）、`test_frontend_app_e2e.py:384-505`（双标签）及 `wait_session_ready`（`sess-iframe`+`sess-header`）覆盖 AC-008 的产品路径，故不构成 AC 假绿，定为测试基础设施缺口。
- 建议：把壳内 UI 断言（overlay / stage title / action / audio toggle）迁到产品级 E2E，壳只保留 iframe 协议探针；或让 fixture 复用产品组件并注入认证态。

## 结论

- 前轮 finding 复核：无（本轮为 Round 1）
- 改测方向复核：本轮有 1 处「让断言迁就当前实现」的改测（f001，`test_frontend_media_e2e.py` 连接状态断言由精确值放宽为子串包含）。其余修改既有测试均为「增强门控 / 等价或更强替换」：`test_frontend_app_e2e.py:126-178` `launch_profile_via_ui` 新增 `wait_session_ready`（`sess-iframe`+`sess-header`）与轮询 runtime API 直到 `observed_state == "running"`，恢复 t038 就绪语义（原 `first_frame_ms <= 8000` 断言未放宽）；`test_stream_runtime_e2e.py:1288-1307`、`test_runtime_coordinator_integration.py:299-322` 用 `poll_until` 就绪门控且原断言原样保留；`test_supervisor_retry_e2e.py:332-440` 改用服务端 `backoff_started_at` 事实字段并新增 `(next_retry_at - backoff_started_at) == 10.0` 精确断言，`10.0` 下界与 `max(5.0, 10.0*0.5)` 容差未放宽；`ProfileIsolation.test.tsx` 删 3 例由 `SessionPage.test.tsx:404-487` 跨 Profile 隔离 3 例等价承接（D16 清单 `progress.md:63-146` 逐用例写明去向）；`scripts/verify_frontend_dist.py:220-244` 删除因 D16 组件删除而失效的 `.bg-primary` 断言，另立 `.bg-accent` / `--color-accent` / `--color-surface` 与默认调色板泄漏负向断言，并配 `test_frontend_build_wiring.py:106-127` 2 例新语义 TDD 单测。
- 本轮新发现：4 条（1 important、3 minor）
- 未进表的提示：
    - `SessionPage.test.tsx:52-62` 与 `ProfileIsolation.test.tsx:31-41` `vi.mock("./useBrowserSession")` mock 同项目模块（组件层隔离）。会话状态机由 `useBrowserSession.stages.test.tsx`（真实 `renderHook` 13 例）、`useBrowserSession.test.tsx`（`observed_state`→stage 映射）、`useBrowserSession.transportRecovery.test.tsx` 走真实 hook 覆盖，符合「会话阶段测试走真实 `useBrowserSession`」策略；未发现 mock 掉被测逻辑制造 AC 假绿。
    - `src/frontend/src/app/router.test.tsx:221` 用例 timeout 由默认 5000ms 增至 20000ms：已调查，断言未弱化、不制造假绿，属新页面渲染链变长的容量调整，不作为 finding。
    - D16 清单承诺的 `SessionPage.test.tsx`「reconnect 更新 iframe src」未落；但 `useBrowserSession.stages.test.tsx:142-152`（reconnect 递增 reloadKey）与 `test_frontend_app_e2e.py:993-998`（`_k=` 递增）承接，组件层可补一条。
    - AC-006「专注模式下组合键不被宿主占用」仅有组件层「不绑定 keydown / 回调不触发 / mousedown 不冒泡」断言（`SessionHeader.test.tsx:350-369`、`FocusModeToolbar.test.tsx:61-86`），无专注模式下真实键盘转发的 E2E；属覆盖可更广。
    - AC-008「应用并重启」子场景无独立真实栈 E2E 点击（全 `tests/` 无 `sess-apply-restart` 点击；`test_frontend_display_apply_e2e.py` 基线仅剩 1 例且 helper 为遗留死代码），由 `SessionHeader.test.tsx:273-284`、`SessionPage.test.tsx:300-308`、`useProfilesQuery.applyresume.test.tsx` 覆盖；为基线状态，非本 task 假绿。
    - 范围外观察：backend 退避事实字段 / Supervisor / migration / `test_supervisor_retry_e2e.py` 改动与 t039 会话页无关（门禁稳定性修复一并交付），属 commit 范围问题，非测试可信问题。
- 总体判断：8 条 AC 打勾均有真实测试或验证支撑、无 TICK-VOID，但存在 1 条未解决 important（f001 弱化断言 / 迁就实现的改测），按判定式本轴判定 FAIL。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`SessionStagePanel.test.tsx:57-121` 按 12 个非 connected 阶段逐条断言原因标题与可执行操作（组件按 `STAGE_TITLE_KEYS` 按 stage 映射，非恒真），`useBrowserSession.stages.test.tsx` 走真实 hook 13 例覆盖恢复语义，D16 删除的 5 个测试文件在 `progress.md:63-146` 逐用例写明去向；`npm test --prefix src/frontend` 独立重跑 59 文件 402 passed。
- AC-002：TICK-VALID，re_verified。`SessionEntryPage.test.tsx:160-198` 断言仅运行中环境为真实 `/session/{id}` 链接并含状态、无运行中时为空态；侧栏「会话」回跳由 `ProfileIsolation.test.tsx:268-302` 的 sessionStorage target 4 例与 `router.test.tsx:192-203` 覆盖。
- AC-003：TICK-VALID，re_verified。`EnvironmentSwitcher.test.tsx:191-253` 断言分组、大小写不敏感搜索、3 个 `href=/session/{id}` 真实链接、Esc 不关闭 popover；产品级 `test_frontend_app_e2e.py:612-643` 断言同 Profile 双标签页 tab_id 独立与复制标签重映射互不影响。
- AC-004：TICK-VALID，re_verified。`SessionHeader.test.tsx:214-348` 断言 observed/transport 四态/待应用标记/应用并重启/5 个按钮回调，`SessionPage.test.tsx:300-308` 断言应用并重启触发 `setDesiredState`（核实 `useProfilesQuery.ts:377` 链路）；诊断连接状态 E2E 断言弱化见 f001（important，未使打勾作废）。
- AC-005：TICK-VALID，re_verified。`SessionDetailsPanel.test.tsx:165-260` 断言四区 join 值（含 `browser_product`/`browser_user_agent`/实例 ID/启动时间）、剪贴板复制与缺失字体告警，`SessionPage.test.tsx:281-289` 断言 `cbrowser.session.details_open` 重挂载后保持。
- AC-006：TICK-VALID，re_verified。`SessionPage.test.tsx:265-279` 断言专注切换前后同一 iframe DOM 节点不重建，`FocusModeToolbar.test.tsx:31-86` 断言顶部热区显示退出工具条/Esc 不退出/mousedown 不冒泡，`SessionHeader.test.tsx:350-369` 与 `EnvironmentSwitcher.test.tsx:237-253` 断言 Esc 与组合键不触发宿主回调、不关闭 popover。
- AC-007：TICK-VALID，re_verified。`design_tokens.test.mjs:177-250` 断言 `assertNoColorViolations`/`runLintSources` 对默认调色板类、white/black、hex/rgb/hsl 字面量抛错并放行语义类，`design_tokens.mjs:241-245` 的 `--lint` 接入 `runLintSources`、`package.json:24` 的 `design:lint` 调用之；`design_lint.log` 84 files clean、`test_frontend_build_wiring.py:106-127` 2 例新语义负向测试。
- AC-008：TICK-VALID，re_verified。逐行查证 `test_frontend_app_e2e.py:507-643`（多页面/复制身份重映射）、`test_frontend_media_e2e.py:435-525`（可见性暂停与恢复）、`launch_profile_via_ui` 恢复 t038 就绪门控与 `_k=` reload 断言；`e2e.log` 并行 48 passed / 2 skipped、串行 54 passed / 50 deselected、0 failed（真实栈运行本身未独立重跑，据门禁日志与逐行查证断言）。

coverage = re_verified / 8

verdict: FAIL

## Round 2 (2026-11-07T21:45:00+08:00)

- 落点校验：不带 `-C` 的 `git rev-parse --show-toplevel` = `<repo_root>`，通过。
- 复核方式：`git -C '<repo_root>' diff 90293b4ae3fc74d39de7449f2a419b471628f431`（完整 worktree 改动，8627 行 diff / 76 文件）+ 逐行查证修复后测试与产品代码 + 重跑 `npx vitest run`（4 文件 46 passed）+ 新增行危险模式全量扫描。`git status --short` 仅 `review_code.md` / `review_test.md` 两份 review 报告未跟踪，无 reviewer 看不到的交付文件。
- diff_anchor：`90293b4ae3fc74d39de7449f2a419b471628f431`；review_level：`full`。

reviewed_scope: 9f8be56c91945517

## Findings

本轮无新增 finding（0 条）。前轮 4 条逐条复核如下，以 diff / 测试代码 / 重跑为准，不采信处置表自称「已修」。

### 前轮 finding 复核

- **t039_test_f001（important，前轮 blocker）—— 已消除。** `tests/e2e/test_frontend_media_e2e.py`：`read_audio_status` 改回读具体 `[data-testid="sess-diag-audio-status"]`（`:841-849`），新增 `read_conn_state` 读具体 `[data-testid="sess-diag-conn-state"]`（`:851-854`，选择器常量 `:837-838`）；全 diff 已无 `"connected" in overlay_text` 子串包含，`assert conn_state == "connected"` 精确相等恢复（`:890`、`:933`）；音频状态恢复精确相等——`normal_text == "音频正常"`（`:883`）、`silence_text == "音频正常"`（`:906`）、`failure_text == "音频无数据"`（`:926`），poll_until 条件亦由 `in` 改 `==`（`:878`、`:921`）；stage 断言由 `"已连接" in stage_title` 升级为读 `sess-page` 的 `data-stage` 并 `assert stage == "connected"`（`:885-888`、`:928-932`）。产品侧 `SessionPage.tsx:91-127` 的 `DiagnosticsOverlay` 给 7 个 `<dd>` 逐一加了 `sessId("diag", ...)` testid（`:123`：conn-state / ice-state / signaling-state / audio-status / frames-decoded / packets-lost / round-trip-time），`session_keys.ts:26-27` 的 `sessId` = `sess-${key}-${id}`，故 `sess-diag-conn-state` / `sess-diag-audio-status` 与 E2E 选择器一一对应。locale 链核实：`launch_browser()` 注入 `locale="zh-CN"`（`media_e2e.py:110`），产品 `detectInitialLocale`（`i18n.tsx:880-893`）在 localStorage 未设时回退 `navigator.language` → zh，zh 字典 `audioStatusNormal="音频正常"` / `audioStatusNoData="音频无数据"`（`i18n.tsx:563-565`），精确相等与产品真实输出一致，既非假绿也非永假。D16 选择器重命名（`session-audio-toggle-btn`→`sess-audio-toggle`、`data-audio-muted`→`aria-pressed`，`:615-654`）值仍 `== "true"/"false"`，产品 `SessionHeader.tsx:157` 确有 `aria-pressed`。改测方向由「迁就实现」反转为「恢复精确相等 + 产品补 testid」的增强，blocker 真正消除。

- **t039_test_f002（minor）—— 已消除（核心），残留非阻断弱断言。** `session_audio_control.test.tsx:168-263` 点名自反断言 `expect(en[labelKey]).toBe(label)` 已删除，改为 `expect(en[labelKey]).toBe(expected[status])`（`:258`，`expected` 为硬编码字面量 `:248-254`），`expect(derive()).toBe(status)`、`expect(labels.size).toBe(5)` 真实；`SessionPage.test.tsx:317-347` 新增「诊断浮层按五种 audioStatus 渲染本地化文案」用例，遍历 5 态 × en/zh，真实 `renderPage()` 渲染 SessionPage、点 `SESS_DIAG_TOGGLE`、断言产品 `sess-diag-audio-status` 的 `toHaveTextContent(dict[key])`，非纯函数、非恒真（本轮重跑通过）。残留：`:259` `expect(label.length).toBeGreaterThan(0)` 弱存在性、`:277` `expect(result.current.t(key)).toBe(en[key])` 自反——均为 Round 1 既有、非本轮新引入，已有 `toBe(expected[status])`、`not.toBe(zh[key])`、硬编码 `"Audio status unknown"` / `"Audio muted"` 等真实断言兜底，不制造 AC 假绿，属覆盖清理类 minor、f002 已覆盖此区域，不重复出 finding、不阻断。组件渲染级覆盖已补回，f002 核心消除。

- **t039_test_f003（minor）—— 已消除。** `SessionDetailsPanel.test.tsx:207-222` 「copies each value」改为 `getAllByTestId(SESS_COPY_VALUE)` 遍历全部按钮（`expect(buttons.length).toBeGreaterThan(1)`），逐按钮从 `closest("dd")` 取显示值 `shown` 并 `expect(writeText).toHaveBeenCalledWith(shown)`，逐值断言、可抓「复制错值」回归；`:224-229` 新增「shows the last coordinator error when present」用 `runtime({ last_coordinator_error: "Supervisor unreachable" })` 断言非空展示；`:165-189` 四区值断言含 `browser_product` / `browser_user_agent` / 实例 ID / 启动时间。本轮重跑通过。

- **t039_test_f004（minor，撤回）—— 同意撤回。** 独立核实：`tests/fixtures/frontend_probe/host_entry.tsx:18-22` 明确标注 test-only host shell，复用真实 `useBrowserSession` 与 `SessionStagePanel`（`:8-9`）而非全平行壳，`:85` 钉 zh locale；产品级真实栈 E2E 用例仍在——`test_frontend_app_e2e.py:384`（双标签 SSE）、`:507`（复制标签页身份重映射）、`:674`（输入/静音）、`:892`（生命周期恢复），`test_frontend_media_e2e.py`（可见性暂停/恢复与音频诊断精确相等），`test_frontend_session_e2e.py:232/368/508`，AC-008 产品路径由产品级 E2E 承担。`test_frontend_session_e2e.py:597-604` 壳内 `sess-diag-overlay` 可见性断言因壳无条件渲染该 div 而不验证产品行为，但该壳按用户明确要求仅作协议探针、产品覆盖另由上述 E2E 承担，不构成 AC 假绿；f004 本为 minor、非 blocker，流程允许撤回（prompt「撤回配合」）。同意撤回。

- 改测方向复核：本轮无「让断言迁就当前实现」的改测；f001 修复为「恢复精确相等 + 产品补 testid」的增强，f002/f003 为等价或更强替换。

- 本轮新发现：0 条。完整 diff 新增行全量扫描硬危险模式（`.skip` / `.only` / `mark.skip` / `eslint-disable` / `@ts-ignore` / `# type: ignore` / `expect(true)` / `assert True` / 注释掉断言）0 命中；166 条删除的 `expect/assert` 行全部来自 D16 删除的旧测试文件（`BrowserSessionView.test.tsx`、`media_controls.test.tsx`、`clipboard_bridge.test.tsx`、`ProfileIsolation.test.tsx` 等，Round 1 已逐用例写明去向），非本轮修复删断言；修复后测试无新恒真 / 弱化 / 删 expect / mock 被测逻辑 / 阈值放宽（`timeout=30.0/15.0`、`interval=0.5` 未变；`vi.mock("./useBrowserSession")` 为 Round 1 已核实的组件层隔离，会话状态机由真实 hook 测试覆盖）。未凑数制造 finding。

- 未进表的提示：`read_conn_state`（`media_e2e.py:851-854`）无 toggle fallback，依赖 `read_audio_status` 的 poll_until 先点开 `sess-diag-toggle`；若浮层未开将返回 "" 使 `assert conn_state == "connected"` 硬失败（非假绿），不构成 finding。f002 残留的弱/自反断言见上，建议后续删除凑数断言（可选、不阻断）。

- 总体判断：前轮唯一 blocker（f001）经 diff / 代码 / 重跑核实真正消除；f002 / f003 已修、f004 撤回可接受；本轮 0 条新发现、无新 blocker；8 条 AC 打勾经本轮独立复验全部成立。判定 PASS。

- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。本轮重跑 `SessionPage.test.tsx:253-263/362-389`（非 connected 阶段显示 stage panel、runtime_not_ready 显示启动操作并触发 setDesiredState）通过；`SessionStagePanel.test.tsx:57-121` 逐 12 阶段断言原因+操作、`useBrowserSession.stages.test.tsx` 真实 hook 13 例，本轮 diff stat 确认文件仍在（A 文件未变），D16 删旧测试去向见 progress.md。
- AC-002：TICK-VALID，re_verified。`SessionEntryPage.test.tsx:160-198` 断言仅运行中环境为真实 `/session/{id}` 链接并含状态、无运行中时空态；侧栏回跳由 `ProfileIsolation.test.tsx:268-302` 与 `router.test.tsx:192-203` 覆盖，本轮 diff stat / 用例名核实仍在。
- AC-003：TICK-VALID，re_verified。`EnvironmentSwitcher.test.tsx:191-253` 断言分组、大小写不敏感搜索、3 个 `href=/session/{id}` 真实链接、Esc 不关闭 popover；本轮 grep 确认产品级 `test_frontend_app_e2e.py:507-643` 同 Profile 双标签 tab_id 独立与复制重映射用例仍在。
- AC-004：TICK-VALID，re_verified。本轮重跑 `SessionHeader.test.tsx:214-348`（observed/transport 四态/待应用/应用并重启/5 按钮回调）与 `SessionPage.test.tsx:317-347`（新增 5 态 en/zh 诊断浮层渲染用例）通过；f001 修复后 `test_frontend_media_e2e.py:883/890/906/926/933` 恢复音频/连接状态精确相等断言，产品 `SessionHeader.tsx:156-177`/`SessionPage.tsx:96-127` 确有 `aria-pressed` 与 `sess-diag-*` testid。
- AC-005：TICK-VALID，re_verified。本轮重跑 `SessionDetailsPanel.test.tsx:165-189`（四区 join 值）、`:207-222`（遍历全复制按钮逐值断言）、`:224-229`（最近错误非空展示）、`:231-236`（缺失字体告警）与 `SessionPage.test.tsx:281-289`（`cbrowser.session.details_open` 重挂载保持）通过。
- AC-006：TICK-VALID，re_verified。本轮重跑 `SessionPage.test.tsx:265-279`（专注切换前后同一 iframe DOM 节点不重建）通过；`FocusModeToolbar.test.tsx:31-86`、`SessionHeader.test.tsx:350-369` 断言顶部热区退出工具条 / Esc 不退出 / 组合键不触发宿主回调。
- AC-007：TICK-VALID，re_verified。`design_tokens.test.mjs:177-250` 断言 `assertNoColorViolations` 对默认调色板类 / white / black / hex / rgb / hsl 抛错并放行语义类，`design_tokens.mjs:241-245` 的 `--lint` 与 `package.json:24` 的 `design:lint` 接入；本轮全量 diff 新增行见 `+ expect(error.message).toContain("bg-red-500")` 等负向断言（diff `:838-839` / `:890-891`），`test_frontend_build_wiring.py:106-127` 2 例新语义负向测试。
- AC-008：TICK-VALID，re_verified。逐行查证产品级真实栈 E2E 断言——`test_frontend_app_e2e.py:384/507/674/892`（多页面 / 复制标签页身份重映射 / 输入静音 / 生命周期恢复）、`test_frontend_media_e2e.py:435-525`（可见性暂停与恢复）与 `:858-938`（音频链路失败后连接仍 connected 的精确相等断言），`launch_profile_via_ui` 就绪门控与 `_k=` reload 断言；真实栈运行据门禁日志（e2e.log）与逐行查证，本环境未独立重跑 Docker 拓扑。

coverage = re_verified / 8

verdict: PASS

## Round 3 (2026-11-07T22:20:00+08:00)

- 落点校验：不带 `-C` 的 `git rev-parse --show-toplevel`（以 `<repo_root>` 为工作根）= `<repo_root>`，通过。
- 复核方式：`git -C '<repo_root>' diff 90293b4ae3fc74d39de7449f2a419b471628f431`（完整 worktree 改动，77 文件 / 5482 insertions / 2114 deletions；HEAD 即 anchor，全部改动在 worktree）+ 逐行查证修复后测试与产品代码 + 重跑 `npx vitest run`（定向 3 文件 35 passed、全量 59 文件 407 passed）+ `npm run design:lint`（`size+color scan: 84 files clean`）+ 新增/改动测试危险模式全量扫描。`git status --short` 无 reviewer 看不到的未跟踪交付文件；`docs/pending/todo/p053*` 经 glob 确认已删除。`task.md` 契约区 8 条 AC 全部 `[x]`。
- diff_anchor：`90293b4ae3fc74d39de7449f2a419b471628f431`；review_level：`full`。

reviewed_scope: e209862ac6e2d3f1

## Findings

本轮无新增 finding（0 条）。前轮 4 条及用户监督纠正 3 项根因修复的测试落点逐条复核如下，以 diff / 测试代码 / 重跑为准，不采信 `progress.md` 处置表自称「已修」。

### 前轮 finding 复核

- **t039_code_f002 相关测试（Esc 旧测试固化错误预期）—— 已消除。** `EnvironmentSwitcher.test.tsx` 现仅 2 例：`:191-235` 分组/搜索/真实链接、`:237-257` 新用例；固化错误预期的旧用例「does not close the popover when Escape is pressed」已删除（全文无命中）。新用例「closes the popover on Escape via the Radix dismissable layer」真实断言关闭：点击 trigger → `findByRole("dialog")` + `expect(trigger).toHaveAttribute("data-state","open")` → `fireEvent.keyDown(document,{key:"Escape"})` → `waitFor` 断言 `data-state="closed"` + `expect(queryByTestId(SESS_SWITCHER_SEARCH)).toBeNull()`（`:242-256`）。非恒真（open→closed 且搜索框消失才通过）、非弱化（精确属性值 + 元素不存在，无 `toBeTruthy`/`toContain`/子串）。产品 `shared/ui/Popover.tsx:16-32` 为纯 `PopoverPrimitive.Root/Content`、无 `onEscapeKeyDown`/`preventDefault`，`EnvironmentSwitcher.tsx:93-96` 未注入该 prop；Radix DismissableLayer 响应 document 的 Escape 由基线 `shared/ui/ui.test.tsx:81-92`（同一 `fireEvent.keyDown(document,...)` 关闭 Popover 且通过）印证。定向 + 全量 vitest 通过，非永假/假绿。**AC-006 边界理由成立**：`docs/blueprint/frontend.md:24`「不用 Esc 退出（Esc 与常用组合键留给远端 iframe）」约束宿主全局截获发往远端 iframe 的按键；`:69` 明确 Popover 等基于 Radix 原语「Esc 关闭……由原语保证」——弹层打开且焦点在弹层内时 Radix 局部响应 Escape 属浮层生命周期，非宿主全局 keydown 截获。会话页组件无全局 `addEventListener("keydown")`（全前端 grep 仅命中 `AppLayout.tsx:309`、`GroupManagerDialog.tsx:185` 的 React 组件级 `onKeyDown`），`FocusModeToolbar.tsx:13-55` 退出靠悬浮工具条按钮 + `onMouseDown` stopPropagation、无 Esc 监听，`FocusModeToolbar.test.tsx:61`、`SessionHeader.test.tsx:350` 断言 Esc/组合键不触发宿主回调。删 `preventDefault` 后 Esc 不再被「吞掉」；旧用例固化的是「既不关闭也不进 iframe」的错误预期，删除有归因且有反向新用例等价承接，改测方向为「修正错误预期」而非「迁就实现」。

- **t039_code_f003 相关测试（阶段桥接双真相）—— 已消除。** `SessionPage.test.tsx` 新增 3 例：`:352-374`「stopping」（`makeStub({observed:"stopping"})`，`stage-action view-status` 存在、`stage-action launch` `toBeNull()`）、`:376-393`「error」（`stage-action reconnect` 存在）、`:395-414`「stopped」（`stage-action launch` 存在）；三例均 `waitFor` 断言 `SESS_PAGE` 且 `expect(SESS_STAGE).toHaveAttribute("data-stage",X)` + `expect(SESS_IFRAME).toHaveAttribute("data-stage",X)` 三处一致（stopping/error/runtime_not_ready）。产品 `SessionPage.tsx:184-193` 单一 `stage` 表达式（`runtime.observed_state` 桥接 + `session.stage` 回落），`:196` `diagnosticsView.stage`、`:249`/`:256`/`:311` 三处 `data-stage`、`:279` `SessionStagePanel stage` 全用同一变量；`SessionStagePanel.tsx:40-54` 动作映射（stopping→view-status、error→reconnect、runtime_not_ready→launch）与三例断言逐一吻合。若存在第二套独立 stage 计算（双真相），三处 `data-stage` 必分歧，故三处一致断言真实覆盖「单一阶段来源」。断言精确（`toHaveAttribute` 精确相等 + 特定 testid 的 `toBeInTheDocument`/`toBeNull`），无恒真/弱化/删 expect；`vi.mock("./useBrowserSession")` 为 Round 1 已核实的组件层隔离（被测逻辑 `:184-193` 未被 mock，mock 的是 ApiClient 边界）。全量 407 passed 确认真实通过。

- **t039_code_f005 相关测试（AC-005 缺失字体不可复制）—— 已消除。** `SessionDetailsPanel.test.tsx:231-239`「warns about missing fonts and copies the value」：`runtime({missing_fonts:["Arial","SimSun"]})` → `screen.getByRole("alert")` 断言含 `"Arial"`/`"SimSun"` → `within(alert).getByTestId(SESS_COPY_VALUE)`（找不到即抛错，真实断言 `SESS_COPY_VALUE` 存在）→ `fireEvent.click(copy)` → `expect(writeText).toHaveBeenCalledWith("Arial, SimSun")` 精确值断言。产品 `SessionDetailsPanel.tsx:239-265` 缺失字体 Banner（`shared/ui/Banner.tsx:20` `role="alert"`、`:19` testId 透传）内补 `SESS_COPY_VALUE` 按钮（`:249-256`），`copyValue("missing_fonts", missingFonts.join(", "))`（`:255`）→ `navigator.clipboard.writeText`（`:117`）；`"Arial, SimSun"` 与 `join(", ")` 真实输出一致，非恒真、非弱化（spy 精确相等），定向 vitest 通过。

- **t039_test_f001（Round 1 important blocker）—— 保持已消除（精确相等断言未回退）。** 逐行核对 `tests/e2e/test_frontend_media_e2e.py:837-955`：`AUDIO_STATUS_SELECTOR`/`CONN_STATE_SELECTOR` 读具体 `sess-diag-audio-status`/`sess-diag-conn-state`（`:837-854`）；`assert normal_text == "音频正常"`（`:883`）、`silence_text == "音频正常"`（`:906`）、`failure_text == "音频无数据"`（`:926`）、`stage == "connected"`（`:888`/`:932`）、`conn_state == "connected"`（`:890`/`:933`）全为精确相等；poll_until 条件 `== "音频正常"`/`== "音频无数据"`（`:878`/`:921`）；`timeout=30.0`/`interval=0.5` 未变；全段无 `"connected" in ...` 或 overlay 子串包含回退。产品 `SessionPage.tsx:96-127` 的 `sess-diag-*` `<dd>` testid 本轮未动。blocker 未回退。

- 前轮 finding 复核：4 项逐条见上，全部已消除 / 保持已消除；三项根因修复测试均真实、精确、经重跑验证。

- 改测方向复核：无「让断言迁就当前实现」的改测。删除旧 Esc 用例属「修正固化错误预期 + 反向新用例等价承接」的合法删除（有 blueprint 原语语义归因）；3 项均为「补真实覆盖 / 恢复精确语义」的增强，未就地改旧测试预期去迁就新实现输出。

- 本轮新发现：0 条。按 prompt「危险模式扫描」逐项调查新增/改动测试：3 个修复文件逐行读 + `browser-session/*.test.tsx` 与 `design_tokens.test.mjs` grep 硬危险模式（`.skip`/`.only`/`eslint-disable`/`@ts-ignore`/`expect(true)`/`assert True`/注释掉断言/`toMatchObject`/`toBeDefined()`）0 命中；命中 6 处 `toBeTruthy`/`toBeGreaterThan(0)`（`session_audio_control.test.tsx:259`、`SessionStagePanel.test.tsx:96`、`SessionDetailsPanel.test.tsx:216/256`、`useBrowserSession.stages.test.tsx:167/225`）均为 Round 1/2 既有弱断言、有 `toHaveBeenCalledWith`/`toHaveTextContent` 等真实断言兜底、非本轮新引入；新增 5 例无删 expect、无 `.skip/.only`、无 mock 掉被测逻辑、无 timeout/重试/容差放宽（media_e2e `timeout=30.0`/`interval=0.5` 未变）。**`makeStub` 新增 `observed` 选项假绿专项核查**：`SessionPage.test.tsx:165-196` 中 `options.observed ?? "running"`（`:168`）默认 `"running"`；既有 17 例均调 `makeStub()` / `makeStub({configVersion:2})` 等不传 observed，走原默认分支；`setDesiredState`/`stop`（`:182-189`）运行时更新 observed 属 stub 模拟后端状态、不改变初始语义；全量 407 passed 且无既有用例断言反转——**不让既有用例假绿**。`design_tokens.test.mjs:231-249` 新增 2 例集成负向测试走真实 `collectSources`+`runLintSources` 门禁路径（`toThrow`/`not.toThrow`+`toContain("bg-red-500")`），非恒真；`npm run design:lint` 实跑 `84 files clean`。按 Pre-Report Gate 逐条自问与 blocking 硬阈值，无可锚定 AC 违反、无可观测坏结果，无 finding 可定级（不凑数），`t039_test_f005` 起编号本轮不消耗。

- 未进表的提示：`SessionDetailsPanel.test.tsx:231` 新用例触发 `copyValue`（`SessionDetailsPanel.tsx:117-120`）异步 `setCopiedKey` 未包 `act(...)` 产生 React 警告；该警告在全量中于 `useProfilesQuery.*`/`providers.defaults.test.tsx`/`auth_guard.test.tsx`/`i18n.test.tsx` 等既有测试普遍存在，不影响 `expect(writeText).toHaveBeenCalledWith("Arial, SimSun")` 同步 spy 断言，非危险模式清单项、非可观测行为缺陷、不满足 blocking 硬阈值，按 Pre-Report Gate 不出 finding。f002 残留弱/自反断言（`session_audio_control.test.tsx:259/277`）见 Round 2，可选清理、不阻断。

- 总体判断：三项根因修复的测试真实、精确、经定向与全量重跑验证；f001 精确相等断言未回退；本轮 0 新 finding、无新 blocker、无未解决 critical/important；8 条 AC 经本轮独立复验全部成立。判定 PASS。

- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。本轮重跑新增 `SessionPage.test.tsx:352-414` 3 例（stopping/error/stopped 单一阶段 + 三处 `data-stage` 一致 + 精确动作）通过，产品 `SessionStagePanel.tsx:40-54` 动作映射与 `SessionStagePanel.test.tsx:57-121` 逐 12 阶段原因+操作、`useBrowserSession.stages.test.tsx` 真实 hook 13 例共同覆盖全部阶段与恢复语义。
- AC-002：TICK-VALID，re_verified。`SessionEntryPage.test.tsx:160-198` 断言仅运行中环境为真实 `/session/{id}` 链接、无运行中时空态，`ProfileIsolation.test.tsx` 的 sessionStorage target 回跳与 `router.test.tsx` 承接侧栏「会话」；本轮全量 407 passed 确认文件与用例仍在。
- AC-003：TICK-VALID，re_verified。本轮重跑 `EnvironmentSwitcher.test.tsx:191-235`（分组/大小写不敏感搜索/3 个 `href=/session/{id}`）与 `:237-257`（Esc 经 Radix 原语关闭）通过；产品级 `test_frontend_app_e2e.py:507-643` 双标签页 tab_id 独立与复制标签身份重映射用例仍在（grep 核实）。
- AC-004：TICK-VALID，re_verified。本轮重跑 `SessionHeader.test.tsx:214-348`（observed/transport 四态/待应用/应用并重启/5 按钮回调）与 `SessionPage.test.tsx:317-347`（5 态 en/zh 诊断浮层）通过；`test_frontend_media_e2e.py:883/890/906/926/933` 精确相等断言逐行核对未回退，产品 `SessionPage.tsx:96-127` `sess-diag-*` testid 在位。
- AC-005：TICK-VALID，re_verified。本轮重跑 `SessionDetailsPanel.test.tsx:165-189`（四区 join 值）、`:207-222`（遍历全复制按钮逐值断言）、`:224-229`（最近错误非空）、`:231-239`（缺失字体 `SESS_COPY_VALUE` + `writeText("Arial, SimSun")` 精确值）与 `SessionPage.test.tsx:284-292`（`cbrowser.session.details_open` 重挂载保持）通过。
- AC-006：TICK-VALID，re_verified。本轮重跑 `SessionPage.test.tsx:268-282`（专注切换前后同一 iframe DOM 节点不重建）通过；`FocusModeToolbar.test.tsx:61-86`/`SessionHeader.test.tsx:350-369` 断言 Esc 不退出与组合键不占用；`Popover.tsx:16-32` 纯 Radix 原语、无全局 keydown，结合 `frontend.md:24/69` 确认弹层局部 Esc 与「Esc 留给远端 iframe」不冲突，边界成立。
- AC-007：TICK-VALID，re_verified。本轮实跑 `npm run design:lint` → `size+color scan: 84 files clean`；`design_tokens.test.mjs:177-215` 负向断言 + `:231-249` 真实 `collectSources`/`runLintSources` 集成负向测试 + `design_tokens.mjs` `--lint` 分支 + `package.json:24` `design:lint` 接入，对默认调色板类/颜色字面量发现即失败。
- AC-008：TICK-VALID，re_verified。逐行查证产品级真实栈 E2E 断言——`test_frontend_app_e2e.py:384/507/674/892`（多页面/复制标签身份重映射/输入静音/生命周期恢复）、`test_frontend_media_e2e.py:435-525`（可见性暂停与恢复）与 `:858-938`（音频链路失败后连接仍 connected 的精确相等）、`launch_profile_via_ui` 就绪门控与 `_k=` reload；真实栈运行据门禁日志（e2e.log）与逐行查证，本环境未独立重跑 Docker 拓扑。

coverage = re_verified / 8

verdict: PASS
