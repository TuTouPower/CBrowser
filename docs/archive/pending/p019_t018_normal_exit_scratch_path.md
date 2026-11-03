# p019 normal_exit_replay 仍写仓库 .scratch

- 来源：t018 遗留（`t018_test_f021`）
- 内容：`tests/integration/test_normal_exit_replay.py` 为满足 API 事件收敛仍需仓库内短路径，四个用例继续写 `.scratch/normal_exit_fix`。改到 `/tmp` 后 `desired_state` 无法收敛，原因未定位。后续应定位路径依赖并把测试状态移出仓库写入域。
- 处理：resolution=resolved；reason=t024 定位 AF_UNIX sun_path 根因（d027）并改短临时根修复

## 历史分析记录

- 分析时间：2026-11-04T00:00:12+08:00。
- 闭环说明：t024 已定位 AF_UNIX sun_path 上限根因（d027_af_unix_sun_path_length_limit.md）并收敛，本条归档闭环。

参考：[测试源码](../../../tests/integration/test_normal_exit_replay.py)、[Supervisor UDS 健康查询](../../../src/backend/cbrowser/supervisor/core.py)、[t024](../../archive/tasks/t024_delivery_verification_evidence/task.md)。
