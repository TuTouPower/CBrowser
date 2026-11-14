# p099 CDP 回环端口缺 host-origin 校验，域名 Host / 跨 Origin WS 返 500 应 403

- 现象：`tests/e2e/test_browser_runtime_e2e.py::test_t064_cdp_loopback_host_origin_boundaries` 在 gate4 单跑稳定失败 `assert 500 == 403`；合法回环 Host `/json/version` 200 正常，但域名 Host（含带端口）与跨 Origin CDP WebSocket 未被拒绝，返回 500。
- 影响：CDP 数据面边界（t064 AC-001/AC-004）；契约 `docs/specs/access_control.md:41`、`docs/blueprint/testing.md:150` 要求 403。同类位点：gateway viewer WS 的 `forward_auth` 已在 `ee94faf` 修正（`src/backend/cbrowser/network_config.py:97-101`），但 CDP 路径不经 Caddy；Supervisor `cdp_proxy`（`control_server.py:526`）只覆盖 UDS；runtime_agent `runner.py:613-614` 仅设回环调试端口。已扫 `src/backend/cbrowser/` 无 host-origin 校验 handler。
- 根因：产品缺陷（缺功能）。引擎内建拒绝依赖未实现，异常落到 500。测试期望正确，禁止改断言凑绿。
- 测试缺口：云端无 Docker 时只能 collect-only，t064 合入后首次真实 E2E 才暴露；应补 runtime_agent 层 host-origin 校验单测 + E2E 正/负例（合法回环 Host 200、跨 Origin WS 403 且回环 Origin 101、畸形头不 500、端口不发布、UDS 认证通道正例不受影响）。
- 线索：`.scratch/local_verify_terminal_gate4/junit/e2e.xml`、`.scratch/terminal_e2e_qualify2.log`；p094 卡点段。
- 处理：未开（须新建 task + 行为 AC；本验证批次不内联实现产品功能）
