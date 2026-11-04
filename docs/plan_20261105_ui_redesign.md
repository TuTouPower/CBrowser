# CBrowser UI 重设计与配套升级方案

- 文档状态：未来状态方案。决策状态 Accepted（用户 2026-11-05 逐项确认）；实现状态 Not started。
- 基线：main@3f15666（2026-11-05T02:27:06+08:00）。
- 读者：实施各工作包的 agent 与用户。前置知识：`docs/blueprint/architecture.md`、`docs/blueprint/frontend.md`、`docs/blueprint/domain.md`。
- 权威关系：本文只定义目标与拆分。各工作包落地后，当前行为以 `docs/specs/`、`docs/blueprint/` 为准；本文同步修订受影响章节，全部工作包完成后迁入 `docs/archive/`。
- 工作包编号 `WPnn` 是本文内部标识，不是 task 编号；task 由 `.repo_template` 流程创建时另行分配 `tNNN`。

## 1. 目标与范围

### 1.1 目标

1. 前端视觉与交互对齐设计参考原型（见第 13 节），并以根目录 `DESIGN.md` 作为唯一设计权威，支持亮色与暗色两种模式。
2. 前端信息架构从「会话页为首页 + 侧栏 Profile 列表」改为「环境列表为首页 + 导航侧栏 + 独立会话页」。
3. 新增业务能力：独立代理库、环境分组（替换现有 Tag）、环境卡片实时缩略图、指纹平台（windows / macos）与平台字体。
4. 底层框架、工具链、运行时与基础镜像升级到当前最新版本；只保留有事实依据的例外（第 7.2 节）。

### 1.2 不在本方案范围

- 会话页内的模拟浏览器框（标签栏、地址栏、书签、缩放）：违反 ADR 003、ADR 006，远端 CloakBrowser 原生标签与地址栏即为唯一浏览器界面。
- 命令面板。
- 代理连通性与出口 IP 检测：已暂搁为 `docs/pending/parked/p040_proxy_connectivity_exit_ip_check.md`。
- 同窗口多会话分屏：已暂搁为 p039。
- 独立桌面应用打包（不依赖 Docker）：已暂搁为 p041。
- 运行 Profile 数量的容量实测与容器资源上限：用户不要求；软件层面不设数量上限（第 6.10 节）。
- 自动化令牌管理 UI：API 已有，前端无界面，不在本方案范围。

### 1.3 设计输入

- 设计参考原型：`.design_reference/kimi_frontend_demo/`（第 13 节）。
- DESIGN.md 规范：[google-labs-code/design.md](https://github.com/google-labs-code/design.md)，格式版本 `alpha`，CLI `@google/design.md@0.4.0`。规范不支持多模式（上游 issue #13 未决），本方案用第 4.2 节的约定实现双模式。

## 2. 已确认决策

|编号|决策|结论|
|---|---|---|
|D1|设计参考原型入库方式|不入库；放 `.design_reference/kimi_frontend_demo/`，已由 `.gitignore` 的 `/.design_reference/` 忽略|
|D2|设计权威|根目录 `DESIGN.md`（design.md alpha 格式）；亮暗双模式按第 4.2 节约定|
|D3|代理管理|独立代理库：新增 Proxy 实体，Profile 引用代理|
|D4|分组|Tag 整体替换为 Group；每个环境最多属于一个分组；代码与文档不再出现业务 Tag 概念（例外见 6.2）|
|D5|缩略图|做|
|D6|指纹平台|做，支持 windows 与 macos 两种指纹平台|
|D7|浏览器内核|无 key 免费内核（Chromium 146）；cloakbrowser 封装库锁 0.6.4（第 7.2 节）|
|D8|平台字体|Windows 与 macOS 专有字体由 agent 获取（来源见 6.8），只在运行时挂载，不进镜像、不入库|
|D9|旧数据|没有旧用户；schema 直接重写 baseline，不写数据迁移；用户测试数据由 agent 手动迁移|
|D10|技术底层|默认升级到最新版本，包括大版本|
|D11|命令面板、容量实测|不做|
|D12|部署形态|当前只做 Docker 版；将来独立桌面应用与 Docker 版并存（`docs/pending/parked/p041_standalone_desktop_app.md`）。本方案的新增功能在两种形态下实现成本相当时，选择不依赖 Docker 或 Linux 的做法|

## 3. 与现状差异总览

|领域|现状|目标|
|---|---|---|
|前端首页|`/` 为会话页，`?profileId=` 指定目标|`/` 为环境列表；会话页为 `/session/:profileId`|
|侧栏|Profile 搜索列表|导航侧栏：环境、代理、会话、设置；可折叠、可拖宽|
|样式|Tailwind 3 工具类 + 硬编码颜色（`surface-0..4`、`gray-*`、`emerald-*`），仅暗色|Tailwind 4 + 由 `DESIGN.md` 生成的语义 CSS 变量；亮色、暗色、跟随系统|
|分组|`profile_tags` 表，每个 Profile 多个自由字符串，颜色未使用|全局 Group 实体，单值引用，颜色取自设计调色板|
|代理|`Profile.proxy` 单 URL 字段，API 原样回显（含账密）|Proxy 实体；Profile 引用 `proxy_id`；密码只写不回显|
|配置版本|任何 PATCH 都生成新版本，改名也提示「待应用并重启」|只有运行配置变化才生成新版本|
|最后活跃|无|运行时记录最后启动与最后停止时间|
|浏览器版本|无真实上报|Runner 经 CDP 取版本与 UA 并上报|
|缩略图|`capture_preview` 字段存在但无实现|Runtime Agent 经 CDP 定时截取当前页面，API 提供预览图|
|指纹平台|`--fingerprint-platform=windows` 写死（`runner.py`）|Profile 字段 `fingerprint_platform`：windows / macos|
|字体|镜像只有 `fonts-liberation`，另有可选文泉驿 `font_bundle`|基础开源字体入镜像；平台字体运行时只读挂载；按指纹平台隔离可见字体|

## 4. 设计系统（DESIGN.md）

### 4.1 文件与格式

- 位置：仓库根目录 `DESIGN.md`。文件名大写属于社区约定例外。
- 章节严格按规范顺序：Overview、Colors、Typography、Layout、Elevation & Depth、Shapes、Components、Do's and Don'ts。
- token 写在 YAML front matter；章节正文写设计理由与使用规则。
- 颜色值统一用 hex（规范推荐），半透明用 8 位 hex。

### 4.2 亮暗双模式约定

已用 `@google/design.md@0.4.0 lint` 实测：下列写法合法，前缀 token 正常解析，亮暗组件分别做 WCAG 对比度检查，无 `unknown-key` 与 `orphaned-tokens` 警告；程序化 API `lint()` 返回已解析的 hex 与 RGB 通道。

1. 与模式无关的颜色：`primary`（品牌色，规范要求必须存在），由 `brand-mark` 组件引用。
2. 模式语义颜色：`light-<role>` 与 `dark-<role>` 成对出现，两套角色名集合必须完全相同。
3. 组件：凡涉及颜色的组件成对定义为 `<component>-light` 与 `<component>-dark`，各自引用同模式 token。状态变体写作 `<component>-<state>-light` / `<component>-<state>-dark`。
4. 字体、间距、圆角与模式无关，只定义一次。
5. 约定写入 `DESIGN.md` 的 Colors 章节正文（`### Modes` 小节），使其他工具与 agent 能读懂。
6. 上游规范将来正式支持多模式时，只改 token 写法与生成器，业务代码不变。

### 4.3 颜色角色与初稿值

初稿由参考原型的 oklch 值换算为 hex。亮色模式下原型的 `accent`、`danger`、`warning` 对比度不达 WCAG AA（文字在 surface 上分别为 4.15、4.01、4.44），初稿已降低亮度修正。最终值以 WP03 的 lint 结果为准。

|角色|用途|light|dark|
|---|---|---|---|
|`background`|页面底色|`#F0F5F1`|`#080E0A`|
|`surface`|卡片、表格、面板|`#F7FBF8`|`#0E1411`|
|`surface-raised`|弹窗、浮层|`#FDFFFD`|`#141B17`|
|`surface-subtle`|表头、次级区块|`#E9EEEA`|`#1B231E`|
|`surface-hover`|悬停|`#E2E9E4`|`#232B26`|
|`sidebar`|侧栏底色|`#E7EDE9`|`#050A07`|
|`stage`|会话画面区背景|WP03 定|WP03 定|
|`on-surface`|主文字|`#0D1611`|`#E6EDE8`|
|`on-surface-muted`|次级文字|`#48534C`|`#A1ABA4`|
|`on-surface-subtle`|三级文字、占位|`#656F69`|`#858F88`|
|`outline`|边框|`#D3DCD6`|`#242C28`|
|`outline-strong`|强边框、滚动条|`#BAC4BD`|`#38433C`|
|`accent`|唯一强调色：主操作、选中、运行中|`#006EDC`|`#49A9FF`|
|`accent-soft`|强调底色|`#DAEEFF`|`#112A43`|
|`on-accent`|强调色上的文字|`#F8FAFD`|`#021020`|
|`danger`|危险操作、错误|`#D02C2E`|`#F66D64`|
|`danger-soft`|危险底色|`#FFE6E2`|`#391A17`|
|`warning`|过渡态、提示|`#A76100`|`#EBAE42`|
|`warning-soft`|提示底色|`#FBEDD1`|`#33230A`|
|`overlay`|遮罩|`#050B0785`|`#010201BD`|
|`focus`|焦点环|同 `accent`|同 `accent`|
|`group-<hue>`|分组色，8 个色相：slate、blue、teal、green、amber、orange、red、violet|WP03 定|WP03 定|

状态色语义：running 用 `accent`；starting、stopping 用 `warning` 并带脉冲；error 用 `danger`；stopped 用 `on-surface-subtle`。状态必须同时有文字，不能只靠颜色。

### 4.4 字体与字号

- UI 字体：Space Grotesk Variable；技术数据字体：IBM Plex Mono。均经 `@fontsource` 随前端产物自托管，不访问外部 CDN。
- 中文回退栈：`"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif`。
- 最小字号 11px；唯一例外是 mono 大写表头 10px（带字距）。原型的 11px 表格正文、9px 表头、8px 国家码不沿用。

|token|字体|字号/字重/行高|用途|
|---|---|---|---|
|`headline-lg`|Space Grotesk|24px / 600 / 1.25，字距 -0.02em|页面标题|
|`headline-md`|Space Grotesk|18px / 600 / 1.3|弹窗、区块标题|
|`title-sm`|Space Grotesk|14px / 600 / 1.4|卡片标题|
|`body-md`|Space Grotesk|13px / 400 / 1.5|默认正文|
|`body-sm`|Space Grotesk|12px / 400 / 1.5|表格单元、次级说明|
|`label-md`|Space Grotesk|12px / 550 / 1|按钮、导航|
|`label-sm`|Space Grotesk|11px / 500 / 1.2|状态标签、字段标签|
|`mono-md`|IBM Plex Mono|12px / 400 / 1.4|ID、host:port、版本号、种子|
|`mono-caps`|IBM Plex Mono|10px / 500 / 1，字距 0.04em，大写|表头|

### 4.5 布局、间距、圆角与层级

- 间距基准 4px：`xs 4`、`sm 8`、`md 12`、`lg 16`、`xl 24`、`2xl 32`。
- 侧栏：默认 232px，可拖宽 200–360px，折叠为 72px 图标栏；状态存 localStorage（`cbrowser.sidebar.width`、`cbrowser.sidebar.collapsed`）。
- 页面内容最大宽度 1600px，内边距 24px（窄屏 16px）。
- 控件高度：常规 36px，小号 30px；表格行高 56px。
- 圆角：`sm 4`（状态标签、分组标签）、`md 7`（按钮、输入框）、`lg 10`（表格、卡片）、`xl 13`（弹窗）、`full`。
- 层级：用深浅不同的底色与边框区分，阴影只用于浮层（popover、弹窗、toast）。规范 alpha 没有阴影 token，阴影精确值写在 Elevation & Depth 正文，由 WP03 落到 Tailwind 主题。
- 动效：160–200ms ease-out；遵守 `prefers-reduced-motion`。
- 响应式：桌面优先（≥1024px）；窄屏侧栏改抽屉，表格隐藏次要列。

### 4.6 组件清单

每个组件在 `DESIGN.md` 中按 4.2 约定成对定义：

- 按钮：`button-primary`、`button-secondary`、`button-ghost`、`button-danger`、`button-connect`（打开会话）、`button-stop`；各自 hover、disabled 变体；小号尺寸。
- `icon-button`、`input`、`select`、`search-field`、`checkbox`、`switch`。
- `nav-item`、`nav-item-active`、`sidebar`。
- `table-header`、`table-row`、`table-row-selected`、`card`、`environment-card`。
- `status-badge-running` / `-transition` / `-error` / `-stopped`、`group-chip`、`protocol-chip`、`region-code`。
- `modal`、`popover`、`menu-item`、`toast`、`tooltip`、`empty-state`、`banner-warning`、`banner-danger`。
- `session-header`、`session-stage`、`session-details-panel`。
- `brand-mark`。

### 4.7 Do's and Don'ts（硬约束）

- 不绘制任何模拟浏览器框；会话画面区只承载 Selkies iframe。
- 每个视图最多一个 `button-primary`。
- 状态必须有文字或图标，不能只靠颜色。
- ID、端口、版本号、种子、host 一律用 mono 字体。
- 两种模式下所有文字与背景组合达到 WCAG AA（正文 4.5:1）。
- 不引用外部字体或图标 CDN。
- 不使用 `DESIGN.md` 之外的颜色值；业务代码只用语义 token。
- 会话页快捷键不得占用 Esc，以及会转发给远端浏览器的常用组合键。

### 4.8 生成器与门禁

- 依赖：`src/frontend` devDependencies 精确固定 `@google/design.md`（当前 0.4.0）。
- `npm run design:tokens`：调用官方解析器读取 `DESIGN.md`，生成 `src/frontend/src/styles/design_tokens.css`：
    - Tailwind 4 `@theme` 块：亮色值作为默认值，另加字体、字号、圆角、间距变量。
    - `.dark` 选择器下覆盖全部颜色变量。
    - 生成前校验：`light-*` 与 `dark-*` 角色集合相同；无未解析引用；不存在既非 `primary` 又无模式前缀的颜色 token。
- 生成产物入库，参照 OpenAPI 生成类型的做法。
- `npm run design:lint`：官方 lint，error 或 warning 任一非零即失败（info 允许）。
- `npm run design:check`：重新生成并与入库产物比对，不一致即失败。
- 三条命令接入 `scripts/run_gates.sh` 的前端阶段。

### 4.9 主题运行时

- 偏好：`system` / `light` / `dark`，默认 `dark`；存 localStorage `cbrowser.theme`，与 `cbrowser.locale` 同一模式。
- `public/theme_boot.js`：在 `<head>` 中以外链经典脚本同步执行，首帧前设置 `<html class="dark">` 与 `color-scheme`；不使用内联脚本，以便将来启用 CSP。
- `system` 模式下监听 `prefers-color-scheme` 变化。
- UI 主题与 Profile 的 `color_scheme`（远端网页的 `prefers-color-scheme`）互不影响。

## 5. 信息架构与页面

### 5.1 路由

|路由|页面|说明|
|---|---|---|
|`/login`|登录|—|
|`/`|环境列表|首页|
|`/session`|会话入口|本标签页无目标时，列出运行中的环境供选择|
|`/session/:profileId`|会话页|每个 Chrome 标签页独立目标（沿用 frontend.md 第 2 节的页面独立状态规则）|
|`/profiles/:profileId`|环境详情|重定向到 `config` 标签|
|`/profiles/:profileId/config`|详情：配置|—|
|`/profiles/:profileId/files`|详情：文件|原 Artifact 页|
|`/profiles/:profileId/automation`|详情：自动化|原 `/automation/:profileId`，并入人工/Agent 控制面板|
|`/profiles/:profileId/maintenance`|详情：维护|复制、重置、删除|
|`/proxies`|代理库|—|
|`/settings`|设置|—|

- 旧路由（`/?profileId=`、`/profiles/new`、`/automation/:profileId`）直接删除，不做重定向。
- 列表、切换器、会话入口中的环境链接一律用真实 `<a href>`，Cmd/Ctrl/中键点击由 Chrome 原生打开新标签页（ADR 003）。

### 5.2 全局布局

- 侧栏：品牌标识（现有 CBrowser logo + 加字距的文字标识）；导航项为环境、代理、会话、设置；底部显示运行中环境数量，并放主题切换、语言切换、退出登录。
- 「会话」导航：本标签页已有会话目标时回到该会话，否则进入 `/session`。
- 全局横幅：Runtime Coordinator 错误（`runtime-coordinator-error`）保留，改用 `banner-warning` 样式。
- 保留 iframe 焦点守卫：宿主外部点击时 `blur()` iframe（d028）。
- 基础组件放 `src/frontend/src/shared/ui/`；Dialog、DropdownMenu、Popover、Tooltip 基于 Radix 原语，不手写焦点陷阱。
- Toast：全局单实例，动作结果与批量汇总经此展示。

### 5.3 环境列表（`/`）

- 工具栏：搜索（名称、备注、代理名）；状态筛选（全部、运行中、已停止、异常）；分组筛选（全部、未分组、各分组；底部「管理分组…」打开分组管理弹窗）；列表/卡片切换（存 `cbrowser.environments.layout`）；排序（手动顺序、名称、最近活跃、创建时间）；主按钮「新建环境」。
- 列表列：

|列|内容|
|---|---|
|选择|复选框；表头全选当前筛选结果|
|名称|名称；备注首行（次级文字）|
|分组|`group-chip`；未分组显示「—」|
|网络|代理名、协议、地区；无代理显示「直连」并带警示样式（真实 IP 暴露）|
|指纹|平台图标、语言与时区；`geoip` 开启时显示「随代理」|
|状态|五态 `status-badge`；error 悬停显示原因|
|最后活跃|运行中显示已运行时长；否则显示最后停止的相对时间|
|操作|主操作：运行中「打开」、已停止「启动」；次操作：停止、编辑（进详情配置页）、复制、删除|

- 卡片视图：缩略图（16:9，第 6.7 节）、名称、状态、分组、网络、平台，以及同样的操作。
- 批量操作（选中后出现浮动条）：启动、停止、移动到分组、删除。前端逐个调用现有单项 API，每项使用独立幂等键；结束后 toast 汇总「成功 n，失败 m」，失败项保持选中。
- 实时状态：沿用 SSE `runtime_state` 增量合并。
- 空状态：无环境时引导新建；筛选无结果时提供「清除筛选」。

### 5.4 新建环境弹窗

- 宽弹窗，分区：
    - 基本：名称（必填）、分组（下拉，可就地新建）、备注。
    - 网络：代理（代理库下拉或「直连」）、`geoip`、时区、语言。
    - 指纹：平台（windows / macos，附平台字体状态提示）、种子（显示当前值，「随机生成」重新生成）、GPU（auto / nvidia / intel）、屏幕分辨率（预设加自定义）、`color_scheme`。
    - 高级（默认折叠）：其余运行配置字段（humanize、human_preset、clipboard_sync、auto_launch、allow_3p_cookies、set_google_default、restore_session、transparent_proxy、portable_cookies、capture_preview、launch_args、extension_paths）。
- 提交按钮：「创建」与「创建并启动」。

### 5.5 环境详情页

- 页头：名称、状态、分组；操作：打开会话、启动或停止。
- 全标签共用提示条：默认搜索初始化失败（含重试，沿用现有 API）；运行配置待应用（含「应用并重启」，沿用现有阶段跟踪语义）。
- `config`：字段分区与新建弹窗一致；只改元数据（名称、分组、备注、排序）时不出现待应用提示。
- `files`：现有 Artifact 管理能力换皮。
- `automation`：现有自动化状态与人工/Agent 控制面板换皮。
- `maintenance`：复制（仅配置 / 含浏览器状态，运行中禁用后者）、重置（列出将清除的 Cookie、站点数据、缓存、登录状态与指纹身份，说明保留设置与 Artifact）、删除。

### 5.6 会话页（`/session/:profileId`）

- 页头（单行）：
    - 环境切换器：popover 内可搜索，按分组列出环境与状态；条目为链接。
    - 状态：observed state 与 transport 状态。
    - 待应用标记与「应用并重启」。
    - 操作：音频、诊断、详情面板、专注模式、停止。
- 画面区：Selkies iframe 铺满。非 `connected` 阶段显示居中状态面板与可执行操作，沿用 frontend.md 第 4 节全部会话阶段与恢复语义。
- 详情面板（右侧 300px，默认收起，状态存 `cbrowser.session.details_open`）：
    - 环境：名称、分组、备注。
    - 网络：代理名、协议、地区、`geoip`。
    - 指纹：平台、平台字体状态、种子、语言、时区、屏幕、GPU、浏览器版本与 UA（WP07）。
    - 运行：实例 ID、配置版本、transport 状态、最近错误、启动时间。
    - 每个值可复制。
- 专注模式：隐藏侧栏与页头；顶部边缘悬停显示悬浮工具条，提供退出按钮。不使用 Esc 退出。
- 剪贴板权限提示、音频状态、诊断浮层沿用现有实现并换皮。
- 保留现有 `data-testid`：`browser-session-iframe`、`session-*` 系列。

### 5.7 代理库（`/proxies`）

- 工具栏：搜索（名称、host、地区）、协议筛选、主按钮「添加代理」。
- 列：名称；协议；地址（`host:port`，mono）；认证（有/无）；地区（国家码 + 标签）；使用环境数（点击跳转到按该代理筛选的环境列表）；操作（编辑、删除）。
- 删除：被引用时按钮禁用并提示先改绑；后端同时以 409 拒绝。
- 添加/编辑弹窗：
    - 字段：名称、协议（http / https / socks5）、host、端口、用户名、密码、国家码、地区标签、备注。
    - 密码只写：编辑时显示「已设置，留空不修改」，并提供「清除密码」。
    - 「从 URL 粘贴」：解析 `scheme://user:pass@host:port` 填入各字段。
    - socks5 加认证时显示提示：Chromium 不支持带认证的 SOCKS5（是否被 CloakBrowser 绕过待验证，见第 12 节）。

### 5.8 分组管理弹窗

- 列出分组：色块、名称、使用环境数。
- 操作：新建、改名、改色（8 色调色板）、拖动排序、删除（确认框显示受影响环境数，删除后这些环境变为未分组）。

### 5.9 设置页（`/settings`）

- 外观：主题（跟随系统、亮色、暗色）。
- 语言：en / zh。
- 系统信息：应用版本、浏览器内核版本、Selkies 版本、Control API 健康状态（只呈现真实探测对象，沿用现有规则）。
- 平台字体：Windows、macOS 字体集的检测结果（WP15）。

### 5.10 登录页

按设计系统换皮，行为不变。

### 5.11 文案与术语

- 中文界面用「环境」，英文界面用「Profile」；代码与领域标识保持 `Profile`，并在 `domain.md` 增加术语对照。
- 新增与改动文案 en/zh 同步补键，沿用 `i18n.tsx` 的键集对齐机制。

## 6. 后端与数据模型

### 6.1 Schema baseline 重写

- 依据 D9：直接改写 `src/backend/migrations/versions/0001_initial_schema.py` 为目标 schema，不新增增量迁移。本方案所有 schema 变更（6.2–6.8）都并入 baseline。
- 执行前备份 `data/v2/cbrowser.db` 与用户实例数据目录，并确认备份可读；重建后手动迁移用户测试数据（当前本地为 2 个 Profile、0 条 tag）。
- 只处理用户本人实例；其他会话或 task 创建的部署实例（例如 `cbrowser-t032*`）不碰。
- 在 `decisions.md` 记录该策略及其失效条件：出现真实用户后，迁移恢复为只追加。

### 6.2 Group（替换 Tag）

- 表 `profile_groups`（避开 SQLite 的 `GROUPS` 关键字）：`id`、`name`（唯一，1–64 字符）、`color`（调色板键：slate、blue、teal、green、amber、orange、red、violet）、`sort_order`、`created_at`、`updated_at`。
- `profiles.group_id`：可空，外键 `ON DELETE SET NULL`。
- API：`GET/POST /api/v1/groups`、`PATCH/DELETE /api/v1/groups/{group_id}`；Profile 创建与 PATCH 接受 `group_id`；`ProfileResponse` 返回 `group_id`。
- 分组属于元数据（6.4），变更不生成配置版本。
- 删除全部 Tag 相关实现：`Tag` 模型、`profile_tags` 表、请求与响应中的 `tags` 字段、快照中的 tags、前端逗号分隔输入、`tagsCommaSeparated` 等文案键，以及 FastAPI `APIRouter(tags=["v1"])` 参数（生成的 OpenAPI 不再含 tags）。
- 仍会出现 tag 字样的范围仅限：`docs/archive/**` 与 `docs/reviews/**` 的历史记录；含义不同的用法（Docker 镜像 tag、git tag、HTML 元素与 `tagName`）；`.repo_template/` 工具链。

### 6.3 Proxy

- 表 `proxies`：`id`、`name`（唯一）、`scheme`（http / https / socks5）、`host`、`port`、`username`（可空）、`password`（可空）、`country_code`（ISO 3166-1 alpha-2，可空）、`region_label`（可空）、`notes`、`created_at`、`updated_at`。
- `profiles.proxy_id`：可空，外键 `ON DELETE RESTRICT`。删除 `Profile.proxy` URL 字段。
- API：`GET/POST /api/v1/proxies`、`GET/PATCH/DELETE /api/v1/proxies/{proxy_id}`。
    - 响应不含 `password`，改为 `has_password`；另返回 `used_by_count`。
    - PATCH `password`：缺失表示不变；`null` 表示清除；字符串表示设置。
    - 删除被引用的代理返回 409，错误码 `proxy_in_use`，附引用数量。
- 配置版本快照保存 `proxy_id` 与解析后的完整代理参数（运行时以快照为准，保持「快照即运行内容」语义）。
- 编辑代理的运行相关字段（scheme、host、port、username、password）时，为每个引用它的 Profile 生成新配置版本；运行中的 Profile 显示待应用。名称、地区、备注等元数据不触发。
- `GET /profiles/{id}/versions` 与 `/versions/{version}` 的响应对代理密码脱敏。
- 凭据存储级别与现状一致（SQLite 明文，现状为 URL 内嵌账密）；不得进入日志、错误信息与 SSE 事件。

### 6.4 元数据与运行配置拆分

- 元数据：`name`、`notes`、`sort_order`、`group_id`。直接写 `profiles` 表，不生成配置版本。
- 运行配置：其余影响浏览器运行的字段（含 `proxy_id` 解析结果与 `fingerprint_platform`）。只有值实际变化时才生成新版本；提交相同值不生成新版本。
- 待应用提示仅由运行配置版本差异驱动。
- 修复的缺陷：现状下任何 PATCH 都无条件生成新版本（`adapters/database/repository.py` 的 update 路径），导致运行中的环境仅改名也提示重启。

### 6.5 运行时活动时间

- `profile_runtimes` 新增 `last_started_at`（observed 进入 running 时写入）、`last_stopped_at`（进入 stopped 或 error 时写入），ISO 8601 带时区。
- 经 `ProfileRuntimeResponse` 与 SSE `ProfileRuntimeStatusEvent` 下发；前端校验规则与现有 `search_defaults`、`transport` 同构。

### 6.6 浏览器版本上报

- Runner 在 ready 时经 CDP `Browser.getVersion` 取 product 与 userAgent。
- Agent `/health` 增加 `browser` 字段；Supervisor 沿现有健康状态链路传给 API；`ProfileRuntimeResponse` 增加 `browser_product`、`browser_user_agent`。
- 具体传递链路在 WP07 开始时读代码确认（第 12 节待验证项）。

### 6.7 缩略图

- 采集：Runtime Agent 在 running 且 `capture_preview=true` 时，每 15 秒经已有的 CDP 连接对当前活动标签页调用 `Page.captureScreenshot`（JPEG，质量 70，缩放到宽 480px）。只截网页区域，不含浏览器标签栏与地址栏。选择 CDP 而不是 X11 截图，是因为 CDP 在 Docker 与将来的独立桌面应用（p041）中都可用。截图对页面行为的影响（例如后台标签页、焦点）待 WP13 验证。
- 存储：原子写入 Profile 专属目录下的 `preview/latest.jpg` 与元数据（`captured_at`、`runtime_instance_id`），权限 0600；停止后保留最后一帧。
- 传给 API：沿用 Artifact 的 Agent → Supervisor → API 转发模式；具体通道在 WP13 读 `supervisor/artifact_forwarder.py` 与 `api/internal_artifacts.py` 后确定。
- API：`GET /api/v1/profiles/{profile_id}/preview` 返回 `image/jpeg`，`Cache-Control: no-store`，ETag 取 `captured_at`；无预览返回 404。
- SSE 新增 `profile_preview` 事件（`profile_id`、`captured_at`）；前端以 `captured_at` 作为图片 URL 版本参数刷新。
- 隐私：截图视同 Cookie 级私密数据，不进日志；重置或删除 Profile 时清除；`capture_preview` 改为 false 时停止采集并删除已有预览。

### 6.8 指纹平台与平台字体

- 字段：`fingerprint_platform`，取值 `windows` / `macos`，默认 `windows`，属于运行配置。Runner 用该字段替换写死的 `--fingerprint-platform=windows`。CloakBrowser 只支持这两种指纹平台，没有 Linux 指纹平台。
- 字体分层：
    - 基础开源字体（CloakBrowser 文档列出的最低要求）进入 Browser 镜像：`fonts-noto-color-emoji`、`fonts-freefont-ttf`、`fonts-unifont`、`fonts-ipafont-gothic`、`fonts-wqy-zenhei`、`fonts-tlwg-loma-otf`。
    - 平台字体放在宿主 `data/fonts/windows/` 与 `data/fonts/mac/`（`data/` 已被忽略），Supervisor 只读挂载进 Browser 容器（例如 `/opt/cbrowser-platform-fonts/{windows,mac}`，位于 fontconfig 默认扫描路径之外）。
    - Runner 为每个 Profile 生成 `FONTCONFIG_FILE`（扩展现有 `runtime_agent/fontconfig.py`），只暴露该指纹平台的字体集以及 spike 认定的基础字体；Liberation 等 Linux 专属字体对两种指纹平台都不可见。
- 现有 `font_bundle`（文泉驿）字段：两种指纹平台都有原生 CJK 字体（微软雅黑、宋体；苹方、冬青黑体），文泉驿本身会成为 Linux 特征。WP14 确认后删除该字段与镜像中的字体包。
- 字体完整性：Agent 用 Profile 的 fontconfig 检查 CloakBrowser 的检测字体清单（Windows 8 个、Office 10 个、Mac 20 个），结果经 runtime 状态与设置页呈现；缺失时 UI 告警，不阻断启动。
- 字体来源（只用官方渠道，不使用第三方字体站或 GitHub 镜像，原因是授权与文件来源无法校验）：
    - Mac：从本机复制 `/System/Library/Fonts`、`/System/Library/Fonts/Supplemental`、`/Library/Fonts`，以及 `/System/Library/AssetsV2/` 下的苹方资源。已核对本机：前两个目录分别有 83、290 个文件，Mac 检测字体清单中的字体齐全。
    - Windows：下载微软官方 Windows 11 企业评估版 ISO（约 6 GB，暂存 `.scratch/`），用本机 `7zz`（`/opt/homebrew/bin/7zz`）从 `sources/install.wim` 提取 `Windows/Fonts`。
- 字体不进入任何镜像，不进入仓库；部署与发布脚本不得 COPY 该目录。

### 6.9 API 变更清单

|变更|接口|
|---|---|
|新增|`/api/v1/groups`、`/api/v1/groups/{group_id}`|
|新增|`/api/v1/proxies`、`/api/v1/proxies/{proxy_id}`|
|新增|`GET /api/v1/profiles/{profile_id}/preview`|
|改|Profile 创建、PATCH、PUT 与响应：删除 `tags`、`proxy`、`font_bundle`；新增 `group_id`、`proxy_id`、`fingerprint_platform`|
|改|`ProfileRuntimeResponse` 与 SSE 事件：新增 `last_started_at`、`last_stopped_at`、`browser_product`、`browser_user_agent`、平台字体状态；新增 `profile_preview` 事件|
|改|配置版本接口：代理密码脱敏|
|删|OpenAPI 中的 `tags` 分组元数据|

所有变更经 `schemas/openapi/cbrowser_v1.json` 导出，前端 `npm run generate:api` 重新生成类型。

### 6.10 并发数量

代码中没有运行 Profile 数量上限。资源池上限：媒体子网池 `10.251.0.0/16` 按每个运行中的 Profile 一个 /24 切分（约 256 个）；UDP mux 端口池 `30000–30991`（992 个）。无 key 免费内核没有并发数限制。本方案不改变这些上限。

## 7. 技术底层升级

### 7.1 升级清单

版本基线取自 2026-11-05 的 npm、PyPI 与 GitHub。目标版本记入 `decisions.md`，不写进行为 AC。

|组件|当前|目标|待验证点|
|---|---|---|---|
|Tailwind CSS|3.4.19|4.3.4（`@tailwindcss/vite`）|与 WP03 合并；删除 postcss、autoprefixer 与 `tailwind.config.ts`|
|Vite|6.4.1|8.3.5|Rolldown 下 `vite.selkies.config.ts` 仍须产出经典 IIFE，`verify_frontend_dist.py` 通过|
|@vitejs/plugin-react|4.7.0|6.2.1|随 Vite 8|
|Vitest|4.1.0|5.1.0|配置变更|
|TypeScript|5.7.3|7.0.2|`openapi-typescript` 7.13 的 peer 为 `typescript ^5.x`，并依赖 TS 编译器 API；不兼容时退到 6.0.3|
|React / ReactDOM|19.2.4|19.3.1|—|
|路由|`react-router-dom` 7.18.5|`react-router` 8.5.1|v8 破坏性变更对照 changelog|
|lucide-react|0.468.0|1.68.0|图标改名|
|jsdom / @testing-library/jest-dom / @types/node|28 / 6 / 24|30 / 7 / 26|`NODE_OPTIONS=--no-experimental-webstorage` 是否仍需要|
|@tanstack/react-query|5.105.0|5.105.3|—|
|Node（宿主构建）|24|26 LTS|`package.json` 增加 `engines`|
|Python|镜像 3.12；本地 venv 3.14；`run_gates.sh` 固定 3.12|3.15|已核对 19 个原生依赖均有 cp315 aarch64 wheel 或 abi3/纯 Python 兜底；`pyproject.toml` 的 `requires-python` 同步|
|基础镜像|Debian 12 bookworm|Debian 13 trixie（`python:3.15-slim-trixie`，digest 固定）|Browser、Stream 镜像 apt 包名变化|
|SQLAlchemy / Alembic / aiosqlite|2.0.43 / 1.16.5 / 0.21.0|2.1.8 / 1.20.1 / 0.22.1|2.1 移除的弃用用法；异步路径回归|
|依赖声明|`pyproject.toml` 下限、`src/backend/requirements.txt`（遗留原生打包，无引用）、各镜像精确版本|`uv.lock` 单一来源，各镜像 requirements 由 `uv export` 生成；删除遗留文件|—|
|Caddy|`caddy:2.8-alpine`|2.11.8|Caddyfile 语法与 `tls internal` 行为|
|Selkies|2.1.0（ADR 固定）|2.2.1|适配层 HELLO / `resume_key` / Web Locks、`x11_keymap` 私有 ABI 校验（当前钉 2.1.0）、官方 Web 客户端 SHA 清单；修订 ADR|
|fastapi、uvicorn、pydantic、websockets、aiohttp、docker、httpx、playwright|—|已是最新|—|

### 7.2 例外：cloakbrowser 封装库锁 0.6.4

- 0.6.4 有三种模式：无 key（旧版免费内核 Chromium 146，不校验 license、不限制并发数）、免费 key（最新内核，1 个并发会话）、Pro（最新内核，多个并发）。当前使用无 key 模式。
- 0.7.0 的 `ensure_binary` 删除了无 key 路径：没有 key 时自动申领免费 key，结果只允许 1 个并发会话，会破坏多 Profile 并发。
- 结论：锁定 0.6.4，在 `decisions.md` 记录原因与复查条件（上游恢复无 key 路径，或用户改用 Pro）。
- 风险：146 内核下载依赖上游 GitHub release 资源长期可用。引擎缓存（`/data/engine-cache`）纳入备份；必要时用 `CLOAKBROWSER_BINARY_PATH` 指向本地二进制。

## 8. 工作包

每个工作包由 `/task-create` 建成一个或多个 task；带 spike 的先经 `.repo_template/scripts/spikes.py new` 取证。下文 AC 为草案，建 task 时按模板改写为 `AC-NNN`。

### WP01 前端工具链升级

- 范围：7.1 节前端各项（Tailwind 除外）。
- AC 草案：前端单测、类型检查、生产构建、`verify_frontend_dist.py`、前端 E2E 全部通过；Selkies 适配层产物仍为经典 IIFE 且注入顺序不变；生成的 API 类型与升级前语义一致。
- 验证：`scripts/run_gates.sh` 全绿；会话 E2E 无头运行通过。

### WP02 后端运行时升级

- 范围：Python 3.15、Debian trixie、SQLAlchemy / Alembic / aiosqlite、`uv.lock` 单一来源、`run_gates.sh` 的 Python 版本、删除 `src/backend/requirements.txt`、cloakbrowser 锁定 ADR。
- AC 草案：全部镜像可重复构建；全量门禁与真实栈 E2E 通过；镜像内依赖与 `uv.lock` 一致。
- 验证：`scripts/run_gates.sh`；部署脚本在隔离实例上完成一次发布与回退演练。

### WP03 设计系统

- 范围：`DESIGN.md`（第 4 节）、Tailwind 4 迁移、生成器、三条门禁、主题运行时、字体自托管、`AGENTS.md` 目录表登记 `DESIGN.md` 与 `.design_reference/`。
- 依赖：WP01。
- AC 草案：官方 lint 0 error / 0 warning；`design:check` 通过；主题偏好三态切换生效且首帧无闪烁；业务代码不含硬编码颜色（以 `gray-`、`surface-[0-4]`、`emerald-`、`#xxxxxx` 等模式 grep 检查）。
- 验证：门禁全绿；亮暗两种模式下各页面截图人工核对（无头截图）。

### WP04 Caddy 升级

- 范围：Caddy 2.11.8 与 Caddyfile 适配。
- AC 草案：HTTPS 访问、静态资源、`/api/v1`、`/stream/*/signal` 转发行为不变。
- 验证：真实栈 E2E。

### WP05 Selkies 2.2.1 升级

- 范围：spike（官方 2.1.0 → 2.2.1 差异；适配层与 `x11_keymap` 私有 ABI；pixelflux / pcmflux 2.2.x）→ 实施（vendor 脚本、SHA 清单、Stream 镜像、适配层）→ 修订 ADR。
- AC 草案：会话阶段、多页面同 Profile、复制标签页身份重映射、IME 组合输入、音频、剪贴板、可见性暂停等现有 E2E 全部通过。
- 验证：会话与 Stream 全部 E2E。

### WP06 后端数据模型重建

- 范围：6.1–6.5 节与 6.8 节的字段部分（`fingerprint_platform`）、6.9 节 API 变更、OpenAPI 重新导出、手动迁移测试数据。
- 依赖：WP02。
- AC 草案：
    - 分组 CRUD；删除分组后引用环境变为未分组。
    - 代理 CRUD；响应不含密码；被引用时删除返回 409 `proxy_in_use`；编辑代理运行字段后引用环境生成新配置版本。
    - 只改元数据不生成配置版本；相同值提交不生成配置版本。
    - 运行时记录最后启动与停止时间并经 SSE 下发。
    - 仓库内（6.2 节例外范围之外）不再出现业务 Tag 概念。
- 验证：unit / integration / API 子进程测试；以「tag」为关键词的仓库扫描。

### WP07 浏览器版本上报

- 依赖：WP02、WP06。
- AC 草案：运行中环境的 runtime 响应含真实 product 与 UA，与容器内 Chrome 实际版本一致。
- 验证：真实栈 E2E。

### WP08 全局布局与基础组件

- 范围：5.2、5.9、5.10 节；`shared/ui/` 组件库；新路由骨架（旧路由删除）。
- 依赖：WP03。
- AC 草案：侧栏折叠、拖宽与持久化；键盘可操作；主题与语言切换；Coordinator 错误横幅；iframe 焦点守卫保持。
- 验证：Vitest 组件与路由测试。

### WP09 环境列表

- 范围：5.3、5.4、5.8 节。
- 依赖：WP06、WP08。
- AC 草案：搜索与三类筛选组合正确；列表/卡片切换持久化；五态实时更新；批量启动、停止、移动分组、删除，结果汇总正确且失败项保持选中；新建、「创建并启动」；分组管理全部操作。
- 验证：Vitest（ApiClient 边界注入 stub、走真实 hooks）；真实栈 E2E 覆盖「新建 → 启动 → 打开会话」。

### WP10 代理库页面

- 范围：5.7 节。
- 依赖：WP06、WP08。
- AC 草案：CRUD；密码只写语义；URL 粘贴解析；被引用时禁止删除；使用数跳转筛选。
- 验证：Vitest；E2E 覆盖「新建代理 → 环境引用 → 启动」。

### WP11 环境详情页

- 范围：5.5 节；原 Artifact 页与自动化页并入。
- 依赖：WP06、WP08。
- AC 草案：四个标签页功能与现有能力等价；元数据保存不出现待应用提示；运行配置保存在运行中出现待应用提示并可「应用并重启」。
- 验证：Vitest；E2E。

### WP12 会话页

- 范围：5.6 节。
- 依赖：WP05、WP07、WP08。
- AC 草案：现有会话阶段与恢复语义全部保持；切换器链接在新标签页打开时互不影响；详情面板值与 API 一致；专注模式进入与退出不影响远端输入。
- 验证：会话 E2E（保留的 `data-testid`）；Vitest。

### WP13 缩略图

- 范围：6.7 节后端与卡片视图展示。
- 依赖：WP06、WP09。
- AC 草案：运行中环境约 15 秒更新一次缩略图；停止后保留最后一帧；关闭 `capture_preview` 后停止采集并删除预览；重置与删除 Profile 时清除；预览接口需鉴权且 `no-store`。
- 验证：integration；真实栈 E2E。

### WP14 指纹平台 spike

- 范围：
    - 获取字体（6.8 节来源）并放入 `data/fonts/`。
    - 在 146 内核下验证 windows 与 macos 两种指纹平台：`cloakbrowser info` 的字体计数；离线字体探测页（按字体名渲染测宽）；`navigator.platform`、UA、Client Hints 一致性。
    - 确定每种指纹平台可见的基础字体组合，以及 `font_bundle` 的去留。
- 依赖：WP02（trixie 字体包）。
- 产出：spike 报告与 `docs/findings/` 条目。

### WP15 指纹平台实施

- 范围：6.8 节其余部分。
- 依赖：WP06、WP11、WP14。
- AC 草案：两种指纹平台启动后 `navigator.platform` 与 UA 一致；平台字体只对对应指纹平台可见；字体缺失时 UI 告警；字体不出现在任何镜像层。
- 验证：E2E；镜像层内容检查。

### WP16 收尾

- 范围：第 11 节文档更新的最终核对；`.design_reference/` 删除（WP12 完成后）；本文迁入 `docs/archive/`。

## 9. 依赖与执行顺序

```text
WP01 ─> WP03 ─> WP08 ─┬─> WP09 ─> WP13
                      ├─> WP10
                      ├─> WP11 ─┐
                      └─> WP12  │
WP02 ─> WP06 ─┬─> WP09/WP10/WP11（同上）
              └─> WP07 ─> WP12
WP02 ─> WP14 ─> WP15（另依赖 WP06、WP11）
WP05 ─> WP12
WP04 独立
WP16 最后
```

可并行的起点：WP01、WP02、WP04、WP05（spike）。WP02 与 WP06 可在独立 worktree 中与 WP01、WP03、WP08 并行。

## 10. 测试策略

- TDD：可测部分先写失败测试。页面测试沿用现有规则：在 ApiClient 边界注入每例独立 stub，走真实 hooks，夹具使用生成类型的完整线形状。
- 旧测试处理：语义仍有效的保留并保持 `data-testid`；结构被删除的（例如侧栏 Profile 列表、`/?profileId=` 路由、tags 输入）整体删除并在 task 记录理由，再为新语义补测试；不就地改旧测试的预期值。
- 隔离语义回归：`scopeMutationToProfile` 的按 Profile 隔离、每标签页独立目标、页面关闭不 stop Profile，在新页面结构下必须有测试覆盖。
- 设计门禁：`design:lint`、`design:check` 进入 `run_gates.sh`。
- 所有浏览器测试无头运行。

## 11. 文档与契约更新

|位置|更新内容|
|---|---|
|`DESIGN.md`|新建（WP03）|
|`AGENTS.md`|目录表新增 `DESIGN.md` 与 `.design_reference/` 两行|
|`docs/blueprint/frontend.md`|重写全局布局、路由、页面、主题、设计门禁相关章节|
|`docs/blueprint/domain.md`|新增 Group、Proxy 实体与「环境」术语对照；删除 Tag；补充元数据与运行配置的区分|
|`docs/blueprint/persistence.md`|新 schema 与 baseline 策略|
|`docs/blueprint/browser_runtime.md`|平台字体、缩略图采集、浏览器版本上报|
|`docs/blueprint/supervisor.md`|平台字体挂载、预览转发|
|`docs/blueprint/security.md`|代理密码只写不回显、预览隐私、字体不进镜像|
|`docs/blueprint/conventions.md`|技术栈版本、`DESIGN.md` 落点|
|`docs/blueprint/testing.md`|设计门禁|
|`docs/blueprint/decisions.md`|新 ADR：DESIGN.md 与双模式约定；schema baseline 重写策略；Tag 替换为 Group；cloakbrowser 锁 0.6.4；Selkies 2.2.1（替代 2.1.0 固定）；平台字体只在运行时挂载；各技术底层组件的目标版本|
|`docs/specs/`|新建 `ui_design_system`、`proxy_management`、`profile_preview`、`fingerprint_platform`；更新 `profile_management`、`webrtc_remote_display`、`runtime_lifecycle`、`release_deployment`、`browser_isolation`|

## 12. 风险与待验证项

|项|缺少的证据|验证方式|影响|
|---|---|---|---|
|TypeScript 7 与 `openapi-typescript`|兼容性未实测|WP01 实测生成；失败则用 6.0.3|TS 版本选择|
|Vite 8（Rolldown）产出 IIFE 适配层|未实测|WP01 构建并运行 `verify_frontend_dist.py`|会话页可用性|
|React Router 8 破坏性变更|未逐项核对|WP01 对照 changelog|路由层改动量|
|Selkies 2.2.1 与适配层、`x11_keymap` 私有 ABI|未实测|WP05 spike|会话核心功能|
|trixie 下 apt 包名|未核对|WP02 构建镜像|镜像构建|
|浏览器版本的传递链路|未读完整链路|WP07 开始时读 Agent → Supervisor → API 代码|WP07 实现方式|
|CDP 截图对页面行为的影响与预览转发通道|未实测|WP13 原型|WP13 实现方式|
|146 内核下 macOS 指纹平台的质量|官方改进记录在 156|WP14 spike|macOS 指纹平台的可用程度|
|每种指纹平台应暴露的基础字体组合|未实测|WP14 spike|字体隔离方案|
|带认证 SOCKS5 是否被 CloakBrowser 支持|Chromium 原生不支持，CloakBrowser 行为未实测|WP10 或 WP14 实测|代理表单提示文案|
|删除运行中 Profile 的现有语义|未核对|WP09 读 API 实现|批量删除交互|

## 13. 设计参考目录（`.design_reference/`）

- 内容：用户提供的前端原型源码（React + Vite + Tailwind 3，Kimi Agent 生成），复制自用户下载的 zip，原样保留。
- 用途：实施 WP03、WP08–WP12 时对照视觉与交互细节。它不是构建输入，不被任何脚本、测试或构建读取。
- 权威关系：设计权威是 `DESIGN.md`。原型与本文或 `DESIGN.md` 冲突时，以后两者为准。原型中的模拟浏览器框、假指纹参数、localStorage 假数据、删除代理后改为直连、未使用的 shadcn 组件与 Kimi 专用 Vite 插件，均不采用。
- 版本控制：由 `.gitignore` 的 `/.design_reference/` 忽略，不入库。被忽略的文件不会出现在 task worktree 中，实施时从主仓库目录读取。
- 生命周期：WP12 完成后由 WP16 删除。
