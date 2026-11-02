# d026 单机同机 Chrome 可经 127.0.0.1 host 候选完成全场景直连媒体

- 来源：s011_direct_media_validation / t015，2026-11-02 真实 Chrome + OrbStack 验证。
- 结论：同机 Google Chrome 与 Stream 容器经 `127.0.0.1:<UDP mux>` host 候选直连即可覆盖多页面、复制标签、刷新、关闭首个页面、可见性暂停/恢复、Viewer 断线 resume、音视频、键鼠与中文输入全部场景；无需 coturn 与任何 TURN 凭证。
- 证据：s011 探针 `direct_media_probe.py`（真实 Browser/Stream 镜像、无 coturn 容器、Gateway 不下发 RTC 配置）通过；两页 selected remote candidate 均为 `127.0.0.1:30097 host/udp`，1920×1080 帧与音频能量持续增长，隐藏页视频停止、可见页不受影响、恢复后继续出帧，Viewer WebSocket 断开后原 tab 身份恢复并继续解码，8 组中文 composition 经 Native 通道提交，关闭首 tab 后次页媒体与输入继续。证据 JSON 保留于 `.scratch/s011/basetemp/.../media_proof.json`。
- 影响：t015 据此删除 coturn/TURN 凭证与轮换/ICE 代次接管/Selkies 私有 ABI 补丁；t012 部署拓扑不再包含 TURN 服务。公网与原生 Linux x86_64 未验证（用户豁免），本结论仅覆盖单机单人部署包络。
- 现状：有效
