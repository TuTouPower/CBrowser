# d031 Chromium 146 支持带认证 SOCKS5（t035 / s013）

- 来源：`docs/spikes/s013_authenticated_socks5_engine_probe/report.md` 正式 spike，2026-11-05 在 Linux arm64 探针容器内以真实引擎 `chromium-146.0.7680.177.3/chrome` 实测。
- 事实：`--proxy-server=socks5://user:pass@host:port` 时，引擎 greeting 只声明 RFC 1928 method `0x02`（用户名/密码认证），完成 RFC 1929 子协商；正确凭据 → 认证 accepted、页面经代理加载、HTTP 目标收到代理转发的请求；错误凭据 → 认证 rejected、`net::ERR_SOCKS_CONNECTION_FAILED`、页面加载失败、无请求到达目标。无认证对照（method `0x00`）亦正常。
- 结论：**CloakBrowser 0.6.4 / Chromium 146 支持带认证 SOCKS5**；契约背景「Chromium 原生不支持」的假设不成立。t035 AC-008 取「引擎支持时端到端经代理出站」分支，API 不以 422 拒绝 `socks5`+凭据组合；但凭据变更须按 `credential_revision` 失败封闭（AC-007）。`--proxy-bypass-list=<-loopback>` 仅为 spike 强制本地目标走代理，生产不需要。
- 复查条件：Chromium 主版本或 `fingerprint_platform` 升级后重跑 s013。
- 采纳：t035（无后续 tid）。
