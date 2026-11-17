# s015：设计系统工具链契约核实（t036）

## 目标

核实 `docs/tasks/t036_design_system_app_shell/task.md` 的两项 UNVERIFIED-SPIKE：

1. `@google/design.md` 最新版（精确固定）的程序化 API 与 lint 规则，验证 `docs/plan_20261105_ui_redesign.md` 4.2 节的亮暗双模式写法在最新版合法。
2. Tailwind 4 `@tailwindcss/vite` 与 t033 选定的 Vite 大版本兼容（构建验证）。

## 环境

- Node 26.13.0（t033 固定）、`npm view` 2026-11-06 查得：`@google/design.md@0.4.0`、`@tailwindcss/vite@4.3.4`、`tailwindcss@4.3.4`；t033 `src/frontend/package.json`：Vite `^8.3.5`、TypeScript `5.9.3`、原 Tailwind `^3.4.17`。

## 实测一：`@google/design.md@0.4.0` 双模式写法

精确安装 `@google/design.md@0.4.0`，写 `code/DESIGN_SPIKE.md`（`primary` 单品牌色 + `light-*` / `dark-*` 成对颜色角色 + `<component>-light` / `<component>-dark` 成对组件 + Colors 章节 `### Modes` 说明）。可复现脚本见 `code/verify_design_system.mjs`。

- `npx @google/design.md lint DESIGN_SPIKE.md`：`{"errors":0,"warnings":0,"infos":1}`（唯一 info 为 `token-summary`）。
- 程序化 `import { lint } from '@google/design.md/linter'`：`lint(content)` 返回 `LintReport`，其中 `designSystem.colors` 是 `Map`，值为 `{type:"color", hex, r, g, b, luminance}`（如 `light-accent` → `#006edc` / `r:0 g:110 b:220`）。`tailwindConfig` 字段可用（`success` / `data`）。
- **结论**：4.2 节双模式写法在 0.4.0 合法，无 `unknown-key` / `broken-ref` / `orphaned-tokens` / `contrast-ratio` 警告（前提：全部 token 被组件引用、组件只用受支持属性、文字/背景组合达 WCAG AA）。spike 首稿曾因 `borderColor` 未被识别、未引用的 `*-muted` token、以及对比度不达标而出现 5 条 warning；按 0.4.0 实测调整后归零。生成器「`light-*` 与 `dark-*` 角色集合相同」的校验必须落在生成器里（lint 本身不检查该集合相等，只检查未解析引用与孤立 token）。

## 实测二：Tailwind 4 `@theme` + Vite 8 构建

精确安装 `@tailwindcss/vite@4.3.4`、`tailwindcss@4.3.4`、`vite@8.3.5`。`vite.config.mjs` 用 `import tailwindcss from '@tailwindcss/vite'` + `plugins:[tailwindcss()]`（Vite 8 CLI 不再接受 `--root`，root 必须写在 config）。

`npx vite build --config vite.config.mjs`：`vite v8.3.5 building client environment for production`，`✓ built`，产物 `dist/index.html` + `dist/assets/index-*.css`。CSS 含 `@theme` 中的 `--color-light-surface` (#f7fbf8)、`--color-light-on-surface` (#0d1611)、`--radius-lg` (10px)、`--spacing-md` (12px)。构建不依赖 PostCSS/autoprefixer。

## 结论

- 结论证据：findings `d034`（设计系统工具链版本与双模式写法契约）。
- **两项 UNVERIFIED-SPIKE 均已核实**：`@google/design.md@0.4.0` 支持 4.2 双模式写法且程序化 `lint()` 可用；`@tailwindcss/vite@4.3.4` 与 Vite 8.3.5 兼容，Tailwind 4 `@theme` 可由 Vite 插件产出 CSS。版本精确固定为 `@google/design.md@0.4.0`、`@tailwindcss/vite@4.3.4`、`tailwindcss@4.3.4`。
- 生成器实现约束：调用 `@google/design.md/linter` 的 `lint()`，从 `designSystem.colors`（Map）取各模式 hex；自己在生成前校验 `light-*` / `dark-*` 角色集合相等、无未解析引用、无既非 `primary` 又无模式前缀的颜色 token。官方 lint 只保证结构/引用/对比度，不保证模式角色集合相等，故该规则必须由生成器实现。
- 复查条件：`@google/design.md` 或 `@tailwindcss/vite` 升级时重跑本 spike 的两条命令（lint 与 build），确认双模式写法与 Vite 插件兼容。

## 决定

- 决定：是（按实测结论采用精确固定版本与 4.2 双模式写法）。
- 后续 task：无需单独立项，结论直接供 t036 实施使用；生成器模式角色集合校验属于 t036 AC-002 的实现职责。
- 无需后续理由：两项 UNVERIFIED-SPIKE 均已核实并回填 `task.md`。
