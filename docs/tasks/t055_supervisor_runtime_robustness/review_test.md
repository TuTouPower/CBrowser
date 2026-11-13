# Task review t055（reviewer_focus: 测试）

- task：`t055_supervisor_runtime_robustness`
- spec：`docs/tasks/t055_supervisor_runtime_robustness/task.md`
- diff_anchor：`1c0963845705e355ccdd7e1c3963533c9df7437a`
- target：`git -C '<home>/workspace/CBrowser_t055' diff 1c0963845705e355ccdd7e1c3963533c9df7437a`
- round：1
- reviewed_at：2026-11-11T23:12:33+08:00

## Findings

### t055_test_f001 - 新测试文件 docstring 的 AC 编号系统性错位一位

- 严重度：minor
- 锚点：测试文档与规格的对应关系（不影响执行结果）
- 位置：`tests/integration/test_t055_cdp_close_code.py:116,133,149`、`tests/unit/test_t055_udp_mux_single_source.py:66,89,112,132`、`tests/unit/test_t055_socket_slot_cleanup.py:50,65,77,89,102,118,126,135`、`tests/unit/test_t055_runner_watchers.py:65,135`
- 问题：4 个新测试文件的 docstring 标注的 AC 编号全部比实际验证的 AC 大一位：CDP 关码三例写 AC-008，实为 AC-007（UDP mux 才是 AC-008）；UDP mux 四例写 AC-009，实为 AC-008（socket slot 才是 AC-009）；socket slot 八例写 AC-010，实为 AC-009（watcher 才是 AC-010）；watcher 两例写 AC-011——AC-011 根本不存在，实为 AC-010。测试体本身测的是正确的行为（已逐一对照断言与生产逻辑），错的只是标签；`tests/unit/test_t055_supervisor_runtime_robustness.py` 的 17 例标签全部正确（AC-001～AC-006 对位无误），说明不是全局偏移，而是这 4 个文件在撰写时集体错位。误导 AC 证据映射：按标签查 AC-008 覆盖会找到 CDP 测试，按标签查 AC-011 会一无所获。
- 建议：把 4 个文件的 docstring 编号各减一（watcher 两例改为 AC-010），与 task.md 契约区对齐。

### t055_test_f002 - CDP fake upstream 不模拟 close_code 随本地 close 的变化，读码顺序无回归防护

- 严重度：minor
- 锚点：AC-007「CDP 关码……在本地 close 之前读取」
- 位置：`tests/integration/test_t055_cdp_close_code.py:36-74`（`_FakeUpstream`）
- 问题：spike 的核心结论是读码点必须在本地 close 之前——实测复现确认：对端先关 4403 时 close 前读得 4403，本地先 close（对端未关）后读得本地自发的 1000。但 `_FakeUpstream.close_code` 是 `__init__` 设定后永不改变的普通属性，`close()` 只置 `self.closed = True`，不改 `close_code`。因此 `test_peer_close_code_is_propagated_to_client` 无法区分“先读码再 close”与“先 close 再读码”：把生产代码 `automation_router.py:242-254` 的读码与 `upstream.close()` 顺序对调，测试仍全绿。生产代码当前顺序正确（已读码确认：读码在 `:242-244`，`upstream.close()` 在 `:254`，且有“客户端先断开”抑制），spike 实验也已复现验证，所以行为本身无缺陷；缺的是把顺序钉住的回归测试。
- 建议：让 `_FakeUpstream.close()` 按真实 websockets 语义把 `close_code` 改写为 1000（对端未关码时的本地自发关码），则顺序写错时 `test_peer_close_code_is_propagated_to_client` 会收到 1000 而非 4403，当场变红。

### t055_test_f003 - AC-005 的 90s 宽限边界未钉住

- 严重度：minor
- 锚点：AC-005「Stream 替换在恢复时刻起 90s 内触发」
- 位置：`tests/unit/test_t055_supervisor_runtime_robustness.py:640-669`（`test_restore_grace_defers_stream_replacement_then_releases`）
- 问题：该测试只证明宽限 ∈ (0, 200]：恢复后立即收敛时 defer（`last_error == "registration_recovery_grace"`，无 `start_stream`），再把 `lost_at` 人工拨回 200 秒前时触发替换。生产常量确为 `_REGISTRATION_LOSS_GRACE_SEC = 90.0`（`core.py:361`），但没有任何测试区分 90s 与其他值——宽限被改成 60s 或 120s 时本测试仍全绿。锚定恢复时刻与不重置两点已有覆盖（`test_restore_armed_grace_survives_gateway_unreachable` 证实 gateway-unreachable 收敛后 `lost_at` 原值不变；`test_fresh_registration_replaces_restore_armed_state_at_once` 证实宽限内注册立即替换），所以 AC-005 的核心行为已验证，缺的只是边界值本身。
- 建议：补边界两例：`lost_at = now - 89` 时仍 defer，`lost_at = now - 91` 时触发替换。

### t055_test_f004 - A4 的 helper 日志截断（取后 2000 字节）无测试

- 严重度：minor
- 锚点：AC-001「日志包含 helper 输出摘要」
- 位置：`tests/unit/test_t055_supervisor_runtime_robustness.py:147-165`（`test_install_failure_logs_helper_output_redacted`）；生产侧 `src/backend/cbrowser/supervisor/docker_adapter.py:127-145`（`_helper_log_tail`）
- 问题：生产代码 `_helper_log_tail` 对 helper 输出取后 `_HELPER_LOG_TAIL_BYTES = 2000` 字节再脱敏，这是“摘要”二字的实现；但红action测试的 helper 日志只有约 50 字节（`b"iptables: rule rejected\ndebug: password=..."`），只验证了“有摘要且脱敏”，从未走过截断分支。截断逻辑若被改坏（例如取前 2000 字节、或忘记截断导致整段原始输出进日志），现有测试不会变红。
- 建议：补一例长输出（>2000 字节，前段含可识别标记、尾段含另一标记），断言日志含尾段标记、不含首段标记，且仍不含凭据。

## 结论

- 改测方向复核：无「迁就实现」的改测。三处删除均为整体删除 + 有后继测试覆盖新语义：`test_p058_browser_lookup.py` 删 `test_other_instance_is_a_fence_mismatch`（单字符串 `observed_instance_id == "other"`），后继为 `test_lookup_reports_single_foreign_instance_as_one_tuple`（元组形式）；`test_a36_socket_root.py` 删 `test_prepare_socket_dir_cleans_only_own_slot`，后继为 `test_prepare_socket_dir_cleans_stale_socket_and_leaves_other_slots`（陈旧清理 + 他槽文件保留）；删 `test_prepare_agent_socket_dir_rejects_overlong_explicit_root`，后继为 `test_path_validator_construction_rejects_overlong_socket_root`（超长根改为在 PathValidator 构造时即失败，失败点前移是 A12 语义本身）。`test_resolve_socket_root_env_override` 由 `tmp_path` 改用 `short_root` fixture，是为适应新增的长度校验而做的夹具调整，测试意图（env 覆盖生效）未变，不属弱化。
- 危险模式扫描：测试 diff 中零命中——无 `.skip` / `.only` / `assert True` / `# type: ignore` / 恒真断言 / 条件跳过弱化断言；mock 只出现在系统边界（fake Docker client、httpx MockTransport、monkeypatched `subprocess.run` 桩、fake websockets 上游），未 mock 被测逻辑本身；无删断言、无反转断言。
- 删除覆盖核对：3 个删除测试均有等价或更高层后继（见上），无覆盖静默丢失。
- Spike 复现：`.scratch/spike_close_code.py`（websockets 17.4）已独立重跑，三场景输出与 task.md 结论逐字一致：[1] 对端先关 4403，close 前读得 4403；[2] 本地先 close，close 后读得 1000（本地自发关码）；[3] 对端先关再本地 close，仍为 4403。读取点定在 `automation_router.py` finally 块内 `upstream.close()` 之前，与实验结论一致。
- A7 偏离说明（测试侧核实，非 finding）：实施未按审阅字面“两处一律保留 lost_at”，改用 `recovery_armed` 区分恢复宽限与过渡宽限。测试侧证实：t026 收敛测试全绿（见实跑），新测试覆盖新语义——恢复宽限在 gateway-unreachable 收敛后保留且 `lost_at` 不变、宽限内注册立即替换、宽限过期后替换。偏离有测试背书，属 code reviewer 的设计裁决范畴。
- 本轮新发现：4 条，全部 minor，无 blocking。
- 未进表的提示：`test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths` 在基线中已红（t051–t053 审阅报告含绝对路径）；本轮审阅报告按提示词模板同样含 `<home>/` 绝对路径，会进入该测试的违规集合，属已知的流程文件问题，不影响任务交付物。`test_automation_cdp.py::test_supervisor_cdp_websocket_forwards_to_agent_uds` 为基线既存失败（见回归比对），与本 task 无关。
- 总体判断：36 个新测试全部真实触达生产逻辑，10 条 AC 均有可信测试支撑；4 条 minor 均为覆盖精度缺口（标签错位、顺序未钉住、边界值未钉住、截断分支未覆盖），不阻断。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。helper remove 失败仍返回原 exit 码（0→True、4→False）与安装失败日志含 helper 输出且脱敏，两测试已独立重跑通过；截断分支未覆盖见 minor f004。
- AC-002：TICK-VALID，re_verified。`test_forget_instance_events_removes_only_matching_instance` 证实只删命名实例的 native-exit 记录、新实例记录与他 Profile 记录保留，已独立重跑通过。
- AC-003：TICK-VALID，re_verified。gateway 解析失败转 `MEDIA_ATTACH_GATEWAY_MISSING` 状态、离线恢复消费返回值并 60s 限频记日志，两测试已独立重跑通过；收敛路径写入 transport 观测（`last_error="gateway_missing"`）由既存 `test_t026_supervisor_convergence.py::test_gateway_missing_aborts_replacement_before_teardown` 与 `test_t049_supervisor_restore.py` 相关断言覆盖且仍通过。
- AC-004：TICK-VALID，re_verified。恢复预置 `starting` 且不向 API 报 `running`、健康确认后升级为 `running`、CDP 代理对 `starting` 会话以 4404 拒绝，三测试均经真实 websocket 链路、已独立重跑通过。
- AC-005：TICK-VALID，re_verified。恢复宽限在 gateway-unreachable 收敛后保留（`lost_at` 不变）、宽限内 defer、过期后替换、宽限内注册立即替换，四测试已独立重跑通过；90s 边界值本身未钉住见 minor f003。
- AC-006：TICK-VALID，re_verified。多异实例全部上报（元组顺序一致）、单异实例元组形式、非 NotFound 异常记日志、调用方级 mismatch 无观测 / 缺失报终态，五测试已独立重跑通过。
- AC-007：TICK-VALID，re_verified。客户端先断开不透传 4403、对端 4403 透传给客户端、`upstream.close()` 抛错仍送达关码，三测试经真实客户端 websocket 链路、已独立重跑通过；读码顺序未钉住见 minor f002。
- AC-008：TICK-VALID，re_verified。空 mux env 用默认值 30000–30991、自定义范围原样到达 PortAllocator、倒置与非整数值启动即失败，四测试经 `run_supervisor` 真实启动路径、已独立重跑通过；各消费者共用单一来源已由 grep 核实（protocol、network_policy、container_spec、docker_adapter、runner、stream_agent 均 import `udp_mux_bounds`）。
- AC-009：TICK-VALID，re_verified。陈旧 socket 清理、live/他 uid/非 socket/symlink 均报冲突且原样保留、超长根在 `resolve_socket_root` 与 `PathValidator` 构造时拒绝，八测试已独立重跑通过。
- AC-010：TICK-VALID，re_verified。停机竞态关流且不 pump、正常 pump 至 stop、两 watcher 各自只关自己的流，三测试直接调用生产 watcher 函数、已独立重跑通过。

coverage = 10/10

## 实跑（只报实数）

- 新 t055 测试 5 文件：36 passed（验证 venv，`PYTHONPATH=src/backend:tests`）。
- 新测试 + 受改动文件（p058、a36）+ t026/t049/a16/t045/automation_cdp 相关批：65 passed，唯一失败为基线既存 `test_supervisor_cdp_websocket_forwards_to_agent_uds`。
- 后端全量（`tests/unit` + `tests/integration`，自跑，533.07s）：2070 passed / 25 failed / 8 skipped / 0 errors；25 个失败与 t054 基线逐名完全一致（agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1），零新增失败；实施方首轮多出的 3 个失败（t045 wheel 缓存 2 个、a16 1 个）已复绿——`.scratch/selkies_wheels/selkies-2.2.1-py3-none-any.whl` 已在位，`test_t045_selkies_wheel_cache.py` 与 `test_a16_protocol_drift.py` 均已独立重跑通过。
- 前端全量（Node 26.13.0，`src/frontend` 内 `npm test`）：538 passed / 0 failed。
- 命名锁死：`com.cbrowser.deployment-id` 全树零命中；`cbrowser-t005` 默认前缀未动（watcher 测试内显式使用）。

reviewed_scope: 9872aed1e2feba1b

verdict: PASS

## Round 2 (2026-11-12T00:06:03+08:00)

## Findings

本轮新发现：0 条。

### 前轮 finding 复核（t055_test_f001–f004 全部已消除，逐条实跑核实，不采信处置表自述）

- **t055_test_f001（minor，docstring AC 编号错位）——已消除**：4 个文件 docstring 逐项 grep 核对——CDP 三例现为 AC-007（`tests/integration/test_t055_cdp_close_code.py:127,144,160`）、UDP mux 四例 AC-008（`tests/unit/test_t055_udp_mux_single_source.py:66,89,112,132`）、socket slot 八例 AC-009（`tests/unit/test_t055_socket_slot_cleanup.py:50,67,90,102,114,127,143,151,160`）、watcher 两例 AC-010（`tests/unit/test_t055_runner_watchers.py:65,135`）；17 例主文件标签未动且正确。`AC-011` 在 t055 文件中零命中（仅 t024 既有 e2e 文件引用其自有 AC-011，与本 task 无关）。
- **t055_test_f002（minor，CDP fake 不模拟 close_code 变化）——已消除**：`_FakeUpstream.close()`（`tests/integration/test_t055_cdp_close_code.py:71-77`）现改写 `close_code` 为 1000；生产侧读码仍在 `upstream.close()` 之前（`src/backend/cbrowser/api/v1/automation_router.py:242-244` 读码，`:254` close）。独立先红探针：临时把生产读码移到 `upstream.close()` 之后，`test_peer_close_code_is_propagated_to_client` 变红（exit 1）；恢复后 sha256 校验与探针前字节一致、复绿。偏离评估：fake 有意严于真实 websockets（spike 场景 3：对端 4403 在本地 close 后仍保留，fake 则改写为 1000），docstring（`:33-44`）已如实写明“fake 强制读码顺序”。该严格化只会让顺序写错的测试更易变红，不会掩盖真实行为；AC-007 明文要求“在本地 close 之前读取”，按规范读码的实现不受影响，不进 finding。
- **t055_test_f003（minor，90s 宽限边界未钉住）——已消除**：新增两例 `test_restore_grace_boundary_89s_still_defers`（`tests/unit/test_t055_supervisor_runtime_robustness.py:690`，`lost_at = now-89` 仍 defer）与 `test_restore_grace_boundary_91s_triggers_replacement`（`:713`，`now-91` 触发替换），边界语义为严格小于 90.0s（`core.py:419`，`now - lost_at < _REGISTRATION_LOSS_GRACE_SEC`，常量 `_REGISTRATION_LOSS_GRACE_SEC = 90.0`，`core.py:361`），各留 1s 余量。独立先红探针：常量改为 60.0 时 89s 例变红、改为 120.0 时 91s 例变红；恢复 90.0 后 sha256 校验字节一致、复绿。
- **t055_test_f004（minor，helper 日志截断无测试）——已消除**：新增 `test_install_failure_logs_only_helper_output_tail`（`tests/unit/test_t055_supervisor_runtime_robustness.py:167`）：首段标记 + 3000 字节填充 + 尾段标记 + 真实 SECRET（`SECRET.encode()` 拼接，文件本义经 muse.read 确认，非字面量 `<redacted>`），断言日志含尾段标记、不含首段标记、仍不含凭据。独立先红探针：截断改为取前 2000 字节（`raw[:_HELPER_LOG_TAIL_BYTES:]`）后该测试变红；去掉 `redact()` 后该测试与 `test_install_failure_logs_helper_output_redacted` 同时变红；恢复后 sha256 校验字节一致、复绿。脱敏断言真实可判别，非空转。
- **Round 1 代码 finding 的测试侧**：`t055_code_f001` 的竞态测试 `test_prepare_socket_dir_tolerates_entry_vanishing_between_exists_and_stat`（`tests/unit/test_t055_socket_slot_cleanup.py:64`）在受影响批内通过；其以 monkeypatch `Path.exists` 在检查成功后真实删除条目的方式模拟竞态，触达生产逻辑，非 mock 被测逻辑。

## 结论

- 前轮 finding 复核：f001–f004 全部已消除（见上，逐条独立先红探针 + sha256 字节还原校验）。
- 改测方向复核：本轮修复只改 4 个测试文件 docstring、fake 的 `close()` 语义、新增 4 例测试（宽限边界 2、截断 1、竞态 1），无既有断言改动、无“迁就实现”的改测。危险模式扫描：测试 diff 零命中——无 `.skip` / `.only` / `assert True` / `# type: ignore` / 恒真断言 / 条件跳过弱化断言；monkeypatch 只出现在系统边界（`Path.exists` 竞态模拟、`subprocess.run` 桩、fake websockets 上游），未 mock 被测逻辑本身。
- 本轮新发现：0 条。
- 未进表的提示：`test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths` 在基线中已红（t051–t054 审阅报告含绝对路径）；本轮审阅报告按提示词模板同样含 `<home>/` 绝对路径，会进入该测试的违规集合，属已知的流程文件问题，不影响任务交付物。f002 的 fake 严格化已评估成立（见复核），不进 finding。
- 总体判断：Round 1 的 4 条 minor 全部真实消除，新测试均可判别；10 条 AC 均有可信测试支撑，无 blocking。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。helper remove 失败仍返回原 exit 码、安装失败日志含 helper 输出且脱敏、>2000 字节输出只留尾段且脱敏，三测试已独立重跑通过；截断分支的先红探针（取前 2000 字节变红、去脱敏变红）已独立执行。
- AC-002：TICK-VALID，re_verified。`test_forget_instance_events_removes_only_matching_instance` 证实只删命名实例的 native-exit 记录、新实例记录与他 Profile 记录保留，已独立重跑通过。
- AC-003：TICK-VALID，re_verified。gateway 解析失败转 `MEDIA_ATTACH_GATEWAY_MISSING` 状态、离线恢复消费返回值并 60s 限频记日志，两测试已独立重跑通过；收敛路径写入 transport 观测（`last_error="gateway_missing"`）由既存 t026/t049 相关断言覆盖且仍通过。
- AC-004：TICK-VALID，re_verified。恢复预置 `starting` 且不向 API 报 `running`、健康确认后升级为 `running`、CDP 代理对 `starting` 会话以 4404 拒绝，三测试均经真实 websocket 链路、已独立重跑通过。
- AC-005：TICK-VALID，re_verified。恢复宽限在 gateway-unreachable 收敛后保留（`lost_at` 不变）、宽限内 defer、过期后替换、宽限内注册立即替换，四测试已独立重跑通过；90s 边界现由 89s/91s 两例钉住，常量 60/120 探针均变红。
- AC-006：TICK-VALID，re_verified。多异实例全部上报（元组顺序一致）、单异实例元组形式、非 NotFound 异常记日志、调用方级 mismatch 无观测 / 缺失报终态，五测试已独立重跑通过。
- AC-007：TICK-VALID，re_verified。客户端先断开不透传 4403、对端 4403 透传给客户端、`upstream.close()` 抛错仍送达关码，三测试经真实客户端 websocket 链路、已独立重跑通过；读码顺序现由 fake 的 1000 改写钉住，顺序对调探针变红。
- AC-008：TICK-VALID，re_verified。空 mux env 用默认值 30000–30991、自定义范围原样到达 PortAllocator、倒置与非整数值启动即失败，四测试经 `run_supervisor` 真实启动路径、已独立重跑通过；docstring 编号已修正为 AC-008。
- AC-009：TICK-VALID，re_verified。陈旧 socket 清理、live/他 uid/非 socket/symlink 均报冲突且原样保留、超长根在 `resolve_socket_root` 与 `PathValidator` 构造时拒绝、exists/stat 间条目消失视为已清理，九测试已独立重跑通过；docstring 编号已修正为 AC-009。
- AC-010：TICK-VALID，re_verified。停机竞态关流且不 pump、正常 pump 至 stop、两 watcher 各自只关自己的流，三测试直接调用生产 watcher 函数、已独立重跑通过；docstring 编号已修正为 AC-010（原 AC-011 不存在）。

coverage = 10/10

## 实跑（只报实数）

- 新 t055 测试 5 文件 + 受改动文件（a36、p058）：69 passed（验证 venv，`PYTHONPATH=src/backend:tests`）。
- 先红探针 5 组全部按预期变红、恢复后 sha256 字节一致：f002 顺序对调 1 failed；f003 常量 60→89s 例 1 failed、常量 120→91s 例 1 failed；f004 取前 2000 字节 1 failed、去脱敏 2 failed。
- 后端全量（`tests/unit` + `tests/integration`，自跑，528.10s）：2074 passed / 25 failed / 8 skipped / 0 errors；25 个失败逐名与 t054 基线分组完全一致（agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1），零新增失败，零 t055 相关失败。
- 前端全量（Node 26.13.0，`src/frontend` 内 `npm test`）：74 文件、538 passed / 0 failed。
- 命名锁死：`com.cbrowser.deployment-id` 全树零命中；`cbrowser-t005` 默认前缀未动。
- 自有探针与 basetemp 已清理（/tmp 44%）；未改任何实现、未提交。

reviewed_scope: 1ea2d3c9a8a562b0

verdict: PASS

## Round 3 (2026-11-12T00:42:28+08:00)

## Findings

本轮新发现：0 条。

### 前轮 finding 复核（t055_code_f002 的测试侧已消除；Round 1/2 finding 仍消除）

- **t055_code_f002（minor，`managed_socket_target` 的 `os.lstat()` 未防 slot 目录竞态消失）——已消除（测试侧）**：新增 `test_managed_socket_target_tolerates_directory_vanishing_between_open_and_lstat`（`tests/unit/test_t055_socket_slot_cleanup.py:163`），逐项独立核实，不采信处置表自述：
  - (a) 测试真实非空转：10 例单测文件全绿；先红探针——临时去掉 `socket_root.py` 的 try/except guard 后该测试变红（`FileNotFoundError`，`test_t055_socket_slot_cleanup.py:188`）；恢复后 sha256 校验与修复前字节一致（`80727d07…`，与修复方自述的哈希一致）、复绿。
  - (b) 桩精确：独立探针记录 `managed_socket_target` 执行期间的全部 `os.lstat` 调用——全路径内仅一次，且恰为目录路径；桩的触发条件（`os.fspath(path) == str(directory)`）与该唯一调用逐字匹配，其余路径委托真实 `lstat` 的分支在该路径内不被触及、未偷走被测行为。
  - (c) 回落值与 open 失败路径逐字一致：两处均为 `yield str(sock)`（`socket_root.py` open ENOENT/ENOTDIR 分支与 lstat guard 分支）；断言 `target == str(sock)` 匹配生产回落值。另以成功路径探针证实断言可判别：无竞态时目标为 `/proc/self/fd/3/agent.sock`（≠ `str(sock)`），即测试区分回落与成功，不是恒真。
  - (d) docstring 选择一致：新测试 docstring 只标 A12 并明言“socket_root read path, not the AC-009 slot-cleanup path”，未给自己编 AC 号；与 Round 2 code 审阅“f002 不在 AC-009 的 slot 清理路径上（属 CDP/健康查询读路径）”的结论一致，未重蹈 t055_test_f001 的编号错位。
  - 调用方语义已核实：两处真实调用方均把非 socket 目标当不存在处理——`control_server.py:510`（`is_socket()` 为假即 `websocket.close(code=1011)` 返回）、`core.py:2051`（`is_socket()` 为假即 `yield None` 返回）；`path_validator.py` 仅 import 未调用，回落不影响回退判定（`validate_socket_deployment` 不调 `os.lstat`）。
- **Round 1/2 finding 仍消除**：受影响批 70 passed（5 个 t055 测试文件 + a36/p058）包含 f001–f004 与 code f001 的全部测试——竞态测试、CDP 读码顺序测试、89s/91s 宽限边界测试、>2000 字节截断测试均通过；本轮改动只涉 `socket_root.py` 的 lstat guard 与 1 个新测试，未触其他测试文件。

## 结论

- 前轮 finding 复核：t055_code_f002 已消除（见上）；Round 1/2 的 5 条 minor 仍消除。
- 改测方向复核：本轮修复只改生产 guard 一处 + 新增 1 例测试，无既有断言改动、无“迁就实现”的改测。危险模式扫描：测试 diff 零命中——无 `.skip` / `.only` / `assert True` / `# type: ignore` / 恒真断言 / 条件跳过弱化断言；monkeypatch 只出现在系统边界（`os.lstat` 桩，且委托真实实现），未 mock 被测逻辑本身。
- 本轮新发现：0 条。
- 未进表的提示：`test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths` 在基线中已红；本轮审阅报告按提示词模板同样含 `<home>/` 绝对路径，会进入该测试的违规集合，属已知的流程文件问题，不影响任务交付物。AC-001 超时分支边界（`helper.wait(timeout=30)` 超时/传输错误时只报异常类型名、不抓 helper 日志）已在生产代码注释中说明意图（`docker_adapter.py:464-470`：wait 文本属传输层、可携带任意 URL，须保持脱敏），属有意边界，措辞收窄与否由 chain runner 裁决，progress.md 已记录，不进 finding。
- 总体判断：f002 修复真实可判别，10 条 AC 均有可信测试支撑，无 blocking。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。helper remove 失败仍返回原 exit 码、安装失败日志含 helper 输出且脱敏、>2000 字节输出只留尾段且脱敏，三测试已独立重跑通过；超时分支只报类型名的有意边界见未进表的提示。
- AC-002：TICK-VALID，re_verified。`test_forget_instance_events_removes_only_matching_instance` 证实只删命名实例的 native-exit 记录、新实例记录与他 Profile 记录保留，已独立重跑通过。
- AC-003：TICK-VALID，re_verified。gateway 解析失败转 `MEDIA_ATTACH_GATEWAY_MISSING` 状态、离线恢复消费返回值并 60s 限频记日志，两测试已独立重跑通过；收敛路径写入 transport 观测（`last_error="gateway_missing"`）由既存 t026/t049 相关断言覆盖且仍通过。
- AC-004：TICK-VALID，re_verified。恢复预置 `starting` 且不向 API 报 `running`、健康确认后升级为 `running`、CDP 代理对 `starting` 会话以 4404 拒绝，三测试均经真实 websocket 链路、已独立重跑通过。
- AC-005：TICK-VALID，re_verified。恢复宽限在 gateway-unreachable 收敛后保留（`lost_at` 不变）、宽限内 defer、过期后替换、宽限内注册立即替换，四测试已独立重跑通过；90s 边界由 89s/91s 两例钉住。
- AC-006：TICK-VALID，re_verified。多异实例全部上报（元组顺序一致）、单异实例元组形式、非 NotFound 异常记日志、调用方级 mismatch 无观测 / 缺失报终态，五测试已独立重跑通过。
- AC-007：TICK-VALID，re_verified。客户端先断开不透传 4403、对端 4403 透传给客户端、`upstream.close()` 抛错仍送达关码，三测试经真实客户端 websocket 链路、已独立重跑通过；读码顺序由 fake 的 1000 改写钉住。
- AC-008：TICK-VALID，re_verified。空 mux env 用默认值 30000–30991、自定义范围原样到达 PortAllocator、倒置与非整数值启动即失败，四测试经 `run_supervisor` 真实启动路径、已独立重跑通过。
- AC-009：TICK-VALID，re_verified。陈旧 socket 清理、live/他 uid/非 socket/symlink 均报冲突且原样保留、超长根在 `resolve_socket_root` 与 `PathValidator` 构造时拒绝、exists/stat 间条目消失视为已清理，九测试已独立重跑通过；slot 目录在 open/lstat 间消失回落普通 socket 路径（f002 新测试）已独立重跑并先红验证。
- AC-010：TICK-VALID，re_verified。停机竞态关流且不 pump、正常 pump 至 stop、两 watcher 各自只关自己的流，三测试直接调用生产 watcher 函数、已独立重跑通过。

coverage = 10/10

## 实跑（只报实数）

- 新测试文件 `test_t055_socket_slot_cleanup.py`：10 passed（验证 venv，`PYTHONPATH=src/backend:tests`）。
- 新 t055 测试 5 文件 + 受改动文件（a36、p058）：70 passed（验证 venv）。
- 先红探针：去掉 lstat guard 后新测试 1 failed（FileNotFoundError）；恢复后 sha256 与修复前字节一致（`80727d07…`）、复绿。成功路径探针：无竞态时目标为 `/proc/self/fd/3/agent.sock`（≠ `str(sock)`）；`os.lstat` 在该路径内仅调用一次且恰为目录路径。
- 后端全量（自跑，423.95s）：2075 passed / 25 failed / 8 skipped / 0 errors；25 个失败名与修复方全量日志逐名完全相同（agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1），零 t055 相关失败，零新增失败。
- 前端全量（Node 26.13.0，`src/frontend` 内 `npm test`）：74 文件、538 passed / 0 failed。
- 命名锁死：`com.cbrowser.deployment-id` 在代码/测试/compose/scripts 中零命中（仅 t051 历史叙述文档中出现）；默认前缀 `cbrowser-t005` 未动。
- 自有探针与 basetemp 已清理（/tmp 44%）；未改任何实现、未提交。

reviewed_scope: 408ae12d627ca219

verdict: PASS

## Round 4 (2026-11-12T01:24:38+08:00)

## Findings

### t055_test_f005 - 新抽出的 `_validate_slot_dir` 的 gid 不匹配分支零测试覆盖

- 严重度：minor
- 锚点：AC-009（关联：socket slot 目录校验；该分支属 CDP/健康查询读路径，不影响 AC-009 打勾成立）
- 位置：`src/backend/cbrowser/runtime_agent/socket_root.py:207-208`（`_validate_slot_dir` 的 gid 分支）；`tests/unit/test_a36_socket_root.py`、`tests/unit/test_t055_socket_slot_cleanup.py`（无对应测试）
- 问题：行覆盖探针（`sys.settrace`，与前轮审阅同款方法）证实：a36 + t055 socket 两文件 36 例跑完后，`_validate_slot_dir` 的 5 个 raise 分支中 dev/ino 不一致（`:200`）、mode 0o022（`:204`）、uid 不匹配（`:206`）均执行，gid 不匹配（`:208`）与 ISDIR（`:202`）从未执行。其中 gid 分支是真实缺口：全仓无任何测试向 `managed_socket_target` 传 `managed_gid`（grep 核实；a36 的 `test_managed_socket_target_rejects_owner_mismatch` 只传了 `managed_uid`），且 helper 在全仓仅一处调用（`socket_root.py:242`），无直接单测。ISDIR 分支经核实不是缺口：`os.open` 带 `O_DIRECTORY`，非目录时以 `ENOTDIR` 走 open 失败回落，`fstat` 的结果恒为目录，该 raise 通过公开路径不可达（重构前内联版同样不可达），不计入。gid 缺口在重构前即存在（base 版五分支内联、同样无 gid 测试），重构未丢失覆盖；但新 helper 是纯函数（两个 `stat_result` + uid/gid），直接单测成本极低，却未补。另如实说明：该分支当前在生产上也不可达——两处真实调用方（`control_server.py:510`、`core.py:2051`）均不传 `managed_gid`（`docker_adapter.py:1159` 只把它传给 `prepare_socket_dir`），故风险是潜在的而非现实的，定 minor、不阻断。
- 建议：给 `_validate_slot_dir` 补直接单测（`SimpleNamespace` 伪造 `stat_result` 即可）：gid 不匹配时 raise `SocketRootError`（match "group"），happy path 返回 None；ISDIR 分支无需补。

### 前轮 finding 复核（t055_code_f003 的测试侧已消除；Round 1/2/3 finding 仍消除）

- **t055_code_f003（minor，`managed_socket_target` 圈复杂度 17）——已消除（测试侧）**：圈复杂度用同一计数器（`.scratch/cc_counter.py`）独立复核：`managed_socket_target` **17 → 10**（base 版实测为 16，f002 guard +1 得 17，与 Round 3 报告一致），新 helper `_validate_slot_dir` 为 **8**，`prepare_socket_dir` 仍为 **12**（与 Round 2 报告逐字一致，证明计数口径相同）；五条 `SocketRootError` 文本与重构前逐字一致（diff 核对）。现有测试真实走过重构路径：行覆盖探针证实 a36 + t055 socket 两文件 36 例执行了 `_validate_slot_dir` 入口与调用点（`socket_root.py:242`），dev/ino、0o022、uid 三分支的 raise 行均被命中（见 f005 的探针结果）；受影响批 70 passed。f002 竞态测试仍可判别：临时去掉 lstat guard 后新测试变红（1 failed），还原后 sha256 与探针前字节一致（`a5ca0a4f…`，与修复方自述一致）、复绿。
- **Round 1/2/3 finding 仍消除**：受影响批 70 passed（5 个 t055 测试文件 + a36/p058）包含 f001–f004 与 code f001/f002 的全部测试——竞态测试、CDP 读码顺序测试、89s/91s 宽限边界测试、>2000 字节截断测试、lstat guard 测试均通过；本轮改动只涉 `socket_root.py` 的抽取重构与 progress.md，未触任何测试文件。

## 结论

- 前轮 finding 复核：t055_code_f003 已消除（见上）；Round 1/2/3 的 6 条 minor 仍消除。
- 改测方向复核：本轮修复只改生产重构一处（五处 if 改为一处 helper 调用）+ progress.md，未改任何测试文件，无既有断言改动、无“迁就实现”的改测。危险模式扫描：测试 diff 零命中——无 `.skip` / `.only` / `assert True` / `# type: ignore` / 恒真断言 / 条件跳过弱化断言；monkeypatch 只出现在系统边界（`Path.exists` 竞态模拟、`os.lstat` 桩、fake websockets 上游），未 mock 被测逻辑本身。
- 本轮新发现：1 条，minor（t055_test_f005，新 helper 的 gid 分支零覆盖）。
- 未进表的提示：`_validate_slot_dir` 的 ISDIR 分支通过公开路径不可达（`O_DIRECTORY` 保证），属既有防御性死代码，不计覆盖缺口；`test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths` 在基线中已红，本轮审阅报告按提示词模板同样含 `<home>/` 绝对路径，会进入该测试的违规集合，属已知的流程文件问题，不影响任务交付物；AC-001 超时分支只报异常类型名、不抓 helper 日志是有意边界（`docker_adapter.py:464-470` 注释说明意图），措辞收窄与否由 chain runner 裁决，progress.md 已记录。
- 总体判断：f003 重构真实降复杂度且行为未变，现有测试覆盖未丢失；仅 1 条 minor（新 helper 的 gid 分支零覆盖，当前生产亦不可达，属潜在风险），不阻断。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。helper remove 失败仍返回原 exit 码、安装失败日志含 helper 输出且脱敏、>2000 字节输出只留尾段且脱敏，三测试已独立重跑通过；本轮重构未触 docker_adapter.py。
- AC-002：TICK-VALID，re_verified。`test_forget_instance_events_removes_only_matching_instance` 证实只删命名实例的 native-exit 记录、新实例记录与他 Profile 记录保留，已独立重跑通过。
- AC-003：TICK-VALID，re_verified。gateway 解析失败转 `MEDIA_ATTACH_GATEWAY_MISSING` 状态、离线恢复消费返回值并 60s 限频记日志，两测试已独立重跑通过；收敛路径写入 transport 观测（`last_error="gateway_missing"`）由既存 t026/t049 相关断言覆盖且仍通过。
- AC-004：TICK-VALID，re_verified。恢复预置 `starting` 且不向 API 报 `running`、健康确认后升级为 `running`、CDP 代理对 `starting` 会话以 4404 拒绝，三测试均经真实 websocket 链路、已独立重跑通过。
- AC-005：TICK-VALID，re_verified。恢复宽限在 gateway-unreachable 收敛后保留（`lost_at` 不变）、宽限内 defer、过期后替换、宽限内注册立即替换，四测试已独立重跑通过；90s 边界由 89s/91s 两例钉住。
- AC-006：TICK-VALID，re_verified。多异实例全部上报（元组顺序一致）、单异实例元组形式、非 NotFound 异常记日志、调用方级 mismatch 无观测 / 缺失报终态，五测试已独立重跑通过。
- AC-007：TICK-VALID，re_verified。客户端先断开不透传 4403、对端 4403 透传给客户端、`upstream.close()` 抛错仍送达关码，三测试经真实客户端 websocket 链路、已独立重跑通过；读码顺序由 fake 的 1000 改写钉住。
- AC-008：TICK-VALID，re_verified。空 mux env 用默认值 30000–30991、自定义范围原样到达 PortAllocator、倒置与非整数值启动即失败，四测试经 `run_supervisor` 真实启动路径、已独立重跑通过。
- AC-009：TICK-VALID，re_verified。陈旧 socket 清理、live/他 uid/非 socket/symlink 均报冲突且原样保留、超长根在 `resolve_socket_root` 与 `PathValidator` 构造时拒绝、exists/stat 间条目消失视为已清理、slot 目录在 open/lstat 间消失回落普通 socket 路径，十测试已独立重跑通过；新 helper 的 gid 分支零覆盖见 minor f005（该分支属读路径、当前生产亦不可达，不影响 AC-009 打勾成立）。
- AC-010：TICK-VALID，re_verified。停机竞态关流且不 pump、正常 pump 至 stop、两 watcher 各自只关自己的流，三测试直接调用生产 watcher 函数、已独立重跑通过。

coverage = 10/10

## 实跑（只报实数）

- 新 t055 测试 5 文件 + 受改动文件（a36、p058）：70 passed（验证 venv，`PYTHONPATH=src/backend:tests`）。
- 行覆盖探针（`sys.settrace`，/tmp 一次性探针，已删）：a36 + t055 socket 两文件 36 例执行了 `_validate_slot_dir` 入口与 `socket_root.py:242` 调用点；dev/ino（:200）、0o022（:204）、uid（:206）三分支 raise 行命中，gid（:208）与 ISDIR（:202）未命中。
- 先红探针：去掉 lstat guard 后 f002 竞态测试 1 failed；恢复后 sha256 与修复前字节一致（`a5ca0a4f…`）、复绿。
- 圈复杂度（`.scratch/cc_counter.py`，与审阅同口径）：`managed_socket_target` 10（base 版 16、f002 guard 后 17）、`_validate_slot_dir` 8、`prepare_socket_dir` 12。
- 后端全量（自跑，536.31s）：**2075 passed / 25 failed / 8 skipped / 0 errors**；25 个失败与修复方 R3 日志 `FAILED` 行逐名完全相同（agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1），零 t055 相关失败，零新增失败。修复方首轮全量曾出 2 个 `test_api_subprocess.py` teardown ERROR 的说法：该文件单跑 4 绿（自跑 34.49s），本轮全量 0 errors，定性为 flaky teardown 可信（t051 基线同类 2 errors）；R3 日志文件内只存第二轮结果，首轮 ERROR 行无法独立复核，已如实说明。
- 前端全量（Node 26.13.0，`src/frontend` 内 `npm test`）：74 文件、**538 passed / 0 failed**。
- 命名锁死：`com.cbrowser.deployment-id` 在 src/scripts/compose.yaml/config/tests 中零命中；默认前缀 `cbrowser-t005` 未动（`docker_adapter.py:254`）。
- 自有探针与 basetemp 已清理（/tmp 44%）；未改任何实现、未提交。

reviewed_scope: b05debcb03a5c46c

verdict: PASS

## Round 5 (2026-11-12T01:53:39+08:00)

## Findings

本轮新发现：0 条。

### 前轮 finding 复核（t055_test_f005 已真实消除，逐条独立实跑核实，不采信处置表自述）

- **t055_test_f005（minor，新 helper `_validate_slot_dir` 的 gid 不匹配分支零覆盖）——已消除**：
  - (a) 3 例新测试全绿：`tests/unit/test_t055_socket_slot_cleanup.py` 13 passed（10 既有 + 3 新增），`test_validate_slot_dir_accepts_matching_identity`（`:208`）、`test_validate_slot_dir_rejects_group_mismatch`（`:221`）、`test_validate_slot_dir_ignores_group_when_unmanaged`（`:234`）。
  - (b) 非空转先红探针：临时把 gid 检查中性化（`if managed_gid is not None and fd_stat.st_gid != managed_gid:` → `if False:`），恰好 1 例变红（`test_validate_slot_dir_rejects_group_mismatch`，1 failed / 12 passed），其余两例仍绿（符合预期——它们不依赖 raise）；恢复后 sha256 与探针前字节一致（`a5ca0a4f…`，与修复方自述一致）、复绿。
  - (c) 行覆盖探针（`sys.settrace`，与 Round 4 审阅同款方法）：3 例执行时 gid raise 行 `socket_root.py:208` 被命中——`test_validate_slot_dir_rejects_group_mismatch` 走到 `[199, 201, 203, 205, 207, 208]`；happy path 与 unmanaged 例走到 `[199, 201, 203, 205, 207]`（五处条件行均求值、无 raise）。R4 的零覆盖缺口已闭合。
  - (d) 伪造 `stat_result` 忠实：helper 只读 `fd_stat` 的 `st_dev/st_ino/st_mode/st_uid/st_gid` 与 `path_stat` 的 `st_dev/st_ino`，`_slot_stat` 的 `SimpleNamespace` 恰好提供这五个属性；happy path 的 `mode=0o40755` 满足 `S_ISDIR` 且 `0o755 & 0o022 == 0`，dev/ino 一致、uid/gid 均匹配，五处条件行在通过方向上均被执行。`match="group"` 可判别：gid 测试的 mode 已通过 0o022 检查，唯一 raise 是 gid 分支（消息 `"Socket slot directory group mismatch"`）；unmanaged 例则钉住 `managed_gid is None` 短路（若无守卫直接比较 `2000 != None` 即 raise，该例变红）。
  - (e) 直接单测与公开路径覆盖互补、无矛盾：dev/ino（`:200`）、0o022（`:204`）、uid（`:206`）三分支 raise 行仍由 `managed_socket_target` 公开路径命中（Round 4 已证实，本轮受影响批重跑一致）；gid 分支现由直接单测覆盖；happy path 与 unmanaged 例只断言 helper 自身契约（返回 None / 不校验组），未改动任何既有断言。ISDIR 分支（`:202`）未补是正确的——`os.open` 带 `O_DIRECTORY`，非目录以 `ENOTDIR` 走回落，`fstat` 结果恒为目录，该 raise 经公开路径不可达（Round 4 已核实）。
- **Round 1–4 finding 仍消除**：受影响批 73 passed（5 个 t055 测试文件 44 例 + a36/p058 相关批 29 例），包含 f001–f004 与 code f001/f002/f003 的全部测试——docstring 编号、CDP 读码顺序、89s/91s 宽限边界、>2000 字节截断、exists/stat 竞态、open/lstat 竞态、CC 拆分后 helper 路径均通过；本轮改动只涉 `tests/unit/test_t055_socket_slot_cleanup.py` 末尾 3 例新测试与 progress.md，未触任何其他测试文件（mtime 核实：R4 审阅后仅该测试文件被改动）。生产代码零改动——`socket_root.py` 的 mtime 变化是我方先红探针恢复时 `cp` 回写所致，内容经 sha256 校验与探针前字节完全一致（`a5ca0a4f…`），无改动。

## 结论

- 前轮 finding 复核：t055_test_f005 已真实消除（见上，行覆盖探针 + 中性化先红探针 + sha256 字节还原校验）；Round 1–4 的 7 条 minor 仍消除。
- 改测方向复核：本轮修复只新增 3 例直接单测，未改任何生产代码、无既有断言改动、无“迁就实现”的改测。危险模式扫描：测试 diff 零命中——无 `.skip` / `.only` / `assert True` / `# type: ignore` / 恒真断言 / 条件跳过弱化断言；新测试未用 monkeypatch（`SimpleNamespace` 伪造的是 helper 的输入数据，helper 本体真实执行，未 mock 被测逻辑本身）。
- 本轮新发现：0 条。
- 未进表的提示：`test_repo_hygiene.py::test_tracked_files_do_not_leak_developer_home_paths` 在基线中已红；本轮审阅报告按提示词模板同样含 `<home>/` 绝对路径，会进入该测试的违规集合，属已知的流程文件问题，不影响任务交付物。AC-001 超时分支只报异常类型名、不抓 helper 日志是有意边界（`docker_adapter.py:464-470` 注释说明意图），措辞收窄与否由 chain runner 裁决，progress.md 已记录。
- 总体判断：f005 修复真实可判别（覆盖探针 + 中性化先红），10 条 AC 均有可信测试支撑，无 blocking；本轮为最后一轮（max_review_round=5），无遗留 finding。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。helper remove 失败仍返回原 exit 码、安装失败日志含 helper 输出且脱敏、>2000 字节输出只留尾段且脱敏，三测试已独立重跑通过；本轮未触 docker_adapter.py。
- AC-002：TICK-VALID，re_verified。`test_forget_instance_events_removes_only_matching_instance` 证实只删命名实例的 native-exit 记录、新实例记录与他 Profile 记录保留，已独立重跑通过。
- AC-003：TICK-VALID，re_verified。gateway 解析失败转 `MEDIA_ATTACH_GATEWAY_MISSING` 状态、离线恢复消费返回值并 60s 限频记日志，两测试已独立重跑通过；收敛路径写入 transport 观测（`last_error="gateway_missing"`）由既存 t026/t049 相关断言覆盖且仍通过。
- AC-004：TICK-VALID，re_verified。恢复预置 `starting` 且不向 API 报 `running`、健康确认后升级为 `running`、CDP 代理对 `starting` 会话以 4404 拒绝，三测试均经真实 websocket 链路、已独立重跑通过。
- AC-005：TICK-VALID，re_verified。恢复宽限在 gateway-unreachable 收敛后保留（`lost_at` 不变）、宽限内 defer、过期后替换、宽限内注册立即替换，四测试已独立重跑通过；90s 边界由 89s/91s 两例钉住。
- AC-006：TICK-VALID，re_verified。多异实例全部上报（元组顺序一致）、单异实例元组形式、非 NotFound 异常记日志、调用方级 mismatch 无观测 / 缺失报终态，五测试已独立重跑通过。
- AC-007：TICK-VALID，re_verified。客户端先断开不透传 4403、对端 4403 透传给客户端、`upstream.close()` 抛错仍送达关码，三测试经真实客户端 websocket 链路、已独立重跑通过；读码顺序由 fake 的 1000 改写钉住。
- AC-008：TICK-VALID，re_verified。空 mux env 用默认值 30000–30991、自定义范围原样到达 PortAllocator、倒置与非整数值启动即失败，四测试经 `run_supervisor` 真实启动路径、已独立重跑通过。
- AC-009：TICK-VALID，re_verified。陈旧 socket 清理、live/他 uid/非 socket/symlink 均报冲突且原样保留、超长根在 `resolve_socket_root` 与 `PathValidator` 构造时拒绝、exists/stat 间条目消失视为已清理、slot 目录在 open/lstat 间消失回落普通 socket 路径，十三测试已独立重跑通过；新 helper 的 gid 分支现由 3 例直接单测覆盖（行覆盖探针证实 `:208` 已执行、中性化先红探针变红）。
- AC-010：TICK-VALID，re_verified。停机竞态关流且不 pump、正常 pump 至 stop、两 watcher 各自只关自己的流，三测试直接调用生产 watcher 函数、已独立重跑通过。

coverage = 10/10

## 实跑（只报实数）

- 新测试文件 `test_t055_socket_slot_cleanup.py`：13 passed（10 既有 + 3 新增）。
- 新 t055 测试 5 文件 + 受改动文件（a36、p058）：73 passed（验证 venv，`PYTHONPATH=src/backend:tests`）。
- 行覆盖探针（`sys.settrace`，/tmp 一次性探针，已删）：gid 测试走到 `[199, 201, 203, 205, 207, 208]`，happy path 与 unmanaged 例走到 `[199, 201, 203, 205, 207]`。
- 中性化先红探针：gid 检查改为 `if False:` 后恰好 gid 测试 1 failed、其余 12 passed；恢复后 sha256 与探针前字节一致（`a5ca0a4f…`）、复绿。
- 后端全量（自跑，624.66s）：**2078 passed / 25 failed / 8 skipped / 0 errors**；25 个失败逐名与修复方 R4 日志完全相同（agent_executor_chain 7、t028 4、normal_exit_replay 4、automation_probe_chain 3、t034 2、automation_cdp_flow 2、repo_hygiene 1、automation_cdp 1、control_attendant_chain 1），零 t055 相关失败，零新增失败。
- 前端全量（Node 26.13.0，`src/frontend` 内 `npm test`，跑两遍取整份日志确认）：74 文件、**538 passed / 0 failed**。
- 命名锁死：`com.cbrowser.deployment-id` 在 src/scripts/compose.yaml/config/tests 中零命中；默认前缀 `cbrowser-t005` 未动；task.md 10/10 AC 已打勾、0 未打勾；`git status` 无未跟踪交付文件。
- 自有探针与 basetemp 已清理（/tmp 44%）；未改任何实现、未提交。

reviewed_scope: 5aa4d0669a575f9b

verdict: PASS
