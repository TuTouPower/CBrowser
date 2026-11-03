# bundle_local_archive_tasks

## responsibilities

- docs/archive/ 是 v2 改造的只追加证据层：handoff.md 累积叙事、tasks/{tid}/ 任务账本（task.md 契约与 AC 勾选、note.md 过程总账与 Review 处置表、review_code.md/review_test.md 双轴报告、handoff.json 机器收尾记录）、pending/ 已归档遗留项、specs/ 已废弃规格、tasks_index.json 状态索引（自声明权威在各 note.md front matter）。
- 本单元的核心问题是闭环完整性：每个 done 的完成声明是否被自身证据支撑、遗留是否都有在册去向、归档记录与当前代码/实况是否一致。

## interfaces

- task.py / pending.py 维护的归档流程：finish/drop 由脚本移入 archive，note.md front matter 为状态权威，tasks_index.json 由脚本生成。
- 跨账本引用链：finding id（tNNN_code/test_fNNN）→ note 处置表 → pNNN pending 或 follow-up tid；handoff.json 的 pending/findings 字段与之呼应。

## dependencies

- 归档账本大量引用账本外证据：.scratch/ 下的门禁日志、编排 JSONL、验证 worktree 证据（均未入库，cleanup 后不可复查），以及 docs/findings/d001-d026、docs/reviews/review_20261102_201727/adoption_decision.md。
- 余项去向依赖 live 状态：docs/tasks/t009/t010/t012 与 docs/pending/todo/p016-p019（本次已逐项对照）。

## flows

- 典型闭环：实施 → 独立黑盒 Verify → full 双轴 review 多轮 → finding 逐项处置（已修/遗留 pNNN/撤回+理由）→ 收尾报告 → finish 归档。本单元逐个任务核对了这条链的每一环。
- 豁免流：t001 首创 NOT_RUN/USER_WAIVED 单列（公网、原生 Linux x86），经 scope_adjustment.md 留档原契约，后续任务继承引用，口径一致。

## constraints

- 仓规：docs/archive/ 内部文件只准新增；归档 spike/spec 字节不可变，因此账本内错误只能以勘误节纠正（多份账本确有 errata 节）。
- AGENTS.md 审查约束：critical/important 未解决不得 PASS；遗留必须指向 pNNN 或 follow-up tid。

## decisions

- 用户决策留痕较完整：t001 两项环境豁免（授权原文留档）、t011 并入 t010（adoption 审批，live t010 以 AC-006~009 承接并标注来源）、t014 drop（AC-002/003/004 转 t009 手动清单 AC-003，p015 transferred）、t018 删除 CI 与并行双跑要求。
- 审查预算纪律：t016 在 tasks_index 中显式记录 review_limit 5->6 及理由；t018 无此记录（见 finding f_archive_tasks_02）。

## evidence

- 正向核实：A25 结构性拆分在当前代码属实（recovery_coordinator 已拆 _observe_profiles/_scan_containers/_classify_abnormal_exits/_schedule_retries；container_spec/volume_spec/network_spec 已提取；stream_agent/messaging.py 存在），p001/p005 的实体结论成立。
- 正向核实：t014→p015→live t009 AC-003 手动清单链完整；t011→live t010 AC-006~009 承接完整；t015-t018 余项分别落 live p016/p017/p018/p019，无悬空。
- 正向核实：t008/t013 时期被用户搁置的 2 个 contract 失败（test_task_archive_dir）在 t015 起的门禁记录中已消失（contract 169 passed），搁置是限时的且有披露。
- 正向核实：全部归档文件未发现凭据明文值（token/secret 字面量扫描为空；规格中使用 <redacted> 占位；仅有秘密文件路径与环境痕迹，见 f_archive_tasks_09）。

## uncertainties

- 账本引用的 .scratch 证据（门禁日志、黑盒原始 JSON、编排 JSONL）不在仓库内，本次只能核对账本间相互一致性与当前代码实况，无法复核原始日志本身。
- p006（agent_secret 挂进 Browser 容器）以 A5 关闭、p008 以具体 commit 关闭：二者的实体修复在后端/监督器单元的审查范围内，本单元仅核对了其归档记录与处置链形式完整，未独立复核挂载代码。
- t017 黑盒栏明示未重跑 Docker E2E（由 t015 真实拓扑与 t018 覆盖收口）：其 AC 以 Vitest/构建/类型门禁支撑，本单元按其声明口径接受，未另行判定。

## Findings

- [Medium][95] docs/archive/tasks/t018_v2_test_gates_hygiene/task.md:43 — t018 的 AC-004 在从未执行其自声明必需验证的情况下打勾关闭（trust_prior）
  - ID: f_archive_tasks_01; verification: static
  - Evidence: task.md 可测试性声明（:43）：「AC-004 的单次资源隔离需真实 Docker 跑一轮门禁验证」；AC-004 本体（:30）已勾 [x]。; note.md 收尾报告（:135）：「结果：全部满足；AC-004 为 trust_prior（真实 Docker 单次门禁未在本环境执行）」；黑盒栏：「默认 E2E 19 passed / 62 skipped……完整 Docker/Chrome E2E 未执行」。; handoff.json blackbox：「Full Docker/Chrome E2E not executed in this environment; AC-004 relies on static checks and prior implementation evidence (trust_prior)」；必需模式仅做了 collection 检查（exit 2 列出 9 个缺失前置），从未绿跑。; 对照同仓兄弟任务的一贯口径（如 t003/t005 task.md：「缺失时保持未通过，不用模拟替代」），AC-004 应保持未勾并单列未运行，而非计入「全部满足」。
  - Impact: t018 是后续所有任务的门禁基线任务，其 AC-004（端口/显示号/容器名派生、仅回环绑定、单次门禁资源隔离）恰是防测试互相污染的核心保证；以 trust_prior 打勾使「门禁可信」的根声明有一条未经实测，后续任务引用该基线时证据强度被高估。披露是诚实的，但勾选与结论口径不符。
  - Fix: 将 AC-004 改回未勾并标注 NOT_RUN（或在真实 Docker 环境补跑一轮 run_gates.sh 必需模式后补记证据再勾）；收尾结论改为「AC-004 未验证」而非「全部满足」。

- [Medium][90] docs/archive/tasks/t018_v2_test_gates_hygiene/note.md:53 — t018 的 Review 处置表退化为样板文本，且 19 轮审查超出记录上限 5 轮无授权留痕、attempt 2 无记录
  - ID: f_archive_tasks_02; verification: static
  - Evidence: note.md 的处置表（:53 起「Round 19」）约 68 行中，除 f017/f029 撤回与 test_f021 遗留外，其余每行 severity 均为模板字面量「critical/important/minor」、rationale 均为同一句「Round 19 全量 diff 复核通过」、fix_ref 均为「b02df0b」；Rounds 1-18 在账本中没有任何处置行。; note.md front matter（:9-10）与 tasks_index.json 均记录 review_limit=5、verify_limit=5；review_code.md 实际有 Round 13/16/17/18/19 等共 16 个 Round 节，最终 Round 19 PASS。账本全文未记录上限上调或用户批准（对照 t016 在 tasks_index 中显式记录「review_limit: 5->6」及理由）。; handoff.json（:3）显示 attempt=2，而 note.md 通篇没有 attempt 1 的任何记录或重启说明。; 细节并未丢失：review_code.md/review_test.md 内有逐条真实 severity 与逐轮 verdict（含多轮 FAIL），故这是账本层处置记录失效，而非审查本身缺失。
  - Impact: note.md 处置表是 finish 门禁与后续读者核对「每个 finding 如何关闭」的第一入口；t018 的表无法回答任何单条 finding 的 severity 与关闭方式，且预算/attempt 账目与实际不符，削弱整套任务账本制度的可审计性。
  - Fix: 按 review_code/review_test 原文为 t018 补齐逐条处置行（真实 severity、各自 rationale 与 fix_ref）；在 note 中补记 review_limit 上调的批准依据与 attempt 2 的起因（若确无批准，应如实记录为流程偏差）。

- [Low][90] docs/archive/tasks/t015_v2_media_link_simplification/note.md:58 — t015 两条 test finding 在处置表标「已修」，但测试审查者连续三轮记录残余未消除且无后续去向
  - ID: f_archive_tasks_03; verification: static
  - Evidence: note.md 处置表（:58-59）：t015_test_f005、t015_test_f006 均标「已修」。; review_test.md Round 3（:163-164）、Round 4（:231）、Round 5（:277-278）反复记录：「t015_test_f005 minor 残余仍在……只断言重启发生且首次退避为 [1.0]，未断言错误日志与 2/4/8 秒递增退避」「t015_test_f006 minor 残余仍在……未覆盖 timeout 完成路径」，且 Round 3 前轮复核（:196）明言「f005、f006 主体已修，minor 残余仍在」。; t015 唯一的遗留 pending p016 只承接 f007/f012/f013；live p017/p018/p019 分别是 t016/t017/t018 的余项，均不承接这两条残余。
  - Impact: 两处测试覆盖深度缺口（退避日志与递增间隔断言、超时完成路径断言）被账面关闭后无任何在册跟踪，后续触及 Stream 监督循环或会话超时逻辑时不会再被提醒补测。
  - Fix: 将两条残余改记为遗留并登记到 live pending（或在 note 处置表中把状态改为「主体已修，残余遗留」并指向承接项）。

- [Low][95] docs/archive/tasks/t015_v2_media_link_simplification/note.md:105 — t015 的 note 收尾与 handoff.json 仍称「Round 2 PASS」，与实际 6/5 轮、且 Round 3 曾推翻该 PASS 的过程不符
  - ID: f_archive_tasks_04; verification: static
  - Evidence: note.md 收尾报告（:105）：「review：full code/test 两路 Round 2 均 PASS」；handoff.json（:10）：「Full code/test review Round 2 PASS both axes」。; review_code.md Round 3 发现 post-Round-2 修复引入 critical 回归（Stream 镜像漏 COPY secret_files.py，Agent 启动即失败），总体判断 FAIL 并明言「Round 2 的 PASS 不再成立」（:240）；其后经 Round 4-6（code）与 Round 3-5（test）复审才最终 PASS，处置表亦延伸到 Round 5/6。; 最终关闭本身有 Round 6/Round 5 PASS 支撑，不是无证关闭；问题仅在两处摘要记录停留在 Round 2。
  - Impact: 收尾报告与 handoff.json 是归档后最先被查阅的两处摘要，读者会误以为 t015 只经两轮审查且无 critical 回归史，低估该任务实际的风险与修复过程。
  - Fix: 将 note 收尾与 handoff.json 的 review 字段更正为最终轮次与 scope（code Round 6 / test Round 5 PASS，并注明 Round 3 曾因镜像回归 FAIL）。

- [Low][90] docs/archive/pending/p011_t007_test_minor_followups.md:9 — p011 以 resolved 关闭，但其 f012 子项自认未做且在 live 文档中无任何承接
  - ID: f_archive_tasks_05; verification: static
  - Evidence: p011 处置行（:9）：resolution=resolved，reason 末尾明言「f012 的 test_frontend_session_e2e 状态断言不在本轮文件所有权内」——即三条子项中 f011/f013 已做、f012 未做。; 对照 live 状态：docs/tasks/、docs/pending/todo/p016-p019、docs/handoff.md 中均无 t007_test_f012 的任何引用（本次 grep 核实）；该子项针对的宽松断言字符串在当前 tests/e2e/test_frontend_session_e2e.py 中已不存在（文件其后被改写），但无任何账本把这一消失与 f012 关联，属无声 moot。
  - Impact: 归档 pending 的 resolved 语义被稀释：子项未完成时应保持开放或拆分登记；现在的记录使「p011 全部关闭」与事实不符，且 f012 是已做、被他处覆盖还是被放弃，三种可能都无从判定。
  - Fix: 在 p011 记录中补注 f012 的最终去向（若已被后续改写覆盖，注明覆盖提交/任务；若放弃，注明决策），或将其重新登记为 live pending。

- [Low][95] docs/archive/pending/p001_supervisor_recovery_tick_complexity.md:5 — p001 的关闭理由与 p005 逐字相同，是以 p005 为主语的批量关闭文本
  - ID: f_archive_tasks_06; verification: static
  - Evidence: p001（:5）与 p005（:11）的「处理」行逐字一致，文本主语是「p005 的 f001/f002/f003 与复杂度项均已在 main 闭环」；p001 本体是 RecoveryCoordinator.tick 复杂度（t005_code_f001），其关闭理由没有一条以自身为对象陈述证据。; 实体结论经本次对照当前代码属实：recovery_coordinator.py 已拆出 _observe_profiles/_scan_containers/_classify_abnormal_exits/_schedule_retries，container_spec.py/volume_spec.py/network_spec.py 已提取，stream_agent/messaging.py 存在——故这是记录质量问题，不是虚假关闭。
  - Impact: 批量粘贴的关闭理由使单项审计时无法从 p001 自身记录确认其关闭依据；若 A25 的某一子项日后被发现未落地，无法从记录区分受影响的是 p001 还是 p005。
  - Fix: 为 p001 补写以自身为对象的关闭说明（tick 拆分的具体方法与所在文件），与 p005 的记录脱钩。

- [Low][90] docs/archive/tasks/t006_v2_gateway_auth_rtc/note.md:147 — t006 的 AC-001 在其 master-token 条款为空满足时整条打勾关闭
  - ID: f_archive_tasks_07; verification: static
  - Evidence: note.md AC 证据节（:119）：「『master token 不返回前端』：当前 Stream 未配置任何 Selkies token，属空满足，见 p004（t007 前定案）」；收尾报告（:147）自认「AC-001 的 master token 条款为空满足」，而 task.md 中 AC-001 已勾 [x]、结论为「全部满足」。; 该条款的真实交付在下一个任务：p004 由 t007 AC-010 完成（Selkies master/controller token，d024），p004 已归档 resolved——最终结果无缺口，问题在 t006 关闭时点的勾选口径。
  - Impact: AC 勾选语义被稀释为「本任务内能做的都做了」；若 p004 未被 t007 承接，这条安全条款（master token 不得出现在前端）会无声丢失。当时靠 p004 登记兜底，未造成实际遗漏。
  - Fix: 口径上应将此类 AC 标为部分满足并在 task.md 行内注明条款转 p004，而非整条打勾后仅在 note 中说明。

- [Low][95] docs/archive/tasks/t011_v2_remove_legacy/note.md:46 — 两个 dropped 任务的自有账本仍是未填写的模板，t014 还缺 handoff.json
  - ID: f_archive_tasks_08; verification: static
  - Evidence: t011 note.md 收尾报告仍为模板原文（:46「结果：全部满足 / 未满足」、测试/黑盒/review 均为「待执行时填写」），处置表只剩模板示例行；其 drop 依据只在 front matter 的 note 字段「merged into t010」与 tasks_index.json 中。实体承接是完整的：live t010 task.md 已把 t011 的 AC-001~004 编为 AC-006~009 并标注 adoption 来源。; t014 note.md 收尾报告同样为模板原文（:78），且 t014 是 16 个归档任务中唯一没有 handoff.json 的；其 drop 决策记录在 front matter note、tasks_index.json、archive handoff.md 与 p015→live t009 AC-003 中，链条完整但本账本内无一字收尾。
  - Impact: 归档账本自身不自洽：只读 archive 的人无法从 t011/t014 的 note.md 得知任务终局与决策，必须跨查 index、handoff 与 live 任务才能拼出，与「note.md 为任务过程总账」的定位不符。
  - Fix: 为 t011/t014 的 note.md 补一节简短的 drop 收尾（决策时间、决策人、承接位置），或至少把模板收尾段替换为指向承接记录的说明。

- [Low][90] docs/archive/handoff.md:289 — 公开仓库的归档区集中留存开发者环境痕迹，且 t018 的路径隐私守卫按设计把归档区排除在外
  - ID: f_archive_tasks_09; verification: static
  - Evidence: 本次扫描（仅计位置与种类，不抄值）：38 个归档文件含开发者本机绝对路径（/Users/karson/kar/code/…，如各 review_*.md 的 target 行）；6 个文件含共 69 个 OpenCode 会话 id；多处含进程 PID、Docker 网桥 IP（如 coturn relay 地址）、宿主机能力备注（t001 note 中唯一 x86_64 机器的内存/swap 与使用限制）；handoff.md（:289、:345）记录了生产管理员密码的文件路径（仅路径）。; 全仓未发现任何凭据明文值（token/secret 字面量扫描为空，规格中使用 <redacted>）。; t018 AC-007 的隐私守卫只覆盖「已跟踪的非归档文本文件」，note 中亦记录「路径隐私守卫纳入 reviews（历史文件 allowlist）」——即以白名单豁免历史文件，而非清理归档本身。
  - Impact: 该仓为公开 fork：开发者用户名、本机目录结构、内部拓扑与运维细节随归档长期公开，且守卫的范围设计使这类痕迹今后仍会随新归档持续累积。无凭据值泄露，故定级 Low。
  - Fix: 将路径隐私守卫扩展到 docs/archive/（或在归档时对本机路径/会话 id 做脱敏替换）；对存量归档做一次路径与会话 id 的批量脱敏。

- [Info][95] docs/archive/specs/chrome_external_tabs.md:1 — 归档 spec chrome_external_tabs 的 5 条 AC 全部未勾且文件内无 superseded 标记
  - ID: f_archive_tasks_10; verification: static
  - Evidence: 该 spec 的 5 条 AC 均为未勾选状态，其 ControlSession 租约模型与 t007 实际交付形态不同；它被移入 archive 的事实只记录在 t007 note.md 的长期文档闭环一节（「旧 chrome_external_tabs（控制租约模型）移入 docs/archive/specs/」），spec 文件本身没有任何已废弃/被替代的标注。
  - Impact: 只读归档 spec 的人无法判断它是未完成的需求还是已被替代的历史设计，可能被误当作待实现契约引用。
  - Fix: 在 spec 文首补一行 superseded 标注，指向 t007 与现行 webrtc_remote_display spec。

- [Info][95] docs/archive/tasks/t008_v2_artifacts_automation/note.md:41 — 多份归档账本保留模板示例行，污染 finding id 空间
  - ID: f_archive_tasks_11; verification: static
  - Evidence: t008 note.md（:41）与 t013 note.md（:39）的 Review 处置表中都保留着模板示例行「t000_code_f001 | critical/important/minor | 已修/遗留/撤回 | 一句话 | 文件:行 / pNNN / tid」；t011/t014 的账本中亦然（见 f_archive_tasks_08）。
  - Impact: 纯文档卫生问题：自动解析处置表的工具会读到一条不存在的 finding；也反映收尾时未做账本清理。
  - Fix: 删除各归档账本中的模板示例行（归档只追加的仓规下，可在各 note 末尾以勘误方式声明该行为模板残留）。

## views

```json
{
  "security": {
    "status": "completed",
    "reviewer": "33b303ad-eff4-4f19-8c5c-64286314b87f"
  },
  "correctness": {
    "status": "completed",
    "reviewer": "33b303ad-eff4-4f19-8c5c-64286314b87f"
  },
  "contracts": {
    "status": "completed",
    "reviewer": "33b303ad-eff4-4f19-8c5c-64286314b87f"
  },
  "performance": {
    "status": "completed",
    "reviewer": "33b303ad-eff4-4f19-8c5c-64286314b87f"
  },
  "design": {
    "status": "completed",
    "reviewer": "33b303ad-eff4-4f19-8c5c-64286314b87f"
  },
  "robustness": {
    "status": "completed",
    "reviewer": "33b303ad-eff4-4f19-8c5c-64286314b87f"
  },
  "tests": {
    "status": "completed",
    "reviewer": "33b303ad-eff4-4f19-8c5c-64286314b87f"
  },
  "documentation": {
    "status": "completed",
    "reviewer": "33b303ad-eff4-4f19-8c5c-64286314b87f"
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
  "docs/archive/pending/p014_v2_upload_picker_access.md",
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
  "docs/archive/tasks/t011_v2_remove_legacy/note.md",
  "docs/archive/tasks/t011_v2_remove_legacy/task.md",
  "docs/archive/tasks/t013_v2_profile_copy_reset/handoff.json",
  "docs/archive/tasks/t013_v2_profile_copy_reset/note.md",
  "docs/archive/tasks/t013_v2_profile_copy_reset/review_code.md",
  "docs/archive/tasks/t013_v2_profile_copy_reset/review_test.md",
  "docs/archive/tasks/t013_v2_profile_copy_reset/task.md",
  "docs/archive/tasks/t014_v2_clipboard_input/note.md",
  "docs/archive/tasks/t014_v2_clipboard_input/review_code.md",
  "docs/archive/tasks/t014_v2_clipboard_input/review_test.md",
  "docs/archive/tasks/t014_v2_clipboard_input/task.md",
  "docs/archive/tasks/t015_v2_media_link_simplification/handoff.json",
  "docs/archive/tasks/t015_v2_media_link_simplification/note.md",
  "docs/archive/tasks/t015_v2_media_link_simplification/review_code.md",
  "docs/archive/tasks/t015_v2_media_link_simplification/review_test.md",
  "docs/archive/tasks/t015_v2_media_link_simplification/task.md",
  "docs/archive/tasks/t016_v2_backend_hardening/handoff.json",
  "docs/archive/tasks/t016_v2_backend_hardening/note.md",
  "docs/archive/tasks/t016_v2_backend_hardening/review_code.md",
  "docs/archive/tasks/t016_v2_backend_hardening/review_test.md",
  "docs/archive/tasks/t016_v2_backend_hardening/task.md",
  "docs/archive/tasks/t017_v2_frontend_convergence/handoff.json",
  "docs/archive/tasks/t017_v2_frontend_convergence/note.md",
  "docs/archive/tasks/t017_v2_frontend_convergence/review_code.md",
  "docs/archive/tasks/t017_v2_frontend_convergence/review_test.md",
  "docs/archive/tasks/t017_v2_frontend_convergence/task.md",
  "docs/archive/tasks/t018_v2_test_gates_hygiene/handoff.json",
  "docs/archive/tasks/t018_v2_test_gates_hygiene/note.md",
  "docs/archive/tasks/t018_v2_test_gates_hygiene/review_code.md",
  "docs/archive/tasks/t018_v2_test_gates_hygiene/review_test.md",
  "docs/archive/tasks/t018_v2_test_gates_hygiene/task.md",
  "docs/archive/tasks_index.json"
]
```
