# 需求规范：WebRTC 远程画面传输与输入

## 适用范围

单机 Docker 中，每个 Profile 使用独立 Browser/Stream Runtime；外部官方 Google Chrome 页面通过 Selkies WebRTC 接收画面和音频、提交原生输入。t004 提供 Stream 组件；正式 Gateway、前端、Supervisor 和部署分别由后续 task 对接，旧入口尚未切换。

## 显示、页面与策略

- 远端显示固定1920×1080、DPR 1，Xvfb :99 / Openbox。不同页面尺寸、连接顺序和客户端 resize 不改变远端几何。
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

## 输入与隔离

中文沿官方 composition → co,end → Native X11 路径提交，组合期间不以剪贴板模拟文本。各页面输入均到达同一真实 Browser。剪贴板内容不得进入日志；完整前端剪贴板权限与1000次一致性验证由后续任务验收。

Stream 只访问对应 Profile 的 X11、Xauthority、Pulse 和媒体网络，不挂载用户数据或 Docker Socket。Agent 失联重连、无 viewer 或媒体暂停不停止 Browser。Stream 私有版本适配与测试约束见 docs/blueprint/stream_runtime.md。

## 验收与剩余边界

组件行为以 t004 的逐项 AC 和真实 E2E 为准，不能用 Mock Peer、编码器或合成音频替代。当前测试的外部 Chrome CDP composition 验证原生客户端路径；桌面输入法候选窗口、1000次输入/剪贴板与最终整机容量仍需后续验收。公网和原生 Linux x86 执行仅按用户明确豁免记 NOT_RUN / USER_WAIVED，不计实测 PASS。
