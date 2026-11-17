---
tid: "t080"
slug: "linux_native_runtime_storage"
title: "运行数据迁入 Linux 原生卷并提供可恢复迁移"
status: "backlog"
branch: ""
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: ""
spec_source_sha: ""
depends_on: ""
conflicts_with: "t075,t076,t078"
note: "2026-11-18 用户授权详细立项；仅创建 backlog，不实施、不发布。"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 创建记录：2026-11-18T00:31:35+08:00，用户要求按已核实资源问题与架构方案详细立项；仅创建 backlog，尚未实施、验证业务 AC 或获得本批 commit/push 授权。
- 跨 task 契约与脱敏现场基线：docs/tasks/t080_linux_native_runtime_storage/architecture_scope.md。长期 specs/blueprint/ADR 在对应实施 finalization 同步，本批不预写生效结论。
- 外部能力仍需正式 spike：见 task.md 未知契约清单。创建门禁通过不等于 SDK/subpath 或最小权限已经实测。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

尚未开始 review，无 finding 或验收结论。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：待执行
- 测试：待执行时填写
- 黑盒：待执行时填写
- review：待执行时填写
- AC 判定：见 `task.md` 行内打勾；创建时全部未勾选

### 结果摘要

- 待执行时填写

### 长期文档闭环

执行 finalization 时更新关联 active spec 的 tasks 清单及 task.md 指定 blueprint/ADR。正式 spike 通过工具创建，结论入 findings 并回填；创建期不提前声明实施或闭环。
