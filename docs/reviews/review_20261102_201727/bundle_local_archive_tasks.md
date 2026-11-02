# bundle_local_archive_tasks

## responsibilities

- 归档区 docs/archive/ 是已完结工作的终局记录面：按 AGENTS.md 约定镜像原路径、内部文件只准新增；保存 t001–t008、t013（done）与 t014（dropped）的完整 task 簿（task/note/review_code/review_test/handoff.json，t014 无 handoff.json）、已闭环 pending p001–p013 与 p015、被替代的 spec chrome_external_tabs.md、历次 live handoff 的过时快照，以及 tasks_index.json。
- 每个归档 task 簿自带可核对的终局证据链：task.md 的 AC 勾选、note.md 的逐轮 Review 处置表（finding→已修/遗留/撤回+fix_ref）、review_code/review_test 的多轮 verdict、handoff.json 的 status/tests/blackbox/review/pending/findings 摘要。
- 归档 pending 每条带「处理：<fix_ref>；resolution=resolved|transferred；reason=...」终局行，fix_ref 具体到 commit（如 p007 d7aeb01、p009/p011/p013 同为 323efaa）或 2026-11-01 审阅采纳项编号（如 p006=A5、p012=A8、p001/p005=A25、p011=A28）。

## interfaces

- docs/archive/tasks_index.json 声明权威来源为各 task note.md front matter 的 status；已核对 t001–t008/t013=done、t014=dropped 与各 note front matter 一致。
- handoff.json 的 pending 链与归档 pending 对应：t005.pending=[p001]、t006.pending=[p003,p004,p005]、t007.pending=[p005–p013]、t008.pending=[p014]（p014 仍在 live docs/pending/todo/，未归档，状态一致）、t013.pending=[]。
- 归档记录向 live 侧的出口指针：p015 transferred→t009 手动清单（已存在性核对：docs/tasks/t009_v2_full_acceptance/task.md:27 AC-003 手动清单、:44 记录用户决定）、t013_code_f014 遗留→t009、t007 note 的长期文档闭环指向 live specs/blueprint/findings d024。

## dependencies

- 依赖 live 侧承接者真实存在：t009（backlog，承接 p015 与 t013 f014）、p014（live todo，承接 t008 文件选择器可达性）。
- p001/p005/p006/p011/p012 的闭环理由引用 live 侧 docs/reviews/review_20261101_075819/adoption_decision.md 的 A 项编号（属 docs_current 单元），本单元只能核对引用形式，不能核对 A 项内容本身。
- 依赖 AGENTS.md 的归档纪律（pending 已闭环才迁入、live handoff 只留最新一节、废弃 spec 移入 archive/specs）作为判定基准。

## flows

- task 终局流程：实施→多轮 full review（FAIL→修复→复核）→note 处置表逐项销账→finish 后整簿迁入 docs/archive/tasks/，handoff.json 汇总测试/黑盒/评审结论与未闭环 pending 引用。
- pending 终局流程：task 遗留登记 pNNN→后续 task 或 adoption 修复→pending.py archive 迁入 docs/archive/pending/ 并写 resolution 行。
- handoff 轮转流程：live docs/handoff.md 只留最新一节，过时段落整段追加迁入 docs/archive/handoff.md（归档文件 1406 行，首节标题为「项目交接记录（归档）」，其后混有多节原样保留「（最新）」标题的历史快照）。
- t014 特殊流：部分交付随 e7f58ce 合入 main→用户决定 drop→AC-002/003/004 经 p015 transferred 转 t009 手动验收，task 簿以 dropped 状态归档。

## constraints

- 归档纪律（AGENTS.md）：归档区镜像原路径、内部只准新增；pending 必须已闭环才可迁入；未闭环项必须在 live 侧留有承接者。
- Review 处置规则（各 note 模板）：遗留必须指向 pNNN 或 follow-up tid；撤回必须写清理由；critical/important 未解决不得 PASS。
- 凭据纪律在归档内得到遵守：全部 68 个文件未发现任何凭据明文值；handoff.md 仅出现管理员密码的文件路径（相对路径 data/secrets/admin_password），从未出现值。

## decisions

- t014 dropped（用户决定，2026-11-02）：AC-001/005 已合入 main，AC-002/003/004 单人使用不做自动化 E2E、改由 t009 手动清单验收，剪贴板改 seamless 同步另行处理；决定同时记录于 t014 note front matter、tasks_index.json 的 t014 note 字段与归档 handoff 最后一节，三处一致。
- t001 review 的 code_f001/f002 经复核为 reviewer 误读而撤回，更正记录同时存在于 note 处置表与 review_code.md；code_f003 遗留指向 t006。
- t008_test_f009、t013_test_f012/f017 以「覆盖扩展」名义撤回并写了理由；t013_code_f014 明确遗留 t009，未随归档消失。
- 归档 spec chrome_external_tabs 的控制租约模型被 t007 的新会话模型替代，t007 finalization 时移入 archive/specs（t007 note 长期文档闭环有记载）。

## evidence

- docs/archive/pending/p011_t007_test_minor_followups.md:9 — resolution=resolved 的同一行 reason 承认 f012「不在本轮文件所有权内」未做
- docs/archive/pending/p001_supervisor_recovery_tick_complexity.md:5 与 docs/archive/pending/p005_t006_review_minors.md:11 — 两条 resolution reason 逐字相同
- docs/archive/specs/chrome_external_tabs.md:31-35 — 五条 AC 全部未勾选，文件内无废弃/替代标记
- docs/archive/handoff.md:100,164,217 — 本机绝对路径 /Users/karson/kar/code/...；全文共 32 处；:33,45,64 含 OpenCode session id 与 PID；:250,278,289 仅提及管理员密码文件路径（无值）
- docs/archive/handoff.md:437,1121,1163,1203,1240,1276 — 归档内多节标题仍为「# 项目交接记录（最新）」
- docs/archive/tasks/t013_v2_profile_copy_reset/note.md:98 — 收尾报告写 reviewed_scope=68994e2bb7fa7d48，而两份 review 的 Round 5 终局指纹为 3b90f37ed20afe31
- docs/archive/tasks/t014_v2_clipboard_input/note.md:78-86 — 收尾报告仍为未填写的模板占位（「全部满足 / 未满足」「待执行时填写」）
- docs/archive/tasks/t008_v2_artifacts_automation/note.md:76 — t008_test_f009 撤回理由含「避免终审后改测导致 scope 失效」
- docs/tasks/t009_v2_full_acceptance/task.md:27,44（live 侧存在性核对）— p015 transferred 的承接清单真实存在；docs/pending/todo/ 仅有 p014、docs/pending/parked/ 为空 — p011 的 f012 余项在 live 侧无任何在册跟踪
- docs/specs_index.md（live）全文无 chrome_external_tabs 条目 — 索引侧已摘除，仅归档文件本身缺废弃标记

## uncertainties

- t001_code_f003（Gateway 恢复探针固定 sleep 轮询、建议生产用事件通知）遗留指向 t006，但 t006 簿内是否落实无法在本单元内确认（t006 review 未逐项回引该条），需 synthesis 结合 live 代码/其他单元判定。
- p001/p005/p006/p011/p012 引用的 adoption A 项（A5/A8/A25/A28）与 fix commit 是否与理由描述完全一致，属 live 侧 adoption_decision.md 与 git 历史的核对范围（docs_current 单元/synthesis），本单元仅核对了引用形式与内部一致性。
- p011 的 f012（test_frontend_session_e2e 容器状态断言收紧）在当前 live 测试文件中是否已被顺带收紧，未核对（属 tests_e2e_supervisor/tests_e2e_stream_frontend 单元）；本单元只确认流程记录层面它被标 resolved 且无 live pending 承接。
- 归档 handoff.md 中大量 .scratch/ 证据路径与 session/PID 均为历史运行痕迹，无法静态核对其现时有效性，仅按隐私/可读性记录。

## Findings

- [Medium][95] docs/archive/pending/p011_t007_test_minor_followups.md:9-9 — p011 标 resolution=resolved 归档，但其 reason 自认三子项之一（f012）未做且 live 侧无任何承接
  - ID: f_archive_tasks_01; verification: static
  - Evidence: p011 处理行：resolution=resolved；reason 写明 A28 只补齐 f011（SSE 失效重取 Vitest）与 f013（audio_status 透传），并明说「f012 的 test_frontend_session_e2e 状态断言不在本轮文件所有权内」; p011 正文（:8）原计划为「下次改前端会话或 SSE 的 task 内补齐」，属开放式后续安排，与 resolved 终局状态矛盾; 存在性核对：live docs/pending/todo/ 只有 p014_v2_upload_picker_access.md，docs/pending/parked/ 为空，f012 余项（session E2E 接受 created 状态、宜收紧为 running）在 live 侧无 pending/task 在册跟踪
  - Impact: 归档读者会认为 t007 三项测试遗留全部闭环，实际 f012 的弱断言（关闭页面后容器状态接受 created，无法区分未停止与被重建）在记录层面被静默丢弃，违反「pending 已闭环才迁入归档」的纪律。
  - Fix: 把 p011 的 resolution 改为 partial 并在 reason 中明确剩余项，或在 live docs/pending/todo/ 重新登记 f012 余项并在 p011 中留指针。

- [Low][90] docs/archive/pending/p001_supervisor_recovery_tick_complexity.md:5-5; docs/archive/pending/p005_t006_review_minors.md:11-11 — p001 与 p005 的 resolution reason 逐字相同，p001 的闭环理由以 p005 为主语，且 p005 未交代其 test_f001 子项
  - ID: f_archive_tasks_02; verification: static
  - Evidence: 两文件处理行 reason 完全一致：「A25 完成结构性拆分：recovery tick 按 observe/classify/schedule 拆分；docker_adapter 提取…；p005 的 f001/f002/f003 与复杂度项均已在 main 闭环」; p001 文件内出现以 p005 为主语的闭环理由，p001 自身的 tick 拆分虽被同一句覆盖，但形式上是复制粘贴而非逐项销账; p005 正文含五个子项（code_f001–f004 与 test_f001 四个 Supervisor E2E 内联重复 coturn 启动代码抽夹具），reason 只枚举 f001/f002/f003 与「复杂度项」，test_f001 无任何交代
  - Impact: 归档闭环理由不可逐项审计：无法从记录判断 p005 的 test_f001 是否已处理，也削弱其余 adoption 引用型闭环（A5/A8/A28）的可信度。
  - Fix: 为 p001/p005 分别补写以自身子项为主语的 reason，并明确 test_f001 的处置（已抽夹具/未做及去向）。

- [Low][90] docs/archive/specs/chrome_external_tabs.md:31-35 — 归档 spec 五条 AC 全部未勾选且文件内无废弃/替代标记，单看文件像一份现行未完成契约
  - ID: f_archive_tasks_03; verification: static
  - Evidence: AC-001 至 AC-005 均为「- [ ]」，内容含每 5 秒心跳、15 秒断开、30 秒重连窗口等控制租约条款，文件通篇无 deprecated/superseded 说明或替代文档指针; live docs/specs_index.md 已无该条目、live docs/specs/ 亦无此文件（索引侧处理正确），替代关系仅记录在 t007 note 的长期文档闭环一笔（「旧 chrome_external_tabs（控制租约模型）移入 docs/archive/specs/」）
  - Impact: 只读归档文件的读者（或后续检索）无法判断该租约模型已被 t007 会话模型替代，可能误按已废弃契约实现或评估。
  - Fix: 在归档 spec 顶部加归档头注：废弃日期、替代文档（docs/specs/webrtc_remote_display.md 等）与迁入来源 task（t007）。

- [Low][85] docs/archive/handoff.md:100-100 — 归档 handoff 通篇含开发者本机绝对路径、用户名与 agent 会话/PID 等个人与运维标识
  - ID: f_archive_tasks_04; verification: static
  - Evidence: 全文 32 处出现 /Users/karson/kar/code/... 形式的本机绝对路径（如 :100、:164、:217、:343、:376），暴露开发者用户名与目录结构; :33、:45、:64 等处含 OpenCode session id（ses_…）、进程 PID 与 owner_id；另多处提及用户记忆目录路径; :250、:278、:289 出现管理员密码文件路径（相对路径 data/secrets/admin_password）——仅路径、无任何凭据值，全部 68 个归档文件均未发现凭据明文
  - Impact: 仓库源头是公开 fork（CloakHQ/CloakBrowser-Manager），归档文档随仓公开时会带出开发者本机用户名、目录布局与历史会话标识；无凭据值泄露，故定级 Low。
  - Fix: 归档前对 handoff 做一次脱敏（本机路径改相对/占位、session id 与 PID 删除），或在仓库发布策略中明确接受该暴露并记录。

- [Low][95] docs/archive/tasks/t014_v2_clipboard_input/note.md:78-86 — t014 已 dropped 归档，但 note.md 收尾报告仍是未填写的模板占位，终局结果只存在于 front matter 与索引
  - ID: f_archive_tasks_05; verification: static
  - Evidence: 收尾报告「结果：全部满足 / 未满足」「测试/黑盒/review：待执行时填写」「结果摘要：待执行时填写」均为模板原文，未按 drop 实际结果回填; t014 的实际终局（AC-001/005 随 e7f58ce 合入、AC-002/003/004 转 t009、用户 drop 决定）只记录在 front matter 的 note 字段与 tasks_index.json 的 note 字段；且 t014 无 handoff.json; 对照：其余归档 task（t001–t008、t013）的收尾报告均已回填验收/测试/review 三项
  - Impact: 按统一收尾格式阅读归档时，t014 看起来像从未执行完的半成品，drop 的事实与去向需要跨 front matter 和索引拼接才能还原。
  - Fix: 回填 t014 收尾报告：结果写 dropped 及用户决定日期、三项验证写已合入部分的评审结论（review 两轮记录在 review_code/review_test.md）、遗留只写 p015/t009 引用。

- [Low][90] docs/archive/tasks/t013_v2_profile_copy_reset/note.md:98-98 — t013 收尾报告引用的 reviewed_scope 是 Round 4 的旧指纹，与两份 review 的 Round 5 终局指纹不一致
  - ID: f_archive_tasks_06; verification: static
  - Evidence: note.md:98 写「reviewed_scope=68994e2bb7fa7d48」（Round 4 指纹）; review_code.md 与 review_test.md 的 Round 5 终局 verdict 均绑定 reviewed_scope 3b90f37ed20afe31；test reviewer Round 5 明确指出 note 收尾报告仍写旧指纹、建议同步，未见后续修正
  - Impact: 归档收尾摘要指向已被取代的评审范围，按该指纹回查会得到与最终交付不一致的评审绑定，削弱归档证据链的精确性。
  - Fix: 把 note.md 收尾报告的 reviewed_scope 更新为 3b90f37ed20afe31 并注明 Round 5 终局。

- [Low][80] docs/archive/tasks/t008_v2_artifacts_automation/note.md:76-76 — t008_test_f009 的撤回理由含流程便利因素（避免终审后改测使 scope 失效），其测试缺口无后续跟踪
  - ID: f_archive_tasks_07; verification: static
  - Evidence: note Round 2 处置表：t008_test_f009 状态=撤回，理由为「255 字符截断属防御性边界；已有 4xx 重试与 API schema 覆盖，单独单测收益低，且避免终审后改测导致 scope 失效」; 该 finding 由 test reviewer 在 Round 3 提出（长文件名截断无测试，截断被移除时 422 会被永久标记 processed 而丢下载），撤回后既未补测，也未登记 pending 或 follow-up; 对照同簿其他遗留均有明确去向（p014），此项是唯一以撤回形式消失且无承接者的测试缺口
  - Impact: 撤回在此被用作绕开终审后 scope 冻结的出口，而非问题不成立的裁决；缺口本身（截断逻辑无回归测试）在记录层面不再可见。
  - Fix: 把该缺口登记为 live pending 或在撤回理由中删除流程便利表述并明确接受风险的依据。

- [Info][95] docs/archive/handoff.md:437-437 — 归档 handoff 内混有多节标题为「项目交接记录（最新）」的历史快照，与归档定位冲突易误读
  - ID: f_archive_tasks_08; verification: static
  - Evidence: 文件首行标题为「# 项目交接记录（归档）」，但 :437、:1121、:1163、:1203、:1240、:1276 等至少六节仍以「# 项目交接记录（最新）」为题，是历次 live handoff 被整段迁入时未改标题的快照; 各快照内容为当时的进行中状态（如某 task active、待用户决策），与文件尾部最新一节（2026-11-02T20:00）的状态并不一致
  - Impact: 从文件中间落地的读者可能把某一历史快照当成当前交接状态；属可读性/误导风险，无事实错误。
  - Fix: 迁入时把快照标题统一改为「项目交接记录（归档快照，<时间>）」，或在文件头加目录说明各节的时间与性质。

## views

```json
{
  "contracts": {
    "reviewer": "d2a5c252-2e09-4aa4-80a9-ab9a7efaa826",
    "status": "completed"
  },
  "correctness": {
    "reviewer": "d2a5c252-2e09-4aa4-80a9-ab9a7efaa826",
    "status": "completed"
  },
  "design": {
    "reviewer": "d2a5c252-2e09-4aa4-80a9-ab9a7efaa826",
    "status": "completed"
  },
  "documentation": {
    "reviewer": "d2a5c252-2e09-4aa4-80a9-ab9a7efaa826",
    "status": "completed"
  },
  "performance": {
    "reason": "本单元全部为归档文档与流程记录（task 簿、pending、handoff 快照、索引），不含可执行代码或运行时路径，无性能/资源行为面；归档内提及的性能事项（如 t013_code_f014 遗留 t009）已按契约视角核对去向。",
    "reviewer": "d2a5c252-2e09-4aa4-80a9-ab9a7efaa826",
    "status": "not_applicable"
  },
  "robustness": {
    "reviewer": "d2a5c252-2e09-4aa4-80a9-ab9a7efaa826",
    "status": "completed"
  },
  "security": {
    "reviewer": "d2a5c252-2e09-4aa4-80a9-ab9a7efaa826",
    "status": "completed"
  },
  "tests": {
    "reviewer": "d2a5c252-2e09-4aa4-80a9-ab9a7efaa826",
    "status": "completed"
  }
}
```

## files_reviewed

```json
[
  "docs/archive/handoff.md",
  "docs/archive/pending/p001_supervisor_recovery_tick_complexity.md",
  "docs/archive/pending/p002_policy_failure_test_conditional_asserts.md",
  "docs/archive/pending/p003_api_supervisor_start_wiring.md",
  "docs/archive/pending/p004_selkies_profile_tokens.md",
  "docs/archive/pending/p005_t006_review_minors.md",
  "docs/archive/pending/p006_browser_runtime_agent_secret_mount.md",
  "docs/archive/pending/p007_frontend_i18n_residue.md",
  "docs/archive/pending/p008_stream_agent_selkies_resume.md",
  "docs/archive/pending/p009_e2e_multi_viewer_fixed_sleep.md",
  "docs/archive/pending/p010_frontend_build_selkies_vendor_wiring.md",
  "docs/archive/pending/p011_t007_test_minor_followups.md",
  "docs/archive/pending/p012_stream_tokens_eviction_close_race.md",
  "docs/archive/pending/p013_ac001_static_frames_flake.md",
  "docs/archive/pending/p015_t014_input_clipboard_e2e.md",
  "docs/archive/specs/chrome_external_tabs.md",
  "docs/archive/tasks/t001_v2_runtime_validation/handoff.json",
  "docs/archive/tasks/t001_v2_runtime_validation/note.md",
  "docs/archive/tasks/t001_v2_runtime_validation/review_code.md",
  "docs/archive/tasks/t001_v2_runtime_validation/review_test.md",
  "docs/archive/tasks/t001_v2_runtime_validation/scope_adjustment.md",
  "docs/archive/tasks/t001_v2_runtime_validation/task.md",
  "docs/archive/tasks/t001_v2_runtime_validation/validation_matrix.md",
  "docs/archive/tasks/t002_v2_backend_foundation/handoff.json",
  "docs/archive/tasks/t002_v2_backend_foundation/note.md",
  "docs/archive/tasks/t002_v2_backend_foundation/review_code.md",
  "docs/archive/tasks/t002_v2_backend_foundation/review_test.md",
  "docs/archive/tasks/t002_v2_backend_foundation/task.md",
  "docs/archive/tasks/t003_v2_browser_runtime/handoff.json",
  "docs/archive/tasks/t003_v2_browser_runtime/note.md",
  "docs/archive/tasks/t003_v2_browser_runtime/review_code.md",
  "docs/archive/tasks/t003_v2_browser_runtime/review_test.md",
  "docs/archive/tasks/t003_v2_browser_runtime/task.md",
  "docs/archive/tasks/t004_v2_stream_runtime/handoff.json",
  "docs/archive/tasks/t004_v2_stream_runtime/note.md",
  "docs/archive/tasks/t004_v2_stream_runtime/review_code.md",
  "docs/archive/tasks/t004_v2_stream_runtime/review_test.md",
  "docs/archive/tasks/t004_v2_stream_runtime/task.md",
  "docs/archive/tasks/t005_v2_supervisor/handoff.json",
  "docs/archive/tasks/t005_v2_supervisor/note.md",
  "docs/archive/tasks/t005_v2_supervisor/review_code.md",
  "docs/archive/tasks/t005_v2_supervisor/review_test.md",
  "docs/archive/tasks/t005_v2_supervisor/task.md",
  "docs/archive/tasks/t006_v2_gateway_auth_rtc/handoff.json",
  "docs/archive/tasks/t006_v2_gateway_auth_rtc/note.md",
  "docs/archive/tasks/t006_v2_gateway_auth_rtc/review_code.md",
  "docs/archive/tasks/t006_v2_gateway_auth_rtc/review_test.md",
  "docs/archive/tasks/t006_v2_gateway_auth_rtc/task.md",
  "docs/archive/tasks/t007_v2_frontend_sessions/handoff.json",
  "docs/archive/tasks/t007_v2_frontend_sessions/note.md",
  "docs/archive/tasks/t007_v2_frontend_sessions/review_code.md",
  "docs/archive/tasks/t007_v2_frontend_sessions/review_test.md",
  "docs/archive/tasks/t007_v2_frontend_sessions/task.md",
  "docs/archive/tasks/t008_v2_artifacts_automation/handoff.json",
  "docs/archive/tasks/t008_v2_artifacts_automation/note.md",
  "docs/archive/tasks/t008_v2_artifacts_automation/review_code.md",
  "docs/archive/tasks/t008_v2_artifacts_automation/review_test.md",
  "docs/archive/tasks/t008_v2_artifacts_automation/task.md",
  "docs/archive/tasks/t013_v2_profile_copy_reset/handoff.json",
  "docs/archive/tasks/t013_v2_profile_copy_reset/note.md",
  "docs/archive/tasks/t013_v2_profile_copy_reset/review_code.md",
  "docs/archive/tasks/t013_v2_profile_copy_reset/review_test.md",
  "docs/archive/tasks/t013_v2_profile_copy_reset/task.md",
  "docs/archive/tasks/t014_v2_clipboard_input/note.md",
  "docs/archive/tasks/t014_v2_clipboard_input/review_code.md",
  "docs/archive/tasks/t014_v2_clipboard_input/review_test.md",
  "docs/archive/tasks/t014_v2_clipboard_input/task.md",
  "docs/archive/tasks_index.json"
]
```
