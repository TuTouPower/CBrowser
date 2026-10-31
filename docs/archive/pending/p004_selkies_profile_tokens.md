# p004 Selkies 每 Profile master/controller token 未落实（计划 8.1）

- 来源：t006 主控审查（2026-10-31）；技术债自查
- 内容：计划 8.1 要求每个 Profile 使用独立的 Selkies master token 与 controller token，master token 永不返回前端、同 Profile 多页面共用 controller token。当前 Stream 入口（`config/docker/stream_runtime/entrypoint.sh`）未配置任何 Selkies token；Selkies 只监听 Stream 容器 loopback，外部页面只能经 Gateway 认证（登录会话 + Origin + Profile）与 Agent 隧道到达，所有 Peer 以无 token 的 controller 身份接入。t006 AC-001 中“master token 不返回前端”因此只是空满足。需要在 t007（AC-008 起显式设置 Selkies 会话参数）前决定：按计划生成并下发 Profile 级 token（Supervisor 随机生成，master 只留 Stream 侧，controller 经 Gateway/Agent 注入），或以 ADR 记录“隧道认证替代 Selkies token”的取舍并获用户确认；不得静默删减。
- 处理：t007；resolution=resolved；reason=t007 AC-010 每 Profile Selkies master/controller token，Agent 代注入（d024）
