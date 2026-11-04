# Task review t026（reviewer_focus: 代码）

- task：`t026_runtime_infrastructure_reconciliation`
- spec：`docs/tasks/t026_runtime_infrastructure_reconciliation/task.md`
- diff_anchor：`c2bd696bf7b2ca869642abb3cf0ea2dc4f6382b3`
- target：`git -C 'CBrowser_t026' diff c2bd696bf7b2ca869642abb3cf0ea2dc4f6382b3`
- round：1
- reviewed_at：2026-11-04T10:07:42+08:00

reviewed_scope: a8ff45528b1989b1

## Findings

### t026_code_f001 - 生产 DockerAdapter 不存在 `get_profile_containers`，收敛 / Stream 替换 / readiness 在生产路径必崩

- 严重度：critical
- 锚点：AC-002 / AC-004 / AC-005 / AC-008 / AC-009——稳态收敛、Stream-only 替换与 readiness 全部经此方法取 Browser/Stream 容器对象，生产不可达即全部不成立
- 位置：`src/backend/cbrowser/supervisor/core.py:297`（另 `:532`、`:683`）；缺失方 `src/backend/cbrowser/supervisor/docker_adapter.py`（全文无此方法）
- 问题：`SupervisorCore._converge_session`、`_replace_stream_only`、`_profile_readiness` 三处调用 `self.docker.get_profile_containers(profile_id)` 并按容器对象语义使用返回值（`.status` / `.id` / `.name` / 传给 `verify_container_policy`）。但 runner 注入的是生产 `DockerAdapter`（`src/backend/cbrowser/supervisor/runner.py:117`、`:131`），该类根本没有这个方法。reviewer 实测：`hasattr(DockerAdapter, 'get_profile_containers') == False`。生产后果：同实例分支调用 `_converge_session` 时在 core.py:297 抛 `AttributeError`，被 `scan_and_reconcile_existing` 的 per-profile 泛 catch 吞成一条 warning——附着 / 策略 / 注册三检永不执行，AC-002/005/008 的稳态收敛在生产为零；`readiness()` 无此层 catch，对任一有 session 的 desired=running Profile 直接 500，AC-009 不成立。单测之所以全绿，是因为 `tests/unit/test_t026_supervisor_convergence.py:64` 的 `_FakeAdapter` 自行发明了这个方法，替身与生产适配器接口分叉，掩盖了缺失。
- 建议：在生产 `DockerAdapter` 补齐 `get_profile_containers`（按 Browser/Stream 容器名或标签解析、返回与现有调用点一致的对象 / None 语义），并加一条直接对生产 Adapter 类（配 Docker 客户端替身）的接口契约测试，防止替身再次发明方法。

### t026_code_f002 - Stream-only 替换先销毁 Stream 与媒体网络、后检查 Gateway 是否存在，Gateway 缺失时把健康 Stream 拆没

- 严重度：important
- 锚点：AC-008 + 范围「Gateway 不可达时不重建 Stream」；AC-002 的 Gateway 缺失应为 recovering 而非破坏
- 位置：`src/backend/cbrowser/supervisor/core.py:469` 的 `_replace_stream_only`（销毁在 `:496`-`:510`，Gateway 解析在 `:511`）；调用侧顺序见 `:310`-`:328`
- 问题：`_replace_stream_only` 先记录替换预算，再 `cleanup_container_by_name(stream)`、（rebuild_network 时）删除并重建媒体网络，之后才 `_resolve_gateway_id()`；Gateway 为 None 时只改 transport 的 `last_error` 并 `return False`，此时 Stream 已删除、媒体网络已被重建。且 `_converge_session` 的媒体网络漂移分支（:313）在解析 Gateway（:328）之前就调用替换——Gateway 容器被删 / 尚未重建这一最常见场景下，一个本来健康的 Stream 会被拆掉且不重建；后续扫描因 Browser/Stream 不成对在 `_reconcile_profile` 完整性检查处直接返回，Stream 长期缺失。失败场景：Gateway 替换窗口内恰逢媒体网络不合规或策略漂移 → Stream 被销毁、Viewer 断流且不自愈，与 AC-008「仅在 Gateway 可达时替换」「Gateway 不可达不重建」直接冲突。
- 建议：把 Gateway 身份解析与可达性检查前移到任何销毁动作之前；Gateway 缺失 / 不可达时只置 recovering 并返回，不得触碰 Stream 与媒体网络；同时让媒体漂移分支先走 Gateway 检查再决定替换。

### t026_code_f003 - Stream 容器缺失 / 已停止时永远走不到 Stream-only 替换，与 AC-008「Stream 缺失」承诺不符

- 严重度：important
- 锚点：AC-008（「Stream 缺失或未注册不再导致停止整个 Browser/Stream 对」）+ 范围「Stream 缺失或持续未注册时有界退避替换 Stream」
- 位置：`src/backend/cbrowser/supervisor/core.py:301`（任一容器为 None 即 return）、`:796`-`:807` 的 `_reconcile_profile` 完整性检查、`:875`-`:897` 同实例分支
- 问题：`_replace_stream_only` 的全部三个调用点都在 `_converge_session` 内，而 `_converge_session` 入口要求 Browser 与 Stream 容器都存在；`_reconcile_profile` 在扫描roles 缺 Stream 时只记「Incomplete sandbox retained」返回；同实例分支在任一容器 status != running 时只上报 `container_exit` 并返回，收敛只在两容器都 running 时才被调用。因此 Stream 容器被删或退出后，没有任何 t026 路径执行 Stream-only 替换——要么永久保留残缺沙箱，要么落回 t022 RecoveryCoordinator 的整对重启语义（spec 明确 t022 预算不覆盖此场景、且 AC-008 要求不再停止整对）。实现只覆盖了「Stream 在、Agent 未注册」一半，「Stream 缺失」一半无实现，属被打勾 AC 的部分缺失。
- 建议：在 `_reconcile_profile` / `_converge_session` 增加 Stream 缺失或已停止、Browser 仍 running 且实例一致时的入口，在同一替换预算内调用 `_replace_stream_only(rebuild_network=False/按需)`；补 Stream 容器缺失场景的收敛测试。

### t026_code_f004 - Browser fail-closed 失败被吞且标记为已处理：永不重试，transport 却报已 fail-closed 的 failed 态

- 严重度：important
- 锚点：AC-005（Browser 策略漂移须「立即进入拒绝全部非 loopback 流量的 fail-closed 状态……不在无策略状态继续运行」）
- 位置：`src/backend/cbrowser/supervisor/core.py:390`-`:407`
- 问题：代码先把 `(profile_id, instance_id)` 加入 `self._policy_fail_closed` 再调用 `fail_close_container`；调用抛 `DockerSandboxError` 时只 `logger.warning` 吞掉，随后无条件把 transport 置为 `transport_state="failed", last_error="browser_policy_drift"`——对外呈现为已 fail-closed 的明确失败，而实际上 DROP 规则从未装上，Browser 仍在漂移 / 无策略状态下联网运行。更糟的是标记已写入集合，后续每一轮收敛都跳过 fail-close 重试，该实例终生不会再尝试封堵。失败场景：policy helper 镜像临时拉取失败 / netns 竞态导致一次 fail-close 失败 → Browser 长期裸奔且观测层撒谎称已封堵。
- 建议：仅在 `fail_close_container` 成功后才加入 `_policy_fail_closed` 并置 failed 态；失败时置 recovering / 明确的 `fail_close_failed` 错误并保留下一轮重试（可计入有界预算，耗尽后升级诊断），不得吞错后宣称已封堵。

### t026_code_f005 - API 离线附着恢复以内存 session 存在为前提，Supervisor 重启 + API 离线时对存量沙箱完全不恢复

- 严重度：important
- 锚点：AC-006（「按 Docker 标签与实例一致性判定合法的既有 Browser/Stream/网络仍完成网络重新附着」）+ 范围「API 离线仍依据受管 Docker 对象恢复网络附着」
- 位置：`src/backend/cbrowser/supervisor/core.py:586` 的 `_recover_attachment_offline`（session 守卫 `:586`-`:588`）；调用点 `:828` 附近 API 异常分支
- 问题：`_recover_attachment_offline` 第一行即 `session = self._sessions.get(profile_id); if session is None: return`。但 session 只由本进程 `start_profile` 或 API 返回 200 的恢复分支填充；Supervisor 重启后 `_sessions` 为空，若此时 API 又不可达，所有存量 Profile 的离线恢复直接跳过，Gateway 附着永不修复——而「重启后 API 尚未恢复」正是离线恢复要兜的核心场景。实现实际依据的是内存 session 而非 spec 要求的 Docker 标签 / 实例一致性；扫描侧 `_reconcile_profile` 手里已有 roles 的 instance_id 却未传入使用。单测 `test_offline_recovery_only_reattaches` 预置了 session，掩盖了此缺口。
- 建议：离线恢复改为依据扫描 roles 与容器标签的实例一致性判定合法性（roles 已在调用点可得），session 仅用于补充观测字段；无 session 时以 Docker 对象为准完成附着，并补「无 session + API 离线」用例。

### t026_code_f006 - readiness 的 policy 检查分支未守 None 容器，Stream 缺失时异常逃逸成 500 而非 not-ready 诊断

- 严重度：important
- 锚点：AC-009（「任一状态未知时不报 ready，返回逐 Profile 可脱敏诊断」）
- 位置：`src/backend/cbrowser/supervisor/core.py:706`-`:729` 的 `_profile_readiness`；异常源 `src/backend/cbrowser/supervisor/docker_adapter.py:1519`、`:1529`
- 问题：policy 分支的进入条件只要求 `roles` 非空、plan 与 session 存在，不要求 `roles["browser"]` / `roles["stream"]` 非 None；当 Stream 容器缺失（如正处于 Stream-only 替换窗口）时，browser/stream 检查已是 False，却仍以 None 调用 `verify_container_policy` / `browser_policy_spec`。生产 adapter 的 `_run_policy_helper` 在 `container.id`（:1519）与 `container.labels`（:1529）处抛 `AttributeError`，该异常不是 `DockerSandboxError`，不被 readiness 的窄 catch 捕获，`readiness()` 本身也无 per-profile 兜底，于是整个 readiness 端点 500、逐 Profile 诊断全丢，与 AC-009「未知不报 ready 并返回诊断」相反。
- 建议：policy 分支先判两容器均非 None，缺失时直接 `checks["policy"] = None` + `policy_unverifiable` 诊断；同时把 `_profile_readiness` 的异常面收敛为「任何单 Profile 异常 → 该 Profile not ready + 诊断」，不让单个 Profile 拖垮整个 readiness 响应。

### t026_code_f007 - 收敛附着 / 巡检失败未落 degraded 观测，端点被占时只剩扫描层一句泛化 warning

- 严重度：minor
- 锚点：AC-003（端点被占、标签不符时须显式 degraded / 失败）
- 位置：`src/backend/cbrowser/supervisor/core.py:302` 的 `inspect_media_network` 调用与 `:336` 的 `attach_profile_infrastructure` 调用
- 问题：同一函数内 policy verify 失败有专门的 recovering 观测落点，但 inspect / attach 抛出的 `DockerSandboxError`（含「Gateway fixed endpoint is held by another container」的端点占用、网络所有权不符）没有任何 catch：异常冒泡到扫描层被泛化为 `Profile reconciliation failed … error_type=…`，transport 观测不置 degraded / failed，API/SSE 侧看不到该 Profile 处于冲突状态，只能等下一轮扫描重复抛错。显式失败在日志里有、在用户可见的观测面缺失。
- 建议：给 inspect / attach 加与 policy 分支同构的异常处理：置 `transport_state="failed"`（或 recovering，按可重试性区分）、`last_error` 写明如 `gateway_endpoint_conflict` / `media_inspect_failed` 后返回。

### t026_code_f008 - 新增网络事件 watcher 的事件流从不关闭，停机时阻塞线程无法被 cancel 打断

- 严重度：minor
- 锚点：行为缺陷（健壮性 / 资源释放）——无对应 AC
- 位置：`src/backend/cbrowser/supervisor/runner.py:257` 的 `watch_docker_network_events`
- 问题：既有容器事件 watcher 有 `_close_stream_sync` 在停机时关闭事件流以打断阻塞迭代；新增的网络 watcher 把 `stream` 放在局部变量里从不关闭，`stop_event` 只在收到下一条事件后才检查。停机路径（runner.py finally）对 `docker_network_events_task` 只有 `cancel()`，而 `asyncio.to_thread` 的阻塞迭代不响应 cancel；gather 超时 15 秒后虽继续走，但进程退出时 executor 关闭仍会等待该线程，Supervisor SIGTERM 后可能挂住不退出，直到恰有网络事件到达或 Docker 事件流自身断开。
- 建议：与容器 watcher 同构管理网络事件流的生命周期：保存引用并在停机时 close，或给事件流设置读取超时后循环检查 `stop_event`。

## 结论

- 本轮新发现：8 条（critical 1 / important 5 / minor 2）
- 未进表的提示：
  - 文件过大（降级规则，仅结论提示）：`src/backend/cbrowser/supervisor/core.py` 2035 行（本 task 净增约 590 行，≥800 important 阈值）；`src/backend/cbrowser/supervisor/docker_adapter.py` 1616 行（净增约 324 行）；`src/backend/cbrowser/gateway/server.py` 923 行（净增约 121 行）；`src/backend/cbrowser/supervisor/network_policy.py` 455 行、`src/frontend/src/features/browser-session/useBrowserSession.ts` 510 行（≥400 minor 阈值）。均未见不可拆的硬约束说明；其中 core.py 的收敛逻辑继续膨胀与 f001 的接口分叉互为因果，建议随修复一并拆分收敛器。
  - 圈复杂度：本 task 新增的 `_converge_session`（core.py:269）约 200 行、手算 CC 远超 15（多层分支 + 6 个 return 出口），`_replace_stream_only`、`_profile_readiness` 亦偏高；复杂度本身不单独出 finding，其已产出的可观测缺陷即 f002 / f004 / f006。
  - 范围外观察：reviewer 全量复跑 unit 时 2 条 `tests/unit/test_runtime_agent_faults.py` X11 socket 用例失败，隔离复跑确认错误为 `OSError: AF_UNIX path too long`——由规定的 `TMPDIR=$PWD/.scratch/t026/tmp` 使 socket 路径超长所致，且本 diff 不触及 runtime_agent / X11 文件，不归因于本 task；实施侧 note 声称的「unit 778 passed」应是在更短 TMPDIR 下取得，建议门禁脚本固定短 TMPDIR 以免后续轮次误判。
  - 安全 / 契约面已扫：Gateway 结构化拒绝不含凭证、拒绝码经 Pydantic 模式约束；reconcile_all / readiness 复用既有内部 token 且仅经容器内 CLI 消费、无新增发布端口或 Caddy 路由（control_client.py / control_server.py 已核）；地址池分配不回退随机地址（address_pool.py / docker_adapter.py 已核）。此三面未发现新增问题。
- 总体判断：存在未解决 critical（f001）与多条 important——生产收敛路径因替身发明接口而整体不可达，且 Stream 替换时序、fail-closed、离线恢复、readiness 均有 AC 级缺口，FAIL。
- 系统性 follow-up：无（均为本 task 范围内缺陷，应在本 task 修复轮内解决，不另立 follow-up）。

### AC 复验方式

- AC-001：`re_verified`——复跑 `tests/integration/test_api_search_defaults_routes.py`（含新增异实例负例）全过；diff 核对夹具改为绑定 `inst_1` 与 stub 一致、原断言未改。
- AC-002：`re_verified`——收敛单测复跑全过，但代码核查发现生产调用链在 core.py:297 必崩（见 f001），且 Gateway 缺失顺序问题见 f002；生产语义不成立。
- AC-003：`re_verified`——复跑 `test_t026_address_pool.py` / `test_t026_media_network_adapter.py` 全过，显式 subnet+ip_range、range 外固定端点、冲突 / 耗尽显式抛错在 adapter 层成立；收敛层观测缺口见 f007。
- AC-004：`re_verified`——收敛单测断言 Browser 容器 ID 不变、网络 + Stream 重建；但生产经 f001 不可达，且迁移时序受 f002 影响。
- AC-005：`re_verified`——复跑 `test_t026_network_policy_verify.py` 与 fail-closed 单测；渲染 / 校验全等成立，但 fail-close 失败处理缺陷见 f004。
- AC-006：`re_verified`——离线附着单测复跑全过，但仅覆盖预置 session 的情况；重启 + 离线缺口见 f005。
- AC-007：`trust_prior`——多 Profile 并发与未知 endpoint 清理依赖实施侧单测与 adapter 代码阅读（`cleanup_network_by_name` 未知 endpoint 拒绝逻辑已读），reviewer 未独立构造真实 Docker 并发场景（本机无 Docker）。
- AC-008：`re_verified`——复跑 `test_t026_gateway_registration.py`（真实 Gateway 进程内集成）全过、结构化拒绝与不可修复分类成立；但 Stream 缺失分支未实现（f003）、Gateway 缺失时替换时序错误（f002）。
- AC-009：`re_verified`——复跑 `test_t026_control_endpoints.py` 与 schema 测试，端点认证 / CLI / schema 导出成立；但 readiness 生产路径受 f001 / f006 影响会崩。
- AC-010：`re_verified`——复跑 `test_t026_transport_api.py` 与前端 `sse.transport.test.ts`（4 过），REST 围栏、SSE 字段同步与前端校验成立；不落库、重启后 absent=unknown 的语义与既有 search-defaults 模式一致。
- AC-011：`re_verified`——复跑前端 `useBrowserSession.transportRecovery.test.tsx`（4 过）：recovering 呈现恢复中、failed 立即失败、窗口耗尽失败、ready 后重连均与实现一致。
- AC-012：`trust_prior`——真实 Docker e2e 在本机无 Docker daemon，按已批准口径只验收集与入口：`--collect-only` 成功收集 3 条用例、文件头含 t032 运行说明；实跑结果依赖 t032，本地不记 PASS。

coverage = re_verified 10 / 总 AC 数 12

### reviewer 复跑记录

- `pytest tests/unit/test_t026_*.py tests/unit/test_supervisor_schema.py tests/unit/test_api_models_and_sse.py -q` → 34 passed
- `pytest tests/integration/test_t026_gateway_registration.py tests/integration/test_t026_transport_api.py tests/integration/test_api_search_defaults_routes.py -q` → 10 passed
- `pytest tests/unit -q`（全量）→ 776 passed / 2 failed / 1 skipped；2 failed 为上文 TMPDIR 路径长度所致的存量 X11 用例，已隔离复现并排除归因
- `pytest tests/e2e/test_supervisor_reconciliation_e2e.py --collect-only -q` → 3 tests collected（本机无 Docker，未实跑）
- 前端 `vitest run useBrowserSession.transportRecovery.test.tsx sse.transport.test.ts` → 8 passed
- `hasattr(DockerAdapter, 'get_profile_containers')` → False（f001 直接证据）

verdict: FAIL

## Round 2 (2026-11-04T10:32:23+08:00)

- round：2
- reviewed_at：2026-11-04T10:32:23+08:00

reviewed_scope: 86308973738556df

## Findings（本轮新发现，续编）

### t026_code_f009 - readiness 的逐 Profile 评估仍可被单个 Docker 异常拖垮：inspect / 容器查询抛错逃逸成端点 500

- 严重度：important
- 锚点：AC-009（「任一状态未知时不报 ready，返回逐 Profile 可脱敏诊断」）；亦为 Round 1 f006 建议中「异常面收敛」部分的未竟项（f006 的 None 容器触发点本身已修，见复核）
- 位置：`src/backend/cbrowser/supervisor/core.py:743`-`:746`（`_profile_readiness` 内 `inspect_media_network` 调用无 catch）、`:729`-`:732`（`get_profile_containers` 调用无 catch）、`:710`（`readiness()` 调用点无 per-profile 兜底）；异常源 `src/backend/cbrowser/supervisor/docker_adapter.py:774`-`:779` 与 `:798`-`:805`（所有权不符 / Docker 故障时 `inspect_media_network` 抛 `DockerSandboxError`）
- 问题：reviewer 用 Round 2 探针实测（借用 convergence 测试夹具构造 core，令 `inspect_media_network` 抛 `DockerSandboxError("ownership mismatch")`）：`await core.readiness()` 直接 RAISE 该异常，而非返回 not-ready + 诊断。生产场景：某 Profile 媒体网络标签所有权漂移（正是 t026 要检测的漂移类状态）或 Docker daemon 在 `networks.get` 时瞬时故障 → `GET /supervisor/v1/readiness` 整体 500，全部 Profile 的逐条诊断一并丢失，t027 的部署门禁只能看到一个不透明 500。已有的隔离只覆盖 runtime 查询失败（core.py:690 附近），覆盖不到评估函数内部的 Docker 调用。
- 建议：把 `_profile_readiness` 的整体调用纳入 per-profile 异常收敛（任何异常 → 该 Profile `ready=False` + 如 `readiness_evaluation_failed:<type>` 诊断），或至少给 inspect / get_profile_containers / resolve 三处调用加与 policy 分支同构的窄 catch 并落 `checks[...] = None` + 诊断。

### t026_code_f010 - fail-closed helper 把 iptables-restore 的失败吞成 exit 0，f004 的「谎报已封堵」在 helper 层重现

- 严重度：important
- 锚点：AC-005（Browser 漂移须真正进入拒绝全部非 loopback 流量的 fail-closed 状态，「不在无策略状态继续运行」）
- 位置：`src/backend/cbrowser/supervisor/network_policy.py:381`-`:390` 的 `install_fail_closed()` 复用 `:252`-`:271` 的 `_install_fail_closed()`；helper 入口 `:399`-`:412`；上层信任点 `src/backend/cbrowser/supervisor/docker_adapter.py:1632`-`:1639` 的 `fail_close_container` 与 `src/backend/cbrowser/supervisor/core.py:390`-`:412` 的标记逻辑
- 问题：`_install_fail_closed` 是 t022 语境下的 best-effort 兜底：`subprocess.run(..., check=False)` 且结果 returncode 从不检查，异常亦被吞为 warning。t026 新增的 `install_fail_closed()` 直接复用它，于是 fail-closed 模式下 restore 返回非 0（如 xtables 锁超时、权限失败、二进制缺失抛错）时 helper 仍以 exit 0 退出。reviewer 探针实测：stub `subprocess.run` 返回 returncode=1 时，`install_fail_closed()` 正常返回、`main(["fail-closed"])` 不触发其设计的 exit 3、进程码为 0。后果链与 f004 同构、深一层：adapter 认定封堵成功 → core 把 `(profile, instance)` 加入 `_policy_fail_closed` 并上报 `browser_policy_drift` 的 failed 态 → 后续每轮 verify 仍不符但因标记在而永不重试，Browser 实际仍带着漂移/缺失策略（可为默认 ACCEPT）联网运行，观测面却显示已封堵的明确失败。Round 1 的 f004 修复（core 层失败重试）因此被 helper 层的假成功短路。
- 建议：为 fail-closed 模式提供严格版安装：任一 family 的 restore returncode 非 0 或抛错即整体失败（helper exit 3，如其错误分支本意）；`_install_fail_closed` 的 best-effort 语义只保留给 apply 失败后的兜底路径，不得作为 AC-005 封堵成功的判据。补一条 stub restore 失败 → helper 非 0 的测试。

### t026_code_f011 - Stream 容器缺失路由绕过替换预算：预算耗尽仍每轮扫描/事件全量重试，无有界退避

- 严重度：important
- 锚点：AC-008（「仅在 Gateway 可达且原因可由替换修复时有界退避地替换」）+ 范围「Stream 缺失或持续未注册时有界退避替换 Stream」
- 位置：`src/backend/cbrowser/supervisor/core.py:921`-`:944` 的 `_reconcile_profile` 缺失-Stream 路由（直接调用 `_replace_stream_only`，未查 `_stream_replacement_allowed`）；对照 `_converge_session` 内三处调用点均先查预算（`:326`、`:373`、`:490` 附近）
- 问题：reviewer 探针实测：把 `_stream_replace_attempts` 预置为窗口内 3 次（`_stream_replacement_allowed` 返回 False）后，`_reconcile_profile` 对 Stream 缺失的 Profile 仍调用了替换。该路由既不查预算、也无任何退避间隔，节奏完全由扫描驱动：30 秒兜底扫描之外，替换尝试自身产生的网络断开/重建事件又会经网络 watcher 唤醒下一轮扫描，形成自加速重试回路。失败场景：Stream 镜像缺失/启动必失败时，每轮都走完整替换（含按媒体合规判定重建网络 + attach + 容器创建），无上限，与 AC-008 的有界退避承诺不符；`_replace_stream_only` 内部虽记录次数，但记录不构成门禁。
- 建议：缺失路由调用前同样查 `_stream_replacement_allowed(profile_id, instance_id)`；耗尽时落 `transport_state="failed", last_error="stream_missing"`（或等价诊断）并 return，靠窗口滑动或显式重启恢复；补预算耗尽用例。

### t026_code_f012 - 网络事件 watcher 的流登记仍有停机竞态：stop 后登记的事件流无人关闭（f008 残余）

- 严重度：minor
- 锚点：行为缺陷（健壮性 / 资源释放）——Round 1 f008 的主体已修，此为残余竞态
- 位置：`src/backend/cbrowser/supervisor/runner.py:283`-`:310` 的 `watch_docker_network_events`（`:295` 登记 `network_events_stream` 时未查 `stop_event`）；对照容器 watcher `:245`-`:262` 的登记前 stop 检查
- 问题：停机序列先 `stop_event.set()` 再 `_close_stream_sync()` 关流；若网络 watcher 线程此时尚卡在 `client.events()` 返回前、随后才登记流，关闭动作已错过该流，`_pump_network_events` 只能等下一条网络事件才发现 stop；`docker_network_events_task` 的 cancel 打不断 `asyncio.to_thread` 阻塞迭代，gather 超时后的兜底分支也只 cancel server 与容器事件任务。窗口虽窄，但 SIGTERM 后进程退出仍可能被该线程挂住，与容器 watcher 已有的防竞态写法不对称。
- 建议：与容器 watcher 同构：登记前（持 `stream_lock` 时）检查 `stop_event`，已置位则立即 close 并返回；或在 `_pump_network_events` 的迭代外层加同样的登记后复查。

### t026_code_f013 - rebuild_media_network 的端点核验弱于同文件 cleanup 语义：异常 role 的受管容器会被当已知端点拆接

- 严重度：minor
- 锚点：AC-007（未知 endpoint 拒绝清理）的一致性延伸——同一 adapter 内两套端点准入标准
- 位置：`src/backend/cbrowser/supervisor/docker_adapter.py:866`-`:880` 的 `rebuild_media_network` 端点核验（只查 prefix + managed-by）；对照 `:1414`-`:1440` 的 `cleanup_network_by_name`（另查 role ∈ {browser, stream, gateway}，其余 role  explicit 拒绝）
- 问题：一个带本 prefix + `managed-by=supervisor` 但 role 为其它值（如未来新增的基础设施容器、或被误附到媒体网络的受管容器）的端点，在 cleanup 路径会被判「Unauthorized container role」拒绝，在 rebuild 路径却被当作已知端点断开并重连（Gateway 以外一律 `new_net.connect`）。两条同为「动网络前先核验端点」的生产路径准入标准分叉，rebuild 可能把不该动的容器卷入媒体网络重建且不报错。
- 建议：rebuild 的端点核验对齐 cleanup：role 须 ∈ {browser, stream, gateway}，且 browser/stream 应核对 profile-id 与本 Profile 一致，其余一律先行拒绝、零拆动。

## 结论

- 前轮 finding 复核（Round 1，共 8 条）：
  - t026_code_f001（critical）：**已消除**。生产 `DockerAdapter.get_profile_containers` 已实现（`docker_adapter.py:1640`-`:1671`：按确定名取容器 + prefix/profile-id/role 标签核验、外国与缺失均读作 None），reviewer 实测 `hasattr(DockerAdapter, 'get_profile_containers') == True`，且有直接对生产 Adapter 的契约测试 2 条（`test_t026_media_network_adapter.py:241`、`:258`），全量 unit 801 passed 中通过。连带实现的 `adapter.rebuild_media_network`（`docker_adapter.py:839`）生产路径真实存在：核验端点→逐个断开→删网→按规格重建→重连非 Gateway 端点、未知端点先行拒绝，AC-004 的生产缺口（Browser 附着时 cleanup 拒绝删网）随之打通；其端点核验口径的小缺口另见 f013。
  - t026_code_f002（important）：**已消除**。`_replace_stream_only`（core.py:501 起）先 `_resolve_gateway_id`，为 None 时只落 `gateway_missing` recovering 观测并 return False，记录预算与一切拆动都在其后；回归测试 `test_gateway_missing_aborts_replacement_before_teardown` 断言零拆动调用且本次复跑通过。
  - t026_code_f003（important）：**修不彻底，仍存在**。容器「缺失」一半已修：`_reconcile_profile` 在 desired=running + 跟踪 session 同实例 + `s_c is None` 时路由 Stream-only 替换（core.py:921-944），无 session 保留语义有测试覆盖。但容器「已停止/退出」一半未修：reviewer 探针实测，roles 中 stream status=`exited`、Browser running、session 同实例时，`_reconcile_profile` 零替换调用、只把 session 置 `observed_state=error` 并报 `container_exit`（core.py:966-985 的同实例分支）——后续收敛要求 observed=running 永不再进入，实际恢复只剩 t022 RecoveryCoordinator 的整对重启语义，正是 AC-008 要消除的「Stream 出问题导致停止整个 Browser/Stream 对」。实施处置表把 f003 整体记为已修，与生产代码不符。
  - t026_code_f004（important）：**core 层已消除，helper 层同构缺陷另立 f010**。core.py:390-412 改为成功后才加入 `_policy_fail_closed`，失败落 `browser_policy_drift_unmitigated`（recovering）并下轮重试，两轮收敛测试本次复跑通过；但封堵成功的判据（helper exit 0）本身不可靠，见 f010。
  - t026_code_f005（important）：**已消除**。`_recover_attachment_offline`（core.py:625 起）接受扫描已核验的 `scan_instance_id`，调用点在实例一致性校验后传入 `b_inst`；无 session 恢复测试 `test_offline_recovery_without_session_uses_scan_instance` 本次复跑通过。
  - t026_code_f006（important）：**原触发点已消除，异常面收敛未竟另立 f009**。readiness policy 分支已要求双容器非 None（core.py:756-765），缺失时落 `policy=None` + `policy_unverifiable`；注册未知诊断已改 `registration_unverifiable`。但 `_profile_readiness` 其余 Docker 调用抛错仍可逃逸成 500，见 f009。
  - t026_code_f007（minor）：**已消除**。`_converge_session` 中 inspect 失败落 `media_inspect_failed`、attach 失败落 `media_attach_failed`（均为 failed + `last_error_at`），与 policy 分支同构，代码与复跑测试一致。
  - t026_code_f008（minor）：**主体已消除，残余竞态另立 f012**。网络流已登记进 `_close_stream_sync` 一并关闭、匹配/泵逻辑抽为 `media_network_event_matches` / `_pump_network_events` 并有 4 条测试本次复跑通过；登记时序竞态见 f012。
- 本轮新发现：5 条（important 3：f009 / f010 / f011；minor 2：f012 / f013）。另 Round 1 的 f003（important）修不彻底、仍未解决。
- 未进表的提示：
  - 文件过大（降级规则，仅结论提示）：`src/backend/cbrowser/supervisor/core.py` 2128 行（Round 1 后再净增约 93 行，仍 ≥800 important 阈值）；`docker_adapter.py` 1721 行；`gateway/server.py` 923 行；`network_policy.py` 455 行、`useBrowserSession.ts` 510 行（≥400 minor 阈值）。本轮 f009/f010/f011 均落在 core.py / network_policy.py 的既有膨胀面上，继续堆叠的风险与 Round 1 提示相同。
  - 圈复杂度：`_converge_session`、`_reconcile_profile`、`_profile_readiness` 仍为多分支长函数（CC 均 >15）；其已产出的可观测缺陷即 f003 残余与 f009、f011，不另出复杂度 finding。
  - 流程观察：`tests/unit/test_t026_control_client.py` 与 `tests/unit/test_t026_runner_network_events.py` 在 `git status` 中仍为未跟踪（`??`）且未 `git add -N`，不出现在 `git diff` 输出内；reviewer 本轮已直接读到并复跑这两文件（均通过），不影响本轮结论，但实施方收尾前应按指纹流程把交付文件纳入索引，避免后续轮次按「未跟踪交付文件不可见」判 INCOMPLETE。
  - 安全 / 契约面本轮复扫：Gateway 结构化拒绝与 build 标识不含凭证（gateway/server.py、stream_agent/protocol.py 已读）；reconcile_all / readiness 仍只经内部 token + 容器内 CLI，无新增发布端口；地址分配不回退随机地址。未发现新增问题。
- 总体判断：Round 1 的 critical 与多数 important 已真实修复（f001/f002/f005/f007 消除，f004/f006 主体消除），但 f003 的「已停止 Stream」一半仍未实现，且本轮新查出 3 条 important（readiness 异常逃逸 f009、fail-closed helper 假成功 f010、缺失路由绕过替换预算 f011）——仍存在未解决 important，FAIL。
- 系统性 follow-up：无（均为本 task 范围内缺陷，应在本 task 修复轮内解决）。

### AC 复验方式

- AC-001：`re_verified`——复跑 `tests/integration/test_api_search_defaults_routes.py` 通过（在本轮 68 项 t026 测试批内），夹具绑定与异实例负例与 Round 1 复核一致。
- AC-002：`re_verified`——convergence / runner 事件测试复跑通过，Gateway 标签重解析与同端点重附代码已读；网络 watcher 残余竞态见 f012（minor）。
- AC-003：`re_verified`——`test_t026_address_pool.py` / `test_t026_media_network_adapter.py` 复跑通过；分配、冲突、耗尽显式失败与 Round 1 一致。
- AC-004：`re_verified`——生产 `rebuild_media_network` 代码已逐行读（docker_adapter.py:839-912），适配器测试（含未知端点拒绝、Browser 保持附着）复跑通过；端点 role 口径小缺口见 f013。
- AC-005：`re_verified`——policy verify 与 core 层 fail-close 重试复跑通过，但 helper 层假成功使「真正封堵」在 restore 失败时不成立，见 f010；本 AC 不能按完全成立计。
- AC-006：`re_verified`——无 session 离线恢复测试复跑通过，`_recover_attachment_offline` 签名与调用点代码已读。
- AC-007：`trust_prior`——依赖实施侧并发/回滚/未知 endpoint 单测（本轮复跑全过）与 adapter 代码阅读；reviewer 未独立构造真实 Docker 并发场景（本机无 Docker）。
- AC-008：`re_verified`——Gateway 注册集成测试复跑通过、Gateway 缺失零拆动与不可修复拒绝分类成立；但已停止 Stream 不走 Stream-only 替换（f003 残余）且缺失路由无预算门禁（f011），本 AC 不能按完全成立计。
- AC-009：`re_verified`——control endpoints / control_client 测试复跑通过、schema 一致；但 readiness 在 Docker 评估异常时 500 而非逐 Profile 诊断，见 f009，本 AC 不能按完全成立计。
- AC-010：`re_verified`——`test_t026_transport_api.py` 与前端 `sse.transport.test.ts`（4 过）复跑通过，围栏与字段同步与生产代码一致。
- AC-011：`re_verified`——复跑前端 `useBrowserSession.transportRecovery.test.tsx`（4 过）：recovering 呈现恢复中、failed 立即失败、窗口耗尽失败、ready 后重连均与实现一致。
- AC-012：`trust_prior`——本机无 Docker daemon，按已批准口径只验收集与入口：`--collect-only` 成功收集 2 条用例（Round 1 的恒真填充用例已按 test f004 删除）；实跑义务仍归 t032。

coverage = re_verified 10 / 总 AC 数 12

### reviewer 复跑记录

- `pytest tests/unit/test_t026_*.py tests/unit/test_supervisor_schema.py tests/unit/test_api_models_and_sse.py tests/integration/test_t026_*.py tests/integration/test_api_search_defaults_routes.py -q`（TMPDIR=/tmp，venv 同实施侧）→ 68 passed
- `pytest tests/unit -q` → 801 passed / 1 skipped（与实施侧自述一致）
- 前端 `vitest run useBrowserSession.transportRecovery.test.tsx sse.transport.test.ts` → 8 passed
- `pytest tests/e2e/test_supervisor_reconciliation_e2e.py --collect-only -q` → 2 tests collected（本机无 Docker，未实跑）
- `hasattr(DockerAdapter, 'get_profile_containers')` / `hasattr(DockerAdapter, 'rebuild_media_network')` → 均 True（f001 直接复核证据）
- Round 2 探针（临时脚本，跑后已删）：readiness 在 `inspect_media_network` 抛 `DockerSandboxError` 时 RAISE（f009）；stream status=exited 时 `_reconcile_profile` 替换调用为空、session observed=error（f003 残余）；stub restore returncode=1 时 `install_fail_closed()` 与 `main(["fail-closed"])` 均以成功返回（f010）；替换预算耗尽后缺失路由仍调用替换（f011）

verdict: FAIL

## Round 3 (2026-11-04T10:43:44+08:00)

- round：3
- reviewed_at：2026-11-04T10:43:44+08:00

reviewed_scope: f8944c6b9d236902

## Findings（本轮新发现，续编）

### t026_code_f014 - container_exit 错误被记录后同实例自愈无出口： pair 恢复健康也永不重回收敛，transport 永卡 recovering、observed 永报 error

- 严重度：important
- 锚点：AC-002（同实例周期扫描须持续做附着/策略/注册检查）+ AC-008（Stream-only 修复后应回到稳态收敛）；可观测行为缺陷——健康 pair 被永久报告为 error/recovering 且收敛整体停摆
- 位置：`src/backend/cbrowser/supervisor/core.py:1001`-`:1009`（预算耗尽/双停回落把 `session.observed_state` 置 `"error"`）、`:1010`-`:1025`（回報 running 与 `_converge_session` 的唯二入口都以 `session.observed_state == "running"` 为门）、`:992`-`:1000`（exited-Stream 修复路由不触碰 observed_state）；`_converge_session` 全仓唯一调用点即 `:1025`
- 问题：reviewer 三段探针实测（生产 `_reconcile_profile`，替身仅作 Docker/API 脚本）：①Stream exited + 替换预算耗尽 → 回落 container_exit，`observed_state="error"`；②窗口滑动后 Stream 仍 exited → Stream-only 修复确实触发（f003 残余已修）；③此后 Browser/Stream 双 running 连扫两轮 → `_converge_session` 零调用、transport 永停 `recovering`、session observed 永停 `error`。根因：同实例块内把 observed 从 error 改回 running 的两条路径（`:1010` 的 elif 回报、`:1020` 的收敛门）都要求 observed 已经是 running，自锁无出口；已有的权威健康信号 `_reconcile_instance_observation` 的返回值（`:975`，Agent 健康时为 `"running"`）只用于 stopped/error 早退、未用于清除这个 Docker 事实型错误。触发面不限于预算耗尽：Browser/Stream 双停后同实例容器被拉起（同 instance 标签不变）走同一回落置 error，同样中招。后果：该实例此后附着/策略/注册三检全停（AC-002 失效）、新 Gateway 附着与策略漂移不再被发现、API 侧 observed 恒 error、Viewer 恒 recovering，直到 Browser 重启换实例——正是 t026 要消除的「小故障靠整对重启恢复」。
- 建议：同实例块在双容器 running 且 `_reconcile_instance_observation` 返回 `"running"`（Agent 已明确健康上报；返回 `"error"`/`"stopped"` 已在 `:979` 早退、返回 None 时不得清除）时，把本地 `session.observed_state` 复位为 `"running"` 并经 `_report_observed` 同步，再走收敛门；`:988` 注释保护的「Agent 错误观测不被 Docker running 覆盖」由此不受影响（Agent 错误在上游已早退）。补回归：耗尽回落 → 窗口滑动 → 修复 → 双 running 后 `_converge_session` 恢复调用且 transport 回 ready。

## 结论

- 前轮 finding 复核（Round 2，共 6 条：f003 残余 + f009–f013）：
  - t026_code_f003（残余，important）：**已消除**。新增 exited-Stream 路由（core.py:992-1000）位于同实例块内：Browser running 且仅 Stream 非 running 且预算内 → 直接 `_replace_stream_only(rebuild_network=False)`；reviewer 探针实测四场景：exited Stream 触发替换且 observed 不置 error；Browser 同停时零替换、回落 container_exit（与 t022 语义边界正确——双停不做 Stream-only 修复）；Browser 单停时零替换；预算耗尽时零替换并回落 container_exit。窗口滑动后修复可再次触发（探针验证）。但该修复与 observed_state 门控的组合产生了新的自锁缺陷，另立 f014。
  - t026_code_f009（important）：**已消除**。`readiness()` 对 `_profile_readiness` 加逐 Profile 兜底（core.py:710-724），任一异常落 `readiness_check_failed:<type>` 的 not-ready 条目、诊断只含异常类型名（可脱敏）；reviewer 探针令 `inspect_media_network` 抛 `DockerSandboxError` 实测：`readiness()` 正常返回、该 Profile ready=False 且诊断符合预期，不再 RAISE/500。
  - t026_code_f010（important）：**已消除，且未误伤 apply 路径**。生产代码核查：显式入口 `install_fail_closed()`（network_policy.py:381-412）已改为严格实现——任一 family restore returncode 非 0 或不可执行即抛 `NetworkPolicyError`，CLI `main(["fail-closed"])` 随之 exit 3，adapter `fail_close_container`（docker_adapter.py:1634-1639）对非 0 抛 `DockerSandboxError`，core（:414-430）不标记、落 `browser_policy_drift_unmitigated` 下轮重试，链条闭合。reviewer 探针实测：stub restore rc=1 → `install_fail_closed()` 抛错、CLI 退出码 3；工具缺失（FileNotFoundError）同样抛错。apply 路径未被误伤：`apply_policy` 失败回滚仍调用 best-effort 的 `_install_fail_closed`（network_policy.py:311，不查 returncode、吞异常），探针令 save 成功/restore 失败时 `apply_policy` 仍以 `NetworkPolicyError` 抛出、回滚兜底不掩盖也不另抛——best-effort 语义原样保留，严格版仅经 CLI fail-closed 模式可达（全仓调用点已 grep 核对）。
  - t026_code_f011（important）：**已消除，预算口径与全仓一致**。缺失-Stream 路由（core.py:935-955）调用替换前先查 `_stream_replacement_allowed`，耗尽落 `transport_state="failed", last_error="stream_missing_budget_exhausted"` 并 return；reviewer 探针实测耗尽时零替换且诊断精确、预算可用时正常替换。预算口径一致性核查：全部 5 条替换入口（converge 内媒体漂移/Stream 策略漂移/注册未修复、缺失路由、exited 路由）均先查同一 `_stream_replacement_allowed(profile, instance)`（同 key、同 3 次/300 s 窗口），`_replace_stream_only` 内 Gateway 解析成功后统一 `_record_stream_replacement` 记 1 次（Gateway 缺失不记——未发生任何拆动，与 f002 的零拆动语义一致），无双记、无漏记。
  - t026_code_f012（minor）：**已消除**。网络 watcher 登记流后立即复查 `stop_event`（runner.py:296-303），已置位则调 `_close_stream_sync()` 自行关流并 return；时序核查：stop 置位必先于停机侧 close pass，登记发生在置位前由 close pass 关闭、发生在置位后由 watcher 自检关闭，两序均无漏关，与容器 watcher 的防竞态语义等价。
  - t026_code_f013（minor）：**已消除**。`rebuild_media_network` 端点核验已加 role ∈ {browser, stream, gateway} 白名单（docker_adapter.py:866-880），与 `cleanup_network_by_name`（:1414-1440）的准入标准对齐（cleanup 同样不查 profile-id，两路径口径现已一致）；未知 role 在任何拆动前抛 `DockerSandboxError` 拒绝。
- 本轮新发现：1 条（important 1：f014；minor 0）。Round 2 的 6 条全部消除，但 f003 修复路径的组合缺陷 f014 仍未解决。
- 未进表的提示：
  - 文件过大（降级规则，仅结论提示）：`core.py` 2166 行（Round 2 后再净增约 38 行，仍 ≥800 important 阈值且本轮 f014 又落在该文件）；`docker_adapter.py` 1723 行；`gateway/server.py` 923 行；`network_policy.py` 482 行、`useBrowserSession.ts` 510 行（≥400 minor 阈值）。f014 的自锁正是 core.py 同实例块多分支状态机继续膨胀的产物，拆分收敛/观测状态机的建议与前两轮相同。
  - 圈复杂度：`_reconcile_profile` 本轮再增分支（exited 路由 + 预算回落），CC 进一步上升；其已产出的可观测缺陷即 f014，不另出复杂度 finding。
  - 流程观察：Round 2 提示的两份未跟踪测试文件现已纳入索引（`git status` 显示为 A），指纹流程已闭合。
  - 安全 / 契约面本轮复扫：readiness 新兜底的诊断仅含异常类型名、无内部细节泄漏；fail-closed 严格化未改动任何鉴权/端口面；未发现新增问题。
- 总体判断：Round 2 全部 finding（含 f003 残余）已真实修复，复核以生产代码 + reviewer 独立探针为准（13 条探针断言全过，含 f010 apply 回滚不误伤、f003 双停边界、f011 预算口径）；但本轮新查出 1 条 important（f014：container_exit 记录后同实例自愈自锁、收敛永久停摆），仍存在未解决 important，FAIL。
- 系统性 follow-up：无（f014 为本 task 范围内缺陷，应在本 task 修复轮内解决）。

### AC 复验方式

- AC-001：`re_verified`——复跑 `tests/integration/test_api_search_defaults_routes.py` 通过（在本轮 integration 批内），与前轮复核一致。
- AC-002：`re_verified`——convergence/runner 测试复跑通过、Gateway 重解析与同端点重附代码已读；但 f014 表明同实例在 container_exit 记录后周期扫描的收敛整体停摆，本 AC 在该状态序列下不成立。
- AC-003：`re_verified`——`test_t026_address_pool.py` / `test_t026_media_network_adapter.py` 复跑通过，与前轮一致。
- AC-004：`re_verified`——`rebuild_media_network` 代码复读（含 f013 的 role 白名单），适配器测试复跑通过。
- AC-005：`re_verified`——本轮以 reviewer 探针独立复验封堵链：restore 失败 → helper 抛错 → CLI exit 3；apply 回滚 best-effort 未被严格化误伤（探针实测）；core 不标记重试逻辑代码复读无误。本 AC 的「真正封堵」判据现已可靠。
- AC-006：`re_verified`——无 session 离线恢复与前轮一致，相关测试复跑通过。
- AC-007：`trust_prior`——依赖实施侧并发/回滚/未知 endpoint 单测（本轮复跑全过）与 adapter 代码阅读；reviewer 未独立构造真实 Docker 并发场景（本机无 Docker）。
- AC-008：`re_verified`——Gateway 注册集成测试复跑通过；exited/缺失两半现均有预算内的 Stream-only 路由（探针实测）；但修复成功后稳态收敛被 f014 自锁，本 AC 不能按完全成立计。
- AC-009：`re_verified`——control endpoints/client 测试复跑通过；readiness 逐 Profile 隔离已经 reviewer 探针实测（Docker 异常不再 500、诊断落 `readiness_check_failed:<type>`），f009 缺口闭合。
- AC-010：`re_verified`——`test_t026_transport_api.py` 与前端 `sse.transport.test.ts`（4 过）复跑通过；另注 f014 下 transport 会永停 recovering——属 AC-002/008 的收敛自锁后果，观测字段本身的同步无误。
- AC-011：`re_verified`——复跑前端 `useBrowserSession.transportRecovery.test.tsx`（4 过），四态呈现与实现一致。
- AC-012：`trust_prior`——本机无 Docker daemon，按已批准口径只验收集与入口：`--collect-only` 成功收集 2 条用例；实跑义务仍归 t032。

coverage = re_verified 10 / 总 AC 数 12

### reviewer 复跑记录

- `pytest tests/unit -q`（TMPDIR=/tmp，venv 同实施侧）→ 812 passed / 1 skipped（与实施侧 Round 2 后自述一致）
- `pytest tests/unit/test_t026_*.py tests/unit/test_supervisor_schema.py tests/unit/test_api_models_and_sse.py -q` → 68 passed
- `pytest tests/integration/test_t026_gateway_registration.py tests/integration/test_t026_transport_api.py tests/integration/test_api_search_defaults_routes.py -q` → 11 passed
- 前端 `vitest run useBrowserSession.transportRecovery.test.tsx sse.transport.test.ts` → 8 passed
- `pytest tests/e2e/test_supervisor_reconciliation_e2e.py --collect-only -q` → 2 tests collected（本机无 Docker，未实跑）
- Round 3 探针（临时脚本，跑后已删）：f010 严格性 4 断言（rc=1 抛错 / CLI exit 3 / 工具缺失抛错 / apply 回滚仍抛 NetworkPolicyError 且 best-effort 不掩盖）；f003/f011 路由 7 断言（exited 修复、双停零替换、Browser 单停零替换、耗尽回落 container_exit、缺失耗尽零替换 + `stream_missing_budget_exhausted` 诊断、缺失预算内替换、窗口滑动后修复恢复）；f009 readiness 隔离 1 断言；f014 自锁复现 1 组（耗尽置 error → 滑动修复 → 双 running 连扫两轮 `_converge_session` 零调用、transport 停 recovering）

verdict: FAIL

## Round 4 (2026-11-04T10:49:55+08:00)

- round：4
- reviewed_at：2026-11-04T10:49:55+08:00

reviewed_scope: 03f1d9ec3f9a7817

## Findings（本轮新发现，续编）

### t026_code_f015 - f014 锁存释放未同步清除终态去重集：同实例恢复后再次发生的终态事实被永久吞掉，Agent 再报 error 时仍收敛、Browser 再退出时 API 永不知情

- 严重度：important
- 锚点：AC-002（同实例周期扫描须持续做附着/策略/注册检查并如实观测）+ AC-008（容器/Agent 故障须被如实报告而非掩盖）；可观测行为缺陷——恢复后的第二次终态故障被去重逻辑吞掉，本地与 API 观测分叉、健康假象
- 位置：`src/backend/cbrowser/supervisor/core.py:980`-`:992`（f014 释放只改 `session.observed_state`，不动终态去重集）、`:2128`-`:2140` 的 `report_terminal_observation`（key `(profile, instance, config_version)` 在去重集内直接 return False、不再上报）、`:1473` 与 `:1523` 的 `_reconcile_instance_observation`（终态上报被去重时返回 None 而非 `"error"`/`"stopped"`，调用方遂不早退）
- 问题：reviewer 探针实测（生产 `_reconcile_profile` + 生产 `report_terminal_observation`，API 为记录型 MockTransport、Agent 健康可脚本化）：①Stream exited + 预算耗尽 → 真实终态上报 `container_exit`，去重集落入 `(prof, inst_1, 1)`、session 锁存 error；②双 running + Agent 健康 → f014 释放生效、API 收到 `running` 上报、收敛恢复，但去重集仍含该 key（探针直接读出）；③此后 Agent 改报 error 健康（`state=error`）→ 终态上报被去重吞掉、obs 返回 None、锁存不回落、**`_converge_session` 照常被调用**、API 零新上报——Browser 进程已丢失的实例被呈现为健康并继续收敛；④此后 Browser 容器 exited → 本地 session 虽置 error，但 API 零新上报，API 侧永远停在第 ② 步的 `running`，与本地/真实状态分叉。根因：终态去重集的「同代次只报一次」语义以「终态即代次终结」为前提，f014 引入同代次恢复后该前提失效——释放本地锁存时必须同时作废该代次的终态已报记录（或在成功上报 `running` 时清除），实施方只释放了一半状态。Round 3 回归测试把 `report_terminal_observation` 换成无去重语义的记录桩，故测不出此交互。
- 建议：锁存释放（core.py:992 处）时同步 discard 该 `(profile_id, instance_id, config_version)` 的 `_terminal_observations` 记录（config_version 取本轮 `bound_version`/session 一致值），或在 `_report_observed` 成功上报 `running` 时统一清除对应 key；补回归（须走生产 `report_terminal_observation`、不得用无去重桩）：锁存 → 恢复 → Agent 再报 error 时 API 收到 error 上报且不进入收敛；锁存 → 恢复 → Browser 再退出时 API 收到第二次 `container_exit`。

## 结论

- 前轮 finding 复核（Round 3，共 1 条）：
  - t026_code_f014（important）：**本体已消除，修复不完整另立 f015**。释放条件与实施自述一致（core.py:980-992：`obs == "running"` 且 session 同实例且 `observed_state == "error"` 时才释放）。reviewer 独立探针复现 Round 3 三段场景全过：耗尽置 error（terminal=`container_exit`、零替换）→ 窗口滑动后 Stream 仍 exited 时 Stream-only 修复触发且锁存已释放 → 双 running 连扫两轮 `_converge_session` 每轮均调用、session 回 `running`。保护语义未误伤（以生产 `_reconcile_instance_observation` + 可脚本化 Agent 健康实测）：Agent 报 error 健康时 obs 返回 `"error"` 早退、锁存保持、API 收到 `agent_exit` 上报；健康为 None（不可达）时 obs 返回 None、锁存保持、零收敛；身份不匹配时 obs 返回 None、锁存保持；normal-exit 健康时 obs 返回 `"stopped"` 早退、不释放。五项保护断言全过——「Docker running 不得覆盖 Agent 错误观测」成立。但释放未同步清理终态去重集，恢复后的终态事实被吞，见 f015。
  - Round 3 test 路处置的 code 侧旁证：f010/f011 补测文件在本轮 unit 全量 816 passed 内通过；f009 遗留登记 `docs/pending/todo/p035_t026_network_watcher_stop_race_regression_test.md` 已在 diff 中（状态 A），与处置表一致。
- 本轮新发现：1 条（important 1：f015；minor 0）。
- 未进表的提示：
  - 文件过大（降级规则，仅结论提示）：`core.py` 2179 行（Round 3 后再净增约 13 行，仍 ≥800 important 阈值）；`docker_adapter.py` 1723 行；`gateway/server.py` 923 行；`network_policy.py` 482 行、`useBrowserSession.ts` 510 行（≥400 minor 阈值）。f015 与 f014 同出 core.py 同实例状态机：本地锁存、终态去重集、transport 观测三份状态散在同文件多处、靠人工同步，正是本轮缺陷的成因，拆分与状态收敛的建议与前三轮相同。
  - 圈复杂度：`_reconcile_profile` / `report_terminal_observation` 交互面即 f015 的载体，复杂度本身不另出 finding。
  - 安全 / 契约面本轮复扫：锁存释放未触及鉴权、端口、地址分配与 Gateway 协议面；f015 的 API 上报内容仍只含状态与 reason，无敏感信息。未发现新增问题。
- 总体判断：f014 本体按 Round 3 建议的最小方向真实修复、三段场景与 Agent 错误保护经独立探针全过；但其修复只释放了本地 session 锁存，未同步作废同代次终态去重记录，使恢复后的第二次终态故障（Agent error / Browser 再退出）被永久吞掉并呈现健康假象——仍存在未解决 important（f015），FAIL。
- 系统性 follow-up：无（f015 为本 task 范围内缺陷，应在本 task 修复轮内解决）。

### AC 复验方式

- AC-001：`re_verified`——`test_api_search_defaults_routes.py` 在本轮 integration 批内通过，与前轮一致。
- AC-002：`re_verified`——convergence/runner 测试复跑通过，f014 三段探针实测收敛在恢复后重启；但 f015 表明恢复后同实例的后续终态观测被去重吞掉、检查结果失真，本 AC 在该状态序列下仍不完全成立。
- AC-003：`re_verified`——`test_t026_address_pool.py` / `test_t026_media_network_adapter.py` 复跑通过，与前轮一致。
- AC-004：`re_verified`——`rebuild_media_network` 代码与适配器测试复跑通过，与前轮一致。
- AC-005：`re_verified`——fail-closed 严格链与前轮探针结论一致，相关测试在本轮全量内通过。
- AC-006：`re_verified`——无 session 离线恢复测试复跑通过，与前轮一致。
- AC-007：`trust_prior`——依赖实施侧并发/回滚/未知 endpoint 单测（本轮复跑全过）与 adapter 代码阅读；reviewer 未独立构造真实 Docker 并发场景（本机无 Docker）。
- AC-008：`re_verified`——Gateway 注册集成测试复跑通过、exited/缺失 Stream-only 路由与前轮一致；但 f015 下 Agent 在恢复后再报 error 时既不上报也不阻断收敛，本 AC 不能按完全成立计。
- AC-009：`re_verified`——control endpoints/client 与 readiness 隔离测试复跑通过，与前轮一致。
- AC-010：`re_verified`——`test_t026_transport_api.py` 与前端 `sse.transport.test.ts`（4 过）复跑通过；另注 f015 的分叉在 Supervisor→API 上报层（API 根本收不到第二次终态），非 SSE/REST 同步字段丢失。
- AC-011：`re_verified`——复跑前端 `useBrowserSession.transportRecovery.test.tsx`（4 过），与前轮一致。
- AC-012：`trust_prior`——本机无 Docker daemon，按已批准口径只验收集与入口：`--collect-only` 成功收集 2 条用例；实跑义务仍归 t032。

coverage = re_verified 10 / 总 AC 数 12

### reviewer 复跑记录

- `pytest tests/unit -q`（TMPDIR=/tmp，venv 同实施侧）→ 816 passed / 1 skipped（与实施侧 Round 3 后自述一致）
- `pytest tests/unit/test_t026_*.py tests/unit/test_supervisor_schema.py tests/unit/test_api_models_and_sse.py tests/integration/test_t026_*.py tests/integration/test_api_search_defaults_routes.py -q` → 83 passed
- 前端 `vitest run useBrowserSession.transportRecovery.test.tsx sse.transport.test.ts` → 8 passed
- `pytest tests/e2e/test_supervisor_reconciliation_e2e.py --collect-only -q` → 2 tests collected（本机无 Docker，未实跑）
- Round 4 探针（临时脚本，跑后已删）：探针 A 三段场景 3 组断言（耗尽锁存 / 滑动后 exited 修复 / 双 running 连扫收敛 2 次）；探针 B 保护语义 5 断言（Agent error 早退且上报 `agent_exit` / 健康释放且上报 `running` / 健康 None 不释放 / 身份不匹配不释放 / normal-exit 不释放）；探针 C 终态去重交互（恢复后去重集残留、Agent 再报 error 时零上报且照常收敛、Browser 再退出时零上报）——f015 直接证据

verdict: FAIL

## Round 5 (2026-11-04T10:56:34+08:00)

- round：5
- reviewed_at：2026-11-04T10:56:34+08:00

reviewed_scope: 0e454727a9a3ca57

## Findings（本轮新发现，续编）

### t026_code_f016 - 终态去重 key 的 config_version 来源在回落分支与释放点不一致：仅当 API 运行时响应缺 config_version 且标签版本 ≠ session 版本时漏清（当前 API 契约下不可达）

- 严重度：minor
- 锚点：行为缺陷（健壮性 / 状态一致性）——f015 修复的残余耦合面；当前生产契约下无可达失败场景，故不阻断
- 位置：`src/backend/cbrowser/supervisor/core.py:997`-`:999`（释放点 discard 使用 `bound_version`）、`:928`-`:930`（`bound_version = int(rt.get("config_version", b_c.get("config_version", 1)))`，回落到容器标签）、`:1024`-`:1032`（同实例 container_exit 回落写入 key 时使用 `int(rt.get("config_version", session.config_version))`，回落到 session 版本）；对照 `src/backend/cbrowser/supervisor/recovery_coordinator.py:213`-`:217`（标签优先、runtime 次之，第三种来源顺序）
- 问题：reviewer 探针 B 实测（生产 `_reconcile_profile` + 生产 `report_terminal_observation`，记录型 API）：构造 rt 不含 `config_version`、session 版本 1、容器标签版本 3 时——锁存写入 key `(pid, inst, 1)`（回落分支取 session 版本），释放时 discard `(pid, inst, 3)`（bound 取标签版本）未命中，Stream 再退出时第二次 `container_exit` 被残留 key 吞掉（API 仍只收到 1 次）。但该场景在当前生产契约下不可达：内部 runtime 端点的 `response_model=ProfileRuntimeResponse` 的 `config_version: int` 为必填字段（`src/backend/cbrowser/domain/models.py:523`，路由绑定见 `src/backend/cbrowser/api/internal_supervisor.py:73`-`:77`），200 响应必含该字段，此时 bound、回落写入与 `_reconcile_instance_observation` 三处取同一 rt 值、完全一致；且 session 版本与容器标签版本同源于启动时的同一 config_version（bind 与标签写入同值）。其余写入点亦已逐一核对一致：`consume_disk_events` 的事件版本、RecoveryCoordinator 的 `_compensate_missing_runtime`（runtime 来源，`recovery_coordinator.py:315`）与 Docker-exit 路径（标签 = 启动版本）在生产语义下均与 bound 相等。探针 A（rt 含 config_version 的生产形状）五段断言全过，见结论。
- 建议：把释放点的 discard 改为按 `(profile_id, instance_id)` 前缀清除该代次全部终态 key（与 `forget_instance_events` 在 `core.py:1325`-`:1329` 的既有做法同构），彻底消除对 config_version 来源一致性的隐含依赖；成本一行级，防止未来 API 响应形状或版本来源变化时 f015 复发。

## 结论

- 前轮 finding 复核（Round 4，共 1 条）：
  - t026_code_f015（important）：**已消除（生产路径）**。修复与处置自述一致：释放点（core.py:996-999）在置 `session.observed_state = "running"` 的同时 `discard((pid, b_inst, bound_version))`，注释明示 f015 语义。reviewer 独立探针 A 复现 Round 4 探针 C 全场景（生产 `_reconcile_profile` + 生产 `_reconcile_instance_observation` + 生产 `report_terminal_observation`，仅 Agent 健康与 `_converge_session` 可脚本化、API 为记录型 MockTransport）：①Stream exited + 预算耗尽 → 锁存 error、API 收到 `container_exit` ×1、key 落集；②双 running + Agent 健康 → 锁存释放、key 已清除、收敛恢复调用；③Agent 改报 error 健康 → API 收到新的 `agent_exit` 上报、obs 返回 `"error"` 早退、**不再进入收敛**（Round 4 的健康假象消除）；④再次健康 → 第二次锁存（③中由生产 report_terminal 落下）同样释放、收敛恢复、key 清除；⑤Browser 再退出 → API 收到第二次 `container_exit`（累计 ×2），不再被去重吞掉。五段断言全过。回归测试亦已按处置自述重写并复跑通过：`test_latched_container_exit_error_releases_on_authoritative_running` 走生产 `report_terminal_observation` + 记录型 API、三段断言含 key 清除与 `container_exit` 共 2 次（`tests/unit/test_t026_supervisor_convergence.py:880`-`:970`）。key 构成全路径核查：写入点唯一在 `report_terminal_observation`（core.py:2136-2147），全部调用方的 config_version 来源逐一核对（见 f016），生产契约下与 discard 的 bound_version 恒一致；仅回落分支的防御性 fallback 来源不对称在不可达条件下漏清，另立 minor f016。
- 本轮新发现：1 条（minor 1：f016；critical / important 0）。
- 未进表的提示：
  - 文件过大（降级规则，仅结论提示）：`core.py` 2186 行（Round 4 后再净增约 7 行，仍 ≥800 important 阈值）；`docker_adapter.py` 1723 行；`gateway/server.py` 923 行；`network_policy.py` 482 行、`useBrowserSession.ts` 510 行（≥400 minor 阈值）。与前四轮提示相同，不另出 finding。
  - 圈复杂度：本轮 delta 仅释放点 3 行，无新增分支；既有长函数复杂度提示与前轮相同，其可观测缺陷（f014/f015）均已闭合。
  - 安全 / 契约面本轮复扫：本轮 delta（core.py discard + 回归测试重写）未触及鉴权、端口、地址分配、Gateway 协议与上报内容；全 diff 的安全/契约结论与前四轮一致，未发现新增问题。
  - 流程说明：本轮为 review 上限内末轮（Round 5/5）；f016 为 minor，按规则由 implementer 写入 note.md 处置表，不阻断本轮 PASS。
- 总体判断：Round 4 唯一未解决 important（f015）已经 reviewer 独立探针在生产路径上确认消除，f014/f015 的锁存-去重交互闭环；本轮仅新增 1 条生产不可达的 minor（f016）——无未解决 critical / important，PASS。
- 系统性 follow-up：无（f016 为本 task 范围内 minor，按处置表流程处理即可，不另立 follow-up）。

### AC 复验方式

- AC-001：`re_verified`——`test_api_search_defaults_routes.py` 在本轮 integration 批内通过，与前轮一致。
- AC-002：`re_verified`——convergence/runner 测试复跑通过，且探针 A 实测同实例在 container_exit 锁存→恢复→再终态全序列下收敛与观测均如实工作，Round 4 指出的状态序列缺口闭合。
- AC-003：`re_verified`——`test_t026_address_pool.py` / `test_t026_media_network_adapter.py` 在本轮 unit 全量内通过，与前轮一致。
- AC-004：`re_verified`——`rebuild_media_network` 与适配器测试在本轮 unit 全量内通过，与前轮一致。
- AC-005：`re_verified`——fail-closed 严格链相关测试在本轮 unit 全量内通过，与前轮探针结论一致。
- AC-006：`re_verified`——无 session 离线恢复测试在本轮 unit 全量内通过，与前轮一致。
- AC-007：`trust_prior`——依赖实施侧并发/回滚/未知 endpoint 单测（本轮全量复跑全过）与 adapter 代码阅读；reviewer 未独立构造真实 Docker 并发场景（本机无 Docker）。
- AC-008：`re_verified`——Gateway 注册集成测试本轮复跑通过；探针 A ③⑤实测恢复后 Agent 再报 error 与 Browser 再退出均被如实上报且阻断收敛，本 AC 现可按完全成立计。
- AC-009：`re_verified`——control endpoints/client 与 readiness 隔离测试在本轮批次内通过，与前轮一致。
- AC-010：`re_verified`——`test_t026_transport_api.py` 与前端 `sse.transport.test.ts`（4 过）本轮复跑通过。
- AC-011：`re_verified`——复跑前端 `useBrowserSession.transportRecovery.test.tsx`（4 过），与前轮一致。
- AC-012：`trust_prior`——本机无 Docker daemon，按已批准口径只验收集与入口：`--collect-only` 成功收集 2 条用例；实跑义务仍归 t032。

coverage = re_verified 10 / 总 AC 数 12

### reviewer 复跑记录

- `pytest tests/unit -q`（TMPDIR=/tmp，venv 同实施侧）→ 816 passed / 1 skipped
- `pytest tests/unit/test_t026_supervisor_convergence.py tests/integration/test_t026_gateway_registration.py tests/integration/test_t026_transport_api.py tests/integration/test_api_search_defaults_routes.py -q` → 40 passed（含重写的 f014/f015 三段回归）
- 前端 `vitest run useBrowserSession.transportRecovery.test.tsx sse.transport.test.ts` → 8 passed
- `pytest tests/e2e/test_supervisor_reconciliation_e2e.py --collect-only -q` → 2 tests collected（本机无 Docker，未实跑）
- Round 5 探针（临时脚本，跑后已删）：探针 A（生产路径，rt 含 config_version）5 段断言全过——锁存+首报 ×1 / 释放+key 清除+收敛恢复 / Agent 再报 error 收到 `agent_exit` 且不收敛 / 二次锁存再释放 / Browser 再退出 `container_exit` 累计 ×2；探针 B（rt 缺 config_version 且标签版本 ≠ session 版本）复现 fallback 来源不对称的漏清，生产契约下不可达，另立 minor f016

verdict: PASS

## Evidence Repair (2026-11-04T11:05:25+08:00)

- reviewed_at：2026-11-04T11:05:25+08:00

reviewed_scope: cf4c2cbdec3d4182

## Findings（本轮新发现）

无。本轮对全 diff（`git diff c2bd696..3ac6777`，63 文件）做代码质量 / 安全 / 契约面复扫，未发现前轮遗漏的 critical / important，亦无新 minor；f017 起的编号本轮未启用。

## 结论

- 前轮 finding 复核（Round 1–5，共 f001–f016；全部以当前 tip 已提交代码独立核实，不采信处置表自述）：
  - t026_code_f001（critical）：**已消除**。生产 `DockerAdapter.get_profile_containers` 存在（`src/backend/cbrowser/supervisor/docker_adapter.py:1642`，按确定名取容器 + prefix/profile-id/role 标签核验、外国与缺失读作 None）；reviewer 实测 `hasattr(DockerAdapter, 'get_profile_containers') == True`、`hasattr(DockerAdapter, 'rebuild_media_network') == True`。
  - t026_code_f002（important）：**已消除**。`_replace_stream_only` 先 `_resolve_gateway_id`、为 None 时只落 `gateway_missing` recovering 观测并 return False，预算记录与一切拆动都在其后（`src/backend/cbrowser/supervisor/core.py:519`-`:545` 段，Gateway 解析位于函数入口）。
  - t026_code_f003（important，含 Round 2 残余）：**已消除**。Stream 缺失路由（core.py:935 起）与 exited-Stream 路由（core.py:1006 起）均在同实例 + Browser running 前提下走 Stream-only 替换，双停 / Browser 单停不触发。
  - t026_code_f004（important）：**已消除**。core.py:413-436：`fail_close_container` 成功后才 `self._policy_fail_closed.add(key)` 并置 failed 态；失败落 `browser_policy_drift_unmitigated`（recovering）并下轮重试。
  - t026_code_f005（important）：**已消除**。`_recover_attachment_offline` 在无 session 时以调用点传入的 `scan_instance_id`（扫描标签已核验的 `b_inst`）为实例依据完成附着（core.py:625 起）。
  - t026_code_f006（important）：**已消除**。readiness policy 分支要求双容器均非 None 才校验，缺失时落 `policy=None` + `policy_unverifiable`（core.py:770 起）。
  - t026_code_f007（minor）：**已消除**。inspect 失败落 `media_inspect_failed`、attach 失败落 `media_attach_failed`（均为 failed + `last_error_at`，core.py:310 与 :355 附近），与 policy 分支同构。
  - t026_code_f008（minor）：**已消除**。网络事件流登记进 `_close_stream_sync` 的统一关闭集（`src/backend/cbrowser/supervisor/runner.py:213`-`:221`、`:287` 起）。
  - t026_code_f009（important）：**已消除**。`readiness()` 对 `_profile_readiness` 加逐 Profile 兜底，任一异常落 `readiness_check_failed:<type>` 的 not-ready 条目、诊断只含异常类型名（core.py:710-724 段）。
  - t026_code_f010（important）：**已消除，且未误伤 apply 路径**。显式入口 `install_fail_closed()` 为严格实现：任一 family restore returncode 非 0 或不可执行即抛 `NetworkPolicyError`（`src/backend/cbrowser/supervisor/network_policy.py:381`-`:419`）；best-effort 的 `_install_fail_closed`（network_policy.py:252）只保留给 apply 失败回滚。
  - t026_code_f011（important）：**已消除**。全部 Stream-only 替换入口均先查同一 `_stream_replacement_allowed`（core.py:321、:384、:487、:942、:1012），缺失路由耗尽落 `stream_missing_budget_exhausted` 并 return。
  - t026_code_f012（minor）：**已消除**。网络 watcher 登记流后立即复查 `stop_event`，已置位则 `_close_stream_sync()` 自行关流并 return（runner.py:295-303）。
  - t026_code_f013（minor）：**已消除**。`rebuild_media_network` 端点核验含 role ∈ {browser, stream, gateway} 白名单，与 cleanup 准入对齐，未知 role 在任何拆动前抛错拒绝（docker_adapter.py:866-880）。
  - t026_code_f014（important）：**已消除**。同实例块在 `_reconcile_instance_observation` 返回 `"running"` 且 session 同实例且 observed 为 `"error"` 时复位 `session.observed_state = "running"`（core.py:980-999），收敛门随之恢复；Agent 错误 / 健康未知在上游早退、不被 Docker running 覆盖的保护语义未动。
  - t026_code_f015（important）：**已消除**。锁存释放点同步 `self._terminal_observations.discard((pid, b_inst, bound_version))`（core.py:996-999），同代次后续终态事实可再次上报。
  - t026_code_f016（minor）：**定性成立，同意遗留 p036**。释放点 discard 用 `bound_version`（回落容器标签，core.py:928-930 与 :997-999），container_exit 回落写入用 session 版本（core.py:1024-1032），来源不对称属实；但 `ProfileRuntimeResponse.config_version: int` 为必填（`src/backend/cbrowser/domain/models.py:523`），200 响应必含该字段、三处恒取同一 rt 值，生产契约下漏清不可达——minor 不阻断，遗留项 `docs/pending/todo/p036_t026_terminal_observation_dedupe_prefix_discard.md` 已存在且与 note.md 处置表一致。
- 本轮新发现：0 条。
- 代码差异核查：本轮所审内容与 Round 5 所审代码零差异——关键文件行数与 Round 5 结论记录逐一相同（`src/backend/cbrowser/supervisor/core.py` 2186 行、`docker_adapter.py` 1723 行、`gateway/server.py` 923 行、`network_policy.py` 482 行、`useBrowserSession.ts` 510 行），指纹变化源于归档后 scope 重绑定，非代码变更。
- 未进表的提示：
  - 文件过大（降级规则，仅结论提示）：同上五文件行数，core.py / docker_adapter.py / gateway/server.py ≥800、network_policy.py / useBrowserSession.ts ≥400，与前五轮提示相同，不另出 finding。
  - 安全 / 契约面复扫：地址池分配耗尽显式抛 `MediaPoolExhaustedError`、不回退随机地址（`src/backend/cbrowser/supervisor/address_pool.py:100`）；Gateway 拒绝与上报不含凭证；reconcile_all / readiness 仍只经内部 token + 容器内 CLI、无新增发布端口。未发现新增问题。
- 总体判断：Round 1–4 全部 code finding（f001–f015）在最终提交内容中经独立核实确已消除；Round 5 结论与 f016（minor、生产不可达、已遗留 p036）的定性成立；本轮复扫无新 critical / important——PASS。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：`re_verified`——本轮复跑 `tests/integration/test_api_search_defaults_routes.py` 通过（在下方 80 项批次内），夹具绑定与异实例负例与前轮一致。
- AC-002：`re_verified`——convergence / runner 事件测试本轮复跑通过；同实例锁存→释放→收敛恢复的代码路径已逐段复读（core.py:975-1055）。
- AC-003：`re_verified`——`test_t026_address_pool.py` / `test_t026_media_network_adapter.py` 本轮复跑通过；地址池校验与耗尽抛错代码已读。
- AC-004：`re_verified`——`rebuild_media_network` 代码复读（含 f013 的 role 白名单），适配器测试本轮复跑通过。
- AC-005：`re_verified`——policy verify 与 fail-closed 严格链相关测试本轮复跑通过，严格入口代码已逐行读。
- AC-006：`re_verified`——无 session 离线恢复代码复读（`scan_instance_id` 回落）与相关测试本轮复跑通过。
- AC-007：`trust_prior`——依赖实施侧并发 / 回滚 / 未知 endpoint 单测（本轮复跑全过）与 adapter 代码阅读；reviewer 未独立构造真实 Docker 并发场景（本机无 Docker）。
- AC-008：`re_verified`——Gateway 注册集成测试本轮复跑通过；缺失 / exited 两半的预算内 Stream-only 路由与 Gateway 缺失零拆动代码已复读。
- AC-009：`re_verified`——control endpoints / client 测试本轮复跑通过；readiness 逐 Profile 异常隔离代码已复读。
- AC-010：`re_verified`——`test_t026_transport_api.py` 与前端 `sse.transport.test.ts`（4 过）本轮复跑通过。
- AC-011：`re_verified`——本轮复跑前端 `useBrowserSession.transportRecovery.test.tsx`（4 过），四态呈现与前轮一致。
- AC-012：`trust_prior`——本机无 Docker daemon，按已批准口径只验收集与入口：`--collect-only` 成功收集 2 条用例；实跑义务仍归 t032。

coverage = re_verified 10 / 总 AC 数 12

### reviewer 复跑记录

- `pytest tests/unit/test_t026_supervisor_convergence.py tests/unit/test_t026_media_network_adapter.py tests/unit/test_t026_network_policy_verify.py tests/unit/test_t026_address_pool.py tests/unit/test_t026_control_endpoints.py tests/unit/test_t026_control_client.py tests/unit/test_t026_runner_network_events.py tests/unit/test_supervisor_schema.py tests/integration/test_t026_gateway_registration.py tests/integration/test_t026_transport_api.py tests/integration/test_api_search_defaults_routes.py -q`（TMPDIR=/tmp，venv 同实施侧）→ 80 passed
- 前端 `vitest run useBrowserSession.transportRecovery.test.tsx sse.transport.test.ts` → 8 passed
- `pytest tests/e2e/test_supervisor_reconciliation_e2e.py --collect-only -q` → 2 tests collected（本机无 Docker，未实跑）
- `hasattr(DockerAdapter, 'get_profile_containers')` / `hasattr(DockerAdapter, 'rebuild_media_network')` → 均 True（f001 直接复核证据）
- `git diff c2bd696..3ac6777 --stat` → 63 files changed, 6714 insertions(+), 106 deletions(-)，与 Round 5 所审 diff 规模一致；工作区干净

verdict: PASS
