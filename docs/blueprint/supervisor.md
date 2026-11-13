# Runtime Supervisor

本模块实现 Profile 生命周期协调：Supervisor 是唯一挂载 Docker Socket 的服务，负责拉起、停止与收敛 Browser / Stream 实例，并经控制面接收 API 的指令、上报实例绑定、观测与事件。

## 权限与数据所有权

Supervisor 是唯一挂载 Docker Socket 的服务，不挂载元数据 SQLite，不导入数据库实现。API 是唯一业务数据库写入者；Supervisor 经 `/api/v1/internal/supervisor` 认证 RPC 读取 Profile、不可变配置版本及运行状态，上报实例绑定、观测与事件。

API/Supervisor 控制面使用外部文件提供的 Bearer 凭证，至少 32 UTF-8 字节。Gateway 控制面使用独立凭证文件。Agent 主密钥保留在 Supervisor/Gateway；每个 Stream 只挂载从 Profile 与 runtime_instance_id 派生的认证文件，不能获得主密钥或其他实例凭证。所有控制端口只用于内部网络，不直接公开。

`PathValidator` 约束统一数据根及 Profile 归属：用户数据、runtime、事件、Artifact、引擎与 GeoIP 缓存不得逃逸。固定 Profile 目录不能用符号链接替换为其他 Profile 目录。快照、派生凭证、操作日志与事件文件采用原子替换、文件与目录 fsync；写入目标本身为符号链接时替换链接，不跟随其写入目标。此约束不构成对恶意宿主机并发修改目录或任意 Docker Socket 使用者的安全承诺。

## 容器与网络

每个 Profile 创建 Browser/Stream 两个容器，均非 root、只读根、cap-drop ALL、restart policy `no`。Browser 提供 shareable IPC 和 1 GiB `/dev/shm`；Stream 只共享对应 Browser IPC/hostname，挂载 X11 socket 文件、Xauthority、Pulse 目录及实例凭证。Stream 不挂载用户数据、Browser Agent socket 或 Docker Socket。

Browser 只加入所属 egress bridge；Stream 只加入所属媒体 bridge。共享 Gateway 动态加入媒体网络，实际地址明确传给 Stream；不再有 coturn（ADR 013）。网络复用与删除要求名称和 managed-by/profile/prefix 标签匹配。清理遇未知端点必须失败，不能强制断开；失败回滚只撤销本次新建连接。

媒体网络自 t026 起使用固定端点规格（d029）：Supervisor 从可配置地址池（默认 `10.251.0.0/16`、每 Profile 一个 /24）显式分配 subnet 与 ip_range（subnet 低半段），Gateway 固定附着在 subnet 内、range 外的端点（广播地址前一可用地址），规格以网络标签记录（`com.cbrowser.media-spec=fixed-endpoint-v1` 等）。分配必须避开全部既有 Docker 网络与宿主路由；池耗尽、subnet 冲突、端点被其他容器占用或标签/IPAM 不一致都显式失败，绝不退回 Docker 自动 subnet 或随机地址。既有不合规网络不做原地修改（Docker 不支持），由收敛器经 Stream-only 替换重建迁移。Gateway 身份每轮按标签（prefix + managed-by + role=gateway）重新解析，配置的静态容器 ID 只作兜底；Gateway 被替换后在同一固定端点重新附着，不重建 Browser/Stream。

引擎初始化通过临时 helper 完成，然后以只读挂载交付 Browser。SDK 初始化显式 pin `get_chromium_version()`，与 Runtime 使用相同引擎版本；不在 helper 失败后用盲目重试掩盖初始化错误。

## 部署身份、扫描归属与媒体网络超时（t051）

- **部署身份**：部署时为实例生成确定性 `instance_id`（`sha256("cbrowser-instance-v1\0<prefix>\0<data_root>")[:32]`），经 `CBROWSER_INSTANCE_ID` 传入 Supervisor；compose 服务与 Supervisor 创建的全部沙箱、helper、网络都带 `com.cbrowser.instance-id=<instance_id>`（部署身份键）。每轮启动唯一的运行时 id 不走标签：写入容器运行时配置（Stream 环境变量、gated entrypoint、Browser 命令参数），扫描/查找/回收从配置读取。
- **扫描归属**：容器扫描、helper 清理、Gateway 扫描与 Browser 查找都以「instance-id 标签值 == 本实例 instance_id」为唯一归属依据；缺失或不符的资源不认领、不删除、不清理。未配置 deployment id 时沿用旧行为（prefix 下全部资源视为己方）。
- **前缀规则**：部署输入的资源 prefix 须匹配 `^[a-z0-9][a-z0-9_]*$`（不含连字符），默认部署前缀 `cbrowser-t005`；Supervisor 启动对显式提供的前缀（`--prefix` / `CBROWSER_PREFIX`）在持锁与任何 Docker 调用前校验，DockerAdapter 构造不校验（收到的已是校验后的值或编译内默认）。纯标签 helper 不校验（直接构造标签的测试不受影响）。
- **媒体网络超时**：Docker 网络调用以超时为限（默认 30 秒，`CBROWSER_DOCKER_NETWORK_TIMEOUT` 可配）；`_ensure_media_network` 的分配锁只覆盖 get+分配+预留阶段，`networks.create` 在锁外经线程 join 超时执行，挂起时该次启动以明确错误失败，不阻塞其它 Profile。并发分配经预留子网集保证不同子网，成功/失败均释放预留；创建冲突为错误，不重试。同一 Profile 的创建在生产路径上由 core 的 per-profile 锁串行化。

## 平台字体集只读挂载与失败封闭（t041）

平台专有字体集不属于任何镜像，只存于宿主 `CBROWSER_FONTS_DIR/{platform}/{set_id}/`，经 `.worktreeinclude` 供各 worktree 共享同一份。Supervisor 按 Profile 绑定的配置版本快照，只把该字体集目录只读挂载进 Browser 容器的 `/run/cbrowser/fonts/{platform}/{set_id}`，挂载点位于 fontconfig 默认扫描路径之外；不挂载整个字体根目录，也不把字体集挂给 Stream 容器。

启动前按绑定快照校验字体集存在且文件与 `manifest.json`（来源、来源系统版本、逐文件 sha256）一致：缺失或不一致即启动失败封闭并报告 `font_set_unavailable`，不降级为无字体启动。`font_set_id` 为 null 时不做挂载，回退镜像内基础开源字体可见、正常启动，由 runtime 状态报告平台字体未配置并在 `missing_fonts` 标明当前暴露 Linux 基础字体。字体集本身不在本系统内删除。

## 生命周期与恢复

API 保存 `desired_state`、实例、失败计数与阻断状态。启动前必须已有 running 意愿并读取不可变配置；配置请求失败不能猜测默认配置继续启动。按 Profile 串行创建，分配 30000–30991 范围独立 UDP mux 端口，容器内外端口一致。UDP mux 范围由 `udp_mux_bounds()` 在进程启动时解析一次（t055），protocol 校验、网络策略、分配器与 runner 共用；env 为空回默认值，非法值启动即失败。

停止命令携带 `operation_id` 与目标 `runtime_instance_id`。操作日志允许同一请求重放；相同操作 ID 配不同请求返回冲突。旧实例停止重放不能终止新实例。停止顺序为标记 unavailable/stopping、Gateway 断开 Viewer、停止 Stream、停止 Browser、移除所属网络，最后回收端口；清理失败不释放仍占用的端口。

Native 事件按目录归属、Profile 与实例核对后进入持久 spool。事件 ID 只作为协议身份，文件名使用哈希，不能充当路径。API 按事件 ID 去重并核对实例/配置代际；ACK 日志跨重启保留，已送达事件不反复上传。API 离线时保持健康运行容器，恢复后重放。

`RecoveryCoordinator` 根据 API 状态与 Docker 扫描协调异常重试。首次异常之后分别等待 2/10/30 秒，共三次自动重试；三次均失败时，原始异常总数 `failure_count=4` 并阻断。调度以 API 持久时间为依据，Supervisor 重启不能重新开始完整等待。正常退出和用户 stopped 意愿不重试；手动解除阻断经 API 幂等意愿事务执行。启动失败由 Core 上报一次稳定事件，协调器不重复计数。

Supervisor 控制目录持进程级 flock，SIGKILL 由内核释放。Supervisor 正常退出仅取消自身后台任务，不终止健康 Runtime；重启时核对 API 意愿、实例及 Docker 标签和实际端口，再恢复本地会话。单纯看到容器对象或端口配置不等于 Runtime 已就绪。Browser 就绪还须核对当前 Profile、实例、配置版本和 PID，Stream 必须完成 Gateway 注册。恢复时 Agent 健康未知，session 预置为 starting 而非 running，健康确认后才升级为 running，CDP 代理在此期间拒绝连接（t055）。注册宽限自恢复时刻起算 90 秒，Gateway 不可见不重置宽限（恢复专属标记；注册丢失过渡的宽限仍在生命周期边界丢弃，同一名字重启的 fresh Stream 立即替换）；宽限内到达的新注册立即替换恢复状态，不等宽限结束。

稳态持续收敛（t026）：同实例运行对在每轮扫描（容器/网络事件唤醒或 30 秒兜底）中依次校验媒体网络合规、Gateway 固定端点附着、Stream 与 Browser 的实际 netns 规则（与渲染规格全等比对，而非假定安装成功）与 Agent 注册状态，只修复漂移的那一层。Stream 层问题（网络不合规、Stream 策略漂移、可修复的未注册）走 Stream-only 替换：保留 Browser 容器、IPC/X11、页面与 Profile 数据、同实例凭证与 UDP 端口，替换在有界预算内进行（同实例窗口内最多 3 次），预算耗尽报 transport failed。Browser 策略漂移则立即 fail-closed（双族 DROP）并报告 error，绝不自动 teardown。注册被 Gateway 以协议级原因（版本/凭证/身份/载荷/实例未绑定）拒绝时不做任何替换、直接报 failed；Gateway 本身不可达时只呈现 recovering、从不重建 Stream。恢复判定感知注册状态：Stream 容器在跑但 Agent 已知未注册时不视为活跃对。API 失联期间只允许按标签/实例一致性恢复媒体附着，不执行任何生命周期动作。Supervisor 控制面另提供 `POST /supervisor/v1/reconcile`（一轮全量收敛）与 `GET /supervisor/v1/readiness`（对全部 desired=running Profile 逐项校验实例/进程/附着/实际策略/注册，任一未知即未就绪并返回逐 Profile 脱敏诊断），宿主机经 `docker compose exec` 在容器内用 `cbrowser.supervisor.control_client` 调用，不新增发布端口或反向代理路由。

分层观测（t026）：Supervisor 维护每 Profile 的 browser/stream/transport 三层观测（状态、协议与 Selkies 版本、Agent/Gateway build 标识、配置版本、固定端点、最近附着/注册时间与最近错误/拒绝码），经控制面 `GET /supervisor/v1/profiles/{id}/transport` 暴露；API 侧仅内存缓存并按实例围栏进入运行响应与 SSE，不新增持久化列，API 重启后为 unknown 直至 Supervisor 下次上报。运行时健壮性收口（t055）：policy helper 删除失败不覆盖校验结果（仅记日志），网络策略安装失败时先抓取 helper 输出（截断、脱敏）再删除 helper；媒体附着的 Gateway 解析失败转为状态返回（gateway_missing），离线恢复消费返回值、非成功状态按 Profile 限频记日志；Browser 容器查找删除不可达的 NotFound 分支，非 NotFound 异常记日志，实例不匹配时报告全部异实例 id；socket slot 清理前校验属主、类型与活跃性（活跃 socket、他人属主、非 socket、符号链接均为冲突，原样保留），socket root 长度在 Supervisor 启动时按最长 slot 路径校验；runner 的两个 watcher 各自只关闭自己的流，容器 watcher 的停机竞态与网络版对称。

API 已绑定但尚无对应 Browser 的启动中断，通过稳定 missing_runtime 事件收敛后进入正常退避。Profile 锁持有期间不合成退出；已读取 Native 退出 journal 时优先等待其送达，避免首次 API 503 后被合成异常抢先覆盖。手动重开先移除旧自有 Browser 容器，再清理指向旧 hostname/PID 的 Chromium singleton 链接；不跟随链接修改目标。

停止命令的结果词汇与观测分离（t022）：结果为 `stopped`（本次实际停止）/ `already_absent`（确认不存在）/ `superseded_noop`（目标已被新实例取代，不触碰新实例），重放返回同一命令结果；API 只按权威观测记录判定收敛。生命周期冲突以类型化 `LifecycleConflictError` 映射 409（不依赖异常文案），端口耗尽 503。诊断事件投递区分已接受/永久拒绝/暂不可用：永久语义拒绝只入死信一次并持久推进游标，认证/限流/网关类失败按暂不可用重试，诊断投递不推进业务状态。X11 权限 helper 仅持 FOWNER 能力、只读根、无新特权并带受管标签，成败/取消均清理。容器扫描在边界校验身份与 config-version，异常资源逐个拒绝不中断整轮，未知身份不接纳不批量删除。网络策略任一地址族应用失败时先装双族 DROP 兜底再报错，诊断含 family/工具/退出码与有界脱敏 stderr。引擎/GeoIP 缓存按代次复用：全量校验后以树指纹 + 根身份封存 sidecar（原子切换），后续启动只验根与封存记录，未知/被改变/刷新后的代次重新全量校验；缓存初始化由 Supervisor 独占写，运行消费者只读挂载；封存指纹覆盖路径/类型/大小/mtime 与链接目标，不是内容哈希——其有效性以该独占写不变式为前提，不变式之外的写入方不在此信任模型内。Supervisor 另提供 search-defaults 观测与重试转发（UDS /control，session 围栏）。

## 资源限制

`ResourcePolicyService` 使用 Linux `/proc/stat` 和 Docker CPU counter，识别 NanoCpus、CFS quota/period、cpuset 的最紧实际预算。缺失、重复和重置 counter 不能被当作新的低负载窗口。Profile 聚合 Browser/Stream 压力，结合真实前台连接状态决定是否下发 8 FPS cap；恢复后解除 cap，由 Stream 自身活动策略决定 8/30 FPS。全后台状态不因 CPU 高负载误触发前台限制。

`ResourceMonitor` 在线程中采集阻塞 Docker stats，在事件循环内串行更新策略。控制端点 `/supervisor/v1/profiles/{profile_id}/resources` 返回决策与对应测量窗口。Viewer 心跳不建立独占控制租约。

实际 CPU 到 Chrome 降帧证明、完整 Supervisor 容器拓扑证明和正式整套部署验收属于不同范围，不能互相替代。当前机型、Docker 配额、性能场景与仅两项环境豁免见 [架构](architecture.md)。

## 网络策略与启动门禁

当前 OrbStack 普通 bridge 跨网可达，单靠网络名字和 IPAM 不能提供隔离，事实见 [d020](../findings/d020_orbstack_bridge_reachability.md)。Supervisor 在每个 Runtime 自有 network namespace 安装 IPv4/IPv6 filter 规则，不修改宿主机、Docker 全局规则或 OrbStack 配置。

策略安装使用同一不可变 Supervisor 镜像的短生命周期 helper，只授予 NET_ADMIN，加入指定 Runtime 网络命名空间，不挂 Docker Socket、宿主目录或用户数据。Browser/Stream 自身仍保持非 root、只读根、cap-drop ALL。启动 gate 在业务进程执行前等待匹配实例、角色和 ready 状态的原子标记；安装失败不开放 gate。已存在规则时拒绝覆盖，避免误接管未知网络策略。

Browser 仅允许 loopback、已建立连接及公共目的地址，私有与保留地址默认拒绝；配置代理只按明确解析的地址和端口例外放行。Stream 仅允许实际 Gateway 地址/端口、本实例 UDP mux、显式白名单与同机直连所需流量；私有与保留地址仍拒绝。IPv6 仅放行带 hop-limit 255 的必要邻居发现类型，不全量放行 ICMPv6。端点 DNS 在 gated Runtime 内解析，私密代理 URL 不传入 helper。

宿主本机代理端点映射与出口探测（t052）：`127.0.0.0/8`、`localhost`、`::1` 的代理端点在数据库与指纹中保持 loopback 原样；Supervisor 在把端点交给容器前把它映射为 `host.docker.internal`（`domain/proxy_endpoint.py:map_endpoint_for_container`），并给 Browser 与探测 helper 加 `extra_hosts={"host.docker.internal": "host-gateway"}`。网络策略只放行映射后地址与该代理端口（`_resolved_endpoint` 在 helper 内解析映射地址），宿主其它端口与其它私有地址仍拒绝；映射失败（daemon 不支持 host-gateway）时启动与探测在执行前以 `LoopbackMappingError` 明确报错并给出处置提示（需支持 host-gateway 的 Docker 20.10+ / OrbStack，或把代理移到非 loopback 地址），绝不出现启动成功但无法联网。凭证文件在写入运行时副本前同样映射 host（0600），只读挂进 Browser。

出口探测 helper 与 Browser 同视角：Supervisor 用 Browser 镜像创建短生命周期 helper（entrypoint 睡眠占位，user 1000:1000、只读根、cap_drop ALL、no-new-privileges、tmpfs /tmp），新建专用 bridge 网络（`{prefix}-probe-net-{probe_id}`，用后删除），以 `_install_network_policy` 装 browser-role 策略（`allowed_tcp` 仅解析出的代理地址:端口），再 `exec_run` 跑 `runtime_agent.egress_probe`（凭证只从 0600 凭证文件读，stdout 只打印一行 JSON `{"egress_ip","country_code"}` 或 `{"error_code"}`）。helper、网络与 probe 目录在 finally 中清理。控制面 `POST /supervisor/v1/proxies/{proxy_id}/probe`（Bearer 校验）先核对端点指纹（不符返回 `endpoint_mismatch`），再经 `asyncio.to_thread` 调 `docker.run_egress_probe`；helper 报告的错误码原样映射为 failed 观测，helper 崩溃/非法输出为 `DockerSandboxError`。网络策略、DNS 解析与凭据文件机制与 Browser 启动共用同一函数（`_install_network_policy` / `_resolved_endpoint` / `_write_proxy_credentials`）；容器加固参数（user、只读根、cap-drop 等）沿用 Browser/Stream 各自内联写法的既有模式，未抽统一构造函数。

探测 helper 与 Browser 的视角一致性只在 fake-docker 单元测试中验证（本机无 Docker）：真实 Docker（OrbStack）上的 helper 启动、host-gateway 映射与策略放行须在用户机实测（t052 AC-010/AC-011 真实部分、AC-012）。

Supervisor 重启仅接管拥有可信策略标签、所属只读 gate 挂载和匹配 ready 标记的 Runtime。启动独占锁内先清理严格匹配 prefix、managed-by、角色、随机名称与 instance-id 的遗留 cache-init/network-policy helper；周期扫描不执行此清理，避免中断当前安装。

真实无过滤 TCP 正负对照、IPv6 私有 echo 拒绝、策略重复安装拒绝及双 Profile 容器拓扑已取得定向证明。完整阶段状态仍以最终源门禁、独立 review 和 task 验收为准，不能以历史候选镜像通过代替当前源验证。

## 预览目录独立挂载、策略即时下发与 health 变化通知（t040）

预览目录 `data_root/profiles/{id}/preview/` 由 Supervisor 单独挂载进 Browser 容器 `/data/preview`，不进入 `/data/profiles/{id}/profile`（user data dir）；`PathValidator` 按同一数据根与 Profile 归属校验，目录内 `policy.json` / `frame_<timestamp_key>_<image_sha256>.jpg` / `meta.json` 全部 0600 原子写。该分离使「含浏览器状态」复制不带走预览，停止后保留最后一帧。

`capture_preview` 为即时策略，不进入配置版本。策略变化链路：

|环节|行为|
|---|---|
|API PATCH|本地写 policy，关闭时清除已有预览|
|`RuntimeCoordinator.request_preview_policy`|POST `/supervisor/v1/profiles/{id}/preview-policy`（`PreviewPolicySyncRequest`，pending保存首次request_id并在重发时复用，成功仅比较后删除对应pending）|
|Supervisor `apply_preview_policy`|写 policy，经 Agent UDS `/control` 以 `action=preview_policy` 即时下发|

下发以 runtime_instance_id + request_id 双重围栏，旧实例与重复请求丢弃；**不重启、不应用配置**。

Agent `/health` 的 details 携带 `preview_captured_at`。Supervisor仅在校验与API上报成功后写入去重缓存。瞬时失败保留同帧重试机会，warning按Profile限频30秒且只记录错误类型；Profile删除或运行代次结束清理预览去重与warning状态。观测到变化且校验 `meta.policy_epoch == policy.epoch` 与 instance 匹配后，POST API 内部端点 `/api/v1/internal/supervisor/profiles/{id}/preview`（`PreviewObservedRequest`）；不复用 Artifact 的事件文件 + 游标模式（面向持久下载，不适合每 15 秒覆盖写）。API侧`record_preview_capture`再校验capture_preview开启、代次与实例，失败丢弃并清预览。

## 共享规则与控制端口权威（t062）

Supervisor 消费的跨服务规则全部来自中立包 `cbrowser/shared/`：Gateway 端点与 Origin（`endpoints`）、Agent 凭证（`agent_credentials`）、原子写（`atomic_write`）、per-profile 锁注册表（`profile_locks`，核心与恢复协调器共用同一注册表与公开探查方法）、事件/工件投递分类（`delivery`，两个转发器同一分类函数）。控制面默认端口唯一权威为 `shared.endpoints.DEFAULT_SUPERVISOR_PORT`（8005）：runner 的 `--port` 默认值与容器内控制客户端的默认 URL 直接派生自该常量；compose 与就绪探针等非 Python 表面保留字面量，但由边界测试逐一与权威值对齐锁定，禁止出现不一致的字面量（历史 8091 分裂已消除）。Supervisor 镜像不再打包 Gateway 包，Gateway 镜像也不再借 Supervisor 文件；镜像闭包由 t062 闭包测试按 Dockerfile 组装验证。
