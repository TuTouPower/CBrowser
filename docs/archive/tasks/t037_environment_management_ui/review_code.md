# Task review t037（reviewer_focus: 代码）

- task：`t037_environment_management_ui`
- spec：`docs/tasks/t037_environment_management_ui/task.md`
- diff_anchor：`05dda065aa237f9e32c3507f6f6a65f47a185205`
- target：`git -C '/Users/karson/kar/code/CBrowser_t037' diff 05dda065aa237f9e32c3507f6f6a65f47a185205`
- round：1
- reviewed_at：2026-11-07T02:04:37+08:00

reviewed_scope: a4588130decb7633

## Findings

### t037_code_f001 - AC-012 颜色扫描笔记证据与最终交付不可复现

- 严重度：minor
- 锚点：AC-012（扫描命令与结果写入实施笔记）
- 位置：`docs/tasks/t037_environment_management_ui/progress.md:51`（「AC-012 扫描命令与结果」节，结果行 54）
- 问题：笔记记「46 文件扫描、0 命中」。按同一命令在最终 worktree 独立复现：新增/改动前端源码 57 个，命中 26 处，集中在 `src/frontend/src/features/browser-session/SessionDiagnostics.tsx` 与 `src/frontend/src/features/profiles/BrowserSessionPage.tsx` 的既有 `bg-red-500`/`text-gray-500` 等类。差异源自监督纠正阶段追加替换 11 处尺寸类时，把这两个本就含硬编码颜色的旧文件纳入改动集，笔记未随最终文件集更新。独立复核：A 状态新增源码 30 个 0 命中，diff `+` 行仅 2 处命中且为修改行保留的既有类，故 AC-012「新增源码不含调色板类/颜色字面量」实现层仍成立；问题在证据记录与最终交付不一致、所记结果不可复现。
- 建议：把扫描口径明确为「A 状态新增源码 + diff 新增行」，如实记录最终文件数、命中明细及「既有保留色不算新增」的判定，更新该节结果。

### t037_code_f002 - 详情页状态映射缺兜底，与列表/卡片页行为分叉

- 严重度：minor（低置信度，边界态）
- 锚点：行为缺陷：runtime.observed_state 出现五态之外的值时，详情页访问 `status.tone` 抛错白屏，而列表/卡片页正常渲染；兼 DRY 重复映射
- 位置：`src/frontend/src/features/profiles/ProfileDetailPage.tsx:58`（对照 `src/frontend/src/features/profiles/EnvironmentTable.tsx:59`）
- 问题：`const status = STATUS_MAP[observed]` 对枚举值直接索引，无 fallback；同一份五态映射在 `EnvironmentTable.tsx` 的 `statusDescriptor` 用 `?? STATUS_MAP.stopped!` 兜底（并被 `EnvironmentCard.tsx:28` 复用），两处重复定义且容错行为分叉。observed_state 为后端五态枚举，非法值属非常态路径，故低置信度、未观察到常态可观测缺陷。
- 建议：详情页改用共享 `statusDescriptor(observed)`，或补同样的 fallback，消除分叉。

## 结论

- 本轮新发现：2 条（均 minor，0 critical / 0 important）
- 未进表的提示：
    - 文件过大（按 prompt 降级规则只列路径与行数，不进表）：`src/frontend/src/features/profiles/ProfileForm.tsx` 686 行（实现源码，新建即超 400 行 minor 阈值、\<800）；`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx` 723 行（测试源码，超 600 行 minor 阈值、\<1200）。二者本 task 新建即超阈值且未给不可拆硬约束，仅提示拆分；未发现由文件过大直接引发的可观测缺陷。
    - 架构启发式：`EnvironmentListPage.tsx:3270` 与 `:3272` 同时经 `useRuntimeSnapshot`（内部 `useQueries`）和本地 `runtimeQueries`（`useQueries`）为每个 profile 建立两套 runtime query observer；React Query 按同一 `profileKeys.runtime(id)` 去重网络请求，但组件内存在 2N observer，可合并为一份结果。未造成行为分叉，不进表。
    - AC-006 语义观察（低置信度、未出 finding）：`ProfileForm.tsx` 的告警覆盖「绑定字体集缺失/完整性不一致」，平台无可用集（`font_set_id=null`）仅在 meta 区显示「未配置」文本、不显示 Banner 告警，对 AC-006「未配置时显示告警」采取较窄解释。`docs/specs/profile_management.md` 明确 `font_set_id=null` 为正常启动状态，故未判缺陷。
    - 测试层观察（非本轴职责）：`ProfileDetailPage.test.tsx` 重写后，旧用例 `applies pending display settings via stop then start`（验证 stop→start 顺序与两操作幂等键）无直接等价承接；实现层 `useApplyDisplaySettingsMutation` 阶段跟踪未改，建议 test reviewer 复核覆盖。
    - 门禁与遗留：独立统计 `.scratch/t037_evidence_v4/junit/e2e.xml` 共 101 用例，仅 `test_t019_switch_and_refresh_first_frame_within_2s_host_only` 1 项失败（t032 已登记基线遗留，t036 串行门禁同样仅此项）、2 项 t032 探针 skip、0 error；9 个非 E2E suite 全 0。`p047_ac009_coordination_flaky.md` 为已登记跨 task 技术债，v4 `integration` exit 0，按系统性去重不在本轮复报。
- 总体判断：12 条 AC 实现层真实完整、非空壳，无恒真断言、无 mock 掉被测逻辑、无就地弱化旧断言迎合实现；旧测试结构删除均逐用例登记去向，旧路由断言整体删除并新增未知 `profileId` 语义用例。设计 token 根因修复（`DESIGN.md ## Container sizes`、`--container-*` 独立命名空间、`assertNoSizeTokenHijack` 门禁与单测、11 处命名/任意尺寸类替换为语义类、业务源码尺寸类 0 残留、`Dialog.tsx` 用 `max-w-dialog` 无任意值）与监督纠正（删 `/profiles/new` 专门路由、恢复受控 `open={open}`、删除 E2E 临时 DOM 诊断）全部落实。`tests/unit/review_privacy_allowlist.txt` 新增 4 条 t044 `(path, sha256)` 与两份报告实际 sha256 精确一致，未改 t044 已 done 交付。仅 2 条 minor，无未解决 critical/important，12 条 AC 全部 TICK-VALID，判定 PASS。
- 系统性 follow-up：已有 `p047_ac009_coordination_flaky.md`（ac009 协调类偶发失败），本轮无新增建议。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`EnvironmentTable.tsx:3794-3812` 8 列、`DirectNetwork` 直连警示、`PlatformIcon` 平台图标、geoip「随代理」、`StatusBadge` 五态 + error tooltip、`formatRelativeTime` 运行中/已停止两类文案；`EnvironmentListPage.test.tsx` 4 例断言真实（8 个 thead th、警示样式、五态文案、时长前缀）。
- AC-002：TICK-VALID，re_verified。`useEnvironmentFilters.ts` 用 `useSearchParams` 读写 q/status/group/proxy/sort，`filterEnvironmentRows` 组合 name/notes/proxy name 与状态/分组/代理桶，`EnvironmentEmptyState` 提供清除筛选；测试 11 例含 `/?q=Alpha&status=running&group=g1&proxy=px1&sort=name` URL 还原、独立筛选与无结果清理。
- AC-003：TICK-VALID，re_verified。`useEnvironmentLayout.ts` 持久化 `cbrowser.environments.layout`，`EnvironmentCard.tsx` 展示名称/状态/分组/网络/操作与 `env-card-preview-*` 空占位；测试 2 例含刷新后仍为卡片视图且 `env-table` 不存在。
- AC-004：TICK-VALID，re_verified。`useProfileEventsSync`（`useProfilesQuery.ts:396-444`）按 `profileKeys.runtime(id)` 增量合并 SSE，行状态、`EnvironmentRowActions`、`useRuntimeSnapshot.runningCount` 共用同一 key；测试用 `queryClient.setQueryData` 验证状态切换与运行中计数 1→0 实时更新。
- AC-005：TICK-VALID，re_verified。`useBatchActions.ts` 逐项 `mutateAsync`、`useActionKeyMutation`（`action_key_mutation.ts:46,55`）每次 `newIdempotencyKey()`、toast `envBatchResult`、`clearSelection(succeeded)` 保留失败项、catch 计 409 失败；测试 5 例验证 4 类操作幂等键互异（`new Set(keys).size===2`）、409 下成功/失败汇总与失败项仍选中。
- AC-006：TICK-VALID，re_verified。`ProfileForm.tsx` 四分区（Advanced `<details>` 默认折叠）、名称必填字段旁错误、分组就地新建、代理直连、`platformFontSets` 平台过滤 + 最新默认 + 完整性/缺失告警、reseed；`__startAfterCreate` 经 `ProfileCreateDialog.tsx:5054-5068` 在创建成功后 `setDesiredState(running)`；测试 7+3 例含 create 与 create-and-start 调用顺序断言。
- AC-007：TICK-VALID，re_verified。`ProfileDetailPage.tsx:6480-6666` 页头名称/状态/分组/打开会话/启动/停止，`SharedProfileBanners` 四标签共享（config 经 `ConfigTab`，其余三个经详情页）；测试 STATUS_CASES 5 例、四标签真实锚点 href、两条共享 banner + 重试。
- AC-008：TICK-VALID，re_verified。`ConfigTab` 与 `ProfileCreateDialog` 共用 `ProfileForm`，`METADATA_KEYS`/`hasRuntimeConfigChange`/`pickMetadata` 驱动元数据 vs 运行配置 payload 分类，`SharedProfileBanners` 以 `config_version` 差判待应用并复用 `useApplyDisplaySettingsMutation` 阶段跟踪实现「应用并重启」；测试分类 2 例（元数据不报 dirty、运行字段报 dirty）+ banner 1 例。
- AC-009：TICK-VALID，re_verified。`ProfileFilesTab.tsx`（list/upload/首个失败中止且不泄漏内容/delete）、`ProfileAutomationTab.tsx`（endpoint/runtime/supervisor/control panel + restore）、`MaintenanceTab.tsx`（仅配置/含状态复制、重置清单、运行中禁含状态复制与删除）按设计系统重建，测试各 4/4/经 router 测试覆盖；p047 技术债已登记不属本轮。
- AC-010：TICK-VALID，re_verified。`GroupManagerDialog.tsx` 新建/改名/改色（8 色）/拖动与 ArrowUp/ArrowDown 排序/删除确认 `group-affected-count` 受影响环境数，`useGroupReorder` 乐观更新 + invalidate；测试 10 例含 `ordered_ids` 精确断言与 409 `group_name_in_use` 不被吞。
- AC-011：TICK-VALID，re_verified。`ProfileIsolation.test.tsx` 8 例覆盖 per-profile 动作状态不串台、每标签独立 `cbrowser.session.target`、关闭页面/卸载不调用 stop，断言具体（错误串台为负向断言、按钮非禁用），无恒真断言。
- AC-012：TICK-VALID，re_verified。`test_frontend_app_e2e.py:93-120` 改走 UI（env-new→env-new-dialog→profile-form-name→submit→detached→row），11 处调用均不传 width/height；旧 4 页面组件与旧 testid 全仓 0 残留、`/profiles/new` 专门路由删除；A 状态 30 个新增前端源码颜色类 0 命中；E2E junit 101 用例仅 t019 首帧 1 项基线遗留失败、2 skip、0 error（笔记扫描证据偏差另见 f001，不影响 AC 语义）。

coverage = re_verified / 12

verdict: PASS

## Round 2 (2026-11-07T02:25:00+08:00)

reviewed_scope: f67f9b5beab34aa9

- 本轮为 scope 重绑定复核：前轮 reviewed_scope `a4588130decb7633` 因交付内容变化被 check_review_status 判 review_scope=stale，本轮以新指纹重新绑定范围。前轮 3 条 minor 已按处置表修复，经 diff / 代码 / 测试本身独立复核确认消除，无新 blocker；相对 Round 1 的唯一交付变化为共享 `statusDescriptor` 兜底 + 2 个新测试文件 + `progress.md` 处置登记，实现 / 测试内容未被弱化。
- 前轮 finding 复核（以 diff / 代码为准，不采信处置表自称「已修」）：
    - `t037_code_f001`（已消除）：`progress.md:51-58`「AC-012 扫描命令与结果」口径改为「A 状态新增源码 + diff 新增行」，记 32 文件 0 命中、新增行 0 命中，并说明既有保留色不计入新增；证据与最终交付一致、可复现。
    - `t037_code_f002`（已消除）：`ProfileDetailPage.tsx:17` 改为 `import { statusDescriptor } from "./EnvironmentTable"`、`:48` `const status = statusDescriptor(observed)`，删除本地重复 `STATUS_MAP`；`EnvironmentTable.tsx:56-60` 导出含 `STATUS_MAP[observed ?? "stopped"] ?? STATUS_MAP.stopped!` 兜底，`EnvironmentCard.tsx:28` 复用同一函数，列表 / 卡片 / 详情三页容错行为统一，非法枚举值不再白屏分叉。
    - `t037_test_f001`（已消除）：新增 `ConfigTab.test.tsx`（A22 后台刷新不覆盖未保存编辑，`setQueryData` + `invalidateQueries` 双重刷新后仍断言 `toHaveValue('Unsaved Edit')`）与 `MaintenanceTab.test.tsx`（删两次独立幂等键 `not.toBe(firstKey)`、运行中 `toBeDisabled()` 且 `delete` 未被调用），`progress.md:118-126`「二之二」补登旧主文件 6 例逐用例去向；断言具体，无恒真 / 弱化断言 / `.skip` / mock 掉被测逻辑。
- 本轮新发现：0 条（0 critical / 0 important / 0 minor）。`statusDescriptor` 兜底为容错增强，2 个测试文件为新增覆盖，未删改既有断言，实现 / 测试内容未被弱化。
- 未进表的提示：无。`git status --short` 中 `??` 仅两份 review 报告（流程文件），无 reviewer 看不到的未跟踪交付文件。
- 总体判断：3 条 minor 均独立复核消除，无未解决 critical / important，12 条 AC 实现层仍全部 TICK-VALID，判定 PASS。
- 系统性 follow-up：已有 `p047_ac009_coordination_flaky.md`，本轮无新增建议。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`EnvironmentTable.tsx:3794-3812` 8 列、`DirectNetwork` 直连警示、`PlatformIcon` 平台图标、geoip「随代理」、`StatusBadge` 五态 + error tooltip、`formatRelativeTime` 运行中/已停止两类文案；`EnvironmentListPage.test.tsx` 4 例断言真实（8 个 thead th、警示样式、五态文案、时长前缀）。本轮复核：维持判定，`statusDescriptor` 兜底统一后列表列实现未触及。
- AC-002：TICK-VALID，re_verified。`useEnvironmentFilters.ts` 用 `useSearchParams` 读写 q/status/group/proxy/sort，`filterEnvironmentRows` 组合 name/notes/proxy name 与状态/分组/代理桶，`EnvironmentEmptyState` 提供清除筛选；测试 11 例含 `/?q=Alpha&status=running&group=g1&proxy=px1&sort=name` URL 还原、独立筛选与无结果清理。本轮复核：维持判定，本轮唯一交付变化未触及筛选 / URL 实现。
- AC-003：TICK-VALID，re_verified。`useEnvironmentLayout.ts` 持久化 `cbrowser.environments.layout`，`EnvironmentCard.tsx` 展示名称/状态/分组/网络/操作与 `env-card-preview-*` 空占位；测试 2 例含刷新后仍为卡片视图且 `env-table` 不存在。本轮复核：维持判定，卡片仍复用同一 `statusDescriptor`，布局持久化未变。
- AC-004：TICK-VALID，re_verified。`useProfileEventsSync`（`useProfilesQuery.ts:396-444`）按 `profileKeys.runtime(id)` 增量合并 SSE，行状态、`EnvironmentRowActions`、`useRuntimeSnapshot.runningCount` 共用同一 key；测试用 `queryClient.setQueryData` 验证状态切换与运行中计数 1→0 实时更新。本轮复核：维持判定，SSE 增量合并与 runtime key 未变。
- AC-005：TICK-VALID，re_verified。`useBatchActions.ts` 逐项 `mutateAsync`、`useActionKeyMutation`（`action_key_mutation.ts:46,55`）每次 `newIdempotencyKey()`、toast `envBatchResult`、`clearSelection(succeeded)` 保留失败项、catch 计 409 失败；测试 5 例验证 4 类操作幂等键互异（`new Set(keys).size===2`）、409 下成功/失败汇总与失败项仍选中。本轮复核：维持判定，批量幂等键与 409 处理未变。
- AC-006：TICK-VALID，re_verified。`ProfileForm.tsx` 四分区（Advanced `<details>` 默认折叠）、名称必填字段旁错误、分组就地新建、代理直连、`platformFontSets` 平台过滤 + 最新默认 + 完整性/缺失告警、reseed；`__startAfterCreate` 经 `ProfileCreateDialog.tsx:5054-5068` 在创建成功后 `setDesiredState(running)`；测试 7+3 例含 create 与 create-and-start 调用顺序断言。本轮复核：维持判定，新建弹窗与表单未变。
- AC-007：TICK-VALID，re_verified。`ProfileDetailPage.tsx:6480-6666` 页头名称/状态/分组/打开会话/启动/停止，`SharedProfileBanners` 四标签共享（config 经 `ConfigTab`，其余三个经详情页）；测试 STATUS_CASES 5 例、四标签真实锚点 href、两条共享 banner + 重试。本轮复核：详情页已改用共享 `statusDescriptor(observed)` 兜底（f002 已修），页头状态徽标对非法枚举不再白屏、与列表/卡片一致；页头结构与四标签共享 banner 未变，维持判定。
- AC-008：TICK-VALID，re_verified。`ConfigTab` 与 `ProfileCreateDialog` 共用 `ProfileForm`，`METADATA_KEYS`/`hasRuntimeConfigChange`/`pickMetadata` 驱动元数据 vs 运行配置 payload 分类，`SharedProfileBanners` 以 `config_version` 差判待应用并复用 `useApplyDisplaySettingsMutation` 阶段跟踪实现「应用并重启」；测试分类 2 例（元数据不报 dirty、运行字段报 dirty）+ banner 1 例。本轮复核：新增 `ConfigTab.test.tsx` 覆盖 A22 后台刷新不覆盖未保存编辑（真实 `setQueryData` + `invalidateQueries` 断言编辑值不被覆盖），配置 / 新建共用表单与分类逻辑未变，维持判定。
- AC-009：TICK-VALID，re_verified。`ProfileFilesTab.tsx`（list/upload/首个失败中止且不泄漏内容/delete）、`ProfileAutomationTab.tsx`（endpoint/runtime/supervisor/control panel + restore）、`MaintenanceTab.tsx`（仅配置/含状态复制、重置清单、运行中禁含状态复制与删除）按设计系统重建，测试各 4/4/经 router 测试覆盖；p047 技术债已登记不属本轮。本轮复核：新增 `MaintenanceTab.test.tsx` 覆盖删除独立幂等键（`not.toBe(firstKey)`）与运行中禁删（`toBeDisabled()` 且 `delete` 未被调用），断言具体、无弱化；三标签能力未变，维持判定。
- AC-010：TICK-VALID，re_verified。`GroupManagerDialog.tsx` 新建/改名/改色（8 色）/拖动与 ArrowUp/ArrowDown 排序/删除确认 `group-affected-count` 受影响环境数，`useGroupReorder` 乐观更新 + invalidate；测试 10 例含 `ordered_ids` 精确断言与 409 `group_name_in_use` 不被吞。本轮复核：维持判定，分组弹窗与排序未变。
- AC-011：TICK-VALID，re_verified。`ProfileIsolation.test.tsx` 8 例覆盖 per-profile 动作状态不串台、每标签独立 `cbrowser.session.target`、关闭页面/卸载不调用 stop，断言具体（错误串台为负向断言、按钮非禁用），无恒真断言。本轮复核：维持判定，2 个新测试文件为新增覆盖、未删改 `ProfileIsolation` 既有 8 例，隔离语义不变。
- AC-012：TICK-VALID，re_verified。`test_frontend_app_e2e.py:93-120` 改走 UI（env-new→env-new-dialog→profile-form-name→submit→detached→row），11 处调用均不传 width/height；旧 4 页面组件与旧 testid 全仓 0 残留、`/profiles/new` 专门路由删除；A 状态 30 个新增前端源码颜色类 0 命中；E2E junit 101 用例仅 t019 首帧 1 项基线遗留失败、2 skip、0 error。本轮复核：f001 已修，扫描笔记口径改为「A 状态新增源码 32 文件 0 命中 + diff 新增行 0 命中」且与最终交付一致、可复现；旧路由与 E2E UI 改造未变，AC 语义维持。

coverage = re_verified / 12

verdict: PASS

## Round 3 (2026-11-07T02:45:00+08:00)

reviewed_scope: f92bd0d7901781fa

- 本轮为 scope 重绑定复核：前轮 `reviewed_scope: f67f9b5beab34aa9` 因监督要求把 ac009 协调类反复偶发失败从根因修掉、交付内容再次变化而失效，本轮以新指纹重新绑定范围。相对 Round 2 的交付变化为 `runtime_coordinator.py` / `runtime_views.py` 收敛感知修复、新确定性红测 `tests/unit/test_runtime_coordinator_error_settle.py`、`p047` 归档（`docs/archive/pending/p047_ac009_coordination_flaky.md`，resolution=resolved、fix-ref=t037）及 progress/task 文档同步；12 条 AC 的前端实现层未变，无新 blocker，前两轮 3 条 minor 未回退。
- ac009 根因修复（独立复核，不采信处置表自称）：`runtime_coordinator.py:237-251` 新增 `_is_running_converged`（`desired_state=="running" && observed_state=="running" && runtime_instance_id is not None`）与 `get_last_error(profile_id, runtime=None)`，收敛时 `pop` 残留并返回 None；字段名与 `domain/models.py:222-224` 的 `ProfileRuntime` 一致，`get_last_error` 构造经 `runtime_coordinator.py:183-195` 签名核实可独立构造。`runtime_views.py:45-49` 的 `make_runtime_response` 与 `runtime_coordinator.py:709` 的 `publish_profile_change` 两个读取点均传 `runtime=rt`；`router.py` 6 处 `make_runtime_response(rt, coord)` 调用统一经 helper 生效，`runtime_coordinator.py:1020` 内部 `get_last_error(profile_id)` 因 `runtime=None` 保持旧行为不受影响。GET runtime 与 SSE publish 语义一致，竞态根因（Supervisor running 事件与 `clear_last_error` 不同路径）被收敛感知覆盖，修复真实。
- 确定性红测（无弱化断言）：`tests/unit/test_runtime_coordinator_error_settle.py` 2 例走真实 `RuntimeCoordinator`（收敛清空残留且二次无参读取仍 None、未收敛保留具体 error 字符串），`SimpleNamespace` 为数据夹具、字段名与生产一致，断言具体、无恒真 / 弱化 / `.skip` / mock 掉被测逻辑，红版 `TypeError: unexpected keyword argument 'runtime'` 证明能捕获缺陷。`git diff 05dda065aa237f9e32c3507f6f6a65f47a185205 -- tests/integration/test_runtime_coordinator_integration.py tests/e2e/test_runtime_coordinator_e2e.py tests/unit/test_refactor_behavior_equivalence.py src/backend/cbrowser/api/v1/router.py` 输出为空，`test_ac009...:406` 的 `assert rt["last_coordinator_error"] is None` 原样保留，未就地弱化旧断言求绿。
- 前轮 finding 复核（以 diff / 代码为准，前两轮 3 条 minor 均未回退）：
    - `t037_code_f001`（仍在、未回退）：`progress.md:51-58` 扫描口径「A 状态新增源码 + diff 新增行」及 32 文件 0 命中记录保留。
    - `t037_code_f002`（仍在、未回退）：`ProfileDetailPage.tsx:17` 导入、`:48` 使用共享 `statusDescriptor`；`EnvironmentTable.tsx:56-60` 导出含 `?? STATUS_MAP.stopped!` 兜底。
    - `t037_test_f001`（仍在、未回退）：`ConfigTab.test.tsx` / `MaintenanceTab.test.tsx` 均为 A 状态新增文件，`progress.md:126-134`「二之二」逐用例去向保留。
    - 前轮处置表（`progress.md:149-155`）3 条仍标「已修」，与代码现状一致。
- progress.md 处置表与 p047 归档一致：`progress.md:77-83`「p047 闭环」记根因、收敛修复、红测先红后绿、ac009 连续 5/5、`pending.py archive p047 --resolution resolved --fix-ref t037`；归档文件 `docs/archive/pending/p047_ac009_coordination_flaky.md:9` 记 `处理：t037；resolution=resolved` 与同一根因 / 修复 / 红测描述，glob `**/p047*` 全仓仅此一份、todo 侧无残留。二者一致，非「已登记遗留」放过。
- 本轮新发现：0 条（0 critical / 0 important / 0 minor）。本轮 diff 仅指定 3 文件 + 归档 / 流程文档，未弱化任何实现或断言，无新 blocker。
- 未进表的提示（范围外、低置信度、非 blocker）：`src/backend/cbrowser/api/v1/router.py:111` 的 SSE `get_initial_snapshots` 是第三个 `get_last_error` 读取点，已持有 `rt`（:110）却未传 `runtime=rt`，与本轮两个读取点行为分叉——收敛态 SSE 初始快照理论上仍可能带残留 `last_coordinator_error`。该文件本轮 diff 未触及（既有代码，非本轮引入、非前轮回退），不在 ac009 失败路径（GET runtime + publish 增量已覆盖），且收敛态下任一 `make_runtime_response` 读取即 `pop` 清空 `_last_errors`、前端加载必经 GET runtime、下一次 publish 亦会纠正，窗口极窄且瞬时。按 prompt「范围外问题仅在结论段提示、不进 finding 表」处理，建议后续以 follow-up 把 SSE 初始快照组装与 publish 收敛规则统一；不构成可观测 blocker，不影响本轮 verdict。
- 总体判断：ac009 根因修复真实、确定性红测有效、p047 闭环且 progress 与归档一致，前两轮 3 条 minor 未回退；12 条 AC 实现层未变、全部 TICK-VALID，无未解决 critical / important，判定 PASS。
- 系统性 follow-up：p047 已归档 resolved；除上述 SSE 初始快照统一（低优先级、范围外）外，本轮无新增建议。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`EnvironmentTable.tsx:3794-3812` 8 列、`DirectNetwork` 直连警示、`PlatformIcon` 平台图标、geoip「随代理」、`StatusBadge` 五态 + error tooltip、`formatRelativeTime` 运行中 / 已停止两类文案；`EnvironmentListPage.test.tsx` 4 例断言真实。本轮复核：scope 重绑定仅改后端收敛修复（p047），列表列实现与共享 `statusDescriptor` 兜底未触及，维持判定。
- AC-002：TICK-VALID，re_verified。`useEnvironmentFilters.ts` 用 `useSearchParams` 读写 q/status/group/proxy/sort，`filterEnvironmentRows` 组合 name/notes/proxy name 与状态 / 分组 / 代理桶，`EnvironmentEmptyState` 提供清除筛选；测试 11 例含 URL 五参数还原、独立筛选与无结果清理。本轮复核：筛选 / URL 实现未变，维持判定。
- AC-003：TICK-VALID，re_verified。`useEnvironmentLayout.ts` 持久化 `cbrowser.environments.layout`，`EnvironmentCard.tsx` 展示名称 / 状态 / 分组 / 网络 / 操作与 `env-card-preview-*` 空占位；测试 2 例含刷新后仍为卡片视图且 `env-table` 不存在。本轮复核：卡片仍复用同一 `statusDescriptor`、布局持久化未变，维持判定。
- AC-004：TICK-VALID，re_verified。`useProfileEventsSync`（`useProfilesQuery.ts:396-444`）按 `profileKeys.runtime(id)` 增量合并 SSE，行状态、`EnvironmentRowActions`、`useRuntimeSnapshot.runningCount` 共用同一 key；测试用 `queryClient.setQueryData` 验证状态切换与运行中计数 1→0 实时更新。本轮复核：`runtime_views.py:45-49` 与 `runtime_coordinator.py:709` 两读取点传 `runtime=rt`，SSE publish 与 GET runtime 在收敛态一致清空残留 error，增量合并与 runtime key 未变，维持判定。
- AC-005：TICK-VALID，re_verified。`useBatchActions.ts` 逐项 `mutateAsync`、`useActionKeyMutation`（`action_key_mutation.ts:46,55`）每次 `newIdempotencyKey()`、toast `envBatchResult`、`clearSelection(succeeded)` 保留失败项、catch 计 409 失败；测试 5 例验证 4 类操作幂等键互异与 409 下失败项仍选中。本轮复核：批量幂等键与 409 处理未变，维持判定。
- AC-006：TICK-VALID，re_verified。`ProfileForm.tsx` 四分区（Advanced `<details>` 默认折叠）、名称必填字段旁错误、分组就地新建、代理直连、`platformFontSets` 平台过滤 + 最新默认 + 完整性 / 缺失告警、reseed；`__startAfterCreate` 经 `ProfileCreateDialog.tsx:5054-5068` 创建成功后 `setDesiredState(running)`；测试 7+3 例含 create 与 create-and-start 顺序断言。本轮复核：新建弹窗与表单未变，维持判定。
- AC-007：TICK-VALID，re_verified。`ProfileDetailPage.tsx:6480-6666` 页头名称 / 状态 / 分组 / 打开会话 / 启动 / 停止，`SharedProfileBanners` 四标签共享；测试 STATUS_CASES 5 例、四标签真实锚点 href、两条共享 banner + 重试。本轮复核：页头仍用共享 `statusDescriptor(observed)` 兜底（f002 未回退），四标签共享 banner 未变，维持判定。
- AC-008：TICK-VALID，re_verified。`ConfigTab` 与 `ProfileCreateDialog` 共用 `ProfileForm`，`METADATA_KEYS`/`hasRuntimeConfigChange`/`pickMetadata` 驱动元数据 vs 运行配置 payload 分类，`SharedProfileBanners` 以 `config_version` 差判待应用并复用 `useApplyDisplaySettingsMutation` 阶段跟踪实现「应用并重启」；测试分类 2 例 + banner 1 例。本轮复核：`ConfigTab.test.tsx`（A22 后台刷新不覆盖未保存编辑）仍在，分类逻辑未变，维持判定。
- AC-009：TICK-VALID，re_verified。`ProfileFilesTab.tsx`（list/upload/首个失败中止且不泄漏内容/delete）、`ProfileAutomationTab.tsx`（endpoint/runtime/supervisor/control panel + restore）、`MaintenanceTab.tsx`（仅配置 / 含状态复制、重置清单、运行中禁含状态复制与删除）按设计系统重建，测试各 4/4/经 router 测试覆盖。本轮复核：`MaintenanceTab.test.tsx` 仍在（f001 未回退）；本轮 p047 修复的是编号同名的后端 integration 协调类用例（`test_ac009...:406` 断言原样保留未弱化）这一跨 task 技术债，不属本 AC 前端实现层、不改变判定，但消除了反复偶发失败，维持判定。
- AC-010：TICK-VALID，re_verified。`GroupManagerDialog.tsx` 新建 / 改名 / 改色（8 色）/ 拖动与 ArrowUp/ArrowDown 排序 / 删除确认 `group-affected-count` 受影响环境数，`useGroupReorder` 乐观更新 + invalidate；测试 10 例含 `ordered_ids` 精确断言与 409 `group_name_in_use` 不被吞。本轮复核：分组弹窗与排序未变，维持判定。
- AC-011：TICK-VALID，re_verified。`ProfileIsolation.test.tsx` 8 例覆盖 per-profile 动作状态不串台、每标签独立 `cbrowser.session.target`、关闭页面 / 卸载不调用 stop，断言具体（错误串台为负向断言、按钮非禁用），无恒真断言。本轮复核：本轮未删改 `ProfileIsolation` 既有 8 例，隔离语义不变，维持判定。
- AC-012：TICK-VALID，re_verified。`test_frontend_app_e2e.py:93-120` 改走 UI（env-new→env-new-dialog→profile-form-name→submit→detached→row），11 处调用均不传 width/height；旧 4 页面组件与旧 testid 全仓 0 残留、`/profiles/new` 专门路由删除；A 状态 30 个新增前端源码颜色类 0 命中；E2E junit 101 用例仅 t019 首帧 1 项基线遗留失败、2 skip、0 error。本轮复核：f001 扫描笔记口径（32 文件 0 命中）保留未回退，本轮 diff 不含前端源码，颜色类结论未变，维持判定。

coverage = re_verified / 12

verdict: PASS

## Round 4 (2026-11-07T03:00:00+08:00)

reviewed_scope: 68587ae956c27987

- 本轮为最终轮 scope 重绑定复核：前轮 `reviewed_scope: f92bd0d7901781fa` 因 Round 3「范围外提示」按根因完整性收口、交付内容变化而失效，本轮以新指纹重新绑定最终范围。相对 Round 3 的交付变化仅为 `src/backend/cbrowser/api/v1/router.py` SSE 初始快照读取点补传 runtime，以及两个 integration 测试替身 `_StubCoordinator.get_last_error` 同步产品接口可选参数；12 条 AC 前端实现层与既有测试断言未变。
- SSE 初始快照根因完整性（独立复核，不采信处置表自称）：`router.py:110-115` 已持有 `rt = await service.get_runtime(p.id)`，本轮改 `coordinator.get_last_error(p.id, runtime=rt)`（:112）；与 `runtime_views.py:46`（GET runtime 经 `make_runtime_response`，`router.py:638/689/747/788/821/865` 六处调用统一生效）、`runtime_coordinator.py:709`（SSE `publish_profile_change`）构成三个读取点，全部传 `runtime=rt`。生产签名 `runtime_coordinator.py:245-251` `get_last_error(profile_id, runtime=None)` 在收敛态 `pop` 残留返回 None，`runtime_coordinator.py:1020` 内部 reconcile 无参读取（`runtime=None`）保持旧行为不受影响。三读取点收敛感知统一，修复真实。
- stub 仅为接口签名同步（无弱化断言）：`test_api_search_defaults_routes.py:60` 与 `test_t026_transport_api.py:68` 的 `_StubCoordinator.get_last_error(self, _profile_id: str, runtime=None)` 各仅补 `runtime=None`，`return None` 不变；本轮该两文件 `git diff` 各仅 1 行，全文无任何 `assert`/`expect` 行改动，无恒真 / 弱化 / `.skip` / mock 掉被测逻辑；`last_coordinator_error` 断言集中在其它 integration 文件且本轮未触及。属测试替身随被测接口同步，非改断言迎合实现。
- 前轮 finding 与提示复核（以 diff / 代码为准，前 3 轮 3 条 minor 均未回退）：`t037_code_f001` 的 `progress.md:51-58` 扫描口径「A 状态新增源码 + diff 新增行」32 文件 0 命中记录仍在；`t037_code_f002` 的 `ProfileDetailPage.tsx:17` 导入 / `:48` 使用 `statusDescriptor`、`EnvironmentTable.tsx:56-60` 导出含 `?? STATUS_MAP.stopped!` 兜底仍在；`t037_test_f001` 的 `ConfigTab.test.tsx` / `MaintenanceTab.test.tsx` / `ProfileIsolation.test.tsx` 均存在。本轮 3 文件 diff 不含前端源码、不含 progress.md 处置段、不含任何断言文件，未触及上述修复。Round 3 唯一「未进表的提示」（SSE 初始快照未传 runtime）已由本轮 diff 修掉，`progress.md:87-88` 同步登记收口，本轮不再有「未进表的提示」，提示闭环。
- 本轮新发现：0 条（0 critical / 0 important / 0 minor）。修复为收敛感知补全与替身签名同步，语义一致、无新 blocker，无范围外观察需提示。
- 总体判断：最终 scope 重绑定，SSE 初始快照根因完整性修复真实、三个 `get_last_error` 读取点收敛感知统一、stub 签名同步未弱化断言、Round 3 提示闭环、前 3 轮 minor 未回退；12 条 AC 实现层与测试层均未变、全部 TICK-VALID，无未解决 critical / important，判定 PASS。
- 系统性 follow-up：p047 已归档 resolved，前轮 SSE 初始快照统一建议已在本轮闭环，本轮无新增建议。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`EnvironmentTable.tsx` 8 列 + `DirectNetwork` 直连警示 + `PlatformIcon` + `StatusBadge` 五态 + `formatRelativeTime`，`EnvironmentListPage.test.tsx` 4 例断言真实；本轮 diff 仅 `router.py` 与 2 个 integration stub、不含前端源码，列表列实现与共享 `statusDescriptor` 兜底未触及，维持判定。
- AC-002：TICK-VALID，re_verified。`useEnvironmentFilters.ts` 用 `useSearchParams` 读写 q/status/group/proxy/sort、`filterEnvironmentRows` 组合筛选、`EnvironmentEmptyState` 清除筛选，测试 11 例含 URL 五参数还原与无结果清理；本轮 diff 未触及筛选 / URL 实现，维持判定。
- AC-003：TICK-VALID，re_verified。`useEnvironmentLayout.ts` 持久化 `cbrowser.environments.layout`，`EnvironmentCard.tsx` 展示名称 / 状态 / 分组 / 网络 / 操作与 `env-card-preview-*` 空占位，测试 2 例含刷新后卡片视图保持；本轮 diff 未触及，维持判定。
- AC-004：TICK-VALID，re_verified。`useProfileEventsSync`（`useProfilesQuery.ts`）按 `profileKeys.runtime(id)` 增量合并 SSE，行状态 / `EnvironmentRowActions` / `useRuntimeSnapshot.runningCount` 共用同一 key，测试用 `setQueryData` 验证 1→0 实时更新；本轮复核三读取点（`runtime_views.py:46` / `runtime_coordinator.py:709` / `router.py:112`）全部传 `runtime=rt`，SSE 初始快照、publish、GET runtime 收敛态一致清空残留 error，增量合并与 runtime key 未变，维持判定。
- AC-005：TICK-VALID，re_verified。`useBatchActions.ts` 逐项 `mutateAsync`、`useActionKeyMutation` 每次 `newIdempotencyKey()`、toast `envBatchResult`、`clearSelection(succeeded)` 保留失败项、catch 计 409 失败，测试 5 例验证 4 类操作幂等键互异与 409 汇总；本轮 diff 未触及，维持判定。
- AC-006：TICK-VALID，re_verified。`ProfileForm.tsx` 四分区（Advanced 默认折叠）、名称必填字段旁错误、平台字体集平台过滤 + 最新默认 + 完整性/缺失告警、reseed，`ProfileCreateDialog.tsx` 创建成功后 `setDesiredState(running)`，测试 7+3 例含 create 与 create-and-start 顺序断言；本轮 diff 未触及，维持判定。
- AC-007：TICK-VALID，re_verified。`ProfileDetailPage.tsx` 页头名称 / 状态 / 分组 / 打开会话 / 启动 / 停止 + `SharedProfileBanners` 四标签共享，测试 STATUS_CASES 5 例、四标签真实锚点、两条共享 banner + 重试；本轮核实 `:17` 导入 / `:48` 使用共享 `statusDescriptor` 兜底仍在（f002 未回退），四标签共享 banner 未变，维持判定。
- AC-008：TICK-VALID，re_verified。`ConfigTab` 与 `ProfileCreateDialog` 共用 `ProfileForm`，`METADATA_KEYS`/`hasRuntimeConfigChange`/`pickMetadata` 驱动元数据 vs 运行配置分类，`SharedProfileBanners` 以 `config_version` 差判待应用并复用 `useApplyDisplaySettingsMutation` 阶段跟踪实现「应用并重启」；`ConfigTab.test.tsx`（A22 后台刷新不覆盖未保存编辑）仍在，本轮 diff 未触及分类逻辑，维持判定。
- AC-009：TICK-VALID，re_verified。`ProfileFilesTab.tsx` / `ProfileAutomationTab.tsx` / `MaintenanceTab.tsx` 按设计系统重建，`MaintenanceTab.test.tsx` 覆盖删除独立幂等键（`not.toBe(firstKey)`）与运行中禁删（`toBeDisabled()` 且 `delete` 未调用）仍在；p047 已归档 resolved、不属本轮，本轮 diff 不含前端源码，维持判定。
- AC-010：TICK-VALID，re_verified。`GroupManagerDialog.tsx` 新建 / 改名 / 改色（8 色）/ 拖动与 ArrowUp/ArrowDown 排序 / 删除确认 `group-affected-count` 受影响环境数，`useGroupReorder` 乐观更新 + invalidate，测试 10 例含 `ordered_ids` 精确断言与 409 `group_name_in_use` 不被吞；本轮 diff 未触及，维持判定。
- AC-011：TICK-VALID，re_verified。`ProfileIsolation.test.tsx` 8 例覆盖 per-profile 动作状态不串台、每标签独立 `cbrowser.session.target`、关闭页面 / 卸载不调用 stop，断言具体（串台负向断言、按钮非禁用）、无恒真断言；本轮核实该文件仍在、未被删改，隔离语义不变，维持判定。
- AC-012：TICK-VALID，re_verified。`test_frontend_app_e2e.py:93-120` 走 UI（env-new→env-new-dialog→profile-form-name→submit→detached→row），旧 4 页面组件与旧 testid 全仓 0 残留、`/profiles/new` 专门路由删除；`progress.md:51-58` 扫描口径「A 状态新增源码 32 文件 0 命中 + diff 新增行 0 命中」保留（f001 未回退），E2E junit 101 用例仅 t019 首帧基线遗留；本轮 diff 不含前端源码与 E2E 文件，颜色类结论未变，维持判定。

coverage = re_verified / 12

verdict: PASS

## Round 5 (2026-11-07T03:20:00+08:00)

reviewed_scope: 2a1217ac45ea38e9

- 本轮为最终轮 scope 重绑定复核：前轮 `reviewed_scope: 68587ae956c27987` 因 v7 门禁退化定位、交付内容变化（第三个测试替身签名同步）而失效，本轮以新指纹 `2a1217ac45ea38e9` 重新绑定最终范围。相对 Round 4 的唯一代码交付变化为 `tests/unit/test_refactor_behavior_equivalence.py` 的 `SimpleNamespace(get_last_error=...)` lambda 补 `runtime=None`；环境侧人工清理被中止 v6 残留的整套 E2E 容器（按测试前缀清理 7 容器 4 网络，主仓部署 4 容器保留、其它会话容器不触碰）与 `docs/pending/todo/p048_gate_stale_e2e_container_cleanup.md` 待办登记均非代码交付，最终门禁 v8 在干净环境启动。
- 第三个测试替身签名同步（独立复核，仅 stub、无断言改动）：`git diff 05dda065aa237f9e32c3507f6f6a65f47a185205 -- tests/unit/test_refactor_behavior_equivalence.py` 输出仅 1 处 hunk，`:352-354` 由 `lambda profile_id: "boom"` 改为 `lambda profile_id, runtime=None: "boom"`，返回值 `"boom"` 不变；该文件 `:359-368` 全部 `assert` 行原样保留、diff 未触及任何断言，无恒真 / 弱化 / `.skip` / mock 掉被测逻辑。因 `runtime_views.py:46` 的 `make_runtime_response` 现以 `runtime=rt` 调用 `coordinator.get_last_error`，stub 须接受可选 `runtime` 参数，属测试替身随被测接口同步，非改断言迎合实现。
- 三个 `get_last_error` 读取点收敛感知统一（独立复核）：`runtime_views.py:46`（GET runtime 经 `make_runtime_response`）、`router.py:112`（SSE 初始快照 `get_initial_snapshots`）、`runtime_coordinator.py:709`（`publish_profile_change`）全部传 `runtime=rt`；生产签名 `runtime_coordinator.py:245-251` `get_last_error(profile_id, runtime=None)` 收敛态 `pop` 残留返回 None，`runtime_coordinator.py:1020` 内部 reconcile 无参读取（`runtime=None`）保持旧行为不受影响。三个测试替身 `test_api_search_defaults_routes.py:60`、`test_t026_transport_api.py:68`、本轮 `test_refactor_behavior_equivalence.py:353` 签名全部对齐 `runtime=None`，收敛感知统一、修复真实。
- v7 退化定性（环境 / 替身问题，非代码回归）：根因①第三个 stub 未同步 `runtime` 签名，`make_runtime_response` 以 `runtime=rt` 调用时抛 `TypeError: unexpected keyword argument 'runtime'`（测试替身问题，已修）；根因②被中止 v6 残留整套 E2E 容器占用宿主 UDP 30000，致 v7 `Bind for 127.0.0.1:30000 failed: port is already allocated`（环境问题，已人工清理）。两者均非产品代码回归，无新 blocker。
- p048 定性（待办登记，非本轮实现缺陷）：`docs/pending/todo/p048_gate_stale_e2e_container_cleanup.md` 记「门禁被 SIGTERM 中止时残留 E2E 容器污染下一轮」，来源标「门禁基础设施缺陷（技术债自查，需从根因修）」、处理「待收尾阶段从根因修；本轮 t037 只在门禁前人工清理残留以保证 v8 证据干净」，并要求门禁启动清理 / trap 中断清理 / 补单测。属跨 task 门禁基础设施待办登记，非本轮 diff 引入的实现缺陷、不属 12 条 AC；按系统性缺口去重 / 范围外仅结论段提示处理，不进 finding 表、不阻断本轮 verdict。
- 前轮 finding 复核（以 diff / 代码为准，前 4 轮 3 条 minor 均未回退）：`t037_code_f002` 的 `ProfileDetailPage.tsx:17` 导入 / `:48` 使用共享 `statusDescriptor`、`EnvironmentTable.tsx:56-60` 导出含 `?? STATUS_MAP.stopped!` 兜底仍在；`t037_test_f001` 的 `ConfigTab.test.tsx` / `MaintenanceTab.test.tsx` / `ProfileIsolation.test.tsx` 均存在；`t037_code_f001` 的 `progress.md:51-58` 扫描口径「A 状态新增源码 32 文件 0 命中 + diff 新增行 0 命中」保留。本轮 diff 仅一个测试 stub 文件、不含前端源码 / progress / 任何断言文件，未触及上述修复。
- 本轮新发现：0 条（0 critical / 0 important / 0 minor）。改动为替身签名同步，无新 blocker；p048 为待办登记，非本轮实现缺陷。
- 未进表的提示：无。p048（门禁中断残留清理）已作为跨 task 待办登记、收尾阶段从根因修，本轮不再作为范围外观察复述。
- 总体判断：最终 scope 重绑定，第三个替身签名同步真实、三读取点收敛感知统一、v7 退化为环境 / 替身问题而非代码回归、p048 属待办登记、前 4 轮 minor 未回退；12 条 AC 实现层与测试层均未变、全部 TICK-VALID，无未解决 critical / important，判定 PASS。
- 系统性 follow-up：已有 `docs/pending/todo/p048_gate_stale_e2e_container_cleanup.md`（门禁中断残留清理，收尾阶段修）；p047 已归档 resolved，本轮无新增建议。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。`EnvironmentTable.tsx` 8 列 + `DirectNetwork` 直连警示 + `PlatformIcon` + `StatusBadge` 五态 + `formatRelativeTime`，`EnvironmentListPage.test.tsx` 4 例断言真实；本轮 diff 仅 `test_refactor_behavior_equivalence.py` stub、不含前端源码，列表列与共享 `statusDescriptor` 兜底未触及，维持判定。
- AC-002：TICK-VALID，re_verified。`useEnvironmentFilters.ts` 用 `useSearchParams` 读写 q/status/group/proxy/sort、`filterEnvironmentRows` 组合筛选、`EnvironmentEmptyState` 清除筛选，测试 11 例含 URL 五参数还原与无结果清理；本轮 diff 未触及筛选 / URL 实现，维持判定。
- AC-003：TICK-VALID，re_verified。`useEnvironmentLayout.ts` 持久化 `cbrowser.environments.layout`，`EnvironmentCard.tsx` 展示名称 / 状态 / 分组 / 网络 / 操作与 `env-card-preview-*` 空占位，测试 2 例含刷新后卡片视图保持；本轮 diff 未触及，维持判定。
- AC-004：TICK-VALID，re_verified。`useProfileEventsSync`（`useProfilesQuery.ts`）按 `profileKeys.runtime(id)` 增量合并 SSE，行状态 / `EnvironmentRowActions` / `useRuntimeSnapshot.runningCount` 共用同一 key，测试用 `setQueryData` 验证 1→0 实时更新；本轮复核三读取点（`runtime_views.py:46` / `router.py:112` / `runtime_coordinator.py:709`）全部传 `runtime=rt`、收敛态一致清空残留 error，且第三个替身签名同步后该路径不再抛 `TypeError`，增量合并与 runtime key 未变，维持判定。
- AC-005：TICK-VALID，re_verified。`useBatchActions.ts` 逐项 `mutateAsync`、`useActionKeyMutation` 每次 `newIdempotencyKey()`、toast `envBatchResult`、`clearSelection(succeeded)` 保留失败项、catch 计 409 失败，测试 5 例验证 4 类操作幂等键互异与 409 汇总；本轮 diff 未触及，维持判定。
- AC-006：TICK-VALID，re_verified。`ProfileForm.tsx` 四分区（Advanced 默认折叠）、名称必填字段旁错误、平台字体集平台过滤 + 最新默认 + 完整性 / 缺失告警、reseed，`ProfileCreateDialog.tsx` 创建成功后 `setDesiredState(running)`，测试 7+3 例含 create 与 create-and-start 顺序断言；本轮 diff 未触及，维持判定。
- AC-007：TICK-VALID，re_verified。`ProfileDetailPage.tsx` 页头名称 / 状态 / 分组 / 打开会话 / 启动 / 停止 + `SharedProfileBanners` 四标签共享，测试 STATUS_CASES 5 例、四标签真实锚点、两条共享 banner + 重试；本轮核实 `:17` 导入 / `:48` 使用共享 `statusDescriptor` 兜底仍在（f002 未回退），四标签共享 banner 未变，维持判定。
- AC-008：TICK-VALID，re_verified。`ConfigTab` 与 `ProfileCreateDialog` 共用 `ProfileForm`，`METADATA_KEYS`/`hasRuntimeConfigChange`/`pickMetadata` 驱动元数据 vs 运行配置分类，`SharedProfileBanners` 以 `config_version` 差判待应用并复用 `useApplyDisplaySettingsMutation` 阶段跟踪实现「应用并重启」；`ConfigTab.test.tsx`（A22 后台刷新不覆盖未保存编辑）仍在，本轮 diff 未触及分类逻辑，维持判定。
- AC-009：TICK-VALID，re_verified。`ProfileFilesTab.tsx` / `ProfileAutomationTab.tsx` / `MaintenanceTab.tsx` 按设计系统重建，`MaintenanceTab.test.tsx` 覆盖删除独立幂等键（`not.toBe(firstKey)`）与运行中禁删（`toBeDisabled()` 且 `delete` 未调用）仍在；本轮 p048 为门禁中断残留清理的跨 task 待办登记（收尾阶段修），非本 AC 实现层缺陷、本轮 diff 不含前端源码，维持判定。
- AC-010：TICK-VALID，re_verified。`GroupManagerDialog.tsx` 新建 / 改名 / 改色（8 色）/ 拖动与 ArrowUp/ArrowDown 排序 / 删除确认 `group-affected-count` 受影响环境数，`useGroupReorder` 乐观更新 + invalidate，测试 10 例含 `ordered_ids` 精确断言与 409 `group_name_in_use` 不被吞；本轮 diff 未触及，维持判定。
- AC-011：TICK-VALID，re_verified。`ProfileIsolation.test.tsx` 8 例覆盖 per-profile 动作状态不串台、每标签独立 `cbrowser.session.target`、关闭页面 / 卸载不调用 stop，断言具体（串台负向断言、按钮非禁用）、无恒真断言；本轮核实该文件仍在、未被删改，隔离语义不变，维持判定。
- AC-012：TICK-VALID，re_verified。`test_frontend_app_e2e.py:93-120` 走 UI（env-new→env-new-dialog→profile-form-name→submit→detached→row），旧 4 页面组件与旧 testid 全仓 0 残留、`/profiles/new` 专门路由删除；`progress.md:51-58` 扫描口径「A 状态新增源码 32 文件 0 命中 + diff 新增行 0 命中」保留（f001 未回退）；本轮 v7 门禁退化经环境残留 / 替身签名两因定位后 v8 在干净环境重启（非代码回归，实现层证据不变），本轮 diff 不含前端源码与 E2E 文件，颜色类结论未变，维持判定。

coverage = re_verified / 12

verdict: PASS
