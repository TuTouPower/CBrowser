# s013 带认证 SOCKS5 真实引擎 spike 报告

- 日期：2026-11-05
- 目的：t035 UNVERIFIED-SPIKE「CloakBrowser 0.6.4（Chromium 146）对带认证 SOCKS5 的支持（Chromium 原生不支持）」实测；结论决定 AC-008 分支（支持则端到端经代理出站，不支持则 API 422 拒绝）。
- 材料：`code/probe.py`，在 Linux arm64 探针容器 `cbrowser-t032-probe:final`（Python 3.12 + Playwright）内运行，挂载真实引擎缓存 `chromium-146.0.7680.177.3/chrome`。脚本自包含三个组件：RFC 1928 SOCKS5 服务器（要求用户名/密码子协商 0x02）、本地 HTTP 目标服务（记录 peer 地址）、真实 Chromium 146 引擎（`--proxy-server=... --proxy-bypass-list=<-loopback>`）。不修改任何产品代码。

## 结论

**带认证 SOCKS5 受支持**，AC-008 采用「引擎支持时端到端经代理出站」分支，不需要 422 拒绝。契约背景中的「Chromium 原生不支持」假设在本引擎版本上不成立。

- 决定：是（按「支持」分支实施，凭据由 `proxies` 表统一保存并在启动时注入 `--proxy-server`）。
- 无需后续理由：认证 SOCKS5 已由真实引擎验证可用，t035 内实现端到端出站与凭据变更失败封闭即可，无独立后续 task。
- 依據：`docs/findings/d031_authenticated_socks5_supported.md`。

## 三组实测（同一容器、递增端口）

|用例|`--proxy-server`|SOCKS5 greeting|认证结果|页面加载|HTTP 请求经代理|
|---|---|---|---|---|---|
|无认证对照|`socks5://127.0.0.1:1080`|methods `[0]`|无|成功（title `probe-ok`）|2 次|
|正确凭据|`socks5://probeuser:probepass@127.0.0.1:1081`|methods `[2]`|5 次 auth_attempt 全部 accepted|成功|2 次|
|错误凭据对照|`socks5://probeuser:wrongpass@127.0.0.1:1082`|methods `[2]`|5 次 auth_attempt 全部 rejected|失败 `net::ERR_SOCKS_CONNECTION_FAILED`|0 次|

关键观察：引擎从 URL 解析出用户名/密码后，greeting 只声明 method `0x02`（用户名/密码认证），并完成 RFC 1929 子协商；错误凭据时代理拒绝、页面无法加载，证明认证确实生效而非被忽略。

## 对 AC-008 的影响

- 契约 AC-008 的两分支中，取「引擎支持时端到端经代理出站」；API 不应以 422 拒绝 `socks5` + 用户名/密码组合。
- 实施注意：`--proxy-bypass-list=<-loopback>` 仅用于 spike 强制本地目标走代理；生产环境目标为公网，无需该参数。凭据只在启动参数中出现一次，不进入日志/错误/SSE；凭据变更时 `credential_revision` 与绑定快照不一致按 `proxy_credentials_changed` 失败封闭（AC-007）。
- 复核条件：引擎版本升级（如 t041 改 `fingerprint_platform` 或 Chromium 主版本）后重跑本 spike 再确认。
