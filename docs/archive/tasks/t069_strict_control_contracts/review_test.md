# Task review t069（reviewer_focus: 测试）

- task：`t069_strict_control_contracts`
- spec：`docs/tasks/t069_strict_control_contracts/task.md`
- diff_anchor：`501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90`
- target：`git -C '<home>/workspace/CBrowser_t069' diff 501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90`
- round：1
- reviewed_at：2026-11-14T05:59:28+08:00

reviewed_scope: a38f0719a1a0bd19

## Findings

### t069_test_f001 - 四条 AC 全部未打勾，打勾真实性无从成立

- 严重度：important
- 锚点：AC-001、AC-002、AC-003、AC-004 全部；契约区规则「未打勾（`- [ ]`）的 AC 一律记 TICK-VOID」
- 位置：`docs/tasks/t069_strict_control_contracts/task.md:28`、`task.md:29`、`task.md:30`、`task.md:31`
- 问题：交付状态下 task.md 四条 AC 均为 `- [ ]` 未勾选（git status 中 task.md 亦无修改）。progress.md 实施笔记自述「AC-003 为 [deploy]，按云端口径不打勾」，但 AC-001/002/004 同样未打勾，progress.md「收尾报告」仍是「待执行时填写」占位。按契约区与复验规则，未打勾即 TICK-VOID，与测试本身是否真实无关，本轮四条 AC 全部标 TICK-VOID，verdict 必为 FAIL。
- 建议：实施方在确认交付内容与门禁证据后，按契约就地打勾 AC-001/002/004（AC-003 为 [deploy]，按其顺延口径处置并在 progress.md 收尾报告中写清），再走下一轮复审。

### t069_test_f002 - viewer 入口 selkies_adapter_entry.ts 的拒绝逻辑零测试覆盖

- 严重度：important
- 锚点：AC-004「viewer 缺失/混用未文档化身份参数被拒」
- 位置：`src/frontend/src/features/browser-session/selkies_adapter_entry.ts:9`（profile_id 出现即抛错）、`selkies_adapter_entry.ts:14-19`（profileId 缺失/空即抛错）；对照 `src/frontend/src/features/browser-session/adapter_identity.test.ts:75-103`
- 问题：AC-004 中「混用未文档化参数被拒」与「入口缺失身份被拒、default 回退删除」只存在于入口模块 selkies_adapter_entry.ts（顶层读取 window.location.search 并抛错）。全仓没有任何测试导入或执行该入口：grep `selkies_adapter_entry` 在前端测试中零命中；`tests/e2e/test_frontend_adapter_build.py:40,66-77` 只断言该文件存在。新增的 adapter_identity.test.ts 三个用例全部直接调用 adapter.ts 的 installSelkiesClientAdapter（构造入参），其中第三用例在 URL 同时带 profileId 与 profile_id 时是「安装成功、shim 忽略 URL 参数」，并不验证入口层面对 profile_id 的拒绝。失败场景：把入口改回 `params.get("profileId") || params.get("profile_id") || "default"`，现有前端全套测试（含本 task 新增 3 用例）仍全绿，而生产 viewer 会重新接受未文档化身份并回退 default——AC-004 该子句实际无任何测试守卫。
- 建议：为入口模块补可执行测试（如将入口逻辑抽为可注入 window/search 的函数后单测，或在 vitest 中以 mock window 动态 import 入口模块），覆盖三种情形：仅 profileId 正常安装、出现 profile_id 抛错、无 profileId 抛错且不回退 default。

## 结论

- 改测方向复核：无「迁就实现」的改测。逐处核对 diff 中的既有测试修改，均为规格变更驱动且有就地归因注释：test_launch_args 的静默过滤用例整体改名替换为严格拒绝（`tests/unit/test_launch_args.py`，保留 Create 严格断言）、test_t035 的 422 降级重发用例整体替换为单次定论（`tests/unit/test_t035_proxy_runtime.py:444` 起，含 t069 说明）、test_agent_executor_control 的 409 旧形状段改为协议错误断言（保留统一形状正例）、test_runtime_coordinator_error_responses 的旧 detail 透传期望改为协议错误标记（文件头 t069 NOTE，防崩溃与状态不变断言原样保留）、test_profile_launch_args_api 的历史行过滤用例整体改名替换为读取即指名拒绝、test_t051/test_refactor_behavior_equivalence 的无身份归属断言改为新契约矩阵。各迁移与 task.md 测试策略「整体替换/迁移」一致，非就地改预期蒙混。
- 危险模式扫描：已逐条扫描全部测试 diff 与两个新增测试文件，未命中恒真断言、删/反转 expect、注释掉断言、`.skip`/`.only`/`pytest.mark.skip`、`# type: ignore`/`eslint-disable`、阈值增大、条件跳过弱化断言、用赋值替代真实交互。被删除的 5 个旧测试名均为改名整体替换（见上），合法删除，不出 finding。mock 边界合规：gateway_client 用 httpx MockTransport（系统边界）、docker 相关用 fake client 断言 remove 未调用/零认领，均为行为断言而非测 mock 本身。
- 本轮新发现：2 条（f001 important、f002 important）。
- 未进表的提示：(1) `tests/unit/test_t069_strict_control_contracts.py` 中 `test_deploy_sh_has_no_label_missing_project_exemption` 是对 deploy.sh 的静态字符串缺席断言，单独看较脆（变量改名即可绕过），但 t027 的 fake-docker 行为测试已补真实执行覆盖，不阻断。(2) AC-001 合法 ErrorResponse 在 coordinator 侧的「保留字段」证据为 `_downstream_error_text` 生产函数级测试，非规范矩阵则经完整 reconcile 路径验证，符合可测试性声明「触达生产函数」，仅提示后续可补一条合法形状经 reconcile 的端到端用例。
- 总体判断：测试本身可信度高（定向重跑全绿、无危险模式、改测均有规格归因），但四条 AC 全部未打勾按规则一律 TICK-VOID，且 AC-004 的 viewer 入口拒绝逻辑零覆盖，结论 FAIL。
- 系统性 follow-up：无。AC-003 真实 Docker 拓扑验收已由实施方登记 `docs/pending/todo/p095_t069_local_deploy_ownership_verification.md` 顺延本地，本轮不重复报告。

### AC 复验方式

- AC-001：TICK-VOID，re_verified。task.md:28 未勾选故打勾作废；行为本身经独立重跑支撑——test_t069 parser 负矩阵/coordinator 透传与协议错误/gateway 三类 503 与 test_agent_executor_control、test_control_http_clients 全绿（见下方重跑数字）。
- AC-002：TICK-VOID，re_verified。task.md:29 未勾选故打勾作废；行为本身经独立重跑支撑——test_t069 的 422 单次定论用例与 test_t035 改名替换用例均断言仅 1 次请求、携带 version 字段、返回未送达，重跑通过。
- AC-003：TICK-VOID，trust_prior。task.md:30 未勾选故打勾作废；fake 层（归属矩阵、\_owns_deployment 未配置不认领、run_supervisor 缺身份先于 Docker 抛 ValueError、a15/t051 外国与无标签容器 remove 未调用）已独立重跑通过，但真实 Docker 拓扑验收本机无 Docker 不可复验，依赖实施方 p095 顺延登记与 progress.md 门禁记录。
- AC-004：TICK-VOID，re_verified。task.md:31 未勾选故打勾作废；launch_args 严格拒绝、repository 指名拒绝、历史行读取拒绝、network CLI 死输出缺席、adapter 层身份拒绝经独立重跑通过，但 viewer 入口层拒绝逻辑零覆盖（见 t069_test_f002）。

coverage = 3 / 4

verdict: FAIL

## Reviewer 独立重跑记录（证据）

- 后端第一批（gate_venv，PYTHONPATH=src/backend）：`tests/unit/test_t069_strict_control_contracts.py`（单跑 40 passed）与 test_launch_args、test_agent_executor_control、test_runtime_coordinator_error_responses、test_t035_proxy_runtime、test_t051_supervisor_identity、test_t054_network_config_cli、test_refactor_behavior_equivalence 合跑 155 passed。
- 后端第二批：test_a15_orphan_helpers、test_t026_media_network_adapter、test_t055_udp_mux_single_source、test_supervisor_docker_boundaries、test_supervisor_infrastructure_config、test_t050_sandbox_grouping、test_t049_supervisor_restore、test_t056_idempotency（幂等键三源保持面）、test_t053_profile_locale（locale/timezone None 保持面）、tests/integration/test_control_http_clients、tests/integration/test_profile_launch_args_api 合跑 107 passed。
- 前端 vitest：adapter_identity.test.ts（3 passed）、adapter_restart.test.ts、adapter_types.test.ts 合跑 17 passed。
- 未跑全量 unit 套件（约 11 分钟）与 Docker 类验证（本机无 Docker），progress.md 所载全量门禁数字（unit 2112 passed / 5 基线 failed 等）仅作 claim 引用，未独立复验。

## Round 2 (2026-11-14T06:11:28+08:00)

- task：`t069_strict_control_contracts`
- diff_anchor：`501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90`
- round：2

reviewed_scope: d6a502ead0b5dbf2

## Findings

本轮无新 finding（0 条）。前轮 4 条 finding 的复核结论见下方「结论」段，其中 test 轴 2 条逐条以 diff、直读与独立重跑（含变异验证）核实。

## 结论

- 前轮 finding 复核：
    - t069_test_f001（important）：修复真实，已消除（就其指控的打勾缺失而言）。直读 `docs/tasks/t069_strict_control_contracts/task.md:28-31`：AC-001、AC-002、AC-004 现为 `- [x]`，AC-003 为 `- [ ] [deploy]`；`progress.md` 收尾报告已填写（验收与验证、结果摘要、长期文档闭环三节齐备，不再是占位），且明写「AC-003 [deploy] 未满足、顺延 p095」。三条已勾 AC 的测试支撑经本轮独立重跑成立（见 AC 复验方式与重跑记录）。注意：AC-003 保持未勾是 Round 1 两轴建议的顺延口径，但按 AC 复验门禁「未打勾一律 TICK-VOID」，AC-003 本轮仍记 TICK-VOID——这是本轮 verdict 为 FAIL 的唯一原因，不构成对 f001 修复真实性的否定。
    - t069_test_f002（important）：修复真实，已消除。身份解析已抽为纯函数模块 `src/frontend/src/features/browser-session/selkies_profile_id.ts:6-21`（`resolveSelkiesProfileId`：出现 `profile_id` 抛错、profileId 缺失/空抛错、无 default 回退）；入口 `selkies_adapter_entry.ts:5-9` 只做装配（`installSelkiesClientAdapter(window, resolveSelkiesProfileId(window.location.search))`，直读核实）。`adapter_identity.test.ts:103-122` 新增 describe「selkies entry identity resolution (t069)」3 用例，覆盖仅 profileId 正常返回、profile_id 单独出现与与 profileId 混用均抛错、缺失/空/无关参数均抛错。独立重跑该文件 6/6 绿；变异验证：将 `resolveSelkiesProfileId` 临时改回旧逻辑 `params.get("profileId") || params.get("profile_id") || "default"` 后重跑，新增用例中 2 条变红（profile_id 拒绝、缺失/空拒绝），正常用例仍绿——证明新用例真实守卫入口层行为而非恒绿；变异后已按原文件 sha256 `9558cab43eabec12b15edb84d4e5fd4977c0c36fdf9416ece006021eaf85fb64` 完整还原并复跑 6/6 绿，`git status` 与审前一致。
    - t069_code_f001（important，与 test_f001 同因）：同上，打勾动作已真实落地，复核结论同 test_f001。
    - t069_code_f002（minor）：修复真实，已消除。`docs/blueprint/testing.md` 末尾已新增「严格契约与归属拒绝验证（t069）」一节（diff 直读核实），内容覆盖错误形状负矩阵与三消费方对称用例、422 请求计数单次断言、fake Docker「先拒绝后零变更」四路径、存量 launch_args 指名拒绝，并明写真实 Docker 拓扑属 [deploy] 层、不以 mock 替代、顺延 p095——与本 task 测试口径一致，无弱化表述。
- 改测方向复核：无「迁就实现」的改测。本轮相对 Round 1 的测试变更只有 `adapter_identity.test.ts` 新增 3 条入口解析用例（新 describe 块，原 3 用例名称与断言未动）；全量测试 diff 再扫：新增行无 `.skip`/`.only`/`pytest.mark.skip`/`xfail`、`# type: ignore`/`@ts-ignore`/`eslint-disable`、恒真断言；删除行中的旧断言均属 Round 1 已 adjudicated 的整体替换（静默过滤、409 旧形状、旧归属签名、旧 detail 矩阵、422 重发、BIND_HOST/PUBLIC_ORIGIN 存在断言改缺席），无新增删/反转/弱化。
- 本轮新发现：0 条。
- 未进表的提示：(1) `progress.md` 收尾报告前端数字措辞略松：「frontend 632 用例（629 首跑绿 + … + 身份新增 3 条）」按门禁终局记录应为总量 633（原 630 + 新增 3）、首跑绿 632 的口径，属表述问题而非证据问题——新增 3 条已由本轮独立重跑坐实（identity 文件 6/6、adapter 三文件合计 20 passed，较 Round 1 的 17 passed 恰增 3）。(2) 本轮尝试的 `tsc -p tsconfig.test.json --noEmit` 在本机超时未完成，未以其为证据；vitest 经 esbuild 转译不做类型检查，处置表所称 frontend_build 通过仍属实施侧 claim，本轮未独立复验（build 的 prebuild 会改写 vendor 产物，不适合 reviewer 只读边界内执行）。(3) Round 1 已提示的 deploy.sh 静态字符串缺席断言脆弱性维持原判，有 t027 fake-docker 行为测试兜底，不阻断。
- 总体判断：Round 1 的 4 条 finding 全部真实修复，测试层无新问题、无危险模式、变异验证证明新覆盖真实守卫 AC-004 的 viewer 入口拒绝行为。但 AC-003（[deploy]）在 task.md 中保持未勾，按门禁规则必须记 TICK-VOID，verdict 必为 FAIL；本轮 FAIL 仅由该未勾/未验的部署 AC 触发，与任何测试缺陷无关。AC-003 的后续处置路径（参照 t062/t064 已打勾 + [deploy] 顺延登记的先例改口径，或待 p095 本地真实 Docker 验收完成后打勾）由实施方/用户裁定，本报告按现行字节如实判定。
- 系统性 follow-up：无。AC-003 真实 Docker 拓扑验收已登记 `docs/pending/todo/p095_t069_local_deploy_ownership_verification.md`（本轮直读实存，内容覆盖缺失/空/不匹配不认领不删除、缺身份启动先于 Docker 失败、合法匹配可恢复清理、deploy.sh 豁免删除四项），不重复建项。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。task.md:28 已勾；本轮独立重跑 test_t069_strict_control_contracts（含 parser 负矩阵、coordinator 透传保留与协议错误标记、gateway 三类 503）与 test_agent_executor_control 等合批 122 passed，打勾有真实测试支撑。
- AC-002：TICK-VALID，re_verified。task.md:29 已勾；同一 122 passed 批次含 test_t069 的 422 单次定论用例与 test_t035_proxy_runtime 整体替换用例（断言仅 1 次请求、不去 version 字段重发、422 返回未送达），打勾成立。
- AC-003：TICK-VOID，trust_prior。task.md:30 未勾（[deploy]），按门禁一律记 TICK-VOID；fake 层证据（归属矩阵、未配置不认领、run_supervisor 缺身份先于 Docker 抛错）已随 122 passed 批次与 Round 1 复跑成立，但真实 Docker 拓扑验收云端无 Docker 不可复验，依赖 p095 顺延登记与实施侧记录，未冒充已验。
- AC-004：TICK-VALID，re_verified。task.md:31 已勾；launch_args 严格拒绝、repository 指名拒绝、network CLI 死输出缺席随 122 passed 批次复跑成立；viewer 入口层经本轮新增 3 用例独立重跑 6/6 绿且变异验证变红（改回旧回退逻辑 2 条失败），Round 1 的入口零覆盖缺口已补实。

coverage = 3 / 4

verdict: FAIL

## Round 2 Reviewer 独立重跑记录（证据）

- 前端 vitest（还原后终态）：`adapter_identity.test.ts` 6 passed；与 adapter_restart.test.ts、adapter_types.test.ts 合跑 20 passed（Round 1 同组合为 17 passed，增量恰为新增 3 条入口用例）。
- 变异验证：临时把 `selkies_profile_id.ts` 的 `resolveSelkiesProfileId` 改为旧回退逻辑（profileId || profile_id || "default"）后，`adapter_identity.test.ts` 2 failed / 4 passed（失败者为 profile_id 拒绝与缺失/空拒绝两条新用例）；随后按备份完整还原，sha256 复核 `9558cab43eabec12b15edb84d4e5fd4977c0c36fdf9416ece006021eaf85fb64` 与改前一致，复跑 6/6 绿，`git status --short` 与审前一致，无残留改动。
- 后端（gate_venv，PYTHONPATH=src/backend）：test_t069_strict_control_contracts、test_launch_args、test_t035_proxy_runtime、test_t051_supervisor_identity、test_t054_network_config_cli 合跑 122 passed。
- 未跑全量 unit/frontend 全套与 Docker 类验证（本机无 Docker；全量数字仍仅作 progress.md claim 引用，未独立复验）；`tsc --noEmit` 尝试超时未完成，未计入证据。

## Round 3 (2026-11-14T06:23:52+08:00)

- task：`t069_strict_control_contracts`
- diff_anchor：`501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90`
- round：3

reviewed_scope: 9b0299b2a9e03c58

## Findings

本轮无新 finding（0 条）。本轮唯一实质变更——AC-003 打勾口径与 progress 数字修正——已逐项以归档先例、p095 直读、原始日志直读与独立串行复跑核实，结论见下方。

## 结论

- 前轮 finding 复核：
    - t069_test_f001 / t069_code_f001（important，打勾缺失）：Round 2 已确认 AC-001/002/004 打勾真实；本轮 AC-003 的打勾按先例口径成立（详见 AC 复验方式），该 finding 的遗留争议就此关闭。
    - t069_test_f002（important，viewer 入口零覆盖）与 t069_code_f002（minor，testing.md 缺失）：Round 2 已以独立重跑与变异验证确认真实修复，本轮交付测试内容未再变更（全量测试 diff 危险模式终扫见下），维持已消除。
    - Round 2 两轴遗留的唯一 FAIL 原因（AC-003 未勾记 TICK-VOID）：本轮已按两轴明示的先例路径处置——`task.md:30` AC-003 现为 `- [x] [deploy]`，`progress.md`「Review 处置」Round 2 小节追加了打勾口径裁定（云端可验部分全部完成才打勾、真实 Docker 拓扑顺延 p095、不冒充已验）。
- AC-003 先例一致性核查（本轮核心）：直读归档件——t062 `docs/archive/tasks/t062_control_plane_boundaries/task.md:30` 的 [deploy] AC-005 为 `- [x]`，其 progress 明写真实 Docker 构建/readiness 顺延 p092、收尾结果写「全部满足（[deploy] 部分顺延）」，且 p092 文件实存并明言「t062 已在云端 finish、云端可验部分经验证」；t064 `docs/archive/tasks/t064_session_auth_cdp_boundary/task.md:29-31,33` 的 [deploy] AC-001/002/004/006 均为 `- [x]`，其 progress 逐条写「云端验足、真实拓扑顺延 p094」，收尾结论为双轴 PASS、五条 AC 全部 TICK-VALID 且「review 中明确不表示已验」。t069 本轮口径与两先例逐点一致：云端可验部分（实现 + fake 层负矩阵 + 启动拒绝 + deploy.sh 静态与 fake-docker 行为覆盖）完成、打勾、顺延登记并存、明示不冒充已验。
- p095 覆盖面核查：`docs/pending/todo/p095_t069_local_deploy_ownership_verification.md` 实存（未跟踪交付文件，`git status` 可见），正文逐项覆盖 AC-003 全部子句：缺失/为空/不匹配 instance-id 的存量容器与网络不被认领或删除、Supervisor 未配置部署身份时于任何 Docker 变更前启动失败、合法匹配资源可正常恢复清理（scan/prune/孤儿 helper）、deploy.sh 前缀冲突检查对无标签历史容器不再按 compose project 豁免认领；且开篇明写云端只完成代码与单元/契约层证据、「不能冒充真实部署已验」。
- progress 数字修正属实性核查：直读 `.scratch/frontend_test2.log` 尾部汇总——`Tests 7 failed | 626 passed (633)`、`Test Files 5 failed | 78 passed (83)`，与修正后收尾报告「总量 633；终局复跑 626 绿 / 7 failed」逐字吻合；7 条失败逐条为 profiles/settings 表单类的 5000ms 超时（ConfigTab 2、ProfileCreateDialog 1、ProfileForm.t058 1、ProfileForm 2、SettingsPage 1），与「失败全在 profiles/settings 表单类」一致。
- 改测方向复核：无。本轮无任何测试文件变更；全量测试 diff 终扫（相对基线的测试 diff 加两个未跟踪新测试文件全文）：新增行无恒真断言、`.skip`/`.only`/`pytest.mark.skip`/`xfail`、`# type: ignore`/`@ts-ignore`/`eslint-disable`、`toBeTruthy`/`toBeDefined` 弱化断言；被删的 5 个旧测试名仍为 Round 1 已 adjudicated 的整体替换（历史行过滤、409 旧形状、静默过滤、422 重发、无身份全认领），无新增删/反转/弱化。
- 本轮新发现：0 条。
- 未进表的提示：progress 收尾报告「串行复跑该 4 文件 28/28 全过」的文件数措辞不准：终局日志中失败涉及 5 个文件，其用例数合计恰为 28（ConfigTab 3 + ProfileCreateDialog 7 + ProfileForm.t058 5 + ProfileForm 10 + SettingsPage 3）。本轮独立复跑覆盖全部 5 个文件且合计 28/28 全过（见重跑记录），故 flaky 定性的实质成立、仅「4 文件」计数措辞有误，属表述问题、不阻断，建议实施方顺手订正为 5 文件。
- 总体判断：前轮 4 条 finding 全部真实修复，AC-003 打勾与 t062/t064 归档先例一致且顺延登记 p095 覆盖完整、明示未验，前端终局数字经原始日志与独立复跑双重坐实，测试层无新问题、无危险模式，本轮 PASS。本 PASS 的 AC-003 判定沿先例口径：表示云端可验部分成立，不表示真实 Docker 拓扑已验（该部分在 p095 本地补验）。
- 系统性 follow-up：无。真实 Docker 拓扑验收已由 p095 登记，不重复建项。

## Round 3 Reviewer 独立重跑记录（证据）

- 落点仓库校验：以 workdir 为仓库目录执行不带 `-C` 的 `git rev-parse --show-toplevel`，输出精确等于 `<home>/workspace/CBrowser_t069`。
- 后端（gate_venv，PYTHONPATH=src/backend）：`tests/unit/test_t069_strict_control_contracts.py` 单跑 40 passed。
- 前端串行抽查（src/frontend 下 `npx vitest run`，低负载时点）：`ProfileForm.test.tsx` 单文件 10/10 passed（终局日志中该文件的 2 条超时失败用例串行下分别约 928ms/443ms 通过）；其余 4 个终局失败文件（ConfigTab、ProfileCreateDialog、ProfileForm.t058、SettingsPage）合跑 18/18 passed。两者合计覆盖终局 7 条失败所在的全部 5 个文件、共 28/28 全过，独立坐实「负载 flaky、审阅后复跑全过」的定性（文件数为 5 而非 progress 所写 4，见未进表的提示）。
- 原始日志直读：`.scratch/frontend_test2.log` 汇总行 `Tests 7 failed | 626 passed (633)`，失败文件清单与失败形态（均为 5000ms 超时）已逐条核对。
- 未跑全量 unit/frontend 全套与 Docker 类验证（本机无 Docker）；全量数字仍仅作 progress.md claim 引用，惟前端终局数字已由原始日志直读独立核实。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。task.md:28 已勾；本轮独立重跑 test_t069_strict_control_contracts 40 passed（含 parser 负矩阵、coordinator 透传保留与协议错误标记、gateway 三类 503），与 Round 2 的 122 passed 合批证据一致，打勾有真实测试支撑。
- AC-002：TICK-VALID，re_verified。task.md:29 已勾；同一 40 passed 批次含 observed 422 单次定论用例（断言仅 1 次请求、不去 version 字段重发、422 返回未送达），与 Round 2 的 test_t035 整体替换用例证据一致。
- AC-003：TICK-VALID，trust_prior。task.md:30 已勾且口径与 t062 AC-005/t064 [deploy] 各条的归档先例一致（云端可验部分完成 + 顺延登记 + 明示不冒充已验）；云端可验部分经本轮 40 passed 批次中的归属矩阵、未配置不认领、run_supervisor 缺身份先于 Docker 抛错与 deploy.sh 豁免缺席断言再确认，但真实 Docker 拓扑验收云端无 Docker 不可独立复验，依赖 p095 顺延登记（覆盖四项子句，本轮直读实存），不表示该部分已验。
- AC-004：TICK-VALID，re_verified。task.md:31 已勾；本轮 40 passed 批次含 launch_args 严格拒绝、repository 指名拒绝与 network CLI 死输出缺席，viewer 入口层证据沿 Round 2 的独立重跑 6/6 与变异验证（改回旧回退逻辑 2 条变红），本轮测试内容未变更。

coverage = 3 / 4

verdict: PASS

## Round 4 (2026-11-14T06:28:17+08:00)

- task：`t069_strict_control_contracts`
- diff_anchor：`501ac0ba0c477cefd2a68a3b93abb8c2cf69eb90`
- round：4

reviewed_scope: 77d365c414ef2b91

## Findings

本轮无新 finding（0 条）。本轮为指纹确认轮：Round 3 PASS 后交付文件全部暂存、finish 门禁按暂存树复算指纹变化，另有两处纯措辞/格式订正，无任何测试内容变更；复核结论见下方。

## 结论

- 前轮 finding 复核：t069_test_f001、t069_test_f002 及 code 轴 f001/f002 在 Round 2/3 已逐条以 diff、直读与独立重跑（含变异验证）确认真实修复；本轮暂存树中测试内容与 Round 3 已 PASS 版本一致（核对见下），维持已消除。
- 指纹变更原因核实：`git status --porcelain` 共 52 个交付文件全部为已暂存状态（`M `/`A `），无未暂存改动、无未跟踪文件，reviewer 可见完整交付内容；`git diff --cached 501ac0b -- tests/ src/frontend/` 与未暂存口径 `git diff 501ac0b -- tests/ src/frontend/` 的 stat 完全一致（22 文件、707 insertions、103 deletions），证明暂存未改变测试/前端内容，指纹变化仅源于暂存树口径复算。两处订正直读核实属纯措辞/格式：`progress.md:78` 收尾报告已作「串行复跑该 5 文件 28/28 全过」（Round 3 提示的「4 文件」计数已订正）；本文件 Round 3 的小节顺序调整不涉及任何判定文字变更。
- 危险模式终扫：对暂存测试 diff（`tests/` 与 `src/frontend/`，1295 行）逐条扫描——新增行无恒真断言（`expect(true)`/`assert True`）、无 `.skip`/`.only`/`pytest.mark.skip`/`xfail`、无 `# type: ignore`/`@ts-ignore`/`eslint-disable`、无 `toBeTruthy`/`toBeDefined` 弱化断言、无注释掉的断言；两个新增测试文件（`tests/unit/test_t069_strict_control_contracts.py`、`adapter_identity.test.ts`）全文复扫同样阴性。被删旧测试仍为 Round 1 已 adjudicated 的整体替换，无新增删/反转/弱化。
- 改测方向复核：无。本轮相对 Round 3 无任何测试文件内容变更，不存在「迁就实现」的改测。
- 本轮新发现：0 条。
- 未进表的提示：无。Round 3 提示的 progress「4 文件」措辞已订正为 5 文件，本轮直读确认。
- 总体判断：暂存测试内容与 Round 3 PASS 版本一致、危险模式终扫维持阴性、四条 AC 判定维持（含 AC-003 沿 t062/t064 先例口径），本轮 PASS。本 PASS 的 AC-003 判定不表示真实 Docker 拓扑已验，该部分仍在 p095 本地补验。
- 系统性 follow-up：无。真实 Docker 拓扑验收已登记 `docs/pending/todo/p095_t069_local_deploy_ownership_verification.md`（本轮直读实存，四项子句齐备、明写不冒充已验），不重复建项。

## Round 4 Reviewer 独立重跑记录（证据）

- 落点仓库校验：以 workdir 为仓库目录执行不带 `-C` 的 `git rev-parse --show-toplevel`，输出精确等于 `<home>/workspace/CBrowser_t069`；当前分支 `t069_strict_control_contracts`。
- 暂存一致性：`git diff --cached` 与 `git diff`（相对基线 501ac0b）对 `tests/ src/frontend/` 的 stat 逐行一致；`git status --porcelain` 52 条全部已暂存，无未暂存/未跟踪项。
- 后端（gate_venv，PYTHONPATH=src/backend）：`tests/unit/test_t069_strict_control_contracts.py` 单跑 40 passed（与 Round 3 单跑数字一致）。
- 前端（src/frontend 下临时 symlink node_modules 后 `npx vitest run`，审后已删除链接，`git status` 与审前一致）：`adapter_identity.test.ts` 6 passed、`adapter_restart.test.ts` 8 passed、`adapter_types.test.ts` 6 passed，合计 20 passed（与 Round 2/3 数字一致，含 identity 入口解析 3 用例）。
- 未跑全量 unit/frontend 全套与 Docker 类验证（本机无 Docker）；全量数字仍仅作 progress.md claim 引用。

### AC 复验方式

- AC-001：TICK-VALID，re_verified。task.md:28 已勾（暂存版直读）；本轮独立重跑 test_t069_strict_control_contracts 40 passed（含 parser 负矩阵、coordinator 透传保留与协议错误标记、gateway 三类 503），暂存测试内容与 Round 3 PASS 版本一致，打勾维持成立。
- AC-002：TICK-VALID，re_verified。task.md:29 已勾；同一 40 passed 批次含 observed 422 单次定论用例（断言仅 1 次请求、不去 version 字段重发、422 返回未送达），与 Round 2/3 证据一致。
- AC-003：TICK-VALID，trust_prior。task.md:30 已勾，沿 Round 3 已核实的 t062/t064 归档先例口径（云端可验部分完成打勾 + 真实 Docker 拓扑顺延 p095 登记、明示不冒充已验）；云端可验部分经本轮 40 passed 批次中的归属矩阵、未配置不认领、run_supervisor 缺身份先于 Docker 抛错再确认，p095 本轮直读实存且覆盖四项子句，但真实 Docker 拓扑云端无 Docker 不可独立复验，不表示该部分已验。
- AC-004：TICK-VALID，re_verified。task.md:31 已勾；本轮 40 passed 批次含 launch_args 严格拒绝、repository 指名拒绝与 network CLI 死输出缺席，前端 adapter 三文件 20 passed 含 identity 入口解析用例 6/6，viewer 入口层证据沿 Round 2 变异验证，本轮测试内容未变更。

coverage = 3 / 4

verdict: PASS
