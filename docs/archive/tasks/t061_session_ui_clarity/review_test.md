# Task review t061（reviewer_focus: 测试）

- task：`t061_session_ui_clarity`
- spec：`docs/tasks/t061_session_ui_clarity/task.md`
- diff_anchor：`c5f83296ece80a9a0ed9f1e48d957ce332f858c4`
- target：`git -C '<home>/workspace/CBrowser_t061' diff c5f83296ece80a9a0ed9f1e48d957ce332f858c4`
- round：1
- reviewed_at：2026-11-13T21:48:01+08:00

reviewed_scope: c5fe8b9c25e5b811

## Findings

### t061_test_f001 - integration「单跑全部恢复」声明在文件粒度未被独立复现（仅单测隔离复现）

- 严重度：minor
- 锚点：行为缺陷（门禁证据定性精度）+ progress.md 声称受影响文件单跑全部恢复，reviewer 文件级重跑仍出现同型 error
- 位置：`docs/tasks/t061_session_ui_clarity/progress.md:62`；`tests/integration/conftest.py:60`
- 问题：实施侧定性 integration 15 errors 为负载 flaky，依据之一是「test_normal_exit_replay.py 单独跑 4 passed，全部恢复」。reviewer 独立复核：该文件单独跑（无 xdist）结果为 3 passed / 1 error，error 仍是同一 `isolated API process did not become ready`（conftest.py:60）；与 supervisor_rpc 合跑为 5 passed / 2 errors。仅在把失败用例单独成测重跑时才 1 passed（15.42s）。即「flaky 且与本 diff 无关」的实质判断成立（本 diff 不触任何 `tests/` 与 `src/backend` 文件，错误模式为子进程就绪超时、隔离后消失），但「单跑 4 passed」这一具体证据强度高于 reviewer 可复现的结果，manifest 中 integration 仍为 exit 1 的非绿状态，处置时不应按「已全量复绿」引用。
- 建议：把 progress.md 该句修正为「文件级单跑仍偶发同型就绪超时、单测隔离重跑通过」的可复现表述；合入前在低负载环境补一次 integration 全量或受影响文件级绿证。

### t061_test_f002 - AC-001「不占宽度」只有 DOM 不渲染证据，无真实布局宽度断言

- 严重度：minor
- 锚点：AC-001
- 位置：`src/frontend/src/features/browser-session/SessionDetailsPanel.test.tsx:203`；`src/frontend/src/features/browser-session/SessionPage.tsx:271`
- 问题：关闭态证据是 jsdom 中 `queryByTestId(SESS_DETAILS_PANEL)` 为 null；可测试性声明称「真实 Chrome 布局断言可自动化」、测试策略称「真实 Chrome 自动化验证布局宽度」，但交付中无任何布局/宽度测量断言，e2e 在云端按跳过登记。结构上结论成立（面板关闭返回空片段、SessionPage 外层 wrapper div 无宽度类），故仅记 minor：宽度结论由结构推得，非测得。
- 建议：本地 e2e 线验证 AC-006/AC-008 时顺带补一条关闭/打开前后内容区宽度实测断言，或把可测试性声明改为与 DOM 级证据一致的口径。

### t061_test_f003 - AC-004 中文与详情侧覆盖不完整：中文仅测 ready、详情侧缺失值兜底未测

- 严重度：minor
- 锚点：AC-004
- 位置：`src/frontend/src/features/browser-session/SessionHeader.test.tsx:263`；`src/frontend/src/features/browser-session/SessionDetailsPanel.test.tsx:191`
- 问题：中文界面断言只覆盖 ready→「正常」一条；recovering/failed/unknown 的中文渲染、以及详情面板在 transport 缺失/枚举外值时回落本地化 unknown，均无测试（顶栏侧枚举外值 `half_open` 回落已测、详情侧仅测 en ready 且断言不含原始 `ready`）。缓解事实：zh/en 词典四词条齐备（`src/frontend/src/i18n.tsx:496-499,973-976`），顶栏与详情共用同一 `transport_state.ts` 映射，缺口是覆盖广度而非行为分叉。
- 建议：补参数化用例：zh 四态各一条（顶栏或详情任一表面）+ 详情侧枚举外值回落一条。

### t061_test_f004 - AC-007「失败原因不含凭据」无任何断言支撑

- 严重度：minor
- 锚点：AC-007
- 位置：`docs/tasks/t061_session_ui_clarity/progress.md:44`（实施自述「现行文案即如此，未改」）；全 diff 无对应测试
- 问题：AC-007 其余部分有组合证据（reconnecting 轻量指示 vs connected 无等待层、`useBrowserSession.wsRecovery.test.tsx` 健康恢复后 `errorMessage` 为 null），但「失败原因不含凭据」只剩实施自述。diff 未改动任何错误文案，风险低，故记 minor 而非阻断；该子句目前是未测声明。
- 建议：补一条断言：故障态渲染的错误文案/诊断行不含凭据类字段（如 token/password/resume_key 字样或 fixture 中的凭据值）。

## 结论

- 改测方向复核：无「就地把旧预期改成新实现输出」的迁就式改测。逐处核对：SessionDetailsPanel「关闭仍保留容器」与内部开关用例整体删除并在测试注释与 progress.md 测试替换登记中写明理由（AC-001 取代）；SessionStagePanel 全阶段居中面板/全阶段重连断言整体替换为等待/故障矩阵并写明理由（AC-002/AC-003 取代 364d191 契约）；session_stage_panel_connected.test.tsx 的 A40 两例由 media_waiting 整体移至 ice_failed 并写明理由（等待态已无诊断表，A40 的叶子更新属性保留在诊断态验证）；SessionHeader 原始机器码断言改为本地化文案且新增「不展示原始值」与枚举外回落断言，属规格变更驱动而非追随输出。特别审查一处：runtime_not_ready 由旧断言「提供重连」改为「无重连」——实施理由已登记（AC-003 对该态只枚举启动与状态提示、重连只会重载回未就绪态），锚定 AC 枚举而非静默追随，判定合法；其规格解释本身属 code/spec 轴，本轴不另出 finding。
- 危险模式扫描：改动测试文件中无恒真断言、无 `.skip`/`.only`、无注释掉断言、无 `eslint-disable`/`@ts-ignore`、无阈值放宽；弱化方向仅见反向强化（多处新增 `not.toContain` 原始值/缺席断言）。`SessionDetailsPanel.test.tsx:236` 的 `toBeTruthy` 为基线既存、未在本 diff 改动且非 AC 证据，不出 finding。wsRecovery 测试只在系统边界替身（iframe 的 `__getWebRTCStats`、ApiClient runtime 查询）并用可控 fake timer 驱动真实 hook，未 mock 被测逻辑本身。
- 门禁非绿独立复核（实跑）：受影响 7 个前端测试文件 92/92 passed；门禁 frontend_test 的 4 个超时失败文件单跑 23/23 passed，flaky 定性成立；unit 唯一失败在本 worktree 单跑复现（`GatewayTopologyHarness.data_dir` AttributeError，2.41s），且本 diff 不触后端/测试文件，基线既存定性成立；integration 见 f001。manifest 如实记录 unit/integration/frontend_test 为 failed、e2e/real_engine 未列入 suites，progress.md 对 [deploy] 真实链明确登记未验顺延，未发现把未验冒充已验。
- 本轮新发现：4 条（均为 minor）
- 未进表的提示：AC-006 的真实 Chrome 链与 AC-008 的无 viewer 保留真实验收仍须在合入前于本地（Mac Docker/Chrome）执行，这是 progress.md 已登记的顺延项，不在本轮云端证据内。
- 总体判断：新语义（等待态矩阵、开关唯一性与持久化、本地化与兜底、WS 恢复四分支）均有真实、可独立重跑的测试支撑，被替换旧测试均为整体替换并写明理由；仅存 4 条 minor 证据精度/覆盖广度问题。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。独立重跑 SessionPage.test.tsx 与 SessionDetailsPanel.test.tsx 通过：开关全页唯一（getAllByTestId 长度 1 且位于页头）、localStorage 持久化跨重挂载、关闭后面板不渲染、无内部标题/第二开关；宽度为结构推得（见 f002）。
- AC-002：TICK-VALID，re_verified。SessionStagePanel.test.tsx 四等待态参数化断言（仅轻量指示、无 diagnostics testid、无操作区、无按钮）与 connected 不渲染均独立重跑通过；connecting_ice 遗留分支已随 StageKey 删除（frontend_build 门禁通过）。
- AC-003：TICK-VALID，re_verified。五故障态保留诊断卡+重连+查看状态且无启动、runtime_not_ready 为启动+查看状态无重连、stopping 仅查看状态，独立重跑通过。
- AC-004：TICK-VALID，re_verified。顶栏 en 四态本地化+不展示原始值、枚举外 `half_open` 回落、zh ready、详情侧 en ready 本地化均独立重跑通过；覆盖广度缺口见 f003。
- AC-005：TICK-VALID，re_verified。EnvironmentSwitcher.test.tsx 独立重跑通过：触发器不含运行状态、下拉条目保留状态；diff 确认仅服务触发器徽标的 `useProfileRuntimeQuery` 已删除。
- AC-006：TICK-VALID，re_verified。新增 useBrowserSession.wsRecovery.test.tsx 4 分支（健康收敛且 snapshot 不变、reloadKey 不变、errorMessage 清除；不健康走重建；旧 generation 迟到健康结果不覆盖；后端停止忽略）独立重跑 4/4 通过；[deploy] 真实 Chrome 链部分按登记顺延、未冒充已验。
- AC-007：TICK-VALID，re_verified。正在恢复（reconnecting 轻量指示）与已经恢复（connected 无等待层、wsRecovery 断言 errorMessage 为 null）可区分且独立重跑通过；「不含凭据」子句无断言，见 f004。
- AC-008：TICK-VALID，trust_prior。依赖实施侧对后端 stream_agent/policy.py 的核查登记与本 reviewer 的 diff 检查：本 diff 不触后端、无新增计时器/停止/删除生命周期调用（负向不变量成立）；真实链保留验收属 [deploy]，云端未执行、已如实登记顺延。

coverage = 7 / 8

verdict: PASS
