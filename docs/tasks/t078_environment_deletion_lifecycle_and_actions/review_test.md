# Task review t078（reviewer_focus: 测试）

- task：`t078_environment_deletion_lifecycle_and_actions`
- spec：`docs/tasks/t078_environment_deletion_lifecycle_and_actions/task.md`
- diff_anchor：`9c203a631e008e6d060161a2c41551b35635cfeb`
- target：`git diff 9c203a631e008e6d060161a2c41551b35635cfeb`
- round：1
- reviewed_at：2026-11-18T01:08:28+08:00

reviewed_scope: 469dc26b823e4530

## Findings

### t078_test_f001 - 批量删除目标集合用 arrayContaining 弱断言，无法发现误删未选中的第三个环境

- 严重度：important
- 锚点：AC-005「批量删除严格作用于明确确认的ID集合……不误删其他行」
- 位置：`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx:1008`（用例 "deletes the confirmed set through one batch request after explicit confirmation"）
- 问题：断言为 `expect(calls[0]?.[0]).toEqual(expect.arrayContaining(["p1", "p2"]))`，只验 p1/p2 被包含，不验集合精确相等。夹具中存在未选中的第三个环境 p3（同文件 `fixture()`，p3 为 error 状态行）：若确认时发送的 ID 集合被实现错误地扩大为 ["p1","p2","p3"]（例如冻结目标被可见行集合替代），本用例仍全绿，AC-005 的「严格集合 / 不误删其他行」在前端发送侧没有被真正证伪过。后端 unit/integration 测试只验证服务端对「收到的集合」的逐项处理，无法补上前端多发 ID 这一环。属危险模式扫描中的弱化断言（包含匹配替代精确相等），且落在删除不可逆的安全关键路径上。
- 建议：改为精确集合断言，如先断言数组长度为 2 再 `expect([...calls[0][0]].sort()).toEqual(["p1", "p2"])`，并补断言 p3 行在批量完成后仍存在/未被选中处理。

### t078_test_f002 - AC-001 的卡片布局与过渡/异常状态删除入口无测试断言

- 严重度：minor
- 锚点：AC-001「每个表格行及卡片在运行、停止、过渡与异常状态下都有最右红色删除入口，停止另行呈现且可用性有解释」
- 位置：`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx:1125` 与 `:1159`（仅表格 running/stopped 两行）；五状态用例 `:622` 只断言状态文案与错误 tooltip，不断言删除/停止按钮
- 问题：新用例只覆盖表格布局下 running 行（删除最右、danger、title 说明）与 stopped 行（danger 删除）。卡片布局从未断言删除入口（卡片与表格共用 `EnvironmentRowActions` 组件，风险较低但未经测试证实）；starting/stopping/error 状态行是否始终呈现删除入口、stopping 时停止按钮的禁用与 title 说明均无断言。属覆盖可更广，不阻断。
- 建议：补一条卡片布局删除入口断言，以及一条 stopping 状态行断言（删除在位、停止禁用且 title 为停止中说明）。

### t078_test_f003 - AC-004 的迟到事件与 cleaning 阶段恢复无测试

- 严重度：minor
- 锚点：AC-004「旧实例迟到事件不能复活已删除目标或误删新实例；服务重启不会失去已接受的执行结果」
- 位置：`tests/unit/test_t078_deletion_lifecycle.py:226`（resume 用例仅从 stopping 阶段构造意图）、`:168`（新实例围栏用例）
- 问题：幂等重复受理（unit `:144` + integration `test_repeat_batch_post_joins_existing_intent`）、新实例围栏、stopping 阶段 resume 均有真实覆盖；但 resume 从 cleaning 阶段恢复、以及删除完成后旧实例迟到 observed 事件/运行时事件到达不复活目标，均无用例。属覆盖可更广，不阻断。
- 建议：补 cleaning 阶段意图 resume 收敛用例，以及删除 done 后对旧 instance 调用 report_observed_state 应失败且 profile 仍不存在的断言。

### t078_test_f004 - 删除弹窗本身的 Escape 关闭与焦点回归未在删除流程层测试

- 严重度：minor
- 锚点：AC-002「取消或Escape不执行，背景不可误操作且焦点管理正确」
- 位置：`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx:1105`（仅测取消按钮零请求；全文件无 Escape 用例）
- 问题：删除流程层只测了点击取消按钮不发请求。Escape 关闭、焦点陷阱与关闭后焦点回归由共享 `Dialog` 组件的既有测试覆盖（`src/shared/ui/ui.test.tsx`，本轮实跑 14 条全过，含 focus trap / Esc / restore focus），删除弹窗确实复用该组件，故风险低；但删除弹窗接线层（关闭后 deleteTargets 清空、焦点回到删除按钮）没有一条流程级断言。属覆盖可更广，不阻断。
- 建议：在删除流程用例中补一条 Escape 关闭且 createDeletions 未被调用的断言即可。

## 结论

- 改测方向复核：无「迁就实现」的改测。diff 中被整体替换的旧用例均有规格归因且替换为新语义的等价或更高层覆盖：前端六条（八列→七列、相对时间移出表格、运行计数移除、逐条 DELETE+toast→单次批量受理+弹窗逐项结果、运行行无删除按钮→停止删除并存）在测试内逐条注明理由；`tests/unit/test_t035_profile_domain.py` 两条（运行中拒绝删除→经停止收敛完成；目录清理失败只记日志仍报成功→清理失败即删除失败于 cleaning、Profile 行保留）与 AC-003/AC-006 新契约一致，旧的「静默成功」预期被删除而非就地改成新输出；`tests/unit/test_t054_migration.py` head 断言与 `tests/unit/test_t056_migrations.py` golden delta 按既定登记模式更新（恰新增 profile_deletions 表与索引，并逐列校验）。
- 危险模式扫描（已逐条调查）：无恒真断言、无删/反转 expect、无注释掉断言、无 .skip/.only、无新增 eslint-disable/@ts-ignore/# type: ignore（t035 中两处 type: ignore 为存量未改动行）；mock 边界合规——前端 stub 只 mock API client 系统边界且 fake 按真实阶段契约推进并返回快照副本，后端 artifact cleaner 经生产注入缝 `set_artifact_cleaner` 注入失败，`shutil.rmtree` monkeypatch 为文件系统故障注入，被测状态机逻辑本身未被 mock。新增用例中 `waitFor(..., { timeout: 5000 })` 经核对与批量查询 1s 轮询间隔（`src/frontend/src/features/profiles/useProfilesQuery.ts:325`）匹配，属等待服务端阶段推进的必要窗口，不作阈值掩盖 finding。唯一弱化断言命中即 f001。
- 本轮新发现：4 条（important 1、minor 3）
- 未进表的提示：无
- 总体判断：后端生命周期与 API 测试可信且实跑全过（本轮复跑 unit/integration/t035/t054/t056 共 47 条全过，前端 EnvironmentListPage 30 条全过），但 f001 使 AC-005「严格 ID 集合」的前端证据不足，打勾不成立，须修断言后重审。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。实跑 EnvironmentListPage.test.tsx 30 条全过：七列表头且无最后活跃列、无运行计数、表格 running/stopped 行删除固定最右且 danger、running 行删除 title 说明先停后删（卡片与过渡/异常状态入口未断言，见 f002 minor）。
- AC-002：TICK-VALID，re_verified。批量与单项用例断言确认前 createDeletions 零调用、弹窗列出冻结目标、取消后弹窗关闭且 delete 与 createDeletions 均未调用；Escape/焦点由共享 Dialog 既有测试覆盖，本轮实跑 ui.test.tsx 14 条全过（删除流程层未单独测 Escape，见 f004 minor）。
- AC-003：TICK-VALID，re_verified。实跑 tests/unit/test_t078_deletion_lifecycle.py 与 tests/integration/test_t078_deletion_api.py 全过：停止超时 failed 于 stopping 且 profile/绑定/目录全保留、重试后收敛 done、同步 DELETE 运行目标 409 带 stage=stopping；前端失败用例断言弹窗内 failed_stage（cleaning/stopping）、具体 error 与可用的重试入口。
- AC-004：TICK-VALID，re_verified。重复 request_deletions 与重复 POST 均返回同一 operation id（unit 与 integration 各一条）；resume_pending_deletions 从 stopping 阶段恢复并收敛 done；cleaning 前新实例绑定使删除 failed 于 instance_changed 且 profile 保留（迟到事件与 cleaning 阶段 resume 未测，见 f003 minor）。
- AC-005：TICK-VOID，re_verified。逐项独立成败、失败项保留选择与重试、成功项清除选择均有真实覆盖，但「严格作用于确认 ID 集合」的前端唯一断言是 arrayContaining 子集匹配（EnvironmentListPage.test.tsx:1008），夹具中未选中的 p3 即使被多发也不会被发现，证据不足以支持打勾（见 f001）。
- AC-006：TICK-VALID，re_verified。artifact 清理失败 failed 于 cleaning、detail.steps.artifacts 记录 error 且 profile 行保留、换可用 cleaner 重试后 done；目录清理失败使删除失败且 error/detail 可追踪（t035 替换用例）；批量独立性用例证明单项失败不影响其他目标，其他环境数据不受影响。
- AC-007：TICK-VALID，trust_prior。按 task.md 契约区「[deploy] AC 打勾处置注记」作处置型判定：云端可做部分已完成（门禁证据 .scratch/t078_gate_evidence/ 与 gate5/gate6 日志在位，新增 unit 11 条、integration 6 条、前端新用例全过且无新增基线失败），真实隔离环境验证已登记 pending p128（status todo）待本地补验；本 reviewer 无法在云端复验真实 Docker/Chrome 删除，依赖实施侧证据与 p128 登记。

coverage = 6 / 7

verdict: FAIL

## Round 2 (2026-11-18T01:28:44+08:00)

- task：`t078_environment_deletion_lifecycle_and_actions`
- diff_anchor：`9c203a631e008e6d060161a2c41551b35635cfeb`
- target：`git diff 9c203a631e008e6d060161a2c41551b35635cfeb`

reviewed_scope: 6e3f303e22a58022

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核：
    - t078_test_f001（important）：已消除。批量删除用例已改为精确集合断言——`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx:1010-1013` 先断言 `requestedIds` 长度恰为 2，再断言排序后精确等于 `["p1", "p2"]`；未选中的 p3 一旦混入即失败，不再是 `arrayContaining` 子集匹配。本轮实跑该文件 32 条全过。
    - t078_test_f002（minor）：已消除。新增用例 `shows a rightmost danger delete entry in every runtime state and in card layout`（`EnvironmentListPage.test.tsx:1035`）遍历 p1–p5 五种状态（running/stopped/error/starting/stopping），逐一断言删除入口存在且为操作区父容器最后一个子元素（最右）；断言 running/starting 删除 title 为先停后删说明、starting 停止入口可用、stopping 时启动禁用且删除入口与 title 仍在、error 态无停止入口但删除入口在位；随后切换卡片布局逐一断言五种状态的删除入口都存在。本轮实跑通过。
    - t078_test_f003（minor）：已消除。新增 `tests/unit/test_t078_deletion_lifecycle.py:354` `test_resume_pending_deletions_from_cleaning`：直接构造 stage=cleaning 的意图，断言 resume 返回 1、意图收敛 done、profile 与目录全清；新增 `:381` `test_late_instance_event_does_not_resurrect_deleted`：删除 done 后对旧实例调用 `report_observed_state` 返回 None、profile 仍不存在、无 open 意图、原意图仍 done。本轮实跑通过。
    - t078_test_f004（minor）：已消除。新增用例 `closes the delete dialog on Escape without sending a request`（`EnvironmentListPage.test.tsx:1090`）：在删除弹窗层派发 Escape，断言弹窗关闭、`createDeletions` 前后均未被调用、焦点不留在已卸载弹窗内。本轮实跑通过；焦点回归触发元素的精确断言仍由共享 Dialog 既有测试承担（`src/shared/ui/ui.test.tsx` 断言 `document.activeElement` 回到 trigger，本轮实跑 14 条全过），删除弹窗复用该组件。
- 改测方向复核：无「迁就实现」的改测。本轮修复对既有测试的唯一改动是把 f001 的子集断言强化为精确集合断言（收紧而非迁就）；其余均为新增用例（前端 2 条、后端 unit 4 条含 code 轴回归、integration 1 条），断言的都是用户/接口可观察结果（新批次回查含意图且收敛 done、并发只产生一个意图 id、唯一索引拒绝第二个 open 意图），未把任何旧预期就地改成新实现输出。
- 危险模式扫描（本轮逐条复查）：无恒真断言、无删/反转 expect、无注释掉断言、无弱化断言（`arrayContaining` 仅剩注释中提及、已不作断言）、无 .skip/.only、无新增 eslint-disable/@ts-ignore/# type: ignore；新增后端回归测试经生产注入缝与真实仓储/HTTP 层验证，未 mock 被测状态机逻辑。
- 本轮新发现：0 条
- 未进表的提示：卡片布局下只断言删除入口存在，未逐卡断言最右与 danger 类名（表格五状态已逐一断言最右，danger 类名由 t073 用例对 running/stopped 行断言，且卡片与表格共用同一 `EnvironmentRowActions` 组件，风险低）；f004 的焦点断言只验焦点不在已卸载弹窗内、未精确指向删除按钮，精确回归由共享 Dialog 测试覆盖。均为可选加强，不阻断。
- 总体判断：Round 1 四条 finding（1 important + 3 minor）已全部真实消除且无新问题；本轮独立实跑后端 t078 unit+integration+t035 共 37 条全过、前端 EnvironmentListPage 32 条与 ui.test 14 条全过，修复后门禁证据（t078_gate7.log 与 .scratch/t078_gate_evidence2/）与 progress 所述基线/flaky 定性一致，全部 AC 打勾成立。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。本轮实跑 EnvironmentListPage.test.tsx 32 条全过：七列无最后活跃列、无运行计数，五种状态（running/stopped/error/starting/stopping）表格行删除入口均在位且最右、卡片布局五种状态删除入口均存在，running/starting 删除 title 说明先停后删（见 f002 复核）。
- AC-002：TICK-VALID，re_verified。新增删除弹窗层 Escape 用例断言关闭且 createDeletions 零调用、取消用例断言零请求，确认前零请求与冻结目标断言仍在；共享 Dialog 的焦点陷阱/Escape/焦点回归由 ui.test.tsx 14 条实跑全过覆盖（见 f004 复核）。
- AC-003：TICK-VALID，re_verified。本轮实跑 tests/unit/test_t078_deletion_lifecycle.py 与 tests/integration/test_t078_deletion_api.py 全过：停止超时 failed 于 stopping 且数据全保留、重试收敛 done、同步 DELETE 运行目标 409 带 stage=stopping；前端失败用例断言弹窗内 failed_stage、具体 error 与重试入口。
- AC-004：TICK-VALID，re_verified。新增 cleaning 阶段 resume 收敛与删除后迟到 observed 事件不复活用例实跑通过；重复受理/重复 POST 返回同一 operation id、并发请求只产生一个 open 意图、failed 再确认归入新批次并收敛 done 的回归用例均实跑通过。
- AC-005：TICK-VALID，re_verified。批量请求 ID 集合已改为长度恰 2 且排序后精确等于 ["p1", "p2"] 的断言（EnvironmentListPage.test.tsx:1010-1013），未选中的 p3 混入即失败；逐项独立成败、失败项保留选择与重试、成功项清除选择的既有覆盖仍实跑通过（见 f001 复核）。
- AC-006：TICK-VALID，re_verified。本轮实跑含 tests/unit/test_t035_profile_domain.py 在内共 37 条后端测试全过：artifact/目录清理失败 failed 于 cleaning、detail.steps 记录 error 且 profile 行保留、重试后 done；批量独立性用例证明单项失败不影响其他目标。
- AC-007：TICK-VALID，trust_prior。按 task.md 契约区「[deploy] AC 打勾处置注记」作处置型判定：云端可做部分已完成（修复后门禁证据 t078_gate7.log 与 .scratch/t078_gate_evidence2/ 在位，失败项与基线/flaky 定性一致、无新增失败），真实隔离环境验证已登记 pending p128（status todo）待本地补验；本 reviewer 无法在云端复验真实 Docker/Chrome 删除，依赖实施侧证据与 p128 登记。

coverage = 6 / 7

verdict: PASS
