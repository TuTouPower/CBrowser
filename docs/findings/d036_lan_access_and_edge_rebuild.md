# d036 局域网访问、边缘容器重建与安全上下文实测契约

- 来源：s017 局域网访问与边缘重建 spike
- 结论：
    1. 端口隔离与来源 IP：OrbStack 下端口绑定 `127.0.0.1` 物理阻断局域网 IP 访问（连接被拒/超时）；绑定 `0.0.0.0` 正常连通；容器内看到的客户端 IP 为宿主机网桥网关 IP `192.168.215.1`。
    2. 非回环客户端模拟：独立容器内客户端经宿主机局域网 IP `192.168.31.76` 发起请求，在回环绑定时被拒（curl code 7），在 `0.0.0.0` 绑定时通畅（200），可直接作为 E2E 非回环测试夹具。
    3. 安全上下文与根证书：Chrome（跳过证书警告）访问局域网 HTTPS 时，`window.isSecureContext` 恒为 `true`，`navigator.locks`（Web Locks）、`RTCPeerConnection`（WebRTC）、`crypto.subtle` 全部正常生效。安装根证书为防中间人攻击与免警告的最佳实践，非 Web Locks/WebRTC 功能阻断前置。
    4. Selkies 媒体参数：官方 Selkies 2.2.1 原生支持 `--webrtc-public-ip` 与 `--webrtc-ice-lite`，`entrypoint.sh` 已支持通过环境变量透传；局域网模式下注入局域网 IP 并将 UDP mux 端口绑定改为 `0.0.0.0` 即可输出局域网 host candidate。
    5. 边缘容器重建归属：Supervisor 作为单机唯一持有 Docker socket 的控制面协调者，统一接管受网络访问配置影响的容器（Caddy 与 Stream 的重建、端口重绑与漂移检测），避免引入宿主机常驻守护，实现完全自愈闭环。
- 证据：
    - `docs/spikes/s017_lan_access_and_edge_rebuild/code/result_network_binding.json`
    - `docs/spikes/s017_lan_access_and_edge_rebuild/code/result_secure_context.json`
    - `docs/spikes/s017_lan_access_and_edge_rebuild/code/result_selkies_public_ip.json`
    - `docs/spikes/s017_lan_access_and_edge_rebuild/code/result_edge_rebuild.json`
- 影响：定案 t042 实现方案与 ADR 026，解除 t042 的 UNVERIFIED-BLOCKING 与 UNVERIFIED-SPIKE 阻塞。
- 现状：有效
