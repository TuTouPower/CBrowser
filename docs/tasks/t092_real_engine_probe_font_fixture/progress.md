---
tid: "t092"
slug: "real_engine_probe_font_fixture"
title: "修复独立真实引擎探针的字体夹具"
status: "done"
branch: "t092_real_engine_probe_font_fixture"
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: "f11e4f4f1857d8de7c8d832cdb81de41be5e6473"
spec_source_sha: "f11e4f4f1857d8de7c8d832cdb81de41be5e6473"
depends_on: ""
conflicts_with: ""
note: "来源 p147；绑定已验证平台字体集，并在独立探针预检时报告缺失字体资产"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 新增快照绑定断言先证实缺字段，再让独立探针选取通过完整性校验的默认 Windows 字体集。探针容器只读挂载选中集，目标引擎快照读取同一 ID。
- 在真实 Linux arm64 容器验证缺失字体时预检退出 2，导入 Windows 字体集后两条探针均通过。实查容器字体挂载为只读。
- 证据见主仓 `.scratch/t092_real_engine_JZ9wym/missing/preflight.txt` 和 `.scratch/t092_real_engine_JZ9wym/verified/evidence.json`。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-19T22:27:30+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t092_gen_f001|minor|已修|候选先按内容寻址目录身份过滤，非规范目录名不再遮蔽较早有效集；新增可复现红测|scripts/automation_probe_evidence.py:73；tests/unit/test_a38_probe_evidence.py:155|

### Round 2 (2026-11-20T01:44:18+08:00)

Round 2 零 finding。前轮 t092_gen_f001 经独立复核已消除；AC-001 / AC-002 均 `TICK-VALID，re_verified`。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：f001 修复后新增非规范目录红测，并完成全量门禁 `python3 scripts/gate_run.py`（退出 0）；探针相关单测 `test_a38_probe_evidence.py` + `test_automation_probe_harness.py` 38 项通过，模板契约 388 项通过。Shell 语法、Markdown 格式、Git diff 检查通过。
- 黑盒：真实入口缺字体时退出 2。带字体的真实 Linux arm64 探针 2 项通过、零跳过，链路子套件 16 项通过。
- review：单路 general review Round 1 PASS（1 minor，已修防遮蔽）；Round 2 PASS（零 finding，`reviewed_scope=f3326e6656a24b73`，AC 2/2 复核有效）。
- AC 判定：见 `task.md` 行内打勾，2/2 已勾选。

### 结果摘要

- 独立探针满足 BrowserRunner 的字体绑定和挂载契约，缺失资产在预检报告。

### 长期文档闭环

在 active spec 的 front matter `tasks` 清单中登记当前 tid（`task.py specs list --json`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
