# Task review t085（reviewer_focus: 通用）

- task：`t085_concurrent_delete_convergence_race_fix`
- spec：`docs/tasks/t085_concurrent_delete_convergence_race_fix/task.md`
- diff_anchor：`5461004dee9b1fac277232b0d5d2f9ddb40e9071`
- target：`git diff 5461004dee9b1fac277232b0d5d2f9ddb40e9071`
- round：1
- reviewed_at：2026-11-19T07:17:14+08:00

reviewed_scope: d55a14ffecf3803d

## Findings

### t085_gen_f001 - AC-005 未完成：p139 仍为 todo，未执行 pending.py close

- 严重度：important
- 锚点：违反 AC-005（p139 经 `pending.py close p139 --resolution resolved --fix-ref <task/commit> --write` 关闭）
- 位置：`docs/tasks/t085_concurrent_delete_convergence_race_fix/task.md:33`（`- [ ] AC-005`，未打勾）；`docs/pending/p139_t078_concurrent_delete_convergence_race.md:4`（`status: "todo"`）
- 问题：实施侧未关闭 p139。实读 p139 文件 front matter 仍为 `status: "todo"`，task.md 中 AC-005 仍为 `- [ ]`。按 t084 先例（其 AC-005 在审阅前即以 fix-ref 任务引用关闭并经审阅核实），fix-ref 可用任务引用，不必等合并提交号，因此不存在无法关闭的客观障碍。
- 建议：运行 `pending.py close p139 --resolution resolved --fix-ref t085 --write` 关闭 p139，将 task.md 的 AC-005 打勾，然后走下一轮审阅复核。

### t085_gen_f002 - final3 单 intent 失败模式的精确交错仍未复现，残余不确定性未消除

- 严重度：minor
- 锚点：AC-003 的书面论证覆盖范围
- 位置：`docs/tasks/t085_concurrent_delete_convergence_race_fix/progress.md:32`
- 问题：progress.md 如实披露：final3 的单 intent 失败（`len(ids)==1` 通过、唯一 intent 以 failed/`profile_not_found` 告终，创建 19:57:51.916、更新 19:57:52.354）其精确交错在 2000 次重负载迭代中一次未复现，未定论。本轮独立核查确认该模式在进程内无已建模路径——单 intent 在 accepted 守卫处遇行已无且无 sibling 时仍会失败（新守卫只覆盖有 sibling 的情形），而行消失的唯一进程内途径是另一 intent 的机器（clean 阶段，`src/backend/cbrowser/services/profile_service.py:1121`，且 API 路由经 `service.delete_profile` 走 `request_deletions` 加入既有 intent、不直接删行）。三处修复覆盖了全部已复现的 :350 路径，但 final3 这一孤例仍无解释：它在修复前 2000 次迭代中亦未出现，修复后门禁与本轮 3×22 复跑亦未出现。
- 建议：不阻断；若未来门禁再次出现单 intent `profile_not_found` 失败，重开 p139 跟踪并补交错证据，不作推测性断言。

### t085_gen_f003 - `find_sibling_deletion` 文档注释夸大了 sibling 的证明力

- 严重度：minor
- 锚点：文档/注释与代码语义一致性
- 位置：`src/backend/cbrowser/adapters/database/repository.py:943-945`（“the row could only have vanished through a sibling machine”）
- 问题：该断言不成立：行还可经直接 `repo.delete_profile` 消失（`test_guard_still_fails_without_sibling_intent` 本身就是这样删行的），或从未存在过。代码逻辑本身无误——本轮已核查 sibling 作为充分证据是成立的：部分唯一索引 `uq_profile_deletions_open_profile` 覆盖全部非 done 阶段（含 failed，`src/backend/cbrowser/adapters/database/models.py:532`），且进程内 per-profile 锁阻止第二个 intent 产生，因此“从未存在过的 profile 配一个 failed sibling”这一反例无基例、不可达——但注释把充分条件写成了必要条件，会误导后续维护者放宽守卫。
- 建议：改写为 sibling 证明“另一删除 pass 曾针对该 profile”，而非行消失的唯一途径。

## 结论

- 本轮新发现：3 条（important 1 条，minor 2 条）
- 未进表的提示：以下三点已核查、无问题，不进表。(1) accepted 守卫不查 sibling 的 stage：已论证无害——“从未存在过的 profile 配一个 failed sibling”不可达（见 f003 的论证），且把条件收紧为 `stage == "done"` 反而会错杀 sibling 尚在 cleaning、行已删但未及标 done 的合法情形。(2) `IntegrityError` 重试在持有 per-profile 锁期间最多轮询 50×10ms：有界，无死锁——驱动端从不在等待请求路径的状态下持该锁，`delete_profile` 调 `request_deletions` 时不持 profile 锁（`src/backend/cbrowser/services/profile_service.py:1163-1185`）；锁的其余持有者（clean 阶段、bind/set_desired_state/duplicate/reset）均为只调 repo 的叶路径，无嵌套取锁。(3) AC-002 字面“多轮循环双并发”：以 10 轮×8 并发压力测试加保留的单次双并发原用例覆盖，8 并发交错严格宽于双并发，实质满足；红信号已在 base 副本上复现（见 AC-002 行）。
- 总体判断：代码与测试本身无阻断缺陷，四条已打勾 AC 全部复验成立；唯一阻断项是程序性的 AC-005 未完成（p139 未关闭），故本轮 verdict 为 FAIL，待关闭后重审。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。原双并发用例加 10 轮×8 并发压力测试均断言单 intent 且最终 done；本轮在 worktree 内自跑该文件 `-n 4` 三轮均为 22/22。
- AC-002：TICK-VALID，re_verified。新增 `test_concurrent_requests_converge_under_repeated_pressure`（10 轮×8 并发，真实 SQLite 库与真实 service，无 mock）及三项针对性测试；在 base 副本（5461004 + 新测试文件）上压力测试 3/3 失败、另两项新测试 2 项失败（红信号确认），无 sibling 守卫测试在 base 上通过（符合预期）。
- AC-003：TICK-VALID，re_verified。2000 次重负载复现中 7 次 `profile_not_found` 全部经追踪栈定位到 accepted 守卫（创建者分支 0 次）；修复覆盖该路径（per-profile 锁 + sibling 守卫）；final3 孤例残余不确定性已在 progress.md 如实披露，见 f002。
- AC-004：TICK-VALID，re_verified。本轮自跑 `test_t078_deletion_lifecycle.py` 连续 3 轮 `-n 4` 均为 22/22；门禁 gate-t085 的 unit.log 两段：并行轮 4 failed、2375 passed、1 skipped、10 errors（与 junit 一致，t078 22 项全 pass，a16 全 pass），`database is locked` 在全部 10 份门禁日志中出现 0 次；14 项非通过与 t077 final3 日志中的同一批（t063×12、t068×2）完全一致，属修复前已存在的老基线，与本 diff 文件无关。
- AC-005：TICK-VOID，re_verified。task.md:33 中 AC-005 未打勾，实读 `docs/pending/p139_t078_concurrent_delete_convergence_race.md` 前置区仍为 `status: "todo"`，未执行 `pending.py close`。

coverage = 5 / 5

verdict: FAIL

## Round 2 (2026-11-19T07:26:41+08:00)

- round：2
- reviewed_at：2026-11-19T07:26:41+08:00

reviewed_scope: bd3d9a36a30696a4

## Findings

本轮新发现：0 条。Round 1 至 Round 2 之间唯一的代码改动是 `src/backend/cbrowser/adapters/database/repository.py` 中 `find_sibling_deletion` 的文档注释措辞（见 f003 复核），逻辑未动；其余改动为 p139 关闭、task.md 打勾与 progress.md 记述，均已逐项核实，无新问题。

## 结论

- 前轮 finding 复核：
    - t085_gen_f001（important，AC-005 未完成）：已消除。实读 `docs/pending/p139_t078_concurrent_delete_convergence_race.md` 前置区现为 `status: "closed"`、`resolution: "resolved"`、`fix_ref: "t085"`，正文处理行亦已更新为 t085 关闭记录；`docs/tasks/t085_concurrent_delete_convergence_race_fix/task.md` 中 AC-005 已打勾（`- [x]`）。fix-ref 用任务引用 t085，符合 task.md 契约原文 `--fix-ref <task/commit>` 与 t084 先例。
    - t085_gen_f002（minor，final3 单 intent 孤例残余不确定性）：已消除（作为观察项如实披露）。`docs/tasks/t085_concurrent_delete_convergence_race_fix/progress.md` 实施笔记现含“final3 单 intent 失败的说明”段：如实记录精确交错在 2000 次重负载迭代中未复现、未定论，修复覆盖全部已建模路径，不作推测性断言；Round 1 处置表写明若再现重开 p139。无需代码动作。
    - t085_gen_f003（minor，`find_sibling_deletion` 注释夸大 sibling 证明力）：已消除。实读 `src/backend/cbrowser/adapters/database/repository.py:939-947`，注释现为“a sibling intent is the evidence that another deletion pass for this profile exists”，“只能经 sibling 机器消失”的必要条件措辞已改掉；方法体（按 profile_id 排除自身、按 created_at 倒序取 1 条）与 Round 1 审过的逻辑一致，未动。
- 本轮新发现：0 条
- 未进表的提示：以下三点已复核、无问题，不进表。(1) 三处修复的正确性复核不变：per-profile 锁仅在单 profile 收敛判定内持有、`delete_profile` 调 `request_deletions` 时不持 profile 锁（无死锁）；`IntegrityError` 重试 50 轮轮询后回退查任意阶段 intent 并 join 已完成胜者，仅完全无 intent 时重抛；accepted 守卫有 sibling 标 done、无 sibling 仍报 `profile_not_found`，与 clean 阶段“行已无即完成”语义及缺失目标收据语义一致。(2) 门禁 14 项非通过与老基线一致，与本 diff 无关（见 AC-004 行）。(3) `git log 5461004..HEAD` 为空，全部交付内容均为相对 base 的未提交 worktree 改动，与 Round 1 审过的交付形态一致；`git status --short` 中除 6 个 diff 文件外仅有本报告自身为未跟踪文件，无 reviewer 看不到的未跟踪交付文件。
- 总体判断：Round 1 的唯一阻断项（f001）已真正关闭，另两条 minor 均已落实，本轮无新 blocking finding，全部 AC 复验成立，故本轮 verdict 为 PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。Round 1 复验结论沿用（10 轮×8 并发压力测试加原双并发用例均断言单 intent 且最终 done）；本轮自跑 `tests/unit/test_t078_deletion_lifecycle.py`（`-n 4`）22/22 通过，其中含压力测试与原用例。
- AC-002：TICK-VALID，re_verified。Round 1 复验结论沿用（新增 4 项针对性测试均触达真实 SQLite 库与真实 service，base 副本红信号已确认）；本轮自跑该文件 22/22 通过，4 项新测试均在 passed 内。
- AC-003：TICK-VALID，re_verified。Round 1 复验结论沿用（2000 次重负载复现的 7 次 `profile_not_found` 全部定位到 accepted 守卫，修复覆盖该路径）；final3 孤例残余不确定性已在 progress.md 如实披露，见 f002 复核。
- AC-004：TICK-VALID，re_verified。本轮自跑 `tests/unit/test_t078_deletion_lifecycle.py`（`-n 4`）22/22 通过；门禁 gate-t085 的 unit.log 独立核查：并行轮 4 failed、2375 passed、1 skipped、10 errors，串行轮 84 passed；junit 的 unit.xml 中 t078 文件 22 项 0 失败，a16 相关 15 项 0 失败；14 项非通过逐项核对为 t063×12（2 failed＋10 errors）与 t068×2（failed），与 t077 final3 的同一批老基线一致；`database is locked` 在全部 10 份门禁日志中出现 0 次。
- AC-005：TICK-VALID，re_verified。实读 p139 前置区 `status: "closed"`、`resolution: "resolved"`、`fix_ref: "t085"`，task.md 中 AC-005 已打勾。

coverage = 5 / 5

verdict: PASS
