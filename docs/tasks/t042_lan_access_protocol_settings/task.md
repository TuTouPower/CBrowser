# Task spec

## 背景

p037（用户提出并确认方案）：局域网访问、HTTP、HTTPS 改为用户在 UI 中可配置，保存后点击「重启软件」重启整个栈生效，不做运行中热切换；局域网指完整可用，其他机器必须能打开并操作远程浏览器画面。2026-11-05 于 main@3101540 核实现状：

- `compose.yaml` 的 caddy 服务只映射 `0.0.0.0:${CBROWSER_HTTPS_PORT:-56661}:443`；入库的 `config/deploy/caddy/Caddyfile` 为只读单文件挂载、`admin off`，站点写死为 `https://127.0.0.1, https://192.168.31.76, https://karsondemacbook-pro.local` 并使用 `tls internal`。
- 会话 Cookie `cbrowser_session` 与 `cbrowser_csrf` 写死 `secure=True`（`api/v1/auth_router.py:94` 起）；`CBROWSER_ALLOWED_ORIGINS` 只在启动时读取（`api/app.py:97`、`gateway/config.py:71`）；部署脚本默认 `PUBLIC_ORIGIN=https://127.0.0.1:$HTTPS_PORT`（`scripts/deploy_v2.sh:44`）。
- 媒体：Supervisor 启动 Stream 时 `public_ip` 默认 `127.0.0.1`（`supervisor/docker_adapter.py:1224`），UDP mux 发布到 `127.0.0.1`（`supervisor/container_spec.py:174`）；Stream entrypoint 已把 `CBROWSER_WEBRTC_PUBLIC_IP` 传给 Selkies `--webrtc-public-ip`。ADR 013 规定媒体只走同机直连。
- 会话适配层依赖 Web Locks 识别复制标签页（`features/browser-session/adapter.ts:125`，不可用时进入 `web_locks_unavailable`）；Web Locks 只在安全上下文（HTTPS 或 localhost）可用，所以局域网 HTTP 下会话页不可用。用户 2026-11-05 决定：会话页显式降级为「需 HTTPS」，设置页告警，并提供 Caddy 本地根证书下载。
- Supervisor 挂载 `/var/run/docker.sock`，已能管理容器；`/api/v1/health` 无需鉴权（`api/app.py:444`）。

## 契约区

### 范围

- 运行时网络配置：一个经 schema 校验的配置文件（位于数据目录，例如 `data/v2/config/runtime.json`）是唯一来源，由 API 写入。字段：允许局域网访问、启用 HTTP、启用 HTTPS、局域网通告 IP。默认允许局域网，HTTP 与 HTTPS 均启用；两种协议不能同时关闭。不写 `settings` 表。
- 各服务启动时读取该配置：
    - Caddy：按配置确定性生成站点与监听；HTTP、HTTPS 两个端口在 compose 中始终映射，由配置决定是否提供服务。删除入库的写死主机与 IP 的 Caddyfile。
    - API / Gateway：Origin 白名单由同一配置派生；会话 Cookie 的 `Secure` 属性按请求来源协议决定。
    - Supervisor：局域网模式下，Stream UDP mux 绑定局域网可达地址，Selkies 通告 IP 设为局域网通告 IP；本机模式下保持 `127.0.0.1`。
- 局域网通告 IP 由用户在设置页确认或填写；部署脚本预填宿主当前局域网 IP。
- 「重启软件」：API 校验管理员会话与 CSRF 后转发给 Supervisor；Supervisor 依次重启 gateway、caddy、api，最后重启自身；防止重复触发。
- 重启交互：前端点击后立即显示「正在重启」，停止普通轮询，改为轮询 `/api/v1/health` 直到恢复，不依赖重启请求本身返回成功；超时后显示失败与恢复指引。
- 切换局域网模式后，Stream 容器按新模式重建；Browser 容器与 Profile 数据保留，已打开的会话自动重连。
- 非安全上下文降级：会话页检测到非安全上下文时显示「需 HTTPS」状态与 HTTPS 链接，不尝试建立信令；管理界面正常可用；剪贴板同步显示为不可用。
- 设置页「网络访问」区块：三个开关与通告 IP；「局域网 + HTTP」组合时显示告警；提供 Caddy 本地根证书（仅公钥证书）下载。
- 新 ADR 修订 ADR 013：媒体链路由「仅同机」改为本机 / 局域网可配置，并记录 HTTP 非安全上下文的降级规则。
- 部署脚本与 compose 同步适配；新增与改动文案 en / zh 同步补键。

### 非范围

- 公网访问、NAT 穿透与 TURN。
- 运行中热切换配置。
- 替换适配层的 Web Locks 身份机制。
- 自动探测多网卡并自动切换通告 IP。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：设置页可配置允许局域网访问、启用 HTTP、启用 HTTPS 与局域网通告 IP；默认允许局域网且 HTTP、HTTPS 均启用；两种协议同时关闭或通告 IP 非法时保存被拒绝；保存只写配置文件，不改变正在运行的服务。
- [ ] AC-002：「重启软件」需要管理员会话与 CSRF；点击后前端立即显示重启中，停止普通轮询并轮询 `/api/v1/health` 直到恢复；重复点击或并发请求只触发一次重启；重启后 Gateway、Caddy、API、Supervisor 都按新配置运行。
- [ ] AC-003：重启后 Caddy 只在已启用的协议上提供服务，未启用的协议端口不返回应用内容；仓库中不再有写死主机或 IP 的 Caddy 配置。
- [ ] AC-004：关闭局域网访问时，来自非本机地址的 HTTP / HTTPS 请求与媒体 UDP 均不可达，本机访问正常；开启时，来自非本机地址的无头 Chrome 可经 HTTPS 登录并完成会话（远程画面帧到达且输入生效）。
- [ ] AC-005：HTTPS 来源下发的会话 Cookie 带 `Secure`，HTTP 来源可正常登录且 Cookie 不带 `Secure`；API 与 Gateway 的 Origin 白名单由同一配置派生且一致，未列出的 Origin 被拒绝。
- [ ] AC-006：在非安全上下文中打开会话页时，显示「需 HTTPS」状态与 HTTPS 链接，不发起信令连接；管理界面功能正常；本机 `http://localhost` 下会话正常。
- [ ] AC-007：设置页在「局域网 + HTTP」组合时显示告警，并提供 Caddy 本地根证书下载；下载内容只含公钥证书，不含私钥。
- [ ] AC-008：切换局域网模式并重启后，Stream 容器按新模式重建（UDP 绑定地址与通告 IP 随模式变化），Browser 容器与 Profile 数据保留，已打开的会话断线后自动重连。
- [ ] AC-009：重启过程中某个服务失败时，依靠容器重启策略与健康轮询最终恢复；前端超时后显示失败与恢复指引（集成测试注入失败）。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试。AC-004 的「非本机地址」客户端由测试在宿主回环之外的网络位置运行无头 Chrome，具体方法由 spike 确定（见未知契约清单）。

## 上下文区

- 来源：p037（2026-11-05 于 main@3101540 核实，现状仍成立，结论见背景）；局域网 HTTP 的会话降级方案由用户 2026-11-05 决定。

### 有意不测

- 真实的第二台物理机器：以宿主回环之外网络位置上的无头 Chrome 代替。

### 测试策略

- unit 覆盖配置 schema 校验、Caddy 配置生成、Origin 白名单派生、Cookie `Secure` 判定。
- integration 覆盖重启编排的顺序、防重入与部分失败恢复（注入失败）。
- 真实栈 E2E 覆盖协议开关、局域网开关、非本机来源的会话、非安全上下文降级与 Stream 重建后重连。
- 所有浏览器测试无头运行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- OrbStack 发布端口下，Caddy 能否用 `remote_ip` 区分本机与局域网来源（macOS 虚拟化网关可能把来源统一成同一 IP）：UNVERIFIED-SPIKE；不可靠时改为按绑定地址区分，此时切换局域网模式需要重建 Caddy 容器。
- 自动化测试中模拟「非本机来源」客户端的方法（例如在 OrbStack 容器内运行无头 Chrome，经宿主局域网 IP 访问）：UNVERIFIED-SPIKE，实施时实测确定。
- 局域网 HTTPS 在证书未被信任、用户跳过警告时，页面是否仍属安全上下文（决定是否必须安装根证书才能使用会话页）：UNVERIFIED-SPIKE，用真实 Chrome 实测，结论写入设置页说明与 ADR。
- Supervisor 经 Docker API 重启自身与同栈容器时，与 compose 依赖和健康检查的时序：UNVERIFIED-SPIKE，集成测试验证。
- t034 升级后的 Selkies 版本对 `--webrtc-public-ip` 与 UDP mux 非回环绑定的行为：UNVERIFIED-SPIKE，真实栈实测。

### 风险与回退

- 风险：局域网开关失效导致服务意外暴露到局域网；重启编排中断后整栈不可用；Cookie 在 HTTP 下降级后被同网段窃听。
- 回退：删除配置文件后按默认值启动；源码层回退本 task commit。

### 依赖与约束

- 依赖 t034（Caddy 与 Selkies 新版本）与 t039（会话页与设置页外壳）。
- 与 t041 同改设置页与 Supervisor，用 `conflicts_with` 串行。
- 只动本 task 的隔离实例，不碰其他会话或 task 的部署实例。
- 所有浏览器测试无头运行。

### Finalization 时更新的 blueprint

- `docs/blueprint/decisions.md`：修订 ADR 013 的新 ADR（本机 / 局域网可配置、HTTP 非安全上下文降级）。
- `docs/blueprint/architecture.md`、`docs/blueprint/gateway.md`、`docs/blueprint/supervisor.md`、`docs/blueprint/stream_runtime.md`：运行时网络配置、重启编排、媒体绑定与通告 IP。
- `docs/blueprint/security.md`：局域网暴露面、Cookie 与 Origin 规则。
- `docs/blueprint/frontend.md`：会话页非安全上下文降级与设置页网络区块。
- `docs/specs/access_control.md`、`docs/specs/release_deployment.md`、`docs/specs/webrtc_remote_display.md`。
