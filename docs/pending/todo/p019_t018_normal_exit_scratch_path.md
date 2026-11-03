# p019 normal_exit_replay 仍写仓库 .scratch

- 来源：t018 遗留（`t018_test_f021`）
- 内容：`tests/integration/test_normal_exit_replay.py` 为满足 API 事件收敛仍需仓库内短路径，四个用例继续写 `.scratch/normal_exit_fix`。改到 `/tmp` 后 `desired_state` 无法收敛，原因未定位。后续应定位路径依赖并把测试状态移出仓库写入域。
- 处理：未开
