# 027 omni 视觉系统迁移采用 AA-safe 色板与 DESIGN.md 派生字体字重（2026-11-09T22:00:00+08:00，t047）

- 背景：用户要求前端界面参考 omni_panel 的 `DESIGN.md` 改造视觉风格（冷灰主题、Inter 字体、高字重标题、大圆角与柔和阴影），且不动主要界面与交互。直接复制 omni 色值在现有 `design:lint` 门禁下有 4 处因 WCAG AA 对比度不足（< 4.5:1）而失败（亮色 accent、亮色 danger、暗色 on-accent、亮色 muted 在背景上）。同时 `@google/design.md` linter 将 front matter 中未知的 `shadows`/`motion` 视作 warning（阻断门禁），且原生成器硬编码 Space Grotesk 字体、未输出字重与行高变量。
- 选项：
    1. 放宽门禁（忽略 contrast warning 或允许部分非 AA 颜色对），手写 Tailwind 阴影配置。
    2. 采用 AA-safe 变体调色板（亮色 accent `#2F66E0`、亮色 danger `#DC2626`、暗色 on-accent `#0B1220`、亮色 muted `#5C6478`），生成器直接从 `DESIGN.md` 的 `typography` 派生字体栈，输出字重、行高与字距变量，并从 `## Elevation & Depth` 正文表格解析 `--shadow-*` 阴影变量；保持 `.dark` 首帧机制不变。
    3. 彻底重构前端主题架构为 `data-theme` 与五档强调色切换。
- 结论：采用选项 2。在不破坏任何业务代码与首帧机制的前提下，纯靠 token 管线升级完成整体视觉换肤；全部颜色对 100% 满足 WCAG AA 4.5:1 门禁；字体平滑迁移至 Inter Variable 与 JetBrains Mono Variable；圆角与阴影全局自动更新。选项 1 违背严格门禁质量铁律；选项 3 超出用户“只改主题背景字体字号、不动主界面”的明确需求范围。
- 替代：本条修订 ADR 025 中的字体栈声明（Space Grotesk / IBM Plex 替换为 Inter / JetBrains Mono）与单字重假设（生成器扩展输出字重、行高、字距与阴影）。
- 修订（2026-11-13，t059）：本条「全部颜色对 100% 满足 WCAG AA 4.5:1 门禁」的声称范围在此收紧并落实为门禁事实。此前官方 linter 的 contrast-ratio 仅覆盖 components 成对 textColor/backgroundColor；t059 实测发现门禁外真实不达标：亮色 warning 作文字对亮色背景仅 2.04:1、亮色 danger 作文字对亮色页面背景 4.01:1、亮 / 暗 on-surface-subtle 对 raised/subtle 底色 3.91–4.50:1、亮色分组 teal/green/amber/orange 作图形对亮色背景低于 3.0:1。t059 将对比度门禁补齐为三类全覆盖（成对 component、仅 textColor 的 component 对同模式四种底色、DESIGN.md `## Contrast` 表声明的代码直用文字对 4.5:1 与图形对 3.0:1），并修正 8 个 token 至门禁通过（light-warning `#F5A524`→`#8D5F15`、light-danger `#DC2626`→`#CA2323`、light-on-surface-subtle `#626A7D`→`#61687B`、dark-on-surface-subtle `#858D9C`→`#929AA7`、light-group-teal `#0EA5A3`→`#0C8F8E`、light-group-green `#16A34A`→`#149443`、light-group-amber `#CA8A04`→`#AC7603`、light-group-orange `#EA580C`→`#DE530B`）。自此 AA 声称以生成器门禁（design_lint / design_check）的实际覆盖面为准，不再作门禁外推断。
