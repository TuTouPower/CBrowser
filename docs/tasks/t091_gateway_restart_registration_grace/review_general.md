# Task review t091（reviewer_focus: 通用）

- task：`t091_gateway_restart_registration_grace`
- spec：`docs/tasks/t091_gateway_restart_registration_grace/task.md`
- diff_anchor：`675c51ca4217adfa6a2cd190e7c05b0c6d69a3be`
- target：`git diff 675c51ca4217adfa6a2cd190e7c05b0c6d69a3be`
- round：1
- reviewed_at：2026-11-20T00:25:45+08:00

reviewed_scope: 7e4684e04a93b502

## Findings

本轮 0 条 finding（clean review）。已按全量视角正交体检并逐项确认无命中：规格合规与 AC 打勾复核、实现正确性、安全、契约·类型·Breaking、性能与资源、架构与可维护性、健壮性与可观测、测试可信与覆盖、文档/配置一致性。仅审查 diff 触及路径，未做全仓扫描。

## 结论

- 前轮 finding 复核：无（本轮为 Round 1）。
- 本轮新发现：0 条。
- 未进表的提示：无。
- 总体判断：`SupervisorCore` 在 `gateway_missing` / `gateway_unreachable` 两处边界统一改用 `_should_drop_registration_on_gateway_outage`（仅清理 `known=False and not recovery_armed` 的陈旧状态），保留活跃 `known=True` 与恢复会话的 90 秒宽限；删除的失效旧断言按 spec「风险与回退」要求整体替换为精确回归，单 `RegistrationState` 对象与四个清理位点不变量保持，未触达非范围路径。无未解决 critical / important。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。重跑 `test_t091_gateway_restart_grace.py` 的 `test_known_registration_survives_gateway_unreachable_and_enters_recovery_grace` 与 `test_known_registration_survives_gateway_missing_and_enters_recovery_grace` 均通过：两处边界后保留 `known=True` 不 pop，Gateway 复联首个 `registered=False` 读数进入 `last_error="registration_recovery_grace"` 且不触发 `start_stream`，宽限过期后照常 Stream-only 替换；对照 `src/backend/cbrowser/supervisor/core.py:834`、`core.py:998`、`core.py:1049-1058` 实现一致。
- AC-002：TICK-VALID，re_verified。重跑 `test_unconfirmed_registration_cleared_at_gateway_outage_boundaries`（`known=False and recovery_armed=False` 在两个边界均清除同一状态对象）、`test_t055_supervisor_runtime_robustness.py::test_restore_armed_grace_survives_gateway_unreachable`（`recovery_armed=True` 保留）、`test_t026_supervisor_convergence.py::test_nonfixable_rejection_never_replaces_stream`（immediate failed 契约）均通过；clean stop 清理点 `core.py:3528` 未改、仍无条件清除。
- AC-003：TICK-VALID，trust_prior。已独立重跑新增/更新单测（t091 + t026 + t055 共 51 passed）；全量门禁与真实 Docker E2E 未由 reviewer 重跑，依赖实施侧证据：`.scratch/t091_gate_r1/manifest.json` `all_passed=true` 且 11 suite 退出码全 0，`junit/e2e.xml` 108 tests / 0 fail / 0 error（skipped 2）且含 `tests.e2e.test_gateway_ac003_media_e2e::test_ac003_dual_chrome_media_inputs_and_gateway_recovery_v2`（41.349s，通过，覆盖 Gateway SIGKILL→backoff→restart→重注册→媒体恢复与 Browser PID 不变）；并核验 `CBROWSER_SUPERVISOR_TEST_IMAGE=sha256:625886a34b34b68b27fd37d51f1604c833d0198c90c43dd225c02c087e0dbc56` 本地存在且内嵌 `core.py` 含 3 处 `_should_drop_registration_on_gateway_outage`（非旧镜像）。

coverage = 2 / 3

建议合并前人工抽查 trust_prior 项（AC-003 的真实 Docker 全量 E2E）：本轮未重跑，依据实施侧门禁证据与镜像身份核验。

verdict: PASS
