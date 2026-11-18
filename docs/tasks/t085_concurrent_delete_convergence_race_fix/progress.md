---
tid: "t085"
slug: "concurrent_delete_convergence_race_fix"
title: "并发删除收敛竞态修复与压力回归测试"
status: "backlog"
branch: ""
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: ""
spec_source_sha: ""
depends_on: ""
conflicts_with: ""
note: "来源：pending p139。范围：修 ProfileService.request_deletions 的去重/建 intent 竞态（两并发请求偶发生成 2 个 intent，:347；另 :350 intent 以 profile_not_found 失败），补并发压力回归测试。证据：t077 final3 门禁与 t084 合入门禁均复现该用例失败，隔离复跑均通过。完成后用 pending.py close p139（--resolution resolved --fix-ref <task/commit> --write）。"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

无

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round N (YYYY-MM-DDThh:mm:ss+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t000_code_f001|critical/important/minor|已修/遗留/撤回|一句话|文件:行 / pNNN / tid|

无 finding 时写“Round N 零 finding”。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足 / 未满足
- 测试：待执行时填写
- 黑盒：待执行时填写
- review：待执行时填写
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 待执行时填写；遗留只写引用，不复制正文

### 长期文档闭环

在 active spec 的 front matter `tasks` 清单中登记当前 tid（`task.py specs list --json`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
