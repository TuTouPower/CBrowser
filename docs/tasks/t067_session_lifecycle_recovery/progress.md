---
tid: "t067"
slug: "session_lifecycle_recovery"
title: "断线重连状态修复与无人连接环境保留"
status: "dropped"
branch: ""
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: ""
depends_on: ""
conflicts_with: ""
note: "只修断线重连；无人连接不停止不销毁；移除启动治理等新增功能；拟合并 t061，待确认; merged into t061"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-13 审阅修订：删除 AC-002、AC-007，编号永久退休；AC-004 移除 reserveTab，AC-006 移除无消费者协议/webhook功能。恢复修复不依赖 t066 身份模型或 t063 改写全部 Selkies 扩展；共享文件用冲突约束。

- 本次仅维护 backlog；不 start、不实现；旧归档来源只追加转办链，不改写历史。

- 调度字段经 task.py edit 写入；plan 的 runnable 只指依赖/冲突候选，不代表产品 BLOCKING 已解决。

- 调度依据：恢复 UI 与 t061、Stream 恢复与 t063、Gateway 握手与 t064、core/operation journal 与后端 task 重叠；现有 helper 已可用，修 bug 不需等待未设计的身份模型或 Selkies 改写。

- 用户最新裁决：只修断线重连；原 AC-003/004/005 及启动治理范围取消，不新建替代 task；新增 AC-008 保留无人连接环境，AC-002/007 继续退休。

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

在 specs_index 行的 task 清单中登记当前 tid（格式见 `.repo_template/docs/usage.md`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
