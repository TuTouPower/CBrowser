# Task spec

## 背景

Gateway 容器替换后丢失 Profile 媒体网络附着；既有 Stream 的 `CBROWSER_GATEWAY_URL` 与 netns egress 白名单在创建时写死当时的 Gateway IP（`docker_adapter.py:763`、`network_policy.py`），Browser 活着却无信令。现行代码缺口：

- 收敛：附着只在 `start_profile` 调用一次（`core.py:1044-1054`）；同实例 reconcile 分支提前返回（`core.py:308-335`）；API 不可达时在任何数据面检查前返回（`core.py:268-278`）。Docker 事件只订阅 `type=container`（`runner.py:224-227`），扫描跳过 `role=gateway`（`docker_adapter.py:1258`），Gateway 身份是启动参数里的静态 ID/名称（`runner.py:388`、`core.py:151`）。
- 地址：Profile 网络使用自动 subnet（`docker_adapter.py:657`）。d029 已实测：固定且受保护的 Gateway 地址只能用显式 subnet + ip_range 预留，aux-address 不可用，既有网络无法就地补 ip_range。
- 策略：`apply_policy` 在已有 filter 规则时拒绝安装（`network_policy.py:274-292`）；policy readiness 只看 `ready.json` 标记（`docker_adapter.py:1216-1246`），不校验实际规则。
- 恢复：没有 Stream-only 替换；Stream 缺失时 RecoveryCoordinator 停止整对（`recovery_coordinator.py:523-598`）；Stream running 但未注册时 `runtime_pair_active` 仍为 true（`recovery_rules.py:92-105`）。
- 协议与观测：注册已有 `version: Literal["v2"]`、selkies/config 版本（`protocol.py:192`），缺 build 标识与结构化拒绝原因；没有 reconcile_all/readiness；Supervisor 无发布端口，Caddy 只代理 `/api/*`。运行模型无分层传输状态（`models.py:486-509`），前端 SSE 同步逐字段手写拷贝（`useProfilesQuery.ts:261-280`），首次连接 1006 直接 `signaling_failed`（`useBrowserSession.ts:245-273`）。
- 门禁：`tests/integration/test_api_search_defaults_routes.py::test_retry_route_requires_csrf_and_maps_outcomes` 必败——stub 返回 `inst_1`，测试 Profile 未绑定实例，被 t022 实例 fence（`runtime_views.py:24`）正确过滤；t023/t024 按存量放过，`scripts/run_gates.sh` integration 段因此恒失败。

## 契约区

### 范围

- 门禁前置：修复 search-defaults 路由测试夹具，使 Profile 绑定实例与 stub 一致，原断言不变；新增实例不一致时 `search_defaults` 为 null 的负例。
- 持续收敛：复用 Supervisor 启动扫描、Docker 事件、30 秒兜底与每 Profile 锁实现幂等 RuntimeReconciler；事件订阅扩展到受管 Profile 网络与 Gateway 容器；扫描纳入 Gateway；Gateway 身份每轮按 prefix/role/managed-by 标签解析。同实例分支也检查附着、实际策略与注册；API 离线仍依据受管 Docker 对象恢复网络附着，生命周期意愿仍由 API 权威保存。
- 固定端点：按 d029，Supervisor 为每个 Profile 媒体网络从可配置地址池分配显式 subnet，检测与现有 Docker 网络及宿主路由冲突；固定 Gateway 地址在 subnet 内、ip_range 外；子网、端点与所有权写入标签。Stream URL 与 egress policy 只使用固定端点。
- 规格收敛：不符合新规格的既有 Profile 媒体网络（含本 task 前创建的）由 Stream-only 替换收敛：重建媒体网络与 Stream，Browser 及其独立网络不动；不保留旧规格兼容路径。
- 策略校验：readiness 与收敛检查比对实际 netns 规则与渲染规格；Stream 不一致以 Stream-only 替换修复；Browser 不一致立即 fail-closed 并报告 error，等待显式重启。
- Stream-only 替换能力：保留 Browser 容器、IPC/X11、页面与 Profile 数据；Stream 缺失或持续未注册时有界退避替换 Stream，不停止整对；Gateway 不可达时不重建 Stream。
- 注册诊断：沿用现有协议版本字段，增加 build 标识与结构化拒绝原因，供 Supervisor 经 Gateway 控制面诊断。
- reconcile_all/readiness：归 Supervisor，使用现有 Supervisor 内部 token 认证；宿主机经容器内命令调用本地控制面（供 t027 以 `docker compose exec` 消费），不新增发布端口或 Caddy 路由；readiness 从 API 取当前全部 desired=running Profile；契约经 Supervisor 协议导出为 schema。
- 分层观测：Supervisor 上报 browser/stream/transport 观测，API 内存保存最新值经运行响应与 SSE 暴露，不新增数据库列或迁移；前端 SSE 同步完整携带新字段，区分 recovering 与明确失败。

### 非范围

- 不承担镜像发布控制器、release env 与 compose 健康检查/健康端点，交 t027；不引入第二个协调循环、K8s、共享媒体网络或 Gateway Docker Socket。
- 不保留旧网络规格或一次性附着兼容路径；不停止所有 Browser 作为修复手段；不持久化传输观测。
- 配额链路、Agent 替换断言等 p016 其余回归交 t028；真实 Docker 故障执行交 t032。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：本 task 基线上 `scripts/run_gates.sh` 非 E2E 段全部通过；search-defaults 路由测试原断言不变，并有实例不一致时 `search_defaults` 为 null 的负例。
- [x] AC-002：同实例周期扫描、Gateway 容器事件与 Profile 网络 connect/disconnect 事件均触发附着、策略与注册检查；Gateway 替换为新容器 ID、断网或 Supervisor 重启后，在配置的有界窗口内以同一固定端点重新附着，Browser/Stream 不重建；通过生产收敛器故障注入验证。
- [x] AC-003：新建 Profile 媒体网络使用 Supervisor 分配的显式 subnet 与 ip_range，Gateway 固定端点位于 range 外，Stream URL 与 egress policy 使用该端点；地址池耗尽、subnet 冲突、端点被占或标签不符时显式 degraded/失败，绝不退回随机地址或整网放行。
- [x] AC-004：规格不符的既有媒体网络经 Stream-only 替换收敛到新规格；Browser 容器 ID、内部页面、IPC/X11 与 Profile 数据不变，替换期间 Viewer 呈现恢复中。
- [x] AC-005：实际 netns 规则与渲染规格不一致或缺失时被检测：Stream 经 Stream-only 替换修复；Browser 立即进入拒绝全部非 loopback 流量的 fail-closed 状态并报告 error，不在无策略状态继续运行，不自动 teardown；新建沙箱等待策略的既有宽限与清理语义不变。
- [x] AC-006：API 失联期间，按 Docker 标签与实例一致性判定合法的既有 Browser/Stream/网络仍完成网络重新附着；Agent 注册与信令按 ADR 010 等待 API 恢复，期间 readiness 为未就绪；不执行未知生命周期意愿，不把 API 不可达或 404 以外的响应当清理授权。
- [x] AC-007：多 Profile 并发、重复事件与周期扫描幂等且不串网；未知 endpoint 拒绝清理；附着后策略安装或校验失败只回滚本轮新建连接，已有合法连接与 Browser 保留。
- [x] AC-008：Gateway 依现有协议版本字段接受或拒绝 Agent，拒绝时返回结构化原因与 build 标识；Supervisor 可诊断拒绝与持续未注册；仅在 Gateway 可达且原因可由替换修复时有界退避地替换对应 Stream；Stream 缺失或未注册不再导致停止整个 Browser/Stream 对。
- [x] AC-009：Supervisor 提供经内部认证的 reconcile_all 与 readiness，宿主机经容器内命令调用，无新增发布端口或 Caddy 路由；readiness 对 API 当前全部 desired=running Profile 校验当前实例、Browser/Stream 进程、固定端点附着、实际策略与 Agent 注册；API/意愿查询不可用或任一状态未知时不报 ready，返回逐 Profile 可脱敏诊断；契约导出 schema 并有一致性测试。
- [x] AC-010：API 运行响应与 SSE 暴露 browser/stream/transport 分层观测、协议与最近附着/注册/错误，不新增持久化列；API 重启后为 unknown 直至下次上报；导出 schema、前端类型与 SSE 缓存同步和生产响应一致，新增字段不在前端同步中丢失。
- [x] AC-011：信令 1006（含首次连接）在 transport 为 recovering 时呈现恢复中；明确失败或超出恢复窗口才显示失败。
- [x] AC-012：以生产入口覆盖 Gateway 替换、网络事件、API 离线、协议拒绝、地址冲突与池耗尽、规格迁移、策略漂移、并发事件和恢复失败；Docker 替身按 d029 已核实行为返回错误，测试不得只检查替身调用次数；交付可收集的真实 Docker 故障用例与运行说明供 t032 AC-009，执行环境有 Docker daemon 时须实跑并记录结果。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；AC 中“目标探针/用例交付”只验入口、断言、报告和收集，不表示已完成目标实跑。真实环境行为执行只在 t032 判定。

## 上下文区

### 执行环境与参考来源

- 执行环境：云端 Muse。完成实现、触达生产逻辑的 unit/integration、可用的普通 Chromium 测试，以及可收集的真实环境用例和逐项运行说明。不要求访问宿主 Mac、OrbStack、用户局域网或真实 CloakBrowser/Stream 镜像；这些执行义务集中到 t032。本 task 的 AC 只验云端交付，不把模拟结果、collect-only、skip 或历史 trust_prior 当作目标环境 PASS。代码交付完成不表示目标环境已验收；t032 通过前不得据此发布或宣称指纹安全。

- 来源：p034（运行时部分）；2026-11-04，main@c6a9322 核实，同日按三方审阅修订并实测 d029。p034 已含真实容器日志与网络根因。审阅补充：网络事件与 Gateway 扫描缺口、策略不可重入与标记式 readiness、整对停止、协议字段已存在、观测与 1006 前端缺口、search-defaults 门禁必败。t022 已 done，其 Agent 恢复预算不覆盖基础设施容器替换。

### 有意不测

- 宿主 Mac/OrbStack、目标 CloakBrowser、真实媒体/X11/指纹站点：当前 task 执行端为云端 Muse，统一由 t032 执行；不得记为 PASS。

### 测试策略

- 先修门禁测试夹具并确认 integration 全绿，再建立 Gateway 替换失败测试；直接触达 Supervisor、DockerAdapter、RecoveryCoordinator 与真实 Gateway HTTP/WS；Docker 替身只用于故障注入，不冒充网络隔离证据。
- 逐项验证锁、fence、退避/次数上限、API 离线、未知资源保护、subnet 分配冲突与 Browser fail-closed；导出 Supervisor/Gateway/OpenAPI 契约并验证，补前端恢复状态与 SSE 字段同步测试。
- 真实固定地址 IPAM、故障矩阵、WebRTC 与 Browser 生存性在 t032 执行。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 固定端点 IPAM：已核实（d029，Docker 29.4.0/OrbStack）——显式 subnet + ip_range 预留可行，aux-address 不可用，自动 subnet 无预留；其它 Docker 版本由 t032 在目标环境复核。

### 风险与回退

- 风险：错误附网或宽放策略破坏隔离；分配 subnet 与用户局域网冲突；超时过短造成 Stream 重建风暴；旧代次观测污染新实例；Browser fail-closed 使用户页面暂时断网。
- 回退：保留本轮失败诊断；只撤销新建连接。版本回退由 t027 的 release 机制承担；禁止回滚时删除运行 Browser 或用户数据。

### 依赖与约束

- 无未完成硬依赖；与 t025 互斥；t027 与 t031 以本 task 为硬依赖。
- 云端/本地边界遵循“执行环境与参考来源”；真实执行义务只在 t032 判定。

### Finalization 时更新的 blueprint

- docs/blueprint/architecture.md：持续收敛与组件生命周期。
- docs/blueprint/supervisor.md：subnet 分配与固定端点、锁、离线收敛、Stream-only 替换、策略校验与 readiness。
- docs/blueprint/gateway.md：协议拒绝原因、build 标识、注册与传输观测。
- docs/blueprint/decisions.md：基础设施可替换、固定端点地址分配、Stream-only 替换与 Browser fail-closed ADR。
- docs/blueprint/frontend.md、docs/blueprint/testing.md：恢复状态和故障矩阵。
