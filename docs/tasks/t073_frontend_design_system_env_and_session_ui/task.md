# Task spec

## 背景

当前前端设计系统（`DESIGN.md` → `src/frontend/src/styles/design_tokens.css`）、基础 UI 原语层、工作台顶栏以及环境管理页存在一连串互相关联的结构与交互缺陷（聚合 `p103`、`p107`、`p108`、`p109` 与 `p105` 容器尺寸/环境弹窗部分）：

1. **缺少绿色语义色体系与深色模式徽标辨识度缺失（`p109`）**：
    - `DESIGN.md` 仅定义 `accent`（蓝）、`warning`（琥珀）、`danger`（红），完全缺失 `success` / `success-soft` 语义色（绿色仅存在分组色板中）。
    - `StatusBadge.tsx` 将 `running` 绑定为 `bg-accent-soft text-on-surface`，`EnvironmentSwitcher.tsx` 的 `statusDotClass("running")` 绑定为 `bg-accent`，导致全仓 10 个文件（环境列表、环境卡片、环境详情、工作台顶栏/切换器/入口、自动化、代理表/卡、设置健康检查）的“运行中 / 正常 / 可用 / 完整”全部呈蓝色。
    - 深色模式下，工作台顶栏 `SessionHeader.tsx` 背景为 `bg-surface-raised`（`#2B313C`），`bg-accent-soft` 为 `#29344E`，两者亮度对比仅 **1.05:1** 且无描边，文字又用了近白色 `text-on-surface`（`#E9ECF3`），导致整个徽标在深色顶栏上几乎隐形、视觉上像无样式白字。
2. **工作台顶栏状态缺少可见主语（`p109`）**：`SessionHeader.tsx:114-125` 把 `sessObservedState`（“状态”）和 `sessTransport`（“传输”）放进 `sr-only` 隐藏，顶栏只露出裸词“运行中”与“正常”（英文 `"Running"` / `"Ready"`），用户难以一眼看清分别是“环境运行中”还是“数据传输正常”。
3. **搜索框绝对定位与内边距冲突导致图标与文字重叠（`p107`）**：`SearchField`（`src/frontend/src/shared/ui/Input.tsx:28-48`）将放大镜图标定位在 `left-md`（12px）+ `size-4`（16px）= 右缘 28px，而传给 `<Input>` 的 `pl-xl`（24px）加上 1px 左边框使文本起于 `25px`，直接重叠 `3px`。全仓 3 处复用的搜索框（`env-search`、`proxy-search`、`sess-switcher-search`）无一幸免。
4. **弹窗容器宽度缺失与环境新建/编辑体验割裂（`p105`）**：`DESIGN.md` `Container sizes` 仅定义了 `dialog: 32rem`；且因 Tailwind 4 `--spacing-*` 命名机制，`max-w-lg` / `max-w-2xl` 会被劫持为极窄像素（必须严禁使用）。结果新建环境弹窗局促拥挤，而环境列表点击“编辑”却直接整页跳转 `/profiles/:id/config`，与“弹窗完成新建与快捷编辑”割裂。
5. **环境管理页信息噪音与行内按钮堆砌（`p108`、`p103`）**：
    - `EnvironmentListPage.tsx:253-258` 直接将 `{snapshot.runningCount}` 渲染进 `env-running-count`，导致搜索栏下方莫名出现孤零零的数字 `"1"` / `"0"`，无任何标签或单位；
    - `EnvironmentTable.tsx` 与 `EnvironmentCard.tsx` 在用户未手动指定时区时依然打印自动匹配默认时区，且每行平铺 6 个带文字的按钮，视觉臃肿，删除键也缺少红色强调。

遵循“开发铁律（架构至上、拒绝妥协、零兼容性负担）”，本 task 一次性重铸 `DESIGN.md` 语义色与容器尺寸、改造 `shared/ui` 基础原语，并彻底翻新工作台顶栏与环境管理列表/弹窗交互。

## 契约区

### 范围

- **设计系统底座升级（`DESIGN.md` → `src/frontend/scripts/design_tokens.mjs` → `design_tokens.css`）**：
    - `Colors` 新增成对语义绿：`light-success` / `dark-success`、`light-success-soft` / `dark-success-soft`（按需成对增补 `*-border` 语义描边色，确保与 `surface` / `surface-raised` / `surface-subtle` 清晰分层且在 `Contrast` 表通过 WCAG AA ≥ 4.5:1 文本 / ≥ 3.0:1 图形对比度）；
    - `status-badge-running-light/dark` 改指绿色语义色与绿色语义文字；`status-badge-transition-*` 改为琥珀文字，`status-badge-error-*` 改为红色文字，三者均需在深色 `bg-surface-raised`（`#2B313C`）与 `bg-surface`（`#1F232C`）背景下具备足够辨识度（彩色文字 + 明显反差底色/语义描边）；
    - `Container sizes` 扩展宽弹窗尺寸梯度（如 `dialog-sm: 24rem`、`dialog-md: 32rem`、`dialog-lg: 44rem`、`dialog-xl: 56rem`，保留 `dialog: 32rem`）；重生成 `design_tokens.css` 并确保 `design:lint` 与 `design:check` 全通过。
- **基础 UI 原语重铸（`src/frontend/src/shared/ui/`）**：
    - `Input.tsx`（`SearchField`）：废弃“绝对定位左图标 + `px-md`/`pl-xl` CSS 级联赌运气”写法，重构为**Flex 组合输入框**（外层容器承载边框、圆角、`bg-surface` 与 `focus-within` 高亮，内部左槽 `shrink-0` 放置 `<Search>` + `gap` + 无边框自适应 `<input>`），从架构上永久根除图标文字重叠（`data-testid` 仍透传到 `<input>` 不破坏检索定位）；
    - `StatusBadge.tsx`：接入绿色 `running` 语义样式（`bg-success-soft` + `text-success` + 语义描边），`transition`（`warning`）与 `error`（`danger`）同步改用彩色语义文字+描边，`stopped` 保持中性 `muted`；
    - `Button.tsx`（`IconButton`）：增加 `variant?: "ghost" | "danger" | "warning"`（全部仅使用 `DESIGN.md` 语义 token，绝不写 Tailwind 调色板类或十六进制色），支持红色删除与琥珀停止图标按钮；
    - `Dialog.tsx`：新增 `size?: "sm" | "md" | "lg" | "xl"`（默认 `"md"`），映射语义 `max-w-dialog-*` token，内容区支持内部平滑滚动（`max-h-dialog-height`）。
- **工作台状态视觉与主语全量修正（`p109` 10 处扫描全覆盖）**：
    - `EnvironmentSwitcher.tsx`：`statusDotClass("running")` 改为 `bg-success`（替代 `bg-accent`），同时影响顶栏触发器圆点与下拉列表项圆点；
    - `SessionHeader.tsx` & `i18n.tsx`：移除 `sr-only` 隐藏标签；顶栏两个状态徽标直接展示完整含主语的本地化文案（例如中文“环境运行中”“数据传输正常”及其余各态对应文案，英文同步含主语 `"Env Running"` / `"Data Ready"` 等，注意不影响 `SessionDetailsPanel` 已有左列标题的纯表格行）。
- **环境管理列表、卡片、运行计数与宽弹窗统一（`p108`、`p103`、`p105` 环境部分）**：
    - 清理 `EnvironmentListPage.tsx:253-258` 孤立渲染裸数字 `{snapshot.runningCount}` 的 `env-running-count`：或移除该多余裸数行，或在保留位置严格使用完整带标签语义文案（如 `t("runningProfiles", { count: snapshot.runningCount })` → “运行中：1” / “Running: 1”，绝不允许渲染纯数字 `/^\d+$/`）；
    - `EnvironmentTable.tsx` & `EnvironmentCard.tsx`：隐藏未手动指定/自动匹配的默认时区，仅当用户显式设置具体 `profile.timezone` 时显示时区；
    - 重构 `EnvironmentRowActions`（参考用户要求的高紧凑风格）：每行仅保留 **1 个带文字主操作按钮**（运行中为蓝色 `primary` 「打开」，未运行为 `secondary` 「启动」，过渡态相应禁用），其余次级操作全部收敛为带 `aria-label` 与 `title` 的**无文字纯图标按钮**：
        - 「配置详情」（`SlidersHorizontal`，打开 `/profiles/:id/config` 深度页，承载文件/自动化/维护）；
        - 「编辑」（`Pencil`，打开新建/统一的 `ProfileEditDialog` 宽弹窗，不再整页跳离列表）；
        - 「复制」（`Copy`）；
        - 「停止」（运行中/启动中时显示 `IconButton variant="warning"` + `Square` 图标）或「删除」（非运行态显示红色 `IconButton variant="danger"` + `Trash2` 图标，不可删除时给出明确禁用态）；
    - `ProfileForm.tsx`、`ProfileCreateDialog.tsx` 与新增 `ProfileEditDialog.tsx`：均采用 `Dialog size="lg"` 宽弹窗及桌面多栏（2–3 列）表单排版、高级参数可折叠，并同步接入 `ProfileDetailPage.tsx`（配置概览提供唤起宽编辑弹窗入口，直接访问 `/profiles/:id/config` 路由仍完整工作）。

### 非范围

- 不修改任何后端 Python 代码、数据库表、OpenAPI 契约或 Proxy / Settings 业务逻辑（留待下游 `t074` 统一全栈改造）。
- 不重做 `/settings` 页面弹窗化、不改动 `ProxyTable` 列结构或代理测速/国家城市筛选（归下游 `t074`）。
- 仅验证并确保已有复用组件（如 `ProxyListToolbar` 的 `proxy-search`、`ProxyTable`/`SettingsPage` 引用的 `StatusBadge`）自然继承基础原语修复不报错即可。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：环境管理（`env-search`）、代理管理（`proxy-search`）及工作台环境切换器（`sess-switcher-search`）的搜索框中，左侧放大镜图标与占位文本及输入文本互不重叠且存在明确视觉间距。
- [ ] AC-002：所有代表“运行中 / 正常 / 可用 / 完整”的状态徽标与工作台环境切换器状态圆点在浅色与深色模式下均呈现绿色语义样式，且在深色顶栏等深色表面上具有清晰可读的彩色文字/描边对比度，不再显示为蓝色或模糊白字。
- [ ] AC-003：工作台顶栏在各运行态与传输态组合下直接显示带主语的本地化状态文案（中文如“环境运行中”“数据传输正常”，英文对应具备主语，不再依赖屏幕阅读器隐藏文本补充上下文）。
- [ ] AC-004：环境管理列表与卡片视图不再出现无标签/无上下文的孤立运行计数数字；未显式设置自定义时区的环境不显示默认/自动匹配时区；仅有显式时区的环境展示时区。
- [ ] AC-005：环境列表与卡片的操作栏每行仅保留一个带文字主按钮（运行中为蓝色“打开”，已停止为“启动”），详情、编辑、复制、停止、删除全部呈现为带可访问名称的无文字纯图标按钮，且删除图标按钮呈现红色危险样式。
- [ ] AC-006：点击“新建环境”及点击列表行“编辑”或详情页编辑入口均在当前上下文弹出宽弹窗多栏表单并可平滑滚动，保留新建幂等防重复提交与编辑差分更新行为；前端设计门禁与全量测试通过。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001..006：全部 AC 可自动测试（Design Token / WCAG 对比度检验、`design:lint` & `design:check`、Vitest UI 原语与页面组件测试、Playwright 无头浏览器 `getBoundingClientRect()` 搜索框不重叠与颜色/交互验证）。

## 上下文区

- 来源与根因线索（已完成静态定位与 `.scratch/` 复现）：
    - `p107`：`SearchField` 位于 `src/frontend/src/shared/ui/Input.tsx:28-48`，复现脚本 `.scratch/repro_search_field_icon_text_overlap.mjs` 实测 `iconBoxX: [12, 28]` vs `textStartX: 25`（重叠 3px）；受影响 3 处：`EnvironmentListToolbar.tsx:79`、`ProxyListToolbar.tsx:60`、`EnvironmentSwitcher.tsx:164`。
    - `p109`：`DESIGN.md:3-67,489-498` 缺 `success` 语义色，`StatusBadge.tsx:7-24` 与 `EnvironmentSwitcher.tsx:60-71` 绑定蓝/中性白，深色对比仅 1.05:1；`SessionHeader.tsx:114-125` 用 `sr-only` 隐藏主语。复现脚本 `.scratch/repro_status_badge_and_session_header.mjs`。
    - `p108`：`EnvironmentListPage.tsx:253-258` 裸输出 `{snapshot.runningCount}`，`EnvironmentListPage.test.tsx:608,627` 仅用 `.toContain("1")` 漏检。复现用例 `.scratch/repro_env_running_count.test.tsx`。
    - `p103`：`EnvironmentTable.tsx` 与 `EnvironmentCard.tsx` 强制回落显示默认自动时区、平铺 6 个文本按钮。
    - `p105`：`DESIGN.md` `Container sizes` 仅 `dialog: 32rem`；Tailwind 4 禁止使用 `max-w-lg`/`max-w-2xl`（会被 `--spacing-lg` 覆盖成 `16px`）；新建与编辑路径割裂。

### 实施蓝图与文件改造清单（给执行者的精确步骤）

1. **Step 1 — 重构 `DESIGN.md` 与 `src/frontend/scripts/design_tokens.mjs`**：
    - 打开 `DESIGN.md`：
        - 在 `## Colors` 成对新增：`light-success`（如 `#137A3D`，在浅面比值 ≥ 4.5:1）、`dark-success`（如 `#34D399`）、`light-success-soft`（如 `#E6F7ED`）、`dark-success-soft`（如 `#112E22`，明显区别于 `#2B313C`）；视描边需要成对增加 `light/dark-success-border`、`light/dark-warning-border`、`light/dark-danger-border`（若用直接边框 token 则一并进 `Colors` 表）。
        - 更新 `status-badge-running-light` / `status-badge-running-dark` 的 `backgroundColor` 与 `textColor` 指向 `*-success-soft` 和 `*-success`；同时把 `status-badge-transition-*` 的 `textColor` 指向 `*-warning`、`status-badge-error-*` 的 `textColor` 指向 `*-danger`。
        - 在 `## Contrast` 表补充 `light/dark-success` 与各 `surface` / `surface-raised` / `surface-subtle` / `background` 的 `text` 与 `graphic` 对比检验行，确保 `design_tokens.mjs` 自动校验全绿。
        - 在 `## Container sizes` 新增宽弹窗尺寸 token：`dialog-sm: 24rem`、`dialog-md: 32rem`、`dialog-lg: 44rem`、`dialog-xl: 56rem`（保留既有 `dialog: 32rem` 避免无谓破坏已有布局），确认 `design_tokens.mjs` 将它们生成为 `--container-dialog-*` 与 Tailwind v4 `@theme` 工具类 `max-w-dialog-*`。
    - 执行 `npm run design:tokens --prefix src/frontend && npm run design:lint --prefix src/frontend && npm run design:check --prefix src/frontend` 验证生成无误。
2. **Step 2 — 改造 `src/frontend/src/shared/ui/` 基础原语**：
    - `Input.tsx`：重做 `SearchField`，外层包装元素用 `flex items-center gap-sm h-(--component-input-height) rounded-md border border-outline bg-surface px-md transition-colors focus-within:outline-2 focus-within:outline-accent`，内部左侧放置 `<Search aria-hidden="true" className="size-(--component-icon-md-size) shrink-0 text-on-surface-muted pointer-events-none" />`，右侧放置无边框 `<input className="min-w-0 flex-1 bg-transparent text-body-md text-on-surface placeholder:text-on-surface-subtle focus:outline-none ..." {...restInputProps} />`（确保 `data-testid`、`value`、`onChange`、`placeholder`、`aria-label` 全落到 `<input>` 上，且支持 `containerClassName` 控制外部宽度）；核对 `Select.tsx` 确认无同类重叠。
    - `StatusBadge.tsx`：`TONES` 改为四态全用彩色/中性语义：
        - `running`: `bg-success-soft text-success border border-success-border`（或合法语义边框 token）
        - `transition`: `bg-warning-soft text-warning border border-warning-border`
        - `error`: `bg-danger-soft text-danger border border-danger-border`
        - `stopped`: `bg-surface-subtle text-on-surface-muted border border-outline`
    - `Button.tsx`：`IconButton` 新增 `variant?: "ghost" | "danger" | "warning"`（`ghost`: 默认；`danger`: `text-danger hover:bg-danger-soft focus-visible:outline-danger`；`warning`: `text-warning hover:bg-warning-soft focus-visible:outline-warning`）。禁止使用任何 `text-red-*` / `#hex`。
    - `Dialog.tsx`：接收 `size?: "sm" | "md" | "lg" | "xl"`（映射 `max-w-dialog-sm` / `max-w-dialog` / `max-w-dialog-lg` / `max-w-dialog-xl`），面板容器设 `max-h-dialog-height flex flex-col overflow-hidden`，header 固定不滚动，body 使用 `min-h-0 flex-1 overflow-y-auto` 内部平稳滚动。
3. **Step 3 — 改造工作台状态视觉与可见主语**：
    - `src/frontend/src/i18n.tsx`：新增/规范工作台顶栏状态带主语键（例如 `sessHeaderEnvRunning`: `"环境运行中"` / `"Env Running"`、`sessHeaderEnvStarting`、`sessHeaderEnvStopping`、`sessHeaderEnvError`、`sessHeaderEnvStopped` 与 `sessHeaderTransportReady`: `"数据传输正常"` / `"Data Ready"`、`sessHeaderTransportRecovering`、`sessHeaderTransportFailed`、`sessHeaderTransportUnknown`），保持 `SessionDetailsPanel` 左列短词不受影响。
    - `src/frontend/src/features/browser-session/SessionHeader.tsx`：删掉 `<span className="sr-only">`，两枚 `StatusBadge` 直接渲染上述带主语的本地化文案，顶栏视觉清爽清晰。
    - `src/frontend/src/features/browser-session/EnvironmentSwitcher.tsx`：`statusDotClass("running")` 改为 `"bg-success"`。
    - `src/frontend/src/features/profiles/EnvironmentTable.tsx` & `EnvironmentCard.tsx` & `ProfileDetailPage.tsx` & `SessionEntryPage.tsx` & `ProfileAutomationTab.tsx`：确认全部正常继承绿色 `StatusBadge`。
4. **Step 4 — 改造环境管理页、操作按钮与新建/编辑宽弹窗**：
    - `src/frontend/src/features/profiles/EnvironmentListPage.tsx`：
        - 彻底修复第 253-258 行 `<div data-testid="env-running-count">` 裸数字输出：改为带完整语义文案的紧凑状态展示（例如复用 `t("runningProfiles", { count: snapshot.runningCount })` 呈现 `"运行中：1"` / `"Running: 1"`，附绿色运行圆点或精简胶囊并收纳于合适顶部计数区，绝不再打印无上下文裸数字）；
        - 将行内触发 `"edit"` 从 `navigate(/profiles/${id}/config)` 改为打开 `ProfileEditDialog` 状态；保留 `"details"` action 跳转 `/profiles/${id}/config`。
    - `src/frontend/src/features/profiles/EnvironmentTable.tsx` & `EnvironmentCard.tsx`：
        - 时区显示：仅当 `row.profile.timezone` 为非空字符串时显示该自定义时区；`timezone` 为空 / 默认自动匹配时，完全不渲染默认或 `envGeoipFollowProxy` 时区文字；
        - `EnvironmentRowActions`：仅 1 个带文本主按钮（`running` → 蓝色 `primary` `打开` + `ExternalLink`；非运行 → `secondary` `启动` + `Play`，`starting`/`stopping` 禁用态）；其余全为 `<IconButton>`（须带 `aria-label` 与 `title`）：
            - 详情 `<IconButton variant="ghost" icon={<SlidersHorizontal />} data-testid={`env-action-details-${id}`}>`
            - 编辑 `<IconButton variant="ghost" icon={<Pencil />} data-testid={`env-action-edit-${id}`}>`
            - 复制 `<IconButton variant="ghost" icon={<Copy />} data-testid={`env-action-copy-${id}`}>`
            - 条件末位按钮：运行/启动中显示 `<IconButton variant="warning" icon={<Square />} data-testid={`env-action-stop-${id}`}>`；停止态显示红色危险 `<IconButton variant="danger" icon={<Trash2 />} data-testid={`env-action-delete-${id}`}>`（注意 `stopping` 等按业务规则保留禁用提示）。
    - `src/frontend/src/features/profiles/ProfileForm.tsx`、`ProfileCreateDialog.tsx`、新增 `ProfileEditDialog.tsx`、`ProfileDetailPage.tsx`：
        - 优化 `ProfileForm.tsx` 桌面端多列（`grid-cols-1 md:grid-cols-2 lg:grid-cols-3`）舒展布局与可折叠高级设置分组；
        - `ProfileCreateDialog.tsx` 切换为 `<Dialog size="lg">`，**原封不动保留 `createActionKeyRef` 幂等键、`submitLockRef` 与失败重试保护**；
        - 新增 `ProfileEditDialog.tsx` 复用 `<Dialog size="lg">` + `<ProfileForm mode="edit">` + `diffProfileValues` + `useUpdateProfileMutation`；
        - `ProfileDetailPage.tsx` 配置页眉增加「编辑参数」按钮直接唤起 `ProfileEditDialog`，同时保留直连路由 `/profiles/:id/config` 的完整配置/文件/自动化/维护功能。
5. **Step 5 — 更新与补全自动化测试（严格遵守 TDD 与不静默改旧断言规则）**：
    - `src/frontend/src/shared/ui/ui.test.tsx`：新增 `SearchField` Flex 容器与 `data-testid` 透传断言、`StatusBadge` 四态颜色/描边类（明确断言不再含 `bg-accent-soft`）、`IconButton` `"danger"` / `"warning"` 类、`Dialog` 多尺寸类测试。
    - `src/frontend/scripts/design_tokens.test.mjs`：验证 `success` 语义色存在、深色徽标与 `surface-raised` 对比度安全、`dialog-sm/md/lg/xl` 容器 token 已生成。
    - `EnvironmentSwitcher.test.tsx` & `SessionHeader.test.tsx`：替换旧 `sr-only` 与裸词 `"正常"` 弱断言（写明理由：旧测试锁定了隐藏主语缺陷），改为校验可见带主语状态与绿色 `bg-success` / `text-success`。
    - `EnvironmentListPage.test.tsx` & `ProfileCreateDialog.test.tsx` & 新增 `ProfileEditDialog.test.tsx`：替换 `:608,627` 弱 `.toContain("1")` 断言（写明理由），严格断言运行计数含标签非 `/^\d+$/`、隐藏默认时区而展示显式时区、每行仅有 1 个主文本按钮 + 纯图标次级按钮 + 红色删除 `variant="danger"`、点击编辑弹出宽弹窗提交差分更新并保幂等。
    - 检索全仓 `tests/`（尤其 `tests/e2e/test_frontend_app_e2e.py`、`test_frontend_session_e2e.py`、`test_frontend_session_smoke.py`）对 `env-action-edit-*`、`env-running-count`、`sessTransport` 的引用并同步对齐新交互；若 Playwright 可用，补充 `getBoundingClientRect()` 验证 3 处 `SearchField` `iconRect.right < inputTextStart`。

### 有意不测

- 不在单测中启停真实容器（由已有 E2E 与后端集成测试保障）。

### 测试策略

- `npm run design:tokens --prefix src/frontend`、`npm run design:lint --prefix src/frontend`、`npm run design:check --prefix src/frontend`
- `npm run test:types --prefix src/frontend && npm test --prefix src/frontend && npm run build --prefix src/frontend`
- 若宿主 Playwright 环境就绪，运行前端 app 与 session E2E 校验。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

无

### 风险与回退

- 风险：`StatusBadge` 增加语义描边或 Tailwind v4 token 写法（如透明度修饰符）可能触犯 `design_tokens.mjs` 规则。处置：统一在 `DESIGN.md` 定义实色 `*-border` 语义 token，跑 `design:lint` 保证 0 违例。
- 风险：`ProfileCreateDialog` 重排版时若误改 `createActionKeyRef` / `submitLockRef` 会破坏新建环境幂等重试契约。处置：仅变更外观布局和 `Dialog size="lg"`，保持提交状态机原封不动并用 `ProfileCreateDialog.test.tsx` 验证。
- 风险：`tests/e2e/test_frontend_*.py` 可能直接用 `env-action-edit-*` 跳配置页面或断言老版 `sr-only` 文案。处置：实施前用 `rg` 搜遍全仓测试引用，同步分离 `env-action-details-*` 与 `env-action-edit-*`。
- 回退：纯前端与设计 token 单一原子 commit，回退只需 `git revert` 并重跑 `npm run design:tokens`。

### 依赖与约束

- 无前置 task；下游 `t074` 依赖本 task 先合入（复用 `success` 绿、`danger` 图标按钮及 `Dialog size="lg"` 底座）。
- 严格遵守 `docs/blueprint/conventions.md` §6（禁止非语义硬编码色值/间距）与 `DESIGN.md` Container sizes 命名规则。

### Finalization 时更新的 blueprint

- `docs/blueprint/frontend.md`：更新第 4 节（工作台顶栏状态带主语文案、状态圆点绿色）、第 6 节（`success` 语义色体系、`Dialog` 尺寸梯度、`SearchField` Flex 容器架构、`IconButton` 危险/警告变体）与第 7 节（环境表隐藏默认时区、图标化操作与红色删除按钮、编辑弹窗与详情页分流）。
