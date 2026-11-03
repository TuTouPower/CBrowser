# Task spec

## 背景

Gateway 容器替换后丢失 Profile 网络附着，既有 Stream 仍连接旧地址，Browser 活着却无信令。当前附着只在启动时执行，同实例 reconcile 提前返回，API 不可用时不能独立恢复数据面。

## 契约区

### 范围

- 统一使用现有 Supervisor 启动扫描、Docker 事件、30 秒兜底与每 Profile 锁，实现持续幂等 RuntimeReconciler；提供受内部认证保护的显式 reconcile_all/readiness 契约供 t027 消费。
- 保持每 Profile 媒体 bridge 与 Gateway 多宿；建立网络级固定 Gateway 端点和所有权标签，固定端点在 Docker IPAM 中可合法保留/附着且不能被普通自动分配占用。不得盲用 aux address：若 Docker 将其标为不可供 endpoint 使用，须采用实测可行的等价保留方式。
- 按顺序收敛附着、受限 egress policy、当前 runtime_instance_id 的 Agent 注册；API 离线仍依据受管 Docker 对象恢复网络连接，生命周期意愿仍由 API 权威保存。
- Agent 注册增加协议版本/构建标识；不兼容或注册持续缺失时有界退避，只滚动替换 Stream，Browser 与页面保留；Gateway 不可达时不无限重建 Stream。
- 经 API/SSE/生成 schema 暴露 browser/stream/transport 分层状态、协议与最近附着/注册/错误；前端区分 recovering 与明确失败。

### 非范围

- 不承担镜像发布控制器与 release env，交 t027；不引入第二个协调循环、K8s、共享媒体网络或 Gateway Docker Socket。
- 不迁移旧 Runtime 或保留双协议/一次性附着兼容路径；不停止所有 Browser 作为修复手段；真实故障执行交 t032。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001：事件与周期扫描面对同一运行实例也检查并修复 Gateway 附着和策略；Gateway 替换、断网或 Supervisor 重启后，在配置的有界收敛窗口内重建连接；通过生产收敛器故障注入验证。
- [ ] AC-002：Stream URL 与 egress policy 使用同一固定 Gateway 端点；地址冲突、错误标签或无法保证端点唯一时显式 degraded/失败，绝不退回随机地址或整网放行。
- [ ] AC-003：API 失联期间，合法既有 Browser/Stream/网络仍能完成数据面重新附着；不执行未知生命周期意愿，不把 API 不可达当成清理授权。
- [ ] AC-004：多 Profile 并发、重复事件与周期扫描幂等且不串网；未知 endpoint 拒绝清理，失败只回滚本轮新建连接，已有合法连接和 Browser 保留。
- [ ] AC-005：Gateway 按显式协议版本接受/拒绝 Agent；拒绝与持续未注册可被 Supervisor 诊断；仅在前置条件成立时有界重建对应 Stream，Browser 实例、内部页面和 Profile 数据不变。
- [ ] AC-006：readiness 对所有 desired=running Profile 校验当前实例、Browser/Stream 进程、Gateway 附着、策略与 Agent 注册；API/意愿查询不可用或状态未知时不能报 ready，返回逐 Profile 可脱敏诊断。
- [ ] AC-007：API/SSE 与前端可观察运行和传输状态差异；信令 1006 在 recovering 时呈现恢复中，明确失败或超出恢复窗口才显示失败；导出 schema 与前端类型同生产响应一致。
- [ ] AC-008：以生产入口完成 Gateway 替换、API 离线、协议不兼容、地址占用、并发事件和恢复失败测试；交付对应 Docker 故障用例供 t032，测试不得只检查替身调用次数。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；AC 中“目标探针/用例交付”只验入口、断言、报告和收集，不表示已完成目标实跑。真实环境行为执行只在 t032 判定。

## 上下文区

### 执行环境与参考来源

- 执行环境：云端 Muse。完成实现、触达生产逻辑的 unit/integration、可用的普通 Chromium 测试，以及可收集的真实环境用例和逐项运行说明。不要求访问宿主 Mac、OrbStack、用户局域网或真实 CloakBrowser/Stream 镜像；这些执行义务集中到 t032。本 task 的 AC 只验云端交付，不把模拟结果、collect-only、skip 或历史 trust_prior 当作目标环境 PASS。代码交付完成不表示目标环境已验收；t032 通过前不得据此发布或宣称指纹安全。

- ego-lite 参考仓库：https://github.com/citrolabs/ego-lite ；固定研究基线：https://github.com/citrolabs/ego-lite/tree/12407167f84a58af24044f072868051952131491 。云端可直接读取公开源码，无需本机目录。其 AGENTS.md 明确只开源 harness/Skill，浏览器本体与 globalThis.ego 原生绑定闭源；只能借鉴公开实现与故障案例，不依赖原生绑定，不照搬合成事件兜底，不将上游效果当成本项目证据。

- 来源：p034（运行时部分）；2026-11-04，main@c6a9322 核实。core.py 的 \_reconcile_profile 同实例分支仍提前结束，启动路径仍单次调用 attach_profile_infrastructure；docker_adapter.py 将分配地址写入运行时，runner.py 现有事件/周期扫描可复用。p034 已含真实容器日志与网络根因，本轮静态复核仍成立。t022 已 done，其 Agent 恢复预算不覆盖基础设施容器替换。

### 有意不测

- 宿主 Mac/OrbStack、目标 CloakBrowser、真实媒体/X11/指纹站点：当前 task 执行端为云端 Muse，统一由 t032 执行；不得记为 PASS。

### 测试策略

- 先建立替换 Gateway 的失败测试，直接触达 Supervisor、DockerAdapter 与真实 Gateway HTTP/WS；Docker 替身只用于故障注入，不冒充网络隔离证据。
- 逐项验证锁、fence、退避/次数上限、API 离线、未知资源保护；导出 Supervisor/Gateway/OpenAPI 契约并验证，补前端恢复状态测试。
- 真实固定地址 IPAM、故障矩阵、WebRTC 与 Browser 生存性在 t032 执行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无（云端行为契约）；真实 Docker 端点保留机制与目标拓扑恢复由 t032 判定。实现须交付可验证的 Docker API 调用及探针，不能把未执行的 IPAM 假设写成 finding 或已验结论。

### 风险与回退

- 风险：错误附网或宽放策略破坏隔离；超时过短造成 Stream 重建风暴；旧代次观测污染新实例。
- 回退：保留本轮失败诊断；只撤销新建连接。版本回退由 t027 明确 release env；禁止回滚时删除运行 Browser 或用户数据。

### 依赖与约束

- 无未完成硬依赖。
- 云端/本地边界遵循“执行环境与参考来源”；真实执行义务只在 t032 判定。

### Finalization 时更新的 blueprint

- docs/blueprint/architecture.md：持续收敛与组件生命周期。
- docs/blueprint/supervisor.md：固定端点、锁、离线收敛和 readiness。
- docs/blueprint/gateway.md：协议握手、注册与传输观测。
- docs/blueprint/decisions.md：基础设施可替换与 Stream 升级边界 ADR。
- docs/blueprint/frontend.md、docs/blueprint/testing.md：恢复状态和故障矩阵。
