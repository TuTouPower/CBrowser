---
tid: "t021"
slug: "control_api_artifact_contracts"
title: "统一控制 API 与文件交换契约"
status: "backlog"
branch: ""
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: ""
depends_on: ""
conflicts_with: "t020"
note: "review_20261103_185924：A2/A4/A5/A6/A7/A12/A31/A40/A41/A42/A46/A54；用户授权分组立项，不实施"
---

# Task 过程总账

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

2026-11-03：用户授权按职责合并立项，本 task 为 53 项采纳结论中 12 项的唯一主承接；完整范围与 AC 对应见 task.md。现有 t019/t020 保留，原 A36/A37 拒绝；本轮未 start、未实现、未跑业务测试。

创建验证：`task.py preflight t021 --creation` 为 PASS；工作区未提交提示属于本批新建文档。无待外部用户决定的产品选项。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

尚未开始 review，无已登记 finding。

无 finding 时写“Round N 零 finding”。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：未实施，AC 全部未验证
- 测试：尚未执行
- 黑盒：尚未执行
- review：尚未执行
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- 本次仅完成创建；无实施结果。遗留只写引用，不复制正文

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
