> 与代码冲突时以代码与生效 spec 为准，并须同步修正本文。

# 架构

cbrowser 是面向隐私浏览器与多身份隔离的远程浏览器管理系统。采用单机 Docker 架构，以 Google Chrome 作为唯一官方支持的外部标签页客户端，通过 Selkies 2.2.1 WebRTC 实现低延迟远程画面传输，由独立的 Docker 容器沙箱实现严格的 Profile 隔离。

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
|**远程画面捕获**|Selkies WebRTC|[selkies-project/selkies](https://github.com/selkies-project/selkies)|Release `2.2.1`（t043 由 2.1.0 升级，ADR 022 / s012 spike）|捕获 Xvfb 画面、低延迟软件视频/音频编码、WebRTC 媒体协商与输入控制协议。官方 2.1.0 缺乏原生公共 ICE restart API（d003）；原同 PC 凭证轮换/ICE 代次机制（d010, d012）已由 ADR 013 删除，媒体改为同机直连，不再依赖 Selkies 私有 ICE 接口适配器；采集策略与 X11 键盘行为自 t063 起由受控构建的 Selkies 包承载（固定上游 wheel＋构建期显式补丁，ADR 034），运行时无全局替换、无私有 ABI 门禁|
|**边缘反向代理**|Caddy|[caddyserver/caddy](https://github.com/caddyserver/caddy)|`2-alpine`|自动化 TLS、SPA 前端静态资源服务与固定路由反向代理入口；仅 viewer signal 路由执行边缘授权与 Cookie 剥离|
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
      │     ├── SQLite (WAL, busy_timeout=5000) + Alembic 持久化（named volume `db`，`/data/db/cbrowser.db`，t051）
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

发布由 `scripts/deploy.sh` 单一入口执行，交付物是不可变 release：六个镜像（API、Gateway、Supervisor、Browser、Stream、Caddy）以镜像 ID 固定在 `config/deploy/releases/<release_id>.{env,json}`，连同 compose/Caddyfile/前端产物指纹与数据库迁移版本；compose 全部服务镜像只读 release 变量、无 build 块。发布与回退都以 t026 的 `reconcile_all` + `readiness` 为唯一验收（经 `docker compose exec` 在 Supervisor 容器内执行探针，宿主机不持密钥、无新增端口），验收通过后才原子移动 current/previous 指针。回退在目标 release 缺 readiness 能力、目标 head 与当前 DB 实际 stamp 不等（无降级：同代旧 head 与跨代旧 release 均拒绝，含旧 t042，不做 `ALLOWED_ORIGINS` 兼容）、或工作树 compose 指纹与目标 `compose_sha256` 不一致时变更前拒绝。实例身份（compose 项目、容器名、资源 prefix、edge 网络、数据根、secrets 目录、HTTPS 端口）全部参数化，第二实例可同 daemon 并存；prefix 被异项目占用时启动前拒绝。细节契约见 `docs/specs/release_deployment.md` 与 ADR 017。

### 3.2 部署身份、数据库位置与发布指针（t051）

首次部署身份确定性派生：`instance_id = sha256("cbrowser-instance-v1\0<prefix>\0<data_root>")[:32]`，媒体子网池按 `pool_index = sha256(identity) mod 64` 得 `10.{192+index}.0.0/16`；两者写入 release env 与 manifest。归属判定以 `com.cbrowser.instance-id` 标签值 == 本实例 instance_id 为唯一依据（该键即部署身份键，AC-021）；每轮唯一的运行时实例 id 不走标签，写入容器运行时配置（Stream 环境变量 `CBROWSER_RUNTIME_INSTANCE_ID`、gated entrypoint `--instance-id`、Browser 命令 `--runtime-instance-id`），扫描/查找/回收经 `container_runtime_instance_id` 从配置读取。project 名豁免已删除。控制面数据库在 named volume `db`（`/data/db/cbrowser.db`），字体为独立部署输入（`${CBROWSER_FONTS_DIR}:/fonts:ro`；t080 起改为 fonts named volume，见 3.4）。发布指针为单一 JSON 文件 `config/deploy/release_pointer.json`（`{"current": …, "previous": …|null}`），原子写含文件与父目录 fsync。部署前对数据库做在线备份并记入 manifest，`deploy.sh restore` 可恢复。细节见 ADR 028。同一 prefix 再次部署且 release 记录的数据根与当前数据根指向同一文件系统目录时，复用该 release 的部署身份、媒体池与 edge 子网；macOS 目录大小写改名不会改变资源归属。

### 3.4 Linux 原生运行存储（t080）

正式运行数据全部位于按部署前缀命名的 Linux named volume（ADR 029，替代 ADR 028 的同路径宿主挂载技巧）：`<prefix>-db`（控制面 DB，独立不变）、`<prefix>-data`（Profile userDataDir、Artifact、预览、runtime-events/outbox、快照、engine/GeoIP 缓存与持久控制状态）、`<prefix>-fonts`（字体集，subpath `<platform>/<set_id>`）、`<prefix>-runtime`（运行期文件：`<profile_id>/…`、`gates/…`、`sockets/…`、`.secrets/…`、`policy-agents/<slot>/…`（Policy Agent 的 UDS socket 目录，t082））。API 与 Supervisor 的容器内逻辑路径不变（`/data`、`/fonts`、socket 根）；Supervisor 的 data_root 成为纯容器内逻辑路径，不再是宿主路径。消费方挂载一律经 `storage_layout.MountPlanner` 把已校验本地路径解析为 `(volume, subpath, target, read_only)` typed mount：Browser 只得自身 Profile 精确 subpath，Stream 不得 Profile/Artifact/字体，字体只读且只给绑定集合；解析不出受管卷归属的来源在构造期拒绝，不存在宿主 bind 回退。宿主数据/字体目录只作迁移源与显式导入/导出源；迁移由 `scripts/storage_migration.py` 以只读盘点、写者/容量/归属校验、恢复点可恢复验证、staging 拷贝、逐文件 SHA-256、journal 分阶段切换与幂等恢复/回退完成，源目录只读保留。release env/manifest 记录卷身份（`CBROWSER_*_VOLUME` / `storage_volumes`）而非宿主路径。跨 DB/data/fonts 的切换不是单一原子事务，靠 journal + 旧集保留收敛（同 3.3 的恢复点口径）。

### 3.5 字体资产目录与验证权威（t081）

字体集是发布后不可变的资源（ADR 030）：受信发布者经导入 CLI 完整验证后以内容寻址 set_id 原子发布进 fonts 卷；API（唯一 DB 写者）在启动接管与显式审计时把验证结论持久化到资产目录 `font_set_assets`（平台、来源/版本、内容身份、文件数、detection 覆盖、验证状态/时间、资源修订 `revision` 与审计围栏 `state_seq`）。runtime REST/SSE、字体列表、默认集选择与 Profile 绑定校验只读目录记录，成本与字体字节数无关；审计有界并发（2）、同集去重、回执按 `state_seq` 围栏条件写入，迟到回执不覆盖已应用的新回执/接管（发布/修复只写文件、经后续审计生效）。运行状态的字体口径以运行实例绑定的配置版本为准。Supervisor 对实际挂入集的启动验证每实例只执行一次（见 supervisor.md），细节与旧实时扫描契约的废止见 ADR 030。

（t075 补充，ADR 040）Profile 的字体绑定改后端托管：服务在创建、克隆与切换平台时按目录默认规则写定绑定，字体根已配置时（一切真实部署）平台无 verified 集则写入前失败，生产数据库中不再产生无绑定的新 Profile（未配置字体根的进程创建可暂无绑定，但启动/就绪失败封闭，真实部署不可达）；迁移 `0013_profile_identity.py` 把存量行与历史快照一次性改写到新形状（删 `gpu_family`、配色收敛 light/dark、按旧有效暴露派生 `include_cjk_fonts`、未绑定行补默认集），不可等价映射在改写前整体阻塞。实例级字体就绪由 Runner 在启动前对实际挂载做一次真实验证（manifest/哈希 + `fc-list` 枚举）并把结论持久化进 `runner_info`，Agent 与 API 只读结论；Supervisor 构造字体挂载时校验源目录存在，杜绝空挂载零字体启动。

### 3.3 环境恢复点（t066）

环境级备份恢复的唯一契约是恢复点（`scripts/restore_point.py`，经 `deploy.sh env-backup` / `env-restore` 以一次性 API 镜像容器挂载 named volume `db` 与数据根运行）：一个恢复点 = 同一静默时刻的控制面 DB（SQLite 在线 backup + integrity_check + schema stamp）与全部 Profile 用户数据目录（逐文件 SHA-256 manifest），外加只记文件名/大小的凭据前提清单。备份在 DB 记录存在实际写者时拒绝。恢复先把整套内容 staging 到目标旁并全量校验（哈希/完整性/版本一致/空间），再按 journal 逐项 rename 成套切换；跨介质（DB 卷与数据根）的切换不是单一原子事务，靠 journal + 旧集保留（`.pre-restore-<switch-id>`）保证任一中断点收敛为完整旧集或完整新集，下一次调用先回滚未完成切换。旧的「tar data/instance + db_restore.py 直覆」不构成环境恢复（tar 漏 named volume DB、直覆不校验），仅保留 db_backup/db_restore 作发布流程的 DB 单件备份。契约细节见 `docs/specs/release_deployment.md` 的 t066 节。

## 4. 核心模块与职责划分

|模块|容器/服务角色|职责与安全边界|
|---|---|---|
|**Caddy**|边缘反向代理（常驻）|统一暴露 HTTPS 端口，托管前端静态资源；仅反向代理固定路径（`/api/*`、`/stream/*`），不动态扫描 Docker，不处理视频与信令内容。外部 `/api/v1/internal/*` 一律 404；只有 `/stream/*/signal` 先删伪造授权头、经 API 解析会话，再删除 Cookie 后代理到 Gateway|
|**Control API**|`cbrowser-api` 容器（常驻）|HTTP 接口、用户鉴权、Profile CRUD、Artifact 文件服务；viewer 握手时经内部边缘解析端点复用 `AuthService.authorize_viewer` 作唯一会话/Origin/Profile 判定，并签发短期 viewer grant。**系统唯一 SQLite 写入者**（开启 WAL 模式，`busy_timeout=5000`）。**严格禁止挂载 Docker Socket**，禁止直接访问 Browser Runtime 私有网络|
|**Runtime Supervisor**|`cbrowser-supervisor` 容器（常驻）|**宿主机唯一持有 Docker Socket 的服务**。仅响应内部受限认证 RPC，负责 Profile 双容器生命周期、网络与 UDP 端口分配；通过受控 UDS 代理 CDP 与事件回传。**严格禁止读写或挂载 SQLite**|
|**Policy Agent**|每目标 netns 一个容器（常驻，t082 / ADR 039）|与 Browser/Stream 目标同 netns 的受限策略执行与观测进程：仅 NET_ADMIN、只读根、无 Docker Socket 与用户数据挂载，只经版本化 UDS 协议接受 Supervisor 的 health/resolve/install/inspect/fail_close 指令，身份在创建时绑定且运行期不可变|
|**状态协调**|API ↔ Supervisor（t083 / ADR 040）|最小批量状态协议：API 以服务鉴权提供仅含协调字段的快照（键集分批）与推送通知（epoch + state_revision 围栏），Supervisor 以状态缓存为唯一意愿视图（单飞快照、30 秒兜底、40 秒权威窗口）；runtime GET/列表/SSE 只读已维护观测，健康观察归各服务控制组件，Compose 无 Docker healthcheck|
|**Stream Gateway**|`cbrowser-stream-gateway` 容器（常驻）|独立信令网关。维护 Stream Agent 动态注册表；viewer 握手只在本地验证 API 签发的短期 grant、Profile 绑定与 Origin，不接收或解析管理会话 Cookie；为每个外部 ViewerConnection 建立隔离信令隧道双向转发 SDP 与 ICE；进程异常重启不影响底层浏览器进程运行|
|**Browser Runtime**|`browser-runtime-{id}` 容器（动态）|特定 Profile 的核心运行沙箱。以非 root 运行真实 CloakBrowser、Xvfb、Openbox、PulseAudio 服务（48000 Hz）与 Browser Agent。作为 IPC 供体显式开启 `HostConfig.IpcMode=shareable` 与 1 GiB `/dev/shm`；代理凭据文件以只读挂载进本容器，CloakBrowser 通过 SDK `proxy=`、WebRTC/QUIC 加固参数及有代理 `OUTPUT -j DROP` 网络策略直连上游代理（ADR 038）|
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
- **长驻 Browser 与连接恢复的职责边界（t061）**：
    - BrowserRuntime 的存续只由运行意愿（desired_state）与 Supervisor 决策决定；ViewerConnection 的连接、断开与恢复是纯呈现/传输层事件，前端阶段收敛（信令异常后媒体健康即回 connected）只改页面呈现，不触发 Browser 的启动、停止、重置或数据删除。
    - 不存在按无人连接或时间触发的自动回收：全部 viewer 断开后环境、已有网页与浏览器数据继续保留，无 idle 期限、绝对期限或 viewer TTL；再次连接直接恢复观看。
    - 无人连接时唯一的服务端行为是 5.2 的采集暂停：所有连接均后台或断开时 Stream Agent 暂停画面捕获与视频编码，任一连接回前台即恢复；暂停采集不等于停止环境。

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
- Profile 拥有部署内唯一、永不复用的 `display_number`（0001…）；Supervisor 用它命名沙箱容器 `<prefix>-<NNNN>-browser|stream`，写 `com.cbrowser.profile-number` 与聚合标签 `com.docker.compose.project=<prefix>-profiles` / `service=<NNNN>-browser|<NNNN>-stream`（t051 前为 `service=browser|stream`），使 Docker UI 单组展示全部沙箱且与产品编号对应（t050）。
- 存量沙箱恢复（Supervisor 重启或部署升级重建 Gateway/Supervisor）不依赖 Gateway 可见性或注册读数：按容器 label 与 API instance fence 判定实例一致后恢复端口与 session，并在同一轮扫描内完成媒体网络附着；Gateway 按 label 动态解析，媒体挂载收敛与内存 session 解耦（t049）。
- Coordinator 需显式配置 `CBROWSER_SUPERVISOR_URL` 与 `CBROWSER_SUPERVISOR_TOKEN_FILE`。缺失时 API 仍可启动但 Coordinator 显式禁用：启动警告一次，且每次意愿变更以 `last_coordinator_error="Supervisor is not configured"` 报告。设置 `CBROWSER_REQUIRE_SUPERVISOR=1` 时缺失配置使 API 启动失败；生产部署（t012）必须启用该模式。

### 5.5 协议兼容与 API 演进

- 内部 UI API 统一规划在 `/api/v1/*`；
- 旧的内部 Profile CRUD 路由已作为破坏性变更移除；
- 旧的 CDP 连接入口已彻底删除：`/api/profiles/{id}/cdp` 兼容适配器与隐藏挂载均不再注册，不保留重定向或旧路由代理；现行唯一入口为 `/api/v1/automation/profiles/{id}/cdp`，完整执行自动化令牌鉴权与控制权围栏。
- 控制面严格契约（t069，零兼容）：服务间错误只有 `ErrorResponse` 一种合法形状，消费方经 `cbrowser/shared/error_response.py` 唯一解析；旧 `detail` 形状、裸文本与缺字段响应一律是协议错误（coordinator 记稳定标记、Gateway 可见性查询判未知、控制调用抛 `control_protocol_error`），不作业务结果。observed-state 上报单次定论：422 不再触发去字段降级重发，失败不伪报收敛。部署资源归属只认 `com.cbrowser.instance-id` 标签与配置的部署实例 ID 相等：缺失、为空或不匹配即不认领、不删除，Supervisor 未配置部署身份时不认领任何资源，且部署身份缺失在启动期（任何 Docker 变更前）即失败。持久化输入单一严格校验：`launch_args` 只有 `validate_launch_args` 一处校验，存量非法值在 Profile 加载时明确拒绝并指名 Profile，不静默过滤或改写。viewer 身份只有宿主页 `?profileId=` 一个文档化通道：缺失/空、未文档化的 `profile_id` 参数与 `__CBROWSER_PROFILE_ID__` 全局注入全部拒绝，不存在 "default" 身份。文档化的例外保持不变：幂等键三源（`Idempotency-Key` / `X-Operation-ID` / `operation_id`）及优先级、locale/timezone 的 None 自动推导。

### 5.6 跨服务中立模块与运行镜像边界（t062）

被两个以上服务镜像消费的规则与实现只有一份权威，归属中立包 `cbrowser/shared/`：端点与 Origin 归一（`endpoints`）、Agent 凭证（`agent_credentials`）、原子写（`atomic_write`）、per-profile 锁注册表（`profile_locks`）、投递分类（`delivery`）、实例 fence（`fencing`）、出口探针 I/O（`egress`）、客户端 IP 解析（`client_ip`）。Gateway 与 Supervisor 互不 import；`shared` 除 `secret_files` 叶子外不 import 任何 cbrowser 模块，保证它在每个镜像内可独立导入。领域层只承载纯值对象与规则：认证返回领域会话对象 `AuthenticatedSession`，路由与依赖不接触 ORM `SessionModel`；`domain/egress_observation` 只留观测值对象与时效规则，探针的 httpx/GeoIP/文件 I/O 在 `shared/egress`。Supervisor 控制端口只有一个权威值 `shared.endpoints.DEFAULT_SUPERVISOR_PORT`（8005），runner、控制客户端、compose 与就绪探针全部派生或与之对齐校验。运行镜像按包粒度 COPY 后端代码（API 镜像为 `cbrowser` 整包 + `migrations`），禁止逐文件复制 shared 或跨服务借文件；镜像文件闭包由 `tests/unit/test_t062_image_closure.py` 按 Dockerfile 组装文件树实际导入验证，依赖方向由 `tests/unit/test_t062_boundaries.py` 守护。不同进程的锁注册表实例互不感知，per-profile 锁只是进程内协调、不是跨进程互斥；API 唯一 SQLite 写者、Supervisor 唯一 Docker Socket、Gateway 无 ORM 三条边界不变。

### 5.7 Viewer 边缘授权与 CDP 边界（t064）

- viewer 授权分两跳且秘密不共用：Caddy 对 `/stream/{profileId}/signal` 删除客户端自带的 `X-cbrowser-Authorized-Profile` 与 `X-cbrowser-Viewer-Grant`，再以 `edge_proof_key` 向 API 的 `GET /api/v1/internal/edge/viewer-authorize` 发起 `forward_auth`；API 校验边缘证明与转发 URI 后，由 `AuthService.authorize_viewer` 唯一判定会话、Origin 与 Profile，并以 `viewer_grant_key` 签发 60 秒 HMAC grant。grant claims 仅含版本、Profile、随机 grant id 与到期时间，不含会话标识。
- Caddy 只把 API 回注的 authorized Profile 与 grant 复制到待代理握手，并删除整个 Cookie 头；Gateway 使用同一 `cbrowser/shared/viewer_grants.py` 在本地验签、验期与验 Profile 绑定，再检查 Agent 与 runtime 就绪。每次新握手都重走 `forward_auth`，登出或撤销在下一次握手生效。直连 Gateway、伪造授权头或只有 Cookie 的请求都没有有效 grant，不能越权。
- 边缘解析端点只存在于内部 schema 与服务网络：渲染后的 Caddyfile 对外部 `/api/v1/internal/*` 显式 404，Caddy 的 `forward_auth` 子请求直达 API upstream、不重入外部站点路由。`/stream/agent/register` 不套用 viewer 授权，继续使用独立 Agent 凭证与 API runtime 绑定校验。
- CDP 本体只由 Browser 容器以临时端口监听 `127.0.0.1`，端口不发布且不向普通 viewer 披露。唯一外部自动化入口仍是带 automation token 与控制权围栏的 `/api/v1/automation/profiles/{profileId}/cdp`；管理会话经专用 Automation 状态端点才可看到 `cdp_ws_path`，普通 Profile 响应不含该字段或 token。引擎内以域名 Host 发起的回环请求（DNS rebinding 的可观察形态）与跨 Origin CDP WebSocket 必须由真实引擎负向测试拒绝。

### 5.8 集合读取投影与全局摘要（t076）

- 列表读是服务端集合投影，不是全量拉取后客户端拼装：`GET /api/v1/profiles|proxies|groups/collection` 在持久层完成搜索 / 筛选 / 稳定排序 / 总数 / 有界分页（`page_size` 钳制 1..100）；有界候选 `…/candidates`（`limit` 钳制 1..50）与代理国家→城市范围 `GET /api/v1/proxies/countries`（键为稳定国家代码）供后续交互使用。
- 代理引用聚合一次取 3 条 SELECT（当前引用、全部运行行、绑定配置版本 `IN` 查询），与代理数 × 运行绑定数无关；`list_proxies` 在 20/100/1000 规模下 SELECT 数恒定。
- 运行状态只读一次批量摘要 `GET /api/v1/profiles/runtime-summary`（全部环境状态 + 运行总数）；SSE `runtime_state` 事件带 `config_version` 围栏，旧版本/旧实例迟到事件丢弃，重复事件无副作用且不触发列表重取，有效事件原地更新运行缓存与摘要缓存——摘要更新不依赖单环境运行缓存，围栏按两份缓存中现有的那份判定。环境集合页的行自带分组名/颜色与代理名（服务端按页批量查名），筛选选项读有界候选；任何变更路径失效列表键时同步失效集合键前缀。前端缓存职责：列表只读集合页与摘要，详情按需单读，批量操作目标按稳定 ID 与明确目标快照确定，当前页全选与全部匹配项语义分开。

### 5.9 停止后删除协调与故障恢复（t078）

- 删除由 API 内 `ProfileService` 编排（不新增进程/服务）：删除意图落 `profile_deletions` 表后由进程内驱动器推进，推进全程持有该 Profile 的生命周期锁，与启停、配置更新串行；驱动器对同一意图单飞，进程重启后由 lifespan 恢复未终结意图（与 Artifact 删除意图恢复同一模式）。
- 协调边界：stopping 阶段只经既有运行意愿通道置 stopped 并轮询观测/写者状态，不直接操作 Docker（Supervisor 唯一持有者边界不变）；超时即失败，不强行清理。cleaning 阶段先复核实例围栏（停止时快照 vs 当前绑定），再调用 Artifact 服务、文件系统与仓储完成清理；每步结果写入意图 `detail`，失败保留在失败阶段等待重试。
- 恢复语义：意图是删除结果的唯一事实来源，客户端断开不影响推进；查询端点（批次/单项）只读意图表。旧单删端点同步驱动同一状态机，不存在第二条删除路径。

### 5.10 服务端异步作业编排与轻量出口探测（t094，t095 补统一状态管道与并发）

- **统一状态管道（t095 AC-002）**：成员每次状态迁移只发一次 `probe_job_progress` SSE 事件：服务端在成员终态写库后推送携带只读 `processed` 的权威作业快照，前端同一处理器既把快照写入作业读模型缓存，又使代理列表查询失效重取——观测已先于事件落库，失效即取回逐条最新结果。行状态随事件逐条刷新，不靠固定间隔轮询；代理列表 Submission 时的一次失效只用于冻结作用域初值。

- **作业为编排权威**：代理测速不复用旧的客户端串行循环与同步探测端点（已删除）。提交 `POST /api/v1/proxies/probe-jobs`（`proxy_ids` 或 `filters` 二选一）只做解析与冻结目标 ID 集合的短请求，立即返回 `202` + `job_id`；`GET /api/v1/proxies/probe-jobs/{job_id}` 读权威读模型，SSE `probe_job_progress` 推送进度。作业与成员持久化在 `proxy_probe_jobs` / `proxy_probe_job_members` 两张表（增量迁移 `0015_proxy_probe_jobs.py`，只进不退）；作业持 `state`（`running` / `done`）、`total` / `completed` / `failed`，成员持 `state`（`pending` / `ok` / `failed`）、脱敏 `error_code` 与观测关联。

- **冻结作用域与单一状态源**：作业作用于提交时解析出的过滤后目标 ID 集合，分页只影响视图、不参与作用域；行状态只由观测表的 `observation_status === "pending"` 表达，批量进度只由作业读模型与 SSE 表达，前端不持有并行进度状态。观测表 `proxy_egress_observations` 仍是逐项结果唯一存储，重复提交、自动探测与迟到结果不得覆盖在途作业归属，卡住的 pending 按预算收敛为终态；页面刷新由读模型恢复进度，API 进程重启按显式规则恢复或终结并暴露失败。

- **轻量探测取代沙箱**：探测在 API 进程内执行（`services/egress_probe.py` + `shared/egress.py`），凭证由服务端从已存端点装载、不进命令行，显式 `proxy=` 且 `trust_env=False` 杜绝直连回退，回显目标限于固定白名单且私有/保留/回环地址拒绝，出口 IP / 城市取自身回显与本地 GeoIP，`latency_ms` 只计一次成功 HTTP 往返。不再创建 helper 容器、专用 bridge 或探测专属 Policy Agent，也不产生任何 Docker 网络 / 策略资源事件。`proxy_enforced=True` 双栈 `OUTPUT -j DROP` 只约束配置代理的 Browser/Stream 运行策略（ADR 038），与探测路径独立；探针只提供测速与出口信息展示，隔离 / 防泄露验证由单元与真实 Docker E2E 承担（见 [testing](testing.md)）。

- **GeoIP 依赖显式注入（t096）**：`InProcessEgressProbeRunner` 在构造时必须注入 `GeoIpLookup`，探测 I/O 不再隐式读取 `CBROWSER_GEOIP_DB` / `CBROWSER_GEOIP_CACHE`。唯一配置解析点是 API 组合根（`api/app.py` 调 `shared/egress.resolve_geoip_db_path()` 一次），结果经 `RuntimeCoordinator(geoip_db_path=...)` → `egress_probe_runner()` 注入 runner。未配置路径时 `GeoIpLookup` 持空路径并判 `geoip_db_missing` 资源类失败，不在探测期崩溃或回退到环境变量；compose 按「谁用谁配」分别给 api 与 supervisor 声明 GeoIP 缓存路径，指向同一物理 mmdb。

- **职责边界不变**：API 仍是唯一 SQLite 写入者，作业表随业务库由 API 独占写入；Supervisor 仍是唯一 Docker Socket 持有者，不参与探测。环境批量 start / stop / moveToGroup 复用同一作业提交与进度组件，与已有批量删除意图状态机并存、边界清晰。

- **受配额并发执行（t095 AC-003）**：`ProfileService._drive_members` 是代理测速与环境批量的唯一驱动：成员探测在共享 `asyncio.Semaphore`（上限取 `CBROWSER_PROBE_JOB_CONCURRENCY`，默认 8）内并行，超限排队；单成员异常就地收敛为 `failed`，不阻塞其他成员；计数在 `asyncio.Lock` 内串行推进，SQLite 写仍走 `write_transaction` 的 `BEGIN IMMEDIATE`，多作业并发不串线、不 BUSY。

## 6. 安全、网络与端口矩阵

|来源|目标|允许操作与协议|安全约束|
|---|---|---|---|
|外部 Chrome|Caddy|HTTPS 页面、REST API 与 WSS 信令|强制 HTTPS，Cookie 设置 `HttpOnly; Secure; SameSite=Strict`，校验 CSRF 与 Origin|
|Caddy|API / Gateway|HTTP 反向代理、WebSocket 代理|仅代理固定路径，不动态暴露 Docker 内部接口；signal 路由先以边缘证明调用 API 解析端点，Gateway 方向只带 API 回注的 grant 上下文且不带 Cookie|
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

部署期网络配置（t054）：Caddyfile 在部署期由 `network_config render` 按部署端口渲染，`caddyfile_sha256` 为渲染后产物的 SHA-256（必填 64 位小写十六进制）；回退时按目标 release 记录的端口重渲染并校验与目标 manifest 一致。已应用网络版本（`AppliedNetworkAccessVersion`）与运行时应用链已删除，无空哈希豁免路径。

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
