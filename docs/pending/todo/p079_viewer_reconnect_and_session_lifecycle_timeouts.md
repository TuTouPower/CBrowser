# p079 断线只重建媒体、三时限解耦与会话可观测归因

- 来源：2026-11-13 同类项目技术调研（`.scratch/reports/隐私浏览器同类项目技术调研.md` P0-4、P1-11、P2-20），借鉴 neko v3、Browserless.reconnect、Selkies 2.2.1、Steel/Kernel 会话生命周期、KasmVNC API
- 内容：会话为权威状态、页面只是 viewer 句柄，标签页关闭不应销毁会话。现状已有 `client_tab_id` / `resume_key` / Web Locks 抢锁 / 复制标签自动分离身份 / refresh 保留身份，方向一致，但缺「断线只重建 media peer、不重建会话」的显式契约与三时限解耦。目标：viewer 检测静默 WebSocket → backoff 重连 → WebRTC 失败请求替换 media peer，信令中断期间流继续；控制平面提供断开前申请保活端点 + token，`disconnect()` 而非 `close()`；后台标签页重连后音视频自动恢复。三时限独立配置：会话绝对上限（从启动算、反复 reconnect 不可续期、`MAX_RECONNECT_TIME` 封顶）/ 断线保活 TTL / viewer 链接 TTL；任意 CDP 命令、remote input、viewer 在线重置 idle；先 standby 保状态停编码再超时销毁；记录 `releaseReason` 与每 viewer 帧率/bottleneck stats，webhook 事件带签名与密钥轮换窗口，HLS/录制回放 API key 只走服务端代理或签名 URL、不下发浏览器。本次为只读调研，未授权改生产代码。
- 处理：未开
- 时间：2026-11-13T19:16:54+08:00
- 关联：p008（archive，Selkies resume）、p009（archive，multi-viewer E2E）、p012（archive，token eviction close race）、p050/p052（archive，媒体帧时序与 close 1006）、p034/p042/p057（archive，生命周期解耦与事件反馈）、p016（archive，配额 E2E）

## 边界

不改动已闭环的 `resume_key` / token 语义（p008/p012），只补显式契约与治理层；输入仲裁见 p076。

## 验收

1. 信令 WebSocket 中断后重连，会话与 Profile 状态不变，仅媒体 peer 被替换，首帧恢复时间有上限。
2. 反复重连不能延长会话绝对 deadline；idle 由 CDP/输入/viewer 在线正确重置。
3. 每 viewer 帧率、bottleneck 与 `releaseReason` 可查询；webhook 签名可校验、密钥可轮换。
