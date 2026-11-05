# Task spec

## 背景

`docs/plan_20261105_ui_redesign.md` 第 4、5.1、5.2、5.9、5.10 节（D1、D2，用户 2026-11-05 确认）：以根目录 `DESIGN.md`（google-labs-code/design.md alpha 格式）作为唯一设计权威，支持亮色与暗色；信息架构改为「导航侧栏 + 环境列表首页 + 独立会话页」。2026-11-05 于 main@3101540 核实现状：Tailwind 3（`tailwind.config.ts`、`postcss.config.js`），颜色硬编码（`surface-0..4`、`gray-*`、`emerald-*`），只有暗色；`AppLayout.tsx` 侧栏为 Profile 搜索列表；路由为 `/`（会话页，`?profileId=`）、`/profiles/new`、`/profiles/:profileId`、`/profiles/:profileId/files`、`/automation/:profileId`、`/settings`、`/login`（`app/router.tsx`）。plan 已用 `@google/design.md@0.4.0 lint` 实测第 4.2 节的双模式写法合法。设计参考原型位于 `.design_reference/kimi_frontend_demo/`（gitignore，不在 task worktree 中，从主仓目录读取），与 plan 或 `DESIGN.md` 冲突时以后两者为准。

## 契约区

### 范围

- `DESIGN.md`：章节、颜色角色、字体字号、布局间距、圆角、层级、组件清单与 Do's and Don'ts 按 plan 第 4 节；亮暗双模式按 4.2 约定，并写入 Colors 章节的 `### Modes`。
- 生成器与门禁：`src/frontend` 精确固定 `@google/design.md`；`npm run design:tokens` 调用官方解析器生成 `src/styles/design_tokens.css`（Tailwind 4 `@theme` 以亮色为默认值，`.dark` 覆盖全部颜色变量），并在生成前校验 4.8 节列出的规则；生成产物入库；`design:lint`、`design:check` 接入 `scripts/run_gates.sh` 前端阶段。
- Tailwind 4 迁移（`@tailwindcss/vite`），删除 PostCSS、autoprefixer 与 `tailwind.config.ts`；主题只暴露 `DESIGN.md` 生成的 token，重置默认调色板。尚未重做的旧页面在被 t037、t039 替换前失去调色板样式（过渡期不要求可用，用户 2026-11-05）；不设任何豁免机制，全局颜色门禁由 t039 在最后一个旧页面删除时启用。
- 主题运行时：偏好 `system` / `light` / `dark`，默认 `dark`，存 `cbrowser.theme`；`public/theme_boot.js` 以外链经典脚本在 `<head>` 中同步执行，首帧前设置 `<html>` 的 class 与 `color-scheme`，不使用内联脚本；`system` 模式监听 `prefers-color-scheme`。UI 主题与 Profile `color_scheme` 互不影响。
- 字体：Space Grotesk Variable 与 IBM Plex Mono 经 `@fontsource` 随产物自托管；中文回退栈按 4.4 节。
- 应用外壳：导航侧栏（品牌标识；环境、代理、会话、设置；底部显示运行中环境数，并放主题切换、语言切换、退出登录），可折叠为 72px 图标栏，可在 200–360px 间拖宽，状态存 `cbrowser.sidebar.width` / `cbrowser.sidebar.collapsed`；窄屏侧栏改为抽屉；Runtime Coordinator 错误改用警示横幅；保留 iframe 焦点守卫。
- `src/frontend/src/shared/ui/` 基础组件：按钮族、IconButton、Input、Select、SearchField、Checkbox、Switch、StatusBadge、GroupChip、ProtocolChip、RegionCode、Table 原语、EmptyState、Banner、Toast（全局单实例）；Dialog、DropdownMenu、Popover、Tooltip 基于 Radix 原语。
- 路由表按 plan 5.1 定稿，旧路由直接删除；尚未重做的页面先用现有组件挂到新路径（详情 / 文件 / 自动化挂 `/profiles/:profileId/{config,files,automation}`，会话挂 `/session/:profileId`），`/`、`/session`、`/proxies` 在对应 task 交付前为空状态页。
- 登录页与设置页按设计系统重做：外观、语言、系统信息行为不变；新增平台字体区块，按平台列出 t041 字体集目录接口返回的字体集、来源版本、完整性与使用环境数。
- `AGENTS.md` 目录表登记 `DESIGN.md` 与 `.design_reference/`。
- 新增与改动文案 en / zh 同步补键。

### 非范围

- 环境列表、详情、代理库、会话页的新实现（t037、t038、t039）。
- 命令面板。
- 设置页的网络访问区块（t042）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：`DESIGN.md` 官方 lint 为 0 error / 0 warning，两种模式下全部组件的文字与背景组合对比度达 WCAG AA；token 覆盖 plan 4.3–4.6 列出的颜色角色（亮暗成对）、字体、间距、圆角与组件。
- [ ] AC-002：`npm run design:tokens` 由 `DESIGN.md` 确定性生成 `design_tokens.css`；`light-*` 与 `dark-*` 角色集合不同、存在未解析引用，或存在既非 `primary` 又无模式前缀的颜色 token 时，生成失败；入库产物与重新生成结果不一致时 `design:check` 失败；三条命令在 `run_gates.sh` 前端阶段执行。
- [ ] AC-003：Tailwind 默认调色板类在构建中不产生样式；外壳、`shared/ui`、登录页、设置页与样式源码不含 Tailwind 默认调色板类与颜色字面量（扫描命令与结果写入实施笔记）。
- [ ] AC-004：主题三态切换即时生效并持久化；`system` 模式跟随 `prefers-color-scheme` 变化；首次渲染前 `<html>` 已具备目标主题 class 与 `color-scheme`，页面不含内联脚本；切换 UI 主题不改变任何 Profile 的 `color_scheme`。
- [ ] AC-005：侧栏可折叠、可拖宽（200–360px），状态刷新后恢复；所有导航与控件可键盘操作；底部运行中环境数随 SSE 更新；窄屏下侧栏为抽屉。
- [ ] AC-006：Runtime Coordinator 错误以全局警示横幅展示；宿主页内、iframe 之外的点击使 iframe 失焦。
- [ ] AC-007：路由表与 plan 5.1 一致：旧路由（`/?profileId=`、`/profiles/new`、`/automation/:profileId`）不再匹配任何页面；导航与环境链接均为真实 `<a href>`。
- [ ] AC-008：Dialog、DropdownMenu、Popover、Tooltip 具备焦点陷阱与焦点归还、Esc 关闭和正确的 ARIA 角色；Toast 全局只有一个实例（组件测试覆盖）。
- [ ] AC-009：前端构建产物不引用任何外部字体或图标 CDN，字体文件随产物分发（产物扫描）。
- [ ] AC-010：登录页与设置页按设计系统重做后，鉴权、登录跳转、语言切换与系统信息的语义由测试覆盖并通过；设置页平台字体区块的内容与 `GET /api/v1/font-sets` 一致，完整性不一致的字体集显示告警。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 来源：`docs/plan_20261105_ui_redesign.md` WP03、WP08 与第 4、5.1、5.2、5.9、5.10 节（2026-11-05 于 main@3101540 核实，结论见背景）。

### 有意不测

- 视觉还原度（与参考原型逐像素比对）：设计权威是 `DESIGN.md`，以 token 门禁与组件测试约束，不做截图比对。

### 测试策略

- 生成器先写失败用例：角色集合不等、未解析引用、无前缀颜色。
- 组件与路由用 Vitest 走生产组件与生产 `routes`；主题首帧以构建后的 `index.html` 加载顺序测试。
- 旧页面在新路由下的现有测试与 E2E 改为新路径；结构被删除的测试整体删除，并在实施笔记写明理由，不就地改预期。
- 所有浏览器测试无头运行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- `@google/design.md` 当前最新版的程序化 API 与 lint 规则（plan 以 0.4.0 实测）：UNVERIFIED-SPIKE，实施时以精确固定的最新版重跑 4.2 节写法验证。
- Tailwind 4 `@tailwindcss/vite` 与 t033 选定的 Vite 大版本兼容：UNVERIFIED-SPIKE，构建验证。

### 风险与回退

- 风险：上游规范变更导致双模式写法失效；首帧主题脚本被缓存或加载顺序变化后出现闪烁。
- 回退：回退本 task commit。

### 依赖与约束

- 依赖 t033（前端工具链）与 t041（字体集目录接口）；经 t041 串在 t035 之后，避免与 t035 同时修改旧前端文件。
- 遵守 `DESIGN.md` 硬约束：不绘制模拟浏览器框；每个视图最多一个主按钮；状态必须有文字或图标；ID、端口、版本号、种子、host 用 mono 字体；不使用 `DESIGN.md` 之外的颜色值；会话页快捷键不占用 Esc 与会转发给远端的常用组合键。
- 所有浏览器测试无头运行。

### Finalization 时更新的 blueprint

- `docs/blueprint/frontend.md`：全局布局、路由、主题、设计门禁。
- `docs/blueprint/conventions.md`：`DESIGN.md` 落点与业务代码只用语义 token。
- `docs/blueprint/testing.md`：设计门禁。
- `docs/blueprint/decisions.md`：ADR「DESIGN.md 为设计权威与双模式约定」。
- `AGENTS.md`：目录表新增 `DESIGN.md` 与 `.design_reference/`。
- 新建 `docs/specs/ui_design_system.md`。
