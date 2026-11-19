---
tid: "t087"
slug: "windows_variable_font_named_instances"
title: "修复 Windows 变量字体命名实例的网页匹配"
status: "done"
branch: "t087_windows_variable_font_named_instances"
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: "1531b20999354236467897f8e02eacfee0d447b8"
spec_source_sha: "1531b20999354236467897f8e02eacfee0d447b8"
depends_on: ""
conflicts_with: ""
note: "来源 p142，Windows 字体原件和映射隔离探针已核实"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 新增 XML 规则回归。运行原代码失败，改动后相关单测 31 passed、7 skipped。Windows 渲染的 E2E 套件 3 passed。

- 规则只处理 Windows 绑定目录下的 Segoe UI Variable 内部家族及对应 PostScript 名字，恢复 Text、Display、Small 的真实光学命名实例。原字体资产只读挂载。

- 固定引擎候选 Browser 镜像经真实 Runner 首次启动和重启，72px CSS 度量分别为 725 / 718 / 752，未知字体回退 612。Canvas 度量与此一致至 0.02px（该独立 task 的引擎噪声策略仍沿用基线）。两个启动中字体校验通过，浏览器 fontconfig 暴露中文覆盖字体为零。证据在主仓 `.scratch/runtime_identity_acceptance/t087_image_probe_r2.jsonl`。

- 第一轮评审用改名导入复现漏配。改用字体内部家族和 PostScript 名字，解除 basename 耦合；真实 Fontconfig 复验改名文件的 Text / Display / Small 原字体索引分别为 0 / 851968 / 196608。最新版候选镜像重跑 3 项字体 E2E 全过，真实 Runner 两次验证通过。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-19T09:45:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t087_gen_f001|important|已修|按字体内部家族和 PostScript 名称注册，改名实测仍匹配正确实例|src/backend/cbrowser/runtime_agent/fontconfig.py|

### Round 2

Round 2 复验前轮 finding 已修，两项 AC 均通过，无新 finding。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：专项 AC 均已验证，共享 Docker E2E 门禁待处理。
- 测试：首轮项目门禁各非 E2E 套件退出 0。最终代码相关单测 31 passed、7 skipped，真实字体 E2E 3 passed。
- 黑盒：最终 Browser 镜像经真实 Runner 两次启动验证字体度量、字体就绪及中文覆盖过滤。原字体改名后照常匹配 Text、Display、Small 的真实实例。共享 Docker E2E 老夹具缺陷见 p145。
- review：Round 2 PASS，两项 AC 独立复验，前轮 finding 已修，无新 finding。
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- Windows 字体运行时匹配真实命名实例。与 t086 联合验证见主仓 `.scratch/runtime_identity_acceptance/combined_probe_r2.jsonl`。

### 长期文档闭环

- 更新 `docs/specs/fingerprint_platform.md` 与 `docs/blueprint/domain.md`。
