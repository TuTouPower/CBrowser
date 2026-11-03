# d022 Selkies RTCApp 的 STUN/TURN 配置契约与 SELKIES_TURN\_\* 环境冲突

- 来源：t006_v2_gateway_auth_rtc E2E lane 实测 relay-only 失败，主控核对源码（2026-10-31）。

- 结论：`selkies.webrtc_engine.RTCApp.update_rtc_config(stun_servers, turn_servers)` 需要两组 URL 字符串，TURN 为 `turn://user:pass@host:port?query`（用户名与凭证百分号编码，由 `format_turn_servers` 解码），只作用于此后新建的 PeerConnection；`RTCApp` 在 `WebRTCService.initialize_components()` 才创建，早于此的配置须在其后补推。`SELKIES_TURN_HOST/PORT` 同时被 Selkies 自身读取，会生成它自己的 RTC 配置并可能启动 RTC 配置监控（`mon_rtc_config` 回写 RTCApp 与信令下发），需在服务子类里关闭；Selkies 新 PC 默认收集 host/srflx 候选，relay-only 需在 ICE 适配层限制。

- 证据：上游 `webrtc_engine.py` 第 1573–1640、1697–1740 行，`webrtc_mode.py` 第 333–420、3026–3036、3245–3300 行；真实 SDK 测试 `tests/e2e/test_stream_rtc_config_e2e.py`（含 relay-only 候选限制）；Gateway E2E AC-005 第 1 代 relay↔relay。

- 影响：Stream 侧 TURN 只经 Gateway→Agent 下发；前端适配层须在官方客户端 `setConfiguration` 后保持 Gateway 下发的 iceServers 与 iceTransportPolicy（t007）。

- 现状：有效，限固定 Selkies 2.1.0。

- 后续（t024 文档收敛）：本条所述 TURN/ICE 代次机制已由 ADR 013（同机直连，见 docs/blueprint/decisions.md）整体删除；本条仅作历史实验事实保留，不再构成现行实现或验收要求，文中指向未来 task 的指令已失效。
