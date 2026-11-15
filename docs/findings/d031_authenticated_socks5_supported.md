# d031 Chromium 146 支持带认证 SOCKS5（t035 / s013）

- 来源：`docs/spikes/s013_authenticated_socks5_engine_probe/report.md` 正式 spike，2026-11-05 在 Linux arm64 探针容器内以真实引擎 `chromium-146.0.7680.177.3/chrome` 实测。
- 事实：`--proxy-server=socks5://user:pass@host:port` 时，引擎 greeting 只声明 RFC 1928 method `0x02`（用户名/密码认证），完成 RFC 1929 子协商；正确凭据 → 认证 accepted、页面经代理加载、HTTP 目标收到代理转发的请求；错误凭据 → 认证 rejected、`net::ERR_SOCKS_CONNECTION_FAILED`、页面加载失败、无请求到达目标。无认证对照（method `0x00`）亦正常。
- 结论：**CloakBrowser 0.6.4 / Chromium 146 支持带认证 SOCKS5**；契约背景「Chromium 原生不支持」的假设不成立。t035 AC-008 取「引擎支持时端到端经代理出站」分支，API 不以 422 拒绝 `socks5`+凭据组合；但凭据变更须按 `credential_revision` 失败封闭（AC-007）。`--proxy-bypass-list=<-loopback>` 仅为 spike 强制本地目标走代理，生产不需要。
- 复查条件：Chromium 主版本或 `fingerprint_platform` 升级后重跑 s013。
- 现状：有效（CloakBrowser 0.6.4 / Chromium 146 现行能力，ADR 023 依据）
- 采纳：t035（无后续 tid）。
- 现状补充：拆除外置认证转发器后，该能力成为 Browser 直连上游代理、凭据直接用于 `--proxy-server` 的依据（ADR 037）；`credential_revision` 失败封闭不变。
- 边界补充（2026-11-15 终局门禁实测）：内联凭据**只对 `socks5://` 成立**。`--proxy-server=http://user:pass@host:port` 时引擎把 `user:pass@host` 整段当作主机名，DNS 解析失败、连 TCP 都不发起（recording proxy 日志为空；去掉 userinfo 后同一代理立刻收到 `PROXY_GET`）；加 407 `Proxy-Authenticate` 挑战亦不重试。故 HTTP/HTTPS 上游若要带凭据，须由上游接受无凭据访问或改用 `socks5`，不能依赖 URL userinfo；`tests/e2e/test_browser_runtime_e2e.py::test_t035_proxy_outbound_and_cdp_browser_version` 以无凭据配置验 egress，内联凭据的 URL 拼装与编码由 `tests/unit/test_t035_proxy_runtime.py` 覆盖。
