# p008 Agent 隧道重连未触发 Selkies 官方 RESUMED

- 来源：t007 fix_fe lane 观察
- 内容：页面信令 WS 断开后，官方客户端以原 `client_tab_id`/`resume_key` 重连，但 Stream Agent 为每个隧道新建 loopback upstream，Selkies 日志 `peer server not found` 后回 `SESSION_OK`（新会话）而非 `RESUMED`。功能可用（重建连接成功），但未利用官方会话恢复。需核实 Selkies 2.1.0 resume 窗口与 Agent upstream 生命周期（旧 upstream 关闭是否立即销毁会话），必要时保持 upstream 到 resume 窗口结束。
- 处理：未开
