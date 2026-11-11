# Task review t036（reviewer_focus: 代码）

- task：`t036_design_system_app_shell`
- spec：`docs/tasks/t036_design_system_app_shell/task.md`
- diff_anchor：`95cccfc9f328290cbb13090ef960b0f22a129782`
- target：`git -C '<repo>_t036' diff --cached 95cccfc9f328290cbb13090ef960b0f22a129782`
- round：1
- reviewed_at：2026-11-06T15:40:00+08:00

reviewed_scope: 9faba922a99c099b

## Findings

零 finding。按 7 视角（安全 / 正确性 / 契约·Breaking / 性能·资源 / 架构·可维护性 / 健壮性·可观测 / 测试·文档·规格）复核被审 diff，未发现 critical / important / minor 级缺陷。

## 结论

- 本轮新发现：0 条。clean 范围内无 critical / important。
- 未进表的提示（纯观察，不阻断、无需处置）：
    - `DESIGN.md` 的 `helper-text` 组件只声明 `textColor`、不声明 `backgroundColor`，官方 lint 的 `contrast-ratio` 规则仅在两者同时存在时校验；该 token 的实际承载背景为 `background` / `surface`，其组合对比度由设计值本身保证（`#656F69` on `#F0F5F1` ≈ 4.6:1、`#858F88` on `#080E0A` ≈ 6.5:1，均达 AA），生成器把两模式值原样落到 CSS 变量，业务代码不写死颜色。属设计系统说明层细节，非行为缺陷。
    - `useRuntimeSnapshot` 对每个 Profile 订阅一个 `getRuntime` 查询（N+1 请求），当前 Profile 规模下开销可忽略；t037 环境列表交付后如引入批量 runtime 接口可收敛。属架构演进观察，不在本 task 范围。
    - `scripts/verify_frontend_dist.py` 的 `CONFIG_INPUTS` 移除 `tailwind.config.ts` / `postcss.config.js` 并新增 repo 级 `DESIGN.md` 输入，使旧 `dist/` 构建戳失效；`npm run build` 的 postbuild 已重新生成并通过 `--check-freshness`，门禁 `frontend_build` 全绿，无残留过期戳风险。
    - 过渡期旧页面（`BrowserSessionPage` / `ProfileDetailPage` / `ProfileFilesPage` / `ProfileAutomationPage`）仍带 Tailwind 3 类名，在 Tailwind 4 重置默认调色板后失去部分样式；task 契约明确「旧页面在被 t037、t039 替换前失去调色板样式（过渡期不要求可用）、不设豁免机制」，本 diff 未加任何兼容层，符合零兼容性负担原则。
    - `t019_switch_and_refresh_first_frame_within_2s_host_only` 在最终全量门禁失败（3.341s > 2s）、定向 84.65s 通过，属 t032 已登记时序遗留；progress 已如实登记且不归因 t036，按用户明确口径不作为本 task 阻塞项。
- 总体判断：`DESIGN.md` 为唯一设计权威、生成器三条校验与确定性产物、Tailwind 4 语义 token 与自托管字体、主题首帧与三态、导航侧栏外壳、plan 5.1 路由、Radix 组件族、登录/设置页重做及长期文档闭环均有真实实现与门禁证据支撑；10 条 AC 打勾可复核，无未解决 critical / important。PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。独立核对 `DESIGN.md` front matter：`primary` + 26 组 `light-*` / `dark-*` 成对角色（含 `group-*` 8 色相、`overlay` 8 位 hex）、typography 9 scale、rounded 5、spacing 6、组件按 `-light` / `-dark` 成对；`npm run design:lint` 输出 `0 error / 0 warning / 1 info`，`contrast-ratio` 与 `orphaned-tokens` 均无告警，章节顺序含 `### Modes`。
- AC-002：TICK-VALID，re_verified。`design_tokens.mjs` 的 `assertValid` 依次校验官方 lint 非 info finding、颜色 token 命名正则 `^(primary|light-.+|dark-.+)$`、`light`/`dark` 角色集合排序相等、`component.unresolvedRefs` 为空；`generateCss` 从 `designSystem.colors`（Map）取 hex 生成 `@theme`（`--color-*: initial` + 亮色默认）与 `.dark` 覆盖全部颜色变量，另含字体 / 字号 / 圆角 / 间距；`design_tokens.test.mjs` 5 用例覆盖三条失败路径、官方 lint 报错路径与确定性；`design:check` 对追加 stale marker 的产物退出 1、恢复后通过；`run_gates.sh` 两处（evidence / 默认）均按 `design_lint` → `design_check` → `design_tokens` 顺序执行，完整门禁三 suite 全绿。
- AC-003：TICK-VALID，re_verified。源码扫描 20 个业务文件命中 0（默认调色板类 / 旧 `surface-*` / 颜色字面量）；构建产物 CSS 中 `bg-red-500` / `text-gray-100` / `bg-emerald-500` / `bg-blue-500` / `text-slate-900` / `bg-surface-0` 均不产生样式，`.bg-primary` 与 `--color-background` / `--color-surface` / `--color-accent` / `--font-ui` / `--font-mono` / `--text-body-md` / `--radius-md` / `--spacing-md` 及 `.dark` 覆盖存在；扫描命令与结果记入 progress。生成产物 `design_tokens.css` 按设计权威含 hex，不列入业务源码扫描，边界说明清晰。
- AC-004：TICK-VALID，re_verified。`theme.tsx` 三态（`system` / `light` / `dark`，默认 `dark`、存 `cbrowser.theme`）与 `matchMedia` 监听；`public/theme_boot.js` 为 `<head>` 外链经典脚本，vm 实跑断言无存储默认 dark、`light` 显式、`system` 跟随；`index.html` 内联脚本 0、无静态 `class="dark"`；`AppLayout.shell.test.tsx` 断言切换主题后 `classList` 与 `colorScheme` 生效、`cbrowser.theme=light` 且 `client.profiles.update` 未被调用（UI 主题不触碰 Profile `color_scheme`）。
- AC-005：TICK-VALID，re_verified。`AppLayout.shell.test.tsx` 覆盖从 localStorage 恢复折叠 / 宽度、拖宽 clamp 200–360 并持久化、窄屏抽屉、SSE（`queryClient.setQueryData(profileKeys.runtime(...))`）更新 `running-count` 与 `runtime-coordinator-error` 警示横幅；resize handle 有 `role="separator"` / `tabIndex=0` / ArrowLeft-Right 键盘操作，导航为 `<a href>`。
- AC-006：TICK-VALID，re_verified。`useRuntimeSnapshot` 聚合 runtime 缓存的 `last_coordinator_error`，`Banner`（`role="alert"`）以 `runtime-coordinator-error` 渲染；`AppLayout.focus.test.tsx` 保留 iframe 焦点守卫（宿主 pointerdown 时 `blur()` + `window.focus()`）断言，新外壳 `useEffect` 逐字保留该守卫。
- AC-007：TICK-VALID，re_verified。`app/router.tsx` 路由表逐条对齐 plan 5.1（`/login`、`/`、`/session`、`/session/:profileId`、`/profiles/:profileId`→`config`、`{config,files,automation,maintenance}`、`/proxies`、`/settings`）；`router.test.tsx` 断言旧 `/profiles/new`（显式回落首页）与 `/automation/:id` 不再渲染旧页面、`/?profileId=` 首页为占位页、导航 `nav a[href]` ≥4 且均有 href、`/profiles/p1` 重定向 `config`。
- AC-008：TICK-VALID，re_verified。`ui.test.tsx` 5 用例实跑：Dialog `role=dialog` / `aria-modal=true` / 焦点在 Content 内 / Esc 关闭 / 焦点归还 trigger；DropdownMenu `role=menu` + 2 menuitem + Esc；Popover `role=dialog` + Esc；Tooltip `role=tooltip`；Toast 多次 show 后 `toast-viewport` 与 `toast-item` 均恰 1 个。浮层基于 Radix 原语，未手写焦点陷阱。
- AC-009：TICK-VALID，re_verified。产物扫描 `dist/index.html` 与 `dist/assets/*.css` 中 `https?://` 仅命中 Tailwind MIT license 注释，无外部字体 / 图标 CDN；`dist/assets/*.woff2` 13 个（Space Grotesk Variable + IBM Plex Mono 400/500 各子集），`index.html` 内联脚本 0；`npm run build` 与 `verify:selkies --check-freshness` 通过。
- AC-010：TICK-VALID，re_verified。登录页保留 `login-page` / `login-password` / `login-submit` / `auth-loading` 与 `sanitizeNextPath` 跳转、`useAuth` 登录语义；设置页保留语言 en/zh 与 Control API 健康检查真实探测；`SettingsPage.test.tsx` 新增 2 用例覆盖 `GET /api/v1/font-sets` 数据一致性与 `integrity.ok=false` 告警（`font-set-integrity-bad` + problems）；`auth_guard.test.tsx` 覆盖鉴权、登录跳转与 401 重定向；完整门禁 `frontend_test` 248 passed。

## 第 2 轮复核（scope 重绑定）

- 交付内容仅因 `md_format.py --changed` 的 Markdown 格式规范化变化（`docs/blueprint/frontend.md`、`docs/specs/ui_design_system.md`），无任何实现 / 测试 / 契约代码变化；被审 diff 指纹由 `9faba922a99c099b` 重绑为 `187b5cfbff2c91cc`（已重跑 `render_review_prompts.py`）。
- 格式规范化不改变 AC-001~010 的实现面与门禁证据：`.scratch/evidence_t036_final/` 完整门禁结论继续有效，10 条 TICK-VALID 不变，TICK-VOID 仍为 0。
- 本轮无新 finding，总体结论保持 PASS。

reviewed_scope: 187b5cfbff2c91cc

coverage = 10 / 10

verdict: PASS
