# 需求规范：v2 运行时技术验证契约 (v2_runtime_validation)

## 1. 业务目标与适用范围

本文档定义 CBrowser v2.3 架构重构前在 t001 阶段完成的底层运行时核心技术可观察行为契约、实测验证证据、范围豁免及技术局限性。

**边界声明**：本文档属于技术可行性验证契约，是对底层通信、媒体捕获、容器边界与控制协议实际可达成行为的权威规范；**不构成当前生产系统已实现上述组件的声明**。当前生产代码（`src/backend`、`src/frontend`）仍保持旧单容器与 VNC/RFB 链路基线未变，正式的 v2 生产组件（`cbrowser-api` v1、`cbrowser-supervisor`、`cbrowser-stream-gateway` 等）将在后续独立 task（t002+）中分步实施并逐步替换旧链路。

当前实验只证明文中引用机制；正式服务命名、授权路由和持久Artifact是目标约束，不能由实验代码推断已交付生产功能。Pulse同UID可绕过Cookie，跨Profile依赖专属Socket卷；不能把IPC或Cookie当绝对防护。

## 2. 可观察技术行为契约

### 2.1 容器沙箱、IPC 命名空间与 X11 跨容器捕获契约

- **双容器沙箱拓扑**：每个 Profile 分配两个专属沙箱容器：
    - `browser-runtime-{profileId}`：承载 CloakBrowser 真实浏览器进程、Xvfb 虚拟屏幕（`:99`）、Openbox 窗口管理器、Browser Agent 及虚拟 PulseAudio 服务。
    - `stream-runtime-{profileId}`：承载 Selkies 2.1.0 WebRTC 捕获编码器及 Stream Agent。
- **IPC 供体与共享契约**：
    - `browser-runtime` 容器必须显式配置 `HostConfig.IpcMode=shareable` 并分配 1 GiB `/dev/shm`（d004）；
    - `stream-runtime` 容器通过 `IpcMode=container:<browser-runtime-id>` 加入该专属 IPC 命名空间；禁止使用宿主机 IPC 命名空间；
    - 经由同 Profile IPC 与专属 X11 Socket 卷，`stream-runtime` 实际使用 XShm（`XShmGetImage` / `pixelflux`）以共享内存捕获 1920×1080 画面（s007, d011）；
    - 不同Profile不配置共享IPC；实测错误IPC中的XShmAttach被BadAccess拒绝，不表示持合法Xauthority/Socket的普通XGetImage也被阻断；只有Supervisor获得容器编排权限。
- **X11 与音频安全边界**：
    - 运行容器必须以非 root 用户（UID 1000）运行，启用 `no-new-privileges` 与只读根文件系统（Read-Only Rootfs）；
    - 专属 X11 Socket 与 `Xauthority` 文件存放于 Profile 独立卷；无对应权限的容器连接 X11 立即被拒（s007）；
    - 虚拟 PulseAudio 服务采样率显式锁定为 `48000 Hz`，Stream 容器通过专属共享 Socket 读取音频监视源并捕获实际音频输出（440 Hz / 880 Hz 实测误差 ≤ 1%）（s007, d011）。

### 2.2 多外部 Chrome 页面连接与无租约控制契约

- **三层分离模型**：Profile、BrowserRuntime、ViewerConnection 三者完全解耦；一个 Profile 对应一个长期运行的真实浏览器实例，可同时接入多个外部 Chrome 标签页连接（ViewerConnection）。
- **废弃独占控制租约**：系统不设立排他性控制租约、租约代次或抢占接管等待机制；所有正式客户端均为 `controller` 角色（s004, d007）。
- **客户端身份薄适配**：
    - 外部 Chrome 页面基于 Selkies 官方 `sessionStorage` 的 `pageTabId()` 生成并在握手发送 `client_tab_id`；
    - 页面刷新时保留原有 `client_tab_id` 身份；官方客户端刷新或重建 iframe 会生成新的 `resume_key`，仅在连接内断线重连时以原 `resume_key` 恢复会话（t007 修订语义）；
    - 复制标签页时利用同 Origin 的 Web Locks 机制探测 ID 冲突，检测到冲突后重新生成独立 ID，防止将新页面误认为重连而踢掉原有活跃页面（s004）；
    - 外部 Chrome 通过 `target="_blank" rel="noopener"` 打开新页面。
- **并发观看与并发输入**：
    - 同一 Profile 的两个或多个外部页面均可同时接收 1080p WebRTC 画面并解码（s004）；
    - 多个页面发送的键鼠输入事件在容器内按实际到达 X11 输入系统的时序处理，经 DOM 实际捕获验证（如交错输入 `121212`）（s004）；
    - 关闭任一外部标签页不会中断同一 Profile 下其他页面的视频与音频播放，亦绝不触发关闭远程真实浏览器进程。

### 2.3 共享编码管线与画面捕获动态仲裁契约

- **单一共享编码管线**：每个 Profile 仅运行单一服务端捕获与视频编码管线，禁止单个外部连接独立改写 Profile 级的全局编码帧率（d005, d013）。
- **8/30 FPS 自适应仲裁**：
    - 初始配置 `SELKIES_FRAMERATE=8,8-30`；
    - 画面静止且无交互时，目标帧率为 8 FPS 以节省宿主 CPU；
    - 只要存在至少一个可见连接发生键鼠输入、页面滚动或画面检测到持续运动（如播放视频、Canvas 动画），帧率提升至 30 FPS（s005, d013）；
    - 采用实际 damage 变化对照而非依赖 `StreamWatch.encoded_fps` 作为运动判定依据（d005）。
- **页面可见性仲裁策略**：
    - 单个 ViewerConnection 可在本地暂停自身视频解码，但不影响全局管线；
    - 当前端标签页切入后台（`hidden`）或最小化时，向 Stream Agent 发送官方状态通知；
    - 只要存在至少一个有活动需求的前台可见连接，目标编码维持30 FPS；全部可见页面静止且无活动时允许8 FPS，后台连接不能压低前台帧率；
    - 当该 Profile 的所有连接均处于后台或断开时，Stream Agent 暂停服务端画面捕获与编码；
    - 任一连接切回前台（`visible`）时，立即恢复画面捕获，先以 8 FPS 重建画面，再根据实际运动自适应提升至 30 FPS（s005, d013）。

### 2.4 信令代理、UDP Mux 与媒体中继契约（历史 t001 验收）

> 2026-11-02 更新：本节 TURN/coturn/ICE 换代内容已被 ADR 013 取代；t015 起媒体只走同机 `127.0.0.1` 直连。以下为 t001 时点验收记录。

- **独立 Stream Gateway 与动态隧道**：
    - Stream Agent 启动后向 Stream Gateway 主动注册，建立长连接心跳隧道；
    - 外部 Chrome 访问 Gateway WebSocket 接口（`/stream/{profileId}/signal`），Gateway 动态查找注册表并为每个 ViewerConnection 建立隔离信令隧道，双向转发 SDP 与 ICE 候选（s006, d008）；
    - Gateway 进程异常（如收到 SIGKILL）后重启，Stream Agent 自动重连注册，实际浏览器主进程（PID 及 `start_ticks`）与容器保持存活不中断；外部页面显式重建连接后即可恢复媒体流（s006, d008）。
- **UDP Mux 端口分配**：
    - 每个 Profile 的 Stream Runtime 仅分配并发布一个专属 UDP mux 端口（池范围 `30000–30991/UDP`），该 Profile 的所有 ViewerConnection 均通过此端口直连媒体传输（s004, s006）。
- **独立 RTC 配置拆分与 TURN HMAC 鉴权**：
    - 正式目标由`RtcConfigService`分别为外部 Chrome 客户端与内部 Stream Runtime 生成适配其可达网络的独立 RTC 配置（客户端使用外部可达 TURN 地址，服务端使用容器内部网络地址）（s008, d012）；
    - coturn 强制启用 TURN REST HMAC-SHA1 短期凭证，单侧提供错误密码或过期凭证均被严格拒绝（401 Unauthorized）（s002, s008, d009, d012）。
- **同 PC ICE 代轮换与媒体接管**：
    - 固定 Selkies 2.1.0 SDK 提交缺少原生公开 ICE restart API（d003）；
    - 在同 SDK 进程内通过显式私有接口适配器（维持同一个 RTCPeerConnection / DTLS / DataChannel 对象引用），在交换新 ICE 凭证后通过显式代栅栏（Generation Barrier）关闭旧代传输并由新代接管媒体（s008, d010, d012）。

### 2.5 CDP UDS 本地控制、下载捕获与服务重启恢复契约

- **受控 Unix Domain Socket 控制通道**：
    - Browser Runtime 不暴露公网或容器网络 CDP 端口，仅监听内部回环 `127.0.0.1`；
    - Browser Agent 在宿主独立挂载目录 `/run/cbrowser/runtime/{profileId}/agent.sock` 暴露 Unix Domain Socket，作为唯一受控 RPC 入口；
    - 经授权的外部自动化 CDP 连接由 API 鉴权后通过 Supervisor 经由 UDS 转发至 Chrome loopback，Browser Agent 不接受任意 shell 命令或通用文件读写（s003, d002）。
- **下载事件捕获与策略自动恢复**：
    - Browser Agent 监听 CDP 下载事件，浏览器将下载文件落盘至 `/exchange/downloads/`（映射到宿主 `/data/artifacts/{profileId}/downloads/`）；
    - 外部 CDP 自动化客户端断开后，Browser Agent 自动重置并恢复默认下载捕获设置，确保后续文件下载继续被系统正常捕获入库（s003, d002）。
- **正常退出事件落盘与单写者状态恢复**：
    - CBrowser API 为 SQLite 唯一写入者（WAL 模式，`busy_timeout=5000`）；Supervisor 严禁直接读写业务数据库；
    - 用户在浏览器内直接点击关闭或触发正常退出时，Browser Agent 将包含唯一 `event_id` 与实例标识的退出事件落盘写入持久化队列；
    - API 离线或 Supervisor 重启时，已落盘事件在恢复后被可靠消费并收敛为 `desired_state=stopped`；多轮 reconcile 不会误将已正常关闭的浏览器重新启动（s003, d006）。

### 2.6 原生 IME 组合输入契约

- 外部 Chrome 原生输入法触发的 `compositionstart`、`compositionupdate` 与 `compositionend` 事件，经由 Selkies input data channel 传递官方控制序列至容器端；
- 本阶段通过原生CDP驱动Chrome composition提交（未验OS候选窗），容器端调用XTest或xdotool type将组合后的实际 Unicode 文本（含中文词组、标点与 Emoji）提交至 CloakBrowser 真实 DOM 输入框（s009, d014）；
- 严禁采用模拟剪贴板粘贴的侵入式方式实现中文输入，输入过程中容器剪贴板哨兵保持不变，宿主剪贴板未访问（s009, d014）。

## 3. 环境范围与豁免条款 (Scope Waivers)

### 3.1 用户环境豁免声明

根据 2026-10-27 用户明确执行指示（“把这两个跳过”），本次重构对两项受限外部环境正式执行豁免：

1. **公网候选地址与公网 TURN 穿透验证**：标记为 `NOT_RUN / USER_WAIVED`；
2. **原生 Linux x86_64 环境运行验证**：标记为 `NOT_RUN / USER_WAIVED`。

**说明与约束**：

- 被豁免项在所有矩阵与报告中均单列记录，绝不标记为 `PASS`，亦不以此宣称具备公网可达性或 Linux x86_64 原生跨平台兼容性；
- 豁免不代表删除对应功能代码：多架构 Dockerfile 与跨平台构建定义保留；TURN/coturn 已按 ADR 013 删除，仅在当前阶段免去不可行环境上的实机阻断性验证。

### 3.2 目标基准硬件与运行边界

系统部署目标明确为当前开发者个人电脑上的本地 Docker 环境配合本机 Chrome 访问：

- **宿主硬件平台**：MacBook Pro（MacBookPro18,2），Apple M1 Max（10核 CPU，64 GiB 统一内存，macOS 26.5.2，arm64）；
- **容器运行引擎**：OrbStack Linux aarch64，Docker Engine 29.4.0；
- **容器资源配额**：实测 `docker info` 分配 10 CPU，内存配额约 15.66 GiB（`16,819,609,600 bytes`）；严格按此配额规划，禁止将宿主 64 GiB 全部计入容器预算；
- **媒体算力预算**：容器内 WebRTC 视频编码按 CPU 纯软件编码基准规划，宿主机 Apple GPU 不计入容器编码加速预算；
- **访问端与网络路径**：同一台 Mac 上的 Google Chrome Stable，经本机回环/容器网络访问本地 CBrowser 服务；不依赖公网 NAT 穿透。

## 4. 可复现归档证据与发现映射

所有技术结论均基于真实环境实测产生，相关测试代码与报告已完整归档至 `docs/archive/spikes/`，技术发现沉淀至 `docs/findings/`：

|验证专题|对应归档目录|关联 Finding|验证结论与证据强度|
|---|---|---|---|
|容器沙箱、IPC 与 MIT-SHM|`docs/archive/spikes/s001_selkies_runtime/`<br>`docs/archive/spikes/s007_profile_isolation/`|d004, d011|实测通过：非 root、只读 rootfs、shareable IPC 与 XShm 画面捕获，Pulse 48000 Hz 音频误差 ≤ 1%|
|多页面并发连接与页面身份|`docs/archive/spikes/s004_media_connections/`|d007|实测通过：双 Chrome 页面同时 1080p 解码、并发交错输入、Web Locks 防复制页冲突|
|动态帧率与页面可见性仲裁|`docs/archive/spikes/s005_capture_policy/`|d005, d013|实测通过：单一仲裁锁、8/30 FPS 自适应、全后台暂停捕获、前台恢复重建画面|
|信令网关与进程存活恢复|`docs/archive/spikes/s006_gateway_media_recovery/`|d008|实测通过：Gateway 动态 Agent 隧道、Gateway SIGKILL 重启后浏览器主进程保持存活|
|CDP 本地控制与下载捕获|`docs/archive/spikes/s003_selkies_control/`|d002|实测通过：跨容器 UDS 代理 CDP，下载自动捕获，外部断开后下载策略自动恢复|
|退出事件落盘与单写者恢复|`docs/archive/spikes/s003_selkies_control/`|d006|实测通过：API 离线落盘退出事件，Supervisor 重启重放，防误重启自愈|
|TURN 鉴权与 ICE 代换代|`docs/archive/spikes/s002_selkies_protocol/`<br>`docs/archive/spikes/s008_turn_generation_media/`|d003, d009, d010, d012|本地实测通过：HMAC-SHA1 鉴权、分离 RTC 配置、私有适配器实现同 PC 换代接管媒体；公网豁免|
|原生 IME 组合输入|`docs/archive/spikes/s009_native_ime_input/`|d014|实测通过：官方 input channel 配合 XTest 提交中文/标点/Emoji，容器剪贴板保持不变|

## 5. 局限性与非生产声明

1. **非生产功能声明**：t001 阶段产出均为技术原型验证与架构定案依据。正式的 `cbrowser-api`、`cbrowser-supervisor`、`cbrowser-stream-gateway` 服务代码、Alembic 迁移脚本以及前端 React 19 重构组件**均未合入生产代码库**（截至 t001 验收时点）。
2. **SDK 私有接口维护约束**：Selkies 2.1.0 缺乏原生公开的 ICE restart API。同 PC 换代当前依赖注入私有字段的适配逻辑，属于固定提交（`6ee68a7a`）下的维护约束，后续升级 SDK 时必须重新评估。
3. **长期性能指标待后续验收**：第 19 章规定的 10 活跃流并发边界、8 小时高压稳定性测试、1000 次长周期输入法/剪贴板压力测试，均属于后续正式阶段（t009+）的验收范围；当前本地技术验证不代表长期 P95 延迟（\<100ms）或高并发无衰退承诺。

## 6. 验收标准

- [x] AC-001：两个隔离容器通过同 Profile IPC/X11 传输固定分辨率真实 CloakBrowser 窗口及音频，MIT-SHM 有实际使用证据，不同 Profile 无法访问。
- [x] AC-002：两个独立页面同时观看并输入同一浏览器，刷新、复制、关闭首个页面不影响其他连接，外部页面关闭不停止浏览器。
- [x] AC-003：后台页面不降低前台画面帧率，持续视频不错误降帧，全部后台暂停捕获，恢复可见后重建画面。
- [x] AC-004（t001 时点）：真实信令经过 Agent/Gateway 独立隧道，媒体经本地 UDP mux 正确发布；本地真实网络中以独立客户端/服务端 RTC 配置完成 TURN 换代、relay-to-relay 和单侧无效凭证拒绝。该机制已由 ADR 013 删除；公网可达性单列 NOT_RUN/USER_WAIVED。
- [x] AC-005：自动化通过 UDS 控制真实浏览器并捕获下载，外部客户端断开后恢复下载捕获；Supervisor/API 重启与正常退出事件不误重启浏览器。
- [x] AC-006：macOS OrbStack arm64 实际运行实验，结果逐项映射第18章17项并保留复现命令、失败和未运行记录；原生 Linux x86_64 验证单列 NOT_RUN/USER_WAIVED，不宣称跨平台通过。
