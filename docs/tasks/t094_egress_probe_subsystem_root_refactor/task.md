# Task spec

## 背景

代理出口测速子系统存在同一个架构根因：把应由服务端编排的异步批量作业、应由测试承担的防泄露验证，分别降格塞进客户端 `for` 循环与运行时容器沙箱，再用局部补丁（超时调大、池化 helper、伪计时、加进度条）掩盖症状。具体表现：代理管理「全部测速」是客户端串行循环（`ProxyListPage.tsx:269-287`），`probingAll`/`probingId` 与服务端 observation 构成双重状态机，同步 `POST /proxies/{id}/probe` 最长 90s 与前端 30s 超时错配，「全部」只测当前页 50 条；egress probe 每次测速新建 helper 容器 + policy-agent sidecar + 专用 bridge 网络并 finally 强删，单次约 5s 且持续容器 churn，把「测速展示」与「验隔离/防泄露」焊成同一职责。

按项目开发铁律（架构至上、拒绝妥协、零兼容负担），p110/d049/t074 等补丁方案均属应拒绝的局部修补。本 task 从根因重构：同步 API 改为服务端异步作业 + SSE 进度 + 单一状态源 + 全量作用域；删除容器沙箱整条路径改为后端内轻量探测；防泄露验证归位到单元与端到端测试。不留双路径、不留兼容开关。p149、p150 共享 `egress_probe.py`/`proxies_router.py`/`ProxyListPage.tsx`/observation 表，合并为一个可独立验收的实现 commit。

## 契约区

### 范围

- 职责归位：egress probe 只提供测速与出口信息展示（出口 IP、国家城市、延迟）；防泄露/隔离验证由单元测试与端到端测试承担，不再由运行时探针承担，也不再把探针描述为防泄露保证。
- 删除容器沙箱整条路径（helper 容器、policy-agent sidecar、专用 bridge 网络、Docker 调用、finally 清理），改为后端内轻量探测：http/https/socks5 协议全覆盖、固定白名单回显域名并拒绝私有/保留地址、每请求独立 client 不共用全局代理环境变量、凭证不进命令行、`monotonic()` 只包 HTTP 往返、读本地 GeoIP。强制走代理由 http client 显式指定 proxy + `trust_env=False` 实现。
- API 契约重定义：删除同步单条 `/probe`；新增批量作业端点，入参为过滤条件/选择集而非当前页 id，立即返回 `202` + `job_id`；作业整体状态（total/completed/failed/state）持久化，逐项进度写入现有 observation 表（`pending → ok/failed` + `observed_at` + TTL）；长耗时从请求路径消失，长操作兜底超时由契约集中声明。
- 前端单一状态源：删除 `probingAll`/`probingId`；行状态读服务端 `observation_status === "pending"`，批量进度读作业状态并经已有 SSE 通道实时推送；提交作业后立即反馈「已提交 N 项」，路由切换/刷新后由 observation 恢复，批量期间行按钮禁用，不再靠 refetch 同步。
- 全量语义归位：作业作用域由服务端过滤条件定义，分页只作视图；代理总数 >50 时「全部测速」作用于过滤后全集。
- 同类位点一并重构：`useBatchActions.ts` 环境批量 start/stop/moveToGroup 改为服务端作业 + 进度事件，与代理测速共用同一进度 UI 组件，删除客户端串行循环与结束单一 toast；批量期间逐行反馈、失败可重试且不重复执行。
- 测试改写与补齐：改写绑定容器沙箱的现有 E2E/单元测试使其不依赖沙箱；补齐防泄露（代理强制、IPv6/DNS 不绕过、私有地址阻断、真实 IP 不泄露、fail-closed）的真实 Docker E2E 与单元测试；替换固化「客户端循环编排」的旧批量测试；新增作业编排/SSE 进度/单一状态源/全集作用域/超时收敛/规模测试。
- 同步 API/契约、OpenAPI 生成类型、前后端代码、文档/UI 文案与蓝图一并更新。

### 非范围

- 不做运行时代理策略的资质认证，不改变浏览器 Profile 隔离与指纹引擎本身的实现，不实现新的代理协议类型。
- 不在用户生产环境做破坏性验证；测试只用隔离夹具与可恢复副本。生产发布需另行授权。
- 不为旧同步 `/probe` 端点或容器沙箱保留兼容路径、开关或降级双路径。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [ ] AC-001：egress probe 的产物与文案只表达测速和出口信息展示（出口 IP、国家城市、延迟）；产品文档、UI 文案、API 契约及代码命名/注释中不再出现把探针表述为「自检隔离是否生效 / 防泄露保证」的描述，防泄露改由单元与 E2E 测试承担。
- [ ] AC-002：单次测速不再创建 helper 容器、policy-agent sidecar、专用 bridge 网络，也不产生 finally 强删；后端轻量探测对 http/https/socks5 全部支持而不降级，回显目标为固定白名单且私有/保留地址被拒，每个请求使用独立 client 不共用全局代理环境变量，凭证不进命令行，计时只覆盖 HTTP 往返，出口信息读本地 GeoIP；代码中不存在容器沙箱路径及其兼容开关。
- [ ] AC-003：同步单条 `/probe` 端点已删除；批量作业端点接受过滤条件/选择集而非当前页 id，立即返回 `202` 与 `job_id`，作业提交为毫秒级短请求而不依赖 `defaultTimeoutMs`；作业总状态（total/completed/failed/state）持久化，逐项进度写入 observation 表并呈现 `pending → ok/failed` 与 `observed_at`，长操作兜底超时由契约集中声明，原 30s/90s 错配调用点不再存在。
- [ ] AC-004：前端不再持有 `probingAll`/`probingId`；行按钮状态由服务端 `observation_status === "pending"` 驱动，批量进度由作业状态经 SSE 实时更新，提交后立即显示「已提交 N 项」，批量期间行按钮禁用；路由切换或刷新后进度由 observation 恢复，作业不中断，列表不再靠 refetch 同步状态。
- [ ] AC-005：「全部测速」作用于服务端过滤后全集，分页只影响视图；代理总数 >50 跨页时作业覆盖全集而非当前页，批量并发受服务端配额约束而非客户端串行。
- [ ] AC-006：环境批量 start/stop/moveToGroup 不再使用客户端串行循环与结束单一 toast，改为提交服务端作业并经同一 SSE 进度组件逐行反馈；部分失败保留逐项结果与重试入口，重试不重复执行已成功项。
- [ ] AC-007：绑定容器沙箱的现有 E2E/单元测试改为不依赖沙箱后仍覆盖代理强制、IPv6/DNS 不绕过、私有地址阻断、fail-closed 与真实 IP 不泄露；原固化「客户端循环编排」的批量测试被整体替换；新增覆盖作业编排、`202`/`job_id`、SSE 进度、刷新恢复、单一状态源、全集作用域、超时收敛与 >50 规模的测试。
- [ ] [deploy] AC-008：在本机隔离真实 Docker/Chrome 拓扑中，轻量探测对 http/https/socks5 出口展示正确且不泄露真实 IP、无容器/网络 churn，批量作业跨页全集、SSE 进度与刷新恢复在真实环境成立，防泄露负向断言（IPv6/DNS/私有地址）真实执行并留证。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

- 除 AC-008 外全部 AC 可自动测试；AC-008 须在本机隔离真实 Docker/Chrome 拓扑执行并留证，缺少前置不得用 mock、skip 或历史结果代替。AC-001 的文案清理以文档/UI/契约扫描结果验证。

## 上下文区

- 关联 spec：docs/specs/proxy_management.md
- 受影响 spec：`docs/specs/profile_management.md`、`docs/specs/runtime_lifecycle.md`、`docs/specs/browser_isolation.md`、`docs/specs/gate_verification.md`、`docs/specs/ui_design_system.md`；执行 finalization 时一并更新。
- 来源：p149、p150；核实于 2026-11-20T14:21:03+08:00，两条在 main（HEAD b297639）均仍有效、根因已分析、无等价 active/backlog task；用户授权按开发铁律聚合为一个 task，并纳入 `useBatchActions` 环境批量与沙箱依赖测试改写。来源 pending 保留完整现象、证据链与测试缺口，转办不代表修复完成。

### 有意不测

- 用户生产环境的代理与真实 Profile：不做破坏性验证；用隔离夹具与可恢复副本，不造生产数据。
- 未支持的新代理协议：协议范围维持 http/https/socks5，不扩展到本 task 之外的新类型。

### 测试策略

- TDD 先红后绿：先写契约层测试断言 `202`/`job_id`、过滤条件全集与 observation 迁移，再写前端作业提交/SSE/刷新恢复/行按钮禁用测试，再写环境批量共用进度组件测试，逐项驱动实现。
- 后端轻量探测用单元/集成测试覆盖协议全覆盖、白名单 SSRF 拒绝、独立 client 隔离、计时边界与 GeoIP 读取，并断言不再调用 Docker 适配器的 egress-probe 路径。
- 改写绑定沙箱的 E2E/单元测试为不依赖沙箱的防泄露断言；真实 Docker E2E 验证代理强制、双栈 IPv6/DNS 不绕过、私有地址阻断与 fail-closed 且不泄露真实 IP。
- 运行项目完整门禁（testing.md 的 doctor/test/blackbox），留存 OpenAPI 重新生成、前后端测试与真实 Docker E2E 证据；旧固化客户端循环的批量测试整体替换而非就地改预期。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无未核实外部契约。作业端点路径、SSE 事件格式与 observation 状态字段由本 task 的 OpenAPI 契约定义并在实现中一并生成；现有 observation 表 `pending → ok/failed` + `observed_at` + TTL 与 `trust_env=False` 强制走代理为已确认约束。

### 风险与回退

- 风险：删除同步 API 与容器沙箱属破坏性变更，OpenAPI/生成类型/E2E 全链路需同步；防泄露原由沙箱 netfilter「顺带保证」，删除后必须由测试真正补上，否则失去副作用防线；多代理并发若共用全局代理环境变量会串扰。
- 回退：不保留兼容双路径；失败时在独立 worktree 回退本实现 commit 并重跑门禁，防泄露测试未补齐前不得宣称可删沙箱。验证前制作隔离可恢复数据备份，生产发布另行授权。

### 依赖与约束

- 与 t074（已 done，方向相反：保留容器沙箱与客户端循环）形成架构替换，本 task 直接取代其相关实现，不叠加兼容层。
- 共享 `egress_probe.py`/`proxies_router.py`/`ProxyListPage.tsx`/observation 表与 `useBatchActions.ts`，须单一实现 commit 完成，避免与涉及同文件的其他 task 并行。
- API 唯一 DB 写者与 Supervisor 唯一 Docker 持有者边界保持；作业作用域由服务端过滤条件定义，不由页面 DOM 或分页推导。

### Finalization 时更新的 blueprint

- `docs/blueprint/architecture.md`：服务端异步作业编排、SSE 进度与 observation 单一状态源；后端轻量探测取代容器沙箱。
- `docs/blueprint/domain.md`：测速作业状态、过滤条件作用域、逐项进度与失败重试语义。
- `docs/blueprint/frontend.md`：提交即反馈、进度组件共用、刷新恢复与批量期间行按钮禁用。
- `docs/blueprint/testing.md`：不依赖沙箱的防泄露断言与真实 Docker E2E 验收。
