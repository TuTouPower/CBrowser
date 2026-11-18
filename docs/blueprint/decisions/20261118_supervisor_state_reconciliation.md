# 040 Supervisor 状态协调收归最小批量协议与缓存，健康责任迁入控制组件（2026-11-18，t083）

- 背景：Supervisor 的协调长期逐 Profile 复用 UI 聚合读：内部
    `GET /profiles`（富列表）+ 每 Profile `GET /profiles/{id}/runtime`
    （富 DTO，handler 内同步刷新 transport/search-defaults 并触发下游
    RPC）。recovery 每秒 tick 先列表再逐个 GET，现场 60 秒窗口出现
    107 次内部 runtime GET；readiness、reconcile、start 意图校验同样
    逐个读。另一面，API/Gateway/Supervisor 三服务的 Compose
    healthcheck 每 5 秒在容器内启动 python 进程（约 34 次 exec/分钟），
    是稳态 Docker exec 的最大来源。t081/t082 已分别消除字体正文读取
    与策略/DNS churn，本 ADR 收口状态协调与健康观察两条线。
- 选项：
    1. 保留逐 Profile GET，仅降低 tick 频率：N+1 与富 DTO 耦合仍在，
        协调延迟与意愿新鲜度互相拉扯。
    2. Supervisor 直读 API 数据库：跨服务共享存储，破坏 API 作为
        意愿唯一权威的边界，且无法围栏进程世代。
    3. 最小批量状态协议 + 推送通知 + Supervisor 状态缓存（本 ADR
        采用）：API 以服务鉴权暴露仅含协调字段的最小 DTO，批量
        快照与变更通知双通道，Supervisor 只消费缓存。
- 结论：采用选项 3。
    - **最小 DTO**：`SupervisorProfileState`（`cbrowser/shared/state_protocol.py`，
        schema 于 `schemas/runtime/state_protocol.json`）仅含意愿、绑定
        实例/配置版本、终态事件与重试/封锁字段；不含字体覆盖、
        transport、search-defaults、control 或任何 UI 信息。旧内部
        `GET /profiles` 与 `GET /profiles/{id}/runtime` 路由删除。
    - **围栏**：`profile_runtimes.state_revision`（迁移 0013，ORM
        `before_update` 事件统一自增，任何写路径不可绕过）+ API 进程
        `api_epoch`。快照跨批次 epoch 不一致即整轮作废；通知按
        revision 单调应用，迟到/重放通知丢弃；未完整读完的快照
        永不当权威。
    - **双通道**：变更通知由 API 在 `publish_profile_change` 汇聚点
        经既有控制通道（supervisor_url + 服务 bearer）推送
        `StateChangeNotice`（全量最小状态 + 移除名单），尽力而为；
        Supervisor 每 30 秒一轮批量快照兜底对齐，快照按 profile_id
        键集分批（声明上限 200/批，一批一 SELECT），请求与查询按
        批次增长、与 Profile 数无关。稳态 tick 零 HTTP。
    - **缓存权威**：`SupervisorStateCache` 单飞快照（同一时刻至多
        一个在途）、失败有界退避；权威 = 完整快照存在且最近成功
        接触（快照完成或通知应用）在 40 秒窗口内。权威外消费者
        暂停（与旧 API 不可达语义一致），readiness 显式未就绪。
        Supervisor 自身写（bind/observed/desired-state）成功后标
        记本地写失效，下一次读取先完成重同步再返回，旧条目在重
        同步落地前仍可读、永不误判为删除。
    - **读纯度**：runtime GET、列表投影与 SSE 组装只读已维护
        观测；transport/search-defaults 改由 coordinator 有界
        后台循环（15 秒、并发上限 4）刷新，未确认项标未知，读取
        不改意愿、不重建容器。
    - **健康责任迁移**：删除三服务 Compose healthcheck 与
        `service_healthy` 依赖（改 `service_started` 仅定启动
        顺序）；周期健康观察归既有控制组件（API coordinator 观
        察 Supervisor、Supervisor 观察 API/Gateway，健康读取返回
        已维护观测，不互相同步探测）；deploy/rollback 以
        `scripts/service_readiness_probe.py` 在单一截止时间内确
        认三服务真实 readiness，未就绪/假活/挂起/未知显式失败，
        不再以进程已启动（`up --wait`）判成功。
    - **稳态探针**：`scripts/steady_state_probe.py` 为生产交付
        的一部分：exec 以 exec_create 计一次（exec_start/exec_die
        为阶段事件单列），测量器自身 exec 打标排除，policy
        helper/Agent churn 与实例重启计数按容器归属。4 Profile/
        10 分钟与故障矩阵的真实栈验证属 [deploy]，登记 p134/p135
        本地补验。
