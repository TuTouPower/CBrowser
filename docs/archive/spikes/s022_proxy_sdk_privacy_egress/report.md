# Spike report: s022 CloakBrowser SDK `proxy=` 与容器代理传输隔离验证

## 问题

确认固定版本 CloakBrowser SDK `0.6.4` + Chromium `146.0.7680.177.3`（`linux-arm64`）在真实隔离 Docker netns 中经由官方 `proxy=` 参数启动时的真实契约：

1. 历史回退根因：为何 `f04293f` 为代理模式启用 `OUTPUT -j DROP` 后触发 readiness 超时并被 `047b4d1` 回退？
2. `proxy=` 协议与鉴权：手动 `--proxy-server` 与官方 SDK `proxy=` 对 `http` / `https` / `socks5` 鉴权（含特殊字符密码）、错密失败封闭、TLS-to-proxy `https://`、IPv6 字面量代理及 GeoIP（`timezone` / `locale` / `--fingerprint-webrtc-ip` / `.cloakbrowser-seed` 稳定性）的真实行为边界。
3. 隐私防泄漏边界：WebRTC ICE/STUN UDP、STUN DNS 解析、QUIC / `SOCKS5 UDP ASSOCIATE`、常规 DNS 在放开 vs 严格 `iptables`/`ip6tables OUTPUT -j DROP` 下的真实报文行为，以及 Egress Probe helper 在现行 `role="browser"` 规则下的旁路风险。

## 成功判据

- 在独立 Docker bridge（IPv4 及 IPv6 双族）内部署可控 HTTP/HTTPS/SOCKS5 代理、HTTPS/TLS 靶站、STUN UDP 服务与 DNS 服务，使用 `AF_PACKET` 原始套接字抓包与 `iptables`/`ip6tables` 计数器逐项实测。
- 不得把 `linux-arm64`（`146.0.7680.177.3`）外推为 `linux-x64`（`146.0.7680.177.5`），后者显式记为 `NOT_RUN / USER_WAIVED`。

## 尝试

- `docs/spikes/s022_proxy_sdk_privacy_egress/code/in_container_services.py`：容器内靶站、HTTP/HTTPS/SOCKS5 代理（含认证、错密拒绝与 `UDP ASSOCIATE` 观测）、STUN UDP、UDP:8443 与 DNS:53 服务；签发带 `KeyUsage(key_cert_sign, crl_sign)` 与 `SKI/AKI` 的测试 CA（满足 Python 3.15 OpenSSL 校验）。
- `docs/spikes/s022_proxy_sdk_privacy_egress/code/netns_sniffer.py`：基于 `AF_PACKET` `SOCK_RAW` 捕获 Browser netns 全量出站帧（目标端口/DNS 查询名/STUN Binding Request）。
- `docs/spikes/s022_proxy_sdk_privacy_egress/code/in_container_browser_probe.py`：调用真实 `cloakbrowser.launch_persistent_context_async` 探测启动、`js_env`、WebRTC ICE candidates、`seed` 与命令行参数。
- 三轮隔离实验编排：`run_spike_s022.py`、`run_spike_s022_round2.py`、`run_spike_s022_round3.py`。

## 证据

### 1. 历史回退 `f04293f` / `047b4d1` 根因定论

1. **策略字段不对称漂移**：`f04293f` 仅在 `start_browser_container()` 传入 `"proxy_enforced": True`，未在 `browser_policy_spec()` 同步返回，导致 `core.py` 的 `verify_container_policy` 对比默认 `proxy_enforced=False` 规则集持续返回不匹配。
2. **SDK `proxy=` 旁路**：`runner.py` 将 `proxy_arg` 拼入 `args` 后以 `proxy=None` 调用 `launch_persistent_context_async`，使 SDK `maybe_resolve_geoip` 绕过代理直连 `https://api.ipify.org`，在 `OUTPUT -j DROP` 下超时阻塞就绪。

### 2. 实测能力与防泄漏矩阵（`linux-arm64` / `0.6.4` / `146.0.7680.177.3`）

|验证项|实测输入与条件|观测结果|是否安全|
|---|---|---|---|
|手动 `--proxy-server` + `geoip=True`|严格 `OUTPUT DROP`，`proxy=None`|直连 `api.ipify.org` 超时，`proxy_hits=0`|否|
|SDK `proxy=` + `geoip=True`（无认证/有认证 `http`、`socks5`）|严格 `OUTPUT DROP`，mock `api.ipify.org` 经代理返回 `8.8.8.8`|`CONNECT`/`ATYP=domain` 走代理，仅设定 `locale` 时保留推导 `timezone` 与 WebRTC spoofing IP|是|
|`http://` / `https://` 特殊字符口令认证|SDK `proxy=` + `p@ss:w=rd%1!/#?`（错密对照组同期验证）|SDK 转为 Playwright `proxy` 字典；HTTP/HTTPS 靶站 200，错密 `target_hits=0`|是|
|`https://`（TLS-to-proxy）|无认证 & 带认证 TLS 代理|200 OK，`Client -> Proxy` 为 TLS 握手|是|
|离线 `geoip=True` + RFC1918 代理|外部 echo 全失败|SDK 回退查代理 IP `GeoLite2-City.mmdb` 并抛出 `RuntimeError` 中止启动|约束|
|WebRTC 仅靠浏览器开关（`OUTPUT` 放开）|同时设 `--fingerprint-webrtc-ip=8.8.8.8`、`--force-webrtc-ip-handling-policy=disable_non_proxied_udp` 或 Pref|`http`/`socks5` 下均实测向 `stun:ip:3478` 发直连 UDP STUN；`stun:host:3478` 额外触发本地 UDP DNS|否|
|WebRTC + 严格 `OUTPUT DROP`（不放行 `127.0.0.11:53`）|`stun:stun-host.s022.invalid:3478` + 仅放行代理 TCP|`dns_queries=[]`，`stun_dsts=[]`，页面 JS 仅见 spoof IP|是|
|QUIC 强制模式 over `socks5://`|`--enable-quic --origin-to-force-quic-on`（`OUTPUT` 放开 vs 仅 TCP 严格 `DROP`）|开放下发 `SOCKS5 UDP ASSOCIATE (cmd=3)` 走代理临时 UDP 端口；严格仅 TCP 下 UDP 被拦截并报 `ERR_QUIC_HANDSHAKE_FAILED`|是|
|`--disable-quic` over `socks5://`|目标返回 `Alt-Svc: h3=":8443"` + 严格仅 TCP `DROP`|0 次 `UDP ASSOCIATE`，HTTPS 200 over TCP|是|
|域名目标 DNS（`http://` 与 `socks5://`）|启用容器 DNS `172.29.42.10:53`，访问 `.invalid` 域名|0 本地 DNS 报文；`socks5` 发 `ATYP=domain`，`http` 发主机名请求|是|
|Seed 稳定性|同一 `user_data_dir` 两次带 `proxy=` 启动|两次 `--fingerprint` seed 均保持 `81923`|是|
|IPv6 代理 + `ip6tables OUTPUT DROP`|IPv6 bridge，仅放行 `[fd00:22::10]:18080/tcp`|IPv6/IPv4 目标均经 IPv6 代理返回 200；v4 全 DROP 无泄露|是|
|Egress Probe `role="browser"` 旁路检查|对照当前 `role="browser"` 与严格仅放行代理策略|`NetworkPolicySpec` 当前对 RFC1918 有前置 DROP，但尾部 `OUTPUT -j ACCEPT` 仍放通非保留公网直连|需收紧|

- **平台覆盖说明**：以上全部为 `macOS arm64` OrbStack Docker 容器内 `linux-arm64`（Chromium `146.0.7680.177.3`）实测；`linux-x64`（`146.0.7680.177.5`）未实测，登记为 `NOT_RUN / USER_WAIVED`。

## 结论

1. 必须废除手动 `--proxy-server` 注入，由 `BrowserRunner` 统一把已校验的 `proxy=` 传给 `launch_persistent_context_async`，并移除不再成立的 `ProxyHttpAuthUnsupportedError` HTTP/HTTPS 认证拦截（`http`/`https`/`socks5` 全协议交由 SDK 接管）。
2. 不可依赖 Chromium WebRTC/QUIC 参数替代内核隔离；代理模式 Browser 与 Egress Probe 均须在双族 `OUTPUT -j DROP` 下工作，仅最小放行解析后的代理 TCP `ip:port`（且代理为主机名时仅在必要场景由容器内 DNS 解析端点后控制 DNS 出站），`127.0.0.11:53` 不应在已拿到字面量代理且无本地解析需要时盲目放行，同时补充 `--disable-quic` 与 WebRTC IP handling 防护参数/Pref 作为纵深防御。
3. `start_browser_container`、`browser_policy_spec`、readiness、reconcile 与 `_install_probe_network_policy` 必须消费同一个从 Profile 配置与凭据派生的出站规划，消除单点字段遗漏导致的策略漂移。

## 是否采纳

- 决定：是
- 理由：已完全定位历史回退根因、HTTP/HTTPS 认证误判、WebRTC/STUN 与 QUIC UDP 泄漏路径及 GeoIP 离线约束，足以支持立即架构定案与全栈落地。
- 后续 task：无
- 无需后续理由：按用户指示（`p102` 直接在 `main` 主分支闭环交付），不在任务板新建 task，直接基于本 spike 结论推进源码改造、测试与门禁验收。

## 关联 findings

- [d046 CloakBrowser SDK 0.6.4 proxy= 支持 HTTP/HTTPS 认证并经代理完成 GeoIP 解析](../../findings/d046_sdk_proxy_http_auth_and_geoip_routing.md)
- [d047 仅靠 Chromium 参数无法阻断 WebRTC STUN 与 QUIC UDP 泄漏，必须保留内核双族 OUTPUT DROP](../../findings/d047_chromium_webrtc_quic_leak_requires_netns_drop.md)
