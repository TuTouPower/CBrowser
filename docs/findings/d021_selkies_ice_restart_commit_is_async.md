# d021 Selkies 应用 answer 不等于 ICE 新代已接管

- 来源：t006_v2_gateway_auth_rtc 主控审查（2026-10-30）。

- 结论：固定 Selkies 2.1.0 的 `RTCPeerConnection.setRemoteDescription` 以 `asyncio.ensure_future(self.__connect())` 在后台做连通性检查，调用返回时新 ICE 代可能尚未完成或已失败；失败时 `GenerationIceTransport.start` 抛 `ConnectionError`，PC 可能整体关闭。轮换方必须等待 transport 的 `committed_generation` 推进且 `restart_pending` 清除（`ice_transport.wait_restart_commit`），再向 Gateway 确认 `ice_restart_committed`。

- 证据：上游源码 `selkies/webrtc/rtcpeerconnection.py` 第 988/1215 行；Stream 镜像内真实 SDK 测试 `tests/e2e/test_stream_ice_commit_e2e.py`：健康代 2 提交，错误 ice-pwd 的代 3 “ICE failed” 后等待抛 ConnectionError、提交代保持 2。失败注入不能关闭对端 PC（SCTP/DTLS 会连带关闭本端）。

- 影响：Gateway 只能以 Agent 确认作为迁移成功依据；对信令未 stable 或 ICE 未连通的 PC 不得发起重启（会替换初始协商）。

- 现状：有效，限固定 Selkies 2.1.0。

- 后续（t024 文档收敛）：本条所述 TURN/ICE 代次机制已由 ADR 013（同机直连，见 docs/blueprint/decisions.md）整体删除；本条仅作历史实验事实保留，不再构成现行实现或验收要求，文中指向未来 task 的指令已失效。
