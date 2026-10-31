# p012 同 tab 驱逐的关闭码偶发 1006

- 来源：t007 黑盒观察（`.scratch/lane_evidence` 外的黑盒 WT 日志 `stream_tokens_e2e.log`）
- 内容：`tests/e2e/test_stream_selkies_tokens_e2e.py::test_e2e_ac010_agent_controller_token_injection_and_coexistence` 首跑在“同 `client_tab_id` 新连接驱逐旧连接”处收到 `close_code=1006` 而非 Selkies 的 `4001`；单跑与整文件复跑均通过。疑为 Agent 隧道关闭旧 upstream 与 Selkies 发送关闭帧的竞态，导致页面侧只看到异常断开。需核实 Agent 在 upstream 收到 4001 时是否先转发关闭码再拆隧道，修复后去掉抖动。
- 处理：未开
