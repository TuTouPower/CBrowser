# Task review t039（reviewer_focus: 代码）

- task：`t039_session_page_redesign`
- spec：`docs/tasks/t039_session_page_redesign/task.md`
- diff_anchor：`90293b4ae3fc74d39de7449f2a419b471628f431`
- target：`git -C '<repo_root>' diff 90293b4ae3fc74d39de7449f2a419b471628f431`
- round：1
- reviewed_at：2026-11-07T21:20:00+08:00

reviewed_scope: ccca6d13972b1388

## Findings

### t039_code_f001 - diff 混入与会话页改版无关的 Supervisor 重试 deadline 改动

- 严重度：minor
- 锚点：「不偏航 / 不自由发挥」维度命中；spec 契约区（范围/验收）全无 Supervisor backoff 语义，属范围外行为与异常规模变更
- 位置：`src/backend/cbrowser/adapters/database/models.py:205`、`src/backend/cbrowser/adapters/database/repository.py:686`、`src/backend/cbrowser/supervisor/recovery_rules.py:86`、`src/backend/cbrowser/supervisor/recovery_coordinator.py:373`、`src/backend/migrations/versions/0001_baseline_v2.py:128`
- 问题：本 task 新增 DB 列 `backoff_started_at` / `next_retry_at`、API 响应字段、`remaining_retry_seconds_from_deadline` 及 coordinator 切换，连带改 `test_supervisor_retry_e2e.py` / `test_domain_and_repository.py` / `test_refactor_behavior_equivalence.py` / `test_runtime_coordinator_integration.py`。这些改动与 `/session/:profileId` 重设计、颜色门禁、`sess-*` 选择器改写无因果关系，却改变了 Supervisor 重试窗口语义（由 `updated_at` 推导改为 durable deadline `next_retry_at`），跨 schema、API、协调器与 4 个测试文件。属于「commit 混入不属于当前工作的改动」。
- 建议：拆到独立 task 或明确说明与 t039 的必要性；若纯为门禁稳定性收口，应归入既有 p051 / t045 线，不进本 task 交付面。

### t039_code_f002 - 环境切换器 Popover 吞掉 Escape，与「Esc 留给远端」语义冲突

- 严重度：minor
- 锚点：AC-006「Esc 与会转发给远端的常用组合键不被宿主占用」；blueprint `docs/blueprint/frontend.md` 第 2 节「Esc 与常用组合键留给远端 iframe」不变量
- 位置：`src/frontend/src/features/browser-session/EnvironmentSwitcher.tsx:96`（`onEscapeKeyDown={(event) => event.preventDefault()}`）、`src/frontend/src/shared/ui/Popover.tsx:24`
- 问题：切换器给 Popover 注入 `onEscapeKeyDown` 并 `preventDefault()`，阻止 Radix 在 Escape 时关闭 popover。`EnvironmentSwitcher.test.tsx:237-253` 把「按 Esc 不关闭 popover」固化为预期。可观测结果：用户打开切换器后按 Esc，popover 保持打开、Esc 既未产生宿主关闭动作、也未进入 iframe，按键被宿主消费；同时失去「Esc 关闭下拉」这一通用预期。与 AC-006 要求的「Esc 不被宿主占用」及 blueprint 不变量方向相反。
- 建议：去掉 `preventDefault`，让 Esc 正常关闭 popover 并把焦点交回页面/iframe；若确需保留 popover，应显式把键盘焦点/事件让给远端 iframe，而非吞掉按键。

### t039_code_f003 - effectiveStage 把 runtime 异常态一律压平为 runtime_not_ready，且 data-stage 与面板不一致

- 严重度：minor
- 锚点：AC-001「保持全部会话阶段与恢复语义」；行为缺陷：状态机错位（stopping/error 阶段不可达、暴露错误动作、状态属性撒谎）
- 位置：`src/frontend/src/features/browser-session/SessionPage.tsx:207-211`（bridge）、`SessionPage.tsx:239`、`SessionPage.tsx:246`、`SessionPage.tsx:301`（`data-stage={session.stage}`）
- 问题：`runtimeState && runtimeState !== "running" && runtimeState !== "starting" ? "runtime_not_ready" : session.stage` 把 `stopping` / `error` / `stopped` 全部压成 `runtime_not_ready`。后果：① `stopping` 阶段（blueprint/`SessionStagePanel.tsx:43` 定义为「仅查看状态、不提供重连」）不可达，反而渲染 `runtime_not_ready` 的 `launch` 按钮（`SessionStagePanel.tsx:42`），用户点它会 `setDesiredState("running")` 与正在进行的停止竞争；② `error` 阶段原因被弱化（`session.errorMessage` 在运行时事后转 error 时不会被 `useBrowserSession` 重设）；③ 面板按 `effectiveStage` 渲染，但 `sess-page` / `sess-stage` / iframe 的 `data-stage` 仍取 `session.stage`，停止后可出现「可见面板=未就绪、data-stage=connected」的状态不一致。
- 建议：把 bridge 改为按 `runtimeState` 映射到对应 `SessionStage`（`stopping→stopping`、`error→error`、其余非 running/starting→`runtime_not_ready`），并统一 `data-stage` 与面板所用阶段（或注明二者语义差异）。

### t039_code_f004 - 详情面板「默认收起」时仍恒占 300px，画面区被挤压

- 严重度：minor
- 锚点：AC-005「默认收起」与范围「画面区：iframe 铺满」；行为缺陷：默认状态可见布局
- 位置：`src/frontend/src/features/browser-session/SessionDetailsPanel.tsx:170`（`w-details`，`--container-details: 18.75rem` = 300px）、`src/frontend/src/features/browser-session/SessionPage.tsx:283-293`（包裹 div 恒 `flex`）
- 问题：`open=false` 时 `<aside>` 仍以 `w-details` 渲染并占 300px，`SessionPage.tsx` 的包裹层也不隐藏，仅内部内容区 `open && ...` 不渲染（`SessionDetailsPanel.test.tsx:191-198` 把「收起仍保留容器」固化为预期）。结果默认状态右侧恒有一条 300px 空白侧栏，iframe 画面区只能拿到 `flex-1` 的剩余宽度，与「默认收起」「iframe 铺满」的直观语义有差距。
- 建议：确认产品意图；若为「面板折叠不占空间」，收起时把 aside 收成窄条或 `hidden`，让 iframe 铺满；若确为「常驻 300px 标题栏」，在 spec/blueprint 写明以免 AC 语义歧义。

### t039_code_f005 - 详情面板复制的是 display 后的拼接值，缺失字体告警无可复制控件

- 严重度：minor
- 锚点：AC-005「面板中的值与 API 响应一致……每个值可复制」；行为缺陷：复制内容不等于原始 API 值、部分值不可复制
- 位置：`src/frontend/src/features/browser-session/SessionDetailsPanel.tsx:28-30`（`display`）、`SessionDetailsPanel.tsx:114-121`（`copyValue` 复制 `value` 字符串）、`SessionDetailsPanel.tsx:154`（`configVersion = "显示 / 显示"` 拼接）、`SessionDetailsPanel.tsx:239-250`（缺失字体 Banner 无复制按钮）
- 问题：`ValueRow` 复制的是 `display()` 之后的字符串，而非 API 原始值：`config_version` 复制 `"1 / 1"`、`transport` 空值复制 `"-"`；指纹区「缺失字体告警」（`missing_fonts`）以 Banner 呈现，不带 `SESS_COPY_VALUE` 按钮，不满足「每个值可复制」的字面要求。
- 建议：复制走原始值（或另附原始值），并为缺失字体等告警项补复制控件；或在 spec 明确「可复制」仅指 ValueRow 数据行。

### t039_code_f006 - 全局颜色门禁的 collectSources 排除测试文件与 styles，与「任一前端源码文件/不设豁免」字面不完全一致

- 严重度：minor
- 锚点：AC-007「在任一前端源码文件中加入默认调色板类或颜色字面量时，门禁失败」「不设豁免」；行为缺陷：部分源码文件不受门禁约束
- 位置：`src/frontend/scripts/design_tokens.mjs:109-126`（`collectSources` 跳过 `generated`/`styles` 目录与 `*.test.*`/`*.spec.*`/`test_setup.ts`）、`src/frontend/scripts/design_tokens.mjs:242-248`（`--lint` 仅扫该源集）、`docs/blueprint/testing.md:184`（口径说明）
- 问题：`run_gates.sh:213` 的 `design_lint` 确实调用 `npm run design:lint`，独立跑 `node src/frontend/scripts/design_tokens.mjs --lint` 得「84 files clean」，产品源码干净；但 `rg` 确认 `src/frontend/src/**/*.test.tsx` 与 `src/frontend/src/styles/globals.css` 不在被扫集合内。在这些文件加入 `bg-red-500` 或 `#ff00aa` 门禁不会失败，与 AC-007「任一前端源码文件」「不设豁免」存在字面差距。当前上述被排除文件无实际颜色违规，故未产生可观测漏报。
- 建议：要么把 `.test.*` / 手写 `styles` 纳入扫描并对生成物 `design_tokens.css` 做精确白名单；要么在 spec/blueprint 明确「豁免」仅指生成物，并把「不设豁免」措辞对齐实际源集口径。

### t039_code_f007 - AC-008「应用并重启」缺真实栈 E2E 单列用例

- 严重度：minor
- 锚点：AC-008「真实栈会话 E2E 无头通过：……应用并重启」；测试·文档·规格视角：AC 列举场景缺 E2E 支撑（实现合理但 spec 描述可能过时，处置为补测或改 spec，不计 FAIL）
- 位置：`tests/e2e/test_frontend_display_apply_e2e.py:169`（该文件唯一测试是 docker 探测）、`tests/e2e/test_frontend_display_apply_e2e.py:78,140,153,162`（`create_profile_via_ui`/`wait_video_size`/`remote_geometry`/`assert_remote_geometry` 等 helper 零调用）；`sess-apply-restart` 在 `tests/` 全目录零引用
- 问题：客观门禁证据 `.scratch/t039_evidence_20261107_201858/suites.tsv` 显示 `e2e exit 0`、junit `104 tests / 0 failures / 0 errors`，双标签身份、复制标签页重映射、可见性暂停恢复用例均 pass；但「应用并重启」只有组件测试（`SessionPage.test.tsx:300-308`、`SessionHeader.test.tsx:282`）与 mutation 单测（`useProfilesQuery.apply.test.tsx` 等）支撑，真实栈 E2E 中没有点击 `sess-apply-restart` 并完成 stop→running 的用例。`test_frontend_display_apply_e2e.py` 仅剩 `test_stream_entrypoint_rejects_missing_supervised_screen_config` 与一批未使用 helper（anchor 版本即如此，非 t039 引入的回归）。
- 建议：要么补一个真实栈「改配置→应用并重启→验证新实例/分辨率」E2E，要么把 AC-008 措辞修订为与既有 E2E 覆盖语义一致；本项属测试层，交 test reviewer 并行核对。

## 结论

- 前轮 finding 复核：无（Round 1）
- 本轮新发现：7 条（0 critical / 0 important / 7 minor）
- 未进表的提示：文件过大标准——审查范围内最大实现源码 `SessionPage.tsx` 305 行、`SessionDetailsPanel.tsx` 306 行（阈值 400），最大测试源码 `SessionPage.test.tsx` 499 行（阈值 600），均未命中；圈复杂度——`SessionStagePanel` 为表驱动分发（排除项），未见 ≥10 的函数命中，无 finding；范围外观察——`test_stream_runtime_e2e.py`、`test_supervisor_retry_e2e.py`、`test_runtime_coordinator_integration.py` 的稳定性/断言改写配合 f001 的范围外后端改动；`SessionHeader.test.tsx`（34 处断言）、`session_audio_control.test.tsx`（28 处）、`ClipboardPermissionHint.test.tsx`（10 处）非空壳。7 视角正交体检均已扫过：安全（外部输入均 `encodeURIComponent`、React 自动转义、无硬编码 secret）、正确性、契约·Breaking（OpenAPI 新增 `backoff_*` 字段有 schema 同步）、性能·资源（未见循环内查库/串行化）、架构·可维护性（f001/f003）、健壮性·可观测（try/catch 均有 fallback、无空 catch）、测试·文档·规格（f007）；未命中视角不出 finding。
- 总体判断：实现层对 8 条 AC 均有可查证的代码、组件测试与客观门禁/E2E 证据支撑，无未解决 critical/important；7 条 minor 交 implementer 处置，PASS。
- 系统性 follow-up：`.repo_template/scripts/task.py list` 只读核对，无与「Supervisor retry deadline 拆分」或「应用并重启 E2E 补齐」等价的既有 task（t044/t045 已 done、p051 为容器消失观察项）。建议 follow-up：①「拆分 t039 中 Supervisor backoff deadline 范围外改动」（slug `supervisor_retry_deadline_split`，非阻断）；②「补齐应用并重启真实栈 E2E 或修订 AC-008 措辞」（slug `session_apply_restart_e2e`，非阻断）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`SessionStagePanel.tsx:24-54` 定义全部 12 阶段标题/动作、`useBrowserSession.ts` 状态机完整、`SessionPage.tsx:267-275` connected 不渲染面板；`useBrowserSession.stages.test.tsx` 用真实 hook 覆盖 14 场景、`SessionStagePanel.test.tsx` 遍历全部非 connected 阶段断言原因与动作，旧 `BrowserSessionView.test.tsx` 已删除。
- AC-002：TICK-VALID，re_verified。`SessionEntryPage.tsx:22-59` 仅列 `observed_state=running` 的环境为真实 `<a href>`，`AppLayout.tsx:152-165` 读 `cbrowser.session.target` 回跳、`SessionPage.tsx:138-145` 写入；`SessionEntryPage.test.tsx` 与 `ProfileIsolation.test.tsx:265-301` 佐证。
- AC-003：TICK-VALID，re_verified。`EnvironmentSwitcher.tsx:64-91,140-146` 实现可搜索/分组/真实链接，per-tab 隔离由 `ProfileIsolation.test.tsx:274-287` 与 E2E `test_frontend_session_dual_tab_identity_refresh_copy_no_kick_and_close`（junit pass）佐证。
- AC-004：TICK-VALID，re_verified。`SessionHeader.tsx:104-205` 含 observed/transport/待应用/应用并重启及音频/诊断/详情/专注/停止，`useProfilesQuery.ts:310-396` 的 `useApplyDisplaySettingsMutation` 做 stop→running；`SessionHeader.test.tsx`、`SessionPage.test.tsx:291-308` 佐证。
- AC-005：TICK-VALID，re_verified。`SessionDetailsPanel.tsx` 四区字段取自 runtime/profile/groups/proxies/fontSets，`SessionPage.tsx:34-43,156-171` 用 `cbrowser.session.details_open` 持久化展开态，`ValueRow` 逐值复制；`SessionDetailsPanel.test.tsx` 8 例与 `SessionPage.test.tsx:281-289` 佐证。
- AC-006：TICK-VALID，re_verified。`SessionPage.tsx:218,243,283,295` 专注模式用 CSS hidden 不卸载 iframe（key/src 固定），`FocusModeToolbar.tsx` 顶部热区且无 Esc 监听，`providers.tsx:77` 挂载 `SessionFocusProvider`；`SessionPage.test.tsx:265-279` 断言 iframe DOM 节点不变、`FocusModeToolbar.test.tsx:61-73` 断言 Esc/Ctrl+C 不触发退出。
- AC-007：TICK-VALID，re_verified。`design_tokens.mjs:22-35,85-107` 把颜色断言并入 `runLintSources`，`run_gates.sh:213` 的 `design_lint` 调用 `npm run design:lint`；独立执行 `node src/frontend/scripts/design_tokens.mjs --lint` 得「84 files clean」，`design_tokens.test.mjs` 与 `test_frontend_build_wiring.py:106-127` 佐证加入调色板类即抛错。
- AC-008：TICK-VALID，re_verified。客观证据 `.scratch/t039_evidence_20261107_201858/suites.tsv`（`e2e exit 0`）与 junit（104 tests / 0 failures）、`test_frontend_session_dual_tab_identity_...`、`test_ac004_visibility_stop_start_through_full_app`、`test_ac007_tab_visibility_pause_resume_...` 均 pass；「应用并重启」功能与组件/mutation 测试齐全，真实栈未单列该场景见 f007（spec 描述可能过时，交 test reviewer 核对）。

coverage = re_verified / 8

verdict: PASS

## Round 2 (2026-11-07T21:45:00+08:00)

reviewed_scope: 9f8be56c91945517

### 落点校验

- `git rev-parse --show-toplevel`（workdir=`<repo_root>`，不带 `-C`）= `<repo_root>`，精确匹配；HEAD 恰为 `90293b4`，全部交付为工作区改动，新文件已 `git add`（status `A`），仅 `review_code.md` / `review_test.md` 为 `??`（reviewer 产物，非交付物，不进 diff）。审查依据为 `git -C '<repo_root>' diff 90293b4ae3fc74d39de7449f2a419b471628f431`（当前完整改动，76 文件），未采信 Round 1 旧结论与 `progress.md` 处置表 claim。

### 前轮 finding 复核

- **f001（Supervisor 范围外 retry deadline 改动）—— 同意撤回（附观察）**：diff 核实后端 `models.py:205` / `repository.py:686,763,871` / `domain/models.py` / `runtime_views.py` / `recovery_rules.py:86` / `recovery_coordinator.py:373` / `0001_baseline_v2.py:128` 的 `backoff_started_at` / `next_retry_at` 改动 Round 1 即在、本轮未变。代码逻辑自洽：error 分支以同一 `now` 写 `next_retry_at = now + AUTO_RETRY_DELAYS[failure_count-1]`，running / bind / set_desired 三处清空，`remaining_retry_seconds_from_deadline` 有 `delay_sec<=0`、解析失败 fallback、tzinfo 归一，`ProfileRuntimeResponse` 新增 optional 字段且 OpenAPI 同步；未见可观测缺陷。撤回理由「门禁阻塞根因」解释动机（progress「纠正 1」记录 retry E2E 边界抖动），但未否认「与 `/session` 改版无因果关系」这一范围外事实，「用户监督明确要求」属 implementer claim、diff 无法独立验证。按硬阈值该范围外观察为 minor、非 AC 违反、后端无缺陷，撤回不掩盖真实缺陷，接受；范围外事实建议 handoff 明示，不进 finding 表。
- **f002（切换器 Popover 吞 Esc）—— 仍存在（minor，撤回理由不完整）**：`EnvironmentSwitcher.tsx:96` 的 `onEscapeKeyDown={(event) => event.preventDefault()}` 与 `Popover.tsx:24` 转发**代码完全未改**，popover 打开时 Esc 既不关闭弹层也不进入 iframe。撤回理由「AC-006 只约束页面级全局 keydown」在 AC-006 适用语境（`frontend.md:24` 专注模式、Esc 留给远端 iframe）内站得住：会话页组件（SessionPage / SessionHeader / FocusModeToolbar / EnvironmentSwitcher）均无宿主全局 `addEventListener("keydown")`，popover 默认关闭时不占用 Esc。但理由**未回应** `docs/blueprint/frontend.md:69`「Popover 的 Esc 关闭由 Radix 原语保证」——`preventDefault` 打破既有预期，按 Esc 不关闭下拉仍是真实 minor 行为缺陷。该缺陷不在 AC-006 场景（专注/iframe 焦点）内，无崩溃/错答案/越权，按硬阈值不阻断、不重新编号，记录遗留观察；撤回部分可接受，理由不完整。
- **f003（effectiveStage 压平 + data-stage 不一致）—— 仍存在（minor，撤回理由引用失实）**：`SessionPage.tsx:206-215` bridge 与 `:243 / :250 / :305` 的 `data-stage={session.stage}` **完全未改**，面板按 `effectiveStage`（:271-279）渲染；`stopping` / `error` 仍被压成 `runtime_not_ready`，停止后可出现「面板=未就绪 / data-stage=connected」不一致（E2E `test_frontend_media_e2e.py:885-888` 读的正是 `sess-page[data-stage]`）。撤回理由称「blueprint 已注明语义差异（frontend.md:47）」，但 `frontend.md:47` 全文只讲阶段清单 / `SessionStagePanel` / `connecting_ice` 字面量分支，**无任何 data-stage 与 effectiveStage 语义差异说明**——引用失实，撤回理由站不住。该不一致是 DOM 属性语义/文档缺口，用户可见面板正确、无严重后果，属 minor，按硬阈值不阻断、不重新编号，记录遗留；建议补 blueprint 说明或统一 `data-stage` 口径。
- **f004（默认收起恒占 300px）—— 同意撤回**：`SessionDetailsPanel.tsx:167-170` `w-details` 恒渲染、`SessionPage.tsx:287-297` 包装层恒 `flex` 未变，`SessionDetailsPanel.test.tsx:191-198` 固化「收起仍保留容器、仅内容不渲染」。AC-005「默认收起」在实现中定义为内容不渲染，常驻 300px 标题栏是布局取舍，`frontend.md:48` 亦写「300px、默认收起」未要求零占位。minor 字面张力、无行为缺陷，撤回可接受；建议 spec 明确「收起」语义。
- **f005（复制 display 值 / 缺失字体无复制）—— 仍存在（部分，minor）**：`SessionDetailsPanel.tsx:154` `configVersion = "1 / 1"` 拼接、`:114-121` 复制 `display()` 后字符串未变，`:239-250` 缺失字体 `missingFonts` 仅以 Banner 呈现、`SESS_COPY_VALUE` 按钮 0 个（本轮 `SessionDetailsPanel.test.tsx:207-222` 遍历复制反而固化「每值复制显示值」）。撤回理由「复制 display 值是产品设计、四区数据行与 API 一致」对 ValueRow 数据行成立，但 AC-005 明确点名「缺失字体」，该值只出现在无复制控件的 Banner 中，理由「Banner 非 ValueRow」是描述事实而非否认缺口，未正面回应 AC-005。minor 语义缺口仍在，按硬阈值不阻断、不重新编号，记录遗留；建议补复制控件或改 spec 澄清「可复制」范围。
- **f006（颜色门禁排除测试/styles）—— 同意撤回（属 spec 措辞应对齐）**：`design_tokens.mjs:109-126` `collectSources` 排除 `generated` / `styles` / `*.test.*` / `test_setup.ts` 未变，`:242-248` `--lint` 调 `runLintSources`（含颜色断言）经既有 `design_lint` suite 接入生效。撤回理由引用 `docs/blueprint/conventions.md:52`，核实该文件确定义「业务代码（shared/ui、app、features/\* 页面、手写 globals.css）」并明确「生成产物 design_tokens.css 不列入业务源码扫描」，且 `testing.md:187` 记录「源集沿用 t036 口径」排除测试源码、业务源码内无豁免；当前被排除文件无实际颜色违规（Round 1 已核实、本轮未变）。AC-007 字面「任一前端源码文件 / 不设豁免」比实现口径宽，属「实现合理但与 spec 描述不符」，按硬阈值处置为改 spec、不计 FAIL。撤回可接受，建议对齐 spec 措辞。
- **f007（AC-008 应用并重启缺 E2E 单列）—— 同意撤回**：`tests/e2e/test_frontend_display_apply_e2e.py` 本轮未改（仍 1 例 docker 探测 + 零调用 helper），`sess-apply-restart` 真实栈点击仍无。该 finding 属测试层职责，撤回理由引用 `review_test.md:56`，核实 test 轴 Round 1 结论段确写明「AC-008 应用并重启子场景无独立真实栈 E2E 点击……为基线状态，非本 task 假绿」并列出组件/mutation 承接；code 轴不重复评审测试层。实现层「应用并重启」经 `SessionPage.tsx:237` → `useApplyDisplaySettingsMutation` 真实 stop→running 链路存在（`SessionPage.test.tsx:300-308` 断言触发）。minor、基线状态、无假绿，撤回可接受。

### 跨轴 blocker 核对

test 轴 Round 1 唯一 important `t039_test_f001`（连接状态精确值断言被放宽为子串包含）经本轮修复：产品 `DiagnosticsOverlay`（`SessionPage.tsx:91-128`）给 7 个诊断值加 `sess-diag-*` testid，`tests/e2e/test_frontend_media_e2e.py:837-854` 的 `read_conn_state` / `read_audio_status` 恢复读具体值元素、`:890 / :933` 恢复 `== "connected"` 精确相等、`:883` 音频 `== "音频正常"` 精确相等；逐行核实产品 `sessId("diag", "conn-state")` = `sess-diag-conn-state` 与 E2E 选择器契约一致。diff 核实该 important 已消除，code 轴无未解决 blocker（未读 test 轴 Round 2 报告，不替其下结论）。

### 本轮新发现

0 条（0 critical / 0 important / 0 minor）。重点审查的修复引入代码逐项结论（均未构成 finding，不凑数）：

- `SessionPage.tsx:91-128` DiagnosticsOverlay 7 行 rows + `sess-diag-*` testid：表驱动、`value ?? "-"` 回退、`audioLabels[status] ?? status`、testid 用既有 `sessId()` 生成且与 E2E 选择器一致，无恒真/空壳，无缺陷。
- `SessionPage.test.tsx:317-347` 5 态 en/zh 音频文案用例：触达真实 `sess-diag-audio-status` 渲染，非 mock 被测逻辑（测试层，code 轴不评质量）。
- `session_audio_control.test.tsx:168-263` 删自反断言改硬编码 `expected` 字典，核实与 `i18n.tsx:145-149` en 值逐字一致，无 `expect(x).toBe(x)` 恒真残留（测试层）。
- `SessionDetailsPanel.test.tsx:207-230` 遍历 `SESS_COPY_VALUE` 逐值断言 + `last_coordinator_error` 非空展示，触达产品 `copyValue`（测试层）。
- 后端产品退避事实字段：逻辑自洽、deadline 续算有 fallback、三处清空、OpenAPI 同步，无破坏性契约或真实 bug（详见 f001）。
- `useBrowserSession.ts:275-284` LIFECYCLE_STALE：诊断阶段仅忽略 WS_CLOSE / PC_STATE，stale 经 `:359-364` 走 `reconnect()`（非 reconnecting / connecting_signaling 时），与注释和修复目标一致，未引入状态机错位。
- view-status 路由 `SessionPage.tsx:276` `navigate(\`/profiles/${id}/config\`)`：恢复 t038 语义、与 E2E 一致；`id`未`encodeURIComponent\`（同文件 :251 用了），但为 SPA 内路由路径、profile id 受控，无可观测注入/越权，不进 finding 表（见提示）。
- `launch_profile_via_ui` 就绪门控、E2E 精确断言恢复属测试层，交 test 轴，本轴不重复。

### 未进表的提示

- 文件过大：实现源码最大 `SessionPage.tsx` 309 行、`SessionDetailsPanel.tsx` 306 行（阈值 400），测试源码最大 `SessionPage.test.tsx` 531 行（阈值 600）；本轮净增 `SessionPage.tsx` +4、`SessionPage.test.tsx` +32，均未超阈值，不出 finding。
- 圈复杂度：`DiagnosticsOverlay` rows 为表驱动、`audioLabels[status] ?? status` 单短路，无函数 ≥10，排除项不进表。
- 风格观察（非缺陷）：`SessionPage.tsx:276` view-status 的 `id` 未编码；7 个诊断值 testid 用 `sessId` 动态生成、未纳入 `session_keys.ts` 常量表（属既有模式）。
- 7 视角正交体检均已扫过确认：安全（外部输入 `encodeURIComponent`、React 自动转义、无硬编码 secret、SPA 路由无注入）、正确性（状态机/bridge/复制值）、契约·Breaking（OpenAPI 新增 optional `backoff_*` 有 schema 同步、SSE 精简投影不变）、性能·资源（`useQueries` 逐 profile runtime 非循环内查库）、架构·可维护性（f001 范围外、f003 bridge）、健壮性·可观测（`copyValue` 有 rejection handler、无空 catch）、测试·文档·规格（f005/f006/f007）；未命中视角不出 finding。
- 范围外观察：后端 Supervisor retry deadline、migration、4 个后端测试文件与 t039 UI 无因果关系（f001 已复核）；`docs/pending/todo/p052_selkies_evict_close_code_1006.md` 为跨 task 观察项（p051 / p052），非本 task 阻断。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`SessionStagePanel.tsx:24-54` 覆盖 13 个 StageKey 的原因标题与动作、`useBrowserSession.ts:38-46` 状态机与 `:275-284 / :359-364` 恢复处理完整，`SessionPage.tsx:271-279` 非 connected 渲染面板，`useBrowserSession.stages.test.tsx` 走真实 hook；旧测试删除去向见 progress.md D16。
- AC-002：TICK-VALID，re_verified。`SessionEntryPage.tsx:15-27` 用 useQueries 仅列 observed_state=running、`:46-58` 真实 `<a href>` 链接，`AppLayout.tsx:159-160` 读 `cbrowser.session.target` 回跳、`SessionPage.tsx:142-149` 写入，`router.tsx:30-35` 两路由就位。
- AC-003：TICK-VALID，re_verified。`EnvironmentSwitcher.tsx:64-91` 分组/大小写不敏感搜索、`:135-148` 真实 `/session/{id}` 链接（encodeURIComponent），per-tab 独立由 `sessionStorage` target 支撑而非跨页共享态。
- AC-004：TICK-VALID，re_verified。`SessionHeader.tsx:110-208` 含 observed/transport/待应用 Banner+应用并重启/音频/诊断/详情/专注/停止，`SessionPage.tsx:91-128` DiagnosticsOverlay 7 值带 `sess-diag-*` testid、`:237` 接 `useApplyDisplaySettingsMutation`；`SessionPage.test.tsx:300-308` 与 E2E `read_conn_state` 精确断言佐证（跨轴 f001 已消除）。
- AC-005：TICK-VALID，re_verified。`SessionDetailsPanel.tsx:190-301` 四区字段取自 runtime/profile/groups/proxies/fontSets，`SessionPage.tsx:34-43,160-175` 用 `cbrowser.session.details_open` 持久化，`ValueRow:62-72` 逐值复制；`SessionDetailsPanel.test.tsx:207-222` 遍历复制、`SessionPage.test.tsx:281-289` 重挂载保持。
- AC-006：TICK-VALID，re_verified。`SessionPage.tsx:222 / 287 / 299` 专注模式仅 hidden 包装层、iframe `:246-255` 固定 key 不卸载，`FocusModeToolbar.tsx:25-49` 顶部热区且无 keydown 监听，`providers.tsx:77-80` 提升 Provider；`SessionPage.test.tsx:265-279` 断言同一 iframe DOM 节点不变。
- AC-007：TICK-VALID，re_verified。`design_tokens.mjs:85-107,242-248` 把 `assertNoColorViolations` 并入 `--lint` / `runLintSources`，既有 `design_lint` suite 接入 run_gates.sh 生效，`design_tokens.test.mjs` 2 例集成门禁、`test_frontend_build_wiring.py:106-127` 负向断言（加入调色板类即失败），业务源码 84 files clean。
- AC-008：TICK-VALID，re_verified。逐行查证 `test_frontend_app_e2e.py` 多页面/复制身份重映射、`test_frontend_media_e2e.py` 可见性暂停恢复与 `:890 / :933` 连接状态精确断言、`launch_profile_via_ui` 就绪门控与 `_k=` reload；客观门禁证据 `.scratch/t039_evidence_20261107_201858/suites.tsv`（E2E 0 failed / junit 104 tests 0 failures）；未独立重跑 Docker 真实栈，据代码与门禁日志查证。

coverage = re_verified / 8

### 总体判断

以 `git -C ... diff 90293b4...` 与代码/测试为准，实现层对 8 条 AC 均有可查证支撑、无 TICK-VOID；前轮 7 条 minor 中 4 条（f001/f004/f006/f007）同意撤回、3 条（f002/f003/f005）因撤回理由不充分或引用失实判定仍存在，均为 minor 非阻断；本轮新发现 0 条，无未解决 critical / important；test 轴 Round 1 唯一 important 已 diff 核实消除。按判定式 PASS。系统性 follow-up：无新增（前轮 `supervisor_retry_deadline_split` / `session_apply_restart_e2e` 仍为非阻断建议，`.repo_template/scripts/task.py list` 只读核对无等价既存 task）。

verdict: PASS

## Round 3 (2026-11-07T22:20:00+08:00)

reviewed_scope: e209862ac6e2d3f1

### 落点校验

- 不带 `-C` 的 `git rev-parse --show-toplevel`（workdir=`<repo_root>`）= `<repo_root>`，精确匹配；HEAD 恰为 `90293b4`，全部交付为工作区改动，新文件已 `git add`（status `A`），`review_code.md` / `review_test.md` 为 reviewer 产物不进指纹。审查依据 `git -C '<repo_root>' diff 90293b4ae3fc74d39de7449f2a419b471628f431`（当前完整改动，77 文件 / 5482+2114），含三项修复；未采信 `progress.md` 处置表 claim。
- 独立复验：`npx vitest run` 定向 4 文件（`ui.test.tsx` / `EnvironmentSwitcher.test.tsx` / `SessionPage.test.tsx` / `SessionDetailsPanel.test.tsx`）40 passed；`git diff <anchor> -- Popover.tsx` 为空、`-- docs/pending/` 仅 p051/p052；`effectiveStage` / `onEscapeKeyDown` 全仓 grep 在 `src/` 0 命中；E2E 精确断言 grep 复核。

### 前轮 finding 复核

- **f002（Esc 吞键）—— 已消除（根因修复成立）。** `EnvironmentSwitcher.tsx:93-106` 的 `<Popover>` 只传 `ariaLabel` / `trigger` / children，全文无 `onEscapeKeyDown`、无 `preventDefault`、无宿主 `addEventListener("keydown")`。`shared/ui/Popover.tsx` 当前 34 行参数仅 `trigger/children/ariaLabel/contentClassName`；`git show HEAD:.../Popover.tsx` 与当前逐字一致、`git diff <anchor> -- Popover.tsx` 为空——t039 曾引入的 `onEscapeKeyDown` 死转发参数已整体删除、回到基线，不在当前 diff。`Popover.Content`（:20-30）无自定义 escape handler，Radix 按默认在 Escape 时关闭弹层。旧用例「按 Esc 不关闭 popover」已删除，改写为 `EnvironmentSwitcher.test.tsx:237-257`「closes the popover on Escape via the Radix dismissable layer」，断言 `data-state="closed"` 与 `SESS_SWITCHER_SEARCH` 消失，真实非恒真（本次定向 40 passed）。
    - 与 AC-006 / `docs/blueprint/frontend.md:69` 冲突复核：**不冲突**。AC-006 约束专注模式下「不重建 iframe、不中断远端输入、Esc 与常用组合键不被宿主占用」，语境为 iframe 焦点（`frontend.md:24`）；`frontend.md:69`「Dialog / DropdownMenu / Popover / Tooltip 基于 Radix 原语（……Esc 关闭与 ARIA 角色由原语保证）」是 HEAD 既有不变量（t039 diff 未改该行）。Popover 打开时 Radix 焦点陷阱把焦点限制在弹层内，Esc 由 dismissable layer 用于关闭弹层、不截获转发给远端 iframe 的按键；`ui.test.tsx:80-93`（HEAD 基线测试）本就断言 Popover「closes on Esc」，修复后切换器行为与 shared/ui 契约一致。修复前 `preventDefault()` 让 Esc 既不关闭弹层也不进入 iframe（按键被吞）才是偏离该不变量；修复后恢复一致。
- **f003（阶段桥接双真相）—— 已消除（根因修复成立）。** `SessionPage.tsx:184-193` 把单一 `stage: SessionStage` 提升到组件顶层（`useBrowserSession` 之后、`pageBody` 之前）：`observed_state==="stopping"→"stopping"`、`==="error"→"error"`、`stopped` 及其余非 running/starting→`"runtime_not_ready"`、`running`/`starting`/`runtime=null`→`session.stage`（WebRTC 层透传）。`types.ts:9-21` 的 `SessionStage` 无 `stopped` 成员，`SessionStagePanel.tsx:27,43` 中 `stopping` 仅 `view-status`、`error` 含 reconnect/view-status/launch、`runtime_not_ready` 含 launch，映射与阶段表一致，不再出现「stopping 暴露 launch 与停止竞争」。统一取值核实：`sess-page`(:311) / `sess-stage`(:249) / iframe(:256) 的 `data-stage={stage}`、`SessionStagePanel`(:279) `stage={stage}`、`diagnosticsView.stage`(:196) = `stage`、connected 判定(:262,:277) 用 `stage`，单一真相。全仓 `effectiveStage` grep 在 `src/` 0 命中（仅 `progress.md` 历史叙事与本报告历史段落残留），**无双真相残留**。TDD 新用例 `SessionPage.test.tsx:352-414`（stopping 无 launch 且三处 data-stage 一致 / error 有 reconnect / stopped 有 launch）以 `vi.mock("./useBrowserSession")` 令 `session.stage="connected"` 验证 runtime 桥接覆盖，具体值断言、非恒真，本次定向 40 passed 通过。
- **f005（缺失字体无复制）—— 已消除（根因修复成立）。** `SessionDetailsPanel.tsx:239-265` 在 `missingFonts.length > 0` 的 Banner 内补 `data-testid={SESS_COPY_VALUE}` 按钮，`onClick={() => copyValue("missing_fonts", missingFonts.join(", "))}`（:254-256），复制 `missing_fonts` 原始数组拼接值、与 Banner 显示(:247) 同值，满足 AC-005「每个值可复制」。按钮状态 `copiedKey === "missing_fonts" ? t("sessCopied") : t("sessCopy")`（:258-260），复用面板单一 `copiedKey` state(:111)，复制键 `"missing_fonts"` 与所有 `ValueRow` 的 `copyKey` 不冲突，非列表渲染无需 React key。`SessionDetailsPanel.test.tsx:231-239` 新用例经 `getByRole("alert")`（`Banner.tsx:20` 无条件 `role="alert"`）→ `within(alert).getByTestId(SESS_COPY_VALUE)` → 点击 → `expect(writeText).toHaveBeenCalledWith("Arial, SimSun")`，真实非恒真，本次定向 40 passed 通过。
- **f001（Supervisor 范围外 retry deadline）撤回 —— 仍有效。** 后端 `models.py` / `repository.py` / `recovery_rules.py` / `recovery_coordinator.py` / migration 与 4 个后端测试在三项修复中未触及（修复面为 3 个前端组件 + 测试 + p053），Round 2 已 diff 核实逻辑自洽、无 AC 违反、后端无缺陷。
- **f004（收起恒占 300px）撤回 —— 仍有效。** `SessionDetailsPanel.tsx:167-170` `w-details` 恒渲染、`:188` `open && (...)` 内容区结构未变（f005 仅在 `extra` 加 Banner 复制按钮），`SessionDetailsPanel.test.tsx:191-198` 仍固化「收起保留容器、仅内容不渲染」。
- **f006（颜色门禁排除测试/styles）撤回 —— 仍有效。** `design_tokens.mjs` / `conventions.md:52` / `testing.md` 口径本轮未触及，属「实现合理但与 spec 描述不符」应对齐措辞，不计 FAIL。
- **f007（AC-008 应用并重启缺 E2E 单列）撤回 —— 仍有效。** `test_frontend_display_apply_e2e.py` 本轮未触及，属测试层、基线状态、非假绿。
- **test 轴 4 条 —— 处置状态均保持有效。** `t039_test_f001`（important，已消除）：`test_frontend_media_e2e.py:838,852,883,890,906,933` 的 `sess-diag-conn-state` 选择器、`read_conn_state`、`== "connected"` / `== "音频正常"` 精确相等 grep 复核仍在，`SessionPage.tsx:96-102` 7 值 testid 仍在。`t039_test_f002`（已修）：`SessionPage.test.tsx:320-350` 5 态 en/zh 诊断浮层渲染用例仍在。`t039_test_f003`（已修）：`SessionDetailsPanel.test.tsx:207-229` 遍历复制 + `last_coordinator_error` 非空展示仍在。`t039_test_f004`（撤回）：`host_entry.tsx` test-only 壳三项修复未触及。
    - 旁证偏差（记录、不翻案）：test 轴 Round 1/2 报告（`review_test.md:65/68/108/111`）把「EnvironmentSwitcher 按 Esc 不关闭 popover」列为 AC-003/AC-006 支撑证据，该描述在当前 diff 下已过时（产品改为 Radix 默认关闭、用例已改写）。属他轴报告历史证据描述滞后、测试层职责，非产品缺陷、非本轴 finding，不影响上述 4 条处置有效性。

### p053 复核

- `glob **/p053*` 0 命中；`git diff <anchor> -- docs/pending/` 仅 p051(M) / p052(A new)，无 p053 → `docs/pending/todo/p053_*` **已删除**，且不在交付 diff 中。
- `progress.md:251-265` 处置表已把 f002/f003/f005 改「已修」、fix_ref 指向代码/测试，不再挂 p053；`:269`（Round 2 段）与 `:286`（结果摘要）均记「p053 已撤销」。**活跃 follow-up 引用已清理**。
- 残留（范围外、不进 finding 表）：`progress.md` 仍有 4 处 p053 文字（:160/:269/:279/:286），其中收尾报告 `:279`「遗留 3 → p053」与 `:286`「p053 已撤销」并存、自相矛盾（旧段未同步）；`:40/:46/:50` 还保留与当前实现相反的「Radix Popover 需 `onEscapeKeyDown` 阻止占 Esc」实施前旧决策文字。均为流程文件历史叙事、非代码缺陷、不锚定 AC、无 reviewer 看不到的未跟踪交付文件；按 read-only 不改，仅记录，建议 handoff 明示。

### 本轮新发现

0 条（0 critical / 0 important / 0 minor），不启用 `t039_code_f008`。重点审查三项修复引入的新代码逐项结论（均未构成 finding，不凑数）：

- 单一 `stage` 映射边界：`running`/`starting` 透传 `session.stage`、未知或非 running/starting 的 `observed_state` 安全落 `runtime_not_ready`；`runtime=null` 时回退 `session.stage`，但 `pageBody` 在 `isLoading`/`isError`/`!profile` 分支先拦、不渲染面板（`SessionPage.tsx:203-224`），无越界；12 个 `SessionStage` 值在 `STAGE_TITLE_KEYS`/`STAGE_ACTIONS` 全覆盖。边界自洽。
- `Popover` 参数删除对 `ui.test.tsx`：`ui.test.tsx` 不在 t039 diff（与 HEAD 一致），其 Popover 用例(:80-93) 只传 `ariaLabel`/`trigger`/children、本就断言 Esc 关闭；本次定向重跑 4 文件 40 passed，**不受影响**。
- Banner 复制按钮 key/状态：`copyKey="missing_fonts"` 唯一不冲突、`copiedKey` 单一 state 复用正确、非列表无需 React key；`SESS_COPY_VALUE` 复用既有 testid，默认 fixture `missing_fonts: []` 不渲染 Banner 按钮，不干扰 `SessionDetailsPanel.test.tsx:207-222` 的 `getAllByTestId` 遍历。
- TDD 新用例真实性：`EnvironmentSwitcher.test.tsx:237-257`、`SessionPage.test.tsx:352-414`（3 例）、`SessionDetailsPanel.test.tsx:231-239` 均为具体值/属性断言、触达产品渲染与 `copyValue`，无恒真 / 弱化 / 删 expect / mock 被测逻辑，本次定向 `vitest run` 40 passed 独立复验。

### 未进表的提示

- `SessionDetailsPanel.test.tsx:231-239`（f005 新用例）触发 React `act(...)` 警告（`copyValue` 的 `clipboard.writeText().then(() => setCopiedKey(...))` 异步 setState 未 await）；但 `expect(writeText).toHaveBeenCalledWith("Arial, SimSun")` 为同步真实断言、非假绿、用例 passed，属测试层异步处理风格、非产品缺陷，code 轴不评测试质量，不进表。
- blueprint `frontend.md:37` 阶段清单（HEAD 既有）未列 `stopping`/`error`，而 `types.ts:9-21` / `SessionStagePanel.tsx` 已定义且 f003 修复会产出这两态；属既有文档精度滞后、非三项修复引入、不锚定 AC、无行为缺陷，建议 finalization 对齐，不进表。
- 文件过大：实现源码最大 `SessionPage.tsx` 315 行、`SessionDetailsPanel.tsx` 321 行（阈值 400），测试源码最大 `SessionPage.test.tsx` 598 行（阈值 600）；三项修复净增均未越阈值。圈复杂度：`stage` 三元映射为表驱动等价分支、无函数 ≥10。范围外观察：后端 Supervisor retry deadline / migration、p051 / p052 为跨 task 项；progress.md 的 p053 与旧决策文字残影见 p053 复核。
- 7 视角正交体检均已扫过：安全（外部输入 `encodeURIComponent`、React 自动转义、`missing_fonts.join` 仅进剪贴板不执行、无硬编码 secret）、正确性（单一 stage 映射与统一取值、复制值一致性）、契约·Breaking（Popover 公开签名回到 HEAD 基线、无配置键/schema 变更）、性能·资源（无循环内查库 / 新 IO / 大库整体 import）、架构·可维护性（单一真相消除 `effectiveStage` 双真相）、健壮性·可观测（`copyValue` 有 rejection handler、无空 catch）、测试·文档·规格（TDD 新用例非恒真、blueprint 精度滞后提示）；未命中视角不出 finding。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`SessionPage.tsx:184-193` 单一顶层 `stage` 正确映射 stopping/error/stopped，`SessionStagePanel.tsx:24-54` 全部阶段有原因标题与动作，`SessionPage.test.tsx:352-414` 三态映射用例本次定向 40 passed 真实通过，旧测试删除去向见 progress D16。
- AC-002：TICK-VALID，re_verified。`SessionEntryPage.tsx` 入口仅列 observed_state=running 的真实链接、`AppLayout.tsx:152-165` 与 `SessionPage.tsx:142-149` 以 `cbrowser.session.target` 回跳；三项修复未触及入口/路由，Round 2 代码级证据仍成立。
- AC-003：TICK-VALID，re_verified。`EnvironmentSwitcher.tsx:64-91,135-148` 分组/大小写不敏感搜索/真实 `/session/{id}` 链接（encodeURIComponent），Esc 现由 Radix 默认关闭（`ui.test.tsx:80-93` 既有契约）；per-tab 隔离由 sessionStorage target 与 E2E 双标签用例承接。
- AC-004：TICK-VALID，re_verified。`SessionHeader.tsx:110-208` 页头全要素、`SessionPage.tsx:73-132` 诊断浮层 7 值带 `sess-diag-*` testid 且 `test_frontend_media_e2e.py:890/933` 精确相等断言仍在，`:243` 应用并重启接 `useApplyDisplaySettingsMutation`。
- AC-005：TICK-VALID，re_verified。`SessionDetailsPanel.tsx:190-316` 四区字段与 API 一致、`:239-265` 缺失字体 Banner 补 `SESS_COPY_VALUE` 复制 `missing_fonts.join(", ")`，`SessionDetailsPanel.test.tsx:231-239` 断言 `writeText("Arial, SimSun")`（本次定向 40 passed），`SessionPage.tsx:160-175` 持久化展开态。
- AC-006：TICK-VALID，re_verified。`SessionPage.tsx:246-255` iframe 固定 key、仅 hidden 包装层不卸载，`FocusModeToolbar.tsx` 顶部热区无 Esc 监听；`EnvironmentSwitcher.tsx:93-106` 已删 `preventDefault`、Radix 原语按默认关闭（`frontend.md:69` 既有不变量），与 AC-006 不冲突。
- AC-007：TICK-VALID，re_verified。`design_tokens.mjs:85-107,242-248` 颜色断言并入 `--lint`/`runLintSources` 经 `run_gates.sh` 的 `design_lint` 生效，`design_tokens.test.mjs` 与 `test_frontend_build_wiring.py:106-127` 负向断言；三项修复未触及门禁脚本。
- AC-008：TICK-VALID，re_verified。真实栈多页面 / 复制标签身份重映射 / 可见性暂停恢复 / 应用并重启由 `test_frontend_app_e2e.py`、`test_frontend_media_e2e.py` 与组件/mutation 承接，客观门禁证据 `.scratch/t039_evidence_20261107_201858`（E2E 0 failed / junit 104 tests 0 failures）；本环境未独立重跑 Docker 真实栈，据代码与门禁日志查证。

coverage = re_verified / 8

### 总体判断

以 `git -C ... diff 90293b4...` 与代码/测试为准：f002/f003/f005 三项自身交付缺陷均已根因修复（Esc 交回 Radix 默认关闭、单一顶层 `stage` 消除双真相并正确映射、缺失字体 Banner 补复制控件），p053 文件已删除且活跃处置引用已清理；前轮 f001/f004/f006/f007 撤回与 test 轴 4 条处置均保持有效；本轮 0 条新 finding、无未解决 critical / important，8 条 AC 复验全部 TICK-VALID。按判定式 PASS。系统性 follow-up：无新增（p053 文字残影与 blueprint 阶段清单精度属收尾文档清理，非阻断）。

verdict: PASS
