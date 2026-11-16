# p107 SearchField 左侧放大镜图标与输入/占位文本横向重叠

- 现象：环境管理（`env-search`）与代理管理（`proxy-search`）搜索框中，左侧放大镜搜索 icon 与“搜索环境...”/“搜索代理...”占位符及输入文本横向混叠（重叠约 3px）。
- 影响：所有使用 `SearchField` 组件的搜索输入框均存在图标遮挡首字的问题，影响可读性与视觉观感。覆盖范围包含 3 处页面/浮层位点：`EnvironmentListToolbar`（环境管理）、`ProxyListToolbar`（代理管理）以及同组件复用的 `EnvironmentSwitcher`（工作台会话切换弹窗搜索框）。
- 根因：产品代码缺陷（`src/frontend/src/shared/ui/Input.tsx` 中 token 间距算术不足 + `cn()` 无冲突类去重风险）。
    - 机制核实：`SearchField`（`Input.tsx:28-48`）将 `<Search>` 定位为 `absolute left-md size-(--component-icon-md-size)`，对应 `src/frontend/src/styles/design_tokens.css` 中 `--spacing-md: 12px` 与 `--component-icon-md-size: 16px`，图标右边界位于容器/输入框外框左侧起 `12 + 16 = 28px` 处；同时向 `<Input>` 传入 `className={cn("pl-xl", className)}`。在已编译 CSS（`src/frontend/dist/assets/index-Cj1nCZZo.css`）中 `.pl-xl`（偏移 19057）排在 `Input` 基础类 `.px-md`（偏移 18533）之后，使 `padding-left` 生效为 `--spacing-xl: 24px`（加 `1px` 左边框后文本起点为 `25px`），`25px < 28px` 导致文本与图标右缘直接重叠 `3px`（纯内边距差 `4px`，且完全没有图标与文本间的呼吸间距）。此外 `src/frontend/src/shared/ui/cn.ts` 仅做字符串拼接而非冲突类合并，`Input` 同时携带 `px-md` 与 `pl-xl` 依赖样式表生成顺序。修复时需采用满足 `left-offset + icon-size + gap` 的 token 表达（如 `pl-[calc(var(--spacing-md)+var(--component-icon-md-size)+var(--spacing-sm))]` = `36px`，符合 `design_tokens.mjs` 的 `isTokenOnlyArbitrary` 规则）并避免 `px-md`/`pl-*` 冲突。
    - 全仓扫描结论：
        - 已确认受影响同类位点（3 处，均直接渲染 `SearchField`）：
            1. `src/frontend/src/features/profiles/EnvironmentListToolbar.tsx:79`（`data-testid="env-search"`）
            2. `src/frontend/src/features/proxies/ProxyListToolbar.tsx:60`（`data-testid="proxy-search"`）
            3. `src/frontend/src/features/browser-session/EnvironmentSwitcher.tsx:164`（`data-testid="sess-switcher-search"`）
        - 已排查非同类/不重叠位点：其余 `<Input>`（`LoginPage.tsx`、`GroupManagerDialog.tsx`、`ProxyFormDialog.tsx`、`ProfileForm.tsx`）及原生 `<input>`（`ProfileFilesTab.tsx`、`TimezoneCombobox.tsx`）均无左侧绝对定位图标；`src/frontend/src/shared/ui/Select.tsx:154-158` 的下拉项虽同样使用 `pl-xl`（`24px`），但其左图标为 `left-sm`（`8px`）+ `--component-icon-sm-size`（`14px`）= `22px < 24px`，不存在重叠。
- 测试缺口：
    - 漏过原因：`EnvironmentListPage.test.tsx:512`、`ProxyListPage.test.tsx:261-281`、`EnvironmentSwitcher.test.tsx:209-240` 仅测 `fireEvent.change` 过滤交互；`shared/ui/ui.test.tsx` 未覆盖 `Input`/`SearchField`；`design_tokens.mjs --lint` 仅检查禁用硬编码尺寸/颜色与 token 语法，不校验叠加图标与文本内边距的几何关系；且 Vitest 运行于 jsdom（无 CSS 计算与布局引擎）。
    - 应补校验：
        1. UI 单测 / 样式契约校验（`src/frontend/src/shared/ui/`）：结合 `design_tokens.css` 数值解析 `SearchField` 的左图标偏移+图标宽度与 `input` 左内边距 token/计算式，断言 `paddingLeft >= iconLeft + iconWidth + gap` 且 `Input` 不依赖 `px-md` 与 `pl-*` 级联覆盖；
        2. 真实浏览器几何回归（端到端/页面级）：在渲染后读取 `getComputedStyle(input)` 与图标/输入框的 `getBoundingClientRect()`，断言 `inputBorderLeft + paddingLeft > iconRect.right - inputRect.left`（分别覆盖 `env-search`、`proxy-search`、`sess-switcher-search` 三处位点）。
- 线索：`.scratch/repro_search_field_icon_text_overlap.mjs`（执行 `node .scratch/repro_search_field_icon_text_overlap.mjs` 复现输出：`iconBoxX: [12, 28]`, `textStartX: 25`, `clearancePx: -3`, `overlaps: true`）
- 处理：t073；resolution=transferred；reason=已核实根因与同类位点并聚合并转交 t073（设计系统底座与状态/搜索框重构）
