# p084 CDP 数据面边界与 isolated world DOM 读取

- 来源：2026-11-13 同类项目技术调研（`.scratch/reports/隐私浏览器同类项目技术调研.md` P1-13），依据 DevTools Protocol、Foil 四层拆解、CloakBrowser 官方警告、Selkies 2.2.1 release notes
- 内容：CDP = 控制面、WebRTC = 数据面，**viewer 不应直接拿到 CDP endpoint**，其输入应由控制平面转译为 `Input.dispatch*` 或 X11 输入。目标：CDP 只绑 `127.0.0.1`/容器内网、Caddy 不代理、`--remote-allow-origins` 只列 CBrowser 前端 origin、依赖 `Host` 校验防 DNS rebinding；如需跨边界则铸 tokenized / 短 TTL / 一次性 WS URL；系统侧 DOM 读取统一走 `Page.createIsolatedWorld`，等待用宿主 `time.sleep()` 而非 `page.wait_for_timeout()`（reCAPTCHA Enterprise 降分）；**不要为投递 init script 削弱页面 CSP**（`'unsafe-eval'` / `'unsafe-inline'` / `*` 是 XSS 防护退化且自身成为检测信号）。鉴权必须用令牌而非反代注入的 Basic Auth——Selkies 2.2.1 release notes 明确「the token, not the Basic login a proxy adds, decides what an API request may do」。本次为只读调研，未授权改生产代码。
- 处理：未开
- 时间：2026-11-13T19:16:54+08:00
- 关联：p028（archive，CDP fingerprint/Playwright harness，已闭环 spike）、p029（archive，CDP 强制执行边界）、p030（archive，connectOverCDP CLI）、p032（archive，Dialog 路由）、p017（archive，CDP rearm ACK）、p075（forward_auth 收口）、p076（viewer 权限位）

## 边界

上述 archive 条目各自闭环了兼容性、控制权、Dialog 与 rearm 范围；本条只补「viewer 不得直连 CDP」这一隔离契约与 DOM 读取方式，不重复其结论。

## 验收

1. viewer 侧任何路径拿不到 CDP endpoint；外部 CDP 连接仅限已认证的自动化通道。
2. `--remote-allow-origins` 白名单与 `Host` 校验生效，DNS rebinding 探测被拒。
3. 页面 CSP 不被放宽；isolated world 读取不留下可检测的全局探测变量或 `isTrusted: false` 合成事件。
