# Task review t049（reviewer_focus: 测试）

- task：`t049_supervisor_restore_gateway_deadlock`
- spec：`docs/tasks/t049_supervisor_restore_gateway_deadlock/task.md`
- diff_anchor：`13e631695e93182cd1f190223e6a8b9759967e89`
- target：`git -C '/Users/karson/kar/code/CBrowser_t049' diff 13e631695e93182cd1f190223e6a8b9759967e89`
- round：2
- reviewed_at：2026-11-10T14:56:20+08:00

reviewed_scope: ef51a572d2463cb9

## Round 2 (2026-11-10T14:56:20+08:00)

### Findings

本轮无新增 finding（0 条）。

### 前轮 finding 复核

- `t049_test_f001`（important，t019 首帧预算 2s→5s）：同意撤回，非换形式弱化。用户 2026-11-10 明确批准把 t019 首帧预算调整为 5s，并把新契约写入长期 spec：`docs/specs/webrtc_remote_display.md:32` 记录「切换/刷新到首帧 ≤5 秒」、本机 Mac/OrbStack + Chrome 156 基线镜像实测 3.4–3.7s、「原 2 秒预算不再满足」，同时保留 ICE host-only 与同机直连约束不变。`docs/blueprint/testing.md:78` 与用例名 `test_t019_switch_and_refresh_first_frame_within_5s_host_only` 已同步。候选集断言未动：`tests/e2e/test_frontend_app_e2e.py:1424,1440` 仅改 `<= 2.0` → `<= 5.0` 与命名/注释，`_assert_host_only_candidates`（host-only、远端恒为 `127.0.0.1`）保持原样。该变更有用户授权与 spec 记录支撑，属产品契约变更而非掩盖回归，撤回成立，不再阻断。

### 改测方向复核

本轮无「迁就当前实现」的改测。除上述用户批准的 t019 预算变更外，其余既有测试改动均为让测试夹具/等待策略与生产能力对齐，未削弱断言：

- `tests/fixtures/supervisor_recovery_probe/offline_fixture.py:513`、`tests/e2e/test_supervisor_container_graph_e2e.py:244` 的 Supervisor `cap_add` 补 `CHOWN`（root 下 `manage_ownership=True` chown socket 目录所需）；`tests/unit/test_baseline_fixture_regressions.py:436` 同步该期望值，属夹具安全选项与真实容器一致，不是删断言。
- `tests/e2e/test_supervisor_container_graph_e2e.py:90-98,191-199` 补挂 `data/sockets` 并给 Gateway 传与 Supervisor 相同的 `CBROWSER_UDP_MUX_MIN_PORT/MAX_PORT`，修正此前注册 `udp_port` 超出 Gateway 解析范围导致的 `invalid_payload`，属夹具与生产能力对齐。
- `tests/e2e/test_supervisor_retry_e2e.py:572-600` 把手写 60 次 sleep 轮询改为 `wait.poll_until(timeout=120.0, interval=0.25)`；仍是「等到 running 且按 instance-id 定位 browser 容器」的同一判据，原 `assert inst_4 is not None and b4_name is not None` 等价的失败仍会经 `poll_until` 超时抛出，只是把就绪语义收敛到统一工具，非放宽容差。
- `scripts/gate_container_cleanup.py` 的 `t049-` 前缀与 cleanup 重试属门禁清理健壮性，不是断言改动。

### 本轮新发现

0 条。

### 未进表的提示

- AC-007 本轮未独立重跑（按用户要求不运行测试/Docker），已审查 `tests/e2e/test_supervisor_upgrade_recovery_e2e.py` 的断言（`READINESS_TIMEOUT_SEC` 预算、`FORBIDDEN_DIAGNOSTICS` 不含三类死锁诊断、重建后新 viewer `framesDecoded > 0`），并依赖 `progress.md` 记录的 103s 通过结果。
- t019 host-only 候选集保护仍在，t049 未触碰；性能容量/P95 归后续性能任务，符合新 spec 表述。
- 范围外观察：无。

### 结论

- 前轮 finding 复核：`t049_test_f001` 已按用户授权撤回（依据 `docs/specs/webrtc_remote_display.md:32` 的 5s 新契约与实测样本、`docs/blueprint/testing.md:78` 与用例名同步），host-only 候选断言未弱化；无「修不彻底 / 换形式弱化」。
- 改测方向复核：无「迁就实现」的改测；其余夹具/轮询改动属测试与生产能力对齐。
- 本轮新发现：0 条。
- 未进表的提示：AC-007 未独立重跑，依赖实施侧记录与用例代码审查。
- 总体判断：无未解决 critical / important，`t049_test_f001` 已撤回，AC-001..008 全部 TICK-VALID，测试轴 PASS。
- 系统性 follow-up：无（未发现与 t049 等价的跨 task 测试基础设施缺口）。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。审查 `tests/unit/test_t049_supervisor_restore.py::test_restore_ignores_gateway_visibility_503`：经真实 `GatewayControlClient` + `httpx.MockTransport` 注入 503 后一次 `scan_and_reconcile_existing` 即建立 `ActiveSession`，断言 `runtime_instance_id`、`udp_mux_port == 30007`、browser/stream 容器 id 落值。
- AC-002：TICK-VALID，re_verified。审查 `test_restore_attaches_gateway_in_same_pass`：同一次扫描内出现 `attach:<GATEWAY>`，`transport_state == "recovering"`，`gateway_endpoint` 与 `last_attached_at` 均落值，不依赖下一轮对账。
- AC-003：TICK-VALID，re_verified。审查 `test_restore_without_gateway_keeps_session`（`last_error == "gateway_missing"`）与 `test_restore_with_unreachable_control_keeps_session`（`last_error == "gateway_unreachable"`）：session 仍建立、`torn_down is False`。
- AC-004：TICK-VALID，re_verified。审查 `test_api_offline_recovery_attaches_without_session`：API 全部不可达时 `adapter.calls == [attach:<GATEWAY>]`，`get_session is None`，transport 为 `recovering`，未建 session、未报生命周期。
- AC-005：TICK-VALID，re_verified。审查 `test_nonconforming_media_network_replaces_stream_only`：`conforms=False` 时 `rebuild_network` 先于 `attach:<GATEWAY>`，且触发 `start_stream`，未向不合规网络直接挂载。
- AC-006：TICK-VALID，re_verified。审查 `test_label_instance_mismatch_is_not_restored` 与 `test_api_fence_mismatch_is_not_restored`：两种不一致场景均 `get_session is None`，label 场景 `adapter.calls == []`。
- AC-007：TICK-VALID，trust_prior。审查 `tests/e2e/test_supervisor_upgrade_recovery_e2e.py::test_upgrade_of_running_profile_self_heals`：真实拓扑运行中 `rebuild_gateway_and_supervisor`，`_wait_profile_ready` 以 300s 预算轮询 readiness，断言诊断不含 `FORBIDDEN_DIAGNOSTICS`，重建后新 headless viewer `framesDecoded > 0`；本轮未重跑，依赖 `progress.md` 记录的 103s 通过结果。
- AC-008：TICK-VALID，trust_prior。用户 2026-11-10 批准豁免：unit/integration/frontend/build 已分别稳定全绿；E2E 在宿主被其他会话压到 load 160–300 时单次随机 1–3 个超时用例，失败项每轮不同且单独复跑均通过，不要求一次完整全绿。依据 `task.md:47` 记录的豁免范围与 `progress.md` 的分套件证据，非假绿。

coverage = 6 / 8

verdict: PASS
