# 需求规范：设计系统与应用外壳 (ui_design_system)

## 1. 业务目标与适用范围

本 spec 累积 t036 / t047 交付的「以 `DESIGN.md` 为唯一设计权威 + 亮暗双模式 + 导航侧栏应用外壳 + omni 冷灰与 Inter 字体系统」契约、t059 交付的「设计系统门禁扩展：圆角一致性、颜色范围、对比度三类全覆盖与尺寸全面 token 化」契约，以及单用户极简界面重构契约（去除冗余副标题与内部 ID、左下角设置入口、折叠态点击应用图标展开、全表格图标化列表/卡片视图切换、数字输入框暗色模式适配）。关联 task：`docs/tasks/t036_design_system_app_shell/task.md`、`docs/tasks/t047_ui_theme_omni_restyle/task.md`、`docs/tasks/t059_design_token_gates/task.md`。证据：正式 spike `docs/spikes/s015_design_system_toolchain/report.md`、finding `d034`（工具链版本与双模式写法契约）、`docs/plan_20261105_ui_redesign.md` 第 4 / 5.1 / 5.2 / 5.9 / 5.10 节。

## 2. 行为契约

### 2.1 设计权威与生成器

- 仓库根 `DESIGN.md`（google-labs-code/design.md alpha 格式，YAML front matter）是唯一颜色 / 字体 / 字号 / 间距 / 圆角 / 组件来源；章节顺序 Overview、Colors（含 `### Modes`）、Typography、Layout、Elevation & Depth、Shapes、Components、Contrast（t059 新增）、Do's and Don'ts。
- `primary` 为模式无关品牌色（由 `brand-mark` 引用）；其余颜色角色以 `light-*` / `dark-*` 成对出现且两套角色名集合完全相同；涉及颜色的组件以 `<component>-light` / `<component>-dark` 成对定义并只引用同模式 token；字体、间距、圆角与模式无关只定义一次。
- `npm run design:tokens` 精确调用 `@google/design.md@0.4.0` 的程序化 `lint()`，生成前校验：`light-*` / `dark-*` 角色集合相同、无未解析引用、不存在既非 `primary` 又无模式前缀的颜色 token；确定性生成 `src/frontend/src/styles/design_tokens.css`（Tailwind 4 `@theme` 以亮色为默认值、`.dark` 覆盖全部颜色变量，另含字体 / 字号 / 圆角 / 间距变量）。产物入库，禁止手改。
- `npm run design:lint`（官方 lint，error 或 warning 任一非零即失败，info 允许）、`npm run design:check`（入库产物与重新生成结果不一致即失败）与 `design:tokens` 三条命令接入 `scripts/run_gates.sh` 前端阶段。生成器失败用例（角色集合不等 / 未解析引用 / 无前缀颜色 / 官方 lint 报错）先红后绿，确定性由测试覆盖。

### 2.2 Tailwind 4 与字体

- `@tailwindcss/vite` 插件替代 PostCSS / autoprefixer / `tailwind.config.ts`；`@theme` 以 `--color-*: initial` 重置默认调色板，只暴露 `DESIGN.md` 生成的语义 token。
- UI 字体 Inter Variable、技术数据字体 JetBrains Mono Variable 经 `@fontsource` 随产物自托管，中文回退栈 `"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif`；构建产物不引用任何外部字体或图标 CDN，字体文件随产物分发。生成器从 `body-md` 与 `mono-md` 派生字体栈，输出字号、字重、行高与字距变量，并解析 `## Elevation & Depth` 阴影表输出 `--shadow-*` 变量。
- 业务代码（外壳、`shared/ui`、登录页、设置页、手写样式）不含 Tailwind 默认调色板类与颜色字面量；生成产物 `design_tokens.css` 按设计权威含 hex，不列入业务源码扫描。数字输入框（`input[type="number"]`）全局隐藏原生浏览器微调按钮，保证深浅色模式视觉一致。

### 2.3 主题运行时

- 偏好 `system` / `light` / `dark`，默认 `dark`，存 `localStorage` 的 `cbrowser.theme`；三态切换即时生效并持久化；`system` 模式监听 `prefers-color-scheme` 变化并跟随。
- `public/theme_boot.js` 为 `<head>` 中外链经典脚本，首帧前设置 `<html>` 的 `dark` / `light` class 与 `color-scheme`；`index.html` 不含内联脚本。UI 主题与 Profile 的 `color_scheme`（远端网页 `prefers-color-scheme`）互不影响：切换 UI 主题不读写任何 Profile 配置。

### 2.4 应用外壳与路由

- 侧栏：顶部品牌标识与主导航项（环境管理 / 代理管理 / 工作台），左下角底部固定放置「设置」入口（主题切换、语言切换与退出登录统一收纳在设置页内，不在侧栏底部堆砌按钮）。可折叠为 72px 图标栏：展开态显示右侧折叠按钮，**折叠态隐藏折叠/展开按钮，点击左上角应用品牌图标即可展开侧栏**；可在 200–360px 间拖宽（双击分隔条重置默认宽度），状态存 `cbrowser.sidebar.width` / `cbrowser.sidebar.collapsed` 并在刷新后恢复；窄屏（\<1024px）侧栏改抽屉；所有导航与控件可键盘操作，链接均为真实 `<a href>`。
- Runtime Coordinator 错误以全局警示横幅（`role="alert"`）展示；保留 iframe 焦点守卫（宿主页内、iframe 之外的点击使 iframe 失焦）。
- 路由表：`/login`、`/`、`/session`、`/session/:profileId`、`/profiles/:profileId`（重定向 `config`）、`/profiles/:profileId/{config,files,automation,maintenance}`、`/proxies`、`/settings`。旧路由 `/?profileId=`、`/profiles/new`、`/automation/:profileId` 直接删除，不做兼容重定向（`/profiles/new` 显式回落首页 catch-all）。会话目标由 path param 决定并写 `sessionStorage` 的 `cbrowser.session.target`。
- `src/frontend/src/shared/ui/` 基础组件：按钮族（primary / secondary / ghost / danger / connect / stop 及 hover / disabled / 小号）、IconButton、Input、Select、SearchField、Checkbox、Switch、StatusBadge、GroupChip、ProtocolChip、RegionCode、Table 原语、EmptyState、Banner、Toast（全局单实例）；Dialog / DropdownMenu / Popover / Tooltip 基于 Radix 原语，具备焦点陷阱、焦点归还、Esc 关闭与正确 ARIA 角色。

### 2.5 登录页与设置页

- 登录页按设计系统换皮，鉴权、登录跳转（含 `next` 目标）、语言切换行为不变。
- 设置入口（t074 起为侧栏按钮触发的 `SettingsDialog` 宽弹窗，不再是 `/settings` 独立窄页）：外观（主题三态）、语言（en / zh）、控制 API 健康状态与退出登录、只读网络访问信息、平台字体区块（数据来自 `GET /api/v1/font-sets`，展示人类可读字体包名称与本地化平台名称；默认隐去 `source_version` 技术哈希，仅完整性不一致时展开 `problems` 明细）。
- 新增与改动文案 en / zh 同步补键，键集由 en 字典派生、zh 编译期对齐；严格杜绝中文界面下暴露英文枚举值。

### 2.6 设计门禁扩展（t059）

- 章节顺序新增 `## Contrast`（位于 Components 与 Do's and Don'ts 之间，官方 linter 章节序实测允许）：声明 components 之外、代码中直接以 token 类使用的文字对（4.5:1）与图形对（3.0:1），生成器逐对计算；装饰 / 结构元素（divider、scrollbar-thumb、modal-backdrop、session-stage）在该节声明不入对比度对。
- 圆角一致性：Shapes 正文含逐 component 的机读映射表，生成器断言与 components 的 `rounded` 定义逐项一致；DESIGN.md components 的圆角按实现现状全量改齐，代码中的圆角刻度类即 token 引用。
- 对比度门禁三类全覆盖：components 成对 text/bg（官方 linter + 生成器）、仅 textColor 的 component 对同模式 background / surface / surface-raised / surface-subtle 四种底色（4.5:1）、Contrast 表声明对。
- 颜色范围：品牌 token `brand-gradient-start/mid/end`（模式无关）与 `light/dark-brand-ink` 登记入 DESIGN.md；生成器按 token 生成 `public/` 的 logo 与 favicon 五件资产（几何保持原文件、仅颜色取 token 值），`design:check` 校验其新鲜度。颜色扫描扩展到 `public/**/*.{svg,html,js}` 与 `index.html`：`src` 字面量全禁，`public` 字面量必须是 token 值（`public/selkies/` 为 .gitignore 的官方 Selkies vendor 投放目录、自有品牌色，不在扫描内）。
- 组件尺寸规格：components 条目以官方 `height` / `width` / `size` 字段登记尺寸（成对条目同值，生成器 counterpart 断言），导出 `--component-<name>-radius/-height/-width/-size` 变量，React 以 Tailwind 变量简写类消费；图标尺寸阶梯为仅尺寸条目 `icon-xs`（12）/ `icon-sm`（14）/ `icon-md`（16）/ `icon-lg`（20）/ `icon-xl`（24）/ `icon-2xl`（32）/ `icon-3xl`（48）。
- 尺寸 / 间距数值类全禁：源码扫描禁止 p/m/gap/space/w/h/min/max/size/inset/定位/translate 族的数值型类与非 token 任意值（任意值仅允许 `var(--…)` 与 calc/min/max/clamp 组合）；零值与 2px 用 spacing token `none` / `2xs`；布局尺寸走 Container sizes（新增 `dropdown-list`、`badge`、`table-select`、`swatch`）。

### 2.7 系统设置宽弹窗与偏好持久化（t074）

- 侧栏左下角「设置」由 `<Link to="/settings">` 改为 `<button>`，直接在 `AppLayout` 内打开 `SettingsDialog`（`Dialog size="lg"`，两列网格分块），不导航、不离开当前页面上下文；`/settings` 路由改为 `<Navigate to="/" replace />`。弹窗收敛主题 / 语言 / 健康状态 / 退出登录 / 只读网络访问摘要 / 平台字体包，信息分区清晰，默认不堆砌 `source_version` 哈希。
- `theme` / `locale` 持久化于控制面 `settings` 表，经 `GET /api/v1/settings` / `PATCH /api/v1/settings` 读写；`SettingsSync` 置于 `AppProviders` 内（在 `I18nProvider` / `ThemeProvider` 之外）负责登录后 hydrate 与后续写服务端，两个 provider 保持独立、不依赖 auth 与 API client；`localStorage` 仅作 `theme_boot.js` 首帧防闪烁镜像，清缓存或重新登录后偏好保持。
- 工作台 `audioMuted` 持久化到 `sessionStorage` 的 `cbrowser.session.audio_muted.${profileId}`，刷新本标签页保持静音，双标签页打开同 Profile 互不串扰。

## 3. 验收标准（摘要）

完整 AC 与可测试性声明见关联 task `t036`；本 spec 只作需求级累积。

- [x] AC-001：`DESIGN.md` 官方 lint 0 error / 0 warning，两模式全部组件文字与背景组合达 WCAG AA，token 覆盖 plan 4.3–4.6。
- [x] AC-002：`design:tokens` 确定性生成，三条校验失败路径与 `design:check` 不一致失败均覆盖，三条命令接入门禁。
- [x] AC-003：默认调色板类在构建中不产生样式，业务源码不含默认调色板类与颜色字面量（扫描结果入实施笔记）。
- [x] AC-004：主题三态切换即时生效并持久化、`system` 跟随系统、首帧 class 与 `color-scheme`、无内联脚本、不影响 Profile `color_scheme`。
- [x] AC-005：侧栏折叠（折叠态隐藏折叠按钮、点击品牌图标展开）/ 拖宽（200–360px，双击恢复默认）/ 刷新恢复、左下角设置导航、窄屏抽屉。
- [x] AC-006：Runtime Coordinator 错误全局警示横幅；iframe 焦点守卫。
- [x] AC-007：路由表与 plan 5.1 一致，旧路由不再匹配，导航为真实 `<a href>`。
- [x] AC-008：Radix 浮层焦点 / ARIA / Esc 与 Toast 全局单实例由组件测试覆盖。
- [x] AC-009：产物无外部字体 / 图标 CDN，字体文件自托管随产物分发。
- [x] AC-010：登录 / 设置页重做后鉴权、跳转、语言、系统信息与平台字体区块（含可读字体包名称与完整性告警）语义由测试覆盖。

t059 的完整 AC 与可测试性声明见 `docs/tasks/t059_design_token_gates/task.md`，摘要：

- [x] t059 AC-001：圆角一致性门禁（Shapes 表与 components 定义逐项断言），DESIGN 与实现全量改齐。
- [x] t059 AC-002：品牌 token 登记、logo/favicon 五件资产生成器生成并校验新鲜度，颜色扫描扩展至 `public/` 与 `index.html`。
- [x] t059 AC-003：对比度门禁三类全覆盖（成对 / 单 textColor 对四底色 / Contrast 声明表），8 个不达标 token 修正后全量通过。
- [x] t059 AC-004：尺寸规格 components 字段登记 + 组件级变量导出，数值型与非 token 任意值尺寸 / 间距类全仓清零并由门禁拦截。
- [x] t059 AC-005：无视觉回归——构建产物逐类核对新工具类生成与计算值，登录页 headless 截图与基线构建比对（差异仅对比度修正的文字像素）。
