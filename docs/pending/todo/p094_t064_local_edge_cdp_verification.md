# p094 t064 合入后本地真实拓扑补验边缘授权与 CDP 边界

- 来源：t064 遗留
- 内容：t064 的云端执行环境无 Docker，AC-001、AC-002、AC-004（真实引擎部分）与 AC-006 只能完成代码、单元、集成、Caddyfile 渲染契约和 E2E collect-only，不能冒充真实部署已验。合入后须在本地 Mac 的隔离 Docker/Chrome 拓扑中运行 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`，至少实跑并留证：`tests/e2e/test_gateway_ac001_auth_e2e.py` 的真实 Caddy 边缘拒绝与 Cookie `Path=/`；合法 viewer 登录、首帧、重连、退出后新握手撤销；Agent register 独立认证回归；认证 automation 通道可用；`tests/e2e/test_browser_runtime_e2e.py::test_t064_cdp_loopback_host_origin_boundaries` 的合法回环正例、域名 Host 403 与跨 Origin CDP WebSocket 403。
- 处理：未开
