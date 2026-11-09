> 与代码冲突时以代码与生效 spec 为准，并须同步修正本文。

# 架构

CBrowser 是面向隐私浏览器与多身份隔离的远程浏览器管理系统。采用单机 Docker 架构，以 Google Chrome 作为唯一官方支持的外部标签页客户端，通过 Selkies 2.2.1 WebRTC 实现低延迟远程画面传输，由独立的 Docker 容器沙箱实现严格的 Profile 隔离。

## 1. 现状与演进状态说明

本文档描述系统现行实现架构（历史演进见 ADR）：

- **历史基线（t001 时点）**：当时生产代码库仍维持旧单容器实现、KasmVNC/noVNC/RFB 协议代理、FastAPI WebSocket 逐帧处理与旧数据模型；t001 阶段生产代码保持不变，该基线已由后续 task 替换，现行实现见下。

- **持久化基础（t002）**：`src/backend/cbrowser/api/main.py` 提供独立 `/api/v1` 入口，落实 Profile 配置/标签/不可变版本、运行意愿与观测状态、实例事件去重、SQLite WAL 与空库 Alembic 初始化。Docker 编排、认证、媒体与前端由后续 task 实施。该入口鉴权与交付分别由 t006/t012 验收。

- **目标架构（已落地为现行架构）**：基于 t001 阶段对 Selkies 2.1.0 WebRTC、Docker shareable IPC、CDP UDS 等专题技术验证（s001–s009，d001–d014）冻结的技术架构。本文档定义的组件（独立 Supervisor 容器、Stream Gateway、Alembic 迁移模型、双容器沙箱等）为**现行拓扑契约**，**已由后续任务分步落地；当前实现状态以本节任务状态为准**。

- **t005/t006 已交付**：唯一 Docker 协调者 Supervisor（见 [Supervisor](supervisor.md)）、认证信令 Gateway（见 [Gateway](gateway.md)）、API 用户鉴权与自动化凭证（见 [安全与凭证边界](security.md)）。t015（ADR 013）已删除 coturn、TURN 凭证轮换与 ICE 代次接管，媒体改为同机直连；文件/CDP、Compose 交付与旧入口切换仍由后续 task 完成。

- **t007 已交付**：前端（见 [前端](frontend.md)）、API 经 Runtime Coordinator 驱动 Supervisor 启停（见 5.4）、每 Profile Selkies master/controller token（见 [Stream Runtime](stream_runtime.md)）。旧 UI 组件移除归 t017（原记 t011；t011 已并入 t010）。

Stream 组件边界、wire 协议与固定 SDK 适配见 [Stream Runtime](stream_runtime.md)。Browser/Stream 的正式编排和入口切换仍由后续任务完成，独立组件测试通过不能代表整套部署完成。

## 2. 上游来源与开源技术依赖矩阵

本项目由 TuTouPower 维护，基于上游仓库 [CloakHQ/CloakBrowser-Manager](https://github.com/CloakHQ/CloakBrowser-Manager) 重构演进。各层关键依赖的开源仓库及技术说明如下：

|依赖层级|组件名称|开源/官方仓库|选型版本 / Commit|职责与架构边界|
|---|---|---|---|---|
|**上游衍生来源**|CloakBrowser-Manager|[CloakHQ/CloakBrowser-Manager](https://github.com/CloakHQ/CloakBrowser-Manager)|0.1.8+ (分支基线)|业务模型原型；现行架构彻底切断对上游 UI 与单容器 VNC 运行时的依赖，独立演进|
|**隐私指纹引擎**|CloakBrowser Engine|[PyPI: cloakbrowser](https://pypi.org/project/cloakbrowser/)|`>=0.6.3`|底层真实隐身浏览器内核与指纹随机对抗引擎（许可参见 `BINARY-LICENSE.md`）|
|**远程画面捕获**|Selkies WebRTC|[selkies-project/selkies](https://github.com/selkies-project/selkies)|Release `2.2.1`（t043 由 2.1.0 升级，ADR 022 / s012 spike）|捕获 Xvfb 画面、低延迟软件视频/音频编码、WebRTC 媒体协商与输入控制协议。官方 2.1.0 缺乏原生公共 ICE restart API（d003）；原同 PC 凭证轮换/ICE 代次机制（d010, d012）已由 ADR 013 删除，媒体改为同机直连，不再依赖 Selkies 私有接口适配器|
|**边缘反向代理**|Caddy|[caddyserver/caddy](https://github.com/caddyserver/caddy)|`2-alpine`|自动化 TLS、SPA 前端静态资源服务与固定路由（`/api/*`、`/stream/*`）反向代理入口|
|**模板与工作流**|repo_template|本地 `../repo_template`|当前工作流基线|消费仓规范：task 状态机驱动、轻量契约门禁、specs/blueprint 规范|
|**文档格式化**|md_kx|[TuTouPower/md_kx](https://github.com/TuTouPower/md_kx)|PyPI `md-kx`|Markdown 文档自动化规范与一致性门禁检查|

## 3. 目标系统整体拓扑

```text
Google Chrome Stable（宿主机同一 Mac 客户端）
│
├── /                                 # 操控主界面（通过 query param ?profileId= 绑定目标）
├── /stream/{profileId}/signal        # 独立 WebSocket 信令隧道
└── /api/v1/*                         # 控制 API
      │
      ├── Caddy 反向代理（HTTPS、静态前端托管、API/信令路由）
      │     ├── /api/*    ──► cbrowser-api
      │     └── /stream/* ──► cbrowser-stream-gateway
      │
      ├── cbrowser-api（FastAPI，唯一 SQLite 写入者）
      │     ├── SQLite (WAL, busy_timeout=5000) + Alembic 持久化
      │     ├── Profile Service / Artifact Service
      │     └── Runtime Coordinator（内部认证 RPC 通道）
      │           │
      │           ▼
      ├── cbrowser-supervisor（独立容器，宿主机唯一持有 Docker Socket）
      │     ├── 容器工厂与网络/端口生命周期管理
      │     ├── 受控 UDS 隔离代理（CDP 双向流代理与下载捕获）
      │     └── 持久化运行事件队列（离线恢复与单写者重放）
      │
      ├── cbrowser-stream-gateway（独立信令网关服务）
      │     ├── Stream Agent 动态注册表（心跳维持与状态感知）
      │     └── ViewerConnection 隔离信令代理（SDP/ICE 双向转发）
      │
      ├── 动态沙箱容器（按 Profile 动态创建 2 个隔离容器）：
      │     │
      │     ├── browser-runtime-{profileId}（IPC 供体：shareable IPC, 1GiB /dev/shm）
      │     │     ├── CloakBrowser 真实浏览器进程（CDP loopback 127.0.0.1）
      │     │     ├── Xvfb (:99, MIT-SHM/XTEST) + Openbox
      │     │     ├── 虚拟 PulseAudio 服务（固定 48000 Hz 采样率）
      │     │     ├── Browser Agent（提供 /run/cbrowser/runtime/{profileId}/agent.sock）
      │     │     └── 挂载：专属 profile 目录与 /exchange 目录
      │     │           │
      │     │           │ (同 Profile 专属卷：X11 Socket, Xauthority, PulseAudio Socket)
      │     │           ▼
      │     └── stream-runtime-{profileId}（IpcMode=container:browser-runtime-{profileId}）
      │           ├── Selkies 2.2.1 WebRTC 捕获编码引擎（XShm 共享内存画面捕获）
      │           ├── Stream Agent（动态注册至 Gateway，执行 8/30 FPS 捕获仲裁）
      │           └── 独占 UDP mux 媒体端口（30000–30991/UDP）
      │                 │
      │                 └── WebRTC DTLS-SRTP 媒体流 ──► 宿主 127.0.0.1
      │                       （同机直连，无 TURN/coturn）
```

### 3.1 发布与实例身份（t027）

发布由 `scripts/deploy.sh` 单一入口执行，交付物是不可变 release：六个镜像（API、Gateway、Supervisor、Browser、Stream、Caddy）以镜像 ID 固定在 `config/deploy/releases/<release_id>.{env,json}`，连同 compose/Caddyfile/前端产物指纹与数据库迁移版本；compose 全部服务镜像只读 release 变量、无 build 块。发布与回退都以 t026 的 `reconcile_all` + `readiness` 为唯一验收（经 `docker compose exec` 在 Supervisor 容器内执行探针，宿主机不持密钥、无新增端口），验收通过后才原子移动 current/previous 指针。回退在目标 release 缺 readiness 能力或迁移版本低于当前数据库时变更前拒绝。实例身份（compose 项目、容器名、资源 prefix、edge 网络、数据根、secrets 目录、HTTPS 端口）全部参数化，第二实例可同 daemon 并存；prefix 被异项目占用时启动前拒绝。细节契约见 `docs/specs/release_deployment.md` 与 ADR 017。

## 4. 核心模块与职责划分

|模块|容器/服务角色|职责与安全边界|
|---|---|---|
|**Caddy**|边缘反向代理（常驻）|统一暴露 HTTPS 端口，托管前端静态资源；仅反向代理固定路径（`/api/*`、`/stream/*`），不动态扫描 Docker，不处理视频与信令内容|
|**Control API**|`cbrowser-api` 容器（常驻）|HTTP 接口、用户鉴权、Profile CRUD、Artifact 文件服务。**系统唯一 SQLite 写入者**（开启 WAL 模式，`busy_timeout=5000`）。**严格禁止挂载 Docker Socket**，禁止直接访问 Browser Runtime 私有网络|
|**Runtime Supervisor**|`cbrowser-supervisor` 容器（常驻）|**宿主机唯一持有 Docker Socket 的服务**。仅响应内部受限认证 RPC，负责 Profile 双容器生命周期、网络与 UDP 端口分配；通过受控 UDS 代理 CDP 与事件回传。**严格禁止读写或挂载 SQLite**|
|**Stream Gateway**|`cbrowser-stream-gateway` 容器（常驻）|独立信令网关。维护 Stream Agent 动态注册表；为每个外部 ViewerConnection 建立隔离信令隧道双向转发 SDP 与 ICE；进程异常重启不影响底层浏览器进程运行|
|**Browser Runtime**|`browser-runtime-{id}` 容器（动态）|特定 Profile 的核心运行沙箱。以非 root 运行真实 CloakBrowser、Xvfb、Openbox、PulseAudio 服务（48000 Hz）与 Browser Agent。作为 IPC 供体显式开启 `HostConfig.IpcMode=shareable` 与 1 GiB `/dev/shm`|
|**Stream Runtime**|`stream-runtime-{id}` 容器（动态）|特定 Profile 的远程显示沙箱。加入对应 Browser Runtime 的专属 IPC 命名空间，通过 XShm 共享内存捕获画面；负责音频/视频编码与 WebRTC 传输；分配独立 UDP mux 端口。**严格禁止挂载浏览器用户数据目录**|
|**Browser Agent**|Browser 容器内守护进程|通过专属挂载目录的 `agent.sock`（UDS）暴露受控 RPC：监听 CDP 下载事件、代理授权 CDP 流、上报正常退出事件并自动恢复默认下载策略|
|**Stream Agent**|Stream 容器内守护进程|向 Gateway 主动注册并保持长连接心跳；执行 Profile 级 8/30 FPS 自适应与页面可见性仲裁（全后台暂停捕获，前台恢复）|

## 5. 核心机制与架构契约

### 5.1 对象模型与无租约并发控制

- **核心对象解耦**：
    - `Profile`：保存隐私浏览器的长期配置、指纹种子、代理设置与数据文件。
    - `BrowserRuntime`：代表该 Profile 的真实浏览器进程、窗口、X11 显示与运行状态。
    - `ViewerConnection`：代表一个外部 Chrome 页面与 BrowserRuntime 之间的实时显示和输入连接。
- **废弃排他控制租约**：
    - 彻底废弃早期设计中的独占控制租约（`ControlSession`）、租约代次、抢占等待或接管锁。
    - 一个 Profile 可同时接纳多个外部 Chrome 页面（ViewerConnection）连接，所有客户端均被赋予 `controller` 角色。
    - 多页面并发输入按实际到达 X11 输入系统的物理时序交错处理，无独占排他锁。
- **官方客户端身份薄适配**：
    - 外部 Chrome 页面利用 Selkies 官方 `sessionStorage` 的 `pageTabId()` 发送 `client_tab_id`，利用官方 `resume_key` 支持断网重连；
    - 新标签页采用 `<a target="_blank" rel="noopener">` 打开；
    - 复制标签页时利用同 Origin 的 Web Locks 机制探测并重映射冲突 ID，防止将新页面误认为重连而踢掉原有活跃连接（d007）；
    - 关闭任一外部标签页不会中断同一 Profile 下其他页面的音视频播放，亦绝不关闭底层浏览器进程。

### 5.2 Profile 级单一共享编码管线与 8/30 动态仲裁

- **单一共享管线**：每个 Profile 服务端仅运行一个共享画面捕获与编码管线，单个外部连接禁止独立改写 Profile 级的全局编码帧率（d005, d013）。废弃未经验证的 60 FPS 恒定帧率与 300ms 画面恢复承诺。
- **8/30 FPS 自适应仲裁**：
    - 初始配置 `SELKIES_FRAMERATE=8,8-30`；
    - 画面静止且无交互时，目标帧率降为 8 FPS 以节省 CPU 开销；
    - 只要至少存在一个前台可见连接发生键鼠输入、滚动或画面检测到持续运动（视频/动画），帧率提升至 30 FPS；运动判定依据真实 damage 对照，不依赖 `StreamWatch.encoded_fps`（d005）；
- **页面可见性仲裁**：
    - 单个连接切入后台（`hidden`）时由 Selkies 官方客户端发送每 Peer `STOP_VIDEO` 暂停该连接视频（计划 9.3），页面不向 Gateway 上报可见性或活动；后台页面不得压低前台帧率；
    - 当该 Profile 的所有连接均处于后台或断开时，Stream Agent 暂停服务端画面捕获与视频编码；
    - 任一连接切回前台（`visible`）时，立即恢复画面捕获，先以 8 FPS 重建画面，再根据实际运动自适应提升至 30 FPS（d013）。

### 5.3 本地控制通道、CDP 与下载捕获

- **受控 UDS 通道**：Browser Runtime 仅在容器回环（`127.0.0.1`）监听 CDP，不映射至宿主机或网络。Browser Agent 在宿主专属目录 `/run/cbrowser/runtime/{profileId}/agent.sock` 暴露 Unix Domain Socket。
- **CDP 代理与下载自动恢复**：
    - 经 API 鉴权授权的外部 CDP 自动化流由 Supervisor 经 UDS 代理至 Chrome loopback，Browser Agent 不接受任意 shell 命令（d002）；
    - 浏览器文件下载保存至 `/exchange/downloads/`（映射到宿主 `/data/artifacts/{profileId}/downloads/`），由 Browser Agent 捕获并通知 Supervisor 转发至 API 记入 Artifact 元数据；
    - 外部自动化客户端断开后，Browser Agent 自动重置并恢复默认下载捕获策略（d002）。
- **运行事件持久化与单写者恢复**：
    - 用户在浏览器内直接点击关闭时，Browser Agent 将包含唯一 `event_id` 的退出事件持久化落盘至运行事件目录；
    - API 离线或 Supervisor 重启时，已落盘事件在恢复后由 API 消费并收敛为 `desired_state=stopped`；多轮 reconcile 不会误重新拉起已正常关闭的浏览器（d006）。
    - 浏览器容器的 Docker restart policy 固定为 `no`，所有自愈与重启均由 Supervisor 统一决策。

### 5.4 运行意愿协调（Runtime Coordinator）

- 用户只经 `/api/v1` 修改运行意愿（`PATCH /api/v1/profiles/{id}/runtime/desired-state` 或 stop）。API 先持久化意愿，再由进程内 Runtime Coordinator 经内部认证 RPC 请求 Supervisor 启动/停止该 Profile 的 Browser/Stream；前端与测试都不直调 Supervisor。
- Supervisor 不可达或 RPC 失败时意愿保留，错误写入 `last_coordinator_error` 并经 API 响应与 SSE `runtime_state` 事件显式报告；Coordinator 按指数退避重试直至收敛，成功即清空错误；API 启动时对意愿与观测不一致的 Profile 同样发起收敛。
- Coordinator 需显式配置 `CBROWSER_SUPERVISOR_URL` 与 `CBROWSER_SUPERVISOR_TOKEN_FILE`。缺失时 API 仍可启动但 Coordinator 显式禁用：启动警告一次，且每次意愿变更以 `last_coordinator_error="Supervisor is not configured"` 报告。设置 `CBROWSER_REQUIRE_SUPERVISOR=1` 时缺失配置使 API 启动失败；生产部署（t012）必须启用该模式。

### 5.5 协议兼容与 API 演进

- 内部 UI API 统一规划在 `/api/v1/*`；
- 旧的内部 Profile CRUD 路由已作为破坏性变更移除；
- 旧的 CDP 连接入口已彻底删除：`/api/profiles/{id}/cdp` 兼容适配器与隐藏挂载均不再注册，不保留重定向或旧路由代理；现行唯一入口为 `/api/v1/automation/profiles/{id}/cdp`，完整执行自动化令牌鉴权与控制权围栏。

## 6. 安全、网络与端口矩阵

|来源|目标|允许操作与协议|安全约束|
|---|---|---|---|
|外部 Chrome|Caddy|HTTPS 页面、REST API 与 WSS 信令|强制 HTTPS，Cookie 设置 `HttpOnly; Secure; SameSite=Strict`，校验 CSRF 与 Origin|
|Caddy|API / Gateway|HTTP 反向代理、WebSocket 代理|仅代理固定路径，不动态暴露 Docker 内部接口|
|API|SQLite|SQLAlchemy 2 WAL 读写|**唯一业务数据库写入者**，事务短小，禁止在事务内等待 Docker 或浏览器|
|API|Supervisor|内部受限认证 RPC|生命周期管理、状态查询、CDP 授权隧道；**API 绝不持有 Docker Socket**|
|Supervisor|Docker Engine|Docker Engine API (`/var/run/docker.sock`)|**宿主机唯一持有 Docker Socket 的服务**；强制校验与规范化挂载路径|
|Supervisor|Browser Agent|Unix Domain Socket (`agent.sock`)|健康检查、CDP 授权代理、下载事件与退出事件接收|
|Stream Agent|Stream Gateway|长连接注册与信令隧道|动态注册运行时状态，双向透传 SDP/ICE 消息|
|外部 Chrome|Stream Runtime|WebRTC DTLS-SRTP 媒体传输|直连经专属 UDP mux 端口（`30000–30991`，本机模式发布至 `127.0.0.1`，局域网模式发布至 `0.0.0.0`）；无 TURN 中继（ADR 026 修订 ADR 013）|
|Browser Runtime A|Browser Runtime B|**禁止**|相互隔离，禁止跨 Profile 挂载或访问|
|Stream Runtime A|Stream Runtime B|**禁止**|相互隔离，禁止跨 Profile 挂载或访问|
|运行容器|Docker Socket|**禁止**|所有运行容器严禁挂载 `/var/run/docker.sock`|
|外部网络|容器 CDP 端口|**禁止**|CDP 仅监听回环 `127.0.0.1`，必须经 API 鉴权代理访问|

## 7. 目标部署环境、基准配额与豁免说明

### 7.1 目标部署环境定案

根据 2026-10-27 用户最新明确指令，系统目标部署基准定案为开发者个人电脑本地运行环境，不以公网或远程服务器发布为目标：

- **宿主硬件平台**：MacBook Pro（MacBookPro18,2），Apple M1 Max（10核 CPU，64 GiB 统一内存，macOS 26.5.2，arm64）。
- **Docker 运行后端**：OrbStack Linux aarch64，Docker Engine 29.4.0。
- **容器可用资源配额**：实测 `docker info` 分配 10 CPU，内存配额约 15.66 GiB（`16,819,609,600 bytes`）；严格按此配额规划容器负载，禁止将宿主机 64 GiB 全部计入容器预算。
- **媒体算力预算**：容器内 WebRTC 视频编码按 CPU 纯软件编码基准规划，宿主机 Apple GPU 不计入容器编码加速预算。
- **访问端与网络路径**：同一台 Mac 上的 Google Chrome Stable，经本机网络入口访问 Docker 服务；公网 NAT/跨互联网链路不在本次基准范围。

### 7.2 环境验证豁免说明 (Scope Waivers)

根据用户明确指示（“把这两个跳过”），本次重构对两项受限外部环境正式执行豁免：

1. **公网候选地址与公网 TURN 穿透验证**：标记为 `NOT_RUN / USER_WAIVED`；
2. **原生 Linux x86_64 环境运行验证**：标记为 `NOT_RUN / USER_WAIVED`。

**约束说明**：

- 被豁免项在所有测试报告与需求矩阵中均单列记录，绝不标记为 `PASS`，亦不以此宣称具备公网可达性或 Linux x86_64 原生兼容性；
- 豁免不代表删除对应功能实现：多架构 Dockerfile 与跨平台构建定义保留；TURN/coturn 机制已按 ADR 013 删除，仅在当前阶段免去不可行环境上的实机阻断性验证；
- 阶段验收与后续任务：第 19 章规定的 10 活跃流并发边界、8 小时高压稳定性测试、1000 次长周期输入法/剪贴板压力测试，均属于后续正式阶段（t009+）的验收范围；当前本地技术验证不代表长期 P95 延迟（\<100ms）或高并发无衰退承诺。
