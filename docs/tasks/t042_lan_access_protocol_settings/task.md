# Task spec

## 背景

p037（用户提出）：局域网访问改为用户在 UI 中可配置，保存后统一应用生效，不做运行中热切换；局域网指完整可用，其他机器必须能打开并操作远程浏览器画面。用户 2026-11-05 决定只保留 HTTPS（D14，取代原「HTTP / HTTPS 开关」与「局域网 HTTP 会话降级」）：局域网设备安装 Caddy 本地根证书；会话页始终处于安全上下文，复制标签页的 Web Locks 机制不变；不存在跨协议 Cookie 冲突。2026-11-05 按外部审阅补全「已保存 / 已生效」状态、可恢复的应用操作、端口绑定重建与私钥隔离。2026-11-05 于 main@3101540 核实现状：

- 端口与 Caddy：
    - `compose.yaml` 的 caddy 服务只映射 `0.0.0.0:${CBROWSER_HTTPS_PORT:-56661}:443`。
    - 入库的 `config/deploy/caddy/Caddyfile` 为只读单文件挂载、`admin off`，站点写死为 `https://127.0.0.1, https://192.168.31.76, https://karsondemacbook-pro.local`。
    - Caddy 使用官方镜像，Caddy 本地 CA（含私钥 `root.key`）位于 `caddy_data` 卷。
    - `scripts/deploy_v2.sh` 校验该 Caddyfile 存在（第 222 行附近），并把它的 sha256 写入 release manifest（第 330 行附近）。
- Origin：`CBROWSER_ALLOWED_ORIGINS` 只在启动时读取（`api/app.py:97`、`gateway/config.py:71`）；Gateway 不挂载数据目录。
- 健康检查：`/api/v1/health` 无条件返回 ok（`api/v1/router.py:69`），不能证明配置已生效。
- 媒体：
    - Supervisor 启动 Stream 时 `public_ip` 默认 `127.0.0.1`（`supervisor/docker_adapter.py:1224`），UDP mux 发布到 `127.0.0.1`（`supervisor/container_spec.py:174`）。
    - `_converge_session`（`supervisor/core.py:295`）不比对 Stream 的绑定地址与通告 IP。
    - `supervisor/network_policy.py:33` 的 `BLOCKED_IPV4_RANGES` 屏蔽私有网段。
    - ADR 013 规定媒体只走同机直连。
- 端口绑定在容器创建时固定，`docker restart` 不会应用新的绑定。

## 契约区

### 范围

- 网络访问配置：字段为「允许局域网访问」与「局域网通告 IP」。API 是唯一权威，区分两种状态：
    - 待应用：保存即写入。
    - 已应用：由应用操作生成的不可变配置版本。
    - 各服务只从已应用版本启动，永不读取待应用配置；各服务报告实际运行的配置版本。
- 应用操作：可持久恢复的操作，记录操作 ID、目标版本、阶段与失败原因；API 或 Supervisor 重启后可继续或明确失败；同一时间只允许一个；以「全部组件报告目标版本且 readiness 通过」判定完成，不以存活探测判定。
- 端口绑定：本机模式下 HTTPS 端口与媒体 UDP 只绑定回环，局域网模式下绑定所有地址；绑定变化的容器（Caddy、Stream）重建生效。边缘容器由谁重建，在正式 spike 后以 ADR 定案。
- Supervisor：
    - 应用期间停止以旧配置对账。
    - Stream 容器以标签记录绑定地址与通告 IP；`_converge_session` 与启动恢复比对已应用版本，漂移时重建。
    - 局域网模式下网络策略放行局域网客户端候选。
- Caddy：配置由已应用版本确定性生成并加载；删除入库的写死主机与 IP 的 Caddyfile；部署脚本、release manifest 指纹与相关测试按新机制改写。
- Origin 白名单由已应用版本派生，API 与 Gateway 读取同一来源（Gateway 只读挂载配置）。
- 入口变化：应用后当前访问来源将不可达时（例如从局域网来源切到本机模式），应用前告警并给出新的可达地址；操作结果可在新来源查询。
- 根证书：只提供 Caddy 本地根证书的公钥证书下载；CA 私钥不挂载进 API，也不对外暴露。
- 设置页「网络访问」区块：局域网开关、通告 IP（部署脚本预填宿主当前局域网 IP）、待应用与已应用状态、「应用」及操作阶段与失败原因、根证书下载与安装说明。
- 新 ADR 修订 ADR 013：媒体链路由「仅同机」改为本机 / 局域网可配置，只提供 HTTPS。
- 新增与改动文案 en / zh 同步补键。

### 非范围

- HTTP 访问（D14）。
- 公网访问、NAT 穿透与 TURN。
- 运行中热切换配置。
- 自动探测多网卡并自动切换通告 IP。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：设置页可配置局域网开关与通告 IP（非法地址被拒绝），并同时显示待应用与已应用状态；保存只改变待应用配置，运行中的服务不受影响。
- [x] AC-002：保存后不应用，单独重启任一服务（API、Gateway、Caddy、Supervisor），该服务仍按已应用版本运行，组件间不出现配置分裂。
- [x] AC-003：应用需要管理员会话与 CSRF，生成带操作 ID、目标版本、阶段与失败原因的操作记录；重复或并发请求不启动第二个操作；API 或 Supervisor 在操作中重启后，操作继续完成或明确标记失败；只有全部组件报告目标版本且 readiness 通过时，操作才标记完成；前端展示阶段与结果。
- [x] AC-004：本机模式下，HTTPS 端口与媒体 UDP 只绑定回环，来自非回环地址的连接不可达；局域网模式下，处于非回环网络位置的无头 Chrome 可经 HTTPS 登录并完成会话（远程画面帧到达且输入生效）。
- [x] AC-005：切换模式时，绑定变化的容器（Caddy、Stream）被重建；Browser 容器与 Profile 数据保留，已打开的会话自动重连。Stream 的绑定地址或通告 IP 与已应用版本不一致时，对账与启动恢复都会检测到并重建该 Stream。
- [x] AC-006：Caddy 配置由已应用版本确定性生成；仓库中没有写死主机或 IP 的 Caddy 配置；release manifest 对生成输入取指纹；部署与回退测试按新机制通过。
- [x] AC-007：API 与 Gateway 的 Origin 白名单来自同一已应用版本，未列出的 Origin 被拒绝；切换模式后新白名单生效。
- [x] AC-008：根证书下载只返回公钥证书；API 容器的挂载中不含 CA 私钥（容器挂载检查）。
- [x] AC-009：应用会使当前访问来源不可达时，前端在应用前告警并显示新的可达地址；从新地址可查询该操作的结果。
- [x] AC-010：注入应用阶段失败时，操作标记失败并给出原因，系统最终收敛到单一已应用版本（完整回到上一版本或完成目标版本），不会长期停留在组件版本不一致的状态。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。AC-004 的非回环客户端由测试在宿主回环之外的网络位置运行无头 Chrome，方法由 spike 确定。

## 上下文区

- 来源：p037（2026-11-05 于 main@3101540 核实，现状仍成立，结论见背景）；只保留 HTTPS 由用户 2026-11-05 决定（D14）；配置双状态、可恢复操作、端口重建、Stream 漂移检测、私钥隔离与部署脚本改造按 2026-11-05 外部审阅补全。

### 有意不测

- 真实的第二台物理机器：以宿主回环之外网络位置上的无头 Chrome 代替。

### 测试策略

- unit 覆盖配置校验、版本生成、Caddy 配置生成与 Origin 派生。
- integration 覆盖应用操作的阶段、防重入、重启续跑与失败收敛，以及 Stream 漂移检测。
- 真实栈 E2E 覆盖两种模式下的可达性、非回环来源会话、模式切换后的重连与私钥隔离。
- 所有浏览器测试无头运行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 绑定变化时边缘容器（Caddy）的重建归属：已在 spike `s017`（结论 `d036`）实测并定案 ADR 026。宿主机严禁常驻进程，Supervisor 作为单机唯一持有 Docker socket 的协调者，统一接管 Caddy 与 Stream 容器在网络配置变更时的端口重建与对账，保留挂载卷与网络环境并原子替换容器。
- OrbStack 下发布端口绑定行为：已在 spike `s017`（`d036`）实测。端口绑定 `127.0.0.1` 物理阻断局域网 IP 访问（超时或拒绝）；绑定 `0.0.0.0` 连通，容器内客户端 IP 为网桥网关 `192.168.215.1`。
- 自动化测试中模拟「非回环来源」客户端的方法：已在 spike `s017`（`d036`）确定。由独立 Docker 容器客户端经宿主机局域网 IP 发起访问，回环绑定时被拒（code 7），全地址绑定时连通。
- 局域网 HTTPS 证书未被信任时的安全上下文：已在 spike `s017`（`d036`）用真实 Chrome 实测。自签名证书跳过警告后，页面中 `window.isSecureContext` 恒为 `true`，`navigator.locks`、`RTCPeerConnection` 正常可用。安装根证书为防中间人攻击与免警告推荐实践，非功能阻断。
- Selkies 2.2.1 对 `--webrtc-public-ip` 与 UDP mux 绑定的行为：已在 spike `s017`（`d036`）实测。官方原生支持 `--webrtc-public-ip` 与 `--webrtc-ice-lite`，局域网模式下 Supervisor 注入通告 IP 并将 UDP mux 绑定到 `0.0.0.0` 即可输出局域网 host candidate。

### 风险与回退

- 风险：局域网开关失效导致服务意外暴露；应用操作中断后组件版本分裂；CA 私钥泄露。
- 回退：应用上一已应用版本；源码层回退本 task commit。

### 依赖与约束

- 依赖 t039（会话页与设置页外壳）与 t043（Selkies 新版本）。
- 与 t038、t040 同改前端共享文件，用 `conflicts_with` 串行。
- 只动本 task 的隔离实例，不碰其他会话或 task 的部署实例。
- 所有浏览器测试无头运行。

### Finalization 时更新的 blueprint

- `docs/blueprint/decisions.md`：修订 ADR 013 的新 ADR（本机 / 局域网可配置、仅 HTTPS）；边缘容器重建归属 ADR；修订 ADR 017 的 Caddy 配置指纹。
- `docs/blueprint/architecture.md`、`docs/blueprint/gateway.md`、`docs/blueprint/supervisor.md`、`docs/blueprint/stream_runtime.md`：网络配置版本、应用操作、媒体绑定与漂移检测。
- `docs/blueprint/security.md`：局域网暴露面、Origin 规则与 CA 私钥隔离。
- `docs/blueprint/frontend.md`：设置页网络区块与入口变化处理。
- `docs/specs/access_control.md`、`docs/specs/release_deployment.md`、`docs/specs/webrtc_remote_display.md`。
