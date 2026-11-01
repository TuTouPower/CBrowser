# p005 t006 评审遗留的 minor 问题（Gateway/Agent/测试）

- 来源：t006 遗留（t006_code_f001–f004、t006_test_f001，均 minor，Round 1 两路 PASS）
- 内容：
    - t006_code_f001：`gateway/config.py` 解析 `CBROWSER_ALLOWED_ORIGINS` 未像 `api/app.py` 那样去尾部 `/`，配置带尾斜杠时 Gateway 会以 403 拒绝合法 Origin。
    - t006_code_f002：轮换准备窗口期新建连接已取得新代配置，却未计入 `migrated_connections`，到期时被多做一次 ICE restart。
    - t006_code_f003：`StreamAgent.connect_and_run` 断开 Gateway 时未取消 `_restart_tasks` 中等待提交的任务（最长 20 秒后自行结束，`stop()` 时才统一取消）。
    - t006_code_f004：`gateway/server.py::handle_agent_register` 圈复杂度约 38，宜把 tunnel/action 报文分发拆为独立函数。
    - t006_test_f001：四个 Supervisor E2E 文件内联重复的 coturn 测试容器启动代码，宜抽成共享夹具。
        t006 收尾时改动交付会使已完成的评审与黑盒失效，故遗留；t007 会改 Gateway/Agent 与前端会话链路，应在 t007 内先 RED 后 GREEN 处理 f001/f003，并按需处理其余项。
- 处理：review/adoption-refactor；resolution=resolved；reason=A25 完成结构性拆分：recovery tick 按 observe/classify/schedule 拆分；docker_adapter 提取 volume/network/container spec；stream_agent 提取 messaging；policy/router 提取纯函数；p005 的 f001/f002/f003 与复杂度项均已在 main 闭环。
