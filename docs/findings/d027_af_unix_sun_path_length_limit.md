# d027 AF_UNIX sun_path 长度上限决定 UDS bind 成败

- 来源：t024 执行期 spike（解 p019）
- 结论：`AF_UNIX` 的 `sun_path` 长度上限使「数据根路径长度」成为 Stream Agent 能否启动的硬条件：路径过长时 UDS bind 失败、Agent 静默不启动，Supervisor 健康探测无 socket，上层只表现为事件不收敛。
- 证据：t024 在本机实测三组：相对路径 89 字符 bind 成功；pytest `tmp_path` 下相对路径 151 字符 bind 报 `AF_UNIX path too long`；短临时根相对路径 91 字符 bind 成功。失败链：`_run_uds_server` 以相对 CWD 路径 bind `<data_root>/runtime/<profile-uuid>/agent.sock`，超限后 Agent 未启动、退出事件不收敛（`desired_state` 停 `running`、`last_exit_event_id=None`）。修复后 `tests/integration/test_normal_exit_replay.py` 以短临时根（`/tmp` 下 `mkdtemp`）运行，4 用例保留原收敛断言全过。
- 影响：任何以长路径数据根启动 Agent 的部署/测试都会静默失败；测试数据根必须使用短路径，生产数据根路径长度应在部署校验中受控。p019 据此关闭。
- 现状：有效
