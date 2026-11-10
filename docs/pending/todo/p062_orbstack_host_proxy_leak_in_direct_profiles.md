# p062 macOS OrbStack 自动继承系统代理导致直连 Profile 出口走宿主机代理分流

- 现象：在 macOS 运行 CBrowser 时，未配置代理（直连）的 Profile 启动后自动走宿主机系统代理（如 FlClash 7890 端口），能访问 Google 且国内外流量被 FlClash 分流（国内直连 IP，国外代理 IP）。
- 影响：未配置代理的 Profile 未能实现真正的纯物理网卡直连，被动使用了宿主机的翻墙代理与分流规则，可能产生出口 IP 污染或多环境关联隐患。
- 根因：环境与底座配置机制（非业务代码缺陷）。macOS 下 Docker 底座为 OrbStack，其默认设置 `network_proxy: auto` 会通过内部网络栈（`proxy.orb.internal:8305`）自动将所有容器出站流量重定向至 macOS 系统代理（FlClash 监听的 127.0.0.1:7890）。FlClash 收到流量后按规则分流（国内 DIRECT，国外 PROXY）。CBrowser 本身启动直连 Profile 时未注入 `--proxy-server`，容器内部亦无代理环境变量，流量在宿主机 VM 网关层被透明劫持。已扫无同类代码缺陷。
- 测试缺口：现有集成与 E2E 测试运行于纯净 Linux/CI 或通过测试 fixture 抹除了 `*_PROXY` 环境变量，未覆盖 macOS + OrbStack 虚拟网络透明代理环境。建议在 `preflight` 或 `doctor` 中增加对 Docker `HTTP Proxy: *proxy.orb.internal*` 的环境检测与告警指引。
- 线索：`.scratch/verify_orbstack_proxy.py`
- 处理：未开
