---
tid: "t029"
slug: "automation_compatibility_probe_harness"
title: "交付自动化兼容性基线与目标引擎验证探针"
status: "backlog"
branch: ""
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: ""
depends_on: ""
conflicts_with: ""
note: "来源 p028；云端 Muse 以目标引擎二进制执行指纹增量与 Dialog 基线，真实镜像复核交 t032"
---

# Task 过程总账

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-04：从 p028（云端研究及探针；真实引擎结论交 t032） 聚合立项，核实基线 main@c6a9322；只创建 backlog，不 start。
- 云端范围与本地最终 t032 分离；真实环境未执行不能按通过回填。
- 2026-11-04：按三方审阅与用户要求修订：指纹增量（L0–L6）与 CDP/XTEST 比较改为云端以 cloakbrowser linux-x64 目标引擎执行并预先登记阈值，云端前提不可用时向用户报告 BLOCKED；新增 no_defaults、下载覆盖、Browser.close 与 Dialog 基线；最后 Tab/adopt 移交 t030。

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
