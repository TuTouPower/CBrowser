# Task review t082（reviewer_focus: 代码）

- task：`t082_persistent_namespace_policy_agents`
- spec：`docs/tasks/t082_persistent_namespace_policy_agents/task.md`
- diff_anchor：`c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- target：`git diff c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- round：1
- reviewed_at：2026-11-18T13:42:04+08:00

reviewed_scope: 42050fd46c1a37fa

## Findings

### t082_code_f001 - 本机制暂停的 Browser 在真实收敛接线下永远无法恢复（resume 分支不可达）

- 严重度：important
- 锚点：AC-008。AC 要求隔离后「只恢复本机制隔离且仍为当前运行意愿的实例」——恢复能力本身是契约行为；实现中恢复分支存在但生产路径永不调用，隔离即永久停机（只能靠用户停/启 Profile 重建），且观测被误报为 container_exit。
- 位置：`src/backend/cbrowser/supervisor/core.py:1637`（调用门禁）、`src/backend/cbrowser/supervisor/core.py:834`（不可达的恢复分支）、`src/backend/cbrowser/supervisor/docker_adapter.py:3289`（scan 状态透传）
- 问题：`_isolate_browser` 经 `pause_container` 暂停目标后（core.py:562-575），Docker 对该容器的状态报告为 `paused`，scan 原样透传（docker_adapter.py:3289 `"status": c.status`）。生产环境中 `_converge_session` 只有两个调用点：其一在同代会话分支末尾，要求 `session.observed_state == "running"` 且 browser/stream 两个 scan 状态均为 `"running"` 才调用（core.py:1637-1641）；暂停后的 scan 在此之前已因「任一状态 != running」把会话标为 error 并上报 `container_exit`（core.py:1603-1625），随后直接 return。另一调用点是无会话时的恢复路径（core.py:1793），同样被前置的「desired=running 且任一状态 != running → 上报后 return」挡住（core.py:1643-1653）。因此 `_converge_session` 内 `_policy_paused` 命中后调 `_attempt_policy_resume` 的分支（core.py:834-841）在真实接线下不可达：规则复验通过也不会 unpause。单元测试未发现此缺口的原因是其 scan 字典恒报双 `"running"`（tests/unit/test_t082_supervisor_policy_convergence.py:169-172 的 `_make_core` 构造），且 `pause_container` 替身只记录调用、不改变 scan 状态，测试绕过了 scan 门禁直接驱动 `_converge_session`。附带问题：`_policy_paused` 仅存内存（core.py:303），Supervisor 重启后所有权记录丢失，同一缺口在重启场景下同样成立。
- 建议：让收敛入口识别本机制暂停目标——例如在同代分支中，当 (profile, instance) 在 `_policy_paused` 内且 browser 状态为 `paused` 时仍进入 `_converge_session` 走恢复分支（或在 scan 门禁前先处理暂停恢复），并补一条经 `scan_and_reconcile_existing` 全链路、scan 状态真实为 `paused` 的回归测试；重启后所有权可由容器 paused 状态 + 规则复验结果重建，或明确登记为已知限制并写入 ADR。

### t082_code_f002 - ADR 编号在交付物内不一致（031 vs 039）

- 严重度：minor
- 锚点：行为缺陷（文档与规格一致性）。决策文件本体与 blueprint 均为 ADR 039，但多处源码注释与 pending 指向不存在的 ADR 031，后续按注释查证会落空。
- 位置：`src/backend/cbrowser/supervisor/policy_agent.py:1`、`src/backend/cbrowser/supervisor/policy_agent_protocol.py:4`、`src/backend/cbrowser/supervisor/network_policy.py:7`、`src/backend/cbrowser/supervisor/container_spec.py:215`、`src/backend/cbrowser/supervisor/docker_adapter.py:311`、`src/backend/cbrowser/supervisor/storage_layout.py:25`、`docs/pending/p132_verify_t082_policy_agent_spikes_locally.md`（正文「回填 findings/ADR 031」）
- 问题：上述位置写 `ADR 031`，而 `docs/blueprint/decisions/20261118_namespace_policy_agent.md` 标题与 architecture/supervisor/security 三处 blueprint 均为 ADR 039；仓内无 ADR 031 的该决策文件。
- 建议：统一改为 ADR 039（含 p132 正文）。

### t082_code_f003 - 一次性 helper 退役后遗留未用 import

- 严重度：minor
- 锚点：行为缺陷（死代码）。临时 policy helper 整体删除后，适配器仍导入其标签函数但模块内再无任何使用点。
- 位置：`src/backend/cbrowser/supervisor/docker_adapter.py:58`
- 问题：`policy_helper_labels` 被导入后在本模块零引用（全仓仅剩 container_spec.py:195 的定义与 tests/unit/test_t050_sandbox_grouping.py 对定义的直接测试）。属本 task 删除面未清干净的残留。
- 建议：删除该 import；`policy_helper_labels` 定义本身若无其他生产消费者，可一并评估退役（其标签契约测试是否保留由实施侧决定）。

### t082_code_f004 - Agent resolve 回执地址未做 IP 字面量校验，畸形回执以未类型化异常逃逸

- 严重度：minor
- 锚点：行为缺陷（健壮性/错误类型一致性）。旧 `_resolved_endpoint` 对 exec 解析结果逐个 `ipaddress.ip_address` 校验并统一映射为 `DockerSandboxError("Invalid runtime DNS response")`；新路径丢失该校验与错误类型。
- 位置：`src/backend/cbrowser/supervisor/policy_agent_client.py:139`（`resolve` 仅判 list 非空、逐项 `str()` 透传）、`src/backend/cbrowser/supervisor/docker_adapter.py:860`（`_resolve_via_agent` 原样返回）
- 问题：若 Agent 回执含非 IP 字符串（Agent 故障/版本错位/回执损坏），Browser 路径要到 `NetworkPolicySpec.model_validate`（docker_adapter.py `_policy_from_egress_plan`）才以 pydantic `ValueError` 失败——该异常不是 `DockerSandboxError`，readiness 的 policy 检查（core.py 只捕 `DockerSandboxError` 记 `policy_verify_unavailable`）与收敛的浏览器 spec 派生（core.py:831 未包 try）都不会把它归一为策略不可用语义，而是向上逃逸为未类型化错误。生产 Agent 的 executor 自身用 `ipaddress` 过滤，故触发面限于故障回执，但这正是该校验原本存在的目的。
- 建议：在 `PolicyAgentClient.resolve` 内逐项校验 IP 字面量，畸形即抛 `PolicyAgentUnavailable`，恢复旧路径的失败语义。

## 结论

- 本轮新发现：4 条（important 1、minor 3）
- 未进表的提示：文件过大（按降级规则只列示）——`src/backend/cbrowser/supervisor/docker_adapter.py` 3301 行、`src/backend/cbrowser/supervisor/core.py` 3478 行，两者均为存量超 800 行文件且本 task 仍有净增（适配器约 +500 行、core 约 +180 行）；新建文件均未超阈值（policy_agent.py 297 行，t082 测试文件 ≤359 行）。圈复杂度：本 task 新增/修改函数手算均未达 15，无复杂度 finding。未知契约：task.md 仍留两项 `UNVERIFIED-SPIKE` 标记，按用户 2026-11-18 裁定与契约区处置注记处理——注记属实、p132 登记内容具体（两项 spike 的实证项与否定假设时的停扩权口径齐全），本报告据修订后契约判定，不把注记当作已实测证据，相关内核能力（仅 NET_ADMIN 的完整策略/DNS、pause 冻结负例）仍待 p132 本地实证。安全面已扫：协议请求全等身份校验、64 KiB 上限、extra=forbid、resolve 仅裸 hostname/port、Agent 仅 NET_ADMIN/只读根/单一 slot 挂载、业务容器不挂 UDS，均与契约一致（f004 为校验深度问题，非注入面）。
- 总体判断：常驻 Agent 替换、修订围栏、冻结派生、漂移封闭与隔离主体实现真实且经复跑验证，但机制暂停后的恢复在生产 scan 接线下不可达（f001），AC-008 打勾不成立，FAIL。
- 系统性 follow-up：无（f001 为本 task 内修复项，不另开 follow-up）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。复跑 test_t082_adapter_policy_agents：启动先建 Agent 并经其 install 修订 1 后才写 gate ready，policy 镜像缺失时启动失败不放行。
- AC-002：TICK-VALID，re_verified。复跑 test_repeated_verification_creates_and_execs_nothing：5 轮 verify 零容器创建、零 exec（替身 exec_run 为 tripwire）、零新增 DNS 解析，inspect 在 Agent 内执行。
- AC-003：TICK-VALID，re_verified。复跑 test_t082_policy_agent 协议测：身份任一字段不符全 op 拒绝、旧修订重放与同修订异 spec 返回 stale_revision、超大/畸形/夹带 command 字段请求被拒、resolve 注入形 hostname 校验失败。
- AC-004：TICK-VALID，trust_prior。创建参数已在适配器测中复验（cap_add 仅 NET_ADMIN、read_only、network_mode=container:\<目标 ID>、唯一挂载为自身 slot 目录、业务容器 cap_drop ALL 不挂 UDS）；「仅 NET_ADMIN 即可在真实 netns 完成安装/查询/封闭」属延期 spike，依赖 p132 本地实证，未在云端实测。
- AC-005：TICK-VALID，re_verified。复跑冻结派生与刷新测：上游未变零 DNS、上游变化走 resolve→install 新修订（replace），刷新失败保留旧冻结 spec 与旧修订且旧 spec 仍可 verify。
- AC-006：TICK-VALID，re_verified。复跑收敛测：Browser 漂移先 fail_close（Agent 确认双栈 DROP 后才算数），fail-close 未确认即在同一收敛遍内 pause 精确目标并记所有权，不删除数据、不重建。
- AC-007：TICK-VALID，re_verified。复跑 stream 侧收敛测：Stream 不可确认超预算只走 Stream-only 有界替换（\_stream_replacement_allowed 既有预算），断言 Browser 未被 pause/fail-close/重建。
- AC-008：TICK-VOID，re_verified。隔离与所有权记录实现属实，但恢复分支在真实 scan 接线下不可达（见 t082_code_f001：paused 状态被 core.py:1637/1643 的 all-running 门禁挡在 \_converge_session 之外，测试以恒 running 的 scan 字典绕过门禁），复验通过后恢复当前实例的行为未真实交付。
- AC-009：TICK-VALID，re_verified。复跑接管与孤儿测：第二适配器凭标签全等 + health 身份回显接管同一 Agent（零新建），目标消失才清孤儿；客户端校验 response request_id，迟到/错位回执不被采用；Agent 事件经 runner 定点修复不触发全量扫描（policy_agent_event_profile 与 \_CONVERGENCE_ROLES 不含 agent 角色已查）。
- AC-010：TICK-VALID，trust_prior。按用户 2026-11-18 裁定判定：task.md 契约区处置注记属实存在、p133 登记内容具体（10 分钟零 churn 计数口径与三类故障窗口正负例齐全），云端可做部分（实现 + e2e 三文件改由真实 PolicyAgentClient 驱动、7 测可收集）已复核；真实部署验证未在云端执行，不作已实测认定，待 p133 本地补验。

coverage = 8 / 10

verdict: FAIL

## Round 2 (2026-11-18T14:12:50+08:00)

- task：`t082_persistent_namespace_policy_agents`
- spec：`docs/tasks/t082_persistent_namespace_policy_agents/task.md`
- diff_anchor：`c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- target：`git diff c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- round：2

reviewed_scope: 904bf1a0d355ebc1

## Findings

### t082_code_f005 - Supervisor 重启后的暂停所有权重登记是死代码，重启场景恢复仍不可达（f001 修不彻底）

- 严重度：important
- 锚点：AC-008。AC 要求本机制隔离后只恢复仍为当前运行意愿的实例；第 1 轮 f001 的附带问题正是「\_policy_paused 仅存内存，Supervisor 重启后所有权记录丢失，同一缺口在重启场景下同样成立」。本轮声称的重启修复（scan 到 paused Browser 时重登记所有权）在生产接线下不可达，重启后被本机制暂停的 Browser 仍永远不会恢复。
- 位置：`src/backend/cbrowser/supervisor/core.py:1664`（先行 return 的门禁）、`src/backend/cbrowser/supervisor/core.py:1813`（不可达的重登记）、`src/backend/cbrowser/supervisor/core.py:1821`（不可达的所有权写入）
- 问题：`_reconcile_profile` 在无同代会话（Supervisor 重启后 `_sessions` 为空）时，先命中 core.py:1664 的门禁——desired=running 且任一容器状态 != running（paused 即满足）→ 以 `container_exit` 上报终态观测并 return。重登记代码位于其后的 restore 分支（core.py:1813-1821），而 restore 分支只在「desired != stopped 且未被 1664 门禁拦截」时进入，对 desired=running 而言进入条件是双容器全 running，此时 `b_c.get("status") == "paused"` 恒为假——该分支对 paused 目标结构性不可达。reviewer 以探针实证（复用 t082 测试替身、无会话无 `_policy_paused` 记录、scan 报 browser=paused/stream=running、API desired=running 驱动 `_reconcile_profile`）：reconcile 直接返回，`_policy_paused` 仍为空、adapter 无任何调用、无会话被创建。交付测试中亦无重启场景用例：`test_reconcile_routes_paused_browser_to_verified_resume` 预置了同代会话与 `_policy_paused` 记录，只覆盖同进程路径。附带地，该重登记的依据本身（「本系统内只有本机制会 pause Browser」）经全仓核查成立（`pause_container` 唯一调用点为 `_isolate_browser`，产品 API 只有 running/stopped 意愿、无用户 pause 入口），问题纯粹是接线不可达，不是依据错误。
- 建议：把 paused 所有权重登记/路由前移到 1664 门禁之前（无会话时先判 browser 状态为 paused 且 stream 同实例 → 登记所有权并走 restore+收敛的复验恢复路径），并补一条无会话、无内存记录、scan 真实报 paused 的接线级回归测试；或若决定不做重启恢复，删除死代码并把限制明确写进 ADR 039 与 AC-008 处置口径，不得保留声称已修的不可达分支。

### t082_code_f006 - 本机制暂停期间 Stream 退出后整对陷入无修复路径

- 严重度：minor
- 锚点：行为缺陷。复合故障场景：Browser 已被本机制暂停隔离期间 Stream 容器退出——不属于任何单条 AC 的正例，但新暂停路由改变了该场景的既有修复路径。
- 位置：`src/backend/cbrowser/supervisor/core.py:1613`（暂停路由条件）、`src/backend/cbrowser/supervisor/core.py:1630`（Stream 替换条件）、`src/backend/cbrowser/supervisor/core.py:1640`（终态上报）
- 问题：同代分支中暂停路由要求 stream 状态为 running（core.py:1613-1617），Stream-only 替换要求 browser 状态为 running（core.py:1630-1633）；browser=paused 且 stream=exited 时两条都不命中，只剩把整对上报 `container_exit` 错误（core.py:1640-1647），且 session 已进入 error 后续扫描重复同一分支，既不替换 Stream 也不进入收敛复验 Browser，整对停滞至人工干预。单故障场景不受影响（暂停路由对真实 exited/dead 状态不误吞，已核对：路由只认精确 `paused` 且须有本机制记录）。
- 建议：暂停路由命中但 stream 非 running 时，至少先走 Stream-only 替换或把 Stream 修复排入收敛前置步骤；或在处置表中明确登记该复合故障为已知限制。

## 结论

- 前轮 finding 复核：f001 修不彻底——同进程主路径已真实修复（同代分支在误报前先判 `_policy_paused` 记录 + browser=paused + stream=running → 直入 `_converge_session`，core.py:1613-1625；`_converge_session` 暂停分支加 desired=running 围栏，core.py:834-848，desired 已变则永不恢复；新增接线级测试经 `_reconcile_profile` 全链路驱动且断言无 container_exit 终态报告，reviewer 复跑通过），但重启场景的所有权重登记为死代码（见 f005），f001 的附带问题未消除。f002 已消除：t082 全部源码注释（policy_agent.py:1、policy_agent_protocol.py:4、network_policy.py:7、container_spec.py:215、docker_adapter.py:310、storage_layout.py:25）与 p132 正文均统一为 ADR 039，仓内其余 ADR 031 均为 t054 既有引用、与本 task 无关。f003 已消除：docker_adapter.py 中 `policy_helper_labels` 导入已删除，全仓仅剩 container_spec.py:195 定义与 t050 对定义的直接测试，模块导入链经全部复跑套件验证正常。f004 已消除：`PolicyAgentClient.resolve`（policy_agent_client.py:128-148）逐项以 `ipaddress.ip_address` 校验回执地址、归一化后返回，畸形回执抛 `PolicyAgentUnavailable`，新增 `test_client_resolve_rejects_non_ip_receipts` 复跑通过，`_resolve_via_agent` 的消费路径失败语义恢复为类型化错误。
- 本轮新发现：2 条（important 1、minor 1）
- 未进表的提示：文件过大（按降级规则只列示）——`src/backend/cbrowser/supervisor/core.py` 3508 行、`src/backend/cbrowser/supervisor/docker_adapter.py` 3300 行，均为存量超 800 行文件且本 task 仍有净增，同第 1 轮。圈复杂度：本轮修复新增/修改分支手算均未达 15，无复杂度 finding。未知契约：task.md 两项 UNVERIFIED-SPIKE 仍按用户 2026-11-18 裁定与处置注记处理、p132 登记具体，不作已实测认定（同第 1 轮口径）。安全面复扫修复面：暂停路由只认精确 paused 状态 + 本机制内存记录，不误吞真实 container_exit；desired 围栏位于收敛恢复分支内、非仅调用方口头保证；resolve 校验位于客户端单点、全部消费方共用，无绕过路径。
- 总体判断：f002/f003/f004 真实修复，f001 同进程恢复主路径真实修复且测试已改为接线级驱动；但 Supervisor 重启后的恢复仍不可达且留有声称已修的死代码（f005），AC-008 打勾仍不完全成立，FAIL。
- 系统性 follow-up：无（f005/f006 均为本 task 内修复项）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。复跑 test_t082_adapter_policy_agents 与 test_t082_policy_agent 全套通过：启动先建 Agent 并经其 install 后才写 gate ready，失败不生成 ready 标记。
- AC-002：TICK-VALID，re_verified。复跑零 churn 测：多轮 verify 零容器创建、零 exec，inspect 在 Agent 内执行，目标不变 Agent 不重建。
- AC-003：TICK-VALID，re_verified。复跑协议测：身份字段不符全 op 拒绝、旧修订重放返回 stale_revision、超大/畸形/注入形请求被拒；本轮身份伪造参数化已扩展至 6 字段 × 5 op。
- AC-004：TICK-VALID，trust_prior。创建参数已在适配器测中复验（Agent 仅 NET_ADMIN/只读根/单一 slot 挂载、业务容器 cap_drop ALL 不挂 UDS）；「仅 NET_ADMIN 即可在真实 netns 完成安装/查询/封闭」属延期 spike，依赖 p132 本地实证，未在云端实测。
- AC-005：TICK-VALID，re_verified。复跑冻结派生与刷新测：上游未变零 DNS、上游变化走 resolve→install 新修订，刷新失败保留旧冻结 spec 与旧修订；本轮 resolve 回执 IP 校验（f004 修复）已在客户端单点落地并复跑其拒绝测。
- AC-006：TICK-VALID，re_verified。复跑收敛测：Browser 漂移先 fail_close，Agent 未确认封闭即在同一收敛遍内 pause 精确目标并记所有权，不删数据、不重建。
- AC-007：TICK-VALID，re_verified。复跑 Stream 侧收敛测：仅 Stream-only 有界替换、Browser 不被 pause/fail-close/重建；本轮新增预算耗尽→failed 不再替换测通过（另见 f006 的复合故障提示，不改变本条正例判定）。
- AC-008：TICK-VOID，re_verified。同进程隔离→复验→恢复主路径已修复并经接线级测复跑通过，desired 围栏属实；但 Supervisor 重启后所有权丢失场景的修复为死代码（见 t082_code_f005：core.py:1664 门禁先行 return，core.py:1813-1821 重登记不可达，reviewer 探针实证无登记、无恢复、无会话创建），AC 声明的恢复行为在重启场景仍未真实交付。
- AC-009：TICK-VALID，re_verified。复跑接管与孤儿测：凭标签全等 + health 身份回显接管同一 Agent（零新建），目标消失才清孤儿，迟到/错位回执不被采用，Agent 事件定点修复不触发全量扫描。
- AC-010：TICK-VALID，trust_prior。按用户 2026-11-18 裁定判定：task.md 契约区处置注记属实存在、p133 登记内容具体（10 分钟零 churn 计数口径与三类故障窗口正负例齐全），云端可做部分已复核（e2e 三文件共 7 测可收集、改由真实 PolicyAgentClient 驱动）；真实部署验证未在云端执行，不作已实测认定，待 p133 本地补验。

coverage = 8 / 10

verdict: FAIL

## Round 3 (2026-11-18T14:56:53+08:00)

- task：`t082_persistent_namespace_policy_agents`
- spec：`docs/tasks/t082_persistent_namespace_policy_agents/task.md`
- diff_anchor：`c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- target：`git diff c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- round：3

reviewed_scope: 5e0732197b369a78

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核：f001 已消除（同进程主路径第 2 轮已确认，本轮回归仍在：同代暂停路由 `src/backend/cbrowser/supervisor/core.py:1614` 与收敛 desired 围栏 `src/backend/cbrowser/supervisor/core.py:834` 复跑通过）。f002 已消除（本轮 grep 复核：t082 全部源码注释与 p132 正文无 `ADR 031` 残留）。f003 已消除（`docker_adapter.py` 无 `policy_helper_labels` 导入残留，grep 零命中）。f004 已消除（`src/backend/cbrowser/supervisor/policy_agent_client.py:128` 的 resolve 逐项 IP 字面量校验仍在，畸形回执抛 `PolicyAgentUnavailable`）。f005 已消除——逐行追踪现控制流：无会话时 `_reconcile_instance_observation` 对 paused 返回 None 不拦截（`src/backend/cbrowser/supervisor/core.py:2216`），无会话门禁对「Browser paused + Stream running」放行落入 restore（`src/backend/cbrowser/supervisor/core.py:1682`），restore 在收敛前重登记所有权（`src/backend/cbrowser/supervisor/core.py:1845`），收敛暂停分支经 `_attempt_policy_resume` 复验（必要时先重装）通过才 unpause 并清除所有权；reviewer 独立探针实证负例：重启 + paused + 规则不可复验（verify 返回 False 或抛 DockerSandboxError 两型）时会话被恢复、所有权保留、不 unpause、transport 为 browser_policy_isolated。f006 已消除——同代分支新增「暂停中 + Stream 非 running + `_stream_replacement_allowed` → Stream-only 替换」一档（`src/backend/cbrowser/supervisor/core.py:1626`），Browser 保持暂停、不报终态；reviewer 探针实证 Stream 为 created（任意非 running）同样路由替换，预算耗尽时不替换、所有权保留、会话置 error 的有界失败语义。
- 本轮新发现：0 条
- 未进表的提示：新改动误吞面已逐项探针核查，无误吞——真实 container_exit 组合（无会话 + Browser exited + Stream running）仍走终态上报、不建会话、不登记所有权；无会话 + Browser paused + Stream exited 不落入 restore（与第 2 轮前基线语义一致，非本轮回归，f006 修复面为同代分支）；desired=stopped 路径（`src/backend/cbrowser/supervisor/core.py:1700`）先于 restore 分支且重登记只在 restore 的 else 分支内，探针确认不登记、不恢复（探针中 stop_profile 因替身缺 disconnect_viewers 中断于所有权断言之后，该步以代码结构为准）。文件过大（按降级规则只列示）：`src/backend/cbrowser/supervisor/core.py` 3532 行、`src/backend/cbrowser/supervisor/docker_adapter.py` 3300 行，均为存量超 800 行文件且本 task 仍有净增，同前轮。圈复杂度：本轮新增分支手算未达 15，无复杂度 finding。未知契约：task.md 两项 UNVERIFIED-SPIKE 仍按用户 2026-11-18 裁定与处置注记处理、p132 登记具体，不作已实测认定（同前轮口径）。
- 测试真实性独立核查：交付的两条新接线测试均经 `_reconcile_profile` + API runtime 全链路驱动（`tests/unit/test_t082_supervisor_policy_convergence.py` 的 `test_reconcile_restores_paused_browser_after_supervisor_restart` 与 `test_stream_loss_during_browser_isolation_repairs_stream_only`；后者以记录替身替换 `_replace_stream_only` 本体，但路由条件与预算门禁为生产代码，属接线层隔离而非 mock 被测逻辑）。reviewer 在 /tmp 副本上独立做三组变异并逐组复跑：关无会话闸门条件 → 重启恢复测试变红；关 f006 分支的 Stream 非 running 条件 → Stream 修复测试变红；删 restore 重登记行 → 重启恢复测试变红（证明测试对重登记本身敏感，不只对闸门敏感）。实施侧变异自报属实。原 worktree 未被变异触碰（副本操作，事后 git status 与审前一致）。
- 复跑实数：t082 三件套（协议/适配器/收敛）37 条全过；全量 unit 2328 条：2312 passed、5 failed、10 errors、1 skipped，15 条 bad 逐项为 t063×12、t068×2、a16×1，与实施侧自报的老基线清单逐项一致、无 t082 相关失败；e2e 三文件 7 条可收集（云端未实跑，归 p133）。
- 总体判断：f001–f006 全部消除且无新问题，AC-008 的恢复行为在同进程与 Supervisor 重启两场景均真实交付，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。复跑 test_t082_adapter_policy_agents 与 test_t082_policy_agent 全套通过：启动先建 Agent 并经其 install 后才写 gate ready，失败不生成 ready 标记。
- AC-002：TICK-VALID，re_verified。复跑零 churn 测：多轮 verify 零容器创建、零 exec，inspect 在 Agent 内执行，目标不变 Agent 不重建。
- AC-003：TICK-VALID，re_verified。复跑协议测：身份字段不符全 op 拒绝、旧修订重放返回 stale_revision、超大/畸形/注入形请求被拒。
- AC-004：TICK-VALID，trust_prior。创建参数已在适配器测中复验（Agent 仅 NET_ADMIN/只读根/单一 slot 挂载、业务容器 cap_drop ALL 不挂 UDS）；「仅 NET_ADMIN 即可在真实 netns 完成安装/查询/封闭」属延期 spike，依赖 p132 本地实证，未在云端实测。
- AC-005：TICK-VALID，re_verified。复跑冻结派生与刷新测：上游未变零 DNS、上游变化走 resolve→install 新修订，刷新失败保留旧冻结 spec 与旧修订；resolve 回执 IP 校验（f004）在客户端单点落地，本轮 grep 与代码复核仍在。
- AC-006：TICK-VALID，re_verified。复跑收敛测：Browser 漂移先 fail_close，Agent 未确认封闭即在同一收敛遍内 pause 精确目标并记所有权，不删数据、不重建。
- AC-007：TICK-VALID，re_verified。复跑 Stream 侧收敛测：仅 Stream-only 有界替换、Browser 不被 pause/fail-close/重建，预算耗尽转 failed；本轮 f006 修复使暂停期间的 Stream 丢失同走此有界替换，探针复核预算耗尽语义不变。
- AC-008：TICK-VALID，re_verified。同进程隔离→复验→恢复与 Supervisor 重启后恢复两路径均经接线级测复跑通过；reviewer 独立探针实证重启负例（规则不可复验两型）所有权保留且不误恢复，变异复核证明测试能抓闸门与重登记两处旧行为。
- AC-009：TICK-VALID，re_verified。复跑接管与孤儿测：凭标签全等 + health 身份回显接管同一 Agent（零新建），目标消失才清孤儿，迟到/错位回执不被采用，Agent 事件定点修复不触发全量扫描；本轮重启恢复路径复用同一 restore 接管流，未见自激或无主 Agent 新路径。
- AC-010：TICK-VALID，trust_prior。按 task.md 处置注记 + p133 判定：注记属实、p133 登记具体（10 分钟零 churn 计数口径、漂移/Agent 故障/Supervisor 重启三类故障窗口正负例齐全），云端可做部分已复核（e2e 三文件 7 测可收集、改由真实 PolicyAgentClient 驱动）；真实部署验证未在云端执行，不作已实测认定，待 p133 本地补验。

coverage = 8 / 10

verdict: PASS

## Round 4 (2026-11-18T14:58:52+08:00)

- task：`t082_persistent_namespace_policy_agents`
- spec：`docs/tasks/t082_persistent_namespace_policy_agents/task.md`
- diff_anchor：`c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- target：`git diff c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- round：4

reviewed_scope: 5bafbf4e01d11667

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核：f001–f006 已在第 3 轮全部消除并 PASS，本轮交付变更不触及任何源码/测试，复核结论不变。
- 变更面核对（本轮核心）：以 `git diff`（未暂存）对 `git diff --cached`（第 3 轮 PASS 时的暂存态）对照——相对上一轮 PASS 指纹 `5e0732197b369a78`，worktree 唯一变更是 `docs/tasks/t082_persistent_namespace_policy_agents/task.md` 未知契约清单两行（2 insertions/2 deletions），无未跟踪文件，源码、测试、AC 打勾状态与 AC-010 处置注记在未暂存 diff 中零改动。
- 改写语义等价性逐条核对：①最小权限条——旧文的最小权限假设先行（仅 NET_ADMIN、只读根、无额外挂载）、正式 spike 延期本地并由 p132 跟踪、结论入 findings/ADR、spike 否定假设或显示需要 SYS_ADMIN/host PID/privileged 时停止扩权并修订设计、不静默绕过，新文逐项保留且触发条件合并表述无弱化；新文明确写「云端无 Docker 不可实证」与「假设冻结并已实现」，未把延期 spike 写成已验证。②pause 条——旧文的 pause 所有权围栏先行实现、真实链路负例验证延期 p132、pause API 返回成功不能单独证明隔离有效，新文逐项保留（「不单独作为隔离有效的证据」与旧文等价），并补入已由第 2/3 轮实证的围栏细节（仅本机制暂停且仍为当前运行意愿的实例可经复验恢复、重启后按 scan 重登记所有权），该细节属实现层事实而非真实链路实证冒充，网络负例与暂停所有权实证仍明确延期。两条均以「结论（2026-11-18，用户裁定）」标明结论来源为用户裁定而非实测，无偷偷弱化、无冒充已实证。
- 未知契约标记清零核对：task.md 未知契约清单两条已无 `UNVERIFIED-SPIKE` 标记（文件内仅剩规范注释中对标记名本身的说明文字，非清单条目）。
- 本轮新发现：0 条
- 未进表的提示：无（文件过大/复杂度同前轮，本轮无代码变更，不重复列示）
- 总体判断：改写前后语义等价、延期事项仍如实标为延期，除此之外无其他交付变更，AC 打勾与处置注记未动，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。第 3 轮复跑结论不变，本轮无代码变更；本轮仅核对 task.md 改写未触及 AC-001 文本与打勾。
- AC-002：TICK-VALID，re_verified。同上，零 churn 实现与测试未变更。
- AC-003：TICK-VALID，re_verified。同上，协议拒绝实现与测试未变更。
- AC-004：TICK-VALID，trust_prior。创建参数已在适配器测中复验；「仅 NET_ADMIN 完整策略/DNS 能力」本轮改写明确写为云端不可实证、假设冻结、spike 延期 p132，未冒充已实证，trust_prior 依据（p132 本地实证）不变。
- AC-005：TICK-VALID，re_verified。同上，冻结派生与刷新实现未变更。
- AC-006：TICK-VALID，re_verified。同上，漂移封闭实现与测试未变更。
- AC-007：TICK-VALID，re_verified。同上，Stream-only 有界替换实现未变更。
- AC-008：TICK-VALID，re_verified。同进程与重启恢复两路径第 3 轮已复验；本轮 pause 条改写补入的围栏细节（本机制暂停+当前运行意愿+复验恢复、重启 scan 重登记）与第 3 轮实证的实现一致，真实链路负例仍明确延期 p132，未冒充已实证。
- AC-009：TICK-VALID，re_verified。同上，接管与孤儿清理实现未变更。
- AC-010：TICK-VALID，trust_prior。处置注记在本轮未暂存 diff 中零改动、原文保留，仍明示不表示已实测通过、延期 p133 本地补验。

coverage = 8 / 10

verdict: PASS

## Round 5 (2026-11-18T15:01:03+08:00)

- task：`t082_persistent_namespace_policy_agents`
- spec：`docs/tasks/t082_persistent_namespace_policy_agents/task.md`
- diff_anchor：`c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- target：`git diff c2d7c892b08ab2df34465b6b08620cc2d43de0d2`
- round：5

reviewed_scope: a370c42e621635ab

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核：f001–f006 已在第 3 轮全部消除、第 4 轮确认不变；本轮增量不触及任何源码/测试，复核结论不变。
- 变更面核对（本轮核心①）：`git status --short` 中仅 `docs/specs/proxy_management.md` 与 `docs/specs/runtime_lifecycle.md` 为 `MM`（暂存 + 未暂存），其余条目均为纯暂存态（第 4 轮已审内容）；`git diff`（未暂存）恰为 2 文件各 1 行——两份 spec 的 front matter `tasks: [baseline]` → `tasks: [baseline, t082]`（`docs/specs/proxy_management.md:4`、`docs/specs/runtime_lifecycle.md:4`），无其他交付变更，无未跟踪文件。
- spec 正文一致性抽查（本轮核心②）：`docs/specs/runtime_lifecycle.md:14` 现行表述为启动前由该目标常驻 Policy Agent（t082，ADR 039：仅 NET_ADMIN、只读根、与目标同 netns、UDS 协议）安装 IPv4/IPv6 策略，与实现一致；`docs/specs/proxy_management.md:71` 现行表述为上游代理解析地址由目标 Policy Agent 在其 netns 内解析，与 AC-005 冻结解析设计一致。另抽查 `docs/specs/browser_isolation.md`、`docs/specs/release_deployment.md`：无 Policy Agent 或临时 helper 安装策略的过时表述（仅角色标签枚举等中性提及），与实施侧核查结论相符。
- AC 打勾与处置注记核对（本轮核心③）：task.md 不在未暂存 diff 内；AC-001 至 AC-010 仍全部为 `- [x]`，AC-010 处置注记原文保留（明示不表示已实测通过、延期 p133 本地补验），未动。
- 本轮新发现：0 条
- 未进表的提示：无（本轮无代码变更，文件过大/复杂度同前轮，不重复列示）
- 总体判断：本轮唯一增量为两行 front matter tasks 登记，恰对应 specs-index 同步要求；两份 spec 正文现行表述与 t082 实现一致，AC 打勾与处置注记未动，PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。第 3 轮复跑结论不变；本轮 git 核实实现与测试相对第 4 轮 PASS 态零变更，仅核对增量未触及 AC-001。
- AC-002：TICK-VALID，re_verified。同上，零 churn 实现与测试未变更。
- AC-003：TICK-VALID，re_verified。同上，协议拒绝实现与测试未变更。
- AC-004：TICK-VALID，trust_prior。创建参数已在适配器测中复验；「仅 NET_ADMIN 完整策略/DNS 能力」仍为延期 spike、依赖 p132 本地实证，未在云端实测；本轮两份 spec 正文的 NET_ADMIN/只读根表述与该冻结假设一致，未冒充已实证。
- AC-005：TICK-VALID，re_verified。同上，冻结派生与刷新实现未变更；proxy_management 正文的 Agent netns 内解析表述与实现一致。
- AC-006：TICK-VALID，re_verified。同上，漂移封闭实现与测试未变更。
- AC-007：TICK-VALID，re_verified。同上，Stream-only 有界替换实现未变更。
- AC-008：TICK-VALID，re_verified。同上，同进程与重启恢复两路径实现未变更。
- AC-009：TICK-VALID，re_verified。同上，接管与孤儿清理实现未变更。
- AC-010：TICK-VALID，trust_prior。处置注记在本轮增量中零改动、原文保留，仍明示不表示已实测通过、延期 p133 本地补验。

coverage = 8 / 10

verdict: PASS
