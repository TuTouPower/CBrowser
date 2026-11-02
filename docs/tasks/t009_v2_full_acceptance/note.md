---
tid: "t009"
slug: "v2_full_acceptance"
title: "完成正式拓扑安全与性能输入压力验收"
status: "backlog"
branch: ""
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: ""
depends_on: "t012"
conflicts_with: ""
note: ""
---

# Task 过程总账

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-02（创建期补记，出处 docs/archive/handoff.md 对应节与 commit 856757d）：用户决定 t014 drop，依赖由 t013,t014 改为 t013；AC-003 由1000次自动化输入/剪贴板压测改为真实 Chrome 手动清单；p015 以 transferred 转入本 task；剪贴板改为 seamless 同步。用户确认不恢复上述降级。
- 2026-11-02（审阅 adoption 重排，出处 docs/reviews/review_20261102_201727/adoption_decision.md）：依赖改为 t012（正式部署产物先于验收）；AC-005 中 coturn/凭证切换项待 t015 媒体链路结论确定后由 task 维护改写。

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

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
