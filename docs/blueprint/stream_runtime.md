# Stream Runtime

## 边界与部署接口

Stream Runtime 负责单个 Profile 的 Selkies 2.1.0 捕获、共享编码、WebRTC Peer 与原生输入；Browser Runtime 独立持有引擎与用户数据。Stream 不启动或停止 Browser，不访问 Profile 数据、Browser Agent UDS 或 Docker Socket。

Stream 使用 UID 1000、只读根文件系统、cap-drop ALL 与独立 PID namespace，加入指定 Browser 的 shareable IPC，使用相同 hostname。只挂载对应 X99 Socket 文件、Xauthority 文件、Pulse 子目录和 Agent 凭证文件；不能挂载整个 Browser runtime 目录。Pulse 源为 cbrowser_sink.monitor，48000 Hz、S16LE、双声道。宿主发布每个 Profile 分配的 UDP mux；Native HTTP 仅监听 Stream 容器 loopback。

config/docker/stream_runtime/Dockerfile 构建独立镜像。入口读取配置与外部提供的凭证；正式网络、端口分配、Gateway 和认证分别由 t005/t006/t012 对接。本阶段 E2E 的 Docker exec 静态资源代理仅为测试夹具，不能用于生产 Gateway。

## 多页面与共享策略

每个 Viewer 有独立 Peer、输入与静音状态，共享 Profile 捕获及编码管线。固定远端几何为1920×1080、DPR 1，页面 viewport、连接顺序和客户端 resize 指令不得修改远端尺寸。保留官方客户端，Web Locks shim 在复制 sessionStorage 造成身份冲突时重签新页，原页继续运行；重连同时绑定 tab_id 与 resume_key。

共享策略的输入全部在 Stream 内取得（计划 9.3）：页面可见性只来自 Selkies 官方每 Peer STOP_VIDEO/START_VIDEO 回调，Peer 加入/离开来自 consumers 变化与断开回调，输入来自数据通道，运动来自捕获 damage；Gateway 不下发可见性。活动前台目标30 FPS，静止前台8 FPS；持续画面变化保持活动目标。一个页面隐藏不能降低其他前台需求；全部隐藏或断开后暂停捕获。恢复可见先恢复8 FPS并请求关键帧，再按活动提高。Supervisor 提供8–30 FPS配额上限，解除后恢复正常目标；客户端数据通道不能覆盖配额或远端几何。

## Gateway wire 协议

Agent 主动通过带 Bearer 凭证的 WebSocket 注册。所有包携带 version=v2、profile_id、runtime_instance_id；注册 ACK 生成 agent_session_id，后续控制与隧道必须同时匹配当前三项身份。旧 session、未知 viewer、未注册控制和身份冲突均拒绝。

- 注册与 ACK：ProtocolEnvelope(action=register) / GatewayRegisterResponse；注册时 session 可为 null。
- 隧道：GatewayTunnelEnvelope(type=open/msg/close)，conn_id 标识独立连接，msg 的 data 承载官方信令。
- 控制：GatewayControlEnvelope，支持 rtc_config、supervisor_quota、ice_restart、ice_restart_answer；返回 ice_restart_offer、ice_restart_committed（新代真实接管后）或 error。
- 健康：注册后立即及每 10 秒发送 heartbeat，载荷含 runtime_state、viewer_count 及取自 Selkies 的未暂停视频 consumer 数与捕获是否运行，供 Supervisor 经 Gateway 查询前台状态。
- schemas/stream/agent_protocol.json 从四种 Pydantic envelope 生成；运行 PYTHONPATH=src/backend python scripts/export_stream_protocol.py。JSON Schema 描述 wire 形状，跨字段约束和动作 payload 仍由实际 Agent/Pydantic 执行，不能只依赖 JSON Schema 做授权。

连接任务与有界队列按 viewer 回收；溢出通知 Gateway 关闭对应连接。断线重注册与 Stream 暂停不改变 Browser 运行意愿。

## ICE 与原生输入适配

官方固定版本无公共 ICE restart API；ice_transport.py 显式检查 Selkies/WebRTC/ICE 版本及私有 ABI，采用同 PC、DTLS、Track 的 generation 切换，不创建替代 Peer 冒充。新代准备失败保留旧代，关闭和取消路径回收临时 TURN/socket。新代接管后关闭旧连接并验证拒绝发送，才允许新代媒体验收。

客户端和容器必须分别使用各自可达 TURN URL 与独立短期凭证。coturn 配置真实 relay 地址及 external/private 映射；不能将0.0.0.0作为具体 relay 映射地址。测试使用 loopback 发布与明确放行，仅限隔离夹具；生产 coturn 配置由部署任务验证。

中文使用官方 composition/co,end → Native X11 输入，不使用剪贴板提交。x11_keymap.py 按运行时 XKB 非空名称过滤 spare，保留 Native 分配顺序；每次新绑定通过有界 xkbcomp reload 通知活跃 Chrome，并保留 SDK settle。按住的槽及当前 batch 已绑定槽不得重绑，无容量则拒绝。该路径有同步 subprocess 成本，P95、1000次输入与8小时稳定性须在 t009/t012 实测，当前不作性能承诺。细节见 d014/d017/d018。

## 验证入口

- tests/e2e/test_stream_runtime_e2e.py：官方 Mac Chrome、真实 Browser/Stream 整镜像、双音视频、复制标签、三代 TURN、策略、组合输入和运行隔离。
- tests/e2e/test_stream_ice_failure_e2e.py / test_stream_ice_relay_e2e.py：真实 SDK socket 回收、失败/取消与三代 DataChannel 中继机制；不能替代 Chrome RTP 证明。
- tests/e2e/test_stream_ice_commit_e2e.py：真实 SDK 下提交等待只在新代接管后返回，新代连通失败时报错且提交代不变。
- tests/e2e/test_stream_rtc_config_e2e.py：Gateway 下发的 Stream 侧 TURN 以 Selkies URL 格式进入真实 RTCApp，RTCApp 晚于配置创建时补推。
- tests/e2e/test_stream_x11_keymap_e2e.py：真实 Xvfb 键位复用、按住槽保护。
- tests/e2e/test_stream_client_identity_e2e.py：Chrome Web Locks 身份与重连。

镜像参数必须是不可变 sha256 ID，完整媒体测试还需 CBROWSER_TURN_TEST_IMAGE 和已初始化只读 Linux 引擎缓存。临时目录预先创建，pytest 显式 --basetemp 与 cache_dir 位于允许写域。公网候选与原生 Linux x86 执行记为 NOT_RUN / USER_WAIVED；容量、延迟和压力验证不在本阶段结果中提前打勾。
