# Task review t078（reviewer_focus: 代码）

- task：`t078_environment_deletion_lifecycle_and_actions`
- spec：`docs/tasks/t078_environment_deletion_lifecycle_and_actions/task.md`
- diff_anchor：`9c203a631e008e6d060161a2c41551b35635cfeb`
- target：`git diff 9c203a631e008e6d060161a2c41551b35635cfeb`
- round：1
- reviewed_at：2026-11-18T09:08:36+08:00

reviewed_scope: 469dc26b823e4530

## Findings

### t078_code_f001 - 加入既有意图的目标在新批次中不可见，再次确认删除静默失效

- 严重度：important
- 锚点：AC-005（批量删除严格作用于明确确认的 ID 集合、失败项保留结果和重试入口）；连带 AC-003 的「界面显示可重试的具体失败阶段」在该路径下同样不成立
- 位置：`src/backend/cbrowser/services/profile_service.py:660-672`（`request_deletions`）、`src/backend/cbrowser/adapters/database/repository.py:874-880`（`list_deletions_for_batch`）、`src/backend/cbrowser/api/v1/router.py:605-615`（`get_profile_deletion_batch`）、`src/frontend/src/features/profiles/EnvironmentListPage.tsx:264-269,476`（`confirmDelete` 与弹窗 operations 来源）
- 问题：`request_deletions` 对已有未终结意图的目标直接返回既有 operation（其 `batch_id` 仍是最初批次），却把一个全新的 `batch_id` 作为本次批次返回；前端确认后丢弃 POST 响应里的 operations、只按新 `batch_id` 轮询批次查询，而批次查询按存储的 `batch_id` 严格过滤。可复现失败场景：①某环境删除失败（如停止超时）后用户关闭弹窗、重新选中该环境再次点删除并确认——返回的新批次不含该意图，批次查询为空集时路由直接 404，前端 `deletionBatch.data` 为空、弹窗停留在确认态，再点确认只是重复同一循环；且既有意图处于 `failed` 时 `request_deletions` 连驱动都不再触发（`profile_service.py:670` 仅对非 failed 踢驱动），删除永远不会执行，用户也看不到失败阶段与重试入口。②部分目标加入既有意图、部分新建时，加入的目标在弹窗里永远显示「已排队」，不显示 done/failed/重试，成功后也不会退出选择。单元/集成测试只断言重复 POST 返回同一 operation id（`tests/unit/test_t078_deletion_lifecycle.py` 的 `test_repeat_request_joins_same_intent`、`tests/integration/test_t078_deletion_api.py` 的 `test_repeat_batch_post_joins_existing_intent`），没有按新批次回查，因此未捕获该断裂。
- 建议：让受理返回的批次与批次查询口径一致——例如加入意图时把其 `batch_id` 更新为本次批次（或批次查询按受理时返回的 operation id 集合解析）；同时前端改为以 POST 返回的 operations 为准轮询单项/批次；既有 `failed` 意图被再次确认时应恢复驱动或至少在弹窗中原样呈现其失败阶段与重试入口。补一条「失败后关弹窗→重新确认→新批次可查且可收敛」的回归测试。

### t078_code_f002 - blueprint 记载删除意图含 retry_count 字段，实现中不存在

- 严重度：minor
- 锚点：行为缺陷（文档与实现不一致）
- 位置：`docs/blueprint/domain.md:66` 对照 `src/backend/cbrowser/adapters/database/models.py` 的 `ProfileDeletionModel` 与 `src/backend/migrations/versions/0011_profile_deletions.py:29-42`
- 问题：domain.md 把 `retry_count` 列为删除意图的持久化字段，但模型、迁移与生成的 API schema 中均无该字段（全仓仅 domain.md 与前端测试 fake 出现 `retry_count`）。按 blueprint 是长期真相的约定，该字段表述会误导后续 task 以为重试次数已落盘可查。
- 建议：二选一——从 domain.md 删除 `retry_count` 表述，或在模型/迁移/API 中真正落盘重试次数并在 retry 时递增。

### t078_code_f003 - request_deletions 的「查既有意图→新建」非原子，并发重复提交可产生两个未终结意图

- 严重度：minor
- 锚点：AC-004（重复确认、网络重试不会产生重复删除）；domain.md 不变量「同一 Profile 同时至多一个未终结意图」
- 位置：`src/backend/cbrowser/services/profile_service.py:667-676`、`src/backend/cbrowser/adapters/database/models.py` 的 `ProfileDeletionModel.__table_args__`（两个索引均非 unique）
- 问题：`find_open_deletion` 与 `create_deletion` 分属两次独立事务，中间无锁与唯一约束兜底；两个并发 POST（首个请求尚未提交新建行时网络重试到达）在窗口内都查不到既有意图，会为同一 profile 建两行未终结意图并各起一个驱动器。当前危害有限（stopping 幂等、cleaning 在 profile 锁内串行、先行者删完后后行者在 `profile is None` 分支收敛为 done、Artifact `remove_profile` 幂等），但「至多一个未终结意图」的不变量靠时序运气而非机制保证，且会留下一条从未真实执行清理却标 done 的意图行，审计口径含糊。
- 建议：给「未终结意图唯一性」加机制保证（如按 profile 的受理锁、或部分唯一索引/受理时串行化），并补并发双提交只产生一行意图的测试。

## 结论

- 本轮新发现：3 条（important 1、minor 2）
- 未进表的提示：
    - 文件过大（按标准只列结论、不进 finding 表）：`src/backend/cbrowser/services/profile_service.py` 现 1689 行（实现源码 ≥800 阈值，本 task 净增约 390 行，删除生命周期约 380 行全部堆入该文件，建议后续按删除协调拆出独立 service 模块）；`src/backend/cbrowser/adapters/database/repository.py` 现 2736 行（本 task 净增 122 行）；`src/backend/cbrowser/api/v1/router.py` 现 1148 行（本 task 净增约 90 行）；`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx` 现 1198 行（测试 ≥600 提示阈值）。
    - 圈复杂度提示：`src/backend/cbrowser/services/profile_service.py` 的 `_deletion_clean_stage` 手算 CC 约 13（≥10 提示线、未达 15），分支集中在围栏复核与分步失败记录，目前未见分支漏处理，不进 finding 表。
    - 范围外观察：详情页 MaintenanceTab 的删除仍走旧单删端点（端点语义已收敛至同一状态机），其「先停止再删除」禁用口径与列表侧新口径不一致——实施方已在 progress.md 声明不在本 task AC 范围，本轮不作 finding，仅记录。
    - 安全/性能/健壮性视角已扫：新端点沿用既有 profile_router 的鉴权与 ORM 参数化查询，无注入/越权/敏感信息落盘新增面；stopping 轮询为 0.5s 定时查单行，无 N+1；驱动器异常有 guarded 兜底记 failed，未见吞错。
- 总体判断：删除生命周期的后端状态机（持久化意图、停止收敛、实例围栏、分步清理与失败保留、重启恢复）实现真实且经独立复跑验证；但批次受理与批次查询的口径断裂使「失败后重新确认删除」这一正常用户路径静默失效，AC-005 打勾不成立，须修复后重审。
- 系统性 follow-up：无（f001 属本 task 内修复，不另立项）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。表格最后活跃列与页头运行计数已删除（EnvironmentTable/EnvironmentListPage diff 实查），表格与卡片共用 EnvironmentRowActions、删除在所有状态固定最右 danger、停止独立呈现且 stopping/运行删除均有 title 说明；独立复跑 EnvironmentListPage.test.tsx 30 条全过含新 AC-001 用例。
- AC-002：TICK-VALID，re_verified。单项/批量统一 DeleteEnvironmentsDialog（共享 Dialog 承担焦点圈定/Escape/遮罩），确认前零请求与取消不发请求由前端用例断言且复跑通过，目标在打开时冻结为 ID+名称快照。
- AC-003：TICK-VALID，re_verified。后端 stopping 阶段置 desired=stopped 并等写者消失后才清理、停止超时失败且数据零删除，独立复跑 tests/unit/test_t078_deletion_lifecycle.py 与 tests/integration/test_t078_deletion_api.py 共 17 条全过；失败阶段在原始批次弹窗内呈现并可重试（再确认路径的呈现缺陷计入 AC-005 的 f001）。
- AC-004：TICK-VALID，re_verified。重复受理加入同一意图、重启 resume 未终结意图、停止后新实例绑定触发 cleaning 围栏失败均有单测且复跑通过；旧实例迟到事件不复活已删除目标依托 profile 行删除与既有 config_version 围栏（本 diff 未改动该机制）。
- AC-005：TICK-VOID，re_verified。见 f001：目标加入既有意图时，受理返回的新 batch_id 与批次查询口径断裂，该目标不在新批次中呈现——全部加入时批次查询 404、弹窗停留在确认态且 failed 意图不再被驱动，失败项的结果与重试入口在再确认路径下丢失，不满足「严格作用于明确确认的 ID 集合、失败项保留结果和重试入口」。
- AC-006：TICK-VALID，re_verified。cleaning 按 artifacts→目录→preview→DB 行顺序执行、每步结果记入 detail.steps、目录清理改严格版（失败即 failed 于 cleaning 且 DB 行保留）、Artifact 失败记录 error 且可重试恢复，单测复跑通过；生产路径的 artifact cleaner 在 app lifespan 中于 resume 前接线（api/app.py diff 实查）。
- AC-007：TICK-VALID，trust_prior。按 task.md 契约区「[deploy] AC 打勾处置注记」作处置型判定：云端可做部分已完成、真实环境补验已登记 pending p128（文件实查存在、status todo、内容与注记要求一致）；真实隔离环境验证未在云端执行，依赖本地补验闭环。

coverage = 6 / 7

verdict: FAIL

## Round 2 (2026-11-18T09:29:06+08:00)

- task：`t078_environment_deletion_lifecycle_and_actions`
- round：2
- reviewed_at：2026-11-18T09:29:06+08:00

reviewed_scope: 6e3f303e22a58022

### Findings

#### t078_code_f004 - 并发两次确认时，后加入者把意图批次改走，先确认者的批次轮询被留空

- 严重度：minor
- 锚点：AC-004（重复确认不失去已接受的执行结果）/ AC-005 的批次呈现口径
- 位置：`src/backend/cbrowser/services/profile_service.py:709-743`（`_join_deletion` 无条件把既有意图的 `batch_id` 改为最新批次）、`src/frontend/src/features/profiles/EnvironmentListPage.tsx:474-477`（弹窗 operations 只来自批次查询）
- 问题：f001 的修复把「加入既有意图」实现为改归最新批次，顺序再确认（关弹窗后重选）已修复；但两个客户端/标签页对同一未终结意图近同时确认时，后到者把意图改归自己的批次，先到者按其批次号轮询得到空集/404，弹窗回落到确认态。影响有限：删除本身不重复、不丢失（部分唯一索引保证单意图，单项查询与再次确认均可恢复，已独立复跑并发用例确认只产生一行意图且收敛 done），故定 minor 而非沿 f001 的 important。
- 建议：批次成员关系与意图分离（如批次-意图关联表，或批次查询按受理返回的 operation id 集合解析），使任一批次号都能查到其受理过的意图；或前端在批次查询为空时回退到 POST 返回的 operations 逐项轮询。

## 结论

- 前轮 finding 复核：
    - t078_code_f001（important）：已消除。`request_deletions` 经 `_join_deletion`（`src/backend/cbrowser/services/profile_service.py:709-743`）把加入意图归入本次批次，failed 意图再确认时清失败、从 failed_stage 恢复并重新驱动；回归用例 `test_reconfirm_failed_intent_retries_under_new_batch`（unit）与 `test_reconfirm_after_failure_surfaces_in_new_batch`（integration，新批次回查含该意图且收敛 done）由本 reviewer 独立复跑通过（后端 t078 unit+integration 共 23 条全过）。
    - t078_code_f002（minor）：已消除。`docs/blueprint/domain.md` 删除意图字段清单已去掉 `retry_count`，改为与模型/迁移一致的字段集并补记部分唯一索引与再确认即 retry 口径；全仓 grep 确认 domain.md、后端源码与迁移 0011 均无 `retry_count`。前端测试 fake 中仍残留同名字段（`EnvironmentListPage.test.tsx`），属测试层夹具残留，不影响生产契约，留 test 轴处置。
    - t078_code_f003（minor）：已消除。模型与迁移 0011 均新增部分唯一索引 `uq_profile_deletions_open_profile`（stage != 'done'，`src/backend/cbrowser/adapters/database/models.py:486` 及迁移文件同名索引）；`request_deletions` 捕获 IntegrityError 后有界重读并加入胜出意图（`profile_service.py:682-700`）。`test_second_open_intent_violates_unique_index` 与 `test_concurrent_requests_create_single_open_intent` 独立复跑通过。
- 本轮新发现：1 条（minor 1：f004 并发改归批次使先确认者批次轮询留空；无 critical / important）
- 未进表的提示：
    - 文件过大（按标准只列结论）：`src/backend/cbrowser/services/profile_service.py` 现 1746 行、`src/backend/cbrowser/adapters/database/repository.py` 现 2739 行、`src/backend/cbrowser/api/v1/router.py` 现 1148 行（实现源码 ≥800 阈值）；`src/frontend/src/features/profiles/EnvironmentListPage.test.tsx` 现 1277 行（测试 ≥1200 阈值）。本轮修复继续小幅堆入 profile_service.py（\_join_deletion 等），拆分建议维持 Round 1 结论。
    - 圈复杂度提示维持 Round 1：`_deletion_clean_stage` 约 13（≥10 提示线），未见分支漏处理。
    - 范围外观察（Round 1 已记、本轮未变）：同步 `delete_profile`（`profile_service.py:1036` 起）遇到既有 failed 意图时直接驱动 `_drive_deletion`，而该驱动对 stage=failed 无分支、随即以旧失败阶段抛 409——不像批量路径再确认即 retry；失败可见且带 stage、非静默，详情页 MaintenanceTab 口径亦不在本 task AC 范围，仅记录。
    - 安全/性能/健壮性视角已扫本轮修复面：批次改归与唯一索引均走 ORM 参数化更新，无新增注入/越权面；IntegrityError 重读为有界 50 次短轮询，无无限重试。
- 总体判断：Round 1 三条 finding 均以 diff 与独立复跑证实真实消除，AC-005 的再确认路径已收敛；本轮仅 1 条 minor 残余（f004），当前全部打勾成立。
- 系统性 follow-up：无（f004 属本 task 内 minor 处置，不另立项）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。表格/卡片共用操作区、删除固定最右 danger、停止独立呈现与状态说明维持 Round 1 实查结论；独立复跑 EnvironmentListPage.test.tsx 32 条全过（含五种状态行与卡片布局断言）。
- AC-002：TICK-VALID，re_verified。DeleteEnvironmentsDialog 维持确认前零请求/取消不发请求，独立复跑前端 32 条全过（含删除弹窗层 Escape 用例）。
- AC-003：TICK-VALID，re_verified。stopping 阶段语义未被本轮修复改动；独立复跑后端 t078 unit+integration 23 条全过，含停止超时失败保留数据与失败后重试收敛。
- AC-004：TICK-VALID，re_verified。部分唯一索引＋IntegrityError 加入胜出意图使并发双提交只产生一行意图（并发用例复跑通过），resume cleaning 与迟到事件用例复跑通过；f004 的批次可见性边缘问题定 minor，不构成重复删除或结果丢失。
- AC-005：TICK-VALID，re_verified。f001 已消除：失败后关弹窗再确认，意图归入新批次、批次回查含该意图并收敛 done——unit 与 integration 两条 f001 回归用例独立复跑通过；成功项退出选择、失败项保留结果与重试入口维持。
- AC-006：TICK-VALID，re_verified。cleaning 分步清理与失败保留语义未被本轮修复改动，后端 23 条复跑全过含 Artifact 失败记录与可重试恢复。
- AC-007：TICK-VALID，trust_prior。按 task.md 契约区「[deploy] AC 打勾处置注记」作处置型判定：云端可做部分已完成、补验 pending p128 文件实查存在且 status 为 todo、内容与注记要求一致；真实隔离环境验证未在云端执行，依赖本地补验闭环。

coverage = 6 / 7

verdict: PASS
