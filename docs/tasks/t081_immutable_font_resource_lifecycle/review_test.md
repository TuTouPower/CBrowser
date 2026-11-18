# Task review t081（reviewer_focus: 测试）

- task：`t081_immutable_font_resource_lifecycle`
- spec：`docs/tasks/t081_immutable_font_resource_lifecycle/task.md`
- diff_anchor：`c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- target：`git diff c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- round：1
- reviewed_at：2026-11-18T12:13:49+08:00

reviewed_scope: 24f07c7638df453f

## Findings

### t081_test_f001 - AC-003 的 SSE 状态组装三分之一无任何测试，零读取测试 docstring 虚报覆盖

- 严重度：important
- 锚点：AC-003（连续 100 次 runtime REST 查询、100 次 SSE 状态组装与 100 次字体列表查询，字体正文打开/读取与完整性哈希均为零）
- 位置：`tests/unit/test_t081_font_catalog.py:144`（docstring）与 `tests/unit/test_t081_font_catalog.py:190`（循环体）
- 问题：`test_reads_never_touch_font_bytes` 的 docstring 声称覆盖「100 runtime REST resolutions + 100 list calls + 100 runtime-view assemblies」，但循环体只调用 `coordinator.get_font_runtime(profile.id)`（无 runtime 参数）与 `font_sets_router.list_font_sets` 各 100 次；全文件无 SSE 事件组装（coordinator 的 runtime 事件构建路径）、无 `runtime_views.make_runtime_response` 调用（grep 全文仅 docstring 出现 "runtime-view" 一词）。SSE 路径实际传 `runtime=rt` 走 `get_font_runtime` 的 config_version 快照分支，该分支从未在计数器下执行——若该分支或 SSE 组装层重新引入字体正文读取，现有计数门禁不会变红。REST 与列表两路本身可信：计数器包装生产 helper（`font_sets.check_font_set` 与 `font_sets.manifest._sha256_file` 均透传原实现计数，非 stub 假绿），断言 `counters == {"check": 0, "sha": 0}` 为精确等值；reviewer 变异验证：在 `runtime_coordinator._font_runtime_from` 恢复一次 live `check_font_set` 调用后本测试立即变红（已从字节副本恢复，sha256 复核一致）。
- 建议：在同一计数器下补 100 次 SSE 组装（经 coordinator 事件构建或 `make_runtime_response`，带 runtime 记录走快照分支）并断言计数仍为零；或修正 docstring 与 AC 证据口径，不得以未执行的组装路径充当已覆盖。

### t081_test_f002 - AC-007 的失败/取消不占用执行槽无任何测试，docstring 虚报「completion/failure」

- 严重度：important
- 锚点：AC-007（失败/取消不永久占用执行槽）
- 位置：`tests/unit/test_t081_font_catalog.py:334`（docstring）与 `tests/unit/test_t081_font_catalog.py:382`（唯一的槽位释放断言）
- 问题：`test_audit_concurrency_bounded_deduped_and_reads_progress` 的 docstring 声称证明「slots free up after completion/failure」，但正文只在三条审计全部成功后断言可再次 `scheduled`；全仓测试无一处让审计验证抛错（如令 `check_font_set` 抛异常）或取消在途审计后再断言同集可重新调度。该路径恰是实施笔记自述曾出真实缺陷的区域（并发写目录丢记录、wait_idle 吞异常），且生产实现 `_run_audit` 以宽泛 `except Exception` 吞审计异常——失败后 `_inflight` 清理与信号量释放若回归（例如异常发生在 done-callback 注册前、或取消被吞），现有测试全绿也发现不了。并发上限（peak ≤ `AUDIT_CONCURRENCY`，精确断言且常量取自生产声明）、同集去重返回 `in_flight`、阻塞期间 `list_assets` 以 `wait_for(timeout=5)` 推进三项本身可信。
- 建议：补一条失败路径用例：注入抛错的验证函数，审计结束后断言目录状态不变、同集再次 `request_audit` 返回 `scheduled` 且能完成；取消路径同理或在 docstring/AC 证据中明确不覆盖取消。

### t081_test_f003 - AC-005 审计级损伤类型只测了内容破坏，删除/额外文件/manifest 异常仅有 helper 级旧覆盖

- 严重度：minor
- 锚点：AC-005（显式审计能发现删除、额外文件、内容破坏和 manifest 异常）
- 位置：`tests/unit/test_t081_font_catalog.py:258`（审计测试唯一的损伤注入）
- 问题：审计级测试只注入 `write_bytes(b"TAMPERED")` 一种损伤；删除文件、额外文件、manifest 异常三类只在未改动的 `tests/unit/test_font_sets.py::test_check_font_set_problem_fields` 里以 helper 级覆盖（四类损伤均断言 `ok is False` 与对应问题字段）。审计层与 helper 共用同一 `check_font_set` 且 tamper 一类已证明「审计→撤销→拒绑→修复→新 revision」全链，故其余三类大概率同路，但审计层无直接证据。
- 建议：把审计损伤参数化为删除/额外文件/manifest 篡改各一条，断言审计后 `verified is False` 即可，不必重复修复链。

### t081_test_f004 - AC-004 多 Profile 共用与资源修订变更围栏未直接测

- 严重度：minor
- 锚点：AC-004（多个 Profile 共用同一已发布集合时普通读取不重复校验；资源修订改变后不会复用错误实例结果）
- 位置：`tests/unit/test_t081_font_catalog.py:205`（`test_supervisor_verifies_once_per_instance` 全文）
- 问题：Supervisor 测试只证明同实例重复调用验一次、新实例再验（reviewer 变异去掉围栏缓存后该测试变红，已恢复并复核 sha256）；但「多 Profile 共用同一集」无用例（零读取测试只有一个 Profile），且 Supervisor 围栏键 `(runtime_instance_id, platform, set_id)` 不含目录 revision，同集被受控修复（revision 递增）后同实例复用旧结论的场景无测试锁定其预期语义（按 ADR 030 该围栏即设计口径，但 AC 文字含「资源修订改变后不会复用错误实例结果」，测试层未留任何对应断言）。
- 建议：补一条双 Profile 共用同集的零重复校验断言；revision 变更场景或补测试、或在 ADR/测试 docstring 中明确该围栏不含 revision 的理由与 AC 对应关系。

### t081_test_f005 - AC-002 中断点只覆盖一种：已发布未接管 + staging 残留

- 严重度：minor
- 锚点：AC-002（在 staging 写入、校验、发布切换和目录提交之间任意中断）
- 位置：`tests/unit/test_t081_font_catalog.py:108`（`test_adoption_recovers_interrupted_publish_and_is_idempotent` 全文）
- 问题：测试构造的中断形态只有「发布完成但目录未提交（API 宕机期间发布）+ 一个 staging 残留目录」，并断言 staging 永不接管、二次接管零重验且 revision 不变（断言精确、可信）；但测试策略列明的 fsync/rename/DB 提交失败注入无一落地，例如 `apply_audit_verdict` 提交失败后不得留下半条目录记录、无 ready 指向半成品的故障注入证据缺失。
- 建议：补一条目录提交失败注入（如令 repository commit 抛错后重跑接管，断言最终恰一条 verified 记录且期间从未 bindable），或收窄 AC-002 的证据口径说明。

### t081_test_f006 - AC-001 无效子情形合并为一个样本，重复名/集合身份不符/manifest 缺失未逐项过接管

- 严重度：minor
- 锚点：AC-001（错误平台、摘要、manifest、集合身份、重复或逃逸文件名均不能被发布为可用）
- 位置：`tests/unit/test_t081_font_catalog.py:76`（`test_invalid_sets_are_never_recorded_verified` 全文）
- 问题：该测试把摘要错误与逃逸文件名合并进同一个坏集样本（任一问题都会使 `ok=False`，无法区分哪条校验在起作用），错误平台只测了导入口抛 `ValueError`；重复文件名、manifest 缺失/不可解析、目录名与内容身份不符三类无接管级样本（导入级校验有未改动的旧测试覆盖，接管级只有合并样本）。
- 建议：把合并样本拆为每类问题一条接管断言（均断言记录为 failed 且不可绑定、无默认集），成本低且能定位回归。

### t081_test_f007 - AC-006 测试丢弃绑定快照的 missing_fonts 结论，只断言 set_id

- 严重度：minor
- 锚点：AC-006（运行状态报告实际实例绑定的字体与验证结论）
- 位置：`tests/unit/test_t081_font_catalog.py:323`（`bound_id, _ = await coordinator.get_font_runtime(...)`）
- 问题：实例绑定测试用 `bound_id, _` 与 `current_id, _` 丢弃了 missing_fonts 返回值，只证明报告的 set_id 来自实例绑定版本（该断言本身精确：v1 绑定 A、当前配置 B 分别命中）；但「验证结论随绑定快照走」——旧集与新集 detection 覆盖不同时，运行状态应报告旧集的覆盖结论——无断言。两源集分别只有 arial.ttf / cour.ttf，覆盖差异现成可用却未断言。
- 建议：对两路返回值补 missing_fonts 断言（如绑定路含 cour.ttf 缺失、当前路含 arial.ttf 缺失），锁定结论随快照走。

## 结论

- 改测方向复核：无「迁就实现」的改测。逐项核对如下——(1) 删除 `tests/unit/test_a5_font_scan_offload.py` 与 `tests/unit/test_t053_coordinator_font_runtime.py`：系 task 测试策略明示 + ADR 030 记录的整体删除（废止每请求审计/实时读取/禁止缓存语义），非就地改预期；其存续属性（审计离线执行、并发有界）在新审计引擎上由 AC-007 测试重新证明，未发现仍被 AC 要求却无替代的覆盖（删除集经审计发现一项的审计级缺口见 f003）。(2) `tests/unit/test_font_sets_api.py` 与 `tests/unit/test_t053_font_sets_chain.py`：经 diff 逐行核对，仅新增 adoption setup helper 并替换调用点，全部断言逐字未动，属合法 setup-only 变更（adoption 即生产启动路径，非 mock 被测逻辑）。(3) `tests/integration/test_font_sets_api.py` 两条 tamper 测试改写为生命周期语义：先断言篡改在显式审计前不可见（integrity 仍 ok、默认集仍在），再经 `_audit_until_failed`（POST audit 202 + 轮询至 state==failed，30 秒硬超时失败而非放行）断言 integrity 不 ok、默认集撤销，且保留并新增 `hash_mismatches` 与 "sha256 mismatch" 问题断言——是断言新契约且局部加强，不是弱化。(4) `tests/unit/test_t054_migration.py` head 测试 0010→0011 改名沿用文件内既有 "Replaces" 先例，断言仍为精确等值。(5) `tests/unit/test_t056_migrations.py` golden 测试把允许差异精确扩展为恰 `font_set_assets` 表 + 其 autoindex，并新增 8 个列定义断言与「旧对象零丢失」断言，非弱化。(6) 前端 3 个测试文件仅在 FontSetInfo fixture 工厂新增 state/revision/verified_at/audited_at 四字段（类型级），无断言变更；第 4 处为生成类型文件，非测试断言。
- 危险模式扫描：改动测试文件全量扫描，无恒真断言、无删/反转/注释断言、无 `.skip`/`.only`/`xfail`、无 `type: ignore`/`eslint-disable`、无阈值放宽掩盖；新测试中的计数器均透传生产原实现（包装计数而非 stub 结果），mock 只出现在 Supervisor 构造的 API client 等系统边界。`test_t081_font_catalog.py:69` 的 `matched >= 3` 与 `:198` 的 truthiness 断言均为旁证，同测试内有精确等值断言锁定核心行为，不构成弱化证据。
- 本轮新发现：7 条（important 2、minor 5）
- 独立复跑证据：reviewer 以门禁 venv 实跑 `tests/unit/test_t081_font_catalog.py` 等 6 个文件共 54 条全过（t081 新测试 9/9），`tests/integration/test_font_sets_api.py` 7/7 全过；门禁证据 junit 直接核对：contract 389 条 0 失败、integration 215 条 0 失败、unit 2308 条 15 条 bad 与自述一致（t063 ×12、t068 ×2、a16 ×1，均为字体无关的老基线文件）。变异抽查 3 处均变红且已从字节副本恢复并复核 sha256：读路径恢复 live `check_font_set` → 零读取测试红；禁用 `state_seq` 围栏条件 → 迟到回执测试红；禁用 Supervisor 实例围栏缓存 → 一次性验证测试红。
- 未进表的提示：AC-008 的卷只读/Browser 只挂绑定集/Stream 无字体挂载由未改动的 t080 挂载测试覆盖（Browser 挂载 `ReadOnly is True`、Stream 无字体挂载断言在册，门禁 unit junit 无 t080 失败），本轮未重复计 finding；`_audit_until_failed` 的轮询等待属异步回执的确定性等待，未见掩盖失败。
- 总体判断：新测试主体可信且经变异验证能抓回归，但 AC-003 的 SSE 三分之一与 AC-007 的失败/取消子项在 docstring 声称覆盖而实际无测试，两条 AC 打勾证据不足，FAIL。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。实跑 adoption/无效集两测试全过：未接管不可绑定、接管后 verified 且 revision==1、坏集记录 failed 且无默认集。
- AC-002：TICK-VALID，re_verified。实跑恢复/幂等测试全过：staging 残留不接管、二次接管零 check 调用且 revision 不变（缺口深度见 f005，minor）。
- AC-003：TICK-VOID，re_verified。REST 与列表各 100 次计数为零经实跑与变异验证属实，但 AC 明列的 100 次 SSE 状态组装从未在计数器下执行，测试 docstring 却声称已覆盖（f001）。
- AC-004：TICK-VALID，re_verified。实跑 Supervisor 一次/实例测试全过且变异去围栏变红；共用与 revision 围栏深度缺口见 f004（minor）。
- AC-005：TICK-VALID，re_verified。实跑审计损伤→撤销→拒绑→修复→新 revision→迟到回执被 fence 丢弃全链全过，fence 变异变红；integration 侧审计后 hash_mismatches 断言在册且实跑 7/7。
- AC-006：TICK-VALID，re_verified。实跑实例绑定测试全过：runtime=config_version 1 报告绑定集 A、无 runtime 报告当前配置集 B（missing 结论断言缺口见 f007，minor）。
- AC-007：TICK-VOID，re_verified。并发上限/去重/读取推进经实跑属实，但 AC 明列的失败/取消不占用执行槽无任何用例，docstring 却声称已覆盖 completion/failure（f002）。
- AC-008：TICK-VALID，re_verified。实跑宿主源变更不泄漏 + 再导入新集全过；卷只读与 Stream 无挂载由未改动的 t080 挂载测试断言覆盖且门禁 unit 无 t080 失败。
- AC-009：TICK-VALID，trust_prior。按用户 2026-11-18 裁定，[deploy] 打勾表示云端可做部分完成、真实验证延期至 pending p131（文件在册且三项补验内容与 AC 对应），不表示已实测通过。

coverage = 8 / 9

verdict: FAIL

## Round 2 (2026-11-18T12:24:44+08:00)

- round：2
- reviewed_at：2026-11-18T12:24:44+08:00

reviewed_scope: ee44960870ed1ed0

## Findings

### t081_test_f008 - AC-003/AC-006：get_font_runtime 的快照分支从未在零读取计数器下执行，快照缺失分支无任何测试

- 严重度：minor
- 锚点：AC-003（100 次 SSE 状态组装零字体正文读取）/ AC-006（运行状态报告实际实例绑定的字体与验证结论）
- 位置：`tests/unit/test_t081_font_catalog.py:204`（零读取循环）与 `src/backend/cbrowser/api/runtime_coordinator.py` 的 `get_font_runtime` 快照分支（`snapshot is None` 时返回 `(None, [])`）
- 问题：零读取循环新增的 `publish_profile_change` 与 `make_runtime_response` 传入的 runtime 其 config_version 与 profile 当前版本相等（测试中从未更新配置），`get_font_runtime` 的快照分支（runtime 版本 ≠ 当前版本时查 `get_config_version`）在计数器下仍不执行；该分支只由 AC-006 测试在无计数器时经过。reviewer 变异验证：在快照分支插入一次 `font_sets.check_font_set(".")` 调用后，t081 全部 14 条测试仍全绿（已从字节副本恢复，sha256 复核一致：runtime_coordinator.py `42250069…`）——该分支若重新引入字体正文读取，计数门禁不会变红。同一函数的快照缺失子分支（本轮代码变更新增的 `(None, [])` 诚实未知语义）全仓无测试：`get_font_runtime` 在测试中仅 4 个调用点，无一传入不存在快照的 config_version，若该分支回归为「返回当前待应用配置」，AC-006 的防误报语义无测试变红。两分支最终都汇入已被计数门禁守住的 `_font_runtime_from`，且快照缺失分支按构造不读文件，故定 minor 不阻断。
- 建议：在零读取循环里给 profile 先做一次配置更新、再以旧版本 runtime 跑 SSE/view 组装，使快照分支进入计数范围；另补一条快照缺失用例断言返回 `(None, [])`。

### t081_test_f009 - AC-004：Supervisor 围栏本轮扩宽到 profile_id/config_version，但测试仍以 None/None 调用，新维度无断言

- 严重度：minor
- 锚点：AC-004（同实例/资源修订完成启动验证后重复健康读取不再次哈希）
- 位置：`tests/unit/test_t081_font_catalog.py:211`（`test_supervisor_verifies_once_per_instance`）与 `src/backend/cbrowser/supervisor/core.py` 的 `_validate_font_set` 围栏键 `(profile_id, runtime_instance_id, config_version, platform, set_id)`
- 问题：本轮生产调用点已传真实 `profile_id`/`config_version`（`start_profile` 内调用），围栏也已扩宽到这两个维度；但测试仍以旧签名位置调用 `_validate_font_set(config, "inst_1")`，两个新维度恒为 None——把围栏改回仅 `(runtime_instance_id, platform, set_id)` 该测试照样全绿，即「同实例换 config_version 必须重验」这一新行为无任何测试锁定。实例维度本身的断言仍可信（同实例 1 次、新实例 2 次，精确计数）。
- 建议：补一条同实例同集、仅 config_version 不同（及仅 profile_id 不同）的调用，断言各重验一次。

## 结论

- 前轮 finding 复核：
    - f001（important，AC-003）：已消除（主体）。零读取循环现于同一计数器下真实执行 `publish_profile_change`（SSE 组装，`tests/unit/test_t081_font_catalog.py:204`）与 `make_runtime_response`（runtime view 组装，`:205`）各 100 次，docstring 与正文一致；reviewer 变异：在共享读路径 `_font_runtime_from` 插入 `check_font_set` 调用后本测试立即变红（已恢复，sha256 一致），证明新增组装路径受计数门禁守卫。残余：快照子分支仍不在计数范围内，转新 minor f008，不再构成 AC-003 打勾作废理由——AC 明列的三类组装现均已真实执行。
    - f002（important，AC-007）：已消除。新增 `test_audit_failure_and_cancellation_free_the_slot`（`:431`）：验证抛 RuntimeError 后断言目录无记录、`audit_in_flight` 为假；取消后断言无记录；随后健康审计 `scheduled` 且落 verified 记录，全过。一处口径提示：该测试在 `request_audit` 返回后立即 `task.cancel()`，其间无 await 让步，任务实际在首步前被取消而非「运行中」取消；reviewer 另以临时探针（已删除）实测生产中途取消（阻塞于 `check_font_set` 内部时取消）同样释放槽位且后续审计落账，探针 1/1 通过，故生产行为成立，仅测试 docstring 的 mid-flight 措辞略强于其力学，不另列 finding。
    - f003（minor，AC-005）：已消除。新增 `test_audit_detects_deletion_extra_file_and_manifest_damage`（`:474`）在审计级分别注入删除/额外文件/manifest 损坏，三例均断言审计后 `verified is False` 且 `problems` 非空，全过。
    - f004（minor，AC-004）：已消除（共用部分）。新增 `test_two_profiles_share_one_set_without_reverification`（`:584`）：双 Profile 同集读取断言 `check_font_set` 调用为零，全过。revision 维度并入新 minor f009（围栏新维度未测），原 finding 的「多 Profile 共用无用例」已补齐。
    - f005（minor，AC-002）：已消除。新增 `test_adoption_db_commit_failure_leaves_no_ready_record`（`:502`）：`apply_audit_verdict` 首次抛错后接管不留任何记录，第二次接管完成 verified 记录，全过；故障经生产 `_run_audit` 的异常记录路径消化，与本轮「接管异常日志」代码变更同路。
    - f006（minor，AC-001）：已消除。新增 `test_adoption_rejects_platform_and_manifest_defects`（`:532`）将外平台 manifest、无 manifest、冲突重复条目拆为三个独立集逐一断言 recorded failed，且同批合法集仍 verified。reviewer 变异：移除 `_verify_directory` 的平台门（`found is None` 强制失败）后该测试立即变红（已从字节副本恢复，sha256 `7c184e87…` 一致），证明平台门被该测试真实隔离覆盖。
    - f007（minor，AC-006）：已消除。实例绑定测试现断言 `bound_missing` 随集 A（arial 不缺、cour 缺，`:336`–`:337`）与 `current_missing` 随集 B（恰相反，`:340`–`:341`），全过。
- 改测方向复核：无。本轮新增 5 条测试均为新增覆盖，未改动既有断言；生产代码变更（平台门、快照缺失返回、default 按 verified_at、删除 record_verified、Supervisor 围栏扩宽、接管异常日志）中，平台门由 f006 测试隔离覆盖（变异实证），快照缺失与围栏新维度的测试缺口见 f008/f009（minor）。
- 本轮新发现：2 条（minor 2）
- 独立复跑证据：reviewer 以门禁 venv（TMPDIR 指向 cloud-task-logs/tmp-t081）实跑 `tests/unit/test_t081_font_catalog.py` 14/14 全过；font/coordinator/migration 回归批次（test_font_sets、test_font_sets_api、test_t053_font_sets_chain、test_t054_migration、test_t056_migrations、test_t041_font_runtime、integration test_font_sets_api）61/61 全过；supervisor 子集（test_supervisor_core、test_supervisor_reconcile_fences、test_supervisor_stop_fence）7/7 全过。变异抽查 3 处：共享读路径加字体读取→零读取测试红；快照分支加字体读取→全绿（f008 证据）；去平台门→f006 测试红。全部变异均已从字节副本恢复并复核 sha256。
- 危险模式扫描：新增/更新测试全量扫描，无恒真断言、无删/反转/注释断言、无 skip/only/xfail、无 type: ignore；f002 测试直接访问 `catalog._inflight` 取任务句柄属测试力学（断言仍落在目录记录与槽位状态等可观察结果上），不构成 mock 被测逻辑。
- 未进表的提示：实施自述的 supervisor 子集 85/85 与回归 71/71 分组口径与 reviewer 本轮所跑批次不同，未逐字复现该分组，但所跑全部批次均全过，无失败被掩盖迹象。
- 总体判断：Round 1 两条 important 均已真修并经变异/探针实证，本轮仅余 2 条 minor 覆盖深度缺口，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。实跑 14/14 中 adoption/无效集/平台与 manifest 缺陷三测试全过；去平台门变异使缺陷测试变红，平台、摘要、manifest、重复、逃逸各子情形均有接管级断言。
- AC-002：TICK-VALID，re_verified。实跑恢复/幂等测试与新增 DB 提交失败测试全过：提交失败不留 ready 记录、二次接管完成且 revision 不变。
- AC-003：TICK-VALID，re_verified。零读取测试现含 100 次 SSE 组装（publish_profile_change）与 100 次 view 组装（make_runtime_response），计数精确为零且共享读路径变异变红；快照子分支计数缺口见 f008（minor）。
- AC-004：TICK-VALID，re_verified。实跑双 Profile 共用零重验测试与 Supervisor 同实例验一次/新实例重验测试全过；围栏新维度断言缺口见 f009（minor）。
- AC-005：TICK-VALID，re_verified。实跑审计损伤矩阵（删除/额外/manifest/内容破坏）→撤销→拒绑→修复→新 revision→迟到回执被 fence 丢弃全链全过。
- AC-006：TICK-VALID，re_verified。实跑实例绑定测试全过且 missing 结论随绑定集断言（f007 已修）；快照缺失分支无测试见 f008（minor）。
- AC-007：TICK-VALID，re_verified。实跑并发上限/去重/读取推进与新增失败/取消释放槽位测试全过；reviewer 探针另实证生产中途取消同样释放槽位。
- AC-008：TICK-VALID，re_verified。实跑宿主源变更不泄漏 + 再导入新集测试全过（在 14/14 内）；卷只读与 Stream 无挂载由未改动的 t080 挂载测试覆盖且本轮回归批次无失败。
- AC-009：TICK-VALID，trust_prior。按用户 2026-11-18 裁定，[deploy] 打勾表示云端可做部分完成、真实验证延期至 pending p131，不表示已实测通过。

coverage = 8 / 9

verdict: PASS

## Round 3 (2026-11-18T12:30:47+08:00)

- round：3
- reviewed_at：2026-11-18T12:30:47+08:00

reviewed_scope: 1f25991583e7e71c

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核：
    - f008（minor，AC-003/AC-006）：已消除。(a) 快照分支零哈希：`tests/unit/test_t081_font_catalog.py:310` 的 `test_runtime_reports_instance_bound_set_not_pending_config` 先更新配置至 version 2，再以 `runtime_v1 = SimpleNamespace(config_version=1)`（stale 版本）调用 `coordinator.get_font_runtime(profile.id, runtime=runtime_v1)`，该调用置于透传原实现的 `_sha256_file` 计数包装内（`counting_sha`），并断言 `sha_calls == []`，同时断言 bound_id 为集 A 且 missing 结论随集 A。reviewer 变异验证：在快照分支插入一次经 `font_sets.manifest._sha256_file` 的直接哈希调用后该测试立即变红（失败于 `sha_calls == []` 断言）；已从字节副本恢复，`runtime_coordinator.py` sha256 复核为 `42250069…` 与变异前一致。真实的 `check_font_set` 复验路径内部亦经同一 `_sha256_file` 哈希，故该计数能守住快照分支重新引入字体正文哈希的回归。(b) 快照缺失分支：同测试后段以 `_no_snapshot` 令 `service.get_config_version` 返回 None，直接调用 `get_font_runtime(profile.id, runtime=runtime_v1)` 并断言 `unknown_id is None` 且 `unknown_missing == []`，即返回 `(None, [])` 而非待应用配置。reviewer 变异验证：将生产快照缺失分支改为回退当前配置后该测试立即变红；已恢复并复核 sha256 一致。
    - f009（minor，AC-004）：已消除。`tests/unit/test_t081_font_catalog.py:211` 的 `test_supervisor_verifies_once_per_instance` 现以真实维度调用：同实例同版本同 profile 两次断言 `len(calls) == 1`，新实例断言 `== 2`，同实例 `inst_1` + 新 `config_version=2`（profile 不变）断言 `== 3`（重新验证），同实例同版本 + 不同 `profile_id="p2"` 断言 `== 4`（重新验证）；生产围栏键为 `(profile_id, runtime_instance_id, config_version, platform, set_id)`（`src/backend/cbrowser/supervisor/core.py` 的 `_validate_font_set`）。reviewer 变异验证：将围栏收窄回 `(runtime_instance_id, platform, set_id)` 后该测试立即变红；已从字节副本恢复，`supervisor/core.py` sha256 复核为 `15d5d269…` 与变异前一致。
    - f001–f007：Round 2 已逐条复核消除，本轮 diff 未见其测试被删改或弱化，14/14 实跑仍全过，不重复展开。
- 改测方向复核：无。本轮对 f008/f009 的修复均为在既有测试内新增断言与调用维度（快照计数、快照缺失用例、围栏新维度调用），未就地把旧预期改成新实现输出，未删/反转既有断言。
- 本轮新发现：0 条
- 独立复跑证据：reviewer 以门禁 venv（`~/workspace/CBrowser/.scratch/gate_venv/bin/python -m pytest tests/unit/test_t081_font_catalog.py -q`，TMPDIR 指向 cloud-task-logs/tmp-t081）实跑 14/14 全过（恢复变异后再次实跑仍 14/14）。变异抽查 3 处均变红且全部从字节副本恢复并复核 sha256：快照分支直接哈希→AC-006 测试红；快照缺失回退当前配置→AC-006 测试红；Supervisor 围栏收窄去 profile_id/config_version→AC-004 测试红。
- 危险模式扫描：本轮新增/修改测试全量扫描，无恒真断言、无删/反转/注释断言、无 skip/only/xfail、无 type: ignore；快照缺失用例替换的是 `profile_service.get_config_version` 这一系统边界的返回值以构造缺失状态，断言落在 coordinator 的可观察返回值 `(None, [])` 上，不构成 mock 被测逻辑本身。
- 未进表的提示：无
- 总体判断：Round 2 仅余的 2 条 minor（f008/f009）均已真修并经变异实证，本轮无新 critical/important/minor，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。实跑 14/14 中 adoption/无效集/平台与 manifest 缺陷测试全过，各无效子情形均有接管级 failed 断言（Round 2 去平台门变异实证沿用，本轮测试未改动该部分）。
- AC-002：TICK-VALID，re_verified。实跑恢复/幂等与 DB 提交失败测试全过：staging 不接管、提交失败不留 ready 记录、二次接管完成且 revision 不变。
- AC-003：TICK-VALID，re_verified。零读取测试含 100 次 REST + 100 次列表 + 100 次 SSE 组装 + 100 次 view 组装计数精确为零；f008 修复后快照分支亦在零哈希计数下执行（见 f008 复核），本轮变异实证其哈希回归可被抓。
- AC-004：TICK-VALID，re_verified。实跑双 Profile 共用零重验与 Supervisor 围栏测试全过；f009 修复后同实例新 config_version 与换 profile_id 均断言重新验证，本轮围栏收窄变异变红实证。
- AC-005：TICK-VALID，re_verified。实跑审计损伤矩阵（删除/额外/manifest/内容破坏）→撤销→拒绑→修复→新 revision→迟到回执被 fence 丢弃全链全过（14/14 内）。
- AC-006：TICK-VALID，re_verified。实跑实例绑定测试全过：stale runtime 报告绑定集 A 及其 missing 结论且零哈希，当前配置报告集 B，快照缺失直接断言返回 (None, [])；两处变异均变红实证。
- AC-007：TICK-VALID，re_verified。实跑并发上限/去重/读取推进与失败/取消释放槽位测试全过（14/14 内）。
- AC-008：TICK-VALID，re_verified。实跑宿主源变更不泄漏 + 再导入新集测试全过（14/14 内）；卷只读与 Stream 无挂载由未改动的 t080 挂载测试覆盖（Round 2 已核）。
- AC-009：TICK-VALID，trust_prior。按用户 2026-11-18 裁定，[deploy] 打勾表示云端可做部分完成、真实验证延期至 pending p131（文件在册，三项补验内容与 AC 对应：现场规模导入、共用绑定 10 分钟零正文读取、审计负例/修复正例留证），task.md 处置注记在册且准确，不表示已实测通过；本轮不要求云端 Docker 证据。

coverage = 8 / 9

verdict: PASS

## Round 4 (2026-11-18T12:32:28+08:00)

- round：4
- reviewed_at：2026-11-18T12:32:28+08:00

reviewed_scope: 69f046775b93e50b

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核：Round 3 已确认 f001–f009 全部消除且无新发现；本轮为最终微确认，复核范围仅为 Round 3 指纹（1f25991583e7e71c）之后的增量是否纯文档，结论见下条。
- reviewed scope 增量核对（doc-only 确认）：相对 diff anchor 的完整变更集逐文件核对修改时间与内容——全部 `src/` 与 `tests/` 文件的修改时间均不晚于 Round 3 评审时刻（生产文件最晚为 `runtime_coordinator.py` 与 `supervisor/core.py`，即 Round 3 变异恢复并经 sha256 复核一致的字节副本）；Round 3 之后仅三份文件被改动且时间同为一批：`docs/blueprint/architecture.md`（§3.5 围栏措辞改实为「迟到回执不覆盖已应用的新回执/接管（发布/修复只写文件、经后续审计生效）」，与 ADR 030 及代码口径一致）、`docs/blueprint/browser_runtime.md`（A16 默认集口径改实为「只取验证通过（verified）的集，`verified_at` 最大者胜出」，与 Round 2 已复核的生产实现一致）、`docs/tasks/t081_immutable_font_resource_lifecycle/progress.md`（处置行 t081_code_f009/f010 记录的正是上述两处文档修复）。无任何测试或生产代码变更，两处文档改动均为措辞与已实现行为对齐，不引入新的可测行为、不改变任何 AC 证据口径。
- 改测方向复核：无。本轮无测试文件改动。
- 本轮新发现：0 条
- 独立复跑证据：reviewer 以门禁 venv（`~/workspace/CBrowser/.scratch/gate_venv/bin/python -m pytest tests/unit/test_t081_font_catalog.py -q`，TMPDIR=~/workspace/cloud-task-logs/tmp-t081）实跑 14/14 全过（25.61s）。
- 危险模式扫描：本轮增量无测试改动，无从命中；全量变更集的危险模式结论沿用 Round 3（无恒真断言、无删/反转/注释断言、无 skip/only/xfail、无 type: ignore）。
- 未进表的提示：无
- 总体判断：Round 3 PASS 的测试证据基础未被本轮增量触动，增量确认为纯文档措辞对齐，维持 PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。实跑 14/14 中 adoption/无效集/平台与 manifest 缺陷测试全过；本轮增量未触动测试与生产代码（修改时间与 diff 逐项核对）。
- AC-002：TICK-VALID，re_verified。实跑恢复/幂等与 DB 提交失败测试全过（14/14 内），增量 doc-only 不影响该证据。
- AC-003：TICK-VALID，re_verified。实跑零读取测试全过：100 次 REST + 100 次列表 + 100 次 SSE 组装 + 100 次 view 组装计数精确为零，快照分支亦在零哈希计数下执行（Round 3 变异实证沿用）。
- AC-004：TICK-VALID，re_verified。实跑双 Profile 共用零重验与 Supervisor 五元组围栏测试全过（14/14 内，Round 3 围栏收窄变异变红实证沿用）。
- AC-005：TICK-VALID，re_verified。实跑审计损伤矩阵→撤销→拒绑→修复→新 revision→迟到回执被 fence 丢弃全链全过（14/14 内）。
- AC-006：TICK-VALID，re_verified。实跑实例绑定测试全过：stale runtime 报告绑定集 A 及 missing 结论且零哈希，快照缺失返回 (None, [])（Round 3 两处变异实证沿用）。
- AC-007：TICK-VALID，re_verified。实跑并发上限/去重/读取推进与失败/取消释放槽位测试全过（14/14 内）。
- AC-008：TICK-VALID，re_verified。实跑宿主源变更不泄漏 + 再导入新集测试全过（14/14 内）；卷只读与 Stream 无挂载由未改动的 t080 挂载测试覆盖（Round 2 已核，本轮增量未触动）。
- AC-009：TICK-VALID，trust_prior。按用户 2026-11-18 裁定，[deploy] 打勾表示云端可做部分完成、真实验证延期至 pending p131（文件在册，三项补验内容与 AC 对应），task.md 处置注记在册且准确，不表示已实测通过；本轮不要求云端 Docker 证据。

coverage = 8 / 9

verdict: PASS
