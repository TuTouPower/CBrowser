# Task review t061（reviewer_focus: 代码）

- task：`t061_session_ui_clarity`
- spec：`docs/tasks/t061_session_ui_clarity/task.md`
- diff_anchor：`c5f83296ece80a9a0ed9f1e48d957ce332f858c4`
- target：`git -C '<home>/workspace/CBrowser_t061' diff c5f83296ece80a9a0ed9f1e48d957ce332f858c4`
- round：1
- reviewed_at：2026-11-13T21:48:24+08:00

reviewed_scope: c5fe8b9c25e5b811

## Findings

### t061_code_f001 - SessionDetailsPanel 内容块缩进停留在已删除的条件渲染层级

- 严重度：minor
- 锚点：行为缺陷（无行为影响；删除 `{open && (...)}` 条件渲染后遗留的缩进不一致，属代码风格/可读性）
- 位置：`src/frontend/src/features/browser-session/SessionDetailsPanel.tsx:175`
- 问题：`if (!open) return <></>;` 提前返回后，原条件块内的内容 `<div className="flex flex-col gap-lg overflow-y-auto">` 及其子内容仍保持旧的一层深缩进（第 175 行起至文件尾的 `</aside>` 前），与 aside 直接子元素的层级不符；仓内无 prettier 门禁兜底，后续编辑易在此基础上继续错位。
- 建议：把该内容块整体回退一层缩进与 aside 子元素对齐（纯格式调整，不动任何 JSX 结构与文案）。

## 结论

- 本轮新发现：1 条（minor 1；critical 0 / important 0）
- 未进表的提示：
    - 文件过大（按标准只列结论段）：`src/frontend/src/features/browser-session/useBrowserSession.ts` 662 行（实现源码 ≥400 行建议拆分阈值，本 task 净增 9 行）；`src/frontend/src/i18n.tsx` 1048 行（翻译词条表，本 task 净增 8 行四词条 en/zh）；`src/frontend/src/features/browser-session/SessionPage.test.tsx` 732 行（测试源码 ≥600 行建议拆分阈值，本 task 净增约 24 行）。三者均未达 important 阈值，且未见由体量直接导致的行为不一致，不进 finding 表。
    - 圈复杂度：本 task 新增/改写的函数（`stageActions`、`transportStateLabelKey`、`transportStateTone`、WS 关闭恢复回调新增分支）手算 CC 均 \<10，无提示项。
    - 观察（不构成 finding）：故障态（ice_failed、error）在基线 `LAUNCH_STAGES` 中除重连/查看状态外还有 launch，本次矩阵改写后 launch 仅保留给 runtime_not_ready，且新测试显式断言故障态 never launch。AC-003 对故障态只要求「诊断及适用重连动作」、仅对 runtime_not_ready 明列「启动」，blueprint/frontend.md 与 specs 已同步为新矩阵，故按已批准契约的文义不判偏航；仅在此登记该行为收窄已核对过。
    - 观察（不构成 finding）：progress.md 称恢复检查「入口与 stats 返回后各加一道 generation fence」——经 `git show` 核对基线，stats 返回后的一道（基线 `useBrowserSession.ts` 原文）在基线已存在，本次实际新增的是入口一道；交付代码中两道 fence 均在位（`useBrowserSession.ts:523` 与 `:531`），结论不受影响，仅实施笔记措辞略有夸大。
    - 观察（不构成 finding）：详情面板 transport_state 行的复制值随显示改为本地化文案（基线复制原始机器码），progress.md 已披露且与「不展示原始机器码」的 AC-004 口径一致，接受。
    - 门禁三处非绿的实施侧定性已独立复核成立：unit 唯一失败 `test_t060_gate_boundaries.py::test_local_topology_profile_does_not_require_public_geoip` 在 pristine 锚点临时 worktree 与交付 worktree 同法单跑均为同一 `AttributeError`（`tests/fixtures/gateway_probe/topology.py:655`），系基线既存、非本 task 引入；frontend_test 4 个超时失败文件（ConfigTab/ProfileCreateDialog/ProfileForm/SettingsPage）单跑复核 23/23 全过，与全量负载超时定性一致；integration 15 errors 抽查 `test_normal_exit_replay.py` 单跑 4/4 全过，与子进程就绪超时定性一致。e2e/real_engine 云端无 Docker未跑，按仓内口径跳过。
    - 安全/契约/性能七视角已逐项扫过：diff 无外部输入拼接执行、无新增 `dangerouslySetInnerHTML`（唯一命中是 wsRecovery 测试 afterEach 的 `document.body.innerHTML = ""` 清理）、无凭据落盘/进日志；`SessionDetailsPanel` 删除 `onOpenChange` prop 的唯一消费方 SessionPage 已同步，全仓无其他消费方；性能上净删除一处仅服务徽标的 runtime 查询，无新增循环查询。
- 总体判断：实现层逐条对齐 AC-001..008 的契约矩阵，无未解决 critical/important；AC-006/AC-008 的 [deploy] 真实链部分云端不可验，实施侧已如实登记顺延、未冒充已验，合并前仍须在本地（Mac Docker/Chrome）补跑该两条的真实链验证。
- 系统性 follow-up：无本 task 新增系统性缺口。基线既存失败 `test_t060_gate_boundaries.py::test_local_topology_profile_does_not_require_public_geoip` 属主线基线问题（锚点即红），由主线基线处置，不在本 task 范围。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。代码核对：`SessionDetailsPanel.tsx:166` 关闭返回空片段不渲染、内部标题行与第二开关已删，`SESS_DETAILS_TOGGLE` 全仓仅 SessionHeader 一处；持久化经 `cbrowser.session.details_open`（SessionPage.tsx:36/104/139 读写同键）；browser-session 全套 181 测试复跑全过。
- AC-002：TICK-VALID，re_verified。`SessionStagePanel.tsx:41-46` WAITING_STAGES 恰为四等待态，仅渲染 spinner+阶段文案（无诊断表 testid、无操作区），connected 返回空片段；`connecting_ice` 已从组件类型与 STAGE_TITLE_KEYS 删除，全仓仅剩文档中的否定式历史表述。
- AC-003：TICK-VALID，re_verified。`SessionStagePanel.tsx:59-68` stageActions 矩阵：故障五态默认 reconnect+view-status 并保留诊断卡，runtime_not_ready 为 launch+view-status，stopping 仅 view-status；SessionPage.tsx:254-261 三回调均真实接线（reconnect/导航/onLaunch 启动 mutation）。
- AC-004：TICK-VALID，re_verified。新增 `transport_state.ts` 单一映射（label+tone，未知/缺失/枚举外回落 unknown 词条），SessionHeader 徽标与 SessionDetailsPanel 详情行共用；i18n en/zh 四词条齐备（zh ready=「正常」）；复跑的 SessionHeader/SessionDetailsPanel 测试含枚举外值「half_open」不泄漏断言且通过。
- AC-005：TICK-VALID，re_verified。`EnvironmentSwitcher.tsx` 触发器仅渲染环境名、StatusBadge 已删；仅服务该徽标的当前环境 `useProfileRuntimeQuery` 已移除，下拉条目仍经 itemRuntimes + currentStatus 显示各环境状态（同文件 :164/:180 在位）。
- AC-006：TICK-VALID，re_verified。`useBrowserSession.ts:520-545` 恢复检查补入口 generation fence（:523）、stats 返回后 fence（:531），健康且有效阶段仍为 reconnecting 时收敛 connected 并清错误文案、不触 reloadKey，不健康沿用 reconnect；独立复跑 `useBrowserSession.wsRecovery.test.tsx` 4/4 通过（健康收敛/不健康重建/迟到 generation/后端停止四分支）。[deploy] 真实 Chrome 链部分云端未验，progress.md 已显式登记顺延至本地 e2e，未冒充已验。
- AC-007：TICK-VALID，re_verified。恢复中（reconnecting 轻量指示）与已恢复（connected 无等待层、errorMessage 已清）呈现可区分由 AC-002/AC-006 实现直接支撑；diff 全量 grep 无 password/secret/token/credential 引入，失败文案均为既有 i18n 词条。
- AC-008：TICK-VALID，re_verified。完整 diff 零后端改动、前端无新增任何 idle/TTL/停止/重置/删除逻辑（diff grep 仅命中文档表述），后端 stream_agent/policy.py 的 consumer 采集暂停为基线既有且未被触碰；本 task 的义务（不新增回收逻辑、保留既有暂停行为）在交付内容上可独立核实。[deploy] 无 viewer 真实保留链云端未验，progress.md 已显式登记顺延，未冒充已验。

coverage = 8 / 8

verdict: PASS
