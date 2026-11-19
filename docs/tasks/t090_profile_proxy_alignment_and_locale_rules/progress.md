---
tid: "t090"
slug: "profile_proxy_alignment_and_locale_rules"
title: "修复 ProfileForm 代理地域对齐展示、重置与地区匹配规则"
status: "done"
branch: "t090_profile_proxy_alignment_and_locale_rules"
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: "1f949747dc2d93a935aa9ed9448f0bd25b928b1d"
spec_source_sha: "1f949747dc2d93a935aa9ed9448f0bd25b928b1d"
depends_on: ""
conflicts_with: ""
note: "来源 p141 及用户确认 A2，暂不扩 ja-JP 语言"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 修复 `src/frontend/src/features/profiles/profile_locale.ts` 中 `timezoneForProxy`：抽取 `hasRegionTerm` 对 ASCII 英文地域单词/缩写（`la`/`ny` 等）按非字母边界正则匹配并补齐 `germany`/`japan`/`korea`/`china`/`france`/`australia`/`united kingdom`，防止 `"Tokyo Relay"` 误命中洛杉矶或 `"Germany"` 误命中纽约。
- 修复 `src/frontend/src/features/profiles/ProfileForm.tsx` 与 `src/frontend/src/i18n.tsx`：基于 `proxyMismatch` 实时比对当前 `timezone`、`locale` 与代理推断默认值（含异步 `proxies` 抵达场景），偏离时展示 `formAlignProxyOverriddenSummary` + `formAlignManualNote` + `profile-form-reset-alignment`；`fontRule` 改按真实 `values.include_cjk_fonts` 渲染；`locale` `onValueChange` 当已有代理推断时区或已有非空 `timezone` 时保留原时区不再覆写为 `Asia/Shanghai`。
- 保持 `SUPPORTED_LOCALES`（`zh-CN` / `en-US`）不变，未改动后端与 OpenAPI 契约。
- 先在 `profile_locale.test.ts` 与 `ProfileForm.test.tsx` 写入 4 条失败单测证实 RED，修复后 `npm test --prefix src/frontend -- --run src/features/profiles/profile_locale.test.ts src/features/profiles/ProfileForm.test.tsx` 23/23 通过。
- 按 Round 1 General Review（`t090_gen_f001` / `t090_gen_f002`）补齐 `ProfileForm.test.tsx` 重置摘要字体断言（中英文双向重置 `en.formAlignFontsEn` / `en.formAlignFontsZh`）及 `docs/specs/profile_management.md:110` 历史小节交叉修订说明；复跑全量前端 `87 files / 722 tests passed`、`test:types`、`build`、`design:lint` 与 `design:check` 全部通过。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-19T16:49:43+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t090_gen_f001|minor|已修|补充 AC-001/AC-002 点击重置对齐后对 `profile-form-alignment-summary` 含 `en.formAlignFontsEn` / `en.formAlignFontsZh` 的显式断言|`src/frontend/src/features/profiles/ProfileForm.test.tsx`:536-539,626-646|
|t090_gen_f002|minor|已修|修订 `docs/specs/profile_management.md` 历史 `t053+` 小节与 `t090` 语言不覆写既有非空/代理推断时区规则保持一致|`docs/specs/profile_management.md`:110|

### Round 2 (2026-11-19T16:59:42+08:00)

Round 2 零 finding，前轮 `t090_gen_f001` 与 `t090_gen_f002` 均已消除，全部 3 条 AC 独立复验 PASS。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：全量非 E2E 门禁 `./scripts/run_gates.sh` 9 个套件全部 `exit 0`（主仓 `.scratch/t090_non_e2e_gates/manifest.json` `all_passed: true`）；Round 1 修复后复跑 `npm test`（`87 files / 722 tests passed`）、`npm run test:types`、`npm run build`、`npm run design:lint`、`npm run design:check` 全部退出 0
- 黑盒：浏览器表单交互在 Vitest + Testing Library + i18n（真实 Radix Select / Combobox / React Query 异步加载）下完整验证，UI tokener/design lint/build 全部通过
- review：Round 2 PASS（3/3 AC `TICK-VALID`，零 finding）
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 修复 `ProfileForm` 代理地域偏离误报与隐藏重置按钮、CJK 摘要未读 `include_cjk_fonts`、切语言覆写时区以及 `timezoneForProxy` 英文缩写子串误判，保持 `zh-CN`/`en-US` 边界。

### 长期文档闭环

- 已在 [profile_management.md](../../specs/profile_management.md) front matter `tasks` 注册 `t090` 并补充长期规则小节；`docs/blueprint/domain.md` 无新增持久化/后端结构变更，以 `profile_management.md` 为契约权威。
