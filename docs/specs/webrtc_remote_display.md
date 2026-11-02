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
- WebRTC DTLS-SRTP 优先直连，必要时 TURN 中继。客户端与服务端配置分别使用可达地址和独立短期凭证；凭证轮换保持同 PC、DTLS 和 Track。
- 新 ICE generation 必须实际接管，旧连接关闭并拒绝发送，然后按新 ufrag 的 selected relay pair 重新采样媒体增量；旧 relay 继续传流不能充当轮换通过。
- 正式信令路径为 /stream/{profileId}/signal，由 Stream Gateway 提供：升级前校验 Origin、登录会话与 Profile 授权及 Agent 就绪；每个页面独立隧道，关闭一条不影响其他连接；媒体不经 Gateway。Gateway 重启不停止 Browser，Agent 按 1/2/4/8/16/30 秒退避重新注册后页面可重连。
- Stream Agent 注册携带 profile_id、runtime_instance_id、selkies_version、runtime_state、webrtc_udp_port、config_version 与本网络 coturn 实际地址，每 10 秒发送健康消息；Gateway 只接受与 API 当前绑定一致的实例，并核对回传报文的 Profile、实例与 session。协议见 schemas/stream/agent_protocol.json。
- 新连接首帧获得当前有效客户端 RTC 配置；Gateway 按 24 小时有效、12 小时换代、到期前 6 小时 ICE restart 轮换 TURN 凭证，同时向 Agent 下发新代 Stream 侧配置；只有 Agent 确认新 ICE 代真实接管后才算该连接迁移成功，失败记录并退避重试，不向新连接下发过期凭证。
- 页面可见性只经 Selkies 官方每 Peer STOP_VIDEO/START_VIDEO 暂停该页自身视频；Gateway 不采集页面可见性或活动，也不向 Agent 下发可见性。Agent 健康消息上报未暂停视频 consumer 数与捕获状态，Gateway 只转存最近上报值供 Supervisor 查询；信令心跳只判存活，不形成控制权。
- 部署目标 coturn 的3478/5349与50000–50999中继端口由 t012 统一编排；t004 测试使用隔离端口，不代表部署完成。

## 前端会话

- 会话页以同源 iframe 加载固定版本官方 Selkies 2.1.0 Web 客户端，薄适配层只改写信令地址、处理 Gateway 控制帧与 RTC 配置、锁定远端尺寸/DPR，不改写官方 HELLO、`client_tab_id`、`resume_key`。复制标签页自动分离身份且不踢原页；刷新与重连保留身份。
- 页面不持有 Selkies token：每 Profile master/controller token 由服务端随机生成，master 只开启 Stream 内安全模式，controller 由 Stream Agent 代注入；经认证 Gateway 隧道的页面以 controller 接入，绕过隧道直连 Selkies 或使用错误 token 被拒。Stream 显式关闭 Selkies 模式切换，客户端无法切到 WebSocket 模式。
- 连接显示阶段：运行时未就绪、信令失败、ICE 失败、媒体无帧分别给出说明与操作（重连、查看运行状态），诊断取自 RTCPeerConnection 状态与 getStats；不出现无解释黑屏、不新增媒体回退通道。
- 页面冻结/恢复（Page Lifecycle freeze/resume、bfcache pageshow）后检测失效连接，以原身份重建。
- 每页静音开关走官方 `pipelineControl`（本页 audio 静音并发 `STOP_AUDIO`/`START_AUDIO`），只影响本页连接。会话诊断另有独立音频状态：正常、已静音、无音频轨道、音频无数据（3 秒内无包），内容静音仍有 Opus 包、不判故障；音频故障不改变视频阶段。
- 远端浏览器内部标签页切换经同一画面同步显示到所有页面。
- 初次画面与操作延迟可测（t007 本机记录，不设阈值，阈值由性能任务验收）。

## 输入与隔离

中文沿官方 composition → co,end → Native X11 路径提交，组合期间不以剪贴板模拟文本。各页面输入均到达同一真实 Browser。剪贴板内容不得进入日志。

- Profile `clipboard_sync` 映射为 Selkies `enable_clipboard=true` 或 `false`；`enable_binary_clipboard=false|locked`、`clipboard_seamless=true|locked`。`enable_clipboard` 是字符串策略，`|locked` 不参与解析；其客户端改写由 Selkies WebRTC settings allowlist 拒绝。开启时纯文本双向自动同步：会话页获得焦点时官方客户端读取本机剪贴板发往远端，远端复制后写回本机剪贴板，无需侧栏剪贴板框；关闭后双向均无传输；图片等二进制内容不传输。
- 前端 ClipboardBridge 只探测 `clipboard-read`/`clipboard-write` 权限并展示拒绝/按需提示，自身不读取或写入本机剪贴板；同步由官方 Selkies seamless 客户端完成。
- 会话页不新增剪贴板同步协议或 Agent RPC；其他 Profile 不共享远端剪贴板。输入/剪贴板手动清单由 t009 验收。

Stream 只访问对应 Profile 的 X11、Xauthority、Pulse 和媒体网络，不挂载用户数据或 Docker Socket。Agent 失联重连、无 viewer 或媒体暂停不停止 Browser。Stream 私有版本适配与测试约束见 docs/blueprint/stream_runtime.md。

## 验收与剩余边界

组件行为以 t004 的逐项 AC 和真实 E2E 为准，不能用 Mock Peer、编码器或合成音频替代。当前测试的外部 Chrome CDP composition 验证原生客户端路径；桌面输入法候选窗口、输入/剪贴板手动清单与最终整机容量仍需后续验收。公网和原生 Linux x86 执行仅按用户明确豁免记 NOT_RUN / USER_WAIVED，不计实测 PASS。
