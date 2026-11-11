# Task spec

## 背景

用户要求前端参考 `<home>/kar/code/omni_panel/DESIGN.md` 改造视觉：只改主题、背景、字体、字号、圆角与阴影，不动主要界面。当前系统为暖绿灰 + Space Grotesk / IBM Plex Mono，全站 400 字重；omni 为冷灰中性色 + Inter / JetBrains Mono，重度依赖字重层级与更大圆角。

设计权威是根目录 `DESIGN.md`，经 `src/frontend/scripts/design_tokens.mjs` 生成 Tailwind 4 token。直接复制 omni 色值会触发两类门禁：

- `design:lint` 把 WCAG contrast warning 当失败：omni 亮色 accent `#3d7afd` 白字 3.89:1、danger `#ef4444` 白字 3.76:1、暗色 `#5b8dff` 白字 2.9:1、亮色 muted `#687085` 在背景上 4.11:1，均不达标。
- front matter 只支持 `colors` / `typography` / `spacing` / `rounded` / `components`，加入 `shadows` / `motion` 会触发 `unknown-key` warning。

因此采用 AA-safe 变体与正文阴影表，保持 `.dark` 主题机制与现有组件结构不变。

## 契约区

### 范围

- `DESIGN.md`：颜色、字体、字号、字重、行高、字距、圆角、阴影；组件清单与角色名保持不变。
- 生成器：字体栈从 typography 派生；输出 `--text-*--font-weight` / `--text-*--line-height` / `--text-*--letter-spacing`；解析 `## Elevation & Depth` 阴影表并输出 `--shadow-*` 与 `.dark` 覆盖；更新单元测试。
- `globals.css`：Inter Variable / JetBrains Mono Variable 的 `@fontsource` import 与 body 字体栈。
- `package.json` / `package-lock.json`：字体依赖替换。
- 重新生成 `design_tokens.css`。
- `Table.tsx` 移除与 token 字距重复的 `tracking-wide`（唯一 TSX 改动）。
- 文档：`docs/specs/ui_design_system.md`、`docs/blueprint/frontend.md`、`docs/blueprint/decisions.md`。

### 非范围

- 布局、信息架构、组件结构、交互行为。
- `data-theme` 机制替换（继续用 `.dark` class + `theme_boot.js`）。
- 五档强调色切换、毛玻璃菜单、动效体系。
- 行高密度、容器尺寸、表格行高、侧栏宽度。
- 默认主题从 `dark` 改为 `system`。
- 新增业务功能或 API。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：亮暗两模式的页面背景、卡片、浮层、侧栏、会话 stage 与 accent / danger / warning / group 色呈现 omni 冷灰视觉；`npm run design:lint --prefix src/frontend` 为 0 error / 0 warning，全部组件文字与背景组合 ≥ 4.5:1。
- [x] AC-002：界面文本使用 Inter Variable 字体栈（含中文回退），技术数据使用 JetBrains Mono Variable 字体栈；两者经 `@fontsource` 自托管，构建产物含 woff2 且无外部字体 CDN 引用。
- [x] AC-003：标题 / 正文 / 标签的实际字号与 omni 层级一致（21 / 17 / 15 / 13.5 / 12.5 / 12.5 / 11.5 / 12.5 / 10.5），并呈现 600 / 550 / 450 字重、1.2–1.55 行高与对应字距；标题不再全部为 400 字重。
- [x] AC-004：圆角呈现 6 / 10 / 14 / 18 四档，浮层与弹窗在亮暗两模式使用 omni 柔和阴影；现有页面与组件无需逐页修改即生效。
- [x] AC-005：`npm run design:tokens --prefix src/frontend` 确定性生成 `design_tokens.css`，`npm run design:check --prefix src/frontend` 通过；生成器单测覆盖字体派生、字重 / 行高 / 字距与阴影输出。
- [x] AC-006：`npm test --prefix src/frontend` 通过；diff 仅包含 token 管线、`globals.css`、`Table.tsx` 的 `tracking-wide` 移除、字体依赖与文档，未改动页面布局或组件结构。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001：`design:lint` 自动验证 token 与 AA；亮暗视觉观感需人工截图走查。
- AC-002：构建产物扫描自动验证字体文件与 CDN 引用。
- AC-003：生成 CSS 与组件渲染断言自动验证 token 值；实际字重观感需人工走查。
- AC-004：生成 CSS 自动验证圆角 / 阴影值；视觉走查确认无布局回归。
- AC-005：生成器单测与 `design:check` 自动验证。
- AC-006：`npm test` 与 `git diff --stat` 自动验证；“未改布局”由 diff 审阅人工确认。

## 上下文区

- 来源：用户 2026-11-09 需求（参考 `<home>/kar/code/omni_panel/DESIGN.md`），已确认全部推荐决策：AA-safe 色板、字重 / 行高落地、omni 圆角、阴影覆盖、默认 dark 不变。

### 有意不测

- 五档强调色切换：非本 task 范围，未实现。
- `data-theme` 迁移：保持 `.dark`，不测试。
- 页面布局回归：只做人工截图走查，不引入视觉回归测试框架。

### 测试策略

- `npm run design:tokens` → `design:check` → `design:lint` 三连。
- 生成器 Vitest：字体派生、weight / line-height / letter-spacing、shadow 表解析、非法输入。
- `npm test --prefix src/frontend` 全量前端测试。
- `npm run build --prefix src/frontend`，扫描 dist 的字体与 CDN。
- 亮暗两模式截图走查：登录、环境列表、详情、代理、设置、会话、Dialog / Toast。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。Tailwind 4 的 `--text-*--font-weight` / `--text-*--line-height` / `--text-*--letter-spacing` 为官方 `@theme` 扩展语法；`@fontsource-variable/inter@5.3.0` 的 family 为 `Inter Variable`、`@fontsource-variable/jetbrains-mono@5.3.0` 的 family 为 `JetBrains Mono Variable`，已用 `npm pack` 核实（2026-11-09）。

### 风险与回退

- 风险：omni 原色值触发 AA 门禁；Inter 字体度量改变文本宽度导致截断；字重 / 行高改变垂直节奏；Tailwind 对 `--text-*` 扩展的输出与预期不符。
- 回退：单 commit 整体 revert；字体依赖版本锁定；先在生成器测试中验证 token 输出，再改 `DESIGN.md`。

### 依赖与约束

- 前置依赖：无。
- 约束：必须通过 `design:lint` / `design:check` / `npm test`；不引入外部字体 CDN；不手改 `design_tokens.css`；不破坏 `.dark` 首帧机制。

### Finalization 时更新的 blueprint

- `docs/blueprint/frontend.md`：设计系统字体栈、字号 / 字重 / 圆角 / 阴影 token 与生成器行为。
- `docs/blueprint/decisions.md`：新增「omni 视觉迁移采用 AA-safe 色板与 DESIGN.md 派生字体 / 字重」决策。
- `docs/specs/ui_design_system.md`：§2.2 字体与 token 契约。
- `docs/specs_index.md`：`ui_design_system` 行追加 `t047`。
