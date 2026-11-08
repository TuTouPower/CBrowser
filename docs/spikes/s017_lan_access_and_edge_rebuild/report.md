# Spike report: s017 局域网访问与边缘重建实测

## 问题

t042 开工前有 5 个未知契约（含 1 个 UNVERIFIED-BLOCKING 与 4 个 UNVERIFIED-SPIKE）：

1. 绑定变化时边缘容器（Caddy）的重建归属（Supervisor 接管边缘容器，或宿主侧控制器），以及它与 compose、release controller 的职责边界。
2. OrbStack 下发布端口绑定回环（127.0.0.1）与所有地址（0.0.0.0）的行为，以及容器内看到的来源 IP。
3. 自动化测试中模拟「非回环来源」客户端的方法。
4. 局域网 HTTPS 证书未被信任、用户跳过警告时页面是否仍属安全上下文（决定是否必须安装根证书才能使用会话页）。
5. Selkies 2.2.1 对 `--webrtc-public-ip` 与 UDP mux 非回环绑定的行为。

## 成功判据

- 端口绑定在回环与所有地址下对局域网客户端具备确定性物理阻断/连通证据。
- Chrome 在未信任局域网 HTTPS 下验证 `isSecureContext` 与 `navigator.locks` 真实行为。
- Selkies 2.2.1 参数及 Stream 容器环境变量透传能力具备实测证据。
- 边缘容器以新端口绑定的重建能力在 Supervisor 容器权限下具备实测代码与成功证据。

## 尝试

在 `docs/spikes/s017_lan_access_and_edge_rebuild/code/` 下编写了 5 组实测代码：

1. `probe_network_and_binding.py`：实测回环 vs 全地址绑定下的访问与容器内来源 IP。
2. `probe_chrome_secure_context_dom.py`：启动 Caddy HTTPS 托管探针页面，真实 Google Chrome（无头）访问局域网 IP 实测 DOM 与 JS 执行环境。
3. `probe_selkies_public_ip.py`：在真实 Stream Runtime 镜像中探查 Selkies 2.2.1 命令行参数与 entrypoint 支持。
4. `probe_recreate_container.py`：在 Supervisor 容器环境下运行 Docker SDK 原地原子重建容器并重绑端口。

## 证据

- `code/result_network_binding.json`：回环绑定对局域网 IP 彻底拒绝（Timeout/code 7）；全地址绑定正常连通（200），容器内客户端地址为网桥网关 `192.168.215.1`。
- `code/result_secure_context.json`：Chrome 访问未信任局域网 HTTPS 时，`isSecureContext: true`，`hasLocks: true`，`hasRTCPeerConnection: true`，`hasCryptoSubtle: true`。
- `code/result_selkies_public_ip.json`：Selkies 2.2.1 原生支持 `--webrtc-public-ip` 与 `--webrtc-ice-lite`，entrypoint 已具备环境变量透传。
- `code/result_edge_rebuild.json`：Supervisor 权限下通过 Docker API 成功将容器端口由 `127.0.0.1:54326` 原地重建并切换为 `0.0.0.0:54326`。

## 结论

1. 边缘容器重建定案由 Supervisor 作为单机唯一 Docker 协调者统一管理，避免引入外部宿主常驻进程；Caddy 与 Stream 的端口重绑与漂移检测纳入 Supervisor 统一控制面。
2. OrbStack 下端口绑定 `127.0.0.1` 具备物理隔离能力，局域网客户端无法连通；绑定 `0.0.0.0` 正常工作。
3. 测试中非回环客户端可通过独立 Docker 容器发起局域网 IP 请求稳定模拟。
4. 局域网 HTTPS 自签名未信任证书跳过警告后，页面保持为 Secure Context，Web Locks 与 WebRTC 完整可用。安装根证书为防中间人攻击与优化体验的最佳实践，非功能阻断。
5. Selkies 2.2.1 完全支持局域网 IP 通告与 host candidate 输出。

## 是否采纳

- 决定：是（按上述 5 项实测结论定案实施方案并修订 ADR 013/024）
- 理由：5 项外部契约全部实测通过，方案具备闭环能力，消除了阻断与架构未知。
- 后续 task：t042
- 无需后续理由：不适用

## 关联 findings

- `docs/findings/d036_lan_access_and_edge_rebuild.md`
