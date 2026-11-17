# 010 Gateway 以 API 绑定判定实例、Stream 侧 TURN 地址由 Agent 注册上报（2026-10-30T21:00:00+08:00）

- 背景：Gateway 是全局服务，需要拒绝过期 Stream 实例的注册，并为每个 Profile 生成 Stream 侧 TURN 配置；但 Gateway 不持久化状态、不访问数据库，也无法得知各 Profile 媒体网络内 coturn 的实际地址。计划 10.3 禁止依赖多网卡 DNS 解析 coturn。
- 选项：
    1. Supervisor 另行向 Gateway 推送期望实例与 coturn 地址。
    2. Gateway 注册时查询 API 持久绑定判定当前实例；Stream Agent 注册时上报 Supervisor 已下发给它的 coturn 实际地址（`turn_host`/`turn_port`），Gateway 只签发凭证并在下发时组装 URL。
    3. Gateway 配置全局 Stream 侧 TURN URL。
- 结论：采用选项 2。实例真相只有 API 一处，Gateway 重启后仍可判定；Agent 上报的地址只影响其自身配置。删除全局 `CBROWSER_TURN_STREAM_URLS` 及 `turn:coturn` 默认值。
- 替代：无
