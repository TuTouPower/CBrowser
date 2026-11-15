# d047 仅靠 Chromium 参数无法阻断 WebRTC STUN 与 QUIC UDP 泄漏，必须保留内核双族 OUTPUT DROP

- 来源：s022 代理 SDK 与传输隔离技术验证（2026-11-15，macOS arm64 OrbStack 容器 AF_PACKET 抓包与 netfilter 计数器实测，CloakBrowser `0.6.4` + Chromium `146.0.7680.177.3` `linux-arm64`）
- 结论：
    1. 在 `iptables OUTPUT` 开放的对比条件下，即使同时配置 `--proxy-server`（`http` 或 `socks5`）、`--fingerprint-webrtc-ip=8.8.8.8`、`--force-webrtc-ip-handling-policy=disable_non_proxied_udp` 或 `Preferences.webrtc.ip_handling_policy="disable_non_proxied_udp"`，Chromium 在 ICE 阶段仍会绕过代理向 `stun:ip:3478` 直接发送真实 UDP STUN Binding Request；若 STUN 服务器为域名（`stun:host:3478`），还会触发绕过 HTTP 代理的本地 UDP DNS 查询。
    2. `socks5://` 代理在强制 QUIC 条件下会发送 `SOCKS5 UDP ASSOCIATE (cmd=3)` 并向代理临时 UDP 中继端口发包；添加 `--disable-quic` 后即使服务端返回 `Alt-Svc: h3` 也全程不发 `UDP ASSOCIATE`，稳定通过 HTTP/TLS over TCP 完成访问。
    3. 仅放行显式解析后的代理 TCP `ip:port`（双族 IPv4/IPv6，IPv6 代理如 `[fd00:22::10]:18080` 在 `ip6tables OUTPUT -j DROP` 下实测可用）而不在带代理时附加 `OUTPUT -j ACCEPT` 或非必要 `127.0.0.11:53` UDP 放行，可在内核层把 STUN UDP 与 STUN DNS 泄漏降为 0；该严格 `OUTPUT -j DROP` 边界对代理模式 Browser 与 Egress Probe helper 均成立。
- 证据：`docs/spikes/s022_proxy_sdk_privacy_egress/report.md`、`docs/spikes/s022_proxy_sdk_privacy_egress/code/`。
- 影响：`NetworkPolicySpec`、Browser 生命周期策略与 `probe` 策略均须共享统一的直连/代理出站规划：无代理保留受限公网放行，有代理时双族一律 `OUTPUT -j DROP` 且仅最小放行解析后的代理 TCP 端点；Runner 同时注入 `--disable-quic` 与 WebRTC IP handling 防护参数/Preferences 作纵深防线。
- 现状：有效
