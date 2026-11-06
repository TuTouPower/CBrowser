# p042 注册恢复宽限状态在生命周期清理点同步

- 来源：t032 review 遗留（`t032_code_f001`，minor）；`src/backend/cbrowser/supervisor/core.py` 新增 `_registration_lost_at` 与既有 `_registration_known` 是配套状态，仅在 `registered=True` 分支同步清理。
- 内容：`core.py` 的 `gateway_missing`、`gateway_unreachable`、clean stop、启动确认注册四处维护 `_registration_known` 时未同步 `_registration_lost_at.pop(profile_id, None)`。profile 停止后 90s 内以同名 `profile_id` 复建、且新 Stream 真实未注册时，残留旧时间戳会把"从未在本轮生命周期注册过"的新 profile 误判进恢复宽限，替换被最多再延迟约 90s。影响有界（过期必替换，有单测证明），不造成崩溃、数据丢失、资源泄漏或协议不兼容，故 t032 不阻断、不在本轮扩大交付范围。
- 处理：t044；resolution=transferred；reason=2026-11-06 于 main@8cdaeb7 核实问题仍存在，按用户决定并入 t044
