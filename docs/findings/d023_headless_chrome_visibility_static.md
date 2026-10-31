# d023 无头官方 Chrome 不因切标签或最小化改变页面可见性

- 来源：t006_v2_gateway_auth_rtc（用户要求测试不得弹出浏览器窗口后主控实测，2026-10-31）。
- 结论：Playwright 以 `channel="chrome"`、`headless=True` 启动本机 Google Chrome 156 时，`bring_to_front()` 切换标签与 CDP `Browser.setWindowBounds` 最小化均不改变 `document.visibilityState`（始终 visible，无 visibilitychange）；CDP 也无设置页面可见性的命令。以 `open -g` 后台启动有界面 Chrome 再经 CDP 连接，`bring_to_front()` 仍会把 Chrome 抢到前台。
- 证据：`.scratch/headless_probe/visibility_probe.py` 与 `bg_visibility_probe.py` 的输出（主控本地，未入库）；Chrome 156.0.8078.76 的 `/json/protocol` 中无可见性命令（仅 `Emulation.setFocusEmulationEnabled`、`Page.setWebLifecycleState`）。
- 影响：无头 E2E 验证页面可见性须在页面内覆盖 `document.visibilityState`/`hidden` 并派发 `visibilitychange`，由官方客户端自身逻辑发 STOP_VIDEO/START_VIDEO；“浏览器真实标签切换发出事件”只能在用户同意的时段做有界面实测（已有 d013/s005）。
- 现状：有效，限本机 Chrome 156 / Playwright 无头模式。
