# p094 t064 合入后本地真实拓扑补验边缘授权与 CDP 边界

- 来源：t064 遗留
- 内容：t064 的云端执行环境无 Docker，AC-001、AC-002、AC-004（真实引擎部分）与 AC-006 只能完成代码、单元、集成、Caddyfile 渲染契约和 E2E collect-only，不能冒充真实部署已验。合入后须在本地 Mac 的隔离 Docker/Chrome 拓扑中运行 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`，至少实跑并留证：`tests/e2e/test_gateway_ac001_auth_e2e.py` 的真实 Caddy 边缘拒绝与 Cookie `Path=/`；合法 viewer 登录、首帧、重连、退出后新握手撤销；Agent register 独立认证回归；认证 automation 通道可用；`tests/e2e/test_browser_runtime_e2e.py::test_t064_cdp_loopback_host_origin_boundaries` 的合法回环正例、域名 Host 403 与跨 Origin CDP WebSocket 403。
- 处理：边缘授权链已补验通过；CDP host-origin 边界暴露产品缺陷，未闭环（须新建 task+spec）
- 时间：2026-11-14T19:07:00+08:00

## 本地补验证据（gate4）

- 已验：gate4 以 `CBROWSER_RUN_E2E=1` 在真实 Caddy+Docker+Chrome 拓扑跑完全量 E2E。`tests/e2e/test_gateway_ac001_auth_e2e.py` 整文件通过（真实 Caddy 边缘拒绝、Cookie `Path=/`、合法 viewer 登录/首帧/重连/退出后新握手撤销、Agent register 独立认证、认证 automation 通道可用）。`ee94faf` 修掉 `src/backend/cbrowser/network_config.py:97-101` 的 `forward_auth` 对 WS 升级子请求误传 `Upgrade`/`Connection`/`Sec-WebSocket-*`（无会话应 401 实测 403），仅改 Caddyfile 模板与快照单测，未动 `internal_edge.py`。
- 卡点：`tests/e2e/test_browser_runtime_e2e.py::test_t064_cdp_loopback_host_origin_boundaries` 单跑稳定失败 `assert 500 == 403`；域名 Host `/json/version` 与跨 Origin CDP WS 应 403，生产实测 500。根因：runtime_agent 仅设回环调试端口（`runner.py:613-614`），未实现 host-origin 校验 handler（契约 `docs/specs/access_control.md:41`、`docs/blueprint/testing.md:150`）；Caddy 不在 CDP 路径、Supervisor `cdp_proxy` 只覆盖 UDS、测试直连 TCP。测试期望正确、生产有 bug，禁止改断言凑绿。属新功能，须新建 task + 行为 AC（合法回环 Host 200 / 跨 Origin WS 403 且回环 Origin 101 / 畸形头不 500 / 端口不发布 / UDS 认证通道正例不受影响）。
