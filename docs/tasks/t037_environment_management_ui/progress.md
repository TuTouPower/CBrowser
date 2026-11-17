---
tid: "t037"
slug: "environment_management_ui"
title: "环境管理界面：列表、新建、详情与分组"
status: "done"
branch: "t037_environment_management_ui"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "05dda065aa237f9e32c3507f6f6a65f47a185205"
depends_on: "t036,t044"
conflicts_with: ""
note: "来源 plan_20261105_ui_redesign WP09+WP11"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-06：`run-begin t037 --base t044_e2e_parallel_execution`（diff_anchor `05dda065aa237f9e32c3507f6f6a65f47a185205`，owner_id `f92f98dd7e464ac98d3231ff465ea3cf`），`preflight t037` = PASS。worktree `../CBrowser_t037` 已软链 `.env` 与 `data/fonts`（t044 导入的持久字体集可复用）。用户裁决「继续跑 t037」，整链完成需多次会话，宿主压缩上下文后按本文件继续。
- 代码地图（explore 子代理结论）：领域层（`useProfilesQuery.ts` 448 行、`scopeMutationToProfile`、SSE `useProfileEventsSync`、`useApplyDisplaySettingsMutation` 阶段跟踪、`useActionKeyMutation` 幂等键）、t036 设计系统组件族（`shared/ui/`，含 `StatusBadge` 4 tone、`GroupHue`/`GroupChip` 8 色）齐备；缺口是列表页/卡片/工具栏/批量条/新建弹窗/共用表单/四标签详情/分组弹窗全部页面组件，`ApiClient` 缺 `groups`/`proxies`/`fontSets` 三个命名空间。旧组件 `ProfileNewPage.tsx`/`ProfileDetailPage.tsx`/`ProfileFilesPage.tsx`/`ProfileAutomationPage.tsx` 含硬编码颜色，按 D16 删除重建。数据 join：`ProfileResponse` 只有 `group_id`/`proxy_id`，分组名/代理名/地区须查 `/groups`、`/proxies` 后 join；五态与 last activity 来自 `runtime`。
- 实施计划（分块，文件边界不重叠；`[步骤] → 验证：[检查方式]`）：
    1. 基础设施：i18n `en`/`zh` 同步补键、`client.ts` 加 groups/proxies/fontSets 命名空间、`types.ts` 加类型别名并扩展 `DEFAULT_PROFILE_CREATE_VALUES`、`useProfilesQuery.ts` 追加 groups/proxies/fontSets hooks → 验证：`npm run test:types` + 既有 Vitest 全绿。
    2. 列表页（AC-001~005）：`EnvironmentListPage`/`EnvironmentTable`/`EnvironmentCardGrid`/`EnvironmentCard`/`EnvironmentListToolbar`/`useEnvironmentFilters.ts`/`useEnvironmentLayout.ts`/`EnvironmentEmptyState`/`BatchActionBar`/`useBatchActions.ts` → 验证：新增 Vitest（ApiClient stub、真实 hooks、完整线形状夹具）。
    3. 表单/弹窗/详情（AC-006~008）：`ProfileForm`（新建与 config 共用）、`ProfileCreateDialog`、新 `ProfileDetailPage`、`ConfigTab`、`SharedProfileBanners`、`MaintenanceTab` → 验证：Vitest。
    4. 分组弹窗（AC-010）：`GroupManagerDialog`/`GroupColorPicker`/`useGroupReorder.ts` → 验证：Vitest。
    5. files/automation 标签（AC-009）：`features/artifacts/ProfileFilesTab.tsx`、`features/automation/ProfileAutomationTab.tsx` → 验证：Vitest。
    6. 路由整合 `app/router.tsx` + 删除旧 4 组件及旧测试改写 + `router.test.tsx` 断言更新 + AC-012 颜色类扫描（命令与结果写本文件）→ 验证：`npm test` / `npm run design:lint` / `npm run design:check` / `npm run build`。
    7. E2E 无头「新建 → 启动 → 打开会话」：`tests/e2e/test_frontend_app_e2e.py` 的 `create_profile_via_ui` 改走新建弹窗 UI → 验证：`CBROWSER_RUN_E2E=1 scripts/run_gates.sh`（沿用 t044 重建的 6 镜像与持久字体集）。
    8. finalization：`docs/specs/profile_management.md` 累积、`docs/blueprint/frontend.md`、specs_index 加 t037、收尾报告 → 验证：`finish` 预检。
    9. full review 两路 → `finish` → `run-close`。
- i18n 键命名（各块共用，避免冲突；中文界面「环境」/英文「Profile」）：列表/工具栏 `envTitle envSearch envFilterAll envFilterRunning envFilterStopped envFilterError envFilterUngrouped envFilterAllGroups envFilterProxy envManageGroups envSortManual envSortName envSortRecent envSortCreated envLayoutList envLayoutCard envNew envClearFilters envEmptyTitle envEmptyAction envNoResults envSelected envBatchStart envBatchStop envBatchMove envBatchDelete envBatchResult envBatchFailed`；列与单元格 `envColName envColGroup envColNetwork envColFingerprint envColStatus envColLastActive envColActions envDirect envDirectWarning envGeoipFollowProxy envRunningFor envLastStopped envOpen envStart envStop envEdit envDuplicate envDelete envUngrouped envErrorReason`；状态 `statusStarting statusStopping statusRunning statusError statusStopped`；表单 `formSectionBasic formSectionNetwork formSectionFingerprint formSectionAdvanced formName formNameRequired formGroup formNewGroup formNotes formProxy formDirect formGeoip formTimezone formLocale formPlatform formPlatformWindows formPlatformMacos formFontSet formFontSetNone formFontSetMissing formFontSetInconsistent formFontSetSourceVersion formFontSetIntegrity formSeed formReseed formGpu formResolution formColorScheme formCreate formCreateAndStart formSave formValidationError formFieldPlatformHint formAdvancedHint`；详情/标签 `detailTabConfig detailTabFiles detailTabAutomation detailTabMaintenance detailOpenSession detailStart detailStop detailSearchDefaultsFailed detailRetrySearchDefaults detailApplyPending detailApplyAndRestart detailApplyError maintenanceDuplicateTitle maintenanceDuplicateConfigOnly maintenanceDuplicateWithState maintenanceDuplicateRunningDisabled maintenanceResetTitle maintenanceResetClear maintenanceResetKeep maintenanceResetConfirm maintenanceDeleteTitle maintenanceDeleteRunningDisabled`；分组 `groupManagerTitle groupNew groupRename groupColor groupDelete groupDeleteConfirm groupAffectedCount groupKeyboardHint groupUsedBy groupColorPalette groupCancel groupSave groupReorderUp groupReorderDown`。
- 硬约束：业务代码只用语义 token 类（禁 Tailwind 默认调色板类与 hex/rgb/hsl/oklch 字面量）；`data-testid` 按新组件结构命名，不保留旧名；旧测试语义有效则改选择器并保留断言语义，结构删除则整体删除并在此写明理由；禁止就地把旧断言预期改成新实现输出；浏览器测试一律无头。

### 门禁失败逐项根因与修复（监督纠正落实）

- 首轮全量门禁 `t037_evidence_v2`：`unit` 1 项失败 + `e2e` 7 项失败（含 t019 基线遗留 1 项）。逐项按失败日志定位，均非「已登记遗留」：
    1. **`unit` `test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths`**：t044 的 `review_code.md` / `review_test.md` 含开发者家目录绝对路径，t037 分支从 t044 起步但未登记白名单。按 t041 既有 A44「精确 `(path, sha256)` 对」模式，在 `tests/unit/review_privacy_allowlist.txt` 补 t044 两份报告的当前路径 + archive 路径共 4 条。定向 `8 passed`。属跨 task 缺陷在本 task 收口，未改 t044 已 done 的交付内容。
    2. **E2E 5 项 `test_frontend_app_e2e.py`（`ac001/ac002/ac004/ac007/ac009`）连锁失败**：`create_profile_via_ui` 走新建弹窗 UI 时 `[data-testid="env-new-dialog"]` 一直 hidden。临时 Playwright DOM 诊断（已删除）给出祖先链：`[role="dialog"]` 的 `data-state="open"`、`display:block`、`visibility:visible`，但 computed `maxWidth: 16px`、`width: 34px`，`env-new-dialog` 自身 `w:0`。根因：`src/styles/design_tokens.css` 定义 `--spacing-lg: 16px`，Tailwind 4 把 `shared/ui/Dialog.tsx` 的 `max-w-lg` 生成为 `max-width: var(--spacing-lg)`，Content 被压到 16px，子元素宽度 0 → Playwright 判 hidden。**试探性改动**（`ProfileCreateDialog` 条件渲染 + `open={true}`）验证后仍 hidden，已按监督要求撤回，恢复受控 `open={open}`；临时诊断代码已删除。修复：`Dialog.tsx` 的 `max-w-lg` → 显式 `max-w-[32rem]`（构建产物生成 `max-width:32rem`，不受 spacing token 污染）。补 `shared/ui/DialogWidth.test.tsx` 组件测试先红（`max-w-lg` 存在）后绿（显式值），定向 E2E `test_ac001_ac006_profile_ui_dual_tab_sse_and_stale_state` 复跑 `1 passed in 38.31s`。
    3. **`test_supervisor_namespace_policy_e2e::test_kernel_network_policy_real_netns`**：门禁 v2 报 `environment has no public egress to 1.1.1.1:80 (timed out)`。定向单跑 `1 passed in 21.00s`，确认是公网出口瞬时波动（testing.md 已记公网可达性 USER_WAIVED 口径），非 t037 回归；t044 最终门禁同一用例通过。
    4. **t019 首帧 3.344s > 2s**：t032 已登记遗留、t036 串行完整门禁同样仅此项失败，按项目惯例如实登记，不归因 t037。
- 监督纠正（偏差 A）已在「测试处置清单 / 三、四」登记：删除 `/profiles/new` 专门路由与旧路由断言，新增未知 `profileId` 按普通详情页的语义用例。

### AC-012 扫描命令与结果（最终交付口径，回应 review `t037_code_f001`）

- 口径：只判「本 task 新增源码」与「diff 新增行」是否引入颜色类 / 字面量；既有文件保留的旧色（`BrowserSessionPage.tsx` / `SessionDiagnostics.tsx` 的 `text-gray-500` / `bg-red-500` 等，属 t039 范围）不计入新增。
- 命令（cwd 仓库根）：
    - 新增源码文件集：`git status --short | grep -E '^\?\?|^ A ' | awk '{print $2}' | grep -E '^src/frontend/src/.*\.(tsx|ts)$' | grep -v 'generated/' | grep -v 'styles/'`（最终 **32 个 A 状态新增源码文件**）。
    - 颜色扫描：`grep -nE 'gray-[0-9]+|red-[0-9]{3}|blue-[0-9]{3}|#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(|oklch\(' <A 状态新增源码文件>` → **0 命中**。
    - 新增行扫描：`git diff --cached | grep -E '^\+' | grep -E 'gray-[0-9]+|red-[0-9]{3}|#[0-9a-fA-F]{3,8}\b'` → **0 命中**。
- 结果：32 个新增源码文件 0 命中、diff 新增行 0 命中；旧 4 个含硬编码颜色的页面组件（`ProfileNewPage` / `ProfileFilesPage` / `ProfileAutomationPage` / 旧 `ProfileDetailPage`）已按 D16 删除重建。AC-012「本 task 新增源码不含 Tailwind 默认调色板类与颜色字面量」成立。

### 监督纠正：设计 token 层根因修复（撤回 max-w-[32rem] 局部补丁）

- 监督判定 `Dialog.tsx` 写死 `max-w-[32rem]` 属局部补丁，绕开设计系统，不接受。根因在设计 token 层：`DESIGN.md` 生成的 `--spacing-xs/sm/md/lg/xl/2xl` 进入 Tailwind 4 的 `--spacing-*` 命名空间后，`max-w-lg` 被解析为 `max-width: var(--spacing-lg)`（16px），`max-w-sm/md/xs` 同理被压成 8/12/4px；`w-*`/`h-*`/`min-w-*`/`max-h-*` 的命名尺寸类同样会被劫持，任何组件写这类类名都会踩坑。
- 修复（从根上，组件只用语义 token 类、不写任意值）：
    1. `DESIGN.md` 新增正文 `## Container sizes` 章节（linter 0 error / 0 warning），定义 9 个独立语义尺寸 token：`dialog` 32rem、`dialog-width` calc(100% - 2rem)、`dialog-height` 90vh、`panel` 28rem、`hint` 20rem、`page` 100rem、`menu` 10rem、`select` 8rem、`control-sm` 1.875rem。
    2. `scripts/design_tokens.mjs` 解析该表，输出 `--container-*` 到 `@theme` 的**独立命名空间**（不被 `--spacing-*` 劫持），并显式生成 `h-*`/`max-h-*`/`min-h-*` 语义类（Tailwind 只对 `w-/max-w-/min-w-*` 自动用 container scale）；`design_tokens.css` 重新生成入库。
    3. 全仓扫描 11 处违规并一并替换为语义类：`Dialog.tsx`（`w-dialog-width max-w-dialog`，撤回 `max-w-[32rem]`）、`LoginPage`/`BrowserSessionPage`/`SessionDiagnostics`/`EmptyState`（`max-w-panel`）、`ClipboardPermissionHint`（`max-w-hint`）、`AppLayout`（`max-w-page`）、`DropdownMenu`（`min-w-menu`）、`Select`（`min-w-select`）、`Button`（`h-control-sm`）、`ProfileCreateDialog`（`max-h-dialog-height`）。构建产物验证 9 个语义类均解析到 `var(--container-*)`。
    4. 设计门禁：`design_tokens.mjs --lint` 新增 `assertNoSizeTokenHijack(sources)`，扫描 74 个业务源码文件，出现命名尺寸类 `(max-w|min-w|w|max-h|min-h|h|size)-(xs|sm|md|lg|xl|2xl)` 或任意尺寸值 `(...)-[...]` 即失败；`npm run design:lint` 结果 `74 files clean`。`scripts/design_tokens.test.mjs` 新增 3 例门禁单测（命名类失败、任意值失败、语义类通过）+ 确定性生成断言 `--container-dialog`；`DialogWidth.test.tsx` 保留并改为断言 `max-w-dialog`。TDD：先加门禁/复现测试确认红（`max-w-lg` 命中、`design:lint` 列出 11 处违规），再修复转绿。
    5. 撤回试探性改动：`ProfileCreateDialog` 恢复受控 `open={open}`（不再条件渲染 + `open={true}`），临时 Playwright DOM 诊断代码已删除。

### 门禁 v3 其它失败处置

- `test_ac007_lifecycle_resume_and_isolated_media_diagnostics`（v3 E2E 失败，`waiting for locator("[data-testid=env-new]")`）：根因是 t037 E2E 改写缺陷——`create_profile_via_ui` 走 UI 后依赖当前页面为首页，而该用例第二次创建时页面停在 `/session/{id}`。修复：`create_profile_via_ui` 每次先 `goto(harness.origin + "/")` 并等 `env-list-page` 再点 `env-new`。定向复跑 `1 passed in 48.25s`。
- `test_ac009_supervisor_unreachable_intent_preserved_and_recovers`（v3 integration 失败，`assert rt["last_coordinator_error"] is None` 实得残留 503）：t035/t041/t037 三个 task 门禁先后出现的同类协调类偶发失败，t041 的 `ac009_experiment.json`（每版 19 次、两版 0/19）只证明不是 t035 回归、未证明不是缺陷。按监督要求用 `pending.py new` 登记 `p047_ac009_coordination_flaky.md`（写明三次 task、用例名、失败断言与证据），收尾阶段从根因修；本轮不记为已登记遗留、不改断言求绿。
- `test_kernel_network_policy_real_netns`（v2 门禁公网 `1.1.1.1:80` egress 超时）：定向单跑 `1 passed in 21.00s`、v3 门禁未复现，属 testing.md 已记「公网候选可达性 USER_WAIVED」口径的环境瞬时波动，非 t037 代码回归；v4 门禁再次验证。
- t019 首帧 3.344s > 2s：t032 已登记遗留、t036 串行完整门禁同样仅此项失败，按项目惯例如实登记。

### 监督要求：ac009 协调类反复偶发失败从根因修复（p047 闭环）

- 门禁 v5 的 integration 再次出现 `test_ac009_supervisor_unreachable_intent_preserved_and_recovers` 失败（`assert rt["last_coordinator_error"] is None` 实得 `'Supervisor start failed (503): Mock supervisor failure'`）。t035 / t041 / t037 v3 / t037 v5 四次门禁反复出现，t041 的 `ac009_experiment.json`（每版 19 次、两版 0/19）只证明不是 t035 回归。按监督裁决「反复出现的偶发失败本身即缺陷」，本轮收尾从根因修复，不再以「已登记」放过。
- 根因：`runtime.observed_state = running` 由 Supervisor 通过 runtime 事件独立上报到 API，**与 `RuntimeCoordinator` 的 backoff 重试循环 `clear_last_error` 不在同一条路径**。恢复后 Supervisor 的 running 观察可能先于 coordinator 下一轮 `POST /supervisor/v1/profiles/start` 成功返回并清空错误；测试一旦观测到 `observed_state == running` 就断言 `last_coordinator_error is None`，命中竞态窗口，表现为低频偶发失败。
- 修复（确定性，产品层；不改断言求绿）：`RuntimeCoordinator.get_last_error(profile_id, runtime=None)` 增加收敛感知——当权威 runtime 记录 `desired_state == running && observed_state == running && runtime_instance_id is not None` 时，残留的 `last_coordinator_error` 视为已解决并清空；`runtime_views.make_runtime_response` 与 `runtime_coordinator.publish_profile_change` 两个读取点都传入当前 runtime，GET runtime 与 SSE publish 语义一致。
- 确定性复现测试（TDD 先红后绿）：新建 `tests/unit/test_runtime_coordinator_error_settle.py` 两例（收敛 runtime 清空残留 error、未收敛 runtime 保留 error），红版 `TypeError: unexpected keyword argument 'runtime'` 证明测试能捕获缺陷，修复后 `2 passed`；`test_runtime_coordinator_integration.py` 全量 `7 passed`。
- 验证：ac009 目标用例连续 **5/5 通过**；`pending.py archive p047 --resolution resolved --fix-ref t037` 归档遗留条目。

### ac009 根因修复的完整性与测试替身同步（Round 3 后补）

- code reviewer Round 3 提示 `src/backend/cbrowser/api/v1/router.py` 的 SSE **初始快照** `get_initial_snapshots` 仍调 `coordinator.get_last_error(p.id)`（不带 runtime），会与 GET runtime / SSE publish 的收敛感知不一致、泄漏残留 error。按「从根因修掉」一并修为 `get_last_error(p.id, runtime=rt)`，三个读取点语义统一。
- 产品接口增加 `runtime` 可选参数后，两个 integration 测试替身 `_StubCoordinator.get_last_error`（`test_api_search_defaults_routes.py`、`test_t026_transport_api.py`）签名未同步导致门禁返回 500。按「测试替身随被测接口同步，非改断言迎合实现」补 `runtime=None` 参数，并在本清单登记；全量 integration `137 passed, 18 skipped`、协调相关 unit `40 passed`。这是接口签名同步，不涉及断言预期修改。
- 门禁 v6 因在 stub 同步前启动而 integration 失败（`TypeError: _StubCoordinator.get_last_error() got an unexpected keyword argument 'runtime'`），已中止；最终以修复全部落地后的 v7 门禁为 finish 依据。

## 测试处置清单

按 D16 逐用例登记既有测试的改写/删除（仅改选择器且断言语义不变者注明结构变化；语义被推翻而删除者写旧用例名、理由与接替新用例；整文件删除者逐个列出用例去向）。

### 一、仅改选择器 / 断言语义不变（D16 结构变化）

- `src/frontend/src/app/router.test.tsx`
    - `renders the plan 5.1 route table`：仅改 testid。D16 结构变化：`/` 占位页 → `EnvironmentListPage`（`env-list-page`）；`/profiles/:id/{config,files,automation,maintenance}` 四个占位/旧页 → 统一新 `ProfileDetailPage`（`profile-detail-view`）。`/session`、`/proxies`、`/session/:id`、`/settings`、`/login` 断言原样保留，断言数量不变。
    - `drops the legacy routes`：仅改预期 testid（三个 legacy 路径落 `*` 兜底回 `/`，渲染 `env-list-page` 而非旧 `placeholder-page`）；保留 `queryByTestId("active-profile-header")` 为空、`router.state.location.pathname === "/"` 等全部断言。D16：旧 `/profiles/new`、`/automation/:id`、`/?profileId=` 不再有页面。
    - `renders navigation as real anchors`：原样不动（侧栏 4+ 个 `<a href>`）。
    - `redirects /profiles/:profileId to the config tab`：原样不动。
    - `offers duplicate and reset confirmations on the config page` → 改名 `offers duplicate and reset actions on the maintenance tab`：改路由为 `/profiles/p1/maintenance`、改 testid 为新 `profile-detail-view`/`profile-maintenance-tab`；保留「duplicate payload 含 `include_browser_state: false`」「reset 前未调用、点击后 `client.profiles.reset`」「重置区含 cookies 说明」三条真实断言语义。移除的 2 条旧断言（`profile-duplicate-button` 打开 `profile-duplicate-panel`、`profile-reset-button` 打开 `profile-reset-panel`）绑定已删除的二次确认面板结构：新 `MaintenanceTab` 为直接按钮执行，属结构删除而非弱化。
- `src/frontend/src/features/settings/SettingsPage.test.tsx`（删除 `ProfileNewPage.tsx` 的必要连带迁移）
    - `switches remaining i18n labels and placeholders`：原 3 条 i18n 断言（`profileNameExample` zh/en、`Width (px)`）迁移为 4 条（`getByText("名称"/"Name")`、`getByLabelText("宽度 (px)"/"Width (px)")`），中英切换覆盖不减反增。D16：渲染对象由 `ProfileNewPage` 改为共用 `ProfileForm`，stub 补 `groups`/`proxies`/`fontSets` 以触达新组件真实 hooks。
    - `renders font set data from GET /api/v1/font-sets`：断言原样不动。
    - `shows an integrity warning for a font set with problems`：断言原样不动。

### 二、整文件删除（结构删除，逐用例去向）

- `src/frontend/src/features/profiles/ProfileDetailPage.control.test.tsx`（4 例）——旧详情页 control 面板与旧 testid；新 control 面板位于自动化 Tab（`ProfileAutomationTab`）。
    - `shows the control owner, handoff reason, and restore entry after a takeover` → `ProfileAutomationTab.test.tsx`「renders status/endpoint/control panel」+「restores agent control」。
    - `restore calls the control endpoint and hides the restore entry` → `ProfileAutomationTab.test.tsx`「restores agent control」。
    - `hides the control panel when the runtime carries no control state` → `ProfileAutomationTab.test.tsx`「hides the control panel when no control」。
    - `SSE takeover event refreshes the panel owner (f007 assembly)` → `useProfilesQuery.control.test.tsx`（SSE control 按 generation 合并）+ `ProfileAutomationTab.test.tsx` 面板读取 runtime。
- `src/frontend/src/features/profiles/ProfileDetailPage.isolation.test.tsx`（4 例）——旧详情页 per-profile 动作隔离与旧 testid；新页面结构下由 `ProfileIsolation.test.tsx`（8 例）承接。
    - `does not show A's apply error on B` → `ProfileIsolation.test.tsx`「does not show A's launch error on B across the new pages」+ `scopeMutationToProfile.test.ts`「does not show A's error on B」。
    - `does not disable B's apply while A's apply is pending, and A's late failure does not pollute B` → `ProfileIsolation.test.tsx`「does not disable B's start while A's start is pending」「does not let A's late failure pollute B's error region」+ `scopeMutationToProfile.test.ts` 同名语义用例 + `useProfilesQuery.actionkeys.test.tsx`（每项独立幂等键）。
    - `does not show A's late update failure on B (local banner channel)` → `ProfileIsolation.test.tsx` 第 3 例 + `useProfilesQuery.actionkeys.test.tsx`。
    - `does not show A's late update success on B (local banner channel)` → 同上。
- `src/frontend/src/features/profiles/ProfileDetailPage.searchDefaults.test.tsx`（2 例）——旧 testid `search-defaults-failed`；新 `SharedProfileBanners` 用 `profile-search-defaults-failed`。
    - `shows an independent failure notice with a retry action` → `ProfileDetailPage.test.tsx`「shows both shared banners on the config tab」（含 retry）+ `useProfilesQuery.test.tsx`「merges search_defaults from runtime events」。
    - `shows no notice when search defaults applied` → `ProfileDetailPage.test.tsx` banner 不显示分支 + `useProfilesQuery.test.tsx`。
- `src/frontend/src/features/artifacts/ProfileFilesPage.test.tsx`（4 例）——旧页面整体被 `ProfileFilesTab` 替换。
    - `lists artifacts with a download link and container path` → `ProfileFilesTab.test.tsx`「lists artifacts with same-origin download link」。
    - `uploads selected files through the artifact API` → `ProfileFilesTab.test.tsx`「uploads through artifacts.upload」。
    - `stops at the first failed upload and reports succeeded/failed/remaining counts (A20)` → `ProfileFilesTab.test.tsx`「first failure stops and does not leak file content」。
    - `deletes an artifact after confirmation and removes its row` → `ProfileFilesTab.test.tsx`「delete confirm + failure banner visible」。
- `src/frontend/src/features/automation/ProfileAutomationPage.test.tsx`（1 例）
    - `renders the authorized endpoint and runtime status on direct load` → `ProfileAutomationTab.test.tsx`「renders status/endpoint」。
- 旧组件文件（非测试，AC-012 一并删除）：`features/profiles/ProfileNewPage.tsx`（→ `ProfileCreateDialog`+`ProfileForm`）、`features/artifacts/ProfileFilesPage.tsx`（→ `ProfileFilesTab`）、`features/automation/ProfileAutomationPage.tsx`（→ `ProfileAutomationTab`）。

### 二之二、旧 `ProfileDetailPage.test.tsx` 主文件 6 例逐用例去向（review `t037_test_f001` 补登）

- 旧主文件相对 diff_anchor 由 6 例整体重写为 8 例，旧 `data-testid` 全删（D16 结构删除），整体删除理由成立；逐用例去向如下：
    - `does not overwrite unsaved edits when background data refreshes`（A22）→ 新 `ConfigTab.test.tsx`「keeps unsaved name edits when the profile query is refreshed in the background」（`setQueryData` + `invalidateQueries` 双重后台刷新，断言编辑值不被覆盖）。
    - `saves edited fields through the update mutation` → `ProfileForm.test.tsx` 提交断言 + E2E `test_ac001_ac006_profile_ui_dual_tab_sse_and_stale_state` 真实栈改名保存。
    - `deletes the profile after confirmation and navigates away` → 新 `MaintenanceTab.test.tsx`「deletes with a fresh idempotency key per action and keeps the tab mounted after success」（按新组件真实行为：删除后标签仍挂载、无导航；不臆造旧语义）+「disables delete while the profile is running」。
    - `duplicates with the settings-only payload from the panel` → `router.test.tsx` 新 maintenance 用例（duplicate payload 含 `include_browser_state: false`）。
    - `resets only after the panel confirmation` → `router.test.tsx` 新 maintenance 用例（reset 前未调用、点击后调 `client.profiles.reset`）。
    - `applies pending display settings via stop then start` → `useProfilesQuery.apply.test.tsx` / `useProfilesQuery.applyresume.test.tsx`（stop→start 独立键与阶段恢复）+ `ProfileDetailPage.test.tsx`「shows both shared banners on the config tab」。

### 三、整合子代理两处偏差裁决

- 偏差 A（监督纠正，最终裁决）：**不接受**保留 `profiles/new` 回落。依据「零兼容性负担」铁律与 plan 第 211 行「旧路由直接删除，不做重定向」——为旧 URL 专门写路由跳回首页就是兼容层。已删除 `router.tsx` 的 `profiles/new` 专门路由，让它被 `profiles/:profileId` 以 `profileId="new"` 捕获，走 `Navigate to="config"` → 新详情页未找到环境的正常状态。`router.test.tsx` 中 `drops the legacy routes` 用例整体删除（三条旧路由断言 `/profiles/new`、`/automation/p1`、`/?profileId=p1` 全部不再有任何特殊语义），新增 `treats an unknown profileId as a normal detail route`（断言 pathname 为 `/profiles/new/config`、渲染 `profile-detail-view`、不渲染列表页、`client.profiles.get("new")` 被调用）。
- 偏差 B：连带修改 `SettingsPage.test.tsx`（非原独占文件）。属删除 `ProfileNewPage.tsx` 的必要连带，断言不减反增。裁决：接受，按上面「一」逐用例登记。

### 四、监督纠正后的逐用例处置（追加）

- `src/frontend/src/app/router.test.tsx` 的 `drops the legacy routes`（1 个用例，内含 3 条针对 `/profiles/new`、`/automation/p1`、`/?profileId=p1` 的旧路由断言）：**整体删除**。理由：零兼容性负担 + plan:211，旧 URL 不再有任何特殊语义，为它们保留断言等于保留兼容层契约。接替：新用例 `treats an unknown profileId as a normal detail route`（覆盖未知 `profileId` 按普通详情页处理、未找到环境的正常状态），`renders the plan 5.1 route table` 仍覆盖 `/` → `env-list-page` 的主路由语义。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-07T02:20:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t037_code_f001|minor|已修|AC-012 扫描笔记口径改为「A 状态新增源码 + diff 新增行」，重扫 32 文件 0 命中、新增行 0 命中，既有保留色不计入新增|本文件「AC-012 扫描命令与结果」|
|t037_code_f002|minor|已修|详情页改用 `EnvironmentTable` 导出的共享 `statusDescriptor(observed)`（含 `?? STATUS_MAP.stopped!` 兜底），删除本地重复 `STATUS_MAP`，消除与列表 / 卡片页分叉|`src/frontend/src/features/profiles/ProfileDetailPage.tsx`|
|t037_test_f001|minor|已修|处置清单补登旧主文件 6 例逐用例去向；新增 `ConfigTab.test.tsx`（A22 后台刷新不覆盖未保存编辑）与 `MaintenanceTab.test.tsx`（删除独立幂等键、运行中禁删）|本文件「测试处置清单」、两个新测试文件|

code 轴另有 1 条 minor 与本表 `t037_code_f001/f002` 对应，test 轴除 `t037_test_f001` 外零 finding。

### Round 2 (2026-11-07T02:25:00+08:00)

Round 2 零新 finding（scope 重绑定 `f67f9b5beab34aa9`）：前轮 3 条 minor 已按处置表修复，无新 blocker。

### Round 3 (2026-11-07T02:45:00+08:00)

Round 3 零新 finding（scope 重绑定 `f92bd0d7901781fa`）：ac009 根因修复 + 确定性红测 + p047 闭环；无新 blocker。

### Round 4 (2026-11-07T03:00:00+08:00)

Round 4 零新 finding（scope 重绑定 `68587ae956c27987`）：SSE 初始快照根因完整性 + stub 签名同步；Round 3 提示闭环。

### Round 5 (2026-11-07T03:20:00+08:00)

Round 5 零新 finding（最终 scope 重绑定 `2a1217ac45ea38e9`）：第三个测试替身签名同步 + 环境残留清理 + p048 登记；无新 blocker、前轮 minor 未回退。`check_review_status.py`：code_verdict=PASS / test_verdict=PASS / overall=PASS / review_scope=ok / ac_review=ok / round=5 / next_action=finalize。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（12 条 AC 全部打勾）
- 测试：最终并行全量门禁 `.scratch/t037_evidence_v8/manifest.json`：requirements_check / contract / unit / integration / design_lint / design_check / frontend_test / frontend_build / image_packages 九 suite exit 0（contract 258 / unit 1143 / integration 155 用例）；前端 `tsc -p tsconfig.test.json` 与 `tsc -p tsconfig.json` 均通过、Vitest `298 passed`（49 文件）、`npm run build` 通过、`design:lint` 0 error/0 warning + 74 文件尺寸门禁 clean、`design:check` 产物一致；AC-012 颜色扫描 32 个新增源码文件 0 命中、diff 新增行 0 命中；ac009 确定性红测 + 连续 5/5 通过、全量 unit 1143 / integration 137 通过。
- 黑盒：最终 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh` E2E 101 用例真实并行执行（无头 Chrome）：`test_t019_switch_and_refresh_first_frame_within_2s_host_only` 1 项为 t032 已登记基线遗留（首帧 3.344s > 2s，t036 串行门禁同样仅此项）；v8 另有 3 项**环境波动**（`test_frontend_adapter_build::test_vendor_replaces_stale_destination_contents` 的 SSL EOF、`test_frontend_app_e2e::test_ac007...` 的媒体帧计数时序、`test_supervisor_recovery_e2e::test_supervisor_dual_profile_port_invariance_on_sigkill` 的 setup ReadTimeout），三者定向重跑 `3 passed in 213.30s`，确认非 t037 代码回归；2 项按开关启用的探针用例 skip（AC-005 可选用例外）、0 error。v4/v5 门禁失败集合仅 t019，达标。被中止的 v6 残留容器已按测试前缀清理（p048 登记门禁基础设施修复）。门禁后无本轮残留容器与网络。
- review：full 两路 `review_code.md` / `review_test.md` 共 5 轮，Round 1 3 条 minor 全部「已修」、Round 2~5 零新 finding，12/12 AC 全程 TICK-VALID（两轴均 re_verified，coverage 12/12），最终 reviewed_scope `2a1217ac45ea38e9`；`check_review_status.py`：overall=PASS / review_scope=ok / ac_review=ok / next_action=finalize。
- AC 判定：见 `task.md` 行内打勾（12/12）

### 结果摘要

- 交付：`features/profiles/` 全套环境管理界面（列表 8 列/卡片/工具栏 URL 筛选排序/批量逐项 API 与独立幂等键/共用 `ProfileForm` 四分区/新建弹窗/新详情页四标签/分组管理弹窗/维护标签）+ `ApiClient` groups/proxies/fontSets 命名空间与 hooks + 121 个双语文案键；`DESIGN.md` 的 `## Container sizes` 独立语义尺寸 token 与生成器 `--container-*` 命名空间 + `assertNoSizeTokenHijack` 设计门禁（撤回局部补丁）；ac009 协调类反复偶发失败从根因修复（`get_last_error` 收敛感知、三读取点统一、确定性红测、p047 归档）。

- 质量整改：按监督纠正逐项查根因并修（`/profiles/new` 兼容层删除、`max-w-[32rem]` 局部补丁撤回改 token 层、ac009 反复失败根因、门禁残留容器清理登记 p048、旧测试逐用例处置登记）；E2E 走 UI 新建弹窗，不直接 POST API。

- 遗留：`p046`（run_gate_suite 空并行集合 exit 5 边界，minor）、`p048`（门禁中断残留容器清理）；t019 首帧超时按 t032 已登记遗留如实登记，不归因 t037。

### 长期文档闭环

- specs_index：`profile_management` 关联 `t037`、`ui_design_system` 关联 `t037`（Container sizes token）。

- 生效 spec：`docs/specs/profile_management.md` 累积「环境管理界面（t037）」节（列表/批量/分组/共用表单/四标签/维护/隔离语义）；`docs/blueprint/frontend.md` 第 7 节（路由、数据装配、共用表单、测试策略、尺寸语义 token）。

- 正式 spike：无；findings：无新增；pending：`p046`（t044 review minor 遗留）、`p047` 已归档 resolved（fix-ref t037）、`p048` 待办（门禁残留清理）。
