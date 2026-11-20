# Task spec

## 背景

代理出口测速子系统存在同一架构根因：把应由服务端编排的异步批量作业、应由测试承担的防泄露验证，分别降格塞进客户端 `for` 循环与运行时容器沙箱，再用超时调大、池化 helper、伪计时、加进度条等局部补丁掩盖症状。基于 main@b52808a 的可核对现状：

- 客户端编排长作业：`src/frontend/src/features/proxies/ProxyListPage.tsx:249-287` 的 `handleProbeAll` 用 `for...of visible` 串行 `await probeMutation.mutateAsync(item.id)`（`:273-275`）；`probingAll`/`probingId` 局部状态（`:157-158`）与行按钮读取的服务端 `observation_status === "pending"`（`:410`）构成双重状态机；`visible` 仅当前页（`:202-206`，`page_size` 50），整批结束只弹一次 toast（`:282-286`）。同类串行循环在 `src/frontend/src/features/profiles/useBatchActions.ts:40-73`。
- 同步请求承载长作业：公开路由 `POST /api/v1/proxies/{proxy_id}/probe`（`schemas/openapi/cbrowser_v1.json:4310-4311`）经 `src/backend/cbrowser/api/v1/proxies_router.py:162-185` → `src/backend/cbrowser/services/profile_service.py:1740-1820` → `src/backend/cbrowser/services/egress_probe.py:75` 的 `SupervisorEgressProbeRunner`（`:90` 默认 `timeout=90.0`，`:119-123` httpx client）。内部控制路由 `POST /supervisor/v1/proxies/{proxy_id}/probe`（`src/backend/cbrowser/supervisor/control_server.py:302-315` 的 `probe_proxy`）→ `src/backend/cbrowser/supervisor/docker_adapter.py:983` 的 `run_egress_probe`（`:990` 默认 `timeout=90.0`），每次建专用 bridge、helper 容器、policy-agent sidecar 并 finally 清理（`:1011-1040,1258-1287,1381-1398`）；容器内 helper 入口为 `src/backend/cbrowser/runtime_agent/egress_probe.py:40` 的 `main()`。前端旧调用 `src/frontend/src/shared/api/client.ts:664-668` 未传超时，吃 `ApiClient` 构造的 `defaultTimeoutMs = 30_000`（`:98`、`:115-119`）。两处 90s 是默认值而非实测耗时上限，与前端 30s 默认值构成两层默认超时错配。
- 历史开销样本：本机实测容器建毁约 5579.66 ms（`docs/tasks/t074_settings_persistence_modal_and_proxy_probe_overhaul/task.md:15`、`docs/spikes/s024_t074_lightweight_probe_isolation/report.md:38`），测量对象是 bridge 网 + helper + policy 容器 + Python 冷启动 + 清理，不是网络 RTT；当前代码仍能证明每次建毁，当前性能阈值须由独立夹具重新定义。

按项目开发铁律（架构至上、拒绝妥协、零兼容负担），本 task 取代 t074 的探测沙箱并清理其遗留编排，不叠加兼容层。历史归因以原文为准：p110 是已转办问题（`docs/pending/p110_proxy_probe_latency_persistence_and_timing.md:4-9`，`fix_ref: t074`）；d049 基于 s024 原型建议池化/常驻轻量 helper、每请求新建短生命周期 client，禁止复用的是跨请求 TCP 连接池（`docs/findings/d049_t074_lightweight_probe_isolation_and_timing.md:3-11`）；t074 要求保留与 Browser 同网络隔离边界并修正延迟、落盘和结构化错误（`docs/tasks/t074_settings_persistence_modal_and_proxy_probe_overhaul/task.md:33-40,62-65`），前端客户端串行是遗留（`docs/pending/p149_proxy_probe_all_no_feedback.md:39-46`），`docs/pending/p150_egress_probe_leak_verification_belongs_to_tests.md:18` 把「不池化」归给 d049 属误引。本 task 保留准确的延迟口径、失败原因和结果持久化契约，替换沙箱与编排方式。p149、p150 共享 `services/egress_probe.py`、`api/v1/proxies_router.py`、`ProxyListPage.tsx` 与 observation 表，合并为一个可独立验收的实现 commit。

## 契约区

### 范围

- 职责归位：egress probe 只提供测速与出口信息展示（出口 IP、国家码/国家名、城市、延迟）；防泄露/隔离验证由单元与端到端测试承担，不再由运行时探针承担，也不再把探针描述为防泄露保证。
- 退役探测沙箱：删除内部控制路由 `POST /supervisor/v1/proxies/{proxy_id}/probe`（`supervisor/control_server.py:302-315`）、容器内 helper（`runtime_agent/egress_probe.py:40`）、`probe_egress_plan`/`NetworkPolicySpec.proxy_enforced` 专属探测策略以及 `docker_adapter.py:1011-1040,1258-1287,1381-1398` 的执行与清理；删除公开同步路由 `POST /api/v1/proxies/{proxy_id}/probe`（`schemas/openapi/cbrowser_v1.json:4310-4311`、`proxies_router.py:162-185`）。
- 轻量探测实现约束：后端内 http/https/socks5 全覆盖、固定白名单回显域名（`src/backend/cbrowser/shared/egress.py:38-42`）且拒绝私有/保留/回环回显目标；代理上游地址按独立策略校验，宿主 loopback 代理沿用现有 `host.docker.internal` 映射契约（`docs/blueprint/supervisor.md:76`、`docs/archive/verification/t074_deploy_import_20261117.md:32-34`）；重定向与域名解析结果在探测执行面按白名单判定；显式指定 proxy + `trust_env=False`（`:156-185`）、每请求新建 client 不共用全局代理环境变量、凭证不进命令行、`monotonic()` 只覆盖一次成功 HTTP 往返（`:293-309`）、读本地 GeoIP（`:70-86,312-357`）并明确缺库/缺城市的状态与是否保留在线补充；探测失败无直连回退。结果标识从 API 视角定义，历史 Browser 视角观测（`src/backend/cbrowser/domain/egress_observation.py:17-39`）的保留或失效规则一并声明。API 镜像需新增 GeoIP/SOCKS 依赖生成（`pyproject.toml:12-24,30-35`、`config/docker/api_runtime/Dockerfile:13-14`、`config/docker/browser_runtime/requirements.txt:36,79`）。
- 作业契约：新增批量作业端点，入参为过滤条件/选择集而非当前页 id，立即返回 `202` + `job_id`；提交时冻结一次过滤后的目标 ID 集合；建立作业与成员的权威读模型（作业身份、成员身份、total/completed/failed/state、逐项结果与观测关联），区分页面刷新（客户端恢复）与 API 进程重启（服务端显式恢复或终结并暴露失败）；卡住的 pending 按预算收敛；作业提交、排队、单项执行与终态收敛分别设预算，长操作兜底超时由契约集中声明并限定本 task 覆盖的作业提交与批量动作。
- 自动探测与并发边界：创建代理、提供新 proxy_url（含端点/密码变更）触发的后台探测（`src/backend/cbrowser/services/profile_service.py:1652-1683,1685-1738,1860-1879`）与手动作业共用执行路径、配额和结果投影；重复提交、自动/手动重叠、执行中代理删除或配置改版、迟到结果与提交重试均有收敛规则；过期尝试无权覆盖当前结果，探测端点与凭据只能由服务端装载（`proxies_router.py:162-185`、`tests/integration/test_t052_proxy_api.py:428-450`），错误与事件保持脱敏。
- 前端单一状态源：删除 `probingAll`/`probingId`；行状态读服务端 `observation_status === "pending"`，批量进度读作业状态并经 SSE 更新；提交后立即反馈「已提交 N 项」，列表与卡片单行入口提交单成员作业，展示成功/部分失败/全失败汇总；新增作业进度事件与首读快照/断线超窗补齐（现有快照只取 Profile runtime：`src/backend/cbrowser/api/v1/router.py:175-233`；历史窗口 `maxlen=1000`：`src/backend/cbrowser/api/runtime_coordinator.py:105-113`；前端分派已知事件：`src/frontend/src/shared/api/sse.ts:376-408`）；「无 refetch」仅指稳态进度更新。
- 环境三动作作业化：start 经通用 desired-state 端点（`src/backend/cbrowser/api/v1/router.py:948-989`）、stop 经 `stop_profile`（`:996-1034`）、moveToGroup 复用 `PATCH /profiles/{id}`，改为提交服务端作业并共用进度组件；按动作定义目标快照、成功判定、部分失败恢复与成功项不重复执行；与已有批量删除（`:587-654`、`docs/specs/profile_management.md:36,40`）边界清晰。
- 测试改写与两条验收链：探针链从 `probe_egress_plan` 构造策略（`tests/e2e/test_supervisor_namespace_policy_e2e.py:716-729,819-825,856-862`）验证三协议、失败无直连与零容器/网络事件；Browser 链用监听代理日志证明 Chrome 出口经代理（`tests/e2e/test_proxy_library_e2e.py:272-294,329-335`）并验证 IPv4/IPv6/DNS、私有地址、失败封闭与公网出口对照；替换固化「客户端循环编排」的旧批量测试；保留 `docs/blueprint/testing.md:38-66` 的 doctor/test/blackbox 必跑门禁。
- 同步 OpenAPI 契约与生成类型、前后端代码、UI 文案及长期文档：修订 `docs/blueprint/supervisor.md:74-80`、`docs/blueprint/security.md:80-88`、`docs/specs/proxy_management.md:13-15,53-64`、`docs/specs/profile_management.md:132`，并在 `docs/blueprint/decisions/20261115_profile_sdk_proxy_webrtc_quic_drop.md:5-11` 补注 ADR 038 与探针策略的边界；旧观测数据与转办后孤立的来源 pending 一并登记迁移说明。

### 非范围

- 不改变 Browser/Stream 运行策略与 ADR 038 双栈 `OUTPUT DROP` 约束，不改指纹引擎，不新增代理协议类型，不做运行时代理策略的资质认证。
- 不为旧同步 `/probe` 端点、容器沙箱或客户端串行保留兼容路径、开关或降级双路径。
- 不重做批量删除与单项生命周期操作（已有持久化查询/重试契约），不实现 reset/clone 新语义。
- 不在用户生产环境做破坏性验证；测试只用隔离夹具与可恢复副本，生产发布需另行授权。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：egress probe 的产物和文案只表达测速与出口信息展示；`docs/blueprint/supervisor.md`、`docs/blueprint/security.md`、`docs/specs/proxy_management.md`、`docs/specs/profile_management.md`、`docs/guides/`、UI 文案、API 契约及代码命名/注释中不再出现把探针表述为「自检隔离是否生效 / 防泄露保证」的描述，防泄露由 AC-008/AC-009 的测试实际承担。
- [ ] AC-002：对 http/https/socks5 代理均能取得出口 IP、国家码/国家名、城市与延迟而无协议降级；回显目标仅限固定白名单且私有/保留/回环地址被拒；探测失败后不直连取得出口信息；两个代理并行探测的结果不串扰；凭据不出现在命令行、日志与事件；延迟数值排除 client 构造、多次回显尝试与网络策略生命周期，只对应冻结口径下的一次成功往返。
- [ ] AC-003：批量作业端点接受过滤条件/选择集而非当前页 id，立即返回 `202` 与 `job_id`；阻塞探测夹具证明提交响应先于任何单项执行完成返回，且提交在明确的毫秒级预算内；「已提交 N 项」的 N 有确定的接受项数来源，零匹配项返回明确的 0 项语义；超过服务端配额或作业超时返回可见结果而非静默丢弃。超时收敛声明只涵盖本 task 的作业提交与批量动作。
- [ ] AC-004：作业存在权威读模型，可回读作业身份、成员身份、total/completed/failed/state 与逐项结果及其观测关联；页面刷新后由读模型恢复进度且作业不中断，API 进程重启后按显式规则恢复或终结并暴露失败；卡住的 pending 在定义预算内收敛为终态；重叠作业和自动探测的新观测不覆盖在途作业的归属结果，重复提交与迟到结果不会让已收敛作业再次变化。
- [ ] AC-005：前端进度仅由服务端作业状态驱动，不持有与服务端并行的本地进度状态；提交后立即显示已提交项数，SSE 进度实时更新，列表与卡片单行入口各提交单成员作业，并显示成功/部分失败/全失败汇总；批量期间行按钮禁用范围与解除时点明确；首读快照与断线超窗（`runtime_coordinator.py:111` 的 1000 条环形缓冲）由快照重建/`resync-required` 补齐，重复与迟到事件有围栏；稳态进度更新不靠 refetch。页面刷新、多标签页、断线后收敛分别验证。
- [ ] AC-006：作业作用于提交时冻结的过滤后 ID 集合，分页只影响视图；跨页且混有不匹配项的夹具断言精确 ID 集合与并发上限；过滤维度（country/city 取自观测，`proxies_router.py:40-61`、`docs/specs/proxy_management.md:13,53-55`）在测速追加观测导致归属变化时目标集合不漂移。
- [ ] AC-007：环境批量 start/stop/moveToGroup 改为提交服务端作业，进度呈现与代理测速一致；按动作定义目标选择快照、成功判定、分组删除/环境消失/冲突的结果、部分失败恢复与成功项不重复执行；延迟任务、部分失败和重复重试各自独立验收；与已有批量删除及单项生命周期操作的边界明确。
- [ ] [deploy] AC-008：真实 Docker 探针链验证 http/https/socks5 出口展示、失败无直连回退、零 helper/网络/策略资源事件与冻结后的延迟口径；受控代理/回显/GeoIP 夹具、预期出口、应为零的旁路流量以及 Junit/网络/Docker 事件证据齐全；从 `probe_egress_plan` 构造策略的现有内核用例改写后仍触达生产路径。
- [ ] [deploy] AC-009：真实 Docker/Chrome 的 Browser 防泄露链验证 IPv4/IPv6/DNS、私有地址阻断、失败封闭与公网出口对照，且配置代理的 Browser Profile 继续受 ADR 038 双栈 `OUTPUT DROP` 约束；监听代理日志证明浏览器出口经代理，镜像与 Chrome 前置、预期出口、应为零的直连/STUN/外部 DNS 旁路流量与 Junit/网络证据齐全。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- AC-001 以文档/UI/契约全文扫描加 AC-008/AC-009 测试存在性验证；AC-002~007 可自动测试；AC-008、AC-009 须在本机隔离真实 Docker/Chrome 拓扑执行并留证，缺少前置不得用 mock、skip 或历史结果代替。

## 上下文区

- 关联 spec：docs/specs/proxy_management.md
- 受影响 spec：`docs/specs/profile_management.md`、`docs/specs/runtime_lifecycle.md`、`docs/specs/browser_isolation.md`、`docs/specs/gate_verification.md`、`docs/specs/ui_design_system.md`；执行 finalization 时一并更新。
- 来源：p149、p150；核实于 2026-11-20T14:32:31+08:00，基线 main@b52808a。立项时引用的 `b297639` 可解析为 `b2976392f926e14f71331304b1717f516b5722b0`，为当前 HEAD 祖先，二者之间仅新增 t094 文档与两份来源 pending。两条来源均仍有效、问题未被解决、无等价 active/backlog task；用户授权按开发铁律聚合为一个 task，并纳入 `useBatchActions` 环境批量与沙箱依赖测试改写。来源 pending 保留完整现象、证据链与测试缺口，转办不代表修复完成。

### 有意不测

- 用户生产环境的代理与真实 Profile：不做破坏性验证；用隔离夹具与可恢复副本，不造生产数据。
- Browser/Stream 运行策略重设计：维持 ADR 038 与现有双栈出站约束，不在本 task 重做。
- 未支持的新代理协议：范围维持 http/https/socks5，不扩展到本 task 之外的新类型。

### 测试策略

- TDD 先红后绿：先用阻塞探测夹具写作业提交与读模型测试，再写前端即时反馈/SSE 进度/刷新恢复/单行与汇总/围栏测试，再写环境三动作与冻结集合/跨页/并发上限测试，逐项驱动实现。
- 轻量探测用单元/集成测试覆盖三协议、白名单 SSRF 拒绝、独立 client 隔离、冻结的延迟口径、GeoIP 与无直连回退，并断言不再调用 `supervisor/control_server.py` 的探测路由与 `docker_adapter.py` 的 helper 建毁路径。
- 两条 E2E 链分别验收：探针链覆盖 http/https/socks5、失败无直连与零 Docker 资源事件；Browser 链覆盖 IPv4/IPv6/DNS、私有地址、失败封闭、公网出口对照与零旁路流量。受控代理/回显/GeoIP 夹具、镜像与 Chrome 前置、出口与网络证据均留档。
- 运行 `docs/blueprint/testing.md:38-66` 的 doctor/test/blackbox 必跑门禁，留存 OpenAPI 重新生成、前后端测试与真实 Docker E2E 证据；替换旧入口时确保仍触达生产路径，旧固化客户端循环的批量测试整体替换而非就地改预期。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- API 镜像三协议可达性（已核实）：API 组仅声明 `httpx`（`pyproject.toml:12-24`）、API 镜像 requirements 无 `socksio`/`geoip2`（`config/docker/api_runtime/requirements.txt`，对照 `config/docker/browser_runtime/requirements.txt:36,79`）。结论：本 task 须在 API 依赖生成中补齐并从 API 镜像内验证； socks5 不降级由 AC-002/AC-008 的受控 socks5 代理夹具断言，不再作为未知项。
- DNS 解析边界（已核实）：`docs/blueprint/supervisor.md:74` 定义配置代理或出口探测时 IPv4/IPv6 `OUTPUT DROP`，仅放行解析后代理地址与 `127.0.0.11:53/udp` Docker DNS。结论：轻量探测复用 `egress_plan` 同源口径，不受外部 DNS 直连由 AC-008/AC-009 的外网流量断言验证，不再作为未知项。
- 回显/Geo 服务的可信证书与 TLS 校验（已核实）：`src/backend/cbrowser/shared/egress.py:173` 的 `httpx.Client(` 未传 `verify=`，默认启用证书校验。结论：轻量探测沿用默认校验并在校验失败时失败封闭，由 AC-008 受控夹具验证，不再作为未知项。
- 真实 Compose 拓扑下 GeoIP 读权限与响应性（已核实）：`compose.yaml:137` 由 Supervisor 配置 `CBROWSER_GEOIP_CACHE`，API 镜像当前无 `geoip2`。结论：本 task 补齐 API 镜像依赖并读取同一缓存路径；探测等待期间普通 API 与 SSE 仍可响应由 AC-008 验证，不再作为未知项。

### 风险与回退

- 风险：删除同步 API 与容器沙箱属破坏性变更，OpenAPI/生成类型/E2E 需同步；沙箱 netfilter 原「顺带保证」被移除，必须由测试真正补上；API 镜像缺 GeoIP/SOCKS 依赖会导致 socks5 降级；探测等待可能阻塞普通 API 与 SSE；作业读模型缺失会使刷新/重启后进度不可恢复。
- 回退：不保留兼容双路径。区分开发提交回退与迁移后数据恢复：失败时在独立 worktree 回退实现 commit 并重跑门禁；持久化作业涉及 SQLite 演进，按 `scripts/deploy.sh:1162-1204` 目标迁移版本须等于库当前版本且无降级迁移，用旧版本与备份配对的隔离恢复验证。防泄露测试未补齐前不得宣称可删沙箱，生产发布另行授权。

### 依赖与约束

- 取代 t074 的探测沙箱与客户端编排遗留，保留其准确延迟口径、失败原因与结果持久化契约，不叠加兼容层。
- 共享 `services/egress_probe.py`、`api/v1/proxies_router.py`、`ProxyListPage.tsx`、observation 表与 `useBatchActions.ts`，须单一实现 commit 完成，避免与涉及同文件的其他 task 并行。
- API 唯一业务 DB 写者、Supervisor 唯一 Docker Socket 持有者边界保持；Browser/Stream 运行策略继续受 ADR 038 约束，共享 GeoIP 消费边界不越界；作业作用域由服务端过滤条件定义，不由页面 DOM 或分页推导。
- 当前无其它 active/backlog task，无依赖与冲突需登记。

### Finalization 时更新的 blueprint

- `docs/blueprint/architecture.md`：服务端异步作业编排、SSE 进度与作业/成员权威读模型；后端轻量探测取代容器沙箱。
- `docs/blueprint/domain.md`：测速作业状态、冻结的过滤作用域、逐项结果、终态保留与失败重试语义。
- `docs/blueprint/frontend.md`：提交即反馈、进度组件共用、刷新/断线恢复与批量期间行按钮禁用。
- `docs/blueprint/testing.md`：两条独立验收链、不依赖沙箱的防泄露断言与真实 Docker 门禁证据。
- `docs/blueprint/supervisor.md`、`docs/blueprint/security.md`：移除探测 helper/RPC/专属策略与「helper 是唯一例外」表述，声明探针失败无直连回退。
- `docs/blueprint/decisions/20261115_profile_sdk_proxy_webrtc_quic_drop.md`：补注 ADR 038 与探针策略边界；`docs/specs/proxy_management.md`、`docs/specs/profile_management.md` 同步修订过时表述。
