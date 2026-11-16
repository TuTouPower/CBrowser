# p094 t064 合入后本地真实拓扑补验边缘授权与 CDP 边界

- 来源：t064 遗留
- 内容：t064 的云端执行环境无 Docker，AC-001、AC-002、AC-004（真实引擎部分）与 AC-006 只能完成代码、单元、集成、Caddyfile 渲染契约和 E2E collect-only，不能冒充真实部署已验。合入后须在本地 Mac 的隔离 Docker/Chrome 拓扑中运行 `CBROWSER_RUN_E2E=1 scripts/run_gates.sh`，至少实跑并留证：`tests/e2e/test_gateway_ac001_auth_e2e.py` 的真实 Caddy 边缘拒绝与 Cookie `Path=/`；合法 viewer 登录、首帧、重连、退出后新握手撤销；Agent register 独立认证回归；认证 automation 通道可用；`tests/e2e/test_browser_runtime_e2e.py::test_t064_cdp_loopback_host_origin_boundaries` 的合法回环正例、域名 Host 403 与跨 Origin CDP WebSocket 403。
- 处理：683aa10；resolution=resolved；reason=gate5 全绿：CDP host-origin 守护已实现，t064 CDP 边界 E2E 与 gateway_ac001 边缘授权整文件在真实 Caddy+Docker+Chrome 拓扑实跑通过
- 时间：2026-11-14T22:36:00+08:00

## 终局补验证据（gate5 / 真实部署栈，最终结论；取代下方 gate4 阶段性记录）

- `src/backend/cbrowser/runtime_agent/cdp_guard.py`（提交 `683aa10`）新增 CDP 边界守护：Chrome DevTools 仅绑内部端口，守护独占对外 `cdp_port`（仅 127.0.0.1），HTTP 校验 Host、WS 升级校验 Origin，合法请求反代（含 `webSocketDebuggerUrl` 改写与 WS 字节透传），域名 Host / 跨 Origin / 畸形头一律 403 且不泄漏版本、不抛 500；内部 UDS 认证通道与 runtime_agent 自身 CDP 客户端不经守护、保持可用；守护未就绪不写 `runner_info`，fail-closed。
- `test_browser_runtime_e2e.py::test_t064_cdp_loopback_host_origin_boundaries` 用重建后的 browser 镜像（`4a9e1bfe`）单跑 `1 passed`；`test_gateway_ac001_auth_e2e.py` 整文件通过（真实 Caddy 边缘拒绝、Cookie `Path=/`、viewer 登录/首帧/重连/退出后撤销、Agent register）。`ee94faf` 修掉 `network_config.py:97-101` 的 `forward_auth` 对 WS 升级子请求误传 `Upgrade`/`Connection` 导致 403（应 401）。
- gate5（`.scratch/local_verify_terminal_gate5/`）`GATE_EXIT=0`，e2e 105 用例 0 failed / 2 skipped、unit 2278、integration 209、contract 258、real_engine 2 passed；新增 `tests/unit/test_cdp_guard.py`（36 例）与 `tests/integration/test_cdp_guard_chain.py` 全绿。本项要求的全部 [deploy]/E2E 切片已留证。

## 本地补验证据（gate4）

- 已验：gate4 以 `CBROWSER_RUN_E2E=1` 在真实 Caddy+Docker+Chrome 拓扑跑完全量 E2E。`tests/e2e/test_gateway_ac001_auth_e2e.py` 整文件通过（真实 Caddy 边缘拒绝、Cookie `Path=/`、合法 viewer 登录/首帧/重连/退出后新握手撤销、Agent register 独立认证、认证 automation 通道可用）。`ee94faf` 修掉 `src/backend/cbrowser/network_config.py:97-101` 的 `forward_auth` 对 WS 升级子请求误传 `Upgrade`/`Connection`/`Sec-WebSocket-*`（无会话应 401 实测 403），仅改 Caddyfile 模板与快照单测，未动 `internal_edge.py`。
- 卡点：`tests/e2e/test_browser_runtime_e2e.py::test_t064_cdp_loopback_host_origin_boundaries` 单跑稳定失败 `assert 500 == 403`；域名 Host `/json/version` 与跨 Origin CDP WS 应 403，生产实测 500。根因：runtime_agent 仅设回环调试端口（`runner.py:613-614`），未实现 host-origin 校验 handler（契约 `docs/specs/access_control.md:41`、`docs/blueprint/testing.md:150`）；Caddy 不在 CDP 路径、Supervisor `cdp_proxy` 只覆盖 UDS、测试直连 TCP。测试期望正确、生产有 bug，禁止改断言凑绿。属新功能，须新建 task + 行为 AC（合法回环 Host 200 / 跨 Origin WS 403 且回环 Origin 101 / 畸形头不 500 / 端口不发布 / UDS 认证通道正例不受影响）。

## 主线 ae02d42 本地复核（2026-11-16）

- 口径：按「按现状做本地复核」；gate5 真实 Caddy + Docker + Chrome 拓扑 E2E 属已验，不重复；基线 `main` @ `ae02d42`。
- 静态核对：`src/backend/cbrowser/runtime_agent/cdp_guard.py` 的 403 fail-closed（:24 / :159 / :228 / :329）与 Host / Origin 校验仍在；`src/backend/cbrowser/network_config.py:97` `forward_auth` 指令顺序仍在。
- 定向实测：`p094_cdp`（`tests/unit/test_cdp_guard.py` + `tests/integration/test_cdp_guard_chain.py`）→ `36 passed / EXIT=0`（collect-only 确认含 chain 的 `test_health_cdp_version_and_internal_ws_survive_guard` 1 例）；日志 `.scratch/p090_p098_reverify_20261116/logs/p094_cdp.log`。
- 结论：CDP 守护与集成链在当前主线仍成立；边缘授权与 CDP 边界的真实拓扑 E2E 属 gate5 已验，不重复；裁定闭环。
- 证据留存：gate5 / gate4 原始目录已缺失；汇总见 `docs/archive/verification/p090_p098_local_reverify_20261116.md`。
