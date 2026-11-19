---
pid: "p146"
slug: "gateway_restart_registration_grace"
status: "closed"
resolution: "transferred"
reason: "已核实 Gateway 瞬断/重启边界误清 known=True 会话恢复宽限的根因（gateway_missing 与 gateway_unreachable 两处同类位点），立项 t091 处理"
fix_ref: "t091"
---
# p146 Gateway 重启期间清除活跃会话注册状态导致健康 Stream 容器被误替换

- 现象：全量 Docker E2E（`main_integrated_gates_r2` 与 `r3`）中 [`tests/e2e/test_gateway_ac003_media_e2e.py`](tests/e2e/test_gateway_ac003_media_e2e.py) 在 `gw_box.kill(signal="KILL")` 后执行 `gw_box.restart()` 等待原 Stream 重注册时稳定在 `stream_box.logs()` 触发 `docker.errors.NotFound: No such container`；单独运行该用例（`task-1727`）及部分调度下可通过。
- 影响：所有在 Supervisor 保持运行期间发生 Gateway 瞬断、kill 或重建的活跃运行沙箱（真实生产栈与 Gateway 恢复 E2E）均受同一竞态影响。已扫 `src/backend/cbrowser/supervisor/core.py` 全文全部 `_registration` 清理位点，同类共两处：`gateway_missing`（825–827 行）与 `gateway_unreachable`（988–990 行）。
- 根因：并发生命周期边界语义缺陷。`runner.py` 将 `gateway` 容器生命周期事件作为 `scan_wakeup` 唤醒源，同时 [`core.py#L442-L449`](src/backend/cbrowser/supervisor/core.py#L442-L449) 与 `docs/specs/runtime_lifecycle.md` 第 71 行要求已注册 Stream 在 Gateway 重启后进入 `90s` 恢复宽限等待退避重连；但 `core.py:826` 与 `core.py:989` 在 `gateway_missing` / `gateway_unreachable` 分支仅保留 `state.recovery_armed=True`（Supervisor 重启路径设置），而将活体运行会话的 `state.known=True, state.recovery_armed=False` 一同 `self._registration.pop(profile_id, None)`。当 Gateway kill/restart 触发收敛扫描恰好命中时，`known=True` 被擦除；Gateway 拉起后 StreamAgent 尚在退避期内，下一次收敛读取 `agent_registered == False` 因 `previously_known=False` 跳过 90s 宽限并立即调用 `_replace_stream_only` 删毁健康 `stream_box`。
- 修复方向：抽取统一边界判定并保留 `known=True` 与 `recovery_armed=True` 会话在 `gateway_missing`/`gateway_unreachable` 期间的 `_registration` 恢复资格（仅清理 `not state.known and not state.recovery_armed` 的陈旧失活记录与停机 clean stop 路径）；同步消除 `docs/specs/runtime_lifecycle.md` 与 `docs/specs/gate_verification.md` 的文档矛盾及替换失效的 `t026` 旧单元测试。
- 测试缺口：既有 [`tests/unit/test_t026_supervisor_convergence.py#L425-L433`](tests/unit/test_t026_supervisor_convergence.py#L425-L433) 错误断言 `registered=True -> None` 会整条删除 `_registration`，且缺少「活跃 `known=True` 会话跨 `gateway_missing`/`gateway_unreachable` 重启保留 90s 恢复宽限、未再重连超时才替换、而陈旧 `known=False` 失活记录仍被清理」的单元测试覆盖两处位点；真实 E2E 在全量回归中受并发时序揭示该缺口。
- 线索：`.scratch/main_integrated_gates_r2/logs/e2e.log`、`.scratch/main_integrated_gates_r3/logs/e2e.log`。
- 处理：t091；resolution=transferred；reason=已核实 Gateway 瞬断/重启边界误清 known=True 会话恢复宽限的根因（gateway_missing 与 gateway_unreachable 两处同类位点），立项 t091 处理
