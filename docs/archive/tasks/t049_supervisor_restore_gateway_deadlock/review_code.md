# Task review t049（reviewer_focus: 代码）

- task：`t049_supervisor_restore_gateway_deadlock`
- spec：`docs/tasks/t049_supervisor_restore_gateway_deadlock/task.md`
- diff_anchor：`13e631695e93182cd1f190223e6a8b9759967e89`
- target：`git -C '/Users/karson/kar/code/CBrowser_t049' diff 13e631695e93182cd1f190223e6a8b9759967e89`
- round：2
- reviewed_at：2026-11-10T14:57:28+08:00

reviewed_scope: ef51a572d2463cb9

## Round 2 (2026-11-10T14:57:28+08:00)

### Findings

本轮无新增 finding（0 条）。

已逐视角扫描并确认无命中：实现正确性 / 并发时序 / 资源释放 / 安全 / 契约与类型 / 性能 / 架构与可维护性 / 健壮性与可观测 / 文档与规格一致性。

### 前轮 finding 复核

- Round 1 代码轴 0 finding（PASS，reviewed_scope `4da535198b7c1e99`），无待复核 blocker。
- `t049_test_f001`（t019 首帧预算 2s→5s）属测试轴 finding，已在 `review_test.md` Round 2 按用户授权撤回；代码轴不重复记。当前 diff 中该变更已同步长期 spec（`docs/specs/webrtc_remote_display.md:32` 记录 ≤5s、本机实测 3.4–3.7s、原 2s 不再满足）与 `docs/blueprint/testing.md:78`，host-only 候选断言未弱化，不构成代码轴缺陷。

### Round 2 增量改动复核

- `scripts/gate_container_cleanup.py:100-132`：`_list_containers` 只在 `docker.errors.NotFound` 或异常文本含 `404` / `No such container` 时重试（最多 3 次），其他异常原样抛出；3 次仍 churn 时抛 `LabelLookupError` 失败关闭。没有把「标签不可读」当作瞬时消失吞掉。
- `scripts/gate_container_cleanup.py:143-194`：`_list_container_labels` 对枚举中消失的单容器跳过，`collect_targets` 再用 `_live_missing_names` 复核「names 有、labels 无」的容器仍存活则报 `LabelLookupError`；归属校验未被削弱。
- `tests/e2e/test_supervisor_retry_e2e.py:569-600`：手写 60×0.25s 循环改为 `wait.poll_until(timeout=120.0, interval=0.25)`，判据仍是「runtime observed=running 且按 instance-id 找到 browser 容器」，失败仍以超时抛出，未放宽容差。
- `tests/e2e/test_supervisor_container_graph_e2e.py:90-98,191-199,245-249` 与 `tests/fixtures/gateway_probe/topology.py:211-215,257-261`：Supervisor/Gateway 使用同一 `CBROWSER_E2E_UDP_BASE` 推导的 mux 端口区间，补挂 `data/sockets`，与生产拓扑一致。
- `tests/fixtures/supervisor_recovery_probe/offline_fixture.py:513`、`tests/e2e/test_supervisor_container_graph_e2e.py:244` 补 `CHOWN` cap，`tests/unit/test_baseline_fixture_regressions.py:436` 同步期望；属夹具与真实容器安全选项对齐。
- 文档同步：`docs/blueprint/architecture.md:147`、`docs/blueprint/testing.md:145`、`docs/specs/runtime_lifecycle.md` 新增 t049 节与 `docs/specs_index.md:12` 均与实现一致。

### 未进表的提示

- 文件过大：`src/backend/cbrowser/supervisor/core.py` 3401 物理行（实现源码阈值 800，既有巨型文件，本 task 净增约 70 行）；`tests/fixtures/gateway_probe/topology.py` 794 行（测试源码阈值 600，本 task 净增约 165 行）。按降级规则仅提示，不进 finding 表。
- 复杂度：`_reconcile_profile` 仍为长函数（既有）；本 diff 把 `_converge_session` 的挂载分支收敛到 `_ensure_media_attachment`（`core.py:383-434`，近似 CC≈7），未新增高复杂度函数。
- AC-007 / AC-008 本轮未独立执行（按要求不运行测试或 Docker），仅审查代码与用例断言并依赖实施侧记录。
- 范围外观察：无新增范围外改动；t019 预算调整已由用户批准并写入长期 spec，不按偏航处理。

### 结论

- 前轮 finding 复核：Round 1 代码轴零 finding，无未解决 blocker。
- 本轮新发现：0 条。
- 未进表的提示：文件过大 2 处（`core.py` 3401 行、`topology.py` 794 行）；AC-007 / AC-008 未独立重跑。
- 总体判断：实现与 spec 一致，无未解决 critical / important，代码轴 PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。恢复路径 `core.py:1163-1173`（label 实例一致）、`1201-1209`（API fence）、`1413-1483`（policy_ready 宽限 → UDP mux 端口恢复 → `ActiveSession`）无 Gateway 可见性读数；`tests/unit/test_t049_supervisor_restore.py::test_restore_ignores_gateway_visibility_503` 用真实 `GatewayControlClient` 注入 503 后断言 session 与 `udp_mux_port == 30007`。
- AC-002：TICK-VALID，re_verified。`_ensure_media_attachment`（`core.py:383-434`）在同一轮内解析 Gateway、执行 `attach_profile_infrastructure` 并置 `transport_state="recovering"`（`core.py:427-433`），`_converge_session`（`core.py:470-472`）直接调用；`test_restore_attaches_gateway_in_same_pass` 断言 `attach:<GATEWAY>`、recovering、endpoint 与 `last_attached_at` 落值。
- AC-003：TICK-VALID，re_verified。Gateway 缺失走 `MEDIA_ATTACH_GATEWAY_MISSING` → `last_error="gateway_missing"`（`core.py:504-512`）；控制不可达走 `agent_registered() is None` → `last_error="gateway_unreachable"`（`core.py:608-616`）；两路径均不拆除容器，测试断言 `torn_down is False`。
- AC-004：TICK-VALID，re_verified。API 不可达时 `_reconcile_profile` 只调 `_recover_attachment_offline`（`core.py:1181-1192`），后者仅委派 `_ensure_media_attachment`（`core.py:843-864`），不建 session、不上报生命周期；`test_api_offline_recovery_attaches_without_session` 断言仅 `attach:<GATEWAY>` 且 `get_session is None`。
- AC-005：TICK-VALID，re_verified。`_ensure_media_attachment` 对 `not exists or not conforms` 直接返回 `MEDIA_ATTACH_DRIFT`（`core.py:409-410`），不执行 attach；`_converge_session` 按替换预算走 `_replace_stream_only(..., rebuild_network=True)`（`core.py:483-503`）；`test_nonconforming_media_network_replaces_stream_only` 断言 `rebuild_network` 先于 `attach` 并触发 `start_stream`。
- AC-006：TICK-VALID，re_verified。label 实例不一致在 `core.py:1166-1173` 直接返回，API fence 不一致在 `core.py:1202-1209` 直接返回，均在 `_converge_session` 之前；`test_label_instance_mismatch_is_not_restored` 与 `test_api_fence_mismatch_is_not_restored` 断言无 session 且 `adapter.calls == []`。
- AC-007：TICK-VALID，trust_prior。审查 `tests/e2e/test_supervisor_upgrade_recovery_e2e.py`：`UpgradeTopologyHarness.rebuild_gateway_and_supervisor`（`tests/fixtures/gateway_probe/topology.py:338-365`）在 Profile 运行中重建两容器，Supervisor 改传稳定容器名并由 label 解析新 Gateway；用例以 300s 轮询 readiness、断言诊断不含三类死锁名、重建后新 headless viewer `framesDecoded > 0`。本轮未重跑，依赖 `progress.md` 记录的 103s 通过结果。
- AC-008：TICK-VALID，trust_prior。用户 2026-11-10 批准豁免：unit/integration/frontend/build 已分别稳定全绿；E2E 在宿主被其他会话压到 load 160–300 时单次随机 1–3 个超时用例，失败项每轮不同且单独复跑均通过，不要求一次完整全绿。依据 `task.md:47` 记录的豁免范围与 `progress.md` 的分套件证据，非假绿。

coverage = 6 / 8

verdict: PASS
