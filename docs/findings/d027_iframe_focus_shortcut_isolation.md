# d027 iframe 焦点锁定与宿主快捷键隔离机制

- 来源：日常
- 结论：当用户点击进入会话 `iframe` 后，点击宿主页面的非表单 DOM 容器（如 `aside`、`div` 等无 `tabIndex` 元素）不会触发浏览器对 `iframe` 的自动 `blur`，导致键盘事件依然发往 `iframe` 内协议栈。必须在宿主容器由 `pointerdown`/`mousedown` 主动执行 `iframe.blur()` + `window.focus()`，并在 `adapter.ts` 捕获阶段按 `win.parent.document.activeElement !== win.frameElement` 校验焦点状态并执行 `stopImmediatePropagation()`，才能实现宿主与远程会话快捷键（如 `Cmd+Shift+R`）的彻底隔离。
- 证据：
    1. 单元测试 `src/frontend/src/features/browser-session/adapter_restart.test.ts`：验证脱焦时 `keydown`/`keyup` 立即阻断。
    2. 单元测试 `src/frontend/src/app/AppLayout.focus.test.tsx`：验证宿主点击时触发 `iframe.blur()` 与 `window.focus()`。
    3. 黑盒验证 `.scratch/verify_focus_isolation_blackbox.py`：基于 Playwright 无头 Chrome 登录真实环境 `https://127.0.0.1:56661`，验证点击侧边栏后宿主 `activeElement` 从 `IFRAME` 变为 `<BODY>`，宿主触发 `Cmd+Shift+R` 时内部 `iframe` 接收事件数为 0。
- 影响：前端 `AppLayout`、`adapter.ts`、会话 iframe 键盘交互。
- 现状：有效
