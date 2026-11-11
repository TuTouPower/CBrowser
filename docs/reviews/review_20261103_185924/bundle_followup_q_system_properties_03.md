# bundle_followup_q_system_properties_03

## Summary

核对范围：StreamAgent 注册主循环与退避实现（stream_agent/agent.py connect_and_run、ReconnectBackoff）、Gateway 注册节流与 429 位点（gateway/registry.py RegistrationThrottle、gateway/server.py handle_agent_register）、Supervisor 的启动/恢复节奏（supervisor/core.py scan_and_reconcile_existing、recovery_coordinator.py、docker_adapter.py 容器重启策略），以及 unit/integration/e2e 三层对该场景的测试覆盖。结论分两层：(1) 行为层——批量恢复在代码机制上是自愈的，无需人工介入。Agent 的 connect_and_run 是无次数上限的 while 循环：WS 握手被 429 拒绝时 aiohttp 抛 WSServerHandshakeError，落入与连接失败、ACK 拒绝相同的兜底 except，统一走确定性指数退避 1/2/4/8/16/30s（封顶 30s、成功后重置）后重试，循环只因 stop()/CancelledError 退出。Gateway 桶为每来源 20 次/60s 滑动窗口，且 allow() 在桶满时直接返回 False 而不记录被拒尝试——重试不消耗额度，窗口随时间连续滑动释放名额；P 个 profile 全量重注册最迟约 ceil(P/20) 个窗口内分波完成，已注册者靠 10s 心跳保持。Supervisor 不放大突发：启动对账按 profile 串行 await、恢复重试是 per-profile 独立退避/冷却、容器 restart_policy=no（Docker 守护进程也不会制造同步重启），且注册动作由各 Agent 自发，Supervisor 不经手。(2) 证据层——上述自愈结论是三段机制的静态组合推演，该组合场景本身在三层测试中零覆盖：没有任何测试驱动真实 Gateway 的注册 429 → 真实 StreamAgent 退避重试这条链，也没有 >20 profile 的批量重启恢复用例；问题自设的反证条件要求『e2e 有批量重启后全部 profile 在有限时间内恢复 running 的断言』，此物不存在，故按关闭标准证据不足，标 insufficient。残余风险（不改变自愈定性）：退避无 jitter，同批掉线的 Agent 以相同节拍近锁步重试（因被拒不占额度，只增加无效握手、不阻碍收敛）；恢复时长随 profile 数线性增长，超过 20 个后每多约 20 个，最后一波注册约多等 1 分钟，期间未注册 profile 无画面——与 f_backend_stream_gateway_01 的影响口径一致。

## Findings

- [Low][85] tests/unit/test_gateway_registry.py; tests/unit/test_stream_agent_lifecycle.py; tests/integration/test_gateway_signaling.py; tests/e2e/test_supervisor_recovery_e2e.py — 批量重注册组合场景（>20 profile 撞 Gateway 注册节流）在三层测试中零覆盖，自愈性只有静态推演、无任何执行证据
    - ID: f_followup_q_system_properties_03_01; verification: static
    - Evidence: 节流与退避只被分开单测：test_gateway_registry.py:96-105 只测 RegistrationThrottle 原语的上限/过期；test_stream_agent_lifecycle.py:461-496 的退避用例用 MockGatewayServer 的 reject_registration（ACK 级拒绝），不是真实 Gateway 返回的 HTTP 429 握手拒绝; tests/integration/test_gateway_signaling.py 中唯一的 429 断言（:249）属于 viewer 授权节流用例，与 Agent 注册节流无关；无任何集成用例把注册桶打满后断言 Agent 最终注册成功; tests/e2e 恢复类用例最多 2 个 profile（test_supervisor_recovery_e2e.py:453），其余均为单 profile；无一用例重启 Gateway 或制造同源注册突发，更无完成时限断言
    - Impact: 全机/网关重启后画面恢复时长是该系统最现实的整体可用性场景，其自愈性（退避重试 + 被拒不占额度 + 窗口滑动三机制的组合）若任一环被重构破坏（例如 allow() 改为记录被拒尝试、或 Agent 对 429 加特殊退出分支），现有测试全绿也发现不了，恢复可能从『延迟数分钟』退化为『永不恢复需人工介入』而无告警
    - Fix: 加一条集成级用例：真实 Gateway（小桶参数如 max_attempts=3）+ 多个真实 StreamAgent 同源并发注册，断言全部在有界时间内注册成功；并加一条 e2e 或集成用例模拟 Gateway 重启后多 profile 分波重注册完成。或至少在 test_gateway_signaling 中补 Agent 注册节流打满→窗口过期→注册成功的链路断言

## evidence

```json
[
  "src/backend/cbrowser/gateway/registry.py:89-105 RegistrationThrottle 默认 max_attempts=20、window_seconds=60.0，仅按 peer（来源地址）建桶；allow() 在 len>=max_attempts 时直接 return False 且不 append——被拒尝试不消耗额度，窗口按时间戳滑动过期",
  "src/backend/cbrowser/gateway/server.py:283-289 handle_agent_register 在 WS 升级与凭据校验之前执行 registration_throttle.allow(request.remote)，桶满返回 HTTP 429 'Too many registration attempts'；闸门实例为 RegistrationThrottle() 默认参数（server.py:106）",
  "src/backend/cbrowser/stream_agent/agent.py:253-370 connect_and_run 为 while self._running 无上限重试循环：ws_connect（:279）握手失败、GatewayRegistrationError、其余 Exception 全部落到 :366-370 的 backoff step+sleep 后重试，循环仅因 CancelledError 或 stop() 退出；429 握手错误（aiohttp WSServerHandshakeError）无任何特殊分支、与普通传输失败同路",
  "src/backend/cbrowser/stream_agent/agent.py:99-131 BACKOFF_SCHEDULE=(1,2,4,8,16,30)、max_delay=30 的确定性退避，无随机 jitter；注册成功后在 :331 reset()；单测 tests/unit/test_stream_agent_lifecycle.py:440-457 钉住序列、:461-496 钉住『注册被拒时按 1/2/4/8/16/30 退避』、:498-544 钉住成功后重置",
  "同机共享桶的前提成立：gateway/endpoint.py:10-11 默认 Gateway 端点为 host.docker.internal，各 Stream 容器经同一桥接/宿主地址到达 Gateway，request.remote 相同或高度集中（与局部 finding f_backend_stream_gateway_01 的 evidence 一致）",
  "Supervisor 不放大且不经手注册：supervisor/core.py:190-207 scan_and_reconcile_existing 在 for 循环中逐 profile await（串行）；recovery_coordinator.py 的重试为 per-profile 调度并带 cleanup cooldown（:349-361、:541-551）；docker_adapter.py:682 与 :875 容器 restart_policy={'Name': 'no'}，守护进程重启不产生同步拉起",
  "节流原语有单测：tests/unit/test_gateway_registry.py:96-105 test_registration_throttle_is_bounded_per_source 钉住每来源上限与窗口过期恢复；但 tests/integration/test_gateway_signaling.py:240-252 唯一的 429 断言针对的是 viewer 授权节流（AuthorizationThrottle），不是 Agent 注册节流",
  "e2e 层无批量恢复用例：tests/e2e 的恢复类用例均为单 profile（test_supervisor_retry_e2e.py:73、test_supervisor_startup_recovery_e2e.py:136 与 :304、test_supervisor_offline_recovery_e2e.py:69）或双 profile（test_supervisor_recovery_e2e.py:453，主题是 Supervisor SIGKILL 后的端口不变性，2 个 profile 远低于 20 桶上限、且不重启 Gateway）；全仓无 >20 同源注册、无『全部 profile 在时限内恢复 registered/running』的断言"
]
```

## result

```json
"insufficient"
```
