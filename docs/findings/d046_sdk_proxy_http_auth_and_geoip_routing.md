# d046 CloakBrowser SDK 0.6.4 proxy= 支持 HTTP/HTTPS 认证并经代理完成 GeoIP 解析

- 来源：s022 代理 SDK 与传输隔离技术验证（2026-11-15，macOS arm64 OrbStack 容器实测，CloakBrowser `0.6.4` + Chromium `146.0.7680.177.3` `linux-arm64`；`linux-x64` `146.0.7680.177.5` 记为 `NOT_RUN / USER_WAIVED`）
- 结论：
    1. 若只传手动 `--proxy-server=...` 而 `launch_persistent_context_async(proxy=None)`，`geoip=True` 会绕过代理直连外部 IP 探针，并在严格 `OUTPUT -j DROP` 下超时失败。改传官方 SDK `proxy=` 参数后，GeoIP 外部 IP 请求（`api.ipify.org`）与浏览器导航均经同一代理出口，`.cloakbrowser-seed` 在复用同一 `user_data_dir` 时保持稳定，且显式只设置 `locale` 时仍可保留 GeoIP 推导的 `timezone` 与 `--fingerprint-webrtc-ip`。
    2. 对 `http://user:pass@host:port` 与 `https://user:pass@host:port`（包含特殊字符口令 URL 编码与 TLS-to-proxy HTTPS 上游），SDK `proxy=` 将其转为结构化 Playwright proxy 参数，实测 HTTP/HTTPS 目标均连通，错误口令在 `0` 目标命中的前提下失败封闭；先前在 runner 中仅针对手动 `--proxy-server` 成立的 `ProxyHttpAuthUnsupportedError` 对官方 SDK `proxy=` 已不适用。
    3. 当 `geoip=True` 且外部 IP echo 全失败时，SDK `maybe_resolve_geoip` 会回退对代理主机 IP 查询 `GeoLite2-City.mmdb`；若代理为 RFC1918/私有地址且离线无 echo 服务，浏览器启动会因 `AddressNotFoundError` 直接中止（`RuntimeError: GeoIP lookup failed`）。
- 证据：`docs/spikes/s022_proxy_sdk_privacy_egress/report.md`、`docs/spikes/s022_proxy_sdk_privacy_egress/code/`。
- 影响：`BrowserRunner` 应移除手动 `--proxy-server` 旁路与已证伪的 HTTP/HTTPS 认证前置拒绝，统一改由官方 SDK `proxy=` 接入；离线或私网模拟代理测试需注意 `geoip=False` 或提供可控 echo 响应。
- 现状：有效（`linux-arm64` 实测确认；`linux-x64` `NOT_RUN / USER_WAIVED`）
