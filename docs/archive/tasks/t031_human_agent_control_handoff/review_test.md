# Task review t031（reviewer_focus: 测试）

- task：`t031_human_agent_control_handoff`
- spec：`docs/tasks/t031_human_agent_control_handoff/task.md`
- diff_anchor：`09bfb3a0cbf90d55875c4f1abb18647e49b46d35`
- target：`git diff 09bfb3a0cbf90d55875c4f1abb18647e49b46d35`
- round：1
- reviewed_at：2026-11-04T21:40:09+08:00

## Round 1 (2026-11-04T21:40:09+08:00)

落点校验：工作仓库顶层与 diff anchor 一致，当前分支为 t031 任务分支，HEAD 为 09bfb3a；`git status` 无未跟踪交付文件，审查范围覆盖全部已暂存与未暂存改动。测试改动共 26 个文件、约 3389 行新增：15 个新增测试文件、4 个既有测试文件修改、其余为生产与前端改动中的测试相关部分。本轮为静态断言与接线审计：本环境无 pytest 可用执行器（无 venv、无 pytest 模块），未实际跑通测试套件，测试执行绿灯本身依赖实施侧门禁证据（见结论段 AC 复验方式）。

## Findings

### t031_test_f001 - 输入上报链组装无测试：前台门禁由测试代码复现，Stream 钩子与 Gateway 泵分支均未被驱动

- 严重度：important
- 锚点：AC-002（前台 Viewer 输入形成交接边界）、AC-008（输入适配器测试覆盖接管）
- 位置：`tests/unit/test_stream_takeover_classifier.py:47`（`test_report_callback_invoked_only_for_foreground_takeover`）；生产钩子 `src/backend/cbrowser/stream_agent/policy.py` 的 `_on_peer_data_message`（分类＋前台判断＋上报组装处）；`src/backend/cbrowser/gateway/server.py:682`（`HUMAN_INPUT_TAKEOVER` 泵分支）；`tests/unit/test_stream_takeover_report.py:22`（`_bare_agent`）
- 问题：三段证据各自为真、组装处全空。分类表测试只测纯函数 `classify_human_takeover_input`；所谓“仅前台上报”测试在测试代码里自己写了 `if kind and agent.is_foreground_input(conn): agent.report_human_takeover(...)`，即测试复现了生产门禁逻辑，从未执行生产钩子里的分类→前台判断→上报组装。查全仓：没有任何测试用接管类输入驱动过真实的 `_on_peer_data_message` 并断言上报回调被触发或抑制（既有 `tests/unit/test_stream_capture_policy.py` 的钩子测试不设 `on_human_takeover`，且其 IME 用例只断言转发，不涉上报）。Gateway 泵分支（收到 `human_input_takeover` 信封后调 `api.report_human_takeover`，失败仅记日志）同样无任何测试驱动，全仓 Gateway 测试无 takeover 用例。`test_stream_takeover_report.py` 用 `StreamAgent.__new__` 手工拼装对象绕过构造器，因此构造器里 `policy.on_human_takeover = self.report_human_takeover` 这根接线本身也未被任何测试证实。可复现的逃逸场景：生产钩子漏调上报、传错 conn/kind，或 Gateway 泵分支丢弃信封，现有全部测试仍全绿，而真实前台输入永远形不成接管——这正是 AC-002 最关键的安全语义。
- 建议：新增一个驱动真实钩子的测试（用真实 `create_policy_controlled_service_class` 包装类，`on_human_takeover` 接记录器）：前台 `kd,65` 应被记录、后台 `sf,3` 不应被记录；另加 Gateway 泵测试，喂 `human_input_takeover` 信封并断言 `api.report_human_takeover` 被调用且失败时泵不中断；上报测试改用真实构造器接线或单独断言构造器接线。

### t031_test_f002 - E2E `_setup` 的宽泛 except 把拓扑启动失败吞成 skip，t032 实跑时真故障会被报成跳过

- 严重度：important
- 锚点：AC-002、AC-004（两条 E2E 条目是交 t032 的实跑证据）
- 位置：`tests/e2e/test_control_handoff_e2e.py:27`（`_setup` 的 `try/except Exception -> pytest.skip`）
- 问题：`_setup` 把 `docker.from_env().ping()` 与 `harness.start()` 包在同一个宽泛 except 里。`tests/fixtures/gateway_probe/topology.py` 的 `start()` 可因真实故障抛错（服务就绪超时、容器未暴露端口、Stream Agent 30 秒未注册，均非“环境缺失”），这些错误同样会被转成 skip。这与文件头 docstring 自称的“fails for real when they are available”直接矛盾：按现有写法，`_setup` 阶段永远不会失败，t032 实跑时一个已启动但损坏的拓扑会被记为跳过而非失败，AC-002/AC-004 的 E2E 证据随之失真。
- 建议：只在 Docker 不可用或镜像缺失时 skip（ping 单独包 try），`harness.start()` 的超时/断言/容器故障一律让测试失败；或按异常类型区分可用性缺失与启动失败。

### t031_test_f003 - 迁移测试只测新鲜库全量升级，未测已有数据的 0008→0009 升级

- 严重度：minor
- 锚点：AC-001（迁移在隔离 DB 上可升级）
- 位置：`tests/unit/test_control_migration.py:43`（`test_migration_upgrade_backup_restore`）
- 问题：`_seed` 在空库上跑全量迁移（含 0009），再做文件拷贝备份恢复；0009 自身的 `upgrade()` 确实被执行，但“已有 profile 数据的 0008 库升级到 0009 后数据与控制行完好”这一路径未被覆盖。鉴于 0009 是新增 `profile_controls` 表而非改动既有表，数据丢失风险低，故只列 minor，不阻断。
- 建议：补一个用例：先在 0008 头上建库并写入 profile，再升级到 0009，断言原 profile 仍在且控制行默认态为 user/0。

### t031_test_f004 - AC-002 注的“重连拒绝”云端证据只到 claim/fence 层，WS 4403 层只在 collect-only E2E 中

- 严重度：minor
- 锚点：AC-002 注（两层关闭与重连拒绝已由云端集成测试验证）
- 位置：`docs/tasks/t031_human_agent_control_handoff/task.md` 的 AC-002 注；`tests/e2e/test_control_handoff_e2e.py` 的 `test_handoff_closes_established_tunnel_and_refuses_reconnect`
- 问题：核对注与实现基本一致，但措辞偏宽。云端已验证的部分是：API 层注册隧道关闭（`tests/integration/test_control_api.py` 的 handoff 关注册隧道测试）、Supervisor 层关闭与围栏（`tests/integration/test_control_supervisor_close.py`）、API→Supervisor 级联确认（attendant 链测试轮询 `pending_supervisor_close` 变 false）、claim 层 409 拒绝与 CLI 陈旧代次拒绝。唯独“已建立 WS 隧道被 4403 关闭、重连被 4403 拒绝”这一用户可观察层只存在于 collect-only E2E（云端无 Docker 即 skip），尚未在云端以真实 WS 验证。注文未区分这两层，读起来像 WS 层也已云端验证。
- 建议：把注收紧为“两层注册表关闭、级联确认与 claim/fence 层重连拒绝已由云端集成测试验证；真实 WS 隧道的 4403 关闭与重连拒绝由 E2E 条目交 t032 实跑”，或补一个云端真实 WS 隧道关闭测试。

### t031_test_f005 - Dialog 打开不切换控制权无断言

- 严重度：minor
- 锚点：AC-006（JS Dialog 按 t030 处理且不无故切换控制权）
- 位置：`tests/integration/test_control_attendant_chain.py`（dialog 持有与应答各阶段均未读控制态）
- 问题：AC-006 的主句（permission/CLI handOff 进入 user）有单元与集成断言；但“Dialog 不无故切换控制权”这一子句无测试：链测试在 agent 持有控制时打开并持有 dialog，全程没有读取并断言控制方仍为 agent；若某次改动让 dialog 打开误触发接管，现有测试不会失败。
- 建议：在链测试 dialog 被持有后、应答前各读一次控制态，断言 owner 仍为 agent 且 generation 未变。

### t031_test_f006 - 过期 SSE 不覆盖新代次状态无测试，前端合并无代次比较

- 严重度：minor
- 锚点：AC-005（过期响应和 SSE 不覆盖新代次状态）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts` 的 `useProfileEventsSync`（control 合并分支）；`src/frontend/src/shared/api/sse.control.test.ts`（仅测解析合法性）
- 问题：AC-005 的“过期响应”一半有证据（CLI 陈旧代次拒绝测试），但“SSE 不覆盖新代次”一半无证据：前端事件同步合并是 `event.control !== undefined ? event.control : old.control`，不比较 generation；没有任何测试喂一个旧代次事件去验证它不会覆盖新状态。SSE 单连接内有序时该场景需重连/乱序才触发，属低概率但 AC 明文写出的语义。
- 建议：补一个同步合并测试（旧代次事件到达已更新的缓存时不覆盖），或在代码注释中写明 SSE 有序性保证并说明该子句为何无需代次比较。

### t031_test_f007 - SSE 事件到管理面面板刷新的组装无测试

- 严重度：minor
- 锚点：AC-007（控制方经 SSE 同步展示）
- 位置：`src/frontend/src/features/profiles/useProfilesQuery.ts` 的 `useProfileEventsSync` control 合并分支；`src/frontend/src/features/profiles/ProfileDetailPage.control.test.tsx`（只测 query 数据渲染与恢复 mutation）
- 问题：SSE 解析测试与面板渲染测试各自为真，但“SSE 事件到达→缓存 control 更新→面板刷新”这条组装线无测试：面板测试用 query 初始数据渲染，SSE 测试只测 `parseProfileRuntimeEvent` 的接受/拒绝，均未驱动 `useProfileEventsSync` 的 control 合并分支。若合并分支写错字段或未触发刷新，面板仍显示旧控制方而测试全绿。
- 建议：补一个事件同步测试：先渲染 user 控制态，再喂入 agent 控制态的 runtime 事件，断言面板控制方随之更新。

## 结论

- 改测方向复核：无“迁就实现”的改测。4 处既有测试修改均合法：`tests/unit/test_api_models_and_sse.py` 仅给事件加 `control: None` 字段（加法）；`tests/unit/test_refactor_behavior_equivalence.py` 仅因 `make_runtime_response` 改为 async 而加 await，断言原文不动；`tests/unit/test_stream_agent_protocol_v2.py` 仅把新契约动作 `human_input_takeover` 加入允许集，删除动作断言保留；`tests/unit/test_t027_release_controller.py` 仅因迁移头变为 0009 而顺延 drill 版本号与期望值，回滚拒绝语义断言不变。
- 本轮新发现：7 条（important 2 条，minor 5 条）
- 未进表的提示：
  - 危险模式扫描：全 diff 仅命中 3 处 skip，且链测试的两处（缺 Playwright Chromium、缺 Xvfb）是窄环境门，符合 spec“可用的普通 Chromium 测试”口径，不出 finding；E2E 的 skip 因掩盖启动失败已单列为 f002。其余模式（恒真断言、删/反转断言、注释断言、弱化断言、独占、静默错误注解、mock 被测逻辑、阈值掩盖、条件断言、程序赋值替代交互、存在即通过）均未命中；前端恢复测试用真实 `fireEvent.click`，不属程序赋值替代交互。
  - AC-004 注核对一致：接管路径代码只动自动化隧道注册表与 attendant 释放，无关闭 Viewer 连接或浏览器生命周期的代码；云端证据为 API 可见的 runtime 连续性与链测试事后页面仍可 extract，真实 WebRTC 多 Viewer 连续性交 t032 的分工与注文相符，不出 finding。
  - AC-001 崩溃路径：`note_runtime_started` 对所有原因统一走 handoff 转移，重启测试已覆盖该转移函数，crash 原因无需单测，不出 finding。
  - 测试替身取舍可接受（f001 除外）：control_service 重试测试中途改私有回调、executor 测试注入私有 client/post、attendant 服务测试直调私有 `_run`，其断言仍落在可观察行为（HTTP 状态、注册表内容、隧道关闭、应答会话）上，不构成 mock 被测逻辑；但 `_bare_agent` 绕构造器的接线缺口已并入 f001。
  - XTEST 不触发属结构性保证：XTEST 注入不经过 WebRTC 数据通道，分类器只消费数据通道字符串，未知前缀一律返回 None，分类表已覆盖纯鼠标移动、按键释放、IME 进行中三类不触发情形，不出 finding。
  - 覆盖面肯定项：控制服务状态机（默认/认领/接管/恢复/二 Agent 冲突/重启/待关闭重试）走真实隔离 DB；API 层走真实应用与 TestClient；Supervisor 层走真实控制应用；attendant 链走真实 Chromium＋真实 API＋真实 Supervisor＋真实 UDS agent 并验证了 API→Supervisor 级联确认；迁移走真实 Alembic 路径与备份恢复文件比对；CLI 含 handoff 停步不重放测试。
- 总体判断：输入上报链组装缺失与 E2E skip 掩盖失败两项 important 未解决，测试证据不足以支撑 AC-002/AC-008 的打勾，故 FAIL。
- 系统性 follow-up：无（f001、f002 均属本 task 内可修，不建议另立跨 task 条目）。

## AC 复验方式

- AC-001：re_verified——控制服务状态机断言与迁移备份恢复断言均已逐条追到生产实现（真实隔离 DB、真实 Alembic 路径），f003 仅为已有数据升级的 minor 扩展。
- AC-002：部分复验，未计入覆盖——claim/接管/两层隧道关闭/围栏/陈旧代次各层断言已静态追认，但 f001 的输入上报组装缺口使“前台输入触发接管”无端到端证据，且 WS 4403 层证据只在 collect-only E2E 中（见 f004）。
- AC-003：re_verified——handoff 后停步不重放断言已追到 `run_program` 的跳过标记实现。
- AC-004：trust_prior——依赖的证据是 collect-only E2E 条目（云端 skip，实跑在 t032）与链测试事后页面可 extract 的间接证据；真实 WebRTC 多 Viewer 连续性无法在本环境复验。
- AC-005：re_verified——finish 不关闭语义的 reclaim 断言、陈旧代次拒绝断言已追认；f006 的 SSE 乱序子项为 minor，不影响主句复验。
- AC-006：re_verified——permission/CLI handOff 进入 user 的断言已追认；f005 的 dialog 不切换子项为 minor，不影响主句复验。
- AC-007：re_verified——面板渲染断言与 SSE 解析断言已追认；f007 的事件到面板组装为 minor，不影响主句复验。
- AC-008：re_verified——云端测试套件（状态机、API、Supervisor、HTTP 客户端、attendant 链、collect-only E2E 条目）已逐项审计；其目标 WebRTC/X11 部分按 spec 本就交 t032，不计入云端复验范围。
- coverage = 6/8（re_verified 6 条：AC-001、AC-003、AC-005、AC-006、AC-007、AC-008；AC-002 部分复验未计入；AC-004 为 trust_prior。trust_prior 占比 12.5%，未超 30%。）
- 补充说明：本环境无 pytest 可用执行器，上述 re_verified 均为静态断言与接线审计，未实际执行测试套件；测试执行绿灯本身仍依赖实施侧门禁证据，复审时应以可执行环境的实跑结果为准。

reviewed_scope: 08cddeb20ce183b2

verdict: FAIL

## Round 2 (2026-11-04T23:29:09+08:00)

本轮为 Round 1 之后修复轮的回归复审：逐项独立核对 R1 七条 finding 是否真消除（读测试代码与生产接线，不采信处置表自述），并全量扫修复轮新增测试有无新问题。本轮仍为静态断言与接线审计：本环境未实际执行测试套件，执行绿灯依赖实施侧门禁证据（见结论段 AC 复验方式）。审查范围为相对 diff anchor 的全部 worktree 内容变化；报告文件本身不计入范围指纹。

### 前轮 finding 复核

- t031_test_f001（important）：已消除。生产钩子本身做分类→前台→上报组装（`src/backend/cbrowser/stream_agent/policy.py` 的包装类 `_on_peer_data_message` 内分类后调 `is_foreground_input` 再调 `report_human_takeover`）；新测试 `tests/unit/test_stream_takeover_chain.py` 用真实包装类驱动该钩子，断言前台 `kd,65` 上报、后台 `sf,3` 不上报、纯移动与单纯释放不上报、未映射连接 fail-closed 上报，且全部消息仍透传到底层；构造器接线测试用真实 `StreamAgent` 构造器断言 `policy.on_human_takeover` 即 `report_human_takeover` 且驱动后进入待上报队列。Gateway 半边：`tests/unit/test_gateway_takeover_pump.py` 用真实 Gateway 应用与真实注册握手喂 `human_input_takeover` 信封，断言转发到 API 客户端，且首报失败后第二报仍送达（泵不中断）。原先“测试复现门禁逻辑”的逃逸口已堵死。
- t031_test_f002（important）：已消除。`tests/e2e/test_control_handoff_e2e.py` 的 `_setup` 现只把 Docker ping 包在 skip 的 try 内，`GatewayTopologyHarness` 构造与 `harness.start()` 的失败直接传播；文件头“fails for real when they are available”与实现一致。剩余的唯一 skip 是 Docker 不可用本身，属窄环境门。
- t031_test_f003（minor）：已消除。`tests/unit/test_control_migration.py` 新增 `test_upgrade_from_0008_preserves_profiles`：在 0008 头上建库写 profile 后升级到 head，断言原 profile 完好、无控制行回填、服务读默认态为 user/0，与处置表措辞一致。
- t031_test_f004（minor）：已消除。`docs/tasks/t031_human_agent_control_handoff/task.md` 的 AC-002 注现写明云端证据只到“两层注册表关闭、API→Supervisor 级联确认与 claim/fence 层重连拒绝”，真实 WS 隧道的 4403 关闭与重连拒绝由 E2E 条目交 t032 实跑；与云端集成测试实际覆盖层一致，不再偏宽。
- t031_test_f005（minor）：已消除。`tests/integration/test_control_attendant_chain.py` 在 dialog 被持有前与持有后（应答前）各读一次控制态，断言 owner 仍为 agent 且 generation 未变。
- t031_test_f006（minor）：已消除。生产合并分支现比较代次（`src/frontend/src/features/profiles/useProfilesQuery.ts` 的 `useProfileEventsSync`：仅当事件代次大于等于缓存代次才应用 control）；`useProfilesQuery.control.test.tsx` 的 stale 用例喂 gen-3 事件到 gen-4 缓存，断言缓存保持 user/4。等代次（>=）重应用属同一代次状态重放，不构成覆盖风险。
- t031_test_f007（minor）：已消除。组装线两段均有测试：hook 级 `useProfilesQuery.control.test.tsx`（新代次事件写入缓存）与页面级 `ProfileDetailPage.control.test.tsx` 的 SSE 用例（事件到达后面板 owner 由 Human 变为 Agent）。页面级用例同时触发 refetch，但 hook 级用例用禁用查询隔离了合并本身，故合并分支写错字段仍会被 hook 级用例捕获。

### 本轮新发现

#### t031_test_f008 - attendant 拆分后的 Target.targetCreated 分支无单元钉子，回归只靠链测试间接覆盖

- 严重度：minor
- 锚点：AC-006（attendant 持有 dialog 的分支正确性）；拆分回归，非 AC 全缺
- 位置：`src/backend/cbrowser/runtime_agent/dialog_attendant.py` 的 `_handle_event`（Target.targetCreated 分支）；`tests/unit/test_dialog_attendant.py`（无 targetCreated 用例）
- 问题：拆分回归（code f007）中一度漏记的 `Target.targetCreated → attachToTarget → pending_attach` 分支现已补回（`_handle_event` 内对 page 类型目标发 attach 并登记 pending_attach），但单元测试只喂了 getTargets 路径（`test_service_attaches_pages_and_holds_dialog` 与应答用例均走 id 2 的 getTargets 响应），没有任何用例向 `_run` 喂 `Target.targetCreated` 事件。链测试跑真实浏览器时该分支可能被附带触发，但链测试未对该分支做定向断言；若该分支再次退化（例如事件分支被误删），单元层不会变红。属“补一个定向 case”的 minor，不阻断：AC-006 主句仍有链测试与 getTargets 路径覆盖。
- 建议：补一个 `_FakeWs` 用例：先完成发现握手，再喂 `Target.targetCreated`（page 类型），断言发出 `Target.attachToTarget` 且 attach 响应后完成 `note_attached` 与 `Page.enable`。

### 修复轮新增测试全量扫描

- 对话门禁测试（`tests/integration/test_control_api.py` 的 `test_control_dialogs_peek_and_answer`）：peek/answer 共用生产门禁 `_require_dialog_agent`（owner 非 agent 拒、非持有 token 拒）；测试覆盖了未鉴权 401、user 态 peek 409、持有 token peek/answer 200、第二 token peek/answer 409、答后 peek 为空与答无持有 dialog 404；两条门禁分支均有断言，无弱化。
- 吊销交接测试（同文件的 `test_revoke_token_hands_off_live_control` 与 `tests/unit/test_control_service.py` 的 `test_handoff_for_identity_moves_only_that_token`）：吊销后控制方变 user、原因为 identity_invalid、reclaim 关闭、旧 token 再认领 401；且同 token 的多 profile 均交接、他 token 的 profile 不受影响。断言落在可观察状态与 HTTP 码上。
- coordinator 标志测试（`tests/unit/test_coordinator_close_flag.py`）：200 但 `attendant_released` 为 False 时判未确认、500 与坏体判未确认；仅在系统边界用 `httpx.MockTransport` 替 Supervisor，未 mock 被测逻辑。
- 锁并发测试（`tests/unit/test_control_service.py` 的 `test_concurrent_claims_serialize_to_conflict`）：8 并发认领恰一胜、7 败者均为 `control_second_agent` 冲突；走真实隔离 DB 与生产锁路径。
- attendant 拆分后的服务测试改动（`tests/unit/test_dialog_attendant.py`）：`_run` 经假 WS（浏览器连接边界）驱动，覆盖 attach→Page.enable→持有、连接结束释放清 dialog（code f006 的 finally 语义）、重 arming 清 released 标志、attendant 会话应答；除 f008 的 targetCreated 分支外无缺口。
- 前端 hook/页面新测试：见 f006、f007 复核；stale 用例的 50ms 等待针对“无变化”断言（waitFor 无法表达否定），不属阈值掩盖。
- 危险模式重扫：修复轮新增测试无新增 skip/only；页面测试的 `toBeTruthy` 均附带 `textContent` 或行为断言（`getByTestId` 本身缺失即抛），不构成存在即通过；无恒真断言、删/反转断言、条件断言、mock 被测逻辑。

### 结论

- 前轮 finding 复核：7/7 已消除（important 2 条、minor 5 条），无修不彻底、无换形式弱化。
- 改测方向复核：无“迁就实现”的改测。E2E `_setup` 的收窄是反向收紧（skip 改失败），其余修复轮改动均为新增测试与生产守卫，未动既有测试的预期。
- 本轮新发现：1 条（minor 1 条）
- 未进表的提示：无。
- 总体判断：R1 的两项 important 已真消除，剩余仅 minor 分支钉子，测试证据足以支撑八条 AC 的打勾（AC-004 的真实 WebRTC 部分仍按 spec 交 t032）。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：re_verified——状态机断言、0008→0009 带数据升级断言与备份恢复断言均已追到真实隔离 DB 与 Alembic 路径。
- AC-002：re_verified——输入上报组装（钩子＋构造器接线＋Gateway 泵）、两层注册表关闭、级联确认与 claim/fence 层重连拒绝均已静态追认；注文明示真实 WS 4403 层交 t032 E2E，该层不在云端复验范围内。
- AC-003：re_verified——handoff 后停步不重放断言已追认（本轮无变动）。
- AC-004：trust_prior——依赖的证据是 collect-only E2E 条目（云端 skip，实跑在 t032）与链测试事后页面可 extract 的间接证据；真实 WebRTC 多 Viewer 连续性无法在本环境复验。
- AC-005：re_verified——finish 不关闭语义、陈旧代次拒绝与 SSE 代次守卫（新旧双向）断言均已追认。
- AC-006：re_verified——permission/CLI handOff 进入 user、dialog 不切换控制权、门禁 409 与 attendant 持有/应答断言均已追认；f008 的 targetCreated 分支钉子为 minor，不影响主句复验。
- AC-007：re_verified——面板渲染、SSE 解析与 SSE→缓存→面板组装断言均已追认。
- AC-008：re_verified——云端测试套件（状态机、API、Supervisor、HTTP 客户端、attendant 链、输入上报链、collect-only E2E 条目）已逐项审计；其目标 WebRTC/X11 部分按 spec 本就交 t032，不计入云端复验范围。
- coverage = 7/8（re_verified 7 条：AC-001、AC-002、AC-003、AC-005、AC-006、AC-007、AC-008；AC-004 为 trust_prior。trust_prior 占比 12.5%，未超 30%。）
- 补充说明：本环境未实际执行测试套件，上述 re_verified 均为静态断言与接线审计；测试执行绿灯本身仍依赖实施侧门禁证据，复审时应以可执行环境的实跑结果为准。

reviewed_scope: eacc2c9ec4e353ec

verdict: PASS

## Round 3 (2026-11-04T23:35:45+08:00)

本轮为 Round 2 之后修复轮的窄范围复审，只核以下三项，不重审全部测试：test f008 的修复、code f009 的配套测试、报告末尾指纹与当前 worktree 的一致性。本轮仍为静态断言与接线审计：本环境无 pytest 可用执行器（无 venv、无 pytest 模块），未实际执行测试套件，执行绿灯仍依赖实施侧门禁证据（与 Round 1/2 口径一致）。审查时只读，未改代码、未提交。

### 1. test f008 已消除：targetCreated 用例真实驱动全链路

- 位置：`tests/unit/test_dialog_attendant.py:138`（`test_service_target_created_attach_records_session`）；生产侧 `src/backend/cbrowser/runtime_agent/dialog_attendant.py` 的 `_handle_event`（`:266`，targetCreated 分支 `:272`–`:281`）与 `_handle_response`（`:235`，pending_attach 分支 `:259`–`:264`），分发在 `_run`（`:315` 建 `pending_attach`，`:327`–`:331` 按有无 id 分流两 handler，与 code f007 拆分一致）。
- 链路核对（逐跳均为生产代码执行，非测试复现）：
  1. 测试等 `fake.sent` 达 2 条（`Target.setDiscoverTargets` + `Target.getTargets`）后再喂 `Target.targetCreated`（page 类型、targetId `page-9`），符合 Round 2 建议的“先完成发现握手”。
  2. `_run` 无 id 消息走 `_handle_event`：发出 `Target.attachToTarget` 并登记 `pending_attach[attach_id] = page-9`。
  3. 测试从已发消息中取该 attach 的真实 id 回填 `sessionId: att-9` 的响应；`_run` 有 id 消息走 `_handle_response`：命中 `pending_attach` 后 pop、执行 `note_attached(att-9, page-9)` 并发出 `Page.enable`（sessionId `att-9`），测试对该 `Page.enable` 做定向等待断言。
  4. 再喂 `Page.javascriptDialogOpening`（sessionId `att-9`）：因会话映射已由生产代码登记，`note_opening` 成功滞留；最终断言 `held` 恰 1 条、target 为 `page-9`、类型为 `alert`。
- 非复现逻辑、非只测存在：测试全程未直接调用 `note_attached`、未自建会话映射、未复写 `pending_attach` 逻辑；会话映射只可能来自生产代码对 attach 响应的处理。`_FakeWs` 仅替代浏览器连接边界（与 Round 2 已接受的既有模式相同），未 mock 被测逻辑。
- 可证伪性：删 targetCreated 分支则无 attach、attach_id 断言失败；删 `pending_attach` 登记则 attach 响应无处落点、无 `Page.enable`、dialog 因未知会话被忽略、`held` 为空而失败。任一环节退化都会变红。
- 结论：符合 Round 2 建议并超出建议（建议只到 attach 响应后 `note_attached` + `Page.enable`，本用例另加 dialog 滞留断言），f008 已消除。

### 2. code f009 配套测试已验证：单 profile 失败不中断整批

- 位置：`tests/unit/test_control_service.py:296`（`test_handoff_for_identity_isolates_per_profile_failures`）；生产侧 `src/backend/cbrowser/services/control_service.py:425`（`handoff_for_identity`，循环 `:448`–`:463`：`ControlNotFoundError` 跳过、通用 `Exception` 记日志后 `continue`、仅成功才 `append`）。
- 注入方式合理、不构成 mock 被测逻辑：测试先用真实服务与真实隔离 DB 对同一 token（`tok-1`）认领两个 profile，再用 `monkeypatch.setattr` 只替换实例上的 `handoff` 为 `failing_once`——对失败 profile（pid）抛 `RuntimeError`，其余一律透传给真实 `handoff`。被测逻辑是 `handoff_for_identity` 的循环隔离（try/except/continue/append），该循环本身全程走生产代码，未被替换、未被复现；`handoff` 在此是循环的下游依赖，对其做单点故障注入是标准做法（真实 DB 故障无法只毒化一个 profile 而不影响同库另一 profile）。`RuntimeError` 恰好命中生产通用 `except Exception` 分支（而非已有的 NotFound 分支），对准 f009 语义。
- 断言落在可观察结果上：`handed == [pid2]`（失败 profile 未被谎报为已交接）、`pid2` 复读为 user（整批确实继续）、失败的 pid 复读仍为 agent（失败未被静默当成功）。若实现改为重抛，测试直接报错；若中途放弃循环，`pid2` 仍为 agent 而失败；若先 append 再处理失败，`handed` 断言失败。
- 结论：该用例真实验证“单 profile 失败不中断整批”，f009 的测试证据成立。

### 3. Scope：指纹与当前 worktree 一致

- 方法：按 checker 的单一真相源 `.repo_template/scripts/repo_task/monitoring.py` 的 `review_scope_fingerprint`，以 diff anchor `09bfb3a0cbf90d55875c4f1abb18647e49b46d35` 与 task 目录重算；过程文件（`note.md`、`review_code.md`、`review_test.md` 等）按该函数规则排除在指纹之外，故本节的追加本身不改变指纹。
- 结果：当前 worktree 指纹为 `de621b4faa4495d9`，与本节末尾的 `reviewed_scope` 一致。Round 2 的 `eacc2c9ec4e353ec` 现已 stale，属预期：f008/f009 的修复（上述两个测试文件与控制服务）在 Round 2 之后才落入 worktree，指纹随交付内容变化而变化，不是报告与实际内容的不一致。
- 范围外提示（不进表、不影响 verdict）：`check_review_status.py` 全量运行时会在处置表校验处中止（`note.md` 中 code f010 的 fix_ref 写法不符合该脚本对 pNNN/tid 的格式要求），该问题属实施侧处置表格式、超出本轮窄范围且 reviewer 不改 `note.md`；故本项 scope 结论以直接重算的指纹函数为准，而非该脚本的整体输出。

### 结论

- 前轮 finding 复核：test f008 已消除、code f009 的配套测试证据成立；Round 2 其余结论本轮未重审、不改动。
- 本轮新发现：0 条。
- 总体判断：三项全过，无新发现，测试证据足以支撑 Round 2 的 AC 结论维持不变（AC-006 的 targetCreated 分支钉子已补齐；AC-001 的吊销整批隔离已有配套测试；coverage 仍为 7/8，AC-004 仍为 trust_prior、交 t032）。

reviewed_scope: de621b4faa4495d9

verdict: PASS
