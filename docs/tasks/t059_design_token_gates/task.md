# Task spec

## 背景

`DESIGN.md` 是 UI 唯一设计权威（ADR 025 / 027），经 `npm run design:tokens` 生成 token。2026-11-10 intensive review 指出其门禁存在缺口，adoption_decision 采纳为 A40、A41、A42、A62：

- 圆角双口径：components 中 card / modal 为 `rounded.md`，正文 Shapes 写卡片 lg、弹窗 xl，实现遵循正文；生成器不校验 components。
- 颜色门禁不扫描 `public/`（logo、favicon）、`index.html`、`theme_boot.js`，logo 渐变与 token 无关。
- t047 声称颜色对全部满足 WCAG AA，但生成器没有对比度计算；未证实疑点中已有色对疑似低于 4.5:1。
- 数值型尺寸与间距工具类（`w-72`、`h-9`、`py-0.5` 等）不受门禁约束，构成第二套事实源。用户 2026-11-10 在 D2 选 A：宽高与间距全部纳入 token。

## 契约区

### 范围

- A40：DESIGN.md components 中 card 改为 `rounded.lg`、modal 改为 `rounded.xl`；生成器导出组件级变量，组件引用变量；生成器断言正文提及的组件 token 与 components 定义一致。
- A41：颜色门禁扫描纳入 `public/**/*.{svg,html,js}` 与 `index.html`；品牌 logo 渐变登记为 DESIGN.md 品牌色 token，logo.svg 与 favicon 由生成器按 token 生成；`theme_boot.js` 颜色引用生成值；不设 allowlist 例外。
- A42：生成器按 DESIGN.md 声明的前景 / 背景角色对计算对比度，正文文字低于 4.5:1、大字与图形低于 3.0:1 即失败；修正门禁发现的全部不达标色对。
- A62：间距（padding / margin / gap / space）全部改用 spacing token；组件宽高（控件高度、浮层宽度、图标尺寸等）写入 DESIGN.md components 规格，由生成器导出组件级变量，组件引用变量；门禁拦截全部数值型尺寸与间距工具类（含任意值写法），不设例外。

### 非范围

- 不改界面布局与交互（只替换尺寸来源，渲染结果保持一致，除非对比度修正要求改色）。
- 不改主题切换机制与字体体系。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：DESIGN.md 中卡片与弹窗圆角只有一个口径，实现中的卡片与弹窗圆角来自该定义；正文与 components 不一致时 `design:check` 失败。
- [x] AC-002：在 `public/`、`index.html` 或 `theme_boot.js` 中写入非 token 颜色时，`design:check` 失败；logo 与 favicon 颜色随品牌 token 变化。
- [x] AC-003：任一声明的颜色角色对低于对应对比度阈值时，`design:check` 失败；当前亮暗两种模式下全部角色对通过。
- [x] AC-004：业务代码中出现数值型或任意值写法的尺寸、间距工具类时，`design:check` 失败；当前代码全部通过。
- [x] AC-005：替换后各页面主要组件的尺寸与间距与替换前一致（对比度修正导致的颜色变化除外）。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001..004：可自动测试（生成器单测、门禁负例）。
- AC-005：视觉一致性以替换前后的页面截图人工比对（headless 截图），并以组件测试中计算样式抽查替代。

## 上下文区

- 来源：`docs/reviews/review_20261110_200842/adoption_decision.md` A40、A41、A42、A62（审阅原文第 103–105 项及未证实疑点色对；A62 为用户 2026-11-10 D2 选 A）。

### 有意不测

- 第三方组件内部样式：不在业务代码扫描范围内。

### 测试策略

- 生成器单测：组件 token 一致性、对比度计算、public 资产生成、数值类拦截负例。
- 门禁：`design:check` 在完整门禁中运行。
- 视觉：headless 截图比对主要页面。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- `@google/design.md` alpha 格式对 components 中自定义尺寸字段的 lint 行为：已实测（2026-11-13，实验在 `.scratch/spike/`）。结论：官方 linter 合法子 token 恰为 `backgroundColor, textColor, typography, rounded, padding, size, height, width` 八个，`height/width/size` 写字面量或 `{spacing.*}` 引用均无 finding 并解析为 dimension；自定义字段名（如 `iconSize`、`borderColor`）产生 warning，而生成器将 warning 视为阻断。实施口径：尺寸规格只用官方 `height/width/size` 字段，生成器侧读取解析值导出组件级变量，不改官方格式。

### 风险与回退

- 风险：尺寸 token 化改动面覆盖全部组件，可能引入视觉回归；以截图比对兜底。
- 回退：revert 实现 commit。

### 依赖与约束

- 与 t052（代理弹窗）、t053（ProfileForm）、t058（会话页与表单）存在前端文件重叠，按 `conflicts_with` 串行。

### Finalization 时更新的 blueprint

- `DESIGN.md`：圆角、品牌色、组件尺寸规格。
- `docs/blueprint/frontend.md`：门禁覆盖范围、对比度与尺寸 token 约定。
- `docs/blueprint/decisions.md`：修订 ADR 027 中 AA 声称为门禁保证。
- `docs/specs/ui_design_system.md`：对应行为。
