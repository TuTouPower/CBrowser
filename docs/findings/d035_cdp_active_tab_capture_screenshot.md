# d035 CDP 无活动标签字段，captureScreenshot 不改可见性/焦点/活动标签

- 来源：s016 spike（t040 UNVERIFIED-SPIKE，2026-11-07 真实 Chromium 146 引擎实测）
- 结论：CDP `Target.getTargets` 无 active/foreground 字段、`attached` 对全部 page 恒 True、顺序不稳定；`document.visibilityState` / `document.hidden` / `document.hasFocus()` 在 headless 与容器 Xvfb 下对全部标签恒为 `visible` / `false` / `True`，`bring_to_front()` 不改变这些信号。因此「当前活动标签页」无法从 CDP 或页面内状态读取，必须由产品自维护（Agent 记录 `Target.activateTarget` / `Page.bringToFront` 目标，或外部 Selkies 客户端上报焦点 `client_tab_id` 映射）。`Page.captureScreenshot` 对前台/后台 page target 均返回有效 JPEG，截图前后可见性、焦点、focus/blur/visibilitychange 事件与 `Target.getTargets` 均无变化，且截的是 page viewport 内容（不含标签栏/地址栏）。
- 证据：`docs/spikes/s016_cdp_active_tab_capture_probe/code/probe.py`、`probe_xvfb.py`、`run.sh`、`run_xvfb.sh`、`result_headless.json`、`result_xvfb.json`；产品 Browser Runtime 镜像 `sha256:1b75e318a2b7e6e0fdeba6d784773dd4848d2f91e7bba8650ded22d24c675513`（同 Chromium 146 引擎）容器内运行，headless 或容器 Xvfb 虚拟显示，未弹宿主窗口、未抢焦点。headless 4 组 + Xvfb 1 组 `Page.captureScreenshot`（含 `captureBeyondViewport=true`、`fromSurface=false`）全部 JPEG 首字节 FF D8、约 10 KB；逐页采样见 JSON。印证 `d023`。
- 影响：t040 实现须按「产品自维护活动 target + `Target.getTargets` 仅枚举 page target + `Page.captureScreenshot` 截 viewport」设计；AC-001 的 480px 缩放 / JPEG q70 由产品侧处理；AC-007 的「截图前后不变」由截图不调用 `bringToFront` / `activate` 保证，真实栈 E2E 断言该性质。Chromium 主版本升级或改用真实宿主窗口时重跑 s016 复核。
- 现状：有效
