# Task spec

## 背景

`main` 全量 E2E 门禁揭示 `SupervisorCore._converge_session` 在处理 Gateway 容器缺失/不可达时存在既有竞态（p146）：`core.py` 一方面定义 90s `registration_recovery_grace` 以保护 Gateway 重启后处于退避重连中的健康 Stream（`docs/specs/runtime_lifecycle.md`），另一方面在 `gateway_missing`（825–827 行）与 `gateway_unreachable`（988–990 行）两个分支把 `known=True` 且 `recovery_armed=False` 的活跃会话 `_registration` 记录一并 `pop` 删除。一旦 Supervisor 在 Gateway 重启窗口触发扫描，`previously_known` 丢失，健康 Stream 会在退避期内被误删替换，导致 `test_gateway_ac003_media_e2e.py` 偶发 `404 No such container`。

## 契约区

### 范围

- 统一 `SupervisorCore` 在 `gateway_missing` 与 `gateway_unreachable` 边界的注册状态保留与清理策略，覆盖两处同类位点及对应单元测试。
- 按 TDD 替换失效的旧 `t026` 单元测试语义并保留/补充真实边界验证；同步更新 `docs/specs/runtime_lifecycle.md`、`docs/specs/gate_verification.md` 与 `docs/blueprint/supervisor.md`。
- 在新任务分支/worktree 验证并合入 `main` 后重建镜像执行全量 E2E 门禁。

### 非范围

- 不更改 Gateway 控制协议、StreamAgent 退避周期（`1/2/4/8/16/30s`）或 90s 恢复宽限时长常数值。
- 不修改 `t086`–`t090` 已交付内容，不触碰浏览器用户数据或 `p143`。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：当已确认注册（`known=True`）的活跃沙箱在 Supervisor 运行期间遭遇一次或多次 `gateway_missing` 或 `gateway_unreachable`，并在 Gateway 恢复后首个周期返回未注册读数时，Supervisor 保留其注册恢复资格、不将其清除为未注册新会话，且立即进入最多 90 秒的 `registration_recovery_grace`（`transport_state="recovering"`, `last_error="registration_recovery_grace"`），不在宽限期内替换健康 Stream；若宽限到期仍未注册，照常执行 Stream-only 替换。

- [ ] AC-002：若会话在遭遇 `gateway_missing` / `gateway_unreachable` 边界前已失去注册（`known=False` 且 `recovery_armed=False`）或 Profile 已正常停止清理，该边界与停机清理点仍清除陈旧 `RegistrationState`，不继承过期宽限；既有的 `recovery_armed=True` 恢复宽限保持与不可修复协议拒绝（immediate `failed`）契约保持不变。

- [ ] AC-003：新增与更新的 Supervisor 收敛单元测试及全部非 E2E 门禁通过；重建镜像后真实全量 Docker E2E 门禁（含 `tests/e2e/test_gateway_ac003_media_e2e.py`）全部通过。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。

## 上下文区

- 关联 spec：docs/specs/runtime_lifecycle.md, docs/specs/gate_verification.md
- 来源：p146（2026-11-19，全量 E2E 门禁 `r2` / `r3` 揭示与代码排查确认）

### 有意不测

- 不在单元测试中启动真实 Docker；真实 Docker Gateway SIGKILL/restart 与 StreamAgent 退避重连由 `tests/e2e/test_gateway_ac003_media_e2e.py` 与全量 E2E 门禁覆盖。

### 测试策略

- 先编写覆盖 `known=True` 经 `gateway_missing` 与 `gateway_unreachable` 边界后保持 `registration_recovery_grace` 的失败单测确认 RED。
- 在 `SupervisorCore` 修复两个边界条件后，重跑 `test_t026_supervisor_convergence.py`、`test_t055_supervisor_runtime_robustness.py` 与新增回归，并在重建 `supervisor` 镜像后跑全量 E2E 门禁验证 `test_gateway_ac003_media_e2e.py` 与完整套件通过。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无。`SupervisorCore` 状态转换与 E2E harness 均为仓库内部实现且已直接核验。

### 风险与回退

- 风险：原有 `test_t026_supervisor_convergence.py` 中 `test_registration_state_is_a_single_per_profile_object` 曾断言 `registered=True -> None` 会清空 `_registration`，按 `AGENTS.md` 需整体移除失效断言测试并替换为精确覆盖“已失活 `known=False` 边界清除 + `known=True` 边界保留”的测试，确保不影响同名重启动保护。
- 回退：通过标准 Git task 分支隔离实现与回归，未验收合入前主干保持不受影响。

### 依赖与约束

- 遵守 `test_four_lifecycle_cleanup_points_use_the_single_state_object` 的结构约束（保留单 `RegistrationState` 对象与四个清理调用位点）。
- E2E 验证须重建含最新 `supervisor` 代码的不可变镜像，不得复用旧镜像。

### Finalization 时更新的 blueprint

- `docs/blueprint/supervisor.md`：同步描述活跃 `known=True` 会话与 `recovery_armed=True` 会话在 Gateway 不可达/缺失边界保留恢复宽限、仅清理 `known=False` 陈旧记录的收敛语义。
