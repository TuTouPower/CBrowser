# d003 固定 Selkies 2.1.0 缺少现成 ICE restart 路径

- 来源：t001 / s002_selkies_protocol；2026-10-27T01:32:00+08:00 主控核查官方固定提交

- 结论：官方 2.1.0 当前配置刷新只应用于新 PeerConnection；已启动 RTCIceTransport 再次 start 会直接返回，不更新 ICE 参数。不能直接满足计划10.6要求的到期前6小时 ICE restart。

- 证据：固定提交 `6ee68a7a815956e6745e916741f13335e0b3ff53` 的 `src/selkies/webrtc_engine.py:1573` 明确 update_rtc_config 仅作用于新连接；`src/selkies/webrtc/rtcicetransport.py:367` 的 start 在 \_\_start 非空时等待后立即返回；`src/selkies/webrtc/rtcpeerconnection.py:749` 的 createOffer 无 iceRestart 参数。主控检索并逐行复核；主控另以真实 UDP 建立两端官方 RTCIceTransport，发送接收实际载荷；再次 start 传入不同远端 ICE 参数后，远端用户名保持原值且旧路径继续传输。实验退出码 0；可重跑脚本见 s002/code/ice_restart_probe.py，原始输出见主仓 .scratch/v2_orchestration/ice_restart_probe.log。该实验证明重复 start 不执行 ICE restart；不等于已验证媒体重协商或全部可能的扩展实现。

- 影响：保持原始 ICE restart 验收要求，未通过前不冻结整体架构。需实现并实测重协商路径，或由用户明确批准变更要求；不能直接改为“凭证只对新连接生效”并宣称完成。连接重建与真正 ICE restart 必须分别命名和验收。

- 现状：有效

- 补充：d010显式私有接口适配器已在同SDK PC/DTLS上完成三轮标准SDP与DataChannel连续性主控真测；不修改上述官方原生API缺口结论，Chrome/TURN/媒体完整路径仍未验证。

- 后续（t024 文档收敛）：本条所述 TURN/ICE 代次机制已由 ADR 013（同机直连，见 docs/blueprint/decisions.md）整体删除；本条仅作历史实验事实保留，不再构成现行实现或验收要求，文中指向未来 task 的指令已失效。
