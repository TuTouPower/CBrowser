# p016 恢复 Supervisor 网络隔离与 Stream 配额端到端覆盖

- 来源：t015 遗留（review_test f007）
- 内容：t015 删除 coturn 时一并移除了 `tests/e2e/test_supervisor_infrastructure_network_e2e.py`（Gateway 动态加入媒体网络、跨 Profile 网络负向隔离、运行容器附着时清理拒绝、未知端点清理拒绝、中途失败原子回滚）与 `tests/e2e/test_stream_runtime_e2e.py` 的 control_proof 块（Supervisor quota 下发、客户端不能越过 FPS cap、布局不变、motion/static 帧率切换、Stream CPU policy）。同时恢复 Agent 替换测试中删除的 close 1001、conn_id 差异、下行回复与 Viewer 存活断言（t015_test_f012/f013）。这些行为与 TURN 无关，应在无 coturn 直连拓扑下恢复为端到端测试；由 t018 测试体系整改时纳入。
- 处理：未开
