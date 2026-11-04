# d029 固定 Gateway 端点只能用显式 subnet + ip-range 预留，aux-address 不可用

- 来源：日常（2026-11-04 backlog t026 审阅实测）
- 结论：在 Docker 29.4.0（OrbStack，linux/arm64）上，Profile 网络要为 Gateway 预留一个固定、不会被自动分配占用的地址，唯一可行方式是创建网络时显式指定 `subnet` 与 `ip_range`，把固定地址放在 subnet 内、ip_range 外，再以静态地址 connect Gateway；`aux_address` 预留的地址不能再分配给容器；自动 subnet 虽可指定静态地址但没有任何预留，且 ip_range 不能脱离显式 subnet 设置，网络 IPAM 创建后不可修改。
- 证据：临时网络 `cbr-review-*` 最小复现（用 `caddy:2.8-alpine` 运行 `sleep`，结束即删）：
    - `--subnet 10.251.77.0/24 --aux-address gw=10.251.77.254` 后 `docker run --ip 10.251.77.254` → `failed to set up container networking: Address already in use`。
    - 自动 subnet（`192.168.107.0/24`）上 `docker run --ip .250` 与 `docker network connect --ip .250` 均成功，但该地址未从自动分配池剔除。
    - `--subnet 10.251.78.0/24 --ip-range 10.251.78.0/25`：静态 `10.251.78.254` 成功；随后无 `--ip` 容器自动拿到 `10.251.78.2`（留在 range 内）；第二个容器再取 `.254` → `Address already in use`；释放持有者后重新取 `.254` 成功（对应 Gateway 替换）；`docker network connect --ip 10.251.79.254` 对 range 外地址同样成功。
- 影响：t026 固定端点必须由 Supervisor 为每个 Profile 媒体网络显式分配 subnet（需要地址池配置、与现有 Docker 网络/宿主路由的冲突检测、标签记录）；现行 `docker_adapter.py` `_ensure_network` 使用自动 subnet，已存在的 Profile 网络无法就地补 ip_range，只能重建网络（网络内只有 Stream 与 Gateway，Browser 在独立网络）。其它 Docker 版本或 IPAM driver 未验证，t032 在目标环境复核。
- 现状：有效
