# Task review t026（reviewer_focus: 测试）

- task：`t026_runtime_infrastructure_reconciliation`
- spec：`docs/tasks/t026_runtime_infrastructure_reconciliation/task.md`
- diff_anchor：`c2bd696bf7b2ca869642abb3cf0ea2dc4f6382b3`
- target：`git -C 'CBrowser_t026' diff c2bd696bf7b2ca869642abb3cf0ea2dc4f6382b3`
- round：1
- reviewed_at：2026-11-04T10:05:41+08:00

reviewed_scope: a8ff45528b1989b1

## Findings

### t026_test_f001 - AC-002 的网络事件触发路径无任何测试，事件唤醒靠未验代码

- 严重度：important
- 锚点：AC-002——「Gateway 容器事件与 Profile 网络 connect/disconnect 事件均触发附着、策略与注册检查……通过生产收敛器故障注入验证」
- 位置：`src/backend/cbrowser/supervisor/runner.py:257`（`watch_docker_network_events`）；测试侧全仓 grep 无引用
- 问题：t026 新增的网络事件订阅（按 `{prefix}-net-` 前缀过滤 Actor name 并 `scan_wakeup.set()`）没有任何 unit/integration 测试触达。新增收敛测试（`tests/unit/test_t026_supervisor_convergence.py`）全部直接调用 `core._converge_session(...)`，只证明「扫描一旦运行能收敛」，不证明「网络事件能唤醒扫描」。`docs/blueprint/testing.md` 的 t026 故障矩阵亦自述该项仅为「runner 代码路径，真实事件流归 t032」——但事件过滤/唤醒的逻辑本身可在云端用替身事件流验证，不属于「有意不测」的真实环境执行。若前缀过滤或 Actor 属性提取写错（如 Docker 事件 name 字段位置不符），事件加速静默失效、只剩 30 秒兜底，AC-002 的「有界窗口内重新附着」在事件路径上无证据。
- 建议：给 `watch_docker_network_events` 加替身事件流测试：受管 Profile 网络的 connect/disconnect 事件置位 wakeup、无关网络事件不置位、事件流异常时不崩溃且扫描兜底仍在。

### t026_test_f002 - AC-009 readiness 的逐 Profile 校验逻辑与宿主 CLI 均无测试

- 严重度：important
- 锚点：AC-009——「readiness 对 API 当前全部 desired=running Profile 校验当前实例、Browser/Stream 进程、固定端点附着、实际策略与 Agent 注册；……返回逐 Profile 可脱敏诊断；宿主机经容器内命令调用」
- 位置：`src/backend/cbrowser/supervisor/core.py:619`（`readiness`）、`src/backend/cbrowser/supervisor/core.py:668`（`_profile_readiness`）、`src/backend/cbrowser/supervisor/control_client.py:1`
- 问题：readiness 唯一的行为测试 `test_readiness_unknown_when_api_unavailable`（`tests/unit/test_t026_supervisor_convergence.py:312`）走的是 API 列表请求失败的早退分支（其 `_make_core` 的 MockTransport 对一切请求返回 404），`_profile_readiness` 的逐 Profile 校验（实例/进程/附着/策略/注册五项 checks 与 diagnostics 组装）从未被执行。控制面测试 `tests/unit/test_t026_control_endpoints.py:40` 用 `_StubCore.readiness` 返回罐头 `ReadinessResponse`，只验路由与鉴权，不验 readiness 逻辑本身。AC-009 指定的宿主入口 `control_client.py`（`docker compose exec ... control_client readiness`）在 `tests/` 中零引用，其参数解析与退出码/输出契约未验。结果是 AC-009 核心条款被打勾，但支撑证据只覆盖「API 挂时不报 ready」与 schema 一致性。
- 建议：用 MockTransport 造 API 返回 desired=running Profile 列表与 runtime 的场景，覆盖 `_profile_readiness` 全 ready、单项未知不 ready、逐 Profile diagnostics 三类断言；给 `control_client` 加一条以替身 HTTP 响应驱动的 CLI 冒烟测试（readiness/reconcile 两子命令各一）。

### t026_test_f003 - AC-007 的回滚、未知 endpoint 与多 Profile 并发条款无测试

- 严重度：important
- 锚点：AC-007——「多 Profile 并发、重复事件与周期扫描幂等且不串网；未知 endpoint 拒绝清理；附着后策略安装或校验失败只回滚本轮新建连接，已有合法连接与 Browser 保留」
- 位置：实现 `src/backend/cbrowser/supervisor/docker_adapter.py:861`（`newly_connected` 回滚，约 938–953 行 disconnect 本轮新建连接）；测试侧 `tests/unit/test_t026_media_network_adapter.py`、`tests/unit/test_t026_supervisor_convergence.py` 全文无对应 case（grep `rollback|unknown.*endpoint|concurr` 在 t026 新测试中零命中）
- 问题：生产代码实现了「attach 失败只 disconnect 本轮新建连接」的回滚，但没有任何测试在「已有一条合法连接 + 本轮新建一条后失败」的场景下断言旧连接保留、新连接被撤销；未知 endpoint 拒绝清理、多 Profile 并发不串网同样无 case。现有收敛测试均为单 Profile 顺序重复调用，只能算顺序幂等的弱证据，不能支撑 AC-007 被打勾的并发与回滚条款。AC-012 的故障矩阵亦把「并发事件」列为应以生产入口覆盖的场景，交付测试中缺席。
- 建议：adapter 层补回滚 case（预置合法连接 → attach 中途失败 → 断言旧连接仍在、新连接已 disconnect、异常上抛）；补未知 endpoint 清理拒绝 case；收敛层补双 Profile 并发/交错事件 case，断言两 Profile 的附着与观测互不串扰。

### t026_test_f004 - 两个填充型测试不触达任何生产逻辑

- 严重度：minor
- 锚点：行为缺陷——测试计数虚增，无 AC 受影响（这两条未被用作任何 AC 的唯一证据）
- 位置：`tests/unit/test_t026_supervisor_convergence.py:324`（`test_agent_key_fixture_is_real`）、`tests/e2e/test_supervisor_reconciliation_e2e.py:161`（`test_httpx_import_keeps_module_collectable`）
- 问题：前者只写一个临时文件再断言 `st_size > 0`，验证的是 tmp_path 与文件系统而非注释声称的「收敛密钥路径不依赖 credentials 对象」；后者断言 `httpx.__name__ == "httpx"`，为恒真式断言。二者通过与否与生产代码无关，留在套件里会稀释「全绿」的含金量。
- 建议：删除或改写为真实断言（如前者改为断言 start 路径确实把 agent secret 写到 validator 指定的 secret 路径，后者直接删除、收集性由 pytest collect 本身保证）。

### t026_test_f005 - AC-010「API 重启后为 unknown」与 AC-004「替换期间恢复中」无直接断言

- 严重度：minor
- 锚点：AC-010、AC-004 的子条款
- 位置：`tests/integration/test_t026_transport_api.py`（全文）、`tests/unit/test_t026_supervisor_convergence.py:175`（`test_stream_policy_drift_replaces_stream_only`）
- 问题：AC-010 的「API 重启后为 unknown 直至下次上报」仅由「观测只存内存」结构性推出，无测试构造全新 coordinator/API 实例断言 transport 为 null/unknown；AC-004 的「替换期间 Viewer 呈现恢复中」无测试在 Stream-only 替换过程中断言 transport_state 为 recovering（收敛测试只断言替换后的终态）。两项均为子条款缺口，核心行为已有覆盖，故 minor。
- 建议：补一条 fresh-coordinator transport 为空的断言，以及替换路径中 `_replace_stream_only` 执行期间观测为 recovering 的断言。

## 结论

- 改测方向复核：无「迁就实现」的改测。`tests/integration/test_api_search_defaults_routes.py` 的夹具变更（绑定 `inst_1` 实例）符合 spec 门禁前置要求，原断言逐字不变，且新增实例不一致负例 `test_runtime_view_hides_status_from_another_instance` 反证围栏未被绕过；`tests/unit/test_api_models_and_sse.py` 与 `tests/unit/test_supervisor_schema.py` 的改动均为纯新增字段/条目，无断言弱化、无删除、无反转。
- 危险模式扫描：未发现 `.skip`/`.only`（e2e 文件的模块级 `skipif` 是 AC-012 规定的真实 Docker 环境门控，本机复跑为 3 skipped，属合法交付形态）、无 `@ts-ignore`/`type: ignore`、无注释掉断言、无 timeout/容差放大、无 `.value =` 冒充交互。收敛测试虽记录替身 call 列表，但同时断言 transport 观测状态与 session 容器 ID，不属于 AC-012 禁止的「只检查替身调用次数」。恒真式断言两处见 f004（minor，因未充当 AC 证据）。
- 本轮新发现：5 条（important 3、minor 2）
- 未进表的提示：复跑全量 unit 时以任务指定 TMPDIR（`$PWD/.scratch/t026/tmp`）出现 2 条 `test_runtime_agent_faults.py` X11 用例失败，根因为 `OSError: AF_UNIX path too long`（深层 TMPDIR 使 unix socket 路径超限）；换 `TMPDIR=/tmp` 后该文件 29 条全过，与基线「778 passed/1 skipped」对齐，属本机环境伪影、非 t026 回归，不出 finding。
- 总体判断：AC-002 事件触发、AC-009 逐 Profile readiness、AC-007 回滚/并发三处核心条款被打勾但无有效测试支撑，存在未解决 important，FAIL。
- 系统性 follow-up：无（三条 important 均为本 task 契约内补测，不另立 task；真实 Docker 执行已由 t032 AC-009 承接）

### AC 复验方式

- AC-001：re_verified——复跑 `tests/integration/test_api_search_defaults_routes.py`（含新增负例）全过；diff 核对原断言不变、仅夹具补绑实例；全量 unit 复跑与基线计数对齐（见未进表提示）。
- AC-002：trust_prior——收敛器层（Gateway 替换只重附着、断网恢复）经 `test_t026_supervisor_convergence.py` 复跑 re_verified，但事件触发条款无测试（f001），该条款依赖实施侧 blueprint 自述，未能独立复验。
- AC-003：re_verified——复跑 `test_t026_address_pool.py`（6 条）与 `test_t026_media_network_adapter.py`（5 条，含端点被占拒绝、池耗尽显式失败、标签漂移不 conforming）全过，断言落在 IPAM 配置与网络状态而非调用次数。
- AC-004：re_verified——复跑收敛测试中规格不符重建网络+Stream、Stream-only 替换两条，断言 Browser 容器 ID 不变；「替换期间恢复中」子条款见 f005。
- AC-005：re_verified——复跑 `test_t026_network_policy_verify.py`（渲染-解析全等、丢规则判漂移、Stream/Browser 规格不可互换）与 fail-closed 单次应用测试全过；monkeypatch 仅替换 `current_filter_rules` 这一系统边界（实时 netns 读取），未 mock 被测校验逻辑。
- AC-006：re_verified——复跑 `test_offline_recovery_only_reattaches`（API 404 时只重附着、session 保留）与 readiness 未就绪测试全过；存量 `test_supervisor_recovery.py`、`test_supervisor_infrastructure_config.py` 复跑全过。
- AC-007：trust_prior——回滚、未知 endpoint、多 Profile 并发条款无测试（f003），仅顺序重复调用提供幂等弱证据，未能独立复验。
- AC-008：re_verified——复跑 `tests/integration/test_t026_gateway_registration.py`（4 条，真实 Gateway harness：成功注册带 build 标识、版本拒绝、身份拒绝结构化、Gateway 不可达区分 None）全过；收敛层「不可修复拒绝不替换 Stream / 未注册有界替换预算」复跑全过。
- AC-009：trust_prior——端点鉴权、schema 一致性（`test_supervisor_schema.py`）与 API 不可用不报 ready 经复跑 re_verified；逐 Profile 校验与宿主 CLI 无测试（f002），未能独立复验。
- AC-010：re_verified——复跑 `tests/integration/test_t026_transport_api.py`（响应携带围栏内 transport、异实例为 null、coordinator 围栏）与前端 `sse.transport.test.ts`（合法/非法 transport 事件解析）全过；「重启后 unknown」子条款见 f005。
- AC-011：re_verified——复跑前端 `useBrowserSession.transportRecovery.test.tsx` 4 条全过（recovering 呈 reconnecting、failed 立即失败、窗口耗尽失败、ready 后重连），经真实 MessageEvent 派发驱动 hook，非 mock 内部函数。
- AC-012：trust_prior——生产入口覆盖在 unit/integration 层经上述复跑 re_verified，但网络事件与并发事件两项缺席（f001/f003）；真实 Docker 用例本机复跑为 3 skipped（无 daemon)，collect 与运行说明齐备，实跑义务按 spec 归 t032 AC-009，未能独立复验。

coverage = re_verified 8 / 总 AC 数 12
建议合并前人工抽查 trust_prior 项

verdict: FAIL

## Round 2 (2026-11-04T10:30:21+08:00)

- round：2
- reviewed_at：2026-11-04T10:30:21+08:00

reviewed_scope: 86308973738556df

### 前轮 finding 复核

- t026_test_f001（important）——已消除。新增 `tests/unit/test_t026_runner_network_events.py`（4 条）直接 import 生产 helper：`media_network_event_matches`（受管媒体网络名命中、browser/无关网络不命中、无 Attributes 时 id 回退、畸形事件 `Actor=None`/非 dict/None 均不命中）与 `_pump_network_events`（仅媒体事件触发 wake 回调、无关事件不触发、stop 置位后停泵）。这两个 helper 正是 `src/backend/cbrowser/supervisor/runner.py` 中 `watch_docker_network_events` 实际调用的匹配/泵逻辑（非测试内复制实现），触发路径不再是未验代码。本人复跑该文件全过（与下述 t026 unit 子集共 52 passed）。
- t026_test_f002（important）——已消除。`tests/unit/test_t026_supervisor_convergence.py` 新增 readiness 三态：全绿 ready（断言 `result.ready is True`、逐 Profile `checks["registration"]/["policy"] is True`，ready 由全部 checks 计算，非罐头）、Gateway 不可达时 `checks["registration"] is None` + `registration_unverifiable` 诊断且 not ready、单 Profile runtime 请求失败被隔离（好 Profile 仍 ready、坏 Profile `runtime_unavailable` 诊断）。`_profile_readiness` 的五项校验与 diagnostics 组装被真实执行（API 侧走 MockTransport 按路径分发，非早退分支）。新增 `tests/unit/test_t026_control_client.py`（4 条）驱动生产 `control_client.main`：readiness ready→0、not ready→1、不可达→1 并输出 `control_unreachable:` JSON；reconcile 成功→0、不可达→2。复跑全过。
- t026_test_f003（important）——已消除。adapter 层 `test_attach_rolls_back_only_this_rounds_connections`（`tests/unit/test_t026_media_network_adapter.py`）：预置合法 Browser 端点，令 Gateway 本轮 connect 落到错误地址触发校验失败，断言 Gateway 本轮连接被 disconnect、Browser 既有端点保留、异常上抛——断言落在网络端点状态而非调用次数。未知 endpoint：`test_cleanup_network_refuses_unknown_endpoint` 与 `test_rebuild_media_network_refuses_unknown_endpoint` 均断言抛错且网络/端点原样保留。并发：`test_concurrent_profiles_converge_without_cross_talk` 以 `asyncio.gather` 同轮跑两个 Profile（一重附、一 Stream-only 替换），断言 attach 各携带自身 Profile、仅 prof_b 的 Stream 被替换、prof_a 观测 ready 不串扰。复跑全过。
- t026_test_f004（minor）——已消除。两条填充测试已真删：全仓 grep `test_agent_key_fixture_is_real` / `test_httpx_import_keeps_module_collectable` 零命中，e2e 文件的无用 httpx import 已移除；e2e 现仅剩 2 条真实 Docker 门控用例（本机复跑 2 skipped，与 AC-012 交付形态一致）。
- t026_test_f005（minor）——已消除。AC-010：`test_fresh_coordinator_reports_transport_unknown`（`tests/integration/test_t026_transport_api.py`）构造全新 `RuntimeCoordinator`（空内存缓存），断言 `get_transport` 与 `fenced_transport` 均为 None——直接断言「重启后 unknown」。AC-004：`test_replacement_observes_recovering_mid_flight` 在 Stream 启动点采样观测，断言替换进行中 `transport_state == "recovering"`。复跑全过。

### 本轮新发现

### t026_test_f006 - readiness 的 Stream 缺失守卫分支（code f006 修复）无回归测试

- 严重度：minor
- 锚点：AC-009 子分支——Stream 容器缺失时 readiness 应 policy=None + `policy_unverifiable` 诊断、不报 ready、不抛 500
- 位置：`src/backend/cbrowser/supervisor/core.py:783`（else 分支）；测试侧 `tests/unit/test_t026_supervisor_convergence.py:64`（`_FakeAdapter.get_profile_containers` 恒返双容器）
- 问题：Round 1 code f006 的修复是「双容器非 None 才进政策校验，否则 policy=None+诊断」，但新增三条 readiness 测试的替身 adapter 恒返回 Browser/Stream 双容器，该守卫 else 分支从未被执行；若守卫回退，readiness 测试仍全绿而 Stream 缺失时端点重新 500。AC-009 主体已有真实覆盖，故 minor。
- 建议：补一条 readiness case：adapter 对 Stream 返回 None，断言不抛异常、entry not ready、`checks["stream"] is False`、`checks["policy"] is None` 且 diagnostics 含 `policy_unverifiable`。

### t026_test_f007 - 收敛 inspect/attach 失败的 degraded 观测（code f007 修复）无测试

- 严重度：minor
- 锚点：AC-002/AC-003 的失败可观测子条款——inspect 失败落 `media_inspect_failed`、attach 失败落 `media_attach_failed` 的 failed 观测
- 位置：`src/backend/cbrowser/supervisor/core.py:311`、`:358`；tests 全仓 grep `media_inspect_failed|media_attach_failed` 零命中
- 问题：Round 1 code f007 的两处 degraded 观测落点没有任何测试触达：收敛替身 adapter 的 `inspect_media_network`/`attach_profile_infrastructure` 从不抛错，这两条失败路径若回退为静默 warning，套件无感知。属可观测性子条款缺口，核心收敛行为已覆盖，故 minor。
- 建议：各补一条 case：令 inspect 抛 `DockerSandboxError` 断言观测 `transport_state == "failed"` 且 `last_error == "media_inspect_failed"`；令 attach 抛错断言 `media_attach_failed`。

### t026_test_f008 - control_client 测试未断言请求路径、_client 的 token/URL 构造未验

- 严重度：minor
- 锚点：AC-009——宿主 CLI 经内部认证调用 Supervisor 控制面
- 位置：`tests/unit/test_t026_control_client.py:18`（`_install_transport` 整体替换 `_client`，handler 不查 `request.url.path`）；生产 `src/backend/cbrowser/supervisor/control_client.py:36`（`_client` 读 token 文件并组 Authorization 头）
- 问题：4 条 CLI 测试断言了退出码与 JSON 透传（真实行为），但 handler 对任意路径都返回同一响应——`main` 若把 readiness/reconcile 路径写反或写错，测试仍全绿；`_client` 的 env 解析、token 文件读取与 Authorization 头组装也因被整体替换而未验。退出码契约已覆盖，故 minor。
- 建议：handler 内断言路径分别为 `/supervisor/v1/readiness` 与 `/supervisor/v1/reconcile`；另补一条以临时 token 文件 + env 驱动真实 `_client()` 的冒烟，断言 base_url 与 Authorization 头。

## 结论

- 前轮 finding 复核：f001–f005 全部已消除（逐条证据见上方「前轮 finding 复核」，均以 diff/代码/本人复跑为准，未采信处置表自述）。
- 改测方向复核：无「迁就实现」的改测。本轮测试改动均为纯新增 case 与删除 2 条填充测试；`test_missing_stream_with_session_routes_to_replacement` 以记录替身替换 `_replace_stream_only` 只验 `_reconcile_profile` 的路由决策，替换行为本身另有 `_converge_session` 层真实覆盖，不构成假绿。
- 危险模式扫描（本轮新增/变更测试）：未发现恒真断言、删/反转 expect、注释断言、`.skip`/`.only`（e2e 模块级 skipif 仍为 AC-012 真实 Docker 门控）、`type: ignore`、timeout/容差放大、条件跳过弱化断言。control_client 测试替换 `_client` 工厂属 HTTP 系统边界替身，`main` 的参数解析/退出码/输出逻辑被真实执行（其路径断言缺口见 f008，minor）。
- 本轮新发现：3 条（均为 minor：f006、f007、f008）
- 未进表的提示：`_pump_network_events` 的事件流中途抛异常路径仍无直接 case（异常隔离在 `watch_docker_network_events` 的 try/except 闭包内，30 秒兜底扫描不受影响），属可选补强；`rebuild_media_network` 的「删网失败回滚重连旧端点」与「网络不存在时新建」两分支无 case，AC-004 主路径（重建保 Browser、未知端点拒绝）已覆盖，均不阻断。
- 复跑证据：t026 unit 子集（runner events/control client/media adapter/convergence/address pool/policy verify/control endpoints）52 passed；integration（transport api/gateway registration/search-defaults）11 passed；e2e 2 skipped（无 Docker daemon，归 t032）；全量 unit 801 passed / 1 skipped（`TMPDIR=/tmp`，与实施侧自述计数一致）。
- 总体判断：Round 1 五条 finding 全部真闭合；新增生产代码（`DockerAdapter.get_profile_containers`、`rebuild_media_network`、core 五处修复）均有触达生产逻辑的测试覆盖，残余 3 条 minor 为分支级补强，不阻断，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：re_verified——复跑 `test_api_search_defaults_routes.py`（含异实例负例）全过，全量 unit 801 passed 与自述一致。
- AC-002：re_verified——网络事件匹配/泵 helper 测试（f001 复核）+ 收敛层 Gateway 替换/断网用例复跑全过；事件加速路径现已可独立复验（原 trust_prior 消除）。
- AC-003：re_verified——address pool 与 media adapter 测试复跑全过（显式 subnet/ip_range、端点占用拒绝、池耗尽显式失败）。
- AC-004：re_verified——规格不符重建、Stream-only 替换、替换中途 recovering 采样（f005 复核）与新增 `rebuild_media_network` 两条 adapter 测试复跑全过。
- AC-005：re_verified——policy verify 与 fail-closed 两轮重试测试（code f004 回归）复跑全过。
- AC-006：re_verified——API 离线只重附着 + 无 session 凭扫描实例恢复（code f005 回归）复跑全过。
- AC-007：re_verified——回滚、未知 endpoint（cleanup 与 rebuild 双入口）、双 Profile 并发不串网三组 case 复跑全过（原 trust_prior 消除）。
- AC-008：re_verified——Gateway 真实 harness 注册/拒绝用例 + Gateway 缺失中止替换（code f002 回归，零拆动断言）复跑全过。
- AC-009：re_verified——readiness 逐 Profile 三态、control_client 退出码契约、control endpoints 鉴权与 schema 一致性复跑全过（原 trust_prior 消除；守卫分支与路径断言残余见 f006/f008，minor）。
- AC-010：re_verified——transport REST 围栏、coordinator 围栏、新实例 unknown（f005 复核）复跑全过。
- AC-011：re_verified——Round 1 已复跑前端四态测试全过，本轮该文件无变更，结论沿用本轮 diff 核对。
- AC-012：trust_prior——生产入口覆盖在 unit/integration 层经本轮复跑 re_verified；真实 Docker e2e 本机 2 skipped（无 daemon），实跑义务按 spec 归 t032 AC-009，依赖其执行记录。

coverage = re_verified 11 / 总 AC 数 12

verdict: PASS

## Round 3 (2026-11-04T10:40:55+08:00)

- round：3
- reviewed_at：2026-11-04T10:40:55+08:00

reviewed_scope: f8944c6b9d236902

### 前轮 finding 复核

#### 本路 Round 2 新立（t026_test_f006–f008）

- t026_test_f006（minor）——已消除。新增 `test_readiness_missing_stream_policy_unverifiable`（`tests/unit/test_t026_supervisor_convergence.py:811`）：替身 adapter 的 `get_profile_containers` 返回 Stream=None，真实驱动生产 `SupervisorCore.readiness()` → `_profile_readiness` 守卫分支，断言不抛异常、`result.ready is False`、`entry.checks["policy"] is None`、`"policy_unverifiable" in entry.diagnostics`——正是 Round 2 建议的守卫语义，本人复跑通过。仅 `checks["stream"] is False` 未单独断言（生产 `core.py:753` 附近 bool 表达式对 stream=None 必为 False），属断言清单的小缺口，记入未进表提示，不另立 finding。
- t026_test_f007（minor）——已消除。新增两条：`test_converge_inspect_failure_records_degraded_observation`（`:841`，令 `inspect_media_network` 抛 `DockerSandboxError`，断言观测 `transport_state == "failed"` 且 `last_error == "media_inspect_failed"`）与 `test_converge_attach_failure_records_degraded_observation`（`:861`，预置 Gateway 附着漂移迫使 attach 后令其抛错，断言 `media_attach_failed`）。两条均经真实 `_converge_session` 触达生产落点（`core.py` inspect/attach 的 degraded 观测分支），断言落在用户可见的 transport 观测而非调用次数，复跑通过。
- t026_test_f008（minor）——已消除。`test_handlers_hit_the_contract_paths`（`tests/unit/test_t026_control_client.py:75`）：handler 按路径分发并记录，断言 `seen == ["GET /supervisor/v1/readiness", "POST /supervisor/v1/reconcile"]`——路径写反/写错即红，不再是任意路径同响应。`test_client_construction_uses_env_url_and_token_file`（`:97`）：不替换 `_client`，以 env URL + 临时 token 文件驱动真实 `control_client._client()`，断言 `base_url` 与 `Authorization == Bearer <token>`（并显式清理代理 env 防 httpx trust-env 干扰）。复跑通过。

#### code 路 Round 2 六条（f003 残余 / f009–f013）的新增回归测试复核

- t026_code_f003 残余（important）——回归测试成立。`test_exited_stream_repaired_in_place_not_pair_error`（`test_t026_supervisor_convergence.py:699`）真实驱动生产 `_reconcile_profile`：roles 中 Browser running、Stream `exited`、session 同实例，断言 Stream-only 替换被路由（`replaced == [PROFILE]`）且整对终局错误未上报（`terminal == []`）。`_replace_stream_only`/`report_terminal_observation` 以记录替身替换属路由决策测试，与 Round 2 已接受的 missing-stream 路由测试同构；替换行为本身另由真实 `_replace_stream_only` 用例覆盖（如 `test_gateway_missing_aborts_replacement_before_teardown` 直调生产实现断言零拆动）。生产分支核对：`core.py:987` 附近 Browser running 且仅 Stream 非 running 时在预算内走替换，与测试场景一致。复跑通过。
- t026_code_f009（important）——回归测试成立（隔离粒度的小缺口另立本轮 f011）。`test_readiness_docker_failure_isolated_per_profile`（`:780`）：令 `inspect_media_network` 抛 `DockerSandboxError`，真实驱动 `readiness()`，断言不 RAISE、返回 not-ready 条目且 `diagnostics[0].startswith("readiness_check_failed")`（后缀为异常类型名，startswith 非弱化）。生产兜底在 `core.py:710` 附近 per-profile try 内，与断言对应。复跑通过。
- t026_code_f010（important）——回归测试成立（粒度的小缺口另立本轮 f010）。`test_install_fail_closed_raises_when_restore_fails` 与 `test_install_fail_closed_succeeds_when_restores_pass`（`tests/unit/test_t026_network_policy_verify.py:74`/`:88`）：在 `subprocess.run` 这一系统边界打桩，直接调用生产 `install_fail_closed()`，restore 非 0 时断言抛 `NetworkPolicyError`、全 0 时断言不抛。生产实现核对：`network_policy.py:381` 严格版逐 family 检查 returncode 并抛错、`main(["fail-closed"])` 失败 exit 3（`:425` 附近），与 f010 的假成功链对应。复跑通过。
- t026_code_f011（important）——回归测试成立。`test_missing_stream_budget_exhausted_never_replaces`（`:744`）：把 `_stream_replace_attempts` 预置为窗口内 3 次（与生产 `_STREAM_REPLACE_MAX` 及 `_stream_replacement_allowed` 的窗口过滤语义一致，`core.py:254`），真实驱动缺失-Stream 路由，断言替换零调用且观测落 `transport_state == "failed"` / `last_error == "stream_missing_budget_exhausted"`——断言同时落在路由行为与用户可见观测上。生产缺失路由核对：`core.py:942` 先查预算、耗尽落该错误码后 return。复跑通过。
- t026_code_f012（minor）——生产修复已核对、无新增回归测试，另立本轮 f009。`runner.py:293` 登记网络流后若 `stop_event` 已置位即 `_close_stream_sync()` 并返回，`_close_stream_sync`（`:216`）确含 network 流；但该 watcher 是 `serve_supervisor` 内嵌套闭包，测试侧零引用（见 f009）。
- t026_code_f013（minor）——回归测试成立。`test_rebuild_refuses_managed_container_with_unknown_role`（`tests/unit/test_t026_media_network_adapter.py:393`）：对生产 `DockerAdapter.rebuild_media_network` 放置 prefix+managed-by 合规但 role=`rogue` 的端点，断言抛 `DockerSandboxError` 且旧网络未被 remove。生产核对：`docker_adapter.py:876` 附近端点核验已加 role ∈ {browser, stream, gateway} 白名单，与 cleanup 口径一致。复跑通过。

### 本轮新发现

### t026_test_f009 - code f012 的 watcher 停机竞态修复无任何回归测试

- 严重度：minor
- 锚点：行为缺陷——Round 2 code f012 修复（登记后 stop 复查）无测试锚点，修复回退套件无感知
- 位置：生产 `src/backend/cbrowser/supervisor/runner.py:295`（登记后 stop 检查与 `_close_stream_sync`）；测试侧 `tests/unit/test_t026_runner_network_events.py` 全文仅覆盖 `media_network_event_matches`/`_pump_network_events`，全仓 grep `watch_docker_network_events`/`serve_supervisor` 在 tests 中零命中
- 问题：f012 的竞态窗口（订阅返回后、登记时 stop 已置位）修复逻辑位于 `serve_supervisor` 的嵌套闭包内，没有任何测试能触达；若该复查被误删，网络事件流再次无人关闭、停机挂住的风险回归而套件全绿。嵌套闭包本身难测属实，故 minor；但这正是 Round 2 本路对 f006/f007 同型缺口立 minor 的口径，不因难测豁免记录。
- 建议：把网络 watcher 的「登记 + stop 复查 + 关闭」抽成与 `_pump_network_events` 同级的可测 helper 后补一条 stop 预置位用例；或在 note 中明确该分支以代码复核代替测试并归 t032 停机实跑观察。

### t026_test_f010 - f010 严格化测试用全败/全胜桩，测不出单 family（ipv6）restore 失败被吞

- 严重度：minor
- 锚点：AC-005 子条款覆盖粒度——fail-closed 须两 family 均严格，现有桩无法区分「只查 ipv4」与「两 family 都查」
- 位置：`tests/unit/test_t026_network_policy_verify.py:74`（`_failing_run` 对所有调用恒返 returncode=1）、`:88`（`_ok_run` 恒返 0）
- 问题：失败桩让每一次 restore 都失败：一个只检查 ipv4、忽略 ip6tables-restore 结果的退化实现同样会抛错通过；一个只检查 ipv6 的实现也同样通过。CLI 层 `main(["fail-closed"])` 的 exit 3 传播亦未断言（code f010 原建议含此条）。生产实现经本人逐行核对为逐 family 严格检查（`network_policy.py:388` 循环两 family、任一非 0 即抛），行为本身成立，故仅为测试判别力缺口，minor。
- 建议：补一条按工具名分发的桩：iptables-restore 返 0、ip6tables-restore 返 1 时仍须抛 `NetworkPolicyError`；并补 `main(["fail-closed"])` 在 restore 失败时 `SystemExit` 码为 3 的断言。

### t026_test_f011 - f009 readiness 隔离测试名实不符：只有单个 Profile，未验健康 Profile 在同轮仍被评估

- 严重度：minor
- 锚点：AC-009 子条款覆盖粒度——「逐 Profile 隔离」应证明一个 Profile 的 Docker 异常不妨碍其余 Profile 的真实评估
- 位置：`tests/unit/test_t026_supervisor_convergence.py:780`（`test_readiness_docker_failure_isolated_per_profile`，API 列表仅含 PROFILE 一个条目）
- 问题：该测试证明了 readiness 不 RAISE 且失败条目带 `readiness_check_failed` 诊断，但场景中不存在第二个健康 Profile，无法排除「首个异常后整体短路、后续 Profile 不再评估」类退化。注：runtime 查询失败层面的双 Profile 隔离已有 `test_readiness_one_profile_runtime_failure_isolated` 覆盖、生产 `readiness()` 的 per-profile try 结构经本人核对（`core.py:710` 附近循环内逐条收敛），行为成立，故 minor。
- 建议：把该用例扩为双 Profile：坏 Profile 的 inspect 抛错、好 Profile 全绿，断言结果同时含坏条目的 `readiness_check_failed` 诊断与好条目的 `ready is True`。

## 结论

- 前轮 finding 复核：本路 f006–f008 全部真闭合；code 路 f003 残余、f009、f010、f011、f013 的新增回归测试均真实触达生产逻辑且断言有意义（逐条证据见上方复核），f012 修复代码已核对但无回归测试（本轮 f009，minor）。
- 改测方向复核：无「迁就实现」的改测。本轮测试改动均为纯新增 case（convergence +6、network_policy_verify +2、media_adapter +1、control_client +2，与本人逐文件清点一致），无既有断言修改/弱化/删除。
- 危险模式扫描（本轮新增测试）：未发现恒真断言、删/反转 expect、注释断言、弱化断言、`.skip`/`.only`、`type: ignore`、timeout/容差放大、条件跳过弱化断言。新增测试中的替身均在系统边界或路由记录层：`subprocess.run`（进程边界）、adapter 方法抛错（Docker 边界）、`_replace_stream_only` 记录替身（路由决策，替换行为另有生产直调覆盖），不构成 mock 被测逻辑本身。`diagnostics[0].startswith("readiness_check_failed")` 是对「固定前缀 + 异常类型后缀」契约的精确断言，非弱化。
- 本轮新发现：3 条（均为 minor：f009、f010、f011）
- 未进表的提示：f006 测试未单独断言 `checks["stream"] is False`（生产表达式对 stream=None 必为 False，见复核）；exited 路由在预算耗尽时回落 `container_exit` 的分支无 case（生产 `core.py:987` 附近 if/else 结构已核对）；二者均为可选补强。实施侧自述计数经本人复跑核对一致（见下）。
- 复跑证据：t026 unit 子集（convergence/network_policy_verify/media_adapter/control_client/runner_network_events/control_endpoints/address_pool）63 passed；integration（gateway_registration/transport_api/search_defaults）11 passed；全量 unit 812 passed / 1 skipped（`TMPDIR=/tmp`，与 note 自述的 Round 2 后计数一致，基线 801 + 本轮 11 条新测恰合）。
- 总体判断：Round 2 全部 important（code f003 残余/f009/f010/f011）与本路 minor（f006–f008）的修复均有真实回归测试支撑且复跑全绿；残余 3 条 minor 为测试判别力/隔离粒度/难测闭包的补强项，不阻断，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：re_verified——复跑 `test_api_search_defaults_routes.py`（在本轮 integration 批 11 passed 内）全过。
- AC-002：re_verified——runner 事件测试与收敛层用例复跑全过；f012 停机竞态分支无测试（f009，minor），不影响事件触发与收敛主体。
- AC-003：re_verified——address pool 与 media adapter 测试复跑全过；degraded 观测两码经 f007 复核新增断言成立。
- AC-004：re_verified——规格重建、Stream-only 替换、rebuild 未知 role 拒绝（f013 复核）复跑全过。
- AC-005：re_verified——policy verify 与 fail-closed 严格化测试复跑全过，生产逐 family 严格检查逐行核对；单 family 判别力缺口见 f010（minor）。
- AC-006：re_verified——离线只重附着与无 session 恢复用例复跑全过，本轮无变更。
- AC-007：re_verified——回滚、未知 endpoint（cleanup/rebuild 双入口）、双 Profile 并发用例复跑全过。
- AC-008：re_verified——exited Stream 路由（f003 残余）、缺失路由预算门禁（f011）、Gateway 注册集成与不可修复拒绝用例复跑全过。
- AC-009：re_verified——readiness 三态 + Docker 失败隔离（f009 复核）+ Stream 缺失守卫（f006 复核）+ control_client 路径/`_client` 构造（f008 复核）复跑全过；双 Profile Docker 隔离粒度见 f011（minor）。
- AC-010：re_verified——transport REST/coordinator 围栏与新实例 unknown 用例复跑全过，本轮无变更。
- AC-011：re_verified——Round 2 已复跑前端四态测试全过，本轮该文件无变更，结论沿用 diff 核对。
- AC-012：trust_prior——生产入口覆盖在 unit/integration 层经本轮复跑 re_verified；真实 Docker e2e 本机无 daemon 未实跑，义务按 spec 归 t032 AC-009，依赖其执行记录。

coverage = re_verified 11 / 总 AC 数 12

verdict: PASS

## Round 4 (2026-11-04T10:49:03+08:00)

- round：4
- reviewed_at：2026-11-04T10:49:03+08:00

reviewed_scope: 03f1d9ec3f9a7817

### 前轮 finding 复核

#### 本路 Round 3 新立（t026_test_f009–f011）

- t026_test_f009（minor）——遗留登记属实合规，本轮确认接受遗留。`docs/pending/todo/p035_t026_network_watcher_stop_race_regression_test.md` 实体存在（`git status` 为已登记的新增交付文件），内容与 note.md Round 3 处置表一致：来源标注 t026_test_f009 / Round 2 code f012 的测试面；理由与处置表同义——watcher 是 `serve_supervisor` 嵌套闭包、确定性复现需先抽可测单元，并给出两条补测路径（抽模块级函数测「stop 先于登记 ⇒ 流被关闭」/ 假 Docker client 驱动 watcher 线程断言流关闭）；明确「生产行为本身无缺陷，本条只追测试债」。生产修复本体已经 Round 2/3 两轮 code 静态核对（`runner.py` 登记后 stop 复查 + `_close_stream_sync` 含 network 流），本轮不重复核对。遗留指向 pNNN、理由具体、非 critical/important，符合处置规范。
- t026_test_f010（minor）——已消除。新增两条均真实触达生产逻辑、断言有意义，本人逐条复跑通过：`test_install_fail_closed_raises_on_single_family_failure`（`tests/unit/test_t026_network_policy_verify.py:98`）在 `subprocess.run` 系统边界按工具名分发——`ip6tables-restore` 返 1、`iptables-restore` 返 0，断言生产 `install_fail_closed()` 仍抛 `NetworkPolicyError`；生产实现逐行核对：`network_policy.py:381` 起按 `("ipv4", "ipv6")` 循环、工具名取 `_FAMILY_TOOLS`（`iptables-restore`/`ip6tables-restore`，与桩的 `args[0]` 判别一致）、任一 family returncode 非 0 即抛——「只查 ipv4」的退化实现在此桩下不抛、必红，判别力成立，正是 Round 3 建议的补法。`test_fail_closed_cli_exits_3_on_restore_failure`（`:113`）驱动生产 `main(["fail-closed"])`，断言 `SystemExit` 码恰为 3（生产 `network_policy.py:436` 附近 fail-closed 失败 `sys.exit(3)`），非弱化断言。
- t026_test_f011（minor）——主体已消除，残余顺序判别力另立本轮 f012。新增 `test_readiness_failure_in_one_profile_still_evaluates_others`（`tests/unit/test_t026_supervisor_convergence.py:946`）：双 Profile 场景，`prof_bad` 的 `inspect_media_network` 抛 `DockerSandboxError`、PROFILE 全绿，真实驱动生产 `readiness()`，断言 `result.ready is False`、好条目 `ready is True`、坏条目 `ready is False` 且 `diagnostics[0].startswith("readiness_check_failed")`——Round 3 建议的断言集完整落地，f009 原始回归（单 Profile Docker 异常使 readiness 整体 RAISE、端点 500）在任何顺序下必红，复跑通过。仅条目顺序使「失败后继续评估」未被证明，见 f012。

#### code 路 Round 3 新立 f014 的三段回归测试复核

- t026_code_f014（important）——回归测试成立。`test_latched_container_exit_error_releases_on_authoritative_running`（`tests/unit/test_t026_supervisor_convergence.py:880`）真实驱动生产 `_reconcile_profile` 全流程（非复制实现），本人逐段对代码核对并复跑通过：
  - 锁存段（生产逻辑实测）：预置 `_stream_replace_attempts` 为窗口内 3 次（与生产 `_STREAM_REPLACE_MAX=3`、窗口 300s 及 `_stream_replacement_allowed` 的真实时间过滤语义一致，`core.py:254`），Stream `exited` 驱动 `_reconcile_profile`——生产同实例分支因预算耗尽不走替换、落锁存分支（`core.py:1015` 附近）置 `session.observed_state = "error"` 并上报 `container_exit`；断言 `observed_state == "error"` 且 `terminal == ["container_exit"]`，锁存由生产代码产生、非测试预置。
  - 释放段（生产逻辑实测）：两容器恢复 running 后再驱动 `_reconcile_profile`——生产 f014 修复点（`core.py:979` 起：权威观测为 `"running"`、同实例且 `observed_state == "error"` 时释放为 `"running"`）被真实执行，断言 `observed_state == "running"`。
  - 收敛恢复段：释放后生产同实例分支的收敛门（`observed_state == "running"` 且双容器 running）放行，断言记录替身收到 `converged == [PROFILE]`——自锁时该调用永不发生，正是 f014 的坏结果面。
  - 替身边界披露：`_reconcile_instance_observation`（观测提供者）、`report_terminal_observation` 与 `_converge_session`（记录替身）被替换，与 Round 2/3 已接受的路由决策测试同构；被测的锁存/释放/门控逻辑本身未被 mock。观测提供者自身的 Agent 健康/身份核验为既有行为、非 f014 修复面，不在本测试证明范围内。「窗口滑动」以 `clear()` 重置预算状态模拟（释放路径本身不依赖预算，未削弱释放断言；预算窗口过滤已由锁存段的真实过滤与既有 f011 测试覆盖）。

### 本轮新发现

### t026_test_f012 - f011 双 Profile 隔离测试中坏 Profile 排末位，「失败后继续评估」仍未被证明

- 严重度：minor
- 锚点：AC-009 子条款覆盖粒度——readiness 逐 Profile 隔离应证明首个 Profile 异常后其余 Profile 仍被评估；本条为 f011 的残余，不影响其主体闭合
- 位置：`tests/unit/test_t026_supervisor_convergence.py:946`（`test_readiness_failure_in_one_profile_still_evaluates_others` 以 `{PROFILE: runtime, "prof_bad": runtime}` 构造）；夹具 `tests/unit/test_t026_supervisor_convergence.py:410`（profiles 列表按 dict 插入序生成）；生产 `src/backend/cbrowser/supervisor/core.py:687`（`readiness` 按 API 列表序逐条评估）
- 问题：测试名与注释声称「一个 Profile 的 Docker 失败不得跳过对其余 Profile 的评估」，但 API 列表序为健康 Profile 在前、`prof_bad` 末位：一个「首个异常后整体短路、返回已收集结果」的退化实现会产出与正确实现完全相同的断言结果（好条目已先行入列），测试无从区分。f009 的原始回归（异常逃逸 RAISE）仍被此测试捕获，故仅为判别力残余，minor。
- 建议：把 dict 顺序改为 `{"prof_bad": runtime, PROFILE: runtime}`（坏在前），其余断言不变，即可同时证明失败后继续评估。

## 结论

- 前轮 finding 复核：f010 已消除；f011 主体已消除（残余顺序判别力见本轮 f012，minor）；f009 遗留登记 p035 经实体核对属实合规（pending 文件存在、内容与处置表一致、理由具体）；code 路 f014 的三段回归测试真实触达生产锁存/释放逻辑、断言有意义（逐段证据见上方复核）。
- 改测方向复核：无「迁就实现」的改测。本轮测试改动为纯新增 4 条（network_policy_verify +2、convergence +2），计数与全量结果恰合（unit 812 → 816），无既有断言修改/弱化/删除。
- 危险模式扫描（本轮新增测试）：未发现恒真断言、删/反转 expect、注释断言、弱化断言、`.skip`/`.only`、`type: ignore`、timeout/容差放大、条件跳过弱化断言。新增替身均在系统边界或记录层：`subprocess.run`（进程边界）、adapter 方法按 Profile 抛错（Docker 边界）、观测/上报/收敛记录替身（f014 路由-状态机测试，锁存与释放逻辑本身为生产代码）。
- 本轮新发现：1 条（minor：f012）
- 未进表的提示：f010 的单 family 桩只覆盖 ipv6 失败方向；ipv4 单独失败由全败桩的第一 family 调用顺带覆盖，「只查 ipv6」的对称退化无判别 case，属可选补强。f014 测试的 `_report_observed` 在 Stage 2 经真实实现走 MockTransport（404 路径）未影响断言，属夹具既有形态。
- 复跑证据：本轮 4 条新测逐条复跑全过；t026 unit 子集（convergence/network_policy_verify/runner_network_events/control_client/media_adapter/control_endpoints/address_pool）67 passed（Round 3 同子集 63 + 本轮 4 恰合）；integration（gateway_registration/transport_api/search_defaults）11 passed；全量 unit 816 passed / 1 skipped（`TMPDIR=/tmp`，与 note 收尾报告自述的最终计数一致）。
- 总体判断：Round 3 遗留三条 minor 中 f010/f011 已补测闭合（f011 残余为顺序判别力 minor）、f009 遗留登记合规，code 路 important f014 有真实三段回归测试支撑；无未解决 critical/important，PASS。
- 系统性 follow-up：f009 的测试债已由 p035 承接，不另立。

### AC 复验方式

- AC-001：re_verified——复跑 `test_api_search_defaults_routes.py`（在本轮 integration 批 11 passed 内）全过。
- AC-002：re_verified——runner 事件测试与收敛层用例在本轮 unit 子集 67 passed 内复跑全过；watcher 停机竞态分支无测试一节已合规遗留 p035（f009 复核），不影响事件触发与收敛主体。
- AC-003：re_verified——address pool 与 media adapter 测试复跑全过，本轮无变更。
- AC-004：re_verified——规格重建、Stream-only 替换、替换中途 recovering 用例复跑全过，本轮无变更。
- AC-005：re_verified——policy verify 与 fail-closed 严格化测试（含本轮新增单 family 判别与 CLI exit 3）复跑全过，生产逐 family 严格检查逐行核对（f010 复核）。
- AC-006：re_verified——离线只重附着与无 session 恢复用例复跑全过，本轮无变更。
- AC-007：re_verified——回滚、未知 endpoint、双 Profile 并发用例复跑全过，本轮无变更。
- AC-008：re_verified——Stream 缺失/退出路由、预算门禁与 f014 锁存-释放三段回归（本轮复核）复跑全过；Gateway 注册集成在本轮 integration 批内全过。
- AC-009：re_verified——readiness 逐 Profile 三态、Docker 失败隔离（含本轮双 Profile 补测）、Stream 缺失守卫、control_client 路径/`_client` 构造复跑全过；双 Profile 顺序判别力残余见 f012（minor）。
- AC-010：re_verified——transport REST/coordinator 围栏与新实例 unknown 用例在本轮 integration 批内复跑全过。
- AC-011：re_verified——前端四态测试已于 Round 2 复跑全过，本轮该文件无变更，结论沿用 diff 核对。
- AC-012：trust_prior——生产入口覆盖在 unit/integration 层经本轮复跑 re_verified；真实 Docker e2e 本机无 daemon 未实跑，义务按 spec 归 t032 AC-009，依赖其执行记录。

coverage = re_verified 11 / 总 AC 数 12

verdict: PASS

## Round 5 (2026-11-04T10:54:44+08:00)

- round：5
- reviewed_at：2026-11-04T10:54:44+08:00

reviewed_scope: 0e454727a9a3ca57

### 前轮 finding 复核

#### 本路 Round 4 新立（t026_test_f012）

- t026_test_f012（minor）——已消除，顺序已改且判别力成立。`test_readiness_failure_in_one_profile_still_evaluates_others`（`tests/unit/test_t026_supervisor_convergence.py:973`）现以 `{"prof_bad": runtime, PROFILE: runtime}` 构造（`:994`-`:996`，注释明示坏 Profile 在 API 列表首位）；夹具 `_core_with_runtime_api`（`:407`-`:413`）的列表响应按该 dict 插入序生成 `[{"id": pid} for pid in runtime_by_profile]`，顺序被真实保留。生产 `readiness()`（`src/backend/cbrowser/supervisor/core.py:688` 起）按 API 列表序逐条评估、逐 Profile 的异常在循环内落 `readiness_check_failed` 条目后继续下一条（`:711`-`:725`）。判别力：若退化为「首个异常即短路/逃逸」，坏 Profile 在首位时健康 Profile 根本不会被评估，`by_id[PROFILE].ready is True` 必然失败（或异常逃逸使整测报错）；Round 4 的旧顺序（健康在前、坏在末）则产出相同结果无法区分。现断言集完整（整体 not ready、健康 ready、坏条目 `readiness_check_failed` 前缀），本人复跑通过。

#### code 路 Round 4 新立 f015（t026_code_f015）的三段回归测试复核

- t026_code_f015（important）——回归测试成立，三段均真走生产终态上报/去重/释放逻辑。生产修复本体先核对：`src/backend/cbrowser/supervisor/core.py:985`-`:999`，权威观测为 `"running"`、同实例且 `session.observed_state == "error"` 时释放锁存并同步 `self._terminal_observations.discard((pid, b_inst, bound_version))`，key 三元组与生产 `report_terminal_observation` 的去重 key 构成（`core.py:2136`，`(profile_id, runtime_instance_id, config_version)`）及首报时落锁存的调用点传参（`core.py:1024`-`:1030` 用同一 `rt` 的 `config_version`，与 `bound_version` 同源）一致，不存在 discard 错 key 的假绿空间。重写后的 `test_latched_container_exit_error_releases_on_authoritative_running`（`tests/unit/test_t026_supervisor_convergence.py:880`）逐段核对：
  - 夹具形态（生产逻辑可达）：测试**不再替换** `report_terminal_observation`（全文件仅 `test_exited_stream_repaired_in_place_not_pair_error` 一处仍替换它，与本测无关）；改为把 `core.api` 换成记录型 MockTransport（`:907`-`:922`）——`runtimes/observed` 的 POST 被逐条记录并返回 200、runtime GET 返回同一 runtime，其余 404。这是 HTTP 系统边界替身：生产 `_report_observed` 的投递判定（200 才算 delivered）与生产 `report_terminal_observation` 的去重检查（`core.py:2137`-`:2138` 命中即 return False 不再 POST）、落集（`:2147`）全部真实执行。被替换的仅剩 `_reconcile_instance_observation`（恒返 `"running"` 的观测提供者）与 `_converge_session`（记录替身）——与前轮已接受的路由/状态机测试同构，被测的锁存、释放、去重、再报逻辑本身未被 mock。
  - Stage 1（锁存 + 首报一次，`:935`-`:947`）：预算以生产真实过滤语义预置耗尽（`[now, now, now]` 对 `_STREAM_REPLACE_MAX=3` / 300s 窗口，`core.py:228`-`:263`），Stream exited 驱动生产 `_reconcile_profile` 落锁存分支；断言 `observed_state == "error"`、记录型 API 中 `container_exit` 恰 1 条、且 `(PROFILE, INSTANCE, 1) in core._terminal_observations`——最后一条直接证明首报是经生产去重路径落的集，旧记录桩（无去重语义、不写该集）在此即会失败，正是 Round 4 指出的旧测盲区被堵上的证据。
  - Stage 2（释放 + key 清除 + 收敛恢复，`:949`-`:960`）：清预算（仅模拟窗口滑动，只影响替换预算、不触终态去重集）、双容器 running 再驱动；生产释放点真实执行，断言 `observed_state == "running"`、`converged == [PROFILE]`、且 `(PROFILE, INSTANCE, 1) not in core._terminal_observations`——discard 缺失在此断言即红。
  - Stage 3（再退出必须再报，`:962`-`:969`）：重设预算耗尽、Stream 再 exited 再驱动；断言回到 `error` 且记录型 API 中 `container_exit` 累计恰 2 条。对 discard 缺失的判别力成立且是功能级（非仅状态级）：若 Stage 2 未 discard，生产 `report_terminal_observation` 在 `core.py:2137` 命中旧 key 直接 return False、不发出 POST，第二条 `container_exit` 永不出现，计数停在 1 必红；Stage 2 的 key-不在集断言与 Stage 3 的 API 计数断言构成双层判别，任一层回退都被捕获。
  - 本人复跑该测试通过；三段的 config_version 恒为 1、instance 恒为同一代次，与 f015 的「同代次恢复后终态再报」语义严格对应。

### 本轮新发现

无（0 条）。新问题编号自 t026_test_f013 起续编，本轮未立任何 finding。

## 结论

- 前轮 finding 复核：本路 f012 已消除（顺序已改、判别力经夹具序与生产循环双向核对成立）；code 路 f015 的三段回归测试真实触达生产 `report_terminal_observation` 去重/落集、生产释放点 discard 与生产 `_reconcile_profile` 锁存/再报全链，断言有意义（逐段证据见上方复核）。本路更早各轮 finding 与 p035 遗留状态本轮无变更，沿用 Round 4 复核结论。
- 改测方向复核：无「迁就实现」的改测。本轮两处测试改动均为判别力增强：f012 仅调整夹具 dict 顺序并加注释、断言逐字不变；f014/f015 回归测试是把记录桩换成生产终态路径 + 记录型 API、断言由「桩调用记录」升级为「API 实际收到几条 container_exit + 去重集状态」，方向是让测试更难通过而非迁就实现。无既有断言删除/弱化/反转，测试总数不变（全量计数与 Round 4 恰合，见复跑证据）。
- 危险模式扫描（最终测试全集）：未发现恒真断言、删/反转 expect、注释断言、弱化断言、`.skip`/`.only`（e2e 模块级 `skipif` 仍为 AC-012 真实 Docker 门控，本轮复跑 2 skipped）、`type: ignore`、timeout/容差放大、条件跳过弱化断言、mock 被测逻辑本身。f015 测试的替身均在合法边界：记录型 MockTransport（HTTP 边界）、`_reconcile_instance_observation` 观测提供者与 `_converge_session` 记录替身（路由层，被测状态机逻辑为生产代码，与前轮接受口径一致）。
- 本轮新发现：0 条
- 未进表的提示：f015 的 Agent-再报-error 变体（经 `_reconcile_instance_observation` 的 `agent_exit` 分支）未在本测中单独分段，但该分支与 Stage 3 的 container_exit 路径调用同一个生产 `report_terminal_observation`、同一个三元组 key（`core.py:1526`-`:1532`），discard 的有效性由 Stage 3 对该共享函数 + 共享 key 的判别完整传递，属可选补强、不立 finding；Stage 3 复用 Stage 1 的 `now` 时间戳预置预算，在测试实际运行时长（亚秒级）内恒在 300s 窗口内，语义成立。
- 复跑证据：两条目标测试（f012 隔离、f014/f015 三段）逐条复跑 2 passed；t026 unit 子集 + 三个 integration 文件（convergence/network_policy_verify/runner_network_events/control_client/media_adapter/control_endpoints/address_pool + gateway_registration/transport_api/search_defaults）78 passed；全量 unit + 同三 integration 文件 827 passed / 1 skipped（`TMPDIR=/tmp`，与 Round 4 的 unit 816 + integration 11 计数恰合，本轮改测为就地重写/改序、无增删）；前端 `useBrowserSession.transportRecovery.test.tsx` + `sse.transport.test.ts` 8 passed；e2e 2 skipped（无 Docker daemon，归 t032）。
- 总体判断：Round 4 遗留的唯一 minor（f012）与 code 路 important（f015）的测试面均已真实闭合，最终测试全集复扫无新 critical/important/minor，PASS。
- 系统性 follow-up：无（f009 测试债仍由 p035 承接）

### AC 复验方式

- AC-001：re_verified——`test_api_search_defaults_routes.py` 在本轮 integration 批（78 passed 的子集与 827 passed 的全量批）内全过。
- AC-002：re_verified——runner 事件、收敛层与 f014/f015 三段回归（恢复后收敛与终态再报）在本轮复跑全过；watcher 停机竞态分支无测试一节已合规遗留 p035，不影响事件触发与收敛主体。
- AC-003：re_verified——address pool 与 media adapter 测试在本轮子集内复跑全过，本轮无变更。
- AC-004：re_verified——规格重建、Stream-only 替换、替换中途 recovering 用例复跑全过，本轮无变更。
- AC-005：re_verified——policy verify 与 fail-closed 严格化（单 family 判别 + CLI exit 3）复跑全过，本轮无变更。
- AC-006：re_verified——离线只重附着与无 session 恢复用例复跑全过，本轮无变更。
- AC-007：re_verified——回滚、未知 endpoint、双 Profile 并发用例复跑全过，本轮无变更。
- AC-008：re_verified——Stream 缺失/退出路由、预算门禁与 f015 三段回归（本轮重点复核：同代次恢复后 container_exit 再报恰 2 条）复跑全过；Gateway 注册集成在本轮 integration 批内全过。
- AC-009：re_verified——readiness 逐 Profile 三态、Docker 失败隔离（含本轮 f012 顺序判别力闭合的双 Profile 补测）、Stream 缺失守卫、control_client 路径/`_client` 构造复跑全过。
- AC-010：re_verified——transport REST/coordinator 围栏与新实例 unknown 用例在本轮 integration 批内复跑全过；前端 sse.transport 本轮复跑 4 passed。
- AC-011：re_verified——前端 `useBrowserSession.transportRecovery.test.tsx` 本轮复跑 4 passed，四态呈现与前轮一致。
- AC-012：trust_prior——生产入口覆盖在 unit/integration 层经本轮复跑 re_verified；真实 Docker e2e 本机 2 skipped（无 daemon），实跑义务按 spec 归 t032 AC-009，依赖其执行记录。

coverage = re_verified 11 / 总 AC 数 12

verdict: PASS

## Evidence Repair (2026-11-04T11:05:59+08:00)

- reviewed_at：2026-11-04T11:05:59+08:00

reviewed_scope: cf4c2cbdec3d4182

## Findings（本轮新发现）

无（0 条）。新问题编号自 t026_test_f014 起续编，本轮未立任何 finding。

## 结论

- 前轮 finding 复核（逐条独立核实方式：以 `git diff c2bd696..3ac6777` 的最终已提交内容为准，逐文件读测试源码、核对生产接口，并以本人复跑结果为准，不采信处置表自述）：
  - f001（important，AC-002 网络事件触发）——已消除。`tests/unit/test_t026_runner_network_events.py` 4 条真实 import 生产 `media_network_event_matches`/`_pump_network_events`（受管命中、无关不命中、畸形事件容忍、stop 停泵），与生产 `src/backend/cbrowser/supervisor/runner.py` 的 watcher 调用点一致；本轮复跑通过。
  - f002（important，AC-009 逐 Profile readiness 与宿主 CLI）——已消除。收敛测试含 readiness 全绿/Gateway 不可达诊断/单 Profile runtime 失败隔离三态，真实驱动生产 `readiness()`/`_profile_readiness`（API 走 MockTransport 按路径分发）；`tests/unit/test_t026_control_client.py` 6 条驱动生产 `control_client.main` 与 `_client()`；本轮复跑通过。
  - f003（important，AC-007 回滚/未知 endpoint/并发）——已消除。`tests/unit/test_t026_media_network_adapter.py` 含 `test_attach_rolls_back_only_this_rounds_connections`（断言旧端点保留、本轮新连接被 disconnect）、cleanup 与 rebuild 双入口未知 endpoint 拒绝、未知 role 拒绝；收敛层双 Profile 并发不串网用例在复跑集内全过。
  - f004（minor，填充测试）——已消除。全仓定向 grep `test_agent_key_fixture_is_real`/`test_httpx_import_keeps_module_collectable` 零命中，两条填充测试确已删除，e2e 仅剩 2 条真实 Docker 门控用例。
  - f005（minor，AC-010 重启 unknown / AC-004 替换中 recovering）——已消除。`test_fresh_coordinator_reports_transport_unknown` 与 `test_replacement_observes_recovering_mid_flight` 均在最终内容中且本轮复跑通过。
  - f006（minor，readiness Stream 缺失守卫）——已消除。`test_readiness_missing_stream_policy_unverifiable`（`tests/unit/test_t026_supervisor_convergence.py:811`）在最终内容中，驱动生产守卫分支并断言 `policy is None` 与 `policy_unverifiable` 诊断；复跑通过。
  - f007（minor，inspect/attach 失败 degraded 观测）——已消除。`test_converge_inspect_failure_records_degraded_observation` 与 `test_converge_attach_failure_records_degraded_observation`（同文件 `:841`/`:861`）分别断言 `media_inspect_failed`/`media_attach_failed` 观测；复跑通过。
  - f008（minor，control_client 路径与 `_client` 构造）——已消除。`test_handlers_hit_the_contract_paths` 断言 GET readiness / POST reconcile 的确切路径序列，`test_client_construction_uses_env_url_and_token_file` 以 env + 临时 token 文件驱动真实 `_client()` 断言 base_url 与 Authorization 头；复跑通过。
  - f009（minor，watcher 停机竞态无回归测试）——遗留 p035 属实合规，本轮再次实体核对：`docs/pending/todo/p035_t026_network_watcher_stop_race_regression_test.md` 存在，内容明确来源（本 finding / Round 2 code f012 测试面）、嵌套闭包难测理由与两条补测路径，并声明生产行为本身无缺陷、只追测试债。非 critical/important，接受遗留，不阻断。
  - f010（minor，fail-closed 单 family 判别力）——已消除。`test_install_fail_closed_raises_on_single_family_failure` 按工具名分发桩（ipv6 restore 返 1、ipv4 返 0）断言仍抛 `NetworkPolicyError`，`test_fail_closed_cli_exits_3_on_restore_failure` 断言 CLI 退出码恰为 3；复跑通过。
  - f011（minor，readiness 隔离单 Profile 名实不符）——主体已消除。双 Profile 用例已落地（见 f012 复核），原始 RAISE 回归在任何顺序下必红；复跑通过。
  - f012（minor，f011 残余顺序判别力）——已消除。本轮逐行核对最终内容：`test_readiness_failure_in_one_profile_still_evaluates_others`（`tests/unit/test_t026_supervisor_convergence.py:973`）以 `{"prof_bad": runtime, PROFILE: runtime}` 构造、坏 Profile 在 API 列表首位，断言整体 not ready、健康条目 `ready is True`、坏条目带 `readiness_check_failed` 诊断；短路退化实现在此顺序下必红，判别力成立；复跑通过。
  - 说明：本路 finding 编号至 f012 为止，无 t026_test_f013（Round 5 已注明新编号自 f013 起续编且当轮未立）；任务所述 f001–f013 中的其余编号属 code 路同序号 finding，其回归测试已在 Round 3–5 逐条复核（f003 残余/f009–f011/f013/f014/f015），本轮在最终内容中抽核其中关键三段（锁存-释放-再报、缺失预算门禁、exited 路由）仍在复跑集内全过，结论沿用且与本轮复跑一致。
- 替身与生产接口一致性复查（本轮重点）：逐项比对 `tests/unit/test_t026_supervisor_convergence.py:39` 的 `_FakeAdapter` 与生产 `src/backend/cbrowser/supervisor/docker_adapter.py` 的 `DockerAdapter` 在收敛/readiness 路径实际被调用的方法——`inspect_media_network`、`resolve_gateway_container_id`、`get_profile_containers`、`get_stream_container_name`、`get_network_name`、`stream_policy_spec`、`browser_policy_spec`、`verify_container_policy`、`attach_profile_infrastructure`、`create_profile_network`、`rebuild_media_network`、`start_stream_container`、`cleanup_container_by_name`、`cleanup_network_by_name`、`fail_close_container`、`scan_active_containers` 与 `validator` 属性：签名位置兼容，`attach_profile_infrastructure` 的关键字形参名同为 `gateway_port`（与生产另一调用点的关键字调用一致）；`inspect_media_network` 的替身返回键集合（exists/conforms/plan/gateway_attached_id/gateway_ip/endpoints）与生产返回键逐字一致。未发现替身与生产接口分叉冒充覆盖的问题。替身未实现的方法（`start_browser_container`、`teardown_profile` 等）不属于收敛/readiness 被测路径，相关启动/拆除行为另由 adapter 层与既有套件覆盖，不构成本轮 finding。
- 改测方向复核：无「迁就实现」的改测。最终内容中的测试均为新增真实 case、删除 2 条填充测试与判别力增强（f012 改序、终态去重改走生产路径），无既有断言弱化/反转/删除（沿用 Round 3–5 逐轮核对，本轮复扫未见反例）。
- 危险模式扫描（最终测试全集定向扫描）：未发现恒真断言、删/反转 expect、注释断言、弱化断言、`.skip`/`.only`、`type: ignore`/`@ts-ignore`、timeout/容差放大、条件跳过弱化断言、mock 被测逻辑本身；e2e 的模块级 `skipif` 为 AC-012 真实 Docker 环境门控（本轮复跑 2 skipped），属合法交付形态。
- 本轮新发现：0 条
- 未进表的提示：无。另核对：本轮所审 `src/` 与 `tests/` 内容与 Round 5 所审代码零差异——最终 tip 为单一执行 commit `3ac6777`，本轮复跑计数与 Round 5 完全一致（后端子集 78 passed、前端 8 passed、e2e 2 skipped），scope 指纹变化源于 finish 归档后的流程文件状态，不含代码/测试改动。
- 总体判断：Round 1–4 全部 test finding（f001–f012）在最终提交内容中的处置经独立核实属实（11 条已消除、f009 合规遗留 p035），替身与生产接口无分叉，AC 证据与 Round 5 结论一致，无未解决 critical/important，PASS。
- 系统性 follow-up：无（f009 测试债仍由 p035 承接）

### AC 复验方式

- AC-001：re_verified——`tests/integration/test_api_search_defaults_routes.py`（含异实例负例）在本轮复跑集内全过，diff 核对原断言不变。
- AC-002：re_verified——runner 事件测试与收敛层 Gateway 替换/断网用例在本轮复跑集内全过；watcher 停机竞态分支无测试一节已合规遗留 p035，不影响事件触发与收敛主体。
- AC-003：re_verified——`test_t026_address_pool.py` 与 `test_t026_media_network_adapter.py`（显式 subnet/ip_range、端点占用拒绝、池耗尽显式失败、标签漂移不 conforming）在本轮复跑集内全过。
- AC-004：re_verified——规格不符重建、Stream-only 替换、替换中途 recovering 采样与 rebuild 未知 role 拒绝在本轮复跑集内全过。
- AC-005：re_verified——policy verify 与 fail-closed 严格化（全败/全胜/单 family 判别 + CLI exit 3）在本轮复跑集内全过。
- AC-006：re_verified——离线只重附着与无 session 凭扫描实例恢复用例在本轮复跑集内全过。
- AC-007：re_verified——回滚、未知 endpoint（cleanup/rebuild 双入口）、双 Profile 并发不串网在本轮复跑集内全过。
- AC-008：re_verified——Gateway 真实 harness 注册/拒绝集成、Stream 缺失/退出路由、预算门禁与锁存-释放-再报三段回归在本轮复跑集内全过。
- AC-009：re_verified——readiness 逐 Profile 三态、Docker 失败隔离（含坏 Profile 首位的双 Profile 顺序判别）、Stream 缺失守卫、control_client 路径/`_client` 构造与 control endpoints 鉴权在本轮复跑集内全过。
- AC-010：re_verified——`tests/integration/test_t026_transport_api.py`（响应围栏、异实例 null、coordinator 围栏、新实例 unknown）在本轮复跑集内全过；前端 `sse.transport.test.ts` 本轮复跑 4 passed。
- AC-011：re_verified——前端 `useBrowserSession.transportRecovery.test.tsx` 本轮复跑 4 passed（recovering 呈恢复中、明确失败/窗口耗尽才失败）。
- AC-012：trust_prior——生产入口覆盖（Gateway 替换、网络事件、API 离线、协议拒绝、地址冲突与池耗尽、规格迁移、策略漂移、并发事件、恢复失败）在 unit/integration 层经本轮复跑 re_verified；真实 Docker e2e 本机无 daemon、复跑 2 skipped，collect 与运行说明齐备，实跑义务按 spec 归 t032 AC-009，依赖其执行记录。

coverage = re_verified 11 / 总 AC 数 12

### reviewer 复跑记录

- 后端 t026 相关子集（`TMPDIR=/tmp`，任务指定 venv 与 `PYTHONPATH=src/backend`）：`tests/unit/test_t026_runner_network_events.py`、`tests/unit/test_t026_control_client.py`、`tests/unit/test_t026_media_network_adapter.py`、`tests/unit/test_t026_supervisor_convergence.py`、`tests/unit/test_t026_network_policy_verify.py`、`tests/unit/test_t026_address_pool.py`、`tests/unit/test_t026_control_endpoints.py`、`tests/integration/test_t026_gateway_registration.py`、`tests/integration/test_t026_transport_api.py`、`tests/integration/test_api_search_defaults_routes.py`、`tests/e2e/test_supervisor_reconciliation_e2e.py` —— 结果 78 passed, 2 skipped（e2e 无 Docker daemon），与 Round 5 计数一致。本轮未跑全量门禁（实施侧已跑且本轮内容与 Round 5 零差异，见结论未进表提示）。
- 前端（`src/frontend` 既有 node_modules，vitest）：`useBrowserSession.transportRecovery.test.tsx` 4 passed、`sse.transport.test.ts` 4 passed，合计 8 passed。

verdict: PASS
