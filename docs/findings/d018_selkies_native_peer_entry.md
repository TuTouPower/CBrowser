# d018 Selkies 2.1.0 的真实 PeerConnection 存放于 peer_conn 键

- 来源：t004_v2_stream_runtime。
- 结论：固定 Selkies 2.1.0 的 `RTCApp._start_rtc_pipeline` 将真实连接存入 `peer_connections[client_peer_id]["peer_conn"]`，不是 `"pc"`。生产适配应按该精确契约读取，不能用单 Peer 猜测或错误字段兼容掩盖绑定失败。
- 证据：不可变 Stream 镜像中的 SDK 源直接显示该字段。先前单元测试伪造 `{"pc": mock_pc}`，没有验证真实 SDK；该用例已整体删除并记明原因。Root 通过两个真实 Google Chrome 媒体 Peer 向注册 Agent 发起合法 Gateway ICE 控制：旧读取返回 `action=error`（25.90 秒实测失败），修正后两个 Peer 均生成 `ice_restart_offer`（26.41 秒通过），没有 Mock PC。日志与最小复现已留存本次执行证据。
- 影响：t004/t007 的 Gateway ICE 轮换必须先验证真实 SDK Peer 元数据关联，再验证协商、代提交与媒体。成功生成 Offer 只证明查找和准备流程，不等于 ICE 连接完成、旧代退役或 relay-to-relay 成功；后续必须遵守 d012 的栅栏与媒体增量要求。
- 现状：有效，限固定 Selkies 2.1.0；SDK 升级时须重新验证字典结构及真实多 Peer 路径。
