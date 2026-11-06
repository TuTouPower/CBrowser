# p049 前端 E2E 文件内共享容器栈

- 来源：用户排队指令（t037 门禁 v1~v8 迭代观察）。
- 内容：`tests/e2e/test_frontend_app_e2e.py`、`test_frontend_session_e2e.py`、`test_frontend_media_e2e.py` 等前端真实栈 E2E 目前每个用例各自启动一套完整拓扑（`FrontendAppTopologyHarness`：Caddy + API + Supervisor + Gateway + Browser/Stream 容器与无头 Chrome）。这些文件在 t044 并行化后被标为 `serial`，串行阶段每个用例重复启停整套容器，是门禁主要耗时之一。要求改为**同一文件内共享一套容器栈**（module/session scope fixture），用例之间只重置状态（Profile 数据、runtime 状态、页面/标签、SSE 订阅），不重复起停容器；共享栈必须保证用例间状态隔离（每个用例独立 Profile id 或显式清理），不得引入跨用例污染。验收：串行阶段容器启停次数显著下降，且文件内全部用例通过、无状态串扰。
- 处理：待转入聚合 task 解决。
