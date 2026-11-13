# 需求规范：WebRTC 远程画面传输与输入

## 适用范围

单机 Docker 中，每个 Profile 使用独立 Browser/Stream Runtime；外部官方 Google Chrome 页面通过 Selkies WebRTC 接收画面和音频、提交原生输入。t004 提供 Stream 组件，t006 交付 Gateway，t007 交付前端会话与 Selkies token；部署与旧入口切换由后续 task 完成。

## 显示、页面与策略

- 远端显示尺寸由 Profile 配置决定（默认1920×1080），DPR 固定 1，Xvfb :99 / Openbox。不同页面尺寸、连接顺序和客户端 resize 不改变远端几何。运行中修改尺寸只保存新配置版本，页面提示待应用，用户明确“应用并重启”后新实例才以新尺寸运行。
- 每页独立 Peer、身份、输入与静音，共享 Profile 捕获和编码；复制标签冲突自动分离身份，关闭或刷新一页不影响其他页。
- 活动前台30 FPS、静止前台8 FPS；持续变化画面保持活动目标。单个后台页不得降低其他前台需求；全部隐藏/断开才暂停捕获，Browser 继续运行。恢复可见先8 FPS并请求关键帧，再按活动升帧。
- Supervisor 通过认证控制面下发8–30 FPS上限，解除后恢复目标；页面不能修改过载配额。
- 当前 Mac/OrbStack 以 CPU 软件编码验收；1/3/10流容量、10 Profile中9后台1前台、P95≤100ms、首帧≤1秒与8小时稳定性由后续性能任务实测。

## 传输与信令

- Profile 的多个 Peer 共用该 Profile 分配的单个 UDP mux 发布端口；端口池30000–30991。Supervisor 负责独占分配、实际映射与回收。
- WebRTC DTLS-SRTP 只使用同机 `127.0.0.1` host 候选直连；不部署 coturn，不下发 TURN 凭证，不做凭证轮换或 ICE 代次接管（ADR 013）。Stream 入口显式启用 ICE-lite（Supervisor `stream_environment` 注入 `SELKIES_WEBRTC_ICE_LITE=true`、entrypoint 同步 export 并传 `--webrtc-ice-lite`），阻止 Selkies 2.2.1 回退其默认外部 STUN/TURN（默认 OpenRelay TURN 的 allocation 超时曾使每个新 PeerConnection 的 offer 固定延迟约 5 秒，t019）。
- 正式信令路径为 /stream/{profileId}/signal，由 Stream Gateway 提供：升级前校验 Origin、登录会话与 Profile 授权及 Agent 就绪；所有拒绝在升级与注册前完成，授权失败按来源与 Profile 限流；每个页面独立隧道，关闭一条不影响其他连接；媒体不经 Gateway。Gateway 重启不停止 Browser，Agent 按 1/2/4/8/16/30 秒退避重新注册后页面可重连。
- Stream Agent 注册携带 profile_id、runtime_instance_id、selkies_version、runtime_state、webrtc_udp_port、config_version，每 10 秒发送健康消息；Gateway 只接受与 API 当前绑定一致的实例，并核对回传报文的 Profile、实例与 session。协议见 schemas/stream/agent_protocol.json，payload 按 action 判别并双向校验。
- 页面可见性只经 Selkies 官方每 Peer STOP_VIDEO/START_VIDEO 暂停该页自身视频；Gateway 不采集页面可见性或活动，也不向 Agent 下发可见性。Agent 健康消息上报未暂停视频 consumer 数与捕获状态，Gateway 只转存最近上报值供 Supervisor 查询；信令心跳只判存活，不形成控制权。
- 部署拓扑不包含 coturn；Stream UDP mux 由 Supervisor 分配并发布到宿主 `127.0.0.1`，由 t012 统一编排。

## 前端会话

- 会话页以同源 iframe 加载固定版本官方 Selkies 2.2.1 Web 客户端（t043 升级，ADR 022），薄适配层只改写信令地址、处理 Gateway 控制帧、锁定远端尺寸/DPR（RTC 配置由 Gateway 下发，适配层不处理），不改写官方 HELLO、`client_tab_id`、`resume_key`。复制标签页自动分离身份且不踢原页；刷新与重连保留身份。
- 页面不持有 Selkies token：每 Profile master/controller token 由服务端随机生成，master 只开启 Stream 内安全模式，controller 由 Stream Agent 代注入；经认证 Gateway 隧道的页面以 controller 接入，绕过隧道直连 Selkies 或使用错误 token 被拒。Stream 显式关闭 Selkies 模式切换，客户端无法切到 WebSocket 模式。
- 连接显示阶段：运行时未就绪、信令失败、ICE 失败、媒体无帧分别给出说明与操作（重连、查看运行状态），诊断取自 RTCPeerConnection 状态与 getStats；不出现无解释黑屏、不新增媒体回退通道。
- 页面冻结/恢复（Page Lifecycle freeze/resume、bfcache pageshow）后检测失效连接，以原身份重建。
- 每页静音开关走官方 `pipelineControl`（本页 audio 静音并发 `STOP_AUDIO`/`START_AUDIO`），只影响本页连接。会话诊断另有独立音频状态：正常、已静音、无音频轨道、音频无数据（3 秒内无包），内容静音仍有 Opus 包、不判故障；音频故障不改变视频阶段。
- 远端浏览器内部标签页切换经同一画面同步显示到所有页面。
- 首帧预算（t019，2026-11-10 用户决定调整）：侧边栏切换已运行 Profile 与同 Profile 刷新重建会话到首帧均 ≤5 秒；本机 Mac/OrbStack + Chrome 156 在基线 supervisor 镜像下实测 3.4–3.7 秒，原 2 秒预算不再满足，故按用户决定更新为此契约。ICE host-only 候选与同机直连约束不变；性能容量与 P95 仍由后续性能任务验收。
- 初次画面与操作延迟可测（t007 本机记录，不设阈值，阈值由性能任务验收）。
- 会话页为独立页面 `/session/:profileId`（t039）：单行页头含环境切换器（Popover 内可搜索、按分组列出环境与状态、条目为真实链接）、observed state 与 transport 状态、待应用标记与「应用并重启」，以及音频、诊断、详情面板、专注模式、停止操作；切换器链接在新标签打开后两标签会话互不影响。环境切换器触发器只显示环境名称、不带状态徽标，顶栏运行状态只出现一次，各环境状态保留在下拉条目内（t061）。transport 状态（ready/recovering/failed/unknown）在页头与详情面板均显示当前界面语言的本地化文案，未知或缺失值回落本地化「未知」，不显示原始机器码（t061）。
- 画面区只承载铺满的 Selkies iframe，不绘制模拟浏览器框（标签栏 / 地址栏 / 书签 / 缩放，ADR 003/006）；阶段呈现分级（t061）：等待态（checking_runtime、connecting_signaling、media_waiting、reconnecting）只显示轻量指示，不渲染居中诊断表或操作按钮；故障态（signaling_failed、ice_failed、media_no_frames、web_locks_unavailable、error）保留居中诊断面板与适用重连动作；runtime_not_ready 保留启动与查看状态；stopping 只显示停止提示与查看状态入口；connected 不显示等待层。
- 详情面板为右侧 300px、默认收起，展开状态存 `cbrowser.session.details_open`（刷新保持），分环境 / 网络 / 指纹 / 运行四区，每个值可复制。详情开关只有页头详情按钮一个，面板内无标题与第二开关，关闭时面板不渲染、不占宽度（t061）。
- 专注模式隐藏侧栏与页头，鼠标悬停顶部边缘显示悬浮退出工具条，**不用 Esc 退出**（Esc 与常用组合键留给远端）；进入与退出不重建 iframe、不中断远端输入。
- `/session` 会话入口在本标签页无目标时列出运行中环境供选择；侧栏「会话」导航在已有目标时回跳该会话。
- 会话页 `data-testid` 全部改 `sess-*` 结构（旧 `browser-session-*` / `session-*` / `diag-*` 弃用），组件与 E2E 选择器同步改写；旧会话页组件整体删除。
- 旧页面全部替换后启用全局颜色门禁（`npm run design:lint` 的 `--lint`），扫描前端源码颜色字面量与默认调色板类发现即失败、无豁免（见 `docs/blueprint/testing.md`）。

## 输入与隔离

中文沿官方 composition → co,end → Native X11 路径提交，组合期间不以剪贴板模拟文本。各页面输入均到达同一真实 Browser。剪贴板内容不得进入日志。

- Profile `clipboard_sync` 映射为 Selkies `enable_clipboard=true` 或 `false`；`enable_binary_clipboard=false|locked`、`clipboard_seamless=true|locked`。`enable_clipboard` 是字符串策略，`|locked` 不参与解析；其客户端改写由 Selkies WebRTC settings allowlist 拒绝。开启时纯文本双向自动同步：会话页获得焦点时官方客户端读取本机剪贴板发往远端，远端复制后写回本机剪贴板，无需侧栏剪贴板框；关闭后双向均无传输；图片等二进制内容不传输。
- 前端 ClipboardBridge 只探测 `clipboard-read`/`clipboard-write` 权限并展示拒绝/按需提示，自身不读取或写入本机剪贴板；同步由官方 Selkies seamless 客户端完成。
- 会话页不新增剪贴板同步协议或 Agent RPC；其他 Profile 不共享远端剪贴板。输入/剪贴板手动清单由 t009 验收。

Stream 只访问对应 Profile 的 X11、Xauthority、Pulse 和媒体网络，不挂载用户数据或 Docker Socket。Agent 失联重连、无 viewer 或媒体暂停不停止 Browser。Stream 私有版本适配与测试约束见 docs/blueprint/stream_runtime.md。

## 验收与剩余边界

组件行为以 t004 的逐项 AC 和真实 E2E 为准，不能用 Mock Peer、编码器或合成音频替代。当前测试的外部 Chrome CDP composition 验证原生客户端路径；桌面输入法候选窗口、输入/剪贴板手动清单与最终整机容量仍需后续验收。公网和原生 Linux x86 执行仅按用户明确豁免记 NOT_RUN / USER_WAIVED，不计实测 PASS。

## Viewer 边缘授权（t064）

- 正式信令路径仍为 `/stream/{profileId}/signal`，但登录会话不再由 Gateway 携 Cookie 回 API 校验。Caddy 对该路由先删伪造授权头、经 API 边缘解析会话/Origin/Profile，再删 Cookie 并把 API 签发的 60 秒单 Profile grant 交给 Gateway 本地验签；其余升级前拒绝、每页独立隧道、Agent 就绪与媒体不经 Gateway 的语义不变。
- 刷新与重连的每次新握手都重新走边缘解析，登出或会话撤销在下一次握手生效；已建立连接不因 grant 到期中途切断。`/stream/agent/register` 不经 viewer 边缘授权，继续使用独立 Agent 凭证恢复注册。

## 注册恢复、消息预算与配额（t022）

- Gateway 注册节流为双预算：在途握手预留与失败窗口分离，成功不消耗失败额度，全部退出路径释放预留；Agent 重连退避带 jitter 且不超上限，网关重启后合法 Agent 可恢复注册。心跳使 registry 的 runtime_state 与 Agent 上报一致。Supervisor 断开按目标逐个隔离清理，发送失败明确 503。
- 隧道预算单一权威：原始 data 1MiB、序列化 envelope 2MiB+64KiB、WS 帧 6MiB+64KiB；超限以 1009 受控关闭单个连接，服务继续处理其他连接。
- FPS 配额协议与策略同规：有限且 ∈ [min_fps, max_fps]，越界严格拒绝，None 仅解除限制。StreamAgent 仅保留可 await 的完整 stop（取消并等待全部后台任务、释放 Viewer 与 detached upstream、幂等）。Selkies 扩展自 t063 起经受控构建包承载（见「Selkies 扩展边界（t063）」），不再经适配层访问私有 API、启动不做 ABI 校验。
- SSE 快照为订阅私有数据并携带 live 基点，不写共享历史；窗口不足显式重建。

## 注册结构化拒绝与信令恢复呈现（t026）

- 注册载荷可携带 Agent build 标识，成功 ACK 返回 Gateway build 标识；WS 建立后的拒绝（版本不支持/载荷非法/身份不一致）先返回结构化拒绝（含原因码与双方 build 标识）再关闭，升级前拒绝（凭证/实例未绑定）同样按 Profile 记录最近拒绝，成功注册清除。Supervisor 经控制端点读取注册状态与拒绝原因做收敛决策。
- 信令首次连接异常关闭（含 1006）：transport 处于 recovering 时呈现恢复中并在有界窗口内等待，变 ready 后重连；明确失败或超窗口才呈现失败。已连接后的断开沿用既有 resume 语义。

## 前端会话一致性（t023）

- SSE 运行时事件以生成的 `ProfileRuntimeStatusEvent` 为唯一类型契约：投递前验证核心字段与状态枚举，畸形或未知事件只进错误通道、不投递给消费者。连接以代次隔离：重复 `start` 不新增连接，旧代次不得投递、报错或触发重连，`stop`（含登出）后不得重连。
- 会话页严格区分加载中、加载失败（显式错误并可重试）、Profile 不存在（仅真实 404）与已停止待启动；请求失败不得呈现为已停止。切换界面语言只更新文案，不得重跑运行时检查或重置已连接会话。

## 前端会话状态一致性（t058）

- 会话阶段与错误文案的单一权威是 `runtimeQuery`：`SessionPage` 把 `runtimeQuery.data?.observed_state` 作为唯一 `runtimeState` 传入会话 hook，hook 不再自行读取 runtime 写错误；`runtimeState` 为空时不写任何错误。
- 帧信号仅在后端状态非 `stopped` / `error` 时推进连接态并启动音频管线。
- 首检完成前收到的 WS 关闭（含 1006）只记录诊断，不启动恢复；首检定版为非 `running`（或其后变为 `stopped` / `error`）时取消同 generation 的恢复轮询。
- 错误边界分层：渲染异常由日志通道记录；路由内容由 `RouteErrorBoundary` 包裹，随路由切换复位，异常只影响该路由；根部保留兜底。

## 媒体链路回环直连（t042；t054 重写：局域网直连删除）

- 媒体直连只走本机回环：不使用 STUN/TURN 中继、无 ICE 重启机制；Stream 容器固定 `CBROWSER_WEBRTC_PUBLIC_IP=127.0.0.1`，UDP mux 端口固定绑定 `127.0.0.1`（t054 删除局域网 host 候选扩展，ADR 013 回到仅回环）。
- 容器网络漂移自愈（AC-005）中的网络版本比对已删除：运行期不存在已应用网络版本，`_converge_session` 与启动对账不再比对绑定地址与通告 IP；媒体策略放行只剩链路本地范围（`169.254.0.0/16` / `fe80::/10`）。

## 会话阶段呈现与断线恢复收敛（t061）

- 阶段集合以 `SessionStage` 类型为唯一权威，共 12 个阶段（含 stopping、error）；`connecting_ice` 不是阶段，组件层不再保留该字面量分支。
- 已连接后信令 WS 异常关闭：先进入 reconnecting 并给官方客户端 5 秒以原 `resume_key` 恢复；5 秒恢复检查读取 WebRTC stats，媒体仍健康（stats.connected）且当前有效阶段仍为 reconnecting 时直接收敛回 connected 并清除错误文案，不重建 iframe、不动内部 Browser 与已有网页；媒体不健康才沿既有路径重建。诊断快照（ConnectionSnapshot）不变时诊断源不发新信号，故健康收敛出口在此检查内，检查结果受 generation fence 保护，旧 generation 的迟到结果不覆盖当前状态。后端已停止时异常关闭被忽略，不启动恢复。
- 诊断呈现可区分正在恢复（reconnecting 轻量指示）与已经恢复（connected、无等待层残留）；恢复失败原因不含凭据。
- 无 viewer 时环境保留：全部 viewer 断开后不停止、不重置、不删除环境与已有网页/浏览器数据；不存在 idle 期限、绝对期限或 viewer TTL 等自动回收。既有按活跃 consumer 暂停/恢复服务端采集编码的行为不变，再次连接可恢复观看。

## Selkies 扩展边界（t063）

- 服务端 Selkies 以受控构建包运行：固定上游 2.2.1 wheel＋构建期显式补丁（身份清单 `config/selkies/selkies_controlled_build.json`，ADR 034）。采集策略服务经构建期工厂钩子（`SELKIES_WEBRTC_SERVICE_FACTORY` → `cbrowser.stream_agent.policy:create_policy_service`）在启动时构造，仍经官方 HELLO / client_tab_id / resume_key 建立会话；运行时不替换上游模块、不解析上游源码、不校验私有 ABI。
- 帧率仲裁语义不变：按 active_peers 与媒体 consumer 信号在静止 8 FPS、运动/输入 30 FPS 间仲裁，零 consumer 暂停可恢复，单个 consumer 暂停不压低其他 consumer。
- X11 键盘行为（named spare 过滤、text_room 整池回退、prebind 容量保护与绑定后 keymap reload/settle）由受控包内实现，中文 IME、普通键盘、剪贴板与复制标签隔离、viewer resume 行为与 t063 前一致；真实链断言见 `tests/e2e/test_stream_x11_keymap_e2e.py`（含受控版本号断言）。
