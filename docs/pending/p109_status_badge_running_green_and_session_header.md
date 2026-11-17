---
pid: "p109"
slug: "status_badge_running_green_and_session_header"
status: "closed"
resolution: "transferred"
reason: "已核实根因与同类位点并聚合并转交 t073（设计系统底座与状态/搜索框重构）"
fix_ref: "t073"
---
# p109 运行中/正常状态徽标与圆点为蓝色、工作台顶栏缺少主语且深色模式辨识极差

- 现象：
    1. 环境管理、工作台、详情页、自动化、代理探测与设置健康检查等处“运行中 / 正常 / 可用 / 完整”状态的 `StatusBadge` 呈蓝色浅底（`accent-soft`）+ 中性文字（`on-surface`），工作台环境切换器状态点（`statusDotClass`）也呈蓝色（`bg-accent`），而非绿色。
    2. 工作台会话顶栏（`SessionHeader`）仅展示裸状态词“运行中”与“正常”（英文 `"Running"` / `"Ready"`），缺少“环境”“数据传输”语义主语；且深色模式下顶栏徽标为接近白色的字（`#E9ECF3`）配暗蓝灰底（`#29344E`），嵌在极相近的顶栏背景（`#2B313C`）上几乎融为一体、辨识极差。
- 影响：所有使用 `StatusBadge`（`tone="running"` 及各彩色状态）和 `statusDotClass("running")` 的页面均受配色语义与深色对比度影响；工作台顶栏用户无法一眼分辨两个徽标分别指“环境运行中”还是“数据传输正常”。覆盖全仓 10 处业务调用点（`EnvironmentTable`、`EnvironmentCard`、`ProfileDetailPage`、`SessionHeader`、`EnvironmentSwitcher`、`SessionEntryPage`、`ProfileAutomationTab`、`ProxyTable`、`ProxyListPage`、`SettingsPage`）。
- 根因：产品设计与实现双层缺陷（设计 token 缺失 `success` 语义色 + 组件纯中性文字样式 + 顶栏主语标签被 `sr-only` 隐藏）。
    1. **缺少 `success` 语义色且 `running` 错误绑定蓝色 `accent-soft` / `accent`**：`DESIGN.md:3-67` 仅定义 `accent`/`warning`/`danger` 三组语义色，未定义 `success`/`success-soft`（绿色仅存在于分组色板 `light-group-green: "#149443"` / `dark-group-green: "#34D27B"`）；`DESIGN.md:489-498` 将 `status-badge-running-light/dark` 绑定到 `accent-soft` + `on-surface`，生成 `src/frontend/src/styles/design_tokens.css:8,244`（`#eef3ff` / `#29344e`）。`src/frontend/src/shared/ui/StatusBadge.tsx:7-24` 将 `TONES.running` 写死为 `"bg-accent-soft text-on-surface"`；对称路径 `src/frontend/src/features/browser-session/EnvironmentSwitcher.tsx:60-71` 的 `statusDotClass("running")` 也将圆点写死为 `bg-accent`。
    2. **深色模式彩色样式与底色分离度缺失**：`StatusBadge.tsx:7-24` 对 `running`、`transition`、`error` 三态全部使用中性字色 `text-on-surface`（深色模式 `#E9ECF3` 近白色），无彩色文字/边框区分；在深色模式下，`SessionHeader.tsx:106` 使用 `bg-surface-raised`（`#2B313C`），而 `StatusBadge` 的 `bg-accent-soft` 为 `#29344E`（浅蓝灰/暗灰蓝），两者亮度对比度仅 **1.05:1**（在 `bg-surface` `#1F232C` 上也仅 **1.27:1**），且无描边，导致视觉上呈“白字浅蓝灰底、几乎与顶栏融为一体”；即便是 `transition`（`#33270F`）与 `error`（`#3A1A18`）也仅靠暗底+白字撑辨识，缺少明确彩色文字/边框。
    3. **工作台顶栏主语被 `sr-only` 隐藏**：`src/frontend/src/features/browser-session/SessionHeader.tsx:114-125` 将 `t("sessObservedState")`（`"状态"`）与 `t("sessTransport")`（`"传输"`）置于 `className="sr-only"` 中，视觉上完全隐藏；`StatusBadge` 仅传入裸词 `t("sessRunning")`（`"运行中"`）与 `t(transportStateLabelKey(transportState))`（`"正常"`/`"恢复中"`/`"失败"`/`"未知"`），缺少“环境”“数据传输”主语（注：`SessionDetailsPanel.tsx:268-270` 已有左列可见 `t("sessTransport")`，`EnvironmentSwitcher.tsx:210` 与 `SessionEntryPage.tsx:98` 紧邻环境名称，均不缺主语，因此应在 `SessionHeader` 侧补齐可见语义主语如“环境运行中”“数据传输正常”及其余各态对应文案，避免破坏详情面板等已有前缀的展示）。
    - 全仓同类位点扫描清单（已确认共 10 处文件，含 11 处 `StatusBadge` 正常态路径 + 2 处 `statusDotClass`）：
        01. `src/frontend/src/shared/ui/StatusBadge.tsx:7-24`（`TONES.running` 使用 `bg-accent-soft text-on-surface`；`transition`/`error` 亦为中性 `text-on-surface` 无彩色文字/边框）
        02. `src/frontend/src/features/browser-session/EnvironmentSwitcher.tsx:60-71,150,206,210`（`statusDotClass("running")` 使用 `bg-accent`，覆盖顶栏触发器圆点 `sess-switcher-trigger-dot` 与下拉项圆点 `switcher-dot-*` 及下拉项 `StatusBadge`）
        03. `src/frontend/src/features/browser-session/SessionHeader.tsx:60-76,114-125`（`observedStatus` + `transportStateTone` 两枚 `StatusBadge` 均为蓝色 `running`，且 `sr-only` 隐藏主语仅显示“运行中”“正常”）
        04. `src/frontend/src/features/profiles/EnvironmentTable.tsx:48,272,279`（环境管理表格 `STATUS_MAP.running`）
        05. `src/frontend/src/features/profiles/EnvironmentCard.tsx:33,100`（环境管理卡片视图复用 `statusDescriptor`）
        06. `src/frontend/src/features/profiles/ProfileDetailPage.tsx:52,116`（环境详情页状态徽标复用 `statusDescriptor`）
        07. `src/frontend/src/features/browser-session/SessionEntryPage.tsx:98`（工作台入口页运行中列表 `<StatusBadge tone="running" label={t("sessRunning")} />`）
        08. `src/frontend/src/features/automation/ProfileAutomationTab.tsx:25,131,145-154`（自动化 Tab 运行态 `stateTone` 与 Supervisor 已配置 `running` 徽标）
        09. `src/frontend/src/features/proxies/ProxyTable.tsx:118`（代理列表表格可用探测 `tone="running"`；注：`p104` 另有代理延迟展示改造，不替代基础 `StatusBadge` 修复）
        10. `src/frontend/src/features/proxies/ProxyListPage.tsx:351`（代理卡片视图可用探测 `tone="running"`）
        11. `src/frontend/src/features/settings/SettingsPage.tsx:148,248`（控制 API 健康状态 `healthy -> "running"`“正常”、平台字体集完整性 `integrity.ok -> "running"`）
        - 已排查非同类位点：`LoginPage.tsx:70`（品牌锁图标圆底 `bg-accent-soft`）、`AppLayout.tsx:207,227`（导航激活态 `bg-accent-soft`）、`Table.tsx:68`（选中行 `bg-accent-soft`）均属强调色常规用法，非状态徽标。
- 测试缺口：
    - 漏过原因：
        1. `src/frontend/src/shared/ui/ui.test.tsx` 完全未覆盖 `StatusBadge`；
        2. `src/frontend/scripts/design_tokens.mjs:273-320` 与 `design_tokens.test.mjs` 仅校验 `DESIGN.md` 组件 `textColor` 对 `backgroundColor` 的内部 WCAG AA 对比度（`#E9ECF3` on `#29344E` = 10.47:1，故通过）及禁止硬编码色值，不校验“正常/运行中”是否属于绿色系，也不校验徽标底色与所在容器底色（如 `#29344E` vs `dark-surface-raised` `#2B313C` = 1.05:1）的辨识度；
        3. 各页面单测（`EnvironmentListPage.test.tsx:414-428`、`ProfileDetailPage.test.tsx:184-202`、`SettingsPage.test.tsx:71`、`ProfileAutomationTab.test.tsx:126-130`、`SessionEntryPage.test.tsx:179`、`EnvironmentSwitcher.test.tsx:204-207`）仅断言文案文本，不检查颜色语义类（`bg-success*` / `text-success` / `border-*`）；
        4. `src/frontend/src/features/browser-session/SessionHeader.test.tsx:216-299` 用 `within(header).getByText(en.sessObservedState)` 与 `getByText(en.sessTransport)` 匹配了 jsdom 下仍存在于 DOM 的 `sr-only` 节点，且显式断言了 `zh.transportStateReady` 为 `"正常"`，把缺少可见主语的缺陷当作预期行为锁定。
    - 应补校验：
        1. `DESIGN.md` / `design_tokens.test.mjs`：校验 `success` / `success-soft` 语义色存在、`status-badge-running-*` 引用 `success-soft` 且深浅模式下各 `status-badge-*` 底色与 `surface` / `surface-raised` 具备明确视觉对比或边框，文本达 WCAG AA；
        2. `src/frontend/src/shared/ui/` 单测：覆盖 `StatusBadge` 四态（`running`、`transition`、`error`、`stopped`）的绿色/琥珀/红色/中性 token 类与彩色文字/边框样式，确保 `running` 不再包含 `bg-accent-soft`；
        3. `EnvironmentSwitcher.test.tsx`：断言 `sess-switcher-trigger-dot` 与 `switcher-dot-*` 在 `running` 态下使用绿色语义类（`bg-success`）而非 `bg-accent`；
        4. `SessionHeader.test.tsx`：更新为断言中英文下可见徽标文本包含主语（如中文 `"环境运行中"`、`"数据传输正常"` 及其余状态组合，而非依赖 `sr-only` 兜底），并断言顶栏两枚 `StatusBadge` 具备明确的彩色样式 token 类；
        5. 其余受影响位点抽检回归（`EnvironmentListPage.test.tsx`、`ProfileDetailPage.test.tsx`、`SettingsPage.test.tsx`、`ProfileAutomationTab.test.tsx`、`ProxyListPage.test.tsx`、`SessionEntryPage.test.tsx`）：补充对运行中/正常/可用状态徽标节点渲染绿色语义类的断言。
- 线索：`.scratch/repro_status_badge_and_session_header.mjs`（执行 `node .scratch/repro_status_badge_and_session_header.mjs` 复现输出：`Dark accent-soft vs surface-raised (SessionHeader bg): #29344e on #2b313c => ratio 1.05:1`、`Has semantic success token in light/dark: false`、`StatusBadge running: bg-accent-soft text-on-surface`、`statusDotClass("running"): bg-accent`、`SessionHeader sr-only keys: [ 'sessObservedState', 'sessTransport' ]` 及 10 处调用文件清单）
- 处理：t073；resolution=transferred；reason=已核实根因与同类位点并聚合并转交 t073（设计系统底座与状态/搜索框重构）
