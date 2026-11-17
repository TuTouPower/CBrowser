# s016 CDP 活动标签页识别与 Page.captureScreenshot 副作用 spike 报告

- 日期：2026-11-07
- 目的：t040 UNVERIFIED-SPIKE「CDP 没有直接的『当前活动标签页』字段；在 CloakBrowser 146 / Xvfb 下识别活动标签页的方法，以及 `Page.captureScreenshot` 对后台标签页、焦点和页面可见性的影响」实测；结论决定 t040 采集侧设计与 AC-001 / AC-007 的可验证性。
- 材料：`code/probe.py`（headless）、`code/probe_xvfb.py`（容器 Xvfb 虚拟显示）、`code/run.sh` / `code/run_xvfb.sh`、`code/result_headless.json` / `code/result_xvfb.json`。全部在当前产品 Browser Runtime 镜像 `sha256:1b75e318a2b7e6e0fdeba6d784773dd4848d2f91e7bba8650ded22d24c675513`（同 Chromium 146 引擎）容器内运行，挂载真实引擎缓存 `chromium-146.0.7680.177.3/chrome`；浏览器 headless 或容器 Xvfb 虚拟显示，未弹宿主窗口、未抢宿主焦点。不修改任何产品代码，不复用已过时的 t032 探针镜像。

## 结论

**CDP 无法直接读取「当前活动标签页」；`Page.captureScreenshot` 不改变页面可见性、焦点与活动标签，且只截 page viewport 内容。**

1. 活动标签识别：`Target.getTargets` 的 `targetInfos` 只有 `type` / `title` / `url` / `attached` / `targetId`，无 active/foreground 字段；`attached` 对全部 page 为 True；顺序不稳定（headless 为 tab-2,1,0；Xvfb 为 tab-1,0,2），`bring_to_front()` 后顺序与字段均不变。`document.visibilityState` / `document.hidden` / `document.hasFocus()` 在 headless 与容器 Xvfb 下对全部 3 个标签恒为 `visible` / `false` / `True`，无 `visibilitychange` / `focus` / `blur` 事件（印证 `d023`）。因此产品必须自行维护「活动标签」事实：以 Agent 侧 `Target.activateTarget` / `Page.bringToFront` 的调用目标，或外部 Selkies 客户端上报的焦点 `client_tab_id` 映射为准；`Target.getTargets` 仅用于枚举 page target。
2. 截图副作用（AC-007）：headless 4 组 + Xvfb 1 组 `Page.captureScreenshot`（前台页、后台页、`captureBeyondViewport=true`、`fromSurface=false`）全部返回有效 JPEG（首字节 FF D8，约 10 KB）；截图前后所有页的 visibilityState / hidden / hasFocus、页面事件计数、`Target.getTargets` 均无变化。截图本身不触发可见性或焦点变化，也不改变活动标签。
3. 截图内容（AC-001）：CDP `Page.captureScreenshot` 截的是 page viewport 渲染内容，headless 与 Xvfb 均不含浏览器标签栏 / 地址栏；480px 缩放与 JPEG 质量 70 由产品侧处理。

- 决定：是（t040 按「产品自维护活动 target + `Target.getTargets` 枚举 page target + `Page.captureScreenshot` 截 viewport」实施；采集不调用 `bringToFront` / `activate`，AC-007 的「不变」由该约束保证）。
- 无需后续理由：活动标签识别方法、截图对可见性 / 焦点 / 活动标签无影响均已用真实 Chromium 146 引擎在 headless 与容器 Xvfb 两种显示模式下实测；实现中只需按产品策略记录活动 target，无需独立后续 task。
- 依据：`docs/findings/d035_cdp_active_tab_capture_screenshot.md`。
- 复核条件：Chromium 主版本升级，或产品改用有界面 + 真实宿主窗口时重跑本 spike 再确认。

## 实测数据

|显示模式|标签数|bringToFront 后变化|captureScreenshot 目标|JPEG 有效|截图前后状态变化|
|---|---|---|---|---|---|
|headless|3|visibility / hasFocus / targets 全不变|后台 p0 / 前台 p1 / beyond viewport / no surface|4/4 是|无|
|容器 Xvfb|3|同上|后台 p2|1/1 是|无|

逐页采样（visibilityState、hidden、hasFocus、marker、事件计数、page target 列表）见 `code/result_headless.json` 与 `code/result_xvfb.json`。
