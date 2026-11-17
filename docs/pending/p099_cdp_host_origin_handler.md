---
pid: "p099"
slug: "cdp_host_origin_handler"
status: "closed"
resolution: "resolved"
reason: "新增 cdp_guard.py 与 36 例单测/集成，重建 browser 镜像后 t064 边界 E2E 1 passed、gate5 全绿，原断言未改"
---
# p099 CDP 回环端口缺 host-origin 校验，域名 Host / 跨 Origin WS 返 500 应 403

- 现象：`tests/e2e/test_browser_runtime_e2e.py::test_t064_cdp_loopback_host_origin_boundaries` 在 gate4 单跑稳定失败 `assert 500 == 403`；合法回环 Host `/json/version` 200 正常，但域名 Host（含带端口）与跨 Origin CDP WebSocket 未被拒绝，返回 500。
- 影响：CDP 数据面边界（t064 AC-001/AC-004）；契约 `docs/specs/access_control.md:41`、`docs/blueprint/testing.md:150` 要求 403。同类位点：gateway viewer WS 的 `forward_auth` 已在 `ee94faf` 修正（`src/backend/cbrowser/network_config.py:97-101`），但 CDP 路径不经 Caddy；Supervisor `cdp_proxy`（`control_server.py:526`）只覆盖 UDS；runtime_agent `runner.py:613-614` 仅设回环调试端口。已扫 `src/backend/cbrowser/` 无 host-origin 校验 handler。
- 根因：产品缺陷（缺功能）。引擎内建拒绝依赖未实现，异常落到 500。测试期望正确，禁止改断言凑绿。
- 测试缺口：云端无 Docker 时只能 collect-only，t064 合入后首次真实 E2E 才暴露；应补 runtime_agent 层 host-origin 校验单测 + E2E 正/负例（合法回环 Host 200、跨 Origin WS 403 且回环 Origin 101、畸形头不 500、端口不发布、UDS 认证通道正例不受影响）。
- 线索：`.scratch/local_verify_terminal_gate4/junit/e2e.xml`、`.scratch/terminal_e2e_qualify2.log`；p094 卡点段。
- 处理：683aa10；resolution=resolved；reason=新增 cdp_guard.py 与 36 例单测/集成，重建 browser 镜像后 t064 边界 E2E 1 passed、gate5 全绿，原断言未改

## 终局补验证据（gate5，已修复）

- 用户批准后按开发铁律从根因实现（提交 `683aa10`）：新增 `src/backend/cbrowser/runtime_agent/cdp_guard.py`（374 行），Chrome DevTools 仅绑内部 `chrome_port`，守护独占对外 `cdp_port`（仅 127.0.0.1），HTTP 校验 Host、WS 升级校验 Origin，合法请求反代并改写 `webSocketDebuggerUrl`、WS 字节透传，非法/畸形一律 403 不泄漏版本；`runner.py` 负责启停守护并把 `health["details"]["cdp_port"]` 指向守护端口，未就绪不写 `runner_info`（fail-closed）；内部 UDS 认证通道与 runtime_agent 自身 CDP 客户端直连 Chrome、不经守护。
- 新增 `tests/unit/test_cdp_guard.py` 与 `tests/integration/test_cdp_guard_chain.py`（合计 36 例）：合法/非法 Host（大小写、带端口、IPv6、空、控制字符、多 Host）、合法/非法 Origin、畸形头不 500、WS 升级拒绝 403、`json/version`/`json/list` 改写、loopback 绑定、health 集成。
- 重建 browser 镜像（`4a9e1bfe`）后 `test_browser_runtime_e2e.py::test_t064_cdp_loopback_host_origin_boundaries` 单跑 `1 passed in 13.69s`；gate5（`.scratch/local_verify_terminal_gate5/`）`GATE_EXIT=0`、e2e 105 用例 0 failed、unit 2278、integration 209。原断言未改动。
