---
tid: "t096"
slug: "geoip_explicit_injection_and_error_semantics"
title: "GeoIP 依赖显式注入与测速失败语义保真"
status: "backlog"
branch: ""
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: ""
spec_source_sha: ""
depends_on: ""
conflicts_with: ""
note: "用户 2026-11-20 授权（p153）：测速全失败真因为 t094 把探测迁入 API 进程后，GeoIP 路径靠隐式环境变量传递且只配给 supervisor，api 进程查不到数据库报 geoip_db_missing（84/88），前端兜底成笼统「测速失败」掩盖根因。按开发铁律从根修：依赖显式注入、配置按谁用谁配、错误语义保真、补真实路径查找测试。"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-20：来源 p153，生产排查与铁律分析已确认；AC 覆盖显式注入、配置归位、错误语义保真与验证闭环，尚未实施。

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
