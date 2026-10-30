# d020 当前 OrbStack 普通 bridge 不能直接当作跨 Profile 隔离证明

- 来源：t005，2026-10-30T01:05:00+08:00 主控独立真实 Docker 探针。
- 结论：同一无过滤 TCP 服务绑定 `0.0.0.0:19999`，同 bridge 和另一普通 bridge 的探针均收到 `PONG`。改用 `internal=True` 的两条 bridge 后，同网成功、跨网返回 `ENETUNREACH`。此结果限于当前 Mac/OrbStack 配置，不外推所有 Docker 环境。
- 证据：t005 `.scratch/t005_api/{plain_bridge_probe,internal_bridge_probe}.py`、对应 `.log` 及 `{plain_bridge_data,internal_bridge_data}/result.json`。普通桥实验 prefix=`t005-plain-a710c290`，目标 `192.168.237.2`；internal 对照 prefix=`t005-plain-585400e7`。探针确认服务器实际 ready、探针进程退出0并解析具体连接结果，非启动失败冒充拒绝；finally 已精确回收实验资源。
- 影响：t005 AC-001/AC-006 的网络隔离部分保持未通过；旧测试服务按对端网关地址主动拒绝连接，只能证明应用过滤，不能证明 Docker 网络隔离，该负例不采纳。独立网络名字、IPAM、inspect 或容器标签均不能代替实际跨网连接测试。
- 待证假设：OrbStack `network_proxy=auto`，macOS HTTP/HTTPS/SOCKS 已启用，OrbStack `network.proxy.exclude` 为空；透明代理可能绕过普通 bridge 隔离。尚未执行代理排除实验，不将假设写成根因。`internal=True` 会改变外部连通能力，不能仅凭此对照直接修改需要上网的 Browser 网络。
- 官方依据：[OrbStack 代理文档](https://docs.orbstack.dev/docker/network#proxies) 说明透明代理跟随 macOS 设置并提供排除项；该文档不证明本机故障因果。
- 当前动作：采用 Runtime 自有 network namespace filter 与启动 gate，不依赖修改 OrbStack 代理。原代理排除对照实验不再是实施前提，未写任何全局设置，透明代理因果仍未证实。
- 修复证据：Supervisor12 定向无过滤网络组合 7PASS13.46秒，独立命名空间黑盒复验3PASS26.80秒；Supervisor13 完整容器图 Round7 1PASS30.44秒，实际 Browser/Stream 双向跨 Profile 四种 TCP 连接均拒绝，同目标 loopback 正例成功。IPv6 实际私有 echo 在宽泛 ICMPv6 规则下先失败，收窄后拒绝且明确允许的 TCP 保持 PONG。日志在 t005 `.scratch/t005_api/`，后续源改动仍须重建复验。
- 现状：有效；普通桥事实已验证，候选策略取得定向实证，尚未替代 t005 最终门禁。
