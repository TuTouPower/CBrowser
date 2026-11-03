# p027 基础设施替换后运行时信令自愈与发布验收重构

- 来源：用户报告 2026-11-04 运行中 Profile 出现“信令连接失败 / WebSocket 1006”；用户要求按最佳架构处理，不做兼容层。
- 内容：把 Compose 管理的基础设施与 Supervisor 管理的运行时彻底解耦，使 Gateway 等基础设施可随时替换而不断开已运行 Browser；删除一次性网络附着路径，改为统一、持续、幂等的运行时收敛；部署脚本改为发布控制器并做收敛验收。当前无用户，允许破坏性重构，不保留旧行为兼容。
- 处理：未开

## 分析基线

- 分析时间：2026-11-04T01:16:40+08:00。
- CBrowser 基线：main@5101f159fab885b245a798e0ffe1fa4241c6b906。
- 证据范围：Docker 实际状态、容器日志、源码与部署脚本静态核对；未执行修复或自动化测试。

## 事件与根因

- 约 17:00 重新部署后 `cbrowser-api`、`cbrowser-gateway`、`cbrowser-supervisor` 被重建；`cbrowser-gateway` 新容器只加入 `cbrowser-edge`（192.168.97.3），不再属于两个 Profile 媒体网络。
- 两个 Stream 容器为 13:14 创建，未随 Compose 重建，仍向旧 Gateway 地址 `ws://192.168.148.2:18080`、`ws://192.168.107.2:18080` 重连，持续 `ClientConnectorError`。
- Gateway 无 Agent 注册，`/stream/{profileId}/signal` 返回 503，前端将异常关闭呈现为 WebSocket 1006。
- 容器本身均在运行；故障是网络附着与生命周期协调缺失，不是容器崩溃。

## 当前设计缺口

- `scripts/deploy_v2.sh` 只执行 `docker compose up -d` 并无条件重启 Caddy；它不知道也不处理 Supervisor 动态创建的 Browser/Stream。
- `src/backend/cbrowser/supervisor/core.py` 只在 Runtime 启动时调用一次 `attach_profile_infrastructure`；`_reconcile_profile` 对同一实例提前返回，不检查 Gateway 是否仍附着。
- `src/backend/cbrowser/supervisor/docker_adapter.py` 的附着逻辑把 Docker 当次分配的地址写入 Stream 环境变量与网络策略；Gateway 重建后没有稳定端点契约。
- `src/backend/cbrowser/supervisor/runner.py` 已有 Docker 事件与 30 秒兜底扫描，但扫描只核对容器状态，不修复网络附着、策略或 Agent 注册。
- Compose 服务无健康检查，部署脚本不验证活跃 Runtime 是否恢复信令。
- Gateway 与 Agent 没有显式协议版本握手；未来 Gateway 升级可能让旧 Stream 永久无法注册。
- Runtime 只有 `observed_state`，无法区分“Browser 在运行但信令断开”。

## 设计不变量

1. 基础设施容器可随时替换；替换不得要求停止 Browser。
2. API 保存生命周期意愿；Supervisor 是运行时观测与收敛执行者；Gateway 注册表只是短暂观测，不作为权威状态。
3. 跨容器连接是持续契约，不是创建时一次接线；创建、恢复、部署统一走同一收敛路径。
4. Browser 是唯一有状态运行时；Stream 可丢弃；Gateway、API、Supervisor、Caddy 无状态可替换。
5. 网络附着收敛不得依赖 API 可用；API 离线时仍应恢复数据面连接。
6. 不做兼容层：删除一次性附着路径，不保留双轨逻辑，不迁移旧 Runtime 状态。

## 目标架构

### 1. Profile 媒体网络固定 Gateway 端点

- 保留每 Profile 独立媒体 bridge 与 Gateway 多宿模型，不改为共享控制网络。
- Supervisor 创建 Profile 媒体网络时预留 Gateway 固定端点（例如每网络 `.2`），通过 IPAM aux address 或等价方式固化，并写入网络标签。
- Gateway 每次接入 Profile 网络必须使用该固定地址；Stream 的 `CBROWSER_GATEWAY_URL` 与 egress policy 都基于该地址生成。
- 固定地址不可分配时，Profile 启动/收敛显式失败，不静默使用 Docker 下一个空闲地址。
- 每个 Profile 媒体网络视为刚好连接 Stream 与 Gateway 的点对点链路，固定端点属于链路契约，不是把动态 IP 写死。

### 2. 单一 RuntimeReconciler

- 复用 `runner.py` 现有启动扫描、Docker 事件与 30 秒兜底循环，不新增第二个竞争循环。
- 收敛输入：
    - 生命周期意愿：API 的 `desired_state`、`runtime_instance_id`、`config_version`。
    - 网络附着意愿：实际存在的 Browser/Stream 容器与 Supervisor 拥有的 Profile 网络，不依赖 API。
    - 实际状态：Docker 容器、网络成员、策略标记、Gateway 控制面查询结果。
- 单 Profile 收敛顺序：
    1. 校验 Gateway 容器存在、运行、role/prefix 标签正确。
    2. 确保 Profile 媒体网络存在且所有权正确。
    3. 确保 Gateway 以预留地址接入该网络。
    4. 确保 Stream egress policy 允许该 Gateway 端点。
    5. 查询 Gateway，确认 Agent 已注册当前 `runtime_instance_id`。
    6. 上报 Browser、Stream、transport 三层观测状态。
    7. Gateway 可达但 Agent 超过窗口未注册时，只重建 Stream，Browser 保持运行。
    8. Browser 自身异常时才进入现有生命周期恢复策略。
- 触发：启动扫描、Gateway/Browser/Stream 容器事件、网络 connect/disconnect、30 秒兜底、部署后显式 `reconcile_all`。
- 并发：每 Profile 一把锁；同网络附着串行；只操作带正确 `managed-by`、prefix、profile、role 标签的对象；未知端点拒绝断开；失败回滚只撤销本次新建连接。
- 删除 `attach_profile_infrastructure` 的“仅启动时调用”语义，改为统一 `ensure_gateway_attachment`，所有路径复用。

### 3. 发布控制器

- `scripts/deploy_v2.sh` 改为幂等发布控制器：
    1. 构建镜像并以不可变 tag/digest 固化。
    2. 保存上一版 release env，支持明确回滚。
    3. 执行 `docker compose up -d --wait`，为 API/Gateway/Supervisor 增加健康检查。
    4. 调用 Supervisor 只读 readiness：Gateway 可达且协议兼容；所有 desired=running 的 Profile 的 Browser/Stream 运行、Gateway 已附着、Agent 已注册、无旧实例代次。
    5. 任一条不满足时输出逐 Profile 诊断并退出非零。
    6. 删除无条件 `restart caddy`；仅在配置实际变化时重建。
    7. 删除脚本中重复的 API 构建行。
- 部署脚本只做发布与验收，不直接承担 Docker 网络编排。

### 4. 协议版本与 Stream 滚动重建

- Agent 注册携带 `protocol_version` 与构建标识；Gateway 明确拒绝不兼容版本。
- Supervisor 识别协议不兼容时，按 Profile 滚动重建 Stream，Browser 保持运行、页面不丢。
- 部署验收等待所有活跃 Profile 收敛，避免旧 Stream 静默失败。
- 不做 Gateway 双协议兼容层；Stream 可丢弃是升级边界。

### 5. 可观测性与前端状态

- Runtime 状态拆分：`desired_state`、`browser_state`、`stream_state`、`transport_state`、`gateway_protocol`、`gateway_attached_at`、`agent_registered_at`、`last_reconcile_error`。
- `transport_state` 至少区分 `attached`、`recovering`、`agent_missing`、`gateway_unreachable`。
- Supervisor 每次收敛上报结构化结果，经 API/SSE 暴露。
- 前端 WebSocket 1006 不再直接等同终态失败；`recovering` 显示自动恢复，只有 Supervisor 明确报错或超过收敛窗口才提示失败。

## 非目标

- 不做旧 Runtime、旧 API 字段、旧部署参数兼容；当前无用户，直接替换。
- 不停止所有 Runtime 后部署，不把停服作为网络修复手段。
- 不把 Gateway 移入 Supervisor 管理，不引入 Swarm/K8s，不改为共享单一控制网络。
- 不让 Gateway 持有 Docker Socket，不扩大现有安全边界。
- 不修改 `.repo_template`。
- 不在本 pending 内实施或创建 task。

## 验收场景

1. 两个 Profile 运行中替换 Gateway 容器：Agent 自动重注册，Browser/Stream 不重建，信令在收敛窗口内恢复。
2. kill Gateway 进程、重启 Supervisor、Docker daemon 重启、手工断开 Gateway 网络：均自动恢复。
3. 网络策略或附着标记缺失：进入明确 degraded，不静默运行。
4. Gateway 协议不兼容：只滚动重建 Stream，Browser 页面保持。
5. API 不可用期间替换 Gateway：网络附着与 Agent 重注册仍完成。
6. 多 Profile 并发收敛不串网、不交叉附着。
7. 连续多次 deploy 幂等；Gateway 永不就绪时部署明确失败并输出诊断，不无限重建 Stream。
8. 部署成功返回必须代表所有活跃 Runtime 已收敛，不允许“容器起来了但信令仍断”的假成功。
9. 前端能区分信令恢复中与终态失败。

## 实施顺序

1. 先写失败测试：运行中替换 Gateway，断言自动重附着与 Agent 重注册。
2. 引入 Profile 网络固定 Gateway 端点契约。
3. 实现统一 `ensure_gateway_attachment` 与 RuntimeReconciler。
4. 增加 API transport 观测字段与前端状态。
5. 增加 Gateway 协议版本与 Stream 滚动重建。
6. 重写部署脚本为发布控制器并增加健康检查/readiness。
7. 补齐故障矩阵集成测试。
8. 更新 `docs/blueprint/architecture.md`、`supervisor.md`、`gateway.md`、`testing.md`，新增 ADR。

## 风险与回退

- 固定端点分配失败必须显式阻断，不能回退到任意地址。
- 网络策略与固定端点绑定；若未来改变拓扑，必须同时更新策略契约，禁止放宽为整网放行。
- 收敛器误重建 Stream 会打断 Viewer；设置明确超时、退避与最大尝试次数，优先等待 Agent 自行重连。
- 部署 readiness 失败时必须保留现场诊断；回退使用上一版 release env，不回退数据或删除运行中 Browser。

## 与现有 backlog 的关系

- `t022` 的 A39 涉及 Gateway 重启后 Agent 恢复与注册预算，但不覆盖 Gateway 容器替换后的 Profile 网络附着、固定端点、发布验收与 transport 观测；本条是独立架构事项。
- 未来转 task 时需明确与 `t022` 的文件/验收边界，避免两处重复实现 Gateway 恢复逻辑。

## 参考

- `scripts/deploy_v2.sh`
- `compose.yaml`
- `src/backend/cbrowser/supervisor/core.py`
- `src/backend/cbrowser/supervisor/docker_adapter.py`
- `src/backend/cbrowser/supervisor/runner.py`
- `src/backend/cbrowser/supervisor/container_spec.py`
- `src/backend/cbrowser/supervisor/network_spec.py`
- `docs/blueprint/architecture.md`
- `docs/blueprint/supervisor.md`
- `docs/blueprint/gateway.md`
- `docs/blueprint/decisions.md`
