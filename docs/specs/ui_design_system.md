# 需求规范：设计系统与应用外壳 (ui_design_system)

## 1. 业务目标与适用范围

本 spec 累积 t036 交付的「以 `DESIGN.md` 为唯一设计权威 + 亮暗双模式 + 导航侧栏应用外壳」契约。前端不再有硬编码颜色，也不再有「顶栏 + Profile 搜索侧栏」的信息架构；路由按 `docs/plan_20261105_ui_redesign.md` 5.1 定稿。关联 task：`docs/tasks/t036_design_system_app_shell/task.md`（AC-001~010）。证据：正式 spike `docs/spikes/s015_design_system_toolchain/report.md`、finding `d034`（工具链版本与双模式写法契约）、`docs/plan_20261105_ui_redesign.md` 第 4 / 5.1 / 5.2 / 5.9 / 5.10 节。非范围：环境列表 / 详情 / 代理库 / 会话页的新实现（t037 / t038 / t039）、命令面板、设置页网络访问区块（t042）。

## 2. 行为契约

### 2.1 设计权威与生成器

- 仓库根 `DESIGN.md`（google-labs-code/design.md alpha 格式，YAML front matter）是唯一颜色 / 字体 / 字号 / 间距 / 圆角 / 组件来源；章节顺序 Overview、Colors（含 `### Modes`）、Typography、Layout、Elevation & Depth、Shapes、Components、Do's and Don'ts。
- `primary` 为模式无关品牌色（由 `brand-mark` 引用）；其余颜色角色以 `light-*` / `dark-*` 成对出现且两套角色名集合完全相同；涉及颜色的组件以 `<component>-light` / `<component>-dark` 成对定义并只引用同模式 token；字体、间距、圆角与模式无关只定义一次。
- `npm run design:tokens` 精确调用 `@google/design.md@0.4.0` 的程序化 `lint()`，生成前校验：`light-*` / `dark-*` 角色集合相同、无未解析引用、不存在既非 `primary` 又无模式前缀的颜色 token；确定性生成 `src/frontend/src/styles/design_tokens.css`（Tailwind 4 `@theme` 以亮色为默认值、`.dark` 覆盖全部颜色变量，另含字体 / 字号 / 圆角 / 间距变量）。产物入库，禁止手改。
- `npm run design:lint`（官方 lint，error 或 warning 任一非零即失败，info 允许）、`npm run design:check`（入库产物与重新生成结果不一致即失败）与 `design:tokens` 三条命令接入 `scripts/run_gates.sh` 前端阶段。生成器失败用例（角色集合不等 / 未解析引用 / 无前缀颜色 / 官方 lint 报错）先红后绿，确定性由测试覆盖。

### 2.2 Tailwind 4 与字体

- `@tailwindcss/vite` 插件替代 PostCSS / autoprefixer / `tailwind.config.ts`；`@theme` 以 `--color-*: initial` 重置默认调色板，只暴露 `DESIGN.md` 生成的语义 token。旧页面在被 t037 / t039 替换前失去调色板样式（过渡期不要求可用），不设豁免机制，全局颜色门禁由 t039 启用。
- UI 字体 Space Grotesk Variable、技术数据字体 IBM Plex Mono 经 `@fontsource` 随产物自托管，中文回退栈 `"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif`；构建产物不引用任何外部字体或图标 CDN，字体文件随产物分发。
- 业务代码（外壳、`shared/ui`、登录页、设置页、手写样式）不含 Tailwind 默认调色板类与颜色字面量；生成产物 `design_tokens.css` 按设计权威含 hex，不列入业务源码扫描。

### 2.3 主题运行时

- 偏好 `system` / `light` / `dark`，默认 `dark`，存 `localStorage` 的 `cbrowser.theme`；三态切换即时生效并持久化；`system` 模式监听 `prefers-color-scheme` 变化并跟随。
- `public/theme_boot.js` 为 `<head>` 中外链经典脚本，首帧前设置 `<html>` 的 `dark` / `light` class 与 `color-scheme`；`index.html` 不含内联脚本。UI 主题与 Profile 的 `color_scheme`（远端网页 `prefers-color-scheme`）互不影响：切换 UI 主题不读写任何 Profile 配置。

### 2.4 应用外壳与路由

- 侧栏：品牌标识；导航项环境 / 代理 / 会话 / 设置；底部运行中环境数随 SSE 更新，并放主题切换、语言切换、退出登录。可折叠为 72px 图标栏，可在 200–360px 间拖宽，状态存 `cbrowser.sidebar.width` / `cbrowser.sidebar.collapsed` 并在刷新后恢复；窄屏（\<1024px）侧栏改抽屉；所有导航与控件可键盘操作，链接均为真实 `<a href>`。
- Runtime Coordinator 错误以全局警示横幅（`role="alert"`）展示；保留 iframe 焦点守卫（宿主页内、iframe 之外的点击使 iframe 失焦）。
- 路由表：`/login`、`/`、`/session`、`/session/:profileId`、`/profiles/:profileId`（重定向 `config`）、`/profiles/:profileId/{config,files,automation,maintenance}`、`/proxies`、`/settings`。旧路由 `/?profileId=`、`/profiles/new`、`/automation/:profileId` 直接删除，不做兼容重定向（`/profiles/new` 显式回落首页 catch-all）。`/`、`/session`、`/proxies` 在对应 task 交付前为空状态页，其余以现有组件挂新路径；会话目标由 path param 决定并写 `sessionStorage` 的 `cbrowser.session.target`。
- `src/frontend/src/shared/ui/` 基础组件：按钮族（primary / secondary / ghost / danger / connect / stop 及 hover / disabled / 小号）、IconButton、Input、Select、SearchField、Checkbox、Switch、StatusBadge、GroupChip、ProtocolChip、RegionCode、Table 原语、EmptyState、Banner、Toast（全局单实例）；Dialog / DropdownMenu / Popover / Tooltip 基于 Radix 原语，具备焦点陷阱、焦点归还、Esc 关闭与正确 ARIA 角色。

### 2.5 登录页与设置页

- 登录页按设计系统换皮，鉴权、登录跳转（含 `next` 目标）、语言切换行为不变。
- 设置页：外观（主题三态）、语言（en / zh）、系统信息（只呈现真实探测对象 Control API 健康检查）、平台字体区块（数据来自 `GET /api/v1/font-sets`，按平台列出字体集、来源版本、完整性与使用环境数；完整性不一致的字体集显示告警）。
- 新增与改动文案 en / zh 同步补键，键集由 en 字典派生、zh 编译期对齐。

## 3. 验收标准（摘要）

完整 AC 与可测试性声明见关联 task `t036`；本 spec 只作需求级累积。

- [x] AC-001：`DESIGN.md` 官方 lint 0 error / 0 warning，两模式全部组件文字与背景组合达 WCAG AA，token 覆盖 plan 4.3–4.6。
- [x] AC-002：`design:tokens` 确定性生成，三条校验失败路径与 `design:check` 不一致失败均覆盖，三条命令接入门禁。
- [x] AC-003：默认调色板类在构建中不产生样式，业务源码不含默认调色板类与颜色字面量（扫描结果入实施笔记）。
- [x] AC-004：主题三态切换即时生效并持久化、`system` 跟随系统、首帧 class 与 `color-scheme`、无内联脚本、不影响 Profile `color_scheme`。
- [x] AC-005：侧栏折叠 / 拖宽（200–360px）/ 刷新恢复、键盘可操作、运行中数随 SSE、窄屏抽屉。
- [x] AC-006：Runtime Coordinator 错误全局警示横幅；iframe 焦点守卫。
- [x] AC-007：路由表与 plan 5.1 一致，旧路由不再匹配，导航为真实 `<a href>`。
- [x] AC-008：Radix 浮层焦点 / ARIA / Esc 与 Toast 全局单实例由组件测试覆盖。
- [x] AC-009：产物无外部字体 / 图标 CDN，字体文件自托管随产物分发。
- [x] AC-010：登录 / 设置页重做后鉴权、跳转、语言、系统信息与平台字体区块（含完整性告警）语义由测试覆盖。
