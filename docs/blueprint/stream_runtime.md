# Stream Runtime

## 边界与部署接口

Stream Runtime 负责单个 Profile 的 Selkies 2.1.0 捕获、共享编码、WebRTC Peer 与原生输入；Browser Runtime 独立持有引擎与用户数据。Stream 不启动或停止 Browser，不访问 Profile 数据、Browser Agent UDS 或 Docker Socket。

Stream 使用 UID 1000、只读根文件系统、cap-drop ALL 与独立 PID namespace，加入指定 Browser 的 shareable IPC，使用相同 hostname。只挂载对应 X99 Socket 文件、Xauthority 文件、Pulse 子目录和 Agent 凭证文件；不能挂载整个 Browser runtime 目录。Pulse 源为 cbrowser_sink.monitor，48000 Hz、S16LE、双声道。宿主发布每个 Profile 分配的 UDP mux；Native HTTP 仅监听 Stream 容器 loopback。

config/docker/stream_runtime/Dockerfile 构建独立镜像。入口读取配置与外部提供的凭证；正式网络、端口分配、Gateway 和认证分别由 t005/t006/t012 对接。本阶段 E2E 的 Docker exec 静态资源代理仅为测试夹具，不能用于生产 Gateway。

## Selkies 安全模式与每 Profile token

入口显式设置 `SELKIES_ENABLE_DUAL_MODE=false`、`SELKIES_FILE_TRANSFERS=none`、`SELKIES_ENABLE_CLIPBOARD=true`/`false`（由 Profile `clipboard_sync` 决定；客户端改写由 WebRTC settings allowlist 拒绝）与 `SELKIES_ENABLE_BINARY_CLIPBOARD=false|locked`、`SELKIES_CLIPBOARD_SEAMLESS=true|locked`（开启剪贴板时纯文本双向自动同步，见 decisions 012），客户端无法经 `/api/switch` 切到 WebSocket 模式（真实负例返回 403 `Dual streaming mode disabled`），文件传输不经 Selkies 通道。`SELKIES_MODE=webrtc`、`ENABLE_SHARING=true`、`ENABLE_COLLAB=false`、`FRAMERATE=8,8-30` 保持不变；不设 `mk_control=true`。

Supervisor 在每次启动 Profile 时用 `secrets.token_urlsafe(32)` 生成 master 与 controller token，以 0600 文件 `runtime/.secrets/<profile_id>/selkies_tokens_<runtime_instance_id>.json`（目录 0700，与挂进 Browser 的 `runtime/<profile_id>` 平级、不挂进 Browser；每次启动用新文件名并删除旧实例文件，不原地替换已被旧容器挂载过的路径）写入并只挂载给该 Profile 的 Stream 容器（`/tmp/selkies_credentials.json`，只读）。挂载前校验存在性与 0600（组/他人任何位即拒绝）。入口读取该文件，把 controller token 写成 tmpfs 上 0600 的 `SELKIES_TOKENS_FILE`（`{token: {"role":"controller","slot":null,"mk_control":false}}`），并以 `SELKIES_MASTER_TOKEN` 开启安全模式；master token 只留在 Stream 内部，不进入 Agent 配置、注册/心跳、Gateway 或 API 响应。未挂载凭证文件时（独立/测试启动），入口自行用 `secrets.token_urlsafe(32)` 生成每次随机的 master/controller 并只写 tmpfs，安全模式始终开启，不存在退回无 token 的路径。

Stream Agent 在转发上游 `HELLO client` 时，若页面未自带 `client_token`，注入本 Profile 的 controller token，不修改 `client_tab_id`/`resume_key`；因此不持有 token 的页面经认证 Gateway 隧道即以 controller 接入，而直连 Selkies 信令缺 token 或错 token 被 Close 4001 `Invalid authentication token` 拒绝。

## 多页面与共享策略

每个 Viewer 有独立 Peer、输入与静音状态，共享 Profile 捕获及编码管线。远端几何取自本次启动绑定的 Profile 不可变配置版本（默认 1920×1080，DPR 固定 1）：Supervisor 从绑定快照读取 `screen_width/screen_height` 注入 Stream（`CBROWSER_SCREEN_WIDTH/HEIGHT`），受管启动缺失或非法即失败；独立启动无注入时入口读取真实 Xvfb 尺寸。页面 viewport、连接顺序和客户端 resize 指令不得修改远端尺寸。保留官方客户端，Web Locks shim 在复制 sessionStorage 造成身份冲突时重签新页，原页继续运行；重连同时绑定 tab_id 与 resume_key。

Viewer 信令隧道关闭或 Gateway 断线时，Agent 不立即关闭该 Viewer 的 loopback Selkies upstream，而是保留会话至 10 秒 resume 窗口；同 `tab_id`/`resume_key` 的重连由 Selkies `RESUMED` 接管，窗口到期或 Agent 停止时才关闭 upstream。Selkies 自身的 `SESSION_HOLD_S=3s` 只覆盖无 close 帧的异常断开，不能覆盖干净关闭；Agent 侧保留窗口覆盖前端 5 秒重连等待，避免把应当恢复的会话误判为新会话。

共享策略的输入全部在 Stream 内取得（计划 9.3）：页面可见性只来自 Selkies 官方每 Peer STOP_VIDEO/START_VIDEO 回调，Peer 加入/离开来自 consumers 变化与断开回调，输入来自数据通道，运动来自捕获 damage；Gateway 不下发可见性。活动前台目标30 FPS，静止前台8 FPS；持续画面变化保持活动目标。一个页面隐藏不能降低其他前台需求；全部隐藏或断开后暂停捕获。恢复可见先恢复8 FPS并请求关键帧，再按活动提高。Supervisor 提供8–30 FPS配额上限，解除后恢复正常目标；客户端数据通道不能覆盖配额或远端几何。

## Gateway wire 协议

Agent 主动通过带 Bearer 凭证的 WebSocket 注册。所有包携带 version=v2、profile_id、runtime_instance_id；注册 ACK 生成 agent_session_id，后续控制与隧道必须同时匹配当前三项身份。旧 session、未知 viewer、未注册控制和身份冲突均拒绝。

- 注册与 ACK：AgentRegisterEnvelope(action=register) / GatewayRegisterResponse；注册时 session 可为 null；载荷不含 TURN 地址或重复 FPS 字段。
- 隧道：GatewayTunnelEnvelope(type=open/msg/close)，conn_id 标识独立连接，msg 的 data 承载官方信令。
- 控制：GatewayControlEnvelope 只支持 supervisor_quota，payload 由 SupervisorQuotaPayload 校验；不再有 rtc_config、ice_restart 或 visibility_update。
- 健康：注册后立即及每 10 秒发送 heartbeat，载荷含 runtime_state、viewer_count 及取自 Selkies 的未暂停视频 consumer 数与捕获是否运行，供 Supervisor 经 Gateway 查询前台状态。
- schemas/stream/agent_protocol.json 从 AgentRegisterEnvelope、AgentHeartbeatEnvelope、GatewayRegisterResponse、GatewayTunnelEnvelope、GatewayControlEnvelope 的判别联合生成；运行 PYTHONPATH=src/backend python scripts/export_stream_protocol.py。Gateway 与 Agent 收发两侧均按判别联合校验，payload 全部入契约；漂移守卫见 tests/unit/test_stream_protocol_schema.py。

连接任务与有界队列按 viewer 回收；溢出通知 Gateway 关闭对应连接。断线重注册与 Stream 暂停不改变 Browser 运行意愿。

配额与关闭（t022）：策略层与协议层同一 FPS 规则——配额必须有限且 ∈ [min_fps, max_fps]，公开入口越界严格拒绝（ValueError）且不改变现值，None 仅表示解除限制。StreamAgent 只保留可 await 的完整 `stop()` 作为唯一关闭入口：取消并等待心跳等全部后台任务、释放全部 Viewer 与 detached upstream，重复调用安全。隧道预算以协议模块为单一权威（见 gateway 蓝图三层预算）。

## 直连媒体与原生输入适配

媒体只使用同机 `127.0.0.1` host 候选直连（ADR 013）：Stream UDP mux 发布到宿主回环，客户端与服务端均不配置 STUN/TURN。已删除 coturn、TURN 凭证与轮换、ICE 代次接管及对 Selkies 私有 ABI 的补丁；Selkies 不再被要求提供 ICE restart。s011/d026 验证了多页面、复制标签、刷新、关闭首 tab、可见性暂停/恢复与 Viewer 断线 resume。「不配置 STUN/TURN」在 Stream 启动参数层由 ICE-lite 落实（t019）：Supervisor `stream_environment` 注入 `SELKIES_WEBRTC_ICE_LITE=true`，Stream entrypoint 同步 export 该变量并向 Selkies 传 `--webrtc-ice-lite`；否则 Selkies 2.1.0 会回退其默认外部 STUN/TURN（OpenRelay），其 TURN allocation 超时使每个新 PeerConnection 的 offer 固定延迟约 5 秒。unit 门禁 `tests/unit/test_stream_ice_config.py` 断言该参数存在且 entrypoint 不出现任何外部 STUN/TURN 配置。

中文使用官方 composition/co,end → Native X11 输入，不使用剪贴板提交。x11_keymap.py 按运行时 XKB 非空名称过滤 spare，保留 Native 分配顺序；每次新绑定通过有界 xkbcomp reload 通知活跃 Chrome，并保留 SDK settle。按住的槽及当前 batch 已绑定槽不得重绑，无容量则拒绝。该路径有同步 subprocess 成本，P95、1000次输入与8小时稳定性须在 t009/t012 实测，当前不作性能承诺。细节见 d014/d017/d018。

Selkies 私有 API 只经 `x11_keymap` 适配层访问（t022）：安装期校验钉版 2.1.0 的完整私有面（prebind/text_room/_find_spare_keycodes/_layout_keycode 签名、`_BIND_SETTLE_S`、__init__ 实例属性），结构或签名不符明确报 unsupported ABI，不静默误判 driver dead；键池 None 时按 SDK 原规则惰性初始化同一有限键池，不当作无限容量。不自动升级 Selkies/CloakBrowser 版本。

## 验证入口

- tests/e2e/test_stream_runtime_e2e.py：官方 Mac Chrome、真实 Browser/Stream 整镜像、双音视频、复制标签、刷新、关闭首 tab、可见性暂停/恢复、Viewer 断线 resume、组合输入和运行隔离；拓扑无 coturn。
- tests/e2e/test_stream_x11_keymap_e2e.py：真实 Xvfb 键位复用、按住槽保护。
- tests/e2e/test_stream_selkies_tokens_e2e.py：真实 Stream 镜像验证双模式关闭（403 负例 + WebRTC 正例）、直连信令无/错 token 4001、Agent 注入 controller token 后页面以 controller 接入、双 tab 共存与同名 tab 驱逐、resume 保持；并以真实 Gateway 拓扑（无头 Chrome）验证安全模式下出帧与输入、页面与所有容器日志不含 master token。

镜像参数必须是不可变 sha256 ID，完整媒体测试还需已初始化只读 Linux 引擎缓存。临时目录预先创建，pytest 显式 --basetemp 与 cache_dir 位于允许写域。公网候选与原生 Linux x86 执行记为 NOT_RUN / USER_WAIVED；容量、延迟和压力验证不在本阶段结果中提前打勾。
