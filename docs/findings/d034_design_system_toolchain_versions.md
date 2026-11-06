# d034 设计系统工具链版本与双模式写法契约（t036 / s015）

- 来源：`docs/spikes/s015_design_system_toolchain/report.md` 正式 spike，2026-11-06 在 Node 26.13.0 下以精确固定版本实测。
- 结论：`@google/design.md@0.4.0` 的程序化 `lint()` 可用（`designSystem.colors` 为 `Map`，值含 hex/RGB/luminance）；plan 4.2 亮暗双模式写法（`primary` + 成对 `light-*` / `dark-*` + 成对 `<component>-light` / `<component>-dark` + `### Modes`）在 0.4.0 的官方 lint 下 0 error / 0 warning。
- 证据：`npx @google/design.md lint DESIGN_SPIKE.md` → `{"errors":0,"warnings":0,"infos":1}`；`import { lint } from '@google/design.md/linter'` 程序化调用返回 resolved color Map 与 `tailwindConfig`。
- 影响：t036 精确固定 `@google/design.md@0.4.0`、`@tailwindcss/vite@4.3.4`、`tailwindcss@4.3.4`；Vite 8.3.5（t033 固定）与 `@tailwindcss/vite` 构建实测通过（`vite build` 产出含 `@theme` token 的 CSS，不需要 PostCSS/autoprefixer）。**官方 lint 不检查 `light-*` / `dark-*` 角色集合相等，该校验须由生成器 `design:tokens` 实现（AC-002）**。Vite 8 的 `root` 必须写在 config，不可用 `--root` CLI 参数。
- 现状：有效
- 复查条件：`@google/design.md` 或 `@tailwindcss/vite` 升级、或 plan 4.2 写法调整时重跑 s015 的 lint 与 build 两条命令。
- 采纳：t036（无后续 tid）。
