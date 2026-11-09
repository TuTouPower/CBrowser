# p053 局域网多设备访问（LAN access + 根证书下载）

- 来源：DS 审阅 P1-4/P1-5，用户决策暂放弃
- 内容：让同一局域网内其他设备（手机/平板/另一台电脑）经 Caddy HTTPS 入口使用 CBrowser（含 WebRTC 画面 + API）。现状三处全坏：Stream `bind_host/public_ip` 从未接线（恒 `127.0.0.1`，`supervisor/core.py:2461-2474` 等）；根证书下载生产恒 404（CA 在 `caddy_data` 卷，API 不可见）；`https_port=443` 时 Origin 白名单不归一化致全写 403（已修：P1-6 默认端口归一化，与 LAN 无关）。
- 保留的代价：修三项均为小改（传参、deploy 拷贝 `root.crt` 到 DATA_ROOT、一行归一化），无新增安全机制；但每台 LAN 设备必须先安装并信任 Caddy 本地根证书（内网 IP/mDNS 拿不到公共证书），且 CA 轮换时拷贝会过期需同步。
- 放弃的代价：Caddy/Stream 固定本机绑定（即现状转正），LAN 设备原生无任何操控路径（UI 与 API 同走 Caddy 唯一出口，`compose.yaml:137-138`）；需多设备时用 `ssh -L` 隧道临时开门。
- 处理：不办
- 暂搁：用户确认暂放弃原生LAN：单机个人用，每设备装根证书成本不值；需多设备时用ssh隧道；复活条件见条目
