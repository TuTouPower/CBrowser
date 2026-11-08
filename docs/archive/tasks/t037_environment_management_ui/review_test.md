# Task review t037（reviewer_focus: 测试）

- task：`t037_environment_management_ui`
- spec：`docs/tasks/t037_environment_management_ui/task.md`
- diff_anchor：`05dda065aa237f9e32c3507f6f6a65f47a185205`
- target：`git -C '/Users/karson/kar/code/CBrowser_t037' diff 05dda065aa237f9e32c3507f6f6a65f47a185205`
- round：1
- reviewed_at：2026-11-07T02:08:00+08:00

reviewed_scope: a4588130decb7633

## Findings

### t037_test_f001 - ProfileDetailPage.test.tsx 主文件 6 例整体重写未逐用例登记，两条旧回归语义无等价接替

- 严重度：minor
- 锚点：改测方向复核（spec「测试策略」「红灯归因与改测审查」）；AC-008 / AC-009 覆盖可更广，非 AC 完全无测试、非假行为
- 位置：`src/frontend/src/features/profiles/ProfileDetailPage.test.tsx`（diff 225→248 行整体重写）、`docs/tasks/t037_environment_management_ui/progress.md:73`（「测试处置清单」）
- 问题：该文件相对 anchor 由 6 例整体重写为 8 例，旧 `does not overwrite unsaved edits when background data refreshes`（A22）、`saves edited fields through the update mutation`、`deletes the profile after confirmation and navigates away`、`duplicates with the settings-only payload from the panel`、`resets only after the panel confirmation`、`applies pending display settings via stop then start` 全部删除。`progress.md:73` 处置清单逐用例登记只覆盖 `router.test.tsx`/`SettingsPage.test.tsx` 改写与 `ProfileDetailPage.control/isolation/searchDefaults.test.tsx`、`ProfileFilesPage.test.tsx`、`ProfileAutomationPage.test.tsx` 整文件删除，未登记本主文件 6 例去向。其中 duplicate/reset 由 `router.test.tsx` 新 maintenance 用例接替、apply 的 stop→start 独立键由 `useProfilesQuery.apply.test.tsx:25` 与 `useProfilesQuery.applyresume.test.tsx` 接替、改名保存由 E2E `test_ac001_ac006...` 真实栈接替；但 A22「后台刷新不覆盖未保存编辑」与「删除确认后导航」两条回归语义在最终交付无等价或更高层测试（全仓复算 `unsaved|overwrite|invalidateQueries` 仅命中 `useProfilesQuery.control.test.tsx:124` 的 SSE generation 注释，与表单无关）。按 spec「旧测试语义失效时新增覆盖新语义 / 整体删除并写明理由」，整体删除理由成立（D16 旧 testid 全删），但逐用例去向与两条语义接替缺失；属覆盖可更广与登记完整性，不构成 blocking。
- 建议：在处置清单补登该主文件 6 例去向；为 A22 补一条 `ProfileForm`/`ConfigTab` 层用例（`invalidateQueries` 后本地编辑值不被覆盖），为维护标签删除补一条 UI 用例。

## 结论

- 改测方向复核：无「让断言迁就当前实现」的改测。逐处核对三处既有测试改写：`router.test.tsx` 的 `drops the legacy routes` 按监督纠正（零兼容性负担）整体删除并新增 `treats an unknown profileId as a normal detail route`（断言 pathname 为 `/profiles/new/config`、渲染 `profile-detail-view`、不渲染列表页、`profiles.get("new")` 被调用）；`renders the plan 5.1 route table` 仅随 D16 改 testid、断言数量不变；`offers duplicate and reset...` 改路由至 maintenance，移除的 2 条断言绑定已删除的二次确认面板（结构删除），`resetCalled` 布尔量改为 spy `not.toHaveBeenCalled()`→`toHaveBeenCalledWith("p1", expect.any(String))` 属增强非弱化。`SettingsPage.test.tsx` 由 `ProfileNewPage` 迁至共用 `ProfileForm`，stub 补 groups/proxies/fontSets 以触达真实 hooks，i18n 断言由 8 条增至 9 条（`getByText`/`getByLabelText` 中英切换），不减反增。`ProfileDetailPage.test.tsx` 为整体重写（非就地改预期）。5 个整文件删除的旧用例名与登记逐一核对一致，接替新用例（`ProfileIsolation` 8、`ProfileFilesTab` 5、`ProfileAutomationTab` 4、`ProfileDetailPage` banner、领域层 apply/control/actionkeys 测试）真实存在。
- 本轮新发现：1 条（critical 0 / important 0 / minor 1）
- 未进表的提示：
    - AC-009 维护标签「删除」「运行中禁含浏览器状态复制/删除」、AC-008「应用并重启按钮点击」、AC-007「双 banner 四标签共享」、AC-010「删除后环境显示未分组」缺直接 UI 断言，属覆盖可更广（实现见 `MaintenanceTab.tsx:71/117`、`SharedProfileBanners`）；`ProfileAutomationTab.test.tsx` 的 `restores agent control` 未断言恢复后 restore 入口隐藏（旧 `ProfileDetailPage.control.test.tsx:181` 有此断言），属接替用例可补一条。均非 AC 完全无测试，不阻断。
    - `progress.md:81` 处置清单「一」仍写 `drops the legacy routes`「仅改预期 testid」，与「三/四」（`progress.md:116/121`）最终裁决「整体删除」字面不一致；以 diff 为准为整体删除 + 新增未知 profileId 用例，最终裁决一致，仅旧描述残留。
    - AC-012 颜色扫描笔记（`progress.md:53-54` 记 46 文件 0 命中）与最终 worktree 独立复算不一致：笔记命令取到 57 文件、颜色类命中 30 处，均为 `BrowserSessionPage`/`SessionDiagnostics` 修改行保留的既有 `text-gray-500` 等类，diff `+` 行仅 1 处命中且非本 task 新增；「新增源码不含调色板类/颜色字面量」实现层成立，证据记录偏差已由同轮 `t037_code_f001` 覆盖，test 轴不重复出 finding。
    - 完整门禁（Vitest 298 / contract 258 / unit 1141 / integration 155 / e2e 101）与 E2E 真实栈运行依赖 `.scratch/t037_evidence_v4/manifest.json` + `junit/*.xml` + `logs/`；本轮独立定向复跑 `design_tokens.test.mjs` + `DialogWidth.test.tsx`（9 例全绿）、查证 10 个新/改测试文件断言、核对 E2E testid 生产定义、重算 reviewed_scope 指纹（`a4588130decb7633` 与当前 worktree 精确匹配）、核对失败集合。
- 总体判断：12 条 AC 打勾均由真实、非恒真、触达生产组件的测试或替代验证支撑；测试只在 ApiClient 边界注入 stub，断言具体（幂等键互异、调用顺序、409 失败汇总、负向隔离、`stop` 未被调用），无 `.skip`/`.only`/静默错误/恒真断言/弱化断言；`DialogWidth.test` 断言能捕获 `max-w-lg` 缺陷、`assertNoSizeTokenHijack` 3 例能捕获命名类与任意值且语义类通过；`design:lint` 74 files clean、`design:check` 一致、构建产物 9 个语义类解析到 `var(--container-*)`；监督纠正（受控 `open={open}` 恢复、临时 DOM 诊断删除、`max-w-[32rem]` 撤回改 `max-w-dialog`）均已落实。v4 门禁 e2e 101 用例仅 `test_t019_switch_and_refresh_first_frame_within_2s_host_only` 1 项失败（3.372s > 2s，t032/t036 基线遗留、如实登记、未改断言求绿）、2 项 t032 开关 skip、0 error，失败集合不超 t036 串行基线；`p047` 对 ac009 协调类偶发失败明确「不记已登记遗留、不改断言求绿」，namespace policy 公网波动按 testing.md USER_WAIVED 口径。唯一 minor 为登记/覆盖扩展，无未解决 critical / important，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`EnvironmentListPage.test.tsx` 4 例：8 个 `thead th`、p1 行含 Alpha/primary/Work/US Proxy/socks5/US/windows、p2 行含 `envUngrouped` 且不含 `envGeoipFollowProxy`、`env-direct-p2` 含警示文案与 svg、五态 `env-status-*` 文案与 `env-error-reason-s4` 含 "coordinator down"、运行中/已停止时长前后缀断言。
- AC-002：TICK-VALID，re_verified。同文件 10 例：`/?q=Alpha&status=running&group=g1&proxy=px1&sort=name` 还原后 `rowIds()==["env-row-p1"]` 且 location.search 含五项参数、status/group/proxy/q 独立筛选各断言精确 rowIds、搜索写入 `q=Beta`、sort=name/manual 两种顺序、清除筛选后 rowIds 恢复三行、无环境空状态 `env-empty-create`。
- AC-003：TICK-VALID，re_verified。同文件 2 例：点击 `env-layout-card` 后 `localStorage["cbrowser.environments.layout"]=="card"`，卸载重渲染仍为 `env-card-grid` 且 `env-table` 为 null，卡片含名称/分组/代理/平台，`env-card-preview-p1` 占位元素存在且内容为空，切回 list 持久化。
- AC-004：TICK-VALID，re_verified。同文件 1 例：`queryClient.setQueryData(profileKeys.runtime("p1"), error runtime)` 模拟 SSE runtime 缓存增量，waitFor 断言行状态 `statusError`、不含 `statusRunning`、`env-running-count` 由 "1" 变 "0"。
- AC-005：TICK-VALID，re_verified。同文件 5 例：4 类批量操作各 `toHaveBeenCalledTimes(2)` 且 `new Set(keys).size===2`（独立幂等键），move 校验 `group_id==="g2"`；`deleteImpl` 对 p2 抛 `ApiError(409,"profile_running")` 后 toast 汇总 success=1/failed=1、p1 `aria-checked=false`、p2 仍 `true`、batch-bar 保留 1 项。
- AC-006：TICK-VALID，re_verified。`ProfileForm.test.tsx` 7 例（四分区、空名阻止提交 + `formNameRequired` 字段错误、字体集同平台过滤并默认最新 `win-new`、完整性告警、reseed 后种子变化、edit 全值提交）+ `ProfileCreateDialog.test.tsx` 3 例（create 不启动、`profile-form-submit-start` 后 `setDesiredState("p-new","running")` 且 `invocationCallOrder` create\<start、空名不关闭弹窗），受控 `open` 已恢复；`DialogWidth.test.tsx` 断言 `max-w-dialog` 且不含 `max-w-lg`。
- AC-007：TICK-VALID，re_verified。`ProfileDetailPage.test.tsx` 8 例：STATUS_CASES 5 例断言 `profile-detail-status` 文案精确等于 `en.status*`，四 tab 锚点 href 精确为 `/profiles/p1/{config,files,automation,maintenance}`，start/stop 分别触发 `setDesiredState`/`stop` 带幂等键，`profile-search-defaults-failed` + `profile-apply-pending` 双 banner 且 retry 触发 `retrySearchDefaults("p1",...)`。
- AC-008：TICK-VALID，re_verified。`ProfileForm.test.tsx` 2 例元数据编辑 `onDirtyRuntimeConfig` 不传 true、运行字段（timezone）改动传 true，配合 `shows both shared banners` 用例；`useProfilesQuery.apply.test.tsx:25` 断言 stop/start 幂等键互异，`applyresume.test.tsx` 7 例覆盖阶段恢复，构成「应用并重启」领域层接替。
- AC-009：TICK-VALID，re_verified。`ProfileFilesTab.test.tsx` 5 例（列表 name/size/time/path + `list("p1")`、same-origin 下载链接、上传经 `artifacts.upload`、首个失败 `toHaveBeenCalledTimes(2)` 且 `not.toContain("SECRET-*")`、删除确认后 `artifact-error` 显示 disk full）+ `ProfileAutomationTab.test.tsx` 4 例（端点/运行状态/复制/恢复 agent control owner Human→Agent/无 control 隐藏面板）+ `router.test.tsx` maintenance 用例（duplicate payload `{include_browser_state:false}`、reset 前置未调用后置 `toHaveBeenCalledWith`）+ E2E `test_ac009...` junit passed；维护标签删除/运行中禁用子行为缺 UI 断言属 minor 覆盖扩展（见 f001/提示）。
- AC-010：TICK-VALID，re_verified。`GroupManagerDialog.test.tsx` 10 例：列表 `group-used-by` 计数 2/1、create `{name:'Team A',color:'teal',sort_order:2}`、rename/改色 `groups.update` 参数、up/down `ordered_ids:['g2','g1','g3']`、键盘 ArrowUp `['g1','g3','g2']`、`dragStart/dragOver/drop` `['g2','g3','g1']`、删除确认框含 "2 environments" 与 `group-affected-count`、409 `group_name_in_use` 不被吞。
- AC-011：TICK-VALID，re_verified。`ProfileIsolation.test.tsx` 8 例：3 例动作状态隔离（A 的 launch error / pending start / late failure 不串到 B，跨 session→detail→list 三页面负向断言 + 按钮 `not.toBeDisabled`），3 例每标签独立 `sessionStorage["cbrowser.session.target"]`（pA、pB 无 A 残留、切换更新），2 例 mount/`beforeunload`/unmount 后 `spies.profiles.stop` 均 `not.toHaveBeenCalled()`。
- AC-012：TICK-VALID，re_verified。`tests/e2e/test_frontend_app_e2e.py:93-120` 的 `create_profile_via_ui` 改走 UI（`goto("/")`→`env-list-page`→`env-new`→`env-new-dialog`→`profile-form-name`→`profile-form-submit`→dialog detached→`env-row-*`），不再直接 POST；5 个旧页面组件与 5 个旧测试文件删除、`env-list-page`/`env-new`/`env-new-dialog`/`profile-form-name`/`profile-form-submit`/`env-row-*`/`profile-detail-view` 均在生产源码有定义；颜色扫描命令与 0 命中结果写入 `progress.md:51-54`（数字偏差见提示，实现层成立）；junit e2e 101 用例中相关 E2E 用例 passed，仅 t019 首帧 1 项基线遗留失败。

coverage = re_verified / 12

verdict: PASS

## Round 2 (2026-11-07T02:25:00+08:00)

reviewed_scope: f67f9b5beab34aa9

本轮 scope 重绑定至 `f67f9b5beab34aa9`（相对 diff_anchor 的完整交付内容含新增交付文件）。前轮 `t037_test_f001` 已按 `progress.md`「Review 处置 / Round 1」处置表补测 + 补登记：处置表 3 条 finding（`t037_code_f001`/`t037_code_f002`/`t037_test_f001`）均标「已修」，「测试处置清单 / 二之二」补齐旧 `ProfileDetailPage.test.tsx` 主文件 6 例逐用例去向。本轮无新 finding、无未解决 blocker；A22 与维护删除语义均有等价或更高层接替。

- 前轮 finding 复核：`t037_test_f001` 已消除。旧 A22「后台刷新不覆盖未保存编辑」由 `ConfigTab.test.tsx` 接替且强化为 `setQueryData` + `invalidateQueries` 双重刷新；旧「删除确认后导航」按新组件真实行为由 `MaintenanceTab.test.tsx`「删除独立幂等键 + 成功后标签仍挂载 + 运行中禁删」接替（progress.md:123 明示不臆造旧导航语义）。6 例去向逐条与接替测试核对一致。
- 新增测试可信与断言强度复核：`ConfigTab.test.tsx`/`MaintenanceTab.test.tsx` 均经 `QueryClientProvider` + `ApiClientContext.Provider` 渲染真实 `ConfigTab`/`MaintenanceTab` 与真实 hooks，stub 只注入在 ApiClient 边界（`profiles.get`/`delete`/`getRuntime` 等），夹具 `profile()`/`runtime()`/`group()`/`proxy()`/`fontSet()` 为带类型标注的完整线形状，未 mock 被测组件逻辑；断言为具体值（`toHaveValue('Unsaved Edit')` 双重刷新后保持、`get` 调 2 次且 cache 变 `Fetched From Backend`、两次删除幂等键互异、`toBeDisabled`、`not.toHaveBeenCalled()`），非恒真，无 `.skip`/`.only`/静默错误/弱化断言。`design_tokens.test.mjs` 3 例尺寸门禁（命名类拒绝、任意值拒绝、语义类通过）与 `DialogWidth.test.tsx` 断言 `max-w-dialog` 且不含 `max-w-lg` 仍有效。
- 改测方向复核：无「让断言迁就当前实现」的改测；本轮仅新增测试与登记，未改既有断言预期。
- 本轮新发现：0 条（critical 0 / important 0 / minor 0）
- 未解决 blocker：无
- 独立复跑：`cd src/frontend && npx vitest run ConfigTab.test.tsx MaintenanceTab.test.tsx design_tokens.test.mjs DialogWidth.test.tsx` → Test Files 4 passed、Tests 12 passed（1 + 2 + 8 + 1），0 失败。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`EnvironmentListPage.test.tsx` 4 例断言 8 列表头、直连警示、geoip 随代理、五态徽标与 error 原因、运行时长/停止相对时间；本轮 scope 重绑定后交付未变。
- AC-002：TICK-VALID，re_verified。同文件 10 例断言 URL 五参数还原 `rowIds`、四类独立筛选、搜索写 `q`、两种排序、清除筛选、无结果空状态；交付未变。
- AC-003：TICK-VALID，re_verified。同文件 2 例断言布局写 `cbrowser.environments.layout`、刷新后仍 card、卡片字段与缩略图占位；交付未变。
- AC-004：TICK-VALID，re_verified。同文件 1 例 `setQueryData(profileKeys.runtime)` 模拟 SSE 增量，断言行状态与 `env-running-count` 实时更新；交付未变。
- AC-005：TICK-VALID，re_verified。同文件 5 例断言四类批量各 2 次调用且 `new Set(keys).size===2`、move 参数、409 失败汇总与失败项保持选中；交付未变。
- AC-006：TICK-VALID，re_verified。`ProfileForm.test.tsx` 7 例 + `ProfileCreateDialog.test.tsx` 3 例断言四分区/必填/字体集过滤/create-start 顺序；本轮 `DialogWidth.test.tsx` 重跑断言 `max-w-dialog` 且不含 `max-w-lg` 通过；交付未变。
- AC-007：TICK-VALID，re_verified。`ProfileDetailPage.test.tsx` 8 例断言五态文案、四 tab href、start/stop 幂等键、双 banner 与 retry；交付未变。
- AC-008：TICK-VALID，re_verified。本轮新增 `ConfigTab.test.tsx`（A22）经 `setQueryData` 推送 + `invalidateQueries` 重取双重后台刷新，`get` 调 2 次且 cache 变 `Fetched From Backend`，断言 `profile-form-name` 编辑值 `Unsaved Edit` 始终保留、`profile-apply-pending` 出现；配合 `ProfileForm.test.tsx` 元数据/运行配置分类与 `useProfilesQuery.apply*` stop→start 独立键，重跑全绿。
- AC-009：TICK-VALID，re_verified。本轮新增 `MaintenanceTab.test.tsx` 2 例断言删除 `('p1', key)` 两次幂等键互异、成功后 `profile-maintenance-delete` 仍挂载且无 error、运行中按钮 disabled 且点击不调用 delete；配合 `ProfileFilesTab`/`ProfileAutomationTab`/`router` maintenance 与 E2E `test_ac009`，重跑全绿。
- AC-010：TICK-VALID，re_verified。`GroupManagerDialog.test.tsx` 10 例断言计数、create/rename/改色参数、拖动与键盘排序、删除确认受影响数、409 不吞；交付未变。
- AC-011：TICK-VALID，re_verified。`ProfileIsolation.test.tsx` 8 例断言动作状态隔离、每标签独立 sessionStorage target、关闭页面不 stop；交付未变。
- AC-012：TICK-VALID，re_verified。E2E `create_profile_via_ui` 走 UI、旧 5 组件/5 测试删除、`progress.md:51-58` 可复现扫描口径 32 文件 0 命中；本轮 `design_tokens.test.mjs` 重跑 8 例（含 3 例尺寸门禁）全绿，相关 junit E2E passed，仅 t019 首帧基线遗留。

coverage = re_verified / 12

verdict: PASS

## Round 3 (2026-11-07T02:45:00+08:00)

reviewed_scope: f92bd0d7901781fa

本轮 scope 重绑定：由 `f67f9b5beab34aa9` 重绑至 `f92bd0d7901781fa`（相对 diff_anchor 的完整交付内容含新增交付文件）。监督要求把反复偶发失败的 ac009 协调类缺陷从根因修掉，不再以「已登记遗留」放过：`RuntimeCoordinator.get_last_error(profile_id, runtime=None)` 增收敛感知（`runtime_coordinator.py:238-251`），`runtime_views.make_runtime_response:46` 与 `runtime_coordinator.publish_profile_change:709` 两个读取点均传当前 runtime，GET runtime 与 SSE publish 语义一致；新增确定性红测 `tests/unit/test_runtime_coordinator_error_settle.py` 两例先红（`TypeError: unexpected keyword argument 'runtime'`）后绿；ac009 目标用例连续 5/5 通过；`p047` 已迁入 `docs/archive/pending/p047_ac009_coordination_flaky.md`（resolution=resolved，fix-ref=t037），`progress.md:77-83` 记录根因与修复。本轮无新 finding；前轮 `t037_test_f001`（minor）与 Round 1 / Round 2 结论均未回退。

- 新红测真实性独立复核：`test_runtime_coordinator_error_settle.py` 直接 `import` 真实 `RuntimeCoordinator` 并以真实构造实例化，`SimpleNamespace` 仅作 runtime 输入夹具（非 mock 被测逻辑）；断言具体非恒真（前置 `is not None`、收敛后 `is None` 且再次读取仍 `is None` 证明清空副作用持久、pending 分支 `== "Supervisor start failed (503)"`）。第二例 pending（`observed_state=stopped`、`runtime_instance_id=None`）走产品 `_is_running_converged` 为假分支返回原 error；实现若误写为「传 runtime 即无条件清空」该断言即失败，证明断言可失败、收敛分支有真实判别力。无 `.skip`/`.only`/静默错误/恒真/弱化断言。
- 未弱化既有断言：`test_ac009_supervisor_unreachable_intent_preserved_and_recovers` 第 406 行 `assert rt["last_coordinator_error"] is None` 及第 382-387 行 `found_err`/`"Supervisor" in ...` 原样保留；修复落在产品层收敛感知，非改断言求绿。改测方向复核：无「让断言迁就当前实现」的改测。
- 前轮 finding 复核：`t037_test_f001` 维持已消除；`progress.md` Round 1 处置表 3 条（`t037_code_f001`/`t037_code_f002`/`t037_test_f001`）均标「已修」，无回退；Round 1 / Round 2 的 `verdict: PASS` 与 `reviewed_scope` 行原样保留。
- 本轮新发现：0 条（critical 0 / important 0 / minor 0）
- 未解决 blocker：无
- 独立复跑：`PYTHONPATH=src/backend .scratch/gate_venv/bin/python -m pytest tests/unit/test_runtime_coordinator_error_settle.py "tests/integration/test_runtime_coordinator_integration.py::test_ac009_supervisor_unreachable_intent_preserved_and_recovers" -q` → `3 passed in 2.80s`（2 单元 + 1 integration），ac009 目标用例在本轮确定性修复后通过。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`EnvironmentListPage.test.tsx` 4 例断言 8 列表头、直连警示、geoip 随代理、五态徽标与 error 原因、运行时长/停止相对时间；本轮 scope 重绑定后前端交付未变。
- AC-002：TICK-VALID，re_verified。同文件 10 例断言 URL 五参数还原 `rowIds`、四类独立筛选、搜索写 `q`、两种排序、清除筛选、无结果空状态；交付未变。
- AC-003：TICK-VALID，re_verified。同文件 2 例断言布局写 `cbrowser.environments.layout`、刷新后仍 card、卡片字段与缩略图占位；交付未变。
- AC-004：TICK-VALID，re_verified。同文件 1 例 `setQueryData(profileKeys.runtime)` 模拟 SSE 增量，断言行状态与 `env-running-count` 实时更新；本轮核对 `publish_profile_change:709` 传 runtime 后 SSE 与 GET 语义一致，交付未变。
- AC-005：TICK-VALID，re_verified。同文件 5 例断言四类批量各 2 次调用且 `new Set(keys).size===2`、move 参数、409 失败汇总与失败项保持选中；交付未变。
- AC-006：TICK-VALID，re_verified。`ProfileForm.test.tsx` 7 例 + `ProfileCreateDialog.test.tsx` 3 例断言四分区/必填/字体集过滤/create-start 顺序，`DialogWidth.test.tsx` 断言 `max-w-dialog` 且不含 `max-w-lg`；交付未变。
- AC-007：TICK-VALID，re_verified。`ProfileDetailPage.test.tsx` 8 例断言五态文案、四 tab href、start/stop 幂等键、双 banner 与 retry；交付未变。
- AC-008：TICK-VALID，re_verified。`ConfigTab.test.tsx`（A22 `setQueryData` + `invalidateQueries` 双重后台刷新保留未保存编辑）+ `ProfileForm.test.tsx` 元数据/运行配置分类 + `useProfilesQuery.apply*` stop→start 独立键；交付未变。
- AC-009：TICK-VALID，re_verified。本轮新增 `test_runtime_coordinator_error_settle.py` 两例走真实 `RuntimeCoordinator`（收敛清空残留 error 并持久、pending 保留具体 error），产品 `get_last_error` 收敛感知 + `make_runtime_response:46`/`publish_profile_change:709` 两个读取点传 runtime，`test_ac009...:406` 的 `assert ... is None` 原样保留未弱化；本次定向 pytest 3 passed，叠加 `ProfileFilesTab`/`ProfileAutomationTab`/`MaintenanceTab`/E2E 既有覆盖；p047 已归档 resolved，非「已登记遗留」放过。
- AC-010：TICK-VALID，re_verified。`GroupManagerDialog.test.tsx` 10 例断言计数、create/rename/改色参数、拖动与键盘排序、删除确认受影响数、409 不吞；交付未变。
- AC-011：TICK-VALID，re_verified。`ProfileIsolation.test.tsx` 8 例断言动作状态隔离、每标签独立 sessionStorage target、关闭页面不 stop；交付未变。
- AC-012：TICK-VALID，re_verified。E2E `create_profile_via_ui` 走 UI、旧 5 组件/5 测试删除、`progress.md:51-58` 可复现扫描口径 32 文件 0 命中、`design_tokens.test.mjs` 3 例尺寸门禁；交付未变。

coverage = re_verified / 12

verdict: PASS

## Round 4 (2026-11-07T03:00:00+08:00)

reviewed_scope: 68587ae956c27987

本轮为 full 级最终收口，scope 由 `f92bd0d7901781fa` 重绑定至 `68587ae956c27987`（相对 diff_anchor 的完整交付内容含新增交付文件）。收口改动：ac009 协调类偶发缺陷从根因修复（`RuntimeCoordinator.get_last_error(profile_id, runtime=None)` 收敛感知）+ 确定性红测 `test_runtime_coordinator_error_settle.py`（先红 `TypeError: unexpected keyword argument 'runtime'` 后绿）+ 三个读取点统一传 `runtime=rt`（GET runtime `runtime_views.py:46`、SSE publish `runtime_coordinator.py:709`、SSE 初始快照 `router.py:112`）+ 产品接口加 `runtime` 可选参数后两个 integration 测试替身 `_StubCoordinator.get_last_error` 同步签名。本轮无新 finding；前轮唯一 minor `t037_test_f001` 维持已消除，Round 1 / 2 / 3 结论未回退。

- stub 签名同步独立复核（无断言弱化）：相对 diff_anchor 的 diff 显示 `test_api_search_defaults_routes.py:60` 与 `test_t026_transport_api.py:68` 均仅把 `def get_last_error(self, _profile_id: str):` 改为 `def get_last_error(self, _profile_id: str, runtime=None):`，`return None` 原样保留，无断言预期修改、无 `.skip`/`.only`/静默错误/弱化断言；属接口签名同步，符合 spec「测试替身随被测接口同步」，非「让断言迁就当前实现」的改测。
- 红→绿证据完整性复核：`test_runtime_coordinator_error_settle.py` 为新增文件（A 状态，54 行），两例直接 import 真实 `RuntimeCoordinator` 并以真实构造实例化，`SimpleNamespace` 仅作 runtime 输入夹具（非 mock 被测逻辑）；断言具体非恒真（前置 `is not None`、收敛后 `is None` 且再次读取仍 `is None` 证明清空副作用持久、pending 分支 `== "Supervisor start failed (503)"`）。第二例 `observed_state=stopped`/`runtime_instance_id=None` 走 `_is_running_converged` 假分支保留原 error，使「传 runtime 即无条件清空」的误实现必然失败，收敛判别力真实；红版 `TypeError` 有据（`progress.md:82`）。
- ac009 未以「已登记遗留」放过：`test_runtime_coordinator_integration.py:406` 的 `assert rt["last_coordinator_error"] is None` 与 `:382-387` 的 `found_err`/`"Supervisor" in ...` 原样保留未弱化；修复落在产品层收敛感知而非改断言求绿。`docs/archive/pending/p047_ac009_coordination_flaky.md` 归档 resolution=resolved、fix-ref=t037；`progress.md:73` 明示「本轮不记为已登记遗留、不改断言求绿」。
- 处置表与逐用例登记复核：`progress.md` Round 1 处置表 3 条（`t037_code_f001`/`t037_code_f002`/`t037_test_f001`）均标「已修」；「测试处置清单 / 二之二」旧 `ProfileDetailPage.test.tsx` 主文件 6 例逐用例去向完备。
- 前轮结论复核：Round 1 / 2 / 3 的 `verdict: PASS` 与各自 `reviewed_scope` 行（`a4588130decb7633` / `f67f9b5beab34aa9` / `f92bd0d7901781fa`）原样保留，未回退。
- 改测方向复核：无「让断言迁就当前实现」的改测；本轮仅接口签名同步与新增确定性红测。
- 本轮新发现：0 条（critical 0 / important 0 / minor 0）
- 未解决 blocker：无
- 独立复跑：`PYTHONPATH=src/backend .scratch/gate_venv/bin/python -m pytest tests/unit/test_runtime_coordinator_error_settle.py tests/integration/test_api_search_defaults_routes.py tests/integration/test_t026_transport_api.py -q` → `9 passed in 2.54s`（红测 2 例 + 两个 stub 所在 integration 文件全量），0 失败。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`EnvironmentListPage.test.tsx` 4 例断言 8 列表头、直连警示、geoip 随代理、五态徽标与 error 原因、运行时长/停止相对时间；本轮 scope 重绑定后前端交付未变。
- AC-002：TICK-VALID，re_verified。同文件 10 例断言 URL 五参数还原 `rowIds`、四类独立筛选、搜索写 `q`、两种排序、清除筛选、无结果空状态；交付未变。
- AC-003：TICK-VALID，re_verified。同文件 2 例断言布局写 `cbrowser.environments.layout`、刷新后仍 card、卡片字段与缩略图占位；交付未变。
- AC-004：TICK-VALID，re_verified。同文件 1 例 `setQueryData(profileKeys.runtime)` 模拟 SSE 增量，断言行状态与 `env-running-count` 实时更新；本轮复核 SSE 初始快照 `router.py:112` 亦传 `runtime=rt`，与 GET runtime（`runtime_views.py:46`）、SSE publish（`runtime_coordinator.py:709`）三读取点语义统一，交付未变。
- AC-005：TICK-VALID，re_verified。同文件 5 例断言四类批量各 2 次调用且 `new Set(keys).size===2`、move 参数、409 失败汇总与失败项保持选中；交付未变。
- AC-006：TICK-VALID，re_verified。`ProfileForm.test.tsx` 7 例 + `ProfileCreateDialog.test.tsx` 3 例断言四分区/必填/字体集过滤/create-start 顺序，`DialogWidth.test.tsx` 断言 `max-w-dialog` 且不含 `max-w-lg`；交付未变。
- AC-007：TICK-VALID，re_verified。`ProfileDetailPage.test.tsx` 8 例断言五态文案、四 tab href、start/stop 幂等键、双 banner 与 retry；交付未变。
- AC-008：TICK-VALID，re_verified。`ConfigTab.test.tsx`（A22 `setQueryData` + `invalidateQueries` 双重后台刷新保留未保存编辑）+ `ProfileForm.test.tsx` 元数据/运行配置分类 + `useProfilesQuery.apply*` stop→start 独立键；交付未变。
- AC-009：TICK-VALID，re_verified。最终收口：`test_runtime_coordinator_error_settle.py` 两例走真实 `RuntimeCoordinator`（收敛清空残留 error 并持久、pending 保留具体 error），产品 `get_last_error` 收敛感知 + 三读取点统一传 `runtime=rt`，`test_ac009...:406` 的 `assert ... is None` 原样保留未弱化；两个 integration stub 仅签名同步（diff 仅加 `runtime=None`）；本次定向 pytest `9 passed in 2.54s`；叠加 `ProfileFilesTab`/`ProfileAutomationTab`/`MaintenanceTab`/E2E 既有覆盖；p047 已归档 resolved，非「已登记遗留」放过。
- AC-010：TICK-VALID，re_verified。`GroupManagerDialog.test.tsx` 10 例断言计数、create/rename/改色参数、拖动与键盘排序、删除确认受影响数、409 不吞；交付未变。
- AC-011：TICK-VALID，re_verified。`ProfileIsolation.test.tsx` 8 例断言动作状态隔离、每标签独立 sessionStorage target、关闭页面不 stop；交付未变。
- AC-012：TICK-VALID，re_verified。E2E `create_profile_via_ui` 走 UI、旧 5 组件/5 测试删除、`progress.md:51-58` 可复现扫描口径 32 文件 0 命中、`design_tokens.test.mjs` 3 例尺寸门禁；交付未变。

coverage = re_verified / 12

verdict: PASS

## Round 5 (2026-11-07T03:20:00+08:00)

reviewed_scope: 2a1217ac45ea38e9

本轮为 full 级最终轮，最终 scope 由 `68587ae956c27987` 重绑定至 `2a1217ac45ea38e9`（相对 diff_anchor 的完整交付内容含新增交付文件）。相对 Round 4 的两处收口：① 第三个测试替身 `tests/unit/test_refactor_behavior_equivalence.py:353` 的 lambda `get_last_error` 同步产品接口 `runtime=None` 签名（仅接口同步、无断言改动），与既有 2 个 integration `_StubCoordinator` 合计三替身一致，消除 v7 门禁 unit 退化；② 被中止的 v6 残留 E2E 容器占用宿主端口，已按测试前缀清理（主仓部署 4 容器保留），并登记 `p048_gate_stale_e2e_container_cleanup.md` 待收尾修，最终门禁 v8 于干净环境启动。本轮无新 finding、前轮唯一 minor `t037_test_f001` 未回退；`p048` 为新增待办（门禁基础设施技术债），不属未闭环 finding。

- 三替身签名同步独立复核（无断言弱化）：产品接口 `runtime_coordinator.py:245-251` 为 `get_last_error(self, profile_id: str, runtime: Any = None)`；`test_api_search_defaults_routes.py:60` 与 `test_t026_transport_api.py:68` 的 `_StubCoordinator.get_last_error(self, _profile_id: str, runtime=None)` 均 `return None` 原样；`test_refactor_behavior_equivalence.py:353` 的 `get_last_error=lambda profile_id, runtime=None: "boom"` 仅补 `runtime=None`，返回值 `"boom"` 与 `test_runtime_view_helpers`（:359-364）的 `== "boom"` / `is None` 断言原样保留。三者均为接口签名同步，无 `.skip`/`.only`/静默错误/弱化断言，非「让断言迁就当前实现」的改测。
- 红→绿与处置表复核：`test_runtime_coordinator_error_settle.py` 两例 import 真实 `RuntimeCoordinator`、`SimpleNamespace` 仅作 runtime 数据夹具，断言具体（前置 `is not None`、收敛后 `is None` 且再次无参读取仍 `is None`、pending 分支 `== "Supervisor start failed (503)"`）；红版 `TypeError: unexpected keyword argument 'runtime'` 见 `progress.md:82`，修复后绿，收敛判别力真实。`progress.md:159-161` 处置表 3 条（`t037_code_f001`/`t037_code_f002`/`t037_test_f001`）均标「已修」，「二之二」(:132-140) 旧主文件 6 例逐用例去向完备。
- ac009 未以「已登记遗留」放过：`test_runtime_coordinator_integration.py:406` 的 `assert rt["last_coordinator_error"] is None` 与 `:382-387` 的 `found_err`/`"Supervisor" in ...` 原样保留未弱化；`docs/archive/pending/p047_ac009_coordination_flaky.md` 归档 resolution=resolved、fix-ref=t037；`progress.md:73` 明示「本轮不记为已登记遗留、不改断言求绿」。
- 前 4 轮结论复核：Round 1 / 2 / 3 / 4 结论均为 PASS，各自范围指纹行（`a4588130decb7633` / `f67f9b5beab34aa9` / `f92bd0d7901781fa` / `68587ae956c27987`）原样保留，未回退；本轮仅在文末追加，不改动前四轮任何内容。
- 改测方向复核：无「让断言迁就当前实现」的改测；本轮仅接口签名同步、环境残留清理与新待办登记。
- 本轮新发现：0 条（critical 0 / important 0 / minor 0）
- 未解决 blocker：无
- 独立复跑：`PYTHONPATH=src/backend .scratch/gate_venv/bin/python -m pytest tests/unit/test_refactor_behavior_equivalence.py tests/unit/test_runtime_coordinator_error_settle.py -q` → `16 passed in 0.14s`（`test_refactor_behavior_equivalence.py` 14 例 + 红测 2 例），0 失败。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`EnvironmentListPage.test.tsx` 4 例断言 8 列表头、直连警示、geoip 随代理、五态徽标与 error 原因、运行时长/停止相对时间；本轮最终 scope 重绑定后前端交付未变。
- AC-002：TICK-VALID，re_verified。同文件 10 例断言 URL 五参数还原 `rowIds`、四类独立筛选、搜索写 `q`、两种排序、清除筛选、无结果空状态；交付未变。
- AC-003：TICK-VALID，re_verified。同文件 2 例断言布局写 `cbrowser.environments.layout`、刷新后仍 card、卡片字段与缩略图占位；交付未变。
- AC-004：TICK-VALID，re_verified。同文件 1 例 `setQueryData(profileKeys.runtime)` 模拟 SSE 增量断言行状态与 `env-running-count` 实时更新；本轮复核三读取点（`runtime_views.py:46`/`runtime_coordinator.py:709`/`router.py:112`）均传 `runtime=rt`，交付未变。
- AC-005：TICK-VALID，re_verified。同文件 5 例断言四类批量各 2 次调用且 `new Set(keys).size===2`、move 参数、409 失败汇总与失败项保持选中；交付未变。
- AC-006：TICK-VALID，re_verified。`ProfileForm.test.tsx` 7 例 + `ProfileCreateDialog.test.tsx` 3 例断言四分区/必填/字体集过滤/create-start 顺序，`DialogWidth.test.tsx` 断言 `max-w-dialog` 且不含 `max-w-lg`；交付未变。
- AC-007：TICK-VALID，re_verified。`ProfileDetailPage.test.tsx` 8 例断言五态文案、四 tab href、start/stop 幂等键、双 banner 与 retry；交付未变。
- AC-008：TICK-VALID，re_verified。`ConfigTab.test.tsx`（A22 双重后台刷新保留未保存编辑）+ `ProfileForm.test.tsx` 元数据/运行配置分类 + `useProfilesQuery.apply*` stop→start 独立键；交付未变。
- AC-009：TICK-VALID，re_verified。`test_runtime_coordinator_error_settle.py` 两例走真实 `RuntimeCoordinator`（收敛清空残留 error 并持久、pending 保留具体 error），产品 `get_last_error` 收敛感知 + 三读取点统一传 `runtime=rt`，`test_ac009...:406` 的 `assert ... is None` 原样保留未弱化；三个测试替身仅签名同步（2 个 integration `_StubCoordinator` 与 1 个 unit lambda 均只补 `runtime=None`、返回值与断言原样）；本次定向 pytest `16 passed in 0.14s`；叠加 `ProfileFilesTab`/`ProfileAutomationTab`/`MaintenanceTab`/E2E 既有覆盖；p047 已归档 resolved，非「已登记遗留」放过。
- AC-010：TICK-VALID，re_verified。`GroupManagerDialog.test.tsx` 10 例断言计数、create/rename/改色参数、拖动与键盘排序、删除确认受影响数、409 不吞；交付未变。
- AC-011：TICK-VALID，re_verified。`ProfileIsolation.test.tsx` 8 例断言动作状态隔离、每标签独立 sessionStorage target、关闭页面不 stop；交付未变。
- AC-012：TICK-VALID，re_verified。E2E `create_profile_via_ui` 走 UI、旧 5 组件/5 测试删除、`progress.md:51-58` 可复现扫描口径 32 文件 0 命中、`design_tokens.test.mjs` 3 例尺寸门禁；本轮 v6 残留 E2E 容器已按前缀清理、v8 干净环境启动，交付未变。

coverage = re_verified / 12

verdict: PASS
