---
tid: "t047"
slug: "ui_theme_omni_restyle"
title: "前端主题改造：omni_panel 冷灰视觉与 Inter 字体体系"
status: "done"
branch: "t047_ui_theme_omni_restyle"
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: "ede48471178d9d69c6fe4903fea379ab9e3d6257"
depends_on: ""
conflicts_with: ""
note: "来源 2026-11-09 用户需求：参考 omni_panel DESIGN.md 改造主题/背景/字体/字号，不动主界面；用户确认全部推荐决策（AA-safe 色板、字重行高、omni 圆角、阴影覆盖、默认 dark）"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

1. 依赖替换：`src/frontend/package.json` 替换字体依赖为 `@fontsource-variable/inter@5.3.0` 与 `@fontsource-variable/jetbrains-mono@5.3.0`，移除 Space Grotesk 与 IBM Plex Mono，并更新 `package-lock.json`。
2. 样式入口更新：`src/frontend/src/styles/globals.css` 导入 Inter 与 JetBrains Mono 的 `wght.css`。
3. `DESIGN.md` 更新：
    - 采用 omni_panel AA-safe 冷灰调色板，确保 80+ 组组件颜色对 WCAG AA 对比度全部 ≥ 4.5:1。
    - 字体与字号尺度映射为 Inter Variable 与 JetBrains Mono Variable，声明 600/550/450/650 字重、1.2–1.55 行高与字距。
    - 圆角映射为 6/10/14/18 四档。
    - `## Elevation & Depth` 章节补充 `lg` 与 `xl` 阴影规范表格。
4. 生成器升级：`src/frontend/scripts/design_tokens.mjs` 自动从 `typography` 派生 `--font-ui` 与 `--font-mono`，输出字重、行高与字距变量，并解析 `## Elevation & Depth` 表格输出 `--shadow-lg` 与 `--shadow-xl` 及 `.dark` 覆盖。
5. 单测扩展：`src/frontend/scripts/design_tokens.test.mjs` 增加字体派生、字体族群一致性校验、字重/行高/字距输出与阴影表格解析覆盖。
6. 组件微调：`src/frontend/src/shared/ui/Table.tsx` 移除与 `mono-caps` token 字距重复的 `tracking-wide`。
7. 产物生成与验证：重新生成 `design_tokens.css`，通过 `design:lint`、`design:check`、`npm test`（73 文件 499 用例）与 `npm run build`。
8. 长期文档更新：同步 `docs/specs_index.md`（追加 t047）、`docs/specs/ui_design_system.md`、`docs/blueprint/frontend.md`，并在 `docs/blueprint/decisions.md` 中新增 ADR 027。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-09T22:15:00+08:00)

Round 1 零 finding。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：`npm run design:tokens`、`design:check`、`design:lint` 0 error/0 warning；`npm test --prefix src/frontend` 73 文件 499 用例全部通过；`npm run build --prefix src/frontend` 成功输出自托管 woff2 且无外部 CDN
- 黑盒：前端产物完整构建并通过 Selkies / Chrome 静态分发校验，所有页面布局、表单与浮层语义无入侵破坏
- review：Round 1 general review PASS（零 finding，reviewed_scope 指纹 92639f51b7b56d70 校验一致，6 条 AC 全部 TICK-VALID）
- AC 判定：见 `task.md` 行内打勾（AC-001 ~ AC-006 全部打勾）

### 结果摘要

- 前端视觉体系完整切换至 omni_panel 冷灰调色板与 Inter / JetBrains Mono 字体体系，满足全部 6 项验收标准，全流程门禁与测试 100% 通过。

### 长期文档闭环

- specs_index：`docs/specs_index.md` 的 `ui_design_system` 行已追加登记 `t047`。
- spec：`docs/specs/ui_design_system.md` §1 累积 t047，§2.2 契约同步。
- blueprint：`docs/blueprint/frontend.md` §6 与 `docs/blueprint/decisions.md` ADR 027 同步完成。
