---
tid: "t036"
slug: "design_system_app_shell"
title: "设计系统与应用外壳"
status: "done"
branch: "t036_design_system_app_shell"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "95cccfc9f328290cbb13090ef960b0f22a129782"
depends_on: "t033,t041"
conflicts_with: ""
note: "来源 plan_20261105_ui_redesign WP03+WP08"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-06（用户监督新增工作规则，自本 task 起生效）：**每次改代码后，先跑与改动直接相关的 unit / integration / E2E 定向用例确认通过，再跑完整门禁**，减少因局部回归导致的完整门禁失败轮次。完整门禁（`CBROWSER_RUN_E2E=1 scripts/run_gates.sh`）仍是 finish 的必要依据，不能省；`.md`-only 变更且产品与测试代码零变化时，按 t035 先例以「受影响的 contract/unit 复跑 + 定向验证」作为补充证据，并在收尾报告说明。
- 2026-11-06（2 项 UNVERIFIED-SPIKE 闭环）：正式 spike `docs/spikes/s015_design_system_toolchain/`（report.md + `code/` 五个可复现文件）；finding `docs/findings/d034_design_system_toolchain_versions.md`；两项 UNVERIFIED-SPIKE 已回填 `task.md` 为结论与验证方式。
    - `@google/design.md@0.4.0`：`npx @google/design.md lint DESIGN_SPIKE.md` = 0 error / 0 warning / 1 info；程序化 `lint()` 的 `designSystem.colors` 为 Map（含 hex/RGB/luminance），`tailwindConfig` 可用。双模式写法在 0.4.0 合法；生成器须自行校验 `light-*` / `dark-*` 角色集合相等（官方 lint 不检查）。
    - `@tailwindcss/vite@4.3.4` + `tailwindcss@4.3.4` + `vite@8.3.5`：构建成功，`@theme` token 产出 CSS；Vite 8 的 root 须在 config。
- 2026-11-06：t036 实施顺序（按新工作规则：每层先定向用例后完整门禁）：`DESIGN.md` 全量 + `scripts/design_tokens.mjs` 生成器（先红后绿）→ Tailwind 4 迁移与 `package.json` / `vite.config.ts` → `public/theme_boot.js` 与主题上下文 → `src/shared/ui/` 组件族（Radix 原语）→ 应用外壳与路由表 → 登录/设置页重做（含平台字体区块，接 t041 `GET /api/v1/font-sets`）→ i18n / AGENTS.md / 产物扫描 → 定向 Vitest / 构建 → 完整门禁 → full review → finish。
- 2026-11-06（实施完成）：各层均按「改代码 → 定向用例 → 下一层」推进，最终定向证据：
    - 生成器 `design_tokens.test.mjs` 先红（模块不存在）后绿（5 用例：角色集合不等 / 未解析引用 / 无前缀颜色 token / 官方 lint 报错 / 确定性生成）。
    - 主题 `theme.test.tsx`（3）+ `theme_boot.test.mjs`（4）先红后绿；`ui.test.tsx`（5：Dialog 焦点陷阱/归还/Esc/aria-modal、DropdownMenu、Popover、Tooltip、Toast 单实例）；`AppLayout.shell.test.tsx`（5：折叠/拖宽 clamp/持久化/窄屏抽屉/SSE 计数与警示横幅/主题不写 color_scheme）。
    - 设置页 `SettingsPage.test.tsx` 补平台字体区块一致性与完整性告警 2 用例；`scopeMutationToProfile.test.ts`（5）接替被删除外壳隔离用例（详见「测试处置清单」）。
    - 前端全量：`npm test` = `46 files / 248 tests passed`；`npm run design:lint` = 0 error / 0 warning；`npm run design:check` 通过；`npm run design:tokens` 幂等；`npm run build`（含 selkies IIFE + postbuild freshness）通过。
    - `design:check` 失败路径验证：向入库产物追加 `/* stale marker */` 后 `npm run design:check` 退出 1 并报 `design_tokens.css is stale or edited`，恢复后重新通过（AC-002）。
- 2026-11-06（AC-003 扫描，命令与结果）：扫描 `src/frontend/src/app/AppLayout.tsx`、`routes/PlaceholderPage.tsx`、`features/auth/LoginPage.tsx`、`features/settings/SettingsPage.tsx`、`styles/globals.css` 与 `shared/ui/*.tsx` 共 20 个文件，正则匹配 Tailwind 默认调色板类（`(bg|text|border|outline|ring|from|to|via|fill|stroke)-(slate|gray|...)-\d{2,3}`）、旧 `surface-0..4` / `primary-foreground` 类与颜色字面量（hex / rgb / hsl / oklch）：**violations=0**。生成产物 `design_tokens.css` 按设计权威含 hex，属生成产物不列入「业务源码」扫描。`dist/assets/*.css` 中 `bg-red-500` / `text-gray-100` / `bg-emerald-500` / `bg-blue-500` / `text-slate-900` / `bg-surface-0` 均未出现（`@theme` 的 `--color-*: initial` 在编译期被 Tailwind 消费），语义类 `.bg-primary` 与 `--color-background` / `--color-surface` / `--color-accent` / `--font-ui` / `--font-mono` / `--text-body-md` / `--radius-md` / `--spacing-md` 及 `.dark` 覆盖均存在。
- 2026-11-06（AC-009 扫描，命令与结果）：`dist/index.html` 与 `dist/assets/*.css` 中 `https?://` 仅命中 `/*! tailwindcss v4.3.4 | MIT License | https://tailwindcss.com */` 注释，无任何外部字体 / 图标 CDN 引用；`index.html` 内联脚本数 = 0（仅 `/theme_boot.js` 外链经典脚本）；产物自托管 `*.woff2` 字体文件 13 个（Space Grotesk Variable 可变字体 + IBM Plex Mono 400/500 各子集）。
- 2026-11-06（路由决策）：`/profiles/new` 会被 `profiles/:profileId` 以 `profileId="new"` 误捕获，故在子路由中显式置于 `:profileId` 之前并以 `<Navigate to="/" replace />` 落到首页 catch-all，符合 AC-007「旧路由不再匹配任何页面」；`/automation/:profileId` 由顶层 `*` 回落。`handleDuplicate` 成功后改跳 `/profiles/:id/config`，避免经 `profiles/:profileId` 二次重定向。
- 2026-11-06（E2E 门禁两轮修复，按「先定向用例后完整门禁」）：
    - 第一轮全量 E2E 16 failed，根因与修复：① 新外壳 `<main>` 未形成确定高度链，会话页 `h-full` 失效、`browser-session-mount` 与 iframe hidden → `AppLayout` 改 `main` 为 flex 列、内层 `flex-1 min-h-0` 容器并给 `<Outlet />` 独立 `flex min-h-0 flex-1 flex-col` 容器（AC-005 外壳布局，非测试妥协）；② `FrontendTopologyHarness` 自带 minimal host 页 `tests/fixtures/frontend_probe/host_entry.tsx` 仍从 `?profileId=` 取目标，新路由 `/session/:id` 下退化为 `"default"` 导致 iframe 连错 Profile 无帧 → 改从 `pathname` 解析 `/session/:id`（fixture 随新路由改造）；③ `verify_frontend_dist.py` 的 utility 检查改为 Tailwind 4 语义变量后，`test_frontend_build_wiring.py::_write_dist` 的 fake CSS 同步为 `@theme` 风格（fixture 变化，校验语义不变）；④ `test_frontend_app_auth_e2e.py` 的 open-redirect 检查等待 `new-profile-link`（旧侧栏）→ 改为 `sidebar`（新外壳元素）；⑤ `test_supervisor_recovery_e2e.py::test_supervisor_sigkill_reconciliation_and_event_persistence` 全量时偶发失败、定向 20s 通过，属编排并发/资源竞争，按 t032 先例如实登记为环境遗留、不归因 t036。
    - 定向验证：3 个代表用例（session dual-tab / app dual-tab SSE / media visibility）+ build_wiring + auth_guard 全绿；supervisor_recovery 定向绿。
    - 第二轮全量 E2E 2 failed：⑥ `test_ac007_lifecycle_resume_and_isolated_media_diagnostics` 等待 `/profiles/{id}$`，plan 5.1 下该路径重定向到 `config` → 断言改 `/profiles/{id}/config$`（断言语义「状态按钮跳详情页」不变）；⑦ `test_t019_switch_and_refresh_first_frame_within_2s_host_only` 我把「侧栏切换」改成 `open_session`（`page.goto` 整页重载），首帧被拖到 3.677s > 2s → 改回 SPA 内 `history.pushState` + `popstate` 切换（不重载，恢复原计时语义）。两用例定向 84.65s 通过。
    - 处置均登记于「测试处置清单」E2E 小节；`t019` 按 t032 已登记遗留口径如实记录，不归因后续 task。

## 测试处置清单

按 AGENTS「旧测试逐用例」规则与 t035 做法登记（2026-11-06 用户监督：t036 改动 6 个既有前端测试，逐用例说明）。分类：仅因 plan 5.1 路由结构变化而改导航路径 / fixture（断言语义不变）、断言语义被推翻（删除旧 + 新增新语义）、整文件删除。

### 仅改 fixture / 导航路径，断言语义不变

|文件|用例|变更|对应路由 / 结构变化|
|---|---|---|---|
|`app/AppLayout.focus.test.tsx`|`blurs active iframe and refocuses window on host pointerdown`|原地新增 `vi.mock("../theme")`（新外壳依赖 `useTheme`）；断言（iframe blur + `window.focus`）不变|新外壳引入 `ThemeProvider` / `useTheme`；AC-006 焦点守卫仍由本用例覆盖|
|`app/auth_guard.test.tsx`|`redirects unauthenticated app routes to /login and preserves the target`|未改（通过）|—|
|`app/auth_guard.test.tsx`|`shows a loading state and issues no business requests while the session check is pending`|`active-profile-header` → `sidebar`（app 渲染标志）|旧 `active-profile-header` 随旧外壳删除|
|`app/auth_guard.test.tsx`|`renders the app and starts SSE only after authentication`|`active-profile-header` + `toHaveTextContent("Profile Alpha")` → `sidebar` + `toBeInTheDocument()`；断言（认证后渲染 app、SSE 恰好 start 1 次）不变|旧 `active-profile-header` 及其 Profile 名称文本删除|
|`app/auth_guard.test.tsx`|`clears auth, stops SSE and redirects to /login preserving the target on API 401`|触发方式 `fireEvent.click(header-launch-btn)` → `api.triggerUnauthorized()`；断言（清 auth / 停 SSE / 重定向 / `next` 保留）不变|旧 header 启动按钮删除；`setOnUnauthorized` 回调仍为 401 真实机制|
|`app/auth_guard.test.tsx`|`logs out through useAuth, stops SSE and redirects to /login`|`getByTitle("Log out")` → `getByRole("button", { name: "Log out" })`|新 `IconButton` 用 `aria-label`，不再有 `title`|
|`app/auth_guard.test.tsx`|`authenticates through AuthProvider and returns to the original target`|`active-profile-header` → `sidebar`|同上|
|`app/auth_guard.test.tsx`|`redirects authenticated visitors away from /login to the target or root`|未改（通过）|—|
|`app/auth_guard.test.tsx`|fixture `mockApi` stub|新增 `request: vi.fn(async () => [])`|设置页新增 `GET /api/v1/font-sets` 调用|
|`app/router.test.tsx`|`offers duplicate and reset confirmations on the profile detail page`|`/profiles/p1` → `/profiles/p1/config`；duplicate 后加 `await view.findByTestId("profile-detail-page")` 等待重挂载；断言（duplicate payload、reset 确认文案、reset 调用）不变|plan 5.1 详情拆为 `config` 标签；`handleDuplicate` 成功后改跳 `/profiles/:id/config`|
|`app/router.test.tsx`|fixture `renderWithRouter` / `makeStubClient`|增加 `ThemeProvider` + `ToastProvider`；stub 加 `request`|新 `AppProviders` 依赖；字体集接口|
|`features/profiles/BrowserSessionPage.test.tsx`|`mounts the session view when the runtime is running`|fixture `["/?profileId=p1"]` + 直接渲染 → `["/session/p1"]` + `<Routes><Route path="/session/:profileId">`；断言不变|plan 5.1：会话目标由 query `?profileId=` 改为 path param `/session/:profileId`（`useSearchParams` → `useParams`）|
|`features/profiles/BrowserSessionPage.test.tsx`|`launches a stopped profile and mounts the session once it runs`|同上|同上|
|`features/profiles/BrowserSessionPage.test.tsx`|`shows a start error instead of swallowing the mutation failure`|同上|同上|
|`features/profiles/BrowserSessionPage.test.tsx`|`shows profile-not-found only for a real 404 (A17)`|同上|同上|
|`features/profiles/BrowserSessionPage.test.tsx`|`shows a load error with retry when the profile request fails (A17)`|同上|同上|
|`features/profiles/BrowserSessionPage.test.tsx`|`shows the loading state while requests are pending (A17)`|同上|同上|
|`features/profiles/BrowserSessionPage.test.tsx`|`retries only the runtime query from the runtime error branch (A17)`|同上|同上|
|`features/profiles/BrowserSessionPage.test.tsx`|`shows a load error when the runtime request fails instead of treating it as stopped (A17)`|同上|同上|
|`features/profiles/BrowserSessionPage.isolation.test.tsx`|`does not show A's launch error on B`|`["/?profileId=pA"]` → `["/session/pA"]`；`<Route path="/">` → `path="/session/:profileId"`；`navigateFn("/?profileId=pB")` → `"/session/pB"`；断言（A 的 launch 错误不串到 B）不变|plan 5.1 path param 化|
|`features/profiles/BrowserSessionPage.isolation.test.tsx`|`does not disable B's launch while A's launch is pending, and A's late failure does not pollute B`|同上（含 `navigateFn("/session/pA")` 返回 A）|同上|
|`features/profiles/BrowserSessionPage.isolation.test.tsx`|`shows A's own action state again when navigating back to A`|同上|同上|

### 断言语义被推翻：删除旧用例 + 新增新语义用例

|文件|删除旧用例（名称 + 理由）|新增新语义用例（名称）|
|---|---|---|
|`app/router.test.tsx`|`navigates to Plan 13.1 routes correctly`：旧路由表（`/profiles/new`、`/automation/:profileId`、`/?profileId=` 会话目标）整体被 plan 5.1 删除|`renders the plan 5.1 route table`|
|`app/router.test.tsx`|`AC-001: URL ?profileId= determines target, switching updates only that page URL, forbidden localStorage, two independent page instances do not interfere`：会话目标由 query 改为 `/session/:profileId`，侧栏 `profile-item-*` 列表删除，跨标签页 URL 独立性不再由外壳承载；会话页 path param 语义由 `BrowserSessionPage.test.tsx` / `.isolation.test.tsx` 接替|`drops the legacy routes`、`renders navigation as real anchors`、`redirects /profiles/:profileId to the config tab`|
|`app/router.test.tsx`|`AC-001: selecting a profile from a sub-route navigates to the session page`：侧栏 `profile-item-*` 结构删除|`renders navigation as real anchors`（导航与环境链接为真实 `<a href>`）|

### 整文件删除：`app/AppLayout.isolation.test.tsx`

新外壳（导航侧栏）不再承载旧顶栏的 `active-profile-header` / `display-apply-restart-btn` / `display-apply-error`，该文件 2 个用例的 UI 挂载点全部删除，故整文件删除。逐用例说明覆盖行为在新外壳下是否仍存在及接替测试：

|被删用例|覆盖行为|新外壳下是否仍存在|接替测试|
|---|---|---|---|
|`does not show A's apply error bar on B`|按 Profile 限定 mutation 状态，A 的 display-apply 错误不串到 B|**核心行为仍存在**：`scopeMutationToProfile` 生产函数未删除，`BrowserSessionPage` / `ProfileDetailPage` 仍使用；但旧顶栏 UI 挂载点删除，t036 外壳不提供该组控件（页面重做由 t037+ 承担）|新增 `features/profiles/scopeMutationToProfile.test.ts > does not show A's error on B`；`BrowserSessionPage.isolation.test.tsx > does not show A's launch error on B`（同一隔离语义）|
|`does not disable B's apply while A's apply is pending, and A's late failure does not pollute B`|A 的 pending 不禁用 B、A 迟到失败不污染 B|同上，核心行为仍存在、UI 挂载点删除|新增 `scopeMutationToProfile.test.ts > does not disable B while A's mutation is pending, and A's late failure stays on A`；`BrowserSessionPage.isolation.test.tsx > does not disable B's launch while A's launch is pending, and A's late failure does not pollute B`|

`scopeMutationToProfile.test.ts` 另新增 `shows A's own state again when navigating back to A`、`unwraps action-key mutation variables shaped as { input, actionKey }`、`surfaces nothing when the mutation has no target yet`，补齐该生产函数的直接覆盖（5 用例）。

### E2E 处置（`tests/e2e/`，同一逐用例规则）

用户 2026-11-06 监督要求登记 6 个前端测试；前端 E2E 亦按同一规则登记。5 个文件：`test_frontend_app_auth_e2e.py`、`test_frontend_app_e2e.py`、`test_frontend_display_apply_e2e.py`、`test_frontend_media_e2e.py`、`test_frontend_session_e2e.py`。

|文件|用例 / 变更|分类|说明|
|---|---|---|---|
|5 个文件|`/?profileId={id}` → `/session/{id}`；`wait_for_url(re.compile(r"/\?profileId="))` → `/session/`；`login_next(...) == "/?profileId=..."` → `"/session/..."`；`parse_qs(urlparse(url).query)["profileId"]` → `urlparse(url).path == "/session/{id}"`|仅改导航路径 / fixture，断言语义不变|plan 5.1 会话目标由 query 改为 path param；双标签页目标独立、SSE、媒体帧、鉴权跳转断言均不变|
|`test_frontend_app_e2e.py` / `test_frontend_display_apply_e2e.py`|`create_profile_via_ui` helper 由 `/profiles/new` UI 表单改为 `POST /api/v1/profiles`（带 name / screen_width / screen_height）|fixture 构造变化，断言语义不变|旧路由 `/profiles/new` 删除；新建 UI 由 t037 环境列表交付|
|`test_frontend_app_e2e.py`|「Profile list shows the created profiles」与「Edit name」后的 `profile-item-*` 列表断言 → `GET /api/v1/profiles` 响应文本校验|fixture 构造变化，断言语义（创建成功 / 改名生效）不变|新外壳导航侧栏无 Profile 列表；环境列表由 t037 交付|
|`test_frontend_app_e2e.py`|`page_a.click(profile-item-pB)` / 切回 pA → `open_session(page_a, harness, pB/pA)` 直接导航；t019 的「sidebar 切换」计时点同改|fixture 构造变化，断言语义（切换目标、首帧 ≤2s、页 B 不受影响）不变|新外壳无 Profile 侧栏，目标由 URL 指定|
|`test_frontend_app_e2e.py` / `test_frontend_app_auth_e2e.py`|`active-profile-header` → 会话页 `session-launch-btn` + `page.content()` 含 Profile 名；`header-launch-btn` → `session-launch-btn`|fixture / 查询选择器变化，断言语义（登录后回到目标会话页、API 401 触发）不变|旧顶栏元素删除；`session-launch-btn` 仍触发 `setDesiredState` 使 401 生效|
|`test_frontend_app_e2e.py`|`launch_profile_via_ui` 等待 `header-stop-btn` → `browser-session-mount`；`stop_profile_via_header(page)` → `stop_profile_via_api(page, harness, profile_id)`（`POST /api/v1/profiles/{id}/stop`），3 处调用点同步|fixture 构造变化，断言语义（启动成功 / 显式停止后容器消失、SSE 收敛）不变|新外壳无顶栏停止按钮；会话停止 UI 由 t039 交付|
|`test_frontend_display_apply_e2e.py`|`test_display_profile_size_requires_explicit_apply` **整体删除**|断言语义被推翻|依赖旧顶栏 `display-pending-badge` 与 `display-apply-restart-btn`，t036 新外壳不承载；会话页待应用提示与「应用并重启」由 t039 重做时交付。显示尺寸显式应用的 API 契约由 t035 `tests/unit` / `tests/integration` 覆盖；**新增新语义 E2E 由 t039 承接**（本 task 不新增，理由：过渡期无对应 UI 可驱动）。同文件 `test_stream_entrypoint_rejects_missing_supervised_screen_config` 不依赖 UI，原样保留|

|`tests/fixtures/frontend_probe/host_entry.tsx`|minimal host 页从 URL query 取 `profileId` → 增加从 `pathname` 解析 `/session/:id`|fixture 随新路由改造，断言语义不变|`FrontendTopologyHarness` 不加载生产 router，新路由下需自行解析 path param，否则退化为 `"default"` 导致 iframe 连错 Profile 无帧|
|`tests/e2e/test_frontend_build_wiring.py`|`_write_dist` fake CSS 由 Tailwind 3 类改为 `@theme` + `--color-primary` / `--color-surface`|fixture 变化，校验语义不变|`verify_frontend_dist.py` 的 utility 检查已改为 Tailwind 4 语义变量|
|`tests/e2e/test_frontend_app_auth_e2e.py`|open-redirect 检查等待 `new-profile-link` → `sidebar`|fixture / 查询选择器变化，断言语义（停留本站 `/`）不变|旧侧栏新建链接删除|
|`src/frontend/src/app/AppLayout.tsx`|`<main>` 改 flex 列 + `flex-1 min-h-0` 容器（实现修复，非测试妥协）|实现修复|新外壳高度链断裂致会话页 `h-full` 失效、`browser-session-mount` 与 iframe hidden；修复后会话页铺满|
|`tests/e2e/test_frontend_app_e2e.py`|`test_ac007` 等待 `/profiles/{id}$` → `/profiles/{id}/config$`|断言路径随 plan 5.1 变化，语义（状态按钮跳详情页）不变|`/profiles/:id` 现重定向到 config 标签|
|`tests/e2e/test_frontend_app_e2e.py`|`test_t019` 切换由 `page.goto`（整页重载）改回 SPA 内 `pushState` + `popstate`|fixture 构造变化，计时语义（SPA 内切换首帧 ≤2s）不变|整页重载把首帧拖到 3.677s；改回 SPA 内切换后定向 84.65s 通过|
|`test_supervisor_recovery_e2e.py::test_supervisor_sigkill_reconciliation_and_event_persistence`|首轮全量偶发失败、定向 20s 通过|t032 已登记类环境遗留，如实登记不归因 t036|编排并发 / 资源竞争|
|`test_t019_switch_and_refresh_first_frame_within_2s_host_only`|最终全量门禁唯一失败（首帧 3.341s > 2s），定向 84.65s 通过|t032 已登记遗留，按用户口径如实登记、不归因后续 task|时序敏感，全量负载下偶发|

结果：5 个 E2E 文件残留旧外壳 testid（`active-profile-header` / `header-launch-btn` / `header-stop-btn` / `profile-item-*` / `profiles/new` / `display-pending-badge` / `display-apply-restart-btn`）为 0；`pytest tests/e2e --collect-only` = 101 tests；`ruff --select F401,F811,F821,F841` 全部通过（删除用例后清理 3 个未使用 import）。完整门禁最终 E2E `95 passed / 5 skipped / 1 failed`（唯一失败为 t032 已登记遗留 t019）。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-06T15:42:00+08:00)

Round 1 零 finding（`review_code.md` / `review_test.md` 两路均 verdict: PASS，10 条 AC 全部 TICK-VALID，scope `9faba922a99c099b`）。

### Round 2 (2026-11-06T15:50:00+08:00)

Round 2 零 finding（仅 `md_format.py --changed` 的 Markdown 格式规范化，scope 重绑定为 `187b5cfbff2c91cc`；无实现 / 测试 / 契约变化，两路 verdict 保持 PASS）。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（AC-001~010 全部打勾）
- 测试：完整门禁证据 `.scratch/evidence_t036_final/manifest.json`：`contract` / `unit` / `integration` / `design_lint` / `design_check` / `design_tokens` / `frontend_test` / `frontend_build` 全绿；前端 Vitest `46 files / 248 tests passed`；`npm run build`（含 vendor Selkies、selkies IIFE、postbuild freshness）通过；`design:lint` = 0 error / 0 warning、`design:check` 通过、`design:tokens` 幂等。
- 黑盒：E2E `95 passed / 5 skipped / 1 failed`。唯一失败 `test_t019_switch_and_refresh_first_frame_within_2s_host_only`（首帧 3.341s > 2s）为 t032 已登记的时序敏感遗留，定向重跑 84.65s 通过；按用户明确口径「按 t032 已登记遗留如实登记，不归因后续 task」登记，不阻断本 task 结论。定向复核另含 3 个代表用例（session dual-tab / app dual-tab SSE / media visibility）、build_wiring、auth_guard、supervisor_recovery，均通过。
- review：full 两路 `review_code.md` / `review_test.md`；结论见 `check_review_status.py` 输出与下方 Review 处置。
- AC 判定：见 `task.md` 行内打勾（AC-001~010 全勾，Reviewer 逐条 TICK-VALID 复核）。

### 结果摘要

- 交付：根目录 `DESIGN.md`（双模式唯一设计权威，官方 lint 0 error / 0 warning）→ `design_tokens.mjs` 确定性生成 Tailwind 4 `@theme` 变量并入库 → 三条 design 命令接入 `run_gates.sh`；Tailwind 4（`@tailwindcss/vite`）重置默认调色板、字体 `@fontsource` 自托管；主题三态（`public/theme_boot.js` 首帧、React `ThemeProvider`）；导航侧栏外壳（折叠 / 拖宽 / 窄屏抽屉 / SSE 运行中数 / 警示横幅 / iframe 焦点守卫）；plan 5.1 路由表与占位页；`shared/ui` 组件族（Radix 浮层）；登录页与设置页重做（含 `GET /api/v1/font-sets` 平台字体区块与完整性告警）。
- 遗留：`t019` 按 t032 已登记遗留如实登记（见「验收与验证」）；`test_display_profile_size_requires_explicit_apply` 整体删除、新增新语义 E2E 由 t039 承接；会话页停止 / 待应用 UI 由 t039 交付；环境列表 / 代理库 / 会话页重做由 t037 / t038 / t039 承接（均非本 task 范围）。

### 长期文档闭环

- `docs/specs_index.md` 新增 `|ui_design_system|t036|2026-11-06T14:26:49+08:00|`；新建 `docs/specs/ui_design_system.md`（需求级 spec，AC-001~010 摘要）。
- `docs/blueprint/frontend.md`（新增第 6 节「设计系统与应用外壳」，并改写路由 / 外壳 / 运行协调错误 / 页面独立状态 / 侧栏导航等现行语句）、`conventions.md`（第 6 节 DESIGN.md 落点与语义 token）、`testing.md`（「t036 设计门禁与产物扫描」）、`decisions.md`（ADR 025 DESIGN.md 为设计权威与亮暗双模式约定）已更新。
- `AGENTS.md` 目录表新增 `DESIGN.md` 与 `.design_reference/`。
- 正式 spike `docs/spikes/s015_design_system_toolchain/`（report.md + `code/` 五个可复现文件）关联现存 finding `d034`；report 含「结论」「决定：是」与「无需后续理由」；`check_finalization('t036')` 返回空警告。
