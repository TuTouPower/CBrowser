# p062 macOS OrbStack 自动继承系统代理导致直连 Profile 出口走宿主机代理分流与反向隔离方案

- 现象：在 macOS 运行 CBrowser 时，未配置代理（直连）的 Profile 启动后自动继承宿主机系统代理（如 FlClash 7890 端口），表现为能够访问 Google 等外网；同时，出站流量被 FlClash 分流规则切分：国内网站访问显示真实物理国内 IP，国外网站访问显示代理节点 IP。
- 影响：防关联与指纹浏览器在未配置代理时，无法实现纯粹的物理网卡直连，被动共用了宿主机个人梯子节点的出口 IP 与路由策略，存在出口 IP 污染、指纹关联或隐私泄露风险。
- 根因：属于运行底座（macOS + OrbStack）网关层透明代理机制与应用隔离预期的冲突，非 CBrowser 业务代码缺陷。详细机制如下：
  1. CBrowser 架构层面：当 Profile 未绑定 `proxy_id` 时，Runner 启动 Chromium 不注入 `--proxy-server` 参数，容器内无任何代理环境变量，出站默认完全交由 Docker 容器网络栈（bridge network）。
  2. OrbStack 网关机制：macOS 上 Docker 底座由 OrbStack 提供，其默认配置为 `network_proxy: auto`。OrbStack 在虚拟机网络网关层通过 `proxy.orb.internal:8305` 自动读取 macOS 系统代理设置（`scutil --proxy` 中的 FlClash `127.0.0.1:7890`）。任何从 Docker 容器发出的未知/直连出站 TCP 流量都会被虚拟机网关无感劫持并重定向至宿主机代理。容器内哪怕配置 `NO_PROXY="*"` 或设置 Chromium 直连模式，也无法阻断网关层的 L3/L4 劫持。
  3. FlClash 规则路由：FlClash 收到来自 OrbStack 的 TCP 流量后，按规则分流：国内域名/IP 命中 DIRECT（物理网卡出口，南京联通 IP），国外域名/IP 命中 PROXY（代理节点出口，海外 IP）。
  4. 官方限制：OrbStack 官方在 Issue #1380 中明确表示透明代理为全量机制（All-or-Nothing），不支持通过 Container Label、单容器环境变量等手段为单个容器关闭透明代理。
- 修复与解决方案（反向隔离架构）：
  1. 切断底层透明劫持：执行 `orb config set network_proxy none && orb restart -a`，使 OrbStack 虚拟机网关彻底停止对容器流量的代理重定向，所有容器默认全部走宿主机物理网卡纯直连。
  2. 客户端注入日常代理：在宿主机 `~/.docker/config.json` 中配置 `proxies.default`，指向 `http://host.docker.internal:7890`。日常通过终端 Docker CLI（`docker run`、`docker compose`、`docker build`）启动的开发容器会自动注入 `HTTP_PROXY` 环境变量，保持顺畅翻墙。
  3. CBrowser 架构天然免疫：CBrowser 的 `cbrowser-supervisor` 容器通过 Docker Socket API 直接调用 Docker 引擎启动浏览器沙箱，不走 Docker CLI，且内部容器未挂载宿主 `~/.docker/config.json`，因此不会被注入客户端代理；加之 OrbStack 网关劫持已关闭，CBrowser 直连 Profile 实现了 100% 物理真实出口（国内真实 IP，国外直连阻断）。若 Profile 需要出海，由 CBrowser 注入独立 `--proxy-server`，实现严格的多环境出口隔离。
- 实测验证数据（双向隔离完全成立）：
  1. 其他日常容器（`docker run --rm curlimages/curl`）：
     - `https://api.ipify.org`：`38.181.82.184`（自动走 FlClash 节点）
     - `https://www.google.com`：`HTTP/2 200`（正常翻墙）
     - `https://myip.ipip.net`：`122.96.120.17`（命中分流规则走国内直连）
  2. CBrowser 真实浏览器沙箱（`cbrowser-0001-browser`）：
     - `https://myip.ipip.net`：`122.96.120.17`（100% 物理国内 IP）
     - `https://api.ipify.org`：`Connection refused`（直连失败，完全不受宿主代理污染）
- 测试缺口：现有集成与 E2E 测试运行于纯净 Linux/CI 或通过测试 fixture 抹除了 `*_PROXY` 环境变量，未覆盖 macOS + OrbStack 虚拟网络透明代理环境。建议在 `preflight` 或 `doctor` 中增加对 Docker `HTTP Proxy: *proxy.orb.internal*` 的环境检测与告警指引。
- 线索：`.scratch/verify_orbstack_proxy.py`、`.scratch/test_docker_py_env.py`、`.scratch/test_cbrowser_simulation.py`、`.scratch/docker_config_backup.json`
- 处理：host-docker-config；resolution=resolved；reason=已完成宿主机 OrbStack 与 Docker CLI 反向隔离配置及全链路双向验证，直连环境与外部容器完全解耦
