---
tid: "t061"
slug: "session_ui_clarity"
title: "会话界面与断线重连修复"
status: "done"
branch: "t061_session_ui_clarity"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "c5f83296ece80a9a0ed9f1e48d957ce332f858c4"
depends_on: ""
conflicts_with: "t062,t063,t064,t065,t066,t069"
note: "合并 t067；来源 p061/p064/p065 及 p079/p083 断线范围；无人连接保留环境，不新增生命周期功能"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-13 审阅修订：采纳视觉契约冲突和遗漏测试意见；AC-001..005 保持编号，AC-002 明确四个等待态，AC-003 单列 runtime_not_ready/stopping。

- 本次仅维护 backlog；不 start、不实现；旧归档来源只追加转办链，不改写历史。

- 调度字段经 task.py edit 写入；plan 的 runnable 只指依赖/冲突候选，不代表产品 BLOCKING 已解决。

- 调度依据：会话视觉与断线恢复已合为同一交付；与服务/媒体/鉴权/代理/数据/严格输入任务存在页面接线或同链 E2E 修改冲突，图字段已改指合并目标。

- 合并确认：用户已明确批准 t067 合入 t061；会话视觉 AC-001..005 保留，t067 AC-001/006/008 分别映射到本 task AC-006/007/008；其余已取消功能不并入。

- 2026-11-13 云端实施（attempt 1，worktree CBrowser_t061，基线 c5f8329 含 364d191）：

    - SPIKE 已结（结论回填 task.md 未知契约）：真实 hook + 可控 timer 复现成功——已连接后异常 WS 关闭、stats 恒健康且 ConnectionSnapshot 不变时，5 秒恢复检查的健康分支无动作、诊断源因快照不变不发信号，阶段永久卡 reconnecting（`useBrowserSession.wsRecovery.test.tsx` 首跑 1 failed/3 passed，失败点与预测一致）。根因是恢复检查缺健康收敛出口，不是 timeout 或 fence 失效；不健康、迟到 generation、后端停止三个负向分支现行行为均正确。
    - AC-006：`useBrowserSession.ts` 的 5 秒恢复检查补健康收敛——stats.connected 且当前有效阶段仍为 reconnecting 时 setStage("connected") 并清错误文案；检查入口新增一道 generation fence（stats 返回后的一道为基线既有，两道在交付代码中均在位）；不健康沿用既有 reconnect 重建；不触碰 adapter 的 resume_key/client_tab_id 语义。修复后 wsRecovery 4/4 通过。
    - AC-002/AC-003：`SessionStagePanel.tsx` 按阶段矩阵重写——等待态（checking_runtime/connecting_signaling/media_waiting/reconnecting）只渲染轻量指示（spinner+阶段文案，无诊断表、无操作区）；故障态（signaling_failed/ice_failed/media_no_frames/web_locks_unavailable/error）保留诊断卡+重连+查看状态；runtime_not_ready 为启动+查看状态（去掉重连：运行时未运行时重连只会把 viewer 重载回同一未就绪态，适用恢复是启动——此点与旧测试断言不同，按 AC-003 枚举「保留启动与状态提示」执行）；stopping 为查看状态only。删除组件遗留的 `connecting_ice` StageKey 扩展（AC-002 明确其不属于 SessionStage；`docs/blueprint/frontend.md` 第 4 节的阶段清单与呈现契约同步改写，理由见下）。
    - AC-001：`SessionDetailsPanel.tsx` 删除内部「详情」标题行与第二开关（SESS_DETAILS_TOGGLE 只剩页头一处）、删除 onOpenChange prop（SessionPage 同步摘除传参）；open=false 时面板直接不渲染，w-details 固定宽容器不再保留。开关状态仍由 SessionPage 经 `cbrowser.session.details_open` 持久化。
    - AC-004：i18n 新增 transportStateReady/Recovering/Failed/Unknown 四词条（en: Ready/Recovering/Failed/Unknown；zh: 正常/恢复中/失败/未知，zh ready 用「正常」依 p065 用户原话）；新增 `transport_state.ts` 单一映射（label key + tone，未知/缺失/枚举外值回落 unknown 词条），SessionHeader 徽标与 SessionDetailsPanel 的 transport_state 行共用，详情行由 mono 原值改本地化文案（复制值=所见文案，与 integrity 等本地化行一致）。
    - AC-005：`EnvironmentSwitcher.tsx` 触发器删除状态徽标，只显环境名；同时删除仅服务该徽标的当前环境 `useProfileRuntimeQuery` 查询。下拉条目的逐环境状态徽标与 itemRuntimes 查询保留。顶栏运行状态只剩 SessionHeader 的 observed 徽标一处。
    - AC-007：随 AC-006 收敛落地——诊断呈现以阶段为准区分正在恢复（reconnecting 轻量指示）与已经恢复（connected 且无等待层残留、错误文案已清）；失败原因文案不含凭据（现行文案即如此，未改）。
    - AC-008：核查后端 stream_agent/policy.py——现行只有「全部 viewer 后台/断开时暂停采集编码」的 consumer 仲裁，无任何按无人连接/时间停止、重置或删除环境的逻辑；本 task 不新增此类逻辑，前端亦无。云端可验部分到此为止，真实链验证属 [deploy]，见跳过登记。
    - 测试替换登记（按 task.md 测试策略整体替换、禁止改旧预期追随输出）：
        1. `SessionStagePanel.test.tsx`：删除「全部非 connected 阶段均渲染居中面板+按钮」与「除 stopping/reconnecting 外全阶段提供重连」两组旧断言（364d191 视觉契约，被 AC-002/AC-003 取代）、删除 connecting_ice 字面量用例（非阶段）；新写等待态轻量、故障态矩阵、runtime_not_ready 无重连等断言。原「media_waiting 显示诊断行」用例改在 ice_failed 上验证诊断行（诊断内容本身未变，只是等待态不再承载）。
        2. `session_stage_panel_connected.test.tsx`（A40）：两例由 media_waiting 改到 ice_failed 验证 source 样本喂入面板与叶子级更新——A40 的属性（高频样本只更新叶子、不触发宿主重渲染）不变，等待态已无诊断表可喂。
        3. `SessionDetailsPanel.test.tsx`：删除「关闭仍保留容器」断言与「面板内部开关 toggles through onOpenChange」用例（AC-001 取代）；新写关闭不渲染、无内部标题/第二开关；「四区渲染」用例中 transport 原值 "ready" 断言改本地化文案（AC-004）。
        4. `SessionPage.test.tsx`：详情开关定位由面板内部改页头，并新增全页唯一性断言与「关闭后面板不渲染」用例（AC-001）。
        5. `SessionHeader.test.tsx`：transport 原值断言改本地化文案，新增枚举外值回落与中文界面用例（AC-004）。
        6. `EnvironmentSwitcher.test.tsx`：触发器含运行状态的旧断言改「触发器无状态、下拉条目保留状态」（AC-005）。
        7. 新增 `useBrowserSession.wsRecovery.test.tsx`（AC-006 SPIKE 复现转回归，4 例）。
    - blueprint 同步（超出 task.md Finalization 清单的一项，已在此登记理由）：`docs/blueprint/frontend.md` 第 4 节是阶段清单与呈现契约的权威出处，其「全部非 connected 阶段居中面板」「connecting_ice 字面量分支保留」与 AC-002 直接冲突，不改则权威文档与交付自相矛盾，故同步改写为新矩阵；task.md 清单内的 testing.md（新增 t061 验证小节）与 architecture.md（5.1 新增「长驻 Browser 与连接恢复的职责边界」）亦已更新。spec 更新 `docs/specs/webrtc_remote_display.md` 并在 specs_index 登记 t061。
    - 环境与门禁口径（云端，如实登记）：
        1. worktree 缺 `.scratch/selkies_wheels` 缓存（gitignored 不随 worktree 走），按门禁脚本自身的带外填充提示从主仓克隆复制 selkies-2.2.1 wheel（SHA256 与期望值一致）后环境阶段通过。
        2. 工具链缺陷（未改工具链、未静默绕过，结论已上报父 agent）：默认入口 `scripts/run_gates.sh` 经 `scripts/gate_run.py` 运行时，gate_run.py 恒置 `CBROWSER_GATE_RUNS_DIR`，内层脚本在任何 suite 之前无条件调用 `cleanup_containers`，其 `gate_container_cleanup.py` 在无 Docker 的云端连接失败返回 1，被内层 `set -e` 放大为整场门禁在首个 suite 前退出（实测两轮均如此，environment 阶段本身通过）。本轮改走脚本自带的 `CBROWSER_GATE_ENV_READY=1` 直跑分支（与 gate_run.py 内部拉起内层脚本的同一路径，venv 已由 gate_run.py 首轮建好并校验），不设 RUNS_DIR 时 cleanup 按其自身「no run registry」路径返回 0；全部 suite 本体、证据模式与 manifest 机制不变。Docker 清理在无 Docker 且无 gate 容器时本就无对象。
        3. jpeginfo 供给与 Node 版本交互（环境问题，非本 task 改动所致）：`ensure_jpeginfo` 按 PATH 先命中 /usr/bin/jpeginfo（云端系统装 1.7.1），把 /usr/bin 前置 PATH 后遮蔽 Node 26（/usr/bin/node 为 24.22.1），frontend_test/frontend_build 首轮因此 exit 1（check:node 拒绝）。按 d040 契约支持的 scratch 副本方式，将 jpeginfo 复制到 worktree `.scratch/t061-bin/` 并置于调用 PATH 最前，ensure 校验通过后前置该目录，Node 解析恢复 26.13.0 后重跑。
        4. e2e 与 real_engine 未运行：云端无 Docker，按本仓口径跳过、按 pass 计；AC-006/AC-008 的 [deploy] 真实链部分同样未验，留待本地 e2e 线（Mac Docker/Chrome）在合入前验证——本 task 不以其未验冒充已验，打勾口径为「实现完成且云端可验部分已验，deploy 链验证显式顺延并在此登记」。
    - 门禁实跑（证据模式，manifest 在 worktree `.scratch/gate_evidence_20261113/manifest.json`，GATE_EXIT=1）：protocol_drift_check PASS、requirements_check PASS、contract 257 passed/1 skipped PASS、design_lint PASS、design_check PASS、frontend_build PASS；unit 并行 1991 passed/1 failed/1 skipped＋串行 64 passed（exit 1）；integration 并行 173 passed/7 skipped/15 errors＋串行 4 passed（exit 1）；frontend_test 623 passed/4 failed（exit 1）。三处非绿均已逐项定性，与本 task 改动（仅前端组件/hook 与文档，零后端改动）无关：
        1. unit 唯一失败 `test_t060_gate_boundaries.py::test_local_topology_profile_does_not_require_public_geoip`（GatewayTopologyHarness.data_dir AttributeError）：单跑复现（2.6s），且在主仓 pristine c5f8329（工作区干净）同法单跑同样失败（1.61s、同错误）——基线既存失败，非本 task 引入；不在 t061 范围内修，留主线基线处置。
        2. integration 15 个 error 全部为 `isolated API process did not become ready`（门禁时 load average 4.5+、1.5 共享 CPU 且多 agent 并行）；复核证据：受影响 6 个文件合跑 13 passed/2 errors，余下 test_normal_exit_replay.py 单独跑实施侧一次 4 passed、test reviewer 独立重跑一次 3 passed/1 error（同型就绪超时），该 error 用例再单独成测重跑 1 passed（15.42s）——文件级结果随负载波动、逐例隔离均可通过，属子进程就绪超时型负载 flaky，如实登记。
        3. frontend_test 4 个失败全部为 5000ms 超时（profiles 的 ConfigTab/ProfileCreateDialog/ProfileForm、settings 的 SettingsPage，均非 browser-session）：受影响 4 文件单跑 23/23 passed；此前全量单跑 `npm test` 为 627/627 全过——超时 flaky，如实登记。
        4. 首两轮门禁的环境性失败（selkies wheel 缺失、/tmp ENOSPC 致 unit 21 failed＋integration 4 errors、jpeginfo 前置 /usr/bin 遮蔽 Node 26）已分别经带外填充 wheel、CBROWSER_GATE_SCRATCH 落工作区磁盘、scratch jpeginfo 副本三法消除，定稿轮次即上述实数；ENOSPC 轮的失败不计入定稿。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-13T21:50:24+08:00)

双路独立 review 均 PASS（code 轴报告 review_code.md、test 轴报告 review_test.md）；AC 复验合计 16 项次全部 TICK-VALID、无 TICK-VOID。finding 5 条均为 minor，处置如下。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t061_code_f001|minor|遗留|SessionDetailsPanel 内容块缩进停留在旧层级，纯格式无行为影响；审后修改会使双路 review 指纹失效，收益低于重审成本，转 follow-up 顺手对齐|p091|
|t061_test_f001|minor|已修|progress.md 对 integration 复核的表述高估证据强度，已按实施侧与 reviewer 双侧实测改写为「文件级随负载波动、逐例隔离均通过」|progress.md 实施笔记（门禁实跑条目 2）|
|t061_test_f002|minor|遗留|AC-001「不占宽度」缺真实 Chrome 布局宽度断言，属本地真实链补验范围，与 AC-006/AC-008 的 deploy 补验同批处理|p090|
|t061_test_f003|minor|遗留|AC-004 中文其余三态与详情侧兜底断言为覆盖广度补强；实现共用单一映射、行为已由顶栏侧断言与词典完备性覆盖|p091|
|t061_test_f004|minor|遗留|AC-007「失败原因不含凭据」缺显式断言，为覆盖广度补强；错误文案为固定 i18n 文案仅以关闭码为参数，风险低|p091|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（AC-006/AC-008 的 [deploy] 真实链部分按登记顺延本地补验，见 p090）
- 测试：证据模式全量门禁（manifest 在 worktree `.scratch/gate_evidence_20261113/`）：protocol_drift/requirements/design_lint/design_check/frontend_build PASS，contract 257 passed/1 skipped；unit 1991+64 passed、1 failed（t060 topology 用例，主仓 pristine 基线同法复现、非本 task 引入）；integration 173+4 passed、15 errors（子进程就绪超时型负载 flaky，逐例隔离复核均通过）；frontend_test 623 passed/4 failed（5000ms 超时 flaky，受影响文件单跑 23/23、全量单跑 627/627）。本 task 直接相关测试：browser-session 22 文件 181 例全过（双路 reviewer 独立复跑一致），含新增 wsRecovery 4 例。
- 黑盒：云端无 Docker，e2e 与 real_engine 未运行、按本仓口径跳过按 pass 计；AC-006/AC-008 的真实 Chrome/Stream 黑盒验证顺延本地（Mac）合入前补验，已登记 p090，不以组件测试替代其结论。
- review：Round 1 双路 PASS（code 轴 1 minor、test 轴 4 minor，均为 minor）；AC 复验 16 项次全部 TICK-VALID、无 TICK-VOID；5 条 finding 处置见上表（1 已修、4 遗留至 p090/p091）。
- AC 判定：见 `task.md` 行内打勾（8/8）

### 结果摘要

- 会话阶段呈现按矩阵分级（等待态轻量指示、故障态诊断+适用动作），详情面板收敛为页头唯一开关的纯内容容器，transport 状态顶栏与详情统一本地化，环境切换器触发器去徽标，信令异常后媒体健康可凭 5 秒恢复检查收敛回 connected；AC-006/AC-008 真实链补验见 p090，测试广度与格式 follow-up 见 p091，unit 基线失败（t060 topology）留主线处置。

### 长期文档闭环

- specs_index：`webrtc_remote_display` 行已登记 t061（最后更新 2026-11-13），spec 正文新增「会话阶段呈现与断线恢复收敛（t061）」节并同步前端会话各条；blueprint 已同步 `frontend.md` 第 4 节（阶段清单与呈现矩阵、恢复收敛、详情面板与本地化）、`testing.md`（新增 t061 验证小节）、`architecture.md`（5.1 长驻 Browser 与连接恢复职责边界）。
