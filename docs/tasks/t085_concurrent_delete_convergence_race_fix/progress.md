---
tid: "t085"
slug: "concurrent_delete_convergence_race_fix"
title: "并发删除收敛竞态修复与压力回归测试"
status: "done"
branch: "t085_concurrent_delete_convergence_race_fix"
worktree: ""
review_level: "single"
review_limit: "5"
verify_limit: "5"
diff_anchor: "5461004dee9b1fac277232b0d5d2f9ddb40e9071"
spec_source_sha: "5461004dee9b1fac277232b0d5d2f9ddb40e9071"
depends_on: ""
conflicts_with: ""
note: "来源：pending p139。范围：修 ProfileService.request_deletions 的去重/建 intent 竞态（两并发请求偶发生成 2 个 intent，:347；另 :350 intent 以 profile_not_found 失败），补并发压力回归测试。证据：t077 final3 门禁与 t084 合入门禁均复现该用例失败，隔离复跑均通过。完成后用 pending.py close p139（--resolution resolved --fix-ref <task/commit> --write）。"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

### 根因（实测确认）

- **:347（两 intent）已确认机制**：部分唯一索引 `uq_profile_deletions_open_profile` 只覆盖非 done 阶段。胜者 intent 跑完变 done 后，败者的 `create_deletion` 插入不再被索引拦截，第二个 intent 建成。压力测试（10 轮 × 8 并发）在未修复代码上首轮即复现 `round 0: 2 intents`；300 次空闲 2 路循环零复现（窗口太窄），4 进程并行重负载 2 路循环 2000 次出现 7 次 two_intents。
- **:350（profile_not_found）已查清**：同一竞态的二阶表现。4 进程重负载复现中 7 次 `profile_not_found` 失败全部来自机器 accepted 守卫（`_drive_deletion` 的 `get_profile is None` 分支，`failed_stage=accepted`、`detail={}`），追踪栈均指向该守卫——迟到的第二个 intent 的机器启动时行已被第一个 intent 的机器删掉。创建者分支（784 行）2000 次迭代一次未触发；其前置（建 intent 前行已无且无任何 intent）经论证在单进程内不可能发生。
- **final3 单 intent 失败的说明**：日志原文（gate-t077-final3.log 559–615 行）确为 `len(ids)==1` 通过、唯一 intent 以 failed/profile_not_found 告终（创建 19:57:51.916、更新 19:57:52.354，约 438ms）。其精确交错未能在 2000 次重负载迭代中复现，未定论；修复覆盖其全部已建模路径：（a）per-profile 锁使进程内根本建不出第二个 intent；（b）守卫改动使“有 sibling intent 证明删除已发生”的情形直接标 done 而非失败。残余不确定性如实记录，不作推测性断言。
- **引用核对**：task.md 全部引用逐项核实存在——gate-t077-final3.log t078 小节 559–615 行、gate-t084-merge/logs/unit.log t078 小节 669–688 行、profile_service.py:722 request_deletions、test 文件 :338 用例、p139 文件；无虚假引用。

### 修复（三处，均在收敛路径内，不改删除业务语义）

1. `profile_service.py: request_deletions`：每 target 的查已有 intent → 建 intent 判定抽为 `_resolve_or_create_deletion`，调用方以既有 t062 `ProfileLockRegistry`（per-profile 锁）串行化。锁只在单 profile 收敛判定内持有，不跨 target、不等待机器：kick 只建 task，机器 clean 阶段的同锁等待有界；`delete_profile` 调 `request_deletions` 时不持 profile 锁，无死锁。
2. 同函数 `IntegrityError` 重试回路：50 轮 `find_open_deletion` 轮空后，回退查 `find_deletion_for_profile`（任意阶段）并 join 已完成胜者；仅当完全无 intent 时才重抛。补跨进程胜者已完成的缺口。
3. `_drive_deletion` accepted 守卫：行已无时查 sibling intent（repo 新增 `find_sibling_deletion`）；有 sibling 则标 done（detail steps database=ok，与 clean 阶段已有的“行已无即完成”语义对齐）；无 sibling 保持 `profile_not_found` 失败，真正缺失目标的收据语义不变（`test_missing_profile_fails_at_accepted` 仍过）。

### 新增测试（tests/unit/test_t078_deletion_lifecycle.py）

- `test_concurrent_requests_converge_under_repeated_pressure`：10 轮 × 每轮新 profile × 8 并发，逐轮断言单 intent 且最终 done（未修复代码首轮即红）。
- `test_late_duplicate_intent_completes_when_sibling_deleted_row`：迟到重复 intent 的机器守卫遇 sibling 已删行时标 done。
- `test_guard_still_fails_without_sibling_intent`：无 sibling 时守卫仍报 profile_not_found。
- `test_integrity_retry_joins_winner_that_completed`：mock create 在建出胜者并标 done 后抛 IntegrityError，验证重试回退 join 胜者。

### 验证（修复后）

- `test_t078_deletion_lifecycle.py` 隔离：22/22 通过（56.6s）。
- 连续 3 轮 `-n 4` 复跑该文件：22/22、22/22、22/22。
- 4 进程并行重负载复现脚本（`.scratch/t085_repro350.py`，每进程 500 次 2 路循环，共 2000 次）：two_intents 0 次、profile_not_found 0 次（修复前：two_intents 7 次、profile_not_found 7 次）。
- 全量门禁（`~/workspace/cloud-task-logs/gate-t085`，flock 串行，TMPDIR 落大盘）：protocol_drift_check 0、requirements_check 0、contract 0、integration 0、design_lint 0、design_check 0、frontend_test 0、frontend_build 0；unit exit 1——并行轮 2390 项（4 failed、2375 passed、1 skipped、10 errors）＋串行轮 84 passed。14 项非通过全部是已知老基线：t063 ×12（2 failed＋10 errors）、t068 ×2（failed）；a16 基线项本轮通过；t078 文件 22 项全在 passed 内；日志中 `database is locked` 出现 0 次。real_engine NOT_RUN（云端无 Docker，预期）。
- Round 1 审阅后修复重验（f003 仅注释措辞改动）：t078 文件隔离 22/22，3 轮 `-n 4` 全部 22/22。
- p139 已关闭：`pending.py close p139 --resolution resolved --fix-ref t085 --write`（status closed）。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-19T07:18:00+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t085_gen_f001|important|已修|AC-005 未完成：按 t084 先例以 fix-ref t085 关闭 p139 并打勾|docs/pending/p139_t078_concurrent_delete_convergence_race.md|
|t085_gen_f002|minor|已修|final3 单 intent 孤例残余不确定性：progress.md 已如实披露无已建模路径；修复覆盖全部已建模路径，列为观察项，若再现重开 p139|progress.md 实施笔记|
|t085_gen_f003|minor|已修|注释夸大 sibling 证明力：“只能经 sibling 机器消失”改为“sibling 是另一删除 pass 存在的证据”，逻辑不动|src/backend/cbrowser/adapters/database/repository.py: find_sibling_deletion|

### Round 2 (2026-11-19T07:27:00+08:00)

Round 2 零 finding。

### Round N (YYYY-MM-DDThh:mm:ss+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t000_code_f001|critical/important/minor|已修/遗留/撤回|一句话|文件:行 / pNNN / tid|

无 finding 时写“Round N 零 finding”。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足
- 测试：t078 文件隔离 22/22；连续 3 轮 `-n 4` 全部 22/22；4 进程重负载复现 2000 次零失败；全量门禁 8/9 套件过（unit 14 项非通过全为 t063/t068 老基线，`database is locked` 0 次）
- 黑盒：不适用（无 `[deploy]` AC，真实多进程并发不测）
- review：2 轮；Round 1 FAIL（仅程序性 AC-005 未完成）；Round 2 PASS，零 finding
- AC 判定：见 `task.md` 行内打勾（5/5）

### 结果摘要

- per-profile 锁原子化收敛判定（`_resolve_or_create_deletion`）、IntegrityError 重试回退已完成胜者、accepted 守卫有 sibling 标 done；新增 4 项测试；p139 已关闭（resolved，fix-ref t085）
- 遗留：final3 单 intent 孤例的精确交错未复现，列为观察项（见实施笔记），若再现重开 p139

### 长期文档闭环

在 active spec 的 front matter `tasks` 清单中登记当前 tid（`task.py specs list --json`）；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。

- specs_index: not_applicable: 本 task 无长期 spec 变更（收敛路径内部修复，不改跨模块行为、接口契约与 blueprint）
