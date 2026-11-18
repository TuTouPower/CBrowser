# Task review t082（reviewer_focus: 测试）

- task：`t082_persistent_namespace_policy_agents`
- spec：`docs/tasks/t082_persistent_namespace_policy_agents/task.md`
- diff_anchor：`c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- target：`git diff c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- round：1
- reviewed_at：2026-11-18T13:39:34+08:00

reviewed_scope: 42050fd46c1a37fa

## Findings

### t082_test_f001 - AC-001 的 ready 标记门控断言随 a11 整体删除后无单元层替代

- 严重度：important
- 锚点：AC-001「失败、超时、畸形回执不生成有效 ready 标记」
- 位置：`tests/unit/test_a11_policy_timeout.py`（整文件删除，原 `test_failed_policy_exit_never_writes_ready` / `test_successful_install_writes_ready_and_reclaims_helper` 等）；新路径 `src/backend/cbrowser/supervisor/docker_adapter.py:921-978` 的 `_install_network_policy` 在 Agent install+inspect 成功后才写 `gate / "ready.json"`
- 问题：a11 的超时/脱敏语义确随临时 helper 退役而失效，整体删除本身有 progress.md 理由；但其中「失败不写 ready.json、成功才写 ready.json」两条断言测的是 gated entrypoint 的通用门控语义，在新机制下依然成立且是 AC-001 的核心子句。复核全量 unit 测试：没有任何测试经进程内 rig 真实调用 `_install_network_policy` 并断言 ready.json 的存在/不存在——`tests/unit/test_t051_docker_error_detail.py:277` 的 install 失败测试只断言错误文案脱敏，不断言 gate 保持关闭；其余引用 `_install_network_policy` 的文件均为 `MagicMock()` 替换。唯一仍断言 ready 标记不生成的证据是 e2e `test_supervisor_policy_failure_e2e.py`，云端未实跑、已延期 p133，而 AC-001 不是 [deploy] AC，不能以延期 e2e 支撑其云端打勾。
- 建议：在 t082 适配器测试中用 `PolicyAgentTestRig` 补两条：Agent install 失败（`fail_install=True`）时 `_install_network_policy` 抛错且 gate 目录无 ready.json；install+inspect 成功时 ready.json 生成且内容身份正确。

### t082_test_f002 - AC-007 的 Stream 替换预算耗尽分支在新策略路径上无测试

- 严重度：minor
- 锚点：AC-007「达到既有替换预算后明确 failed，不无限建毁」
- 位置：`tests/unit/test_t082_supervisor_policy_convergence.py::test_stream_agent_unavailable_replaces_stream_only_after_budget`
- 问题：该测试只证明预算内触发一次 Stream-only 替换且不触碰 Browser；新路径 `core.py` 中 `stream_policy_agent_unavailable` 分支在 `_stream_replacement_allowed` 为假（预算耗尽）时应转 failed 的行为没有任何测试驱动。主条款（仅修复 Stream、Browser 不变）已被覆盖，故仅记 minor 覆盖扩展。
- 建议：补一条预算耗尽（如预置替换计数达上限）时不出现 `start_stream` 且 observation 为 failed 的用例。

### t082_test_f003 - AC-008「不恢复用户主动暂停/已停止实例」只有他实例记录一条间接覆盖

- 严重度：minor
- 锚点：AC-008「只恢复本机制隔离且仍为当前运行意愿的实例，不触碰用户暂停、停止或更新实例」
- 位置：`tests/unit/test_t082_supervisor_policy_convergence.py::test_other_instances_pause_record_is_never_resumed`
- 问题：已测的是「他实例的 `_policy_paused` 记录不泄漏到当前实例」与「本机制暂停在复验后恢复」；没有用例把当前实例置为用户暂停/期望停止状态并断言收敛不发出 unpause。恢复围栏主路径（当前实例 + 复验通过才 unpause）已覆盖，故记 minor。
- 建议：补一条 desired 非 running（或存在用户暂停语义）时即使规则复验通过也不 unpause 的用例。

### t082_test_f004 - AC-003 身份伪造在 Agent 协议层只参数化了 profile_id 一个字段

- 严重度：minor
- 锚点：AC-003「伪造部署/实例/配置/角色/目标 ID … 均被拒绝」
- 位置：`tests/unit/test_t082_policy_agent.py::test_identity_mismatch_is_rejected_for_every_op`
- 问题：该测试只伪造 `profile_id` 一个字段（且只对 `fail_close` 一个 op 验证，标题称 every op 但循环未展开）；deployment_id / runtime_instance_id / config_version / role / target_container_id 的伪造拒绝靠同一条身份全等比较路径，适配器层另有标签接管/采用测试间接覆盖，故记 minor 而非阻断。
- 建议：把该测试参数化为六个身份字段 × 至少 install/inspect/fail_close 三个 op。

### t082_test_f005 - t055 删除 5 测后留下无调用方的死 harness

- 严重度：minor
- 锚点：行为缺陷（测试卫生，无 AC 影响）
- 位置：`tests/unit/test_t055_supervisor_runtime_robustness.py:78` 的 `_policy_adapter` 与 `:99` 的 `_install`
- 问题：5 个 `_run_policy_helper` 测试删除后，`_policy_adapter` / `_install` / `_Helper` 链已无任何测试调用（grep 全文件仅定义处命中），死代码会误导后续维护者以为临时 helper 路径仍被覆盖。
- 建议：随删除一并移除这组死 harness，或在补 f001 的 ready 标记测试时复用 `_install` 形状并接 rig。

## 结论

- 改测方向复核：逐项核对全部既有测试改动，未发现「就地把旧预期改成当前实现输出」的迁就式改测。删除面（a11 全文件、t055 五测、boundaries 一测、t026 CLI 一测、t026 convergence 一测、t051 一测）均整体删除且 progress.md 逐项写明理由，符合仓内 TDD 铁律；其中 a11 的 ready 标记子集语义未失效却未补回，见 f001。harness 适配文件（t052、t080 mounts、a36、t051 identity/error、display_config、network_policy_input_safety）断言值保持不变，仅补 `deployment_instance_id` 构造参数与 rig 接线；egress parity 的 spec dict 断言逐字不变（`tests/unit/test_egress_plan_and_runner_sdk.py` 中 `{"role": "browser", "allowed_tcp": [("203.0.113.50", 18080)], ...}` 与改前一致），t052 中 policy 文档断言由 JSON dict 形改为同一 spec 对象的等值字段断言（元组/列表形状随生产返回类型统一，非弱化）。
- 危险模式扫描说明：无恒真断言、无 skip/only、无注释掉断言、无阈值放宽。新代码中的 `# type: ignore[...]` 均为测试替身上的窄范围标注（rig 的 `executor.resolve` 计数包装、容器 pause/unpause lambda、`adapter._test_rig` 属性注入），不屏蔽任何断言或生产错误，已逐处调查后放行，不出 finding。`policy_agent_test_support.stub_ensure` 替换的是 `ensure_policy_agent` 生命周期本身，仅用于被测主题不在生命周期上的既有套件（a36/t051/egress），且返回 handle 经真实 `_policy_agent_identity` 派生并注册、后续 derive/verify/fail-close 仍走真实 rig 协议路径；测生命周期本身的 t082 适配器套件只用 `install_on` 走真实 ensure，未 mock 被测逻辑，不出 finding。
- 新测可信度：`test_t082_policy_agent.py`（10 测）直接驱动生产 `PolicyAgent.handle` 与真实 UDS `_Server`/`PolicyAgentClient`，断言修订围栏、幂等、身份拒绝、fail-close 确认与畸形/超大请求类型化；`test_t082_adapter_policy_agents.py`（10 测）经进程内 rig（真实 `PolicyAgent` 状态机 + 假 executor，仅在 Docker/内核边界替身）驱动真实 `DockerAdapter`，断言 Agent 容器形状（NET_ADMIN only、只读根、精确 `network_mode=container:<id>`、单一 socket 挂载）、稳态 5 次 verify 零创建零 exec 零重复 DNS、刷新 replace 与失败保留旧冻结 spec、第二适配器接管、孤儿精确清理；`test_t082_supervisor_policy_convergence.py`（10 测）驱动真实 `SupervisorCore._converge_session`，断言漂移封闭/未确认暂停/复验恢复/30 秒预算隔离/Stream-only 替换/事件定点修复。三者均触达生产逻辑，非测 fake 本身。本人复跑：上述三文件 + 受影响既有套件共 15 个文件 194 条全绿；e2e 三文件可收集 7 测（云端无 Docker 未实跑，与 p133 一致）。
- 本轮新发现：5 条（1 important、4 minor）
- 未进表的提示：task.md 未知契约清单两项仍带 UNVERIFIED-SPIKE 字样，但均附用户 2026-11-18 裁定处置注记并登记 p132 延期本地 spike，按父任务给定的修订后契约口径不另出 blocking finding；AC-010 同理按处置注记 + p133 判定。e2e 三文件改由生产 `PolicyAgentClient` 驱动后，内核正负断言（允许口 PONG、封锁口失败、他 netns 不受影响、Agent 移除后规则持续、IPv6 修订围栏拒绝）在 diff 中均保留，仅云端未实跑。
- 总体判断：AC-001 的 ready 标记门控子句在云端可跑的单元层失去全部直接断言（f001，important），该 AC 打勾在测试轴不成立；其余 AC 均有真实、可信且本人复跑通过的测试支撑。
- 系统性 follow-up：无（f001/f002/f003 均为本 task 内补测，不需新 tid）

### AC 复验方式

- AC-001：TICK-VOID，re_verified。安装/校验协议层有真实测试，但「失败不生成 ready 标记、成功才生成」子句随 a11 删除后无任何云端可跑测试断言（见 f001），仅剩未实跑且延期 p133 的 e2e，不能支撑非 [deploy] AC 的打勾。
- AC-002：TICK-VALID，re_verified。`test_repeated_verification_creates_and_execs_nothing` 断言 5 次 verify 零容器创建、exec 替身为 tripwire、DNS 解析计数恒为 1；本人复跑通过。
- AC-003：TICK-VALID，re_verified。协议层身份不符拒绝、旧修订重放/同修订换 spec 拒绝、64 KiB 超大与畸形请求类型化、ResolveRequest 拒绝凭据/URL/路径/命令形输入、额外字段被 schema 拒绝；本人复跑通过（字段参数化广度见 f004 minor）。
- AC-004：TICK-VALID，re_verified。适配器测试断言 Agent 仅 NET_ADMIN、只读根、单一 socket 目录挂载、无业务挂载，`network_mode` 为精确目标 ID；业务容器形状由未改断言的 t080 mounts 等套件继续断言且本人复跑通过；真实内核完成性属 p132 spike 延期范围。
- AC-005：TICK-VALID，re_verified。`test_upstream_change_refreshes_with_replace` 与 `test_refresh_failure_keeps_old_frozen_spec` 断言同一冻结派生、replace 刷新升修订、失败保留旧 spec 且旧 spec 仍可 verify、巡检不重复解析；本人复跑通过。
- AC-006：TICK-VALID，re_verified。收敛测试断言 Browser 漂移 fail-close 成功不暂停、未确认时暂停精确目标且不删数据不重建，观察错误可定位；本人复跑通过（双栈内核正负例在 e2e 中保留、延期 p133）。
- AC-007：TICK-VALID，re_verified。收敛测试断言 Stream 代理不可用时仅 `start_stream` 替换、Browser 不暂停不 fail-close 不重建；本人复跑通过（预算耗尽分支见 f002 minor）。
- AC-008：TICK-VALID，re_verified。收敛测试断言 Agent 不可用先定点修复、30 秒预算内 recovering 不暂停、超预算隔离、本机制暂停复验后才恢复、他实例记录永不恢复；协议层修订失配/响应错误不能返回 ready 由 t082 协议测试覆盖；本人复跑通过（用户暂停分支见 f003 minor）。
- AC-009：TICK-VALID，re_verified。适配器接管测试断言第二 Supervisor 采用同一 Agent 零新建、孤儿仅在目标消失时清理、Profile 拆除精确清理；收敛测试断言 Agent 事件只修复对应 Profile、未知 Profile 无动作；迟到回执由协议修订围栏测试覆盖；本人复跑通过。
- AC-010：TICK-VALID，trust_prior。按 task.md 契约区用户 2026-11-18 裁定处置注记判定：云端可做部分（e2e 三文件已改由生产 PolicyAgentClient 驱动、内核断言保留、7 测可收集，本人已核 diff 与 collect 结果）完成即视为流程完成，真实 10 分钟稳态验证延期 p133，不表示已实测通过。

coverage = 8 / 10

verdict: FAIL

## Round 2 (2026-11-18T14:27:56+08:00)

- task：`t082_persistent_namespace_policy_agents`
- spec：`docs/tasks/t082_persistent_namespace_policy_agents/task.md`
- diff_anchor：`c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- target：`git diff c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- round：2

reviewed_scope: 904bf1a0d355ebc1

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核：
    - t082_test_f001（important，AC-001 ready 标记门控无单元替代）：**已消除**。`tests/unit/test_t082_adapter_policy_agents.py:363` 新增 `test_install_writes_ready_marker_only_after_agent_success`，经 `PolicyAgentTestRig.install_on`（真实 `PolicyAgent` 状态机，仅 Docker/内核边界替身）驱动生产 `DockerAdapter._install_network_policy`（`src/backend/cbrowser/supervisor/docker_adapter.py:907`，ready 标记写于 install 成功之后、异常路径不写）：成功臂断言 `ready.json` 内容恰为 `{"instance_id": "inst_1", "role": "browser", "status": "ready"}`；失败臂置 `rig.executor.fail_install = True` 并换 spec（走 revision+1 安装路径，Agent 侧 install 内部核验见 `policy_agent.py:67-73`），断言抛 `DockerSandboxError` 且独立 gate 目录无 `ready.json`。双向断言均非恒真、非直调 fake，本人单独复跑通过。畸形回执不写 ready 与失败臂同为「异常先于 `atomic_write_text`」的同一生产路径，另有协议/客户端畸形回执类型化测试支撑。
    - t082_test_f002（minor，Stream 替换预算耗尽无测试）：**已消除**。`tests/unit/test_t082_supervisor_policy_convergence.py:428` 新增 `test_stream_agent_unavailable_budget_exhausted_fails`：预置 `_stream_replace_attempts` 达 `_STREAM_REPLACE_MAX` 且 unknown 已过期 31 秒，驱动生产 `_converge_session`，断言无 `start_stream`、observation 为 failed 且 `last_error == "stream_policy_agent_unavailable"`，与生产分支（`core.py` stream 不可用 + 预算耗尽转 failed）逐字对应。本人复跑通过。
    - t082_test_f003（minor，不恢复非 running 意愿无用例）：**已消除**。同文件 `:451` 新增 `test_paused_target_with_stopped_intent_is_never_resumed`：当前实例置 `_policy_paused` 记录且 `session.desired_state = "stopped"`、规则可复验（`browser_policy_ok = True`），驱动 `_converge_session`，断言无 `unpause:c_browser`、暂停记录保留、observation 为 failed/`browser_policy_isolated`，对应生产围栏（`core.py` paused 分支先查 `session.desired_state != "running"` 即不恢复）。本人复跑通过。
    - t082_test_f004（minor，身份伪造只参数化一个字段一个 op）：**已消除**。`tests/unit/test_t082_policy_agent.py:93` 的 `test_identity_mismatch_is_rejected_for_every_op` 已参数化为 6 个身份字段（deployment_id / profile_id / runtime_instance_id / config_version / role / target_container_id）× 5 个 op（health / resolve / install / inspect / fail_close）共 30 组合，每组合断言 `ok is False`、`error_code == "identity_mismatch"` 且 `executor.installed == []`，经生产 `PolicyAgent.handle` 校验。同文件 `:128` 另增 `test_client_resolve_rejects_non_ip_receipts`：替身仅替换客户端传输边界 `_call`，被测的回执 IP 校验逻辑在生产 `PolicyAgentClient.resolve` 内，断言非 IP 回执抛 `PolicyAgentUnavailable` 而非裸 ValueError。本人复跑通过。
    - t082_test_f005（minor，t055 死 harness）：**已消除**。`tests/unit/test_t055_supervisor_runtime_robustness.py` 中 `_Helper` / `_policy_adapter` / `_install` 已整体删除（grep 全文件仅余 15 条无关测试、无上述符号），文件在本人复跑中全绿（见下）。
    - 代码轴第 1 轮接线 bug（暂停恢复不可达）的接线级测试复核：`tests/unit/test_t082_supervisor_policy_convergence.py:386` 的 `test_reconcile_routes_paused_browser_to_verified_resume` **真实覆盖生产路由，非绕过门禁的直调**。它以 MockTransport 提供 API runtime 载荷（desired=running、本实例）、roles 扫描给出 Browser `status="paused"` / Stream running、预置本机制 `_policy_paused` 记录，调用生产入口 `SupervisorCore._reconcile_profile`（`core.py:1457`）；生产路由在同实例分支命中「机制暂停 + browser paused + stream running」条件（`core.py:1614-1624`）后转入 `_converge_session`，再经 `_attempt_policy_resume` 复验才 unpause。断言 `unpause:c_browser` 已发出、`_policy_paused` 清空、`_terminal_observations` 为空（暂停未被误报为 container_exit）、transport observation 为 ready。本人复跑通过。
- 改测方向复核：本轮新增测试均为净新增用例（ready 双向、预算耗尽、desired=stopped、身份 6×5 参数化扩展、client 回执校验、reconcile 接线），未就地改动任何既有测试的预期迁就实现；t055 为整体删除死 harness，与第 1 轮建议一致。无迁就式改测。
- 危险模式扫描（本轮新增测试）：无恒真断言、无 skip/only、无注释掉断言、无弱化断言、无阈值放宽。身份参数化测试对每个组合都有实质断言（ok/error_code/零副作用）；client 回执测试的替身只替换传输层 `_call`，校验逻辑本身在生产代码内，不属 mock 被测逻辑。
- 本轮新发现：0 条
- 未进表的提示：本人全量 unit 复跑（`-n 4`）初次出现 23 条 bad，其中 t028×4 / t060×3 / t034×1 共 8 条不在实现侧自报内；逐条归因后确认系本人直跑 pytest 时 PATH 缺 `~/.local/bin` 致子进程找不到 `uv`（t034 失败栈直接为 `FileNotFoundError: 'uv'`），补上 PATH 后该三文件 30 条全过，与 t082 diff 无关（该三测试文件未被本 diff 修改）。其余 15 条 bad（t063 2 failed + 10 errors、t068×2、a16×1）与实现侧自报「2326 条、15 条 bad 全老基线」精确吻合。integration 抽查：208 passed + 7 skipped = 215，与自报「215 全过」一致。
- 总体判断：第 1 轮 5 条 finding 全部真实修复、复跑通过，接线级测试真实覆盖生产路由，本轮无新 critical / important / minor finding；AC-001 在测试轴恢复成立。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。新增 ready 标记双向测试经 rig 驱动生产 `_install_network_policy`：成功才写且内容身份正确、install 失败抛错且 gate 无 ready.json（见 f001 复核）；本人复跑通过。
- AC-002：TICK-VALID，re_verified。`test_repeated_verification_creates_and_execs_nothing` 等适配器套件本轮随三文件复跑全绿，断言口径与第 1 轮一致（5 次 verify 零创建零 exec、DNS 计数恒 1）。
- AC-003：TICK-VALID，re_verified。身份伪造已扩展为 6 字段 × 5 op 全参数化拒绝 + 零副作用断言，叠加原有旧修订重放、超大/畸形请求、注入形输入拒绝测试，本人复跑通过。
- AC-004：TICK-VALID，re_verified。适配器容器形状断言（NET_ADMIN only、只读根、精确 network_mode、单一 socket 挂载）随套件复跑通过；真实内核完成性属 p132 spike 延期范围，与第 1 轮口径一致。
- AC-005：TICK-VALID，re_verified。刷新 replace 与失败保留旧冻结 spec 两测随套件复跑通过，巡检不重复解析断言不变。
- AC-006：TICK-VALID，re_verified。收敛套件漂移封闭/未确认暂停两测复跑通过；双栈内核正负例在 e2e 中保留、延期 p133，与第 1 轮口径一致。
- AC-007：TICK-VALID，re_verified。Stream-only 替换主条款测试复跑通过，且预算耗尽分支已由新增 `test_stream_agent_unavailable_budget_exhausted_fails` 补齐（见 f002 复核）。
- AC-008：TICK-VALID，re_verified。机制暂停复验恢复、超预算隔离、他实例记录不恢复等原有用例复跑通过，且新增 desired=stopped 不恢复用例与 reconcile 接线级恢复用例均通过（见 f003 复核与接线复核）。
- AC-009：TICK-VALID，re_verified。第二适配器接管、孤儿精确清理、事件定点修复、协议修订围栏各测随套件复跑通过。
- AC-010：TICK-VALID，trust_prior。按 task.md 契约区用户 2026-11-18 裁定处置注记判定：云端可做部分完成即视为流程完成，真实 10 分钟稳态验证延期 p133，不表示已实测通过；与第 1 轮口径一致。

coverage = 9 / 10

verdict: PASS

## Round 3 (2026-11-18T14:42:51+08:00)

- task：`t082_persistent_namespace_policy_agents`
- spec：`docs/tasks/t082_persistent_namespace_policy_agents/task.md`
- diff_anchor：`c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- target：`git diff c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- round：3

reviewed_scope: 5e0732197b369a78

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核：第 2 轮测试轴已 PASS、第 1 轮 5 条 finding（t082_test_f001–f005）全部消除，本轮变更面未触碰其修复内容，相关套件随本轮抽查复跑全绿（见下），无回退、无换形式弱化。本轮重点复核的是代码轴第 2 轮 f005/f006 两条接线修复的新增测试：
    - 代码 f005（Supervisor 重启后暂停所有权重登记不可达）：`tests/unit/test_t082_supervisor_policy_convergence.py:472` 新增 `test_reconcile_restores_paused_browser_after_supervisor_restart` **真实驱动生产入口** `SupervisorCore._reconcile_profile`，而非测 fake 本身。构造与重启语义一致：经 `_core_with_runtime_api` 建核后 `core._sessions.clear()`、断言 `_policy_paused == {}`（无会话、无内存所有权记录），roles 扫描给 Browser `status="paused"` / Stream `running`；替身仅在系统边界（Docker 适配器 `_FakeAdapter`、`adapter.client.api.inspect_container` 的端口绑定查询、API runtime 的 MockTransport）。断言关键结果齐全：恢复创建会话（`PROFILE in core._sessions`）、所有权流转完成（恢复时在 `src/backend/cbrowser/supervisor/core.py:1837-1845` 重登记 `_policy_paused`、复验恢复后清空）、`unpause:c_browser` 已发出、`_terminal_observations` 为空（暂停未被误报为 container_exit）、transport observation 为 ready。本人复跑通过。
    - 代码 f006（本机制暂停期间 Stream 退出无修复路径）：同文件 `:529` 新增 `test_stream_loss_during_browser_isolation_repairs_stream_only` 同样驱动生产 `_reconcile_profile`：预置本机制 `_policy_paused` 记录，roles 给 Browser `paused` / Stream `exited`。断言 Stream-only 替换被分发（`replaced == [PROFILE]`）、Browser 未被 unpause（`unpause:c_browser` 不在 adapter.calls）、暂停记录保留、`_terminal_observations` 为空。生产闸门在 `core.py:1625-1642`（机制暂停 + Browser paused + Stream 非 running + 替换预算内 → `_replace_stream_only` 并 return，先于 container_exit 误报分支）。本人复跑通过。
    - 变异校验独立复核（不采信实现侧自报）：本人以文件备份方式临时变异、测毕按备份还原（未用 `git checkout --`，还原后 `core.py` md5 与变异前一致 `c7dee72aa609012c3ac2ecfa3ae27b2e`）。①把 f006 闸门（`core.py:1625-1631` 的条件）加 `and False` 改永假 → `test_stream_loss_during_browser_isolation_repairs_stream_only` 在 `:570` 变红、重启接管测试仍绿，证明该测精确锚定此闸门；②把 f005 fall-through 闸门（`core.py:1683` 的 `b_c["status"] == "paused" and s_c["status"] == "running"`）改永假 → `test_reconcile_restores_paused_browser_after_supervisor_restart` 在 `:520` 变红（会话未恢复）、Stream 丢失测试仍绿。两变异各自只打红对应测试，与实现侧「两闸门永假后两测变红」自报一致；还原后全文件 15 条复跑全绿。
- 改测方向复核：本轮测试变更为文件末尾净新增两条用例，未就地改动任何既有测试预期。无迁就式改测。
- 危险模式扫描（本轮新增两测）：无恒真断言、无 skip/only、无注释掉断言、无弱化断言、无阈值放宽。f006 测试以记录替身替换 `core._replace_stream_only` 本身：被测对象是 `_reconcile_profile` 的路由决策（隔离期间 Stream 丢失应分发 Stream-only 修复而非误报退出/整对失败），替身只记录分发这一下游接缝；`_replace_stream_only` 的真实行为（有界替换、经适配器 `start_stream`）由同文件收敛级测试 `test_stream_agent_unavailable_replaces_stream_only_after_budget`（断言 `start_stream` 经真实生产方法发出）覆盖，故不构成「mock 掉被测逻辑」，调查后放行、不出 finding。f005 测试的 `adapter.client` 替身仅提供 Stream 端口绑定 inspect 这一 Docker 边界数据，恢复/重登记/复验/unpause 全走生产代码。
- 本轮复跑证据：`tests/unit/test_t082_supervisor_policy_convergence.py` 全文件 15 passed；抽查 `tests/unit/test_t082_policy_agent.py` + `tests/unit/test_t082_adapter_policy_agents.py` + 上述收敛文件 + `tests/unit/test_t026_supervisor_convergence.py` + `tests/unit/test_t026_network_policy_verify.py` 共 79 passed，无回归。运行环境为仓内 gate venv、`PATH` 含 `~/.local/bin`、`PYTHONPATH=src/backend`。全量 unit / gates 未在本轮重跑（第 2 轮已全量复跑且本轮变更面仅限两处闸门与其测试，抽查范围与父任务口径一致）。
- 本轮新发现：0 条
- 未进表的提示：无
- 总体判断：两条新测试真实驱动生产入口并断言会话恢复/所有权流转/unpause 与 Stream-only 分发/无 container_exit 误报，变异校验经本人独立复现成立，其余测试面抽查无回归；本轮无未解决 critical / important / minor finding。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。ready 标记双向测试（第 2 轮复核）随适配器套件本轮抽查复跑通过，断言口径不变。
- AC-002：TICK-VALID，re_verified。适配器套件零 churn 断言随本轮抽查复跑通过。
- AC-003：TICK-VALID，re_verified。协议套件 6 字段 × 5 op 身份拒绝等测试随本轮抽查复跑通过。
- AC-004：TICK-VALID，re_verified。适配器容器形状断言随本轮抽查复跑通过；真实内核完成性属 p132 spike 延期范围，与前轮口径一致。
- AC-005：TICK-VALID，re_verified。刷新 replace 与失败保留旧冻结 spec 两测随本轮抽查复跑通过。
- AC-006：TICK-VALID，re_verified。收敛套件漂移封闭/未确认暂停两测随本轮全文件复跑通过；双栈内核正负例在 e2e 中保留、延期 p133。
- AC-007：TICK-VALID，re_verified。Stream-only 替换与预算耗尽两测复跑通过；本轮新增 f006 测试进一步证明 Browser 隔离期间 Stream 丢失仍只分发 Stream-only 修复、Browser 保持暂停。
- AC-008：TICK-VALID，re_verified。机制暂停复验恢复、desired=stopped 不恢复、超预算隔离等用例复跑通过；本轮新增重启接管测试证明 Supervisor 重启后所有权重登记→复验→unpause 全链路（代码 f005），且经本人变异复核锚定生产闸门。
- AC-009：TICK-VALID，re_verified。第二适配器接管、孤儿精确清理、事件定点修复各测随抽查复跑通过；重启接管测试同时证明接管后无 container_exit 误报、无自激终态报告。
- AC-010：TICK-VALID，trust_prior。按 task.md 契约区用户 2026-11-18 裁定处置注记判定：云端可做部分完成即视为流程完成，真实 10 分钟稳态验证延期 p133，不表示已实测通过；与前轮口径一致。

coverage = 9 / 10

verdict: PASS

## Round 4 (2026-11-18T14:59:19+08:00)

- task：`t082_persistent_namespace_policy_agents`
- spec：`docs/tasks/t082_persistent_namespace_policy_agents/task.md`
- diff_anchor：`c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- target：`git diff c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- round：4

reviewed_scope: 5bafbf4e01d11667

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核：第 3 轮测试轴已 PASS，第 1 轮 5 条 finding（t082_test_f001–f005）与代码轴 f005/f006 的接线测试在本轮变更面中未被触碰（核对方法见下条），无回退、无换形式弱化。
- 本轮变更面核对方法与结论（增量确认轮，只核三项）：
- 变更面定界：以工作目录为本 worktree 执行 `git rev-parse --show-toplevel` 输出精确等于本 worktree 路径，落点校验通过。`git status --short` 显示全部交付文件均为已暂存状态（状态列单字母），唯一双列条目是 `task.md`（`MM`）；`git diff`（未暂存增量，即第 3 轮 PASS 指纹 `5e0732197b369a78` 之后的全部变化）只有 `docs/tasks/t082_persistent_namespace_policy_agents/task.md` 一个文件、2 行替换，无其他文件、无未跟踪交付文件。该增量正是未知契约清单两条 spike 的结论化改写，除此之外交付内容与第 3 轮审阅时逐字节相同。
- ① 改写语义等价性：与改写前原文（暂存版，即第 1 轮所见「原文＋注记」形态，`git diff` 中以 `-` 行可见）逐项对照。第一条（仅 NET_ADMIN 完整策略/DNS 能力）：原文要件为「UNVERIFIED-SPIKE、先用正式隔离 spike、结论入 findings/ADR；若需 SYS_ADMIN/host PID/privileged 停止扩权并修订设计、不静默绕过」＋处置「云端无 Docker、经用户裁定设计按最小权限假设先行（仅 NET_ADMIN、只读根、无额外挂载）、正式 spike 延期本地并由 p132 跟踪、spike 若否定假设按上文停止扩权并修订」。改写后逐项保留：云端无 Docker 不可实证、设计按最小权限假设冻结并已实现（仅 NET_ADMIN、只读根、无额外挂载）、正式隔离 spike 延期本地执行并由 pending p132 跟踪、结论入 findings/ADR、spike 若否定假设或显示需要 SYS_ADMIN/host PID/privileged 则停止扩权并修订设计、不静默绕过。新增的「ADR 039」引用指向实存文件 `docs/blueprint/decisions/20261118_namespace_policy_agent.md`（其结论与该口径一致），「已实现」指设计已落入本 diff 的实现（第 1–3 轮已核），不是实证完成的表述。第二条（暂停/恢复安全行为）：原文要件为「UNVERIFIED-SPIKE、验证网络负例和暂停所有权、pause API 返回成功不能单独证明隔离有效」＋处置「机制按 pause 所有权围栏先行实现、真实链路负例验证延期 p132」。改写后逐项保留：机制按 pause 所有权围栏先行实现、真实链路的网络负例与暂停所有权实证延期本地并由 p132 跟踪、pause API 返回成功不单独作为隔离有效的证据；括号内补充的围栏细则（仅本机制暂停且仍为当前运行意愿的实例可经复验恢复、重启后按 scan 重登记所有权）与第 2/3 轮已复核的生产实现及接线测试口径一致，属机制描述而非实证冒充。两条改写均未把延期中的 spike 写成已完成、已实证或已通过，「结论」一词在行内均明确锚定为「（2026-11-18，用户裁定）」的流程结论，与改写前处置注记语义等价；改写后 `task.md` 中已无作为条目标记的 `UNVERIFIED-SPIKE` 字样（仅剩未知契约清单规范注释中的标记定义本身）。
- ② 测试面零变更：未暂存增量中 `tests/` 路径下文件数为零；`git status --short` 中全部 `tests/` 条目均为已暂存单列状态（与第 3 轮审阅时的暂存内容相同），无未跟踪测试文件。故测试面相对第 3 轮 PASS 指纹零变更，第 3 轮的测试可信、覆盖与危险模式结论原样成立。本人另抽查复跑 t082 三个单元套件（协议/适配器/收敛）共 37 passed，无回归。
- ③ progress.md 口径一致性：`progress.md` 在未暂存增量中零变更，处置表（t082_code_f001–f006、t082_test_f001–f005 全部「已修」）与第 3 轮审阅时相同。其与 spike/AC-010 相关的表述逐处核对，与改写后口径一致且无新增冒充：「[deploy] 与 spike 处置」段仍写两项 spike 云端无 Docker 不可验、打勾「不表示已实测通过」；收尾报告写「两项 spike 延期 p132」「AC-010 按契约区处置注记打勾（本地补验 p133）」；结果摘要写云端不可验部分「已逐项登记 p132/p133 留待本地统一补验，未在云端冒充实测」；长期文档闭环写「spike 结论待本地执行后入 findings 并回填（p132）」。p132/p133 两个 pending 文件均为 `todo`、内容仍要求本地正式 spike 与真实链路负例，未被写成已完成。
- 改测方向复核：本轮无任何测试改动。无迁就式改测。
- 本轮新发现：0 条
- 未进表的提示：无
- 总体判断：本轮唯一交付变更（未知契约清单两条结论化改写）与改写前处置注记语义等价，延期本地 spike（p132）与 AC-010 延期补验（p133）的口径完整保留、无冒充已实证表述；测试面与 progress.md 相对第 3 轮 PASS 状态零变更。本轮无未解决 critical / important / minor finding。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。测试面相对第 3 轮零变更，ready 标记双向测试随 t082 套件本轮抽查复跑通过（37 passed）。
- AC-002：TICK-VALID，re_verified。适配器零 churn 断言随套件本轮抽查复跑通过，测试内容与第 3 轮一致。
- AC-003：TICK-VALID，re_verified。协议套件 6 字段 × 5 op 身份拒绝等测试随套件本轮抽查复跑通过。
- AC-004：TICK-VALID，re_verified。适配器容器形状断言随套件复跑通过；真实内核完成性属 p132 spike 延期范围，改写后口径不变（设计按最小权限假设先行、未冒充实证）。
- AC-005：TICK-VALID，re_verified。刷新 replace 与失败保留旧冻结 spec 两测随套件本轮抽查复跑通过。
- AC-006：TICK-VALID，re_verified。收敛套件漂移封闭/未确认暂停两测随套件复跑通过；双栈内核正负例在 e2e 中保留、延期 p133。
- AC-007：TICK-VALID，re_verified。Stream-only 替换、预算耗尽与隔离期间 Stream 丢失分发三测随套件本轮抽查复跑通过。
- AC-008：TICK-VALID，re_verified。机制暂停复验恢复、desired=stopped 不恢复、重启接管重登记等用例随套件复跑通过；真实链路暂停所有权实证延期 p132，改写后口径不变。
- AC-009：TICK-VALID，re_verified。第二适配器接管、孤儿精确清理、事件定点修复各测随套件本轮抽查复跑通过。
- AC-010：TICK-VALID，trust_prior。按 task.md 契约区用户 2026-11-18 裁定处置注记判定：云端可做部分完成即视为流程完成，真实 10 分钟稳态验证延期 p133，不表示已实测通过；本轮改写未触碰该注记，口径与前轮一致。

coverage = 9 / 10

verdict: PASS

## Round 5 (2026-11-18T15:01:08+08:00)

- task：`t082_persistent_namespace_policy_agents`
- spec：`docs/tasks/t082_persistent_namespace_policy_agents/task.md`
- diff_anchor：`c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- target：`git diff c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- round：5

reviewed_scope: a370c42e621635ab

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核：第 4 轮测试轴已 PASS，第 1 轮 5 条 finding（t082_test_f001–f005）全部消除的结论在本轮变更面中未被触碰，无回退、无换形式弱化；相关套件随本轮抽查复跑全绿（见下）。
- 本轮变更面核对方法与结论（增量确认轮，只核两项）：
- 变更面定界：以工作目录为本 worktree 执行 `git rev-parse --show-toplevel`，输出精确等于本 worktree 路径，落点校验通过。`git status --short` 显示全部交付文件为已暂存状态，唯二双列条目（`MM`）是 `docs/specs/runtime_lifecycle.md` 与 `docs/specs/proxy_management.md`；无未跟踪文件。`git diff`（未暂存增量，即第 4 轮 PASS 之后的全部变化）恰为 2 个文件、2 行替换（`git diff --stat`：2 files changed, 2 insertions, 2 deletions），除此之外交付内容与第 4 轮审阅时相同。
- ① 未暂存增量恰为两行：`docs/specs/runtime_lifecycle.md:4` 的 front matter 由 `tasks: [baseline]` 改为 `tasks: [baseline, t082]`；`docs/specs/proxy_management.md:4` 同样由 `tasks: [baseline]` 改为 `tasks: [baseline, t082]`。两处均为 specs-index 检查要求的任务关联登记，正文表述已在 finalization 同步（暂存区正文改动属前轮已审范围），本轮未暂存部分不含任何正文、代码或配置改动。工作区文件头实读与 diff 一致。
- ② tests/ 与其他交付零变更：`git diff --name-only -- tests/` 输出为空（0 个文件）；未暂存增量文件清单仅上述两份 spec，`src/`、`scripts/`、`schemas/`、`compose.yaml`、蓝图与 task 目录文件均无未暂存改动。故测试面相对第 4 轮 PASS 状态零变更，第 4 轮的测试可信、覆盖与危险模式结论原样成立。
- ③ 抽查无回归：本人以仓内 gate venv、`TMPDIR` 指向任务临时目录、`PATH` 含 `~/.local/bin`、`PYTHONPATH=src/backend`，复跑 t082 三个单元套件 `tests/unit/test_t082_policy_agent.py`、`tests/unit/test_t082_adapter_policy_agents.py`、`tests/unit/test_t082_supervisor_policy_convergence.py`，结果 37 passed，无失败、无跳过。
- 改测方向复核：本轮无任何测试改动。无迁就式改测。
- 危险模式扫描：本轮无测试文件变更，无新增危险模式；既有测试面与第 4 轮一致。
- 本轮新发现：0 条
- 未进表的提示：无
- 总体判断：本轮唯一交付变更为两份关联 spec 的 front matter 各加一行 t082 关联登记，未暂存增量与预期逐行吻合，tests/ 与其他交付零变更，t082 三套件抽查 37 条全绿无回归。本轮无未解决 critical / important / minor finding。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。测试面相对第 4 轮零变更，ready 标记双向测试随 t082 套件本轮抽查复跑通过（37 passed）。
- AC-002：TICK-VALID，re_verified。适配器零 churn 断言随套件本轮抽查复跑通过，测试内容与第 4 轮一致。
- AC-003：TICK-VALID，re_verified。协议套件 6 字段 × 5 op 身份拒绝等测试随套件本轮抽查复跑通过。
- AC-004：TICK-VALID，re_verified。适配器容器形状断言随套件复跑通过；真实内核完成性属 p132 spike 延期范围，口径与前轮一致。
- AC-005：TICK-VALID，re_verified。刷新 replace 与失败保留旧冻结 spec 两测随套件本轮抽查复跑通过。
- AC-006：TICK-VALID，re_verified。收敛套件漂移封闭/未确认暂停两测随套件复跑通过；双栈内核正负例在 e2e 中保留、延期 p133。
- AC-007：TICK-VALID，re_verified。Stream-only 替换、预算耗尽与隔离期间 Stream 丢失分发三测随套件本轮抽查复跑通过。
- AC-008：TICK-VALID，re_verified。机制暂停复验恢复、desired=stopped 不恢复、重启接管重登记等用例随套件复跑通过；真实链路暂停所有权实证延期 p132，口径不变。
- AC-009：TICK-VALID，re_verified。第二适配器接管、孤儿精确清理、事件定点修复各测随套件本轮抽查复跑通过。
- AC-010：TICK-VALID，trust_prior。按 task.md 契约区用户 2026-11-18 裁定处置注记判定：云端可做部分完成即视为流程完成，真实 10 分钟稳态验证延期 p133，不表示已实测通过；本轮改动未触碰该注记，口径与前轮一致。

coverage = 9 / 10

verdict: PASS
