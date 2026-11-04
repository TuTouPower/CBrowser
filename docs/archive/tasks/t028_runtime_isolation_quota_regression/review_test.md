# Task review t028（reviewer_focus: 测试）

- task：`t028_runtime_isolation_quota_regression`
- spec：`docs/tasks/t028_runtime_isolation_quota_regression/task.md`
- diff_anchor：`2bbce465d16d958866691dd97bdbfd1cd7693616`
- target：相对 diff_anchor 的完整 worktree diff（分支 `t028_runtime_isolation_quota_regression`）
- round：1
- reviewed_at：2026-11-04T12:37:44+08:00

reviewed_scope: 7c33f67e39250190

## Findings

### t028_test_f001 - 覆盖矩阵与 t032 映射引用不存在的测试文件，p016 网络行与 search-defaults 行的入口声明不成立

- 严重度：important
- 锚点：AC-001（矩阵逐项列出现行入口、缺口均有可收集执行入口）与 AC-007（运行指令逐项映射到 t032）
- 位置：`docs/blueprint/testing.md:181`、`docs/blueprint/testing.md:196`、`docs/blueprint/testing.md:212`
- 问题：reviewer 对 testing.md 中全部 `test_*.py` 引用做文件名存在性扫查（对照 `tests/` 全树），两处 t028 新增引用无对应文件：(1) 第 181 行 p016「网络保护真实行为」现行入口写 `test_supervisor_network_protection_e2e.py`，仓库无此文件，该行云端结果却记「skip」——不存在的文件不可能 collect-only 通过；第 212 行 t032 AC-008 指令要求单跑该文件，t032 执行者照表运行会直接 collection error。(2) 第 196 行 search-defaults 行引用 integration 层 `test_search_defaults_runtime_chain.py` 并记「集成已跑」，仓库无此文件（现行 integration 覆盖是 `tests/integration/test_api_search_defaults_routes.py`）。矩阵是 AC-001 的交付物本身，入口指错使这两条历史项的覆盖声明不可信、t032 映射不可执行。
- 建议：把两处改指真实存在的文件（网络保护行改指实际覆盖该行为的 namespace/ipv6/policy_failure 与 network_ownership 等现行用例；search-defaults 行改指 `test_api_search_defaults_routes.py` 等真实文件），并同步修正云端结果与第 212 行指令；改后对矩阵全部引用再做一次存在性扫查。

### t028_test_f002 - testing.md 称旧三个 resource E2E「已于 88f5d7d 退役」，与仓库现状矛盾

- 严重度：important
- 锚点：AC-001（覆盖矩阵/证据层级表述须与实际一致）；本 task 范围含「修正 testing.md 中高于实际证据层级的表述」
- 位置：`docs/blueprint/testing.md:153`
- 问题：该行新增表述称 `test_supervisor_resource_policy_e2e.py`、`test_supervisor_resource_capacity_e2e.py`、`test_supervisor_resource_monitor_e2e.py` 已退役，但 reviewer 实测三文件仍在 `tests/e2e/` 且 collect-only 可收集 5 条用例；所引提交 `88f5d7d` 在本仓库历史中不存在（`git log` 查无此 revision）。这是 t028 自己引入的失真表述：t032 决策者据此会以为这 5 条实跑用例已不存在而不再运行，p016 资源覆盖被静默丢弃，且与同文件矩阵「只引用既有入口」的自述矛盾。
- 建议：删除「已退役」断言与不存在的提交引用，改为如实描述三文件现状及其与配额链 E2E 的分工（哪些行为仍由它们覆盖、哪些由 `test_supervisor_quota_chain_e2e.py` 接替）；若确应退役，须在本 task 内真实删除文件并让 collect 结果与文档一致。

### t028_test_f003 - AC-002「旧 Agent 退出不误关新 Viewer」断言存在时序竞态窗口

- 严重度：minor
- 锚点：AC-002（旧 Agent 退出不误关新 Viewer）
- 位置：`tests/integration/test_gateway_signaling.py:522`（`test_agent_replacement_closes_old_viewers`）
- 问题：`await ws_agent_1.close()` 返回后立即断言 `not ws_viewer_2.closed` 并做一次 STILL_ALIVE 往返；若 Gateway 的误关是异步延迟触发（在往返完成之后才落到 Viewer 2），本用例仍会通过。该窗口较窄（进程内 Gateway 通常在 close 握手处理中同步关 Viewer），不阻断，但断言强度弱于 AC 语义的「退出后持续可用」。
- 建议：误关检查前加一个短暂的事件循环让步/轮询窗口（如在 0.5s 内持续断言 Viewer 2 未关闭且可往返），或让 Viewer 2 再收一条下行消息作为存活终证。

### t028_test_f004 - 配额链保留证据只记 CPU 采样窗数量，counter/采样窗明细只落在临时 proof 文件

- 严重度：minor
- 锚点：AC-003（记录投递值、CPU counter/采样窗、限帧值与实际帧数）
- 位置：`tests/e2e/test_supervisor_quota_chain_e2e.py:232`
- 问题：`save_evidence` 保存的 `quota_chain_proof` 中 `cpu_policy.windows` 只是 `len(cpu_proof["windows"])` 计数，采样窗明细（含 CPU counter）只存在于 `tmp_path/supervisor_cpu_stream_proof.json`；在 `run_gates.sh` 证据模式下 basetemp 位于随运行清理的 scratch 目录，保留证据里将查不到 AC-003 要求记录的 counter/采样窗。明细在运行期确有产生，故仅记 minor。
- 建议：把 CPU proof 的 windows 明细（或其经 `save_evidence` 脱敏后的副本）并入保留证据，使 t032 按 AC-008 artifact 字段能直接取到 windows/deliveries 明细。

## 结论

- 改测方向复核：无「迁就实现」的改测。diff 中唯一的既有测试改动是 `test_agent_replacement_closes_old_viewers` 新增 close=1001、新旧 conn_id 不同、下行回复、旧 Agent 退出后续传四组断言（强化，归因为恢复 t015 弱化前的 251fa0f 语义，docstring 与实施笔记均有说明）；`stream_monitor.py` 投递由自建 mock socket 改为生产 `GatewayControlClient.set_quota`、归属标签断言由真值改精确等值，均为强化方向。无删除测试、无删/反转断言。
- 危险模式扫描：全 diff 扫查恒真断言、`.skip`/`.only`、`type: ignore`/`eslint-disable`、条件跳过断言、阈值放宽——未命中。唯一形似项是 `tests/unit/test_t028_image_identity.py:165` 的 `pytest.raises(pytest.skip.Exception)`，其语义正是断言 fail-closed 时以 skip 拒绝构造，属被测行为本身，合法。
- 本轮新发现：4 条（important 2、minor 2）
- 未进表提示：`test_artifact_download_chain_e2e.py` finally 中对 proof 文件的检查带 `if proof.exists()` 条件（主断言为 API 字节/sha256 比对，不依赖该检查，仅作提示）；证据模式 unit 未覆盖 `CBROWSER_RUN_E2E=1` 时 e2e suite 的纳入与环境构建失败路径，可后续补 case（minor 扩展，不阻断）。已知基线失败（unit hygiene 源于 t027 报告绝对路径、integration ac009 协调器超时）经任务说明为干净 base 同 ID/同签名，未重复计为本 task finding。
- 总体判断：AC-002/005/006 的测试真实可信且经 reviewer 实跑复验，AC-003/004 的真实环境入口齐备（实跑归 t032）；但 AC-001 覆盖矩阵存在两处指向不存在文件的入口声明与一处与仓库现状矛盾的退役表述，矩阵作为本 task 核心交付物不可信，须先修正。
- 系统性 follow-up：无（两条 important 均为本 task 文档内可直接修正项，无需另立 tid）

### AC 复验方式

- AC-001：re_verified——reviewer 对 testing.md 矩阵全部测试文件引用做存在性扫查并对新旧 resource E2E 做 collect-only 实测，发现 f001/f002 两处声明与仓库现状不符；其余行引用文件均存在。打勾不成立（限 f001/f002 所涉行）。
- AC-002：re_verified——实跑 `tests/integration/test_gateway_signaling.py` 全文件 16 passed，并逐行核对新增断言（close.data == 1001、conn_id 不同、下行 REPLY_FROM_A2、旧 Agent 退出后 STILL_ALIVE 往返），与 AC 四项一一对应。
- AC-003：trust_prior——本机无 Docker，真实链无法实跑；依赖实施侧 collect-only 结果与 reviewer 静态核查：新增入口 collect 通过（新 6 文件共 7 条可收集），`stream_monitor.py` 投递已改走生产 `GatewayControlClient.set_quota`、无内存回调/mock socket 残留，帧窗与 cap 断言齐备。实跑判定归 t032。
- AC-004：trust_prior——五个新入口均 collect 通过且断言经逐行核查（下载字节/sha256、注册预算 4→429 与 20→429 与重启恢复、X11 0750 与无残留 helper、search-defaults CSRF 403 与幂等终态）；其中删除续跑一条由 reviewer 实跑通过（真实 API 子进程，basetemp 置于 /tmp，1 passed），其余四条实跑归 t032。
- AC-005：re_verified——实跑 unit 9 条全过；另以 required 模式 + 全部镜像变量设为 tag 值实跑 collect，收集期逐项报出「not an immutable sha256 image ID」并退出，fail-closed 成立；`.scratch` 旁路读取已删除且有 unit 守卫。
- AC-006：re_verified——实跑 unit 4 条全过（PATH stub 驱动真实 `run_gates.sh`，redactor 与 manifest builder 为真实脚本执行）：证据模式跑完五 suite、integration 失败时总退出非零、manifest 逐 suite 命令/退出码/JUnit 齐备、保留日志中 secret 形态值已脱敏、默认模式仍首失败即停。
- AC-007：re_verified——逐行核查各新入口的 finally 清理与独立资源（harness cleanup、X11 uuid 前缀与残留回收、stream_monitor finally 恢复原 quota 并落 proof、删除续跑子进程 stop），且 testing.md「t032 运行映射」逐项给出指令/镜像/预算/artifact 字段；真实环境中的清理实效随 t032 实跑判定。

coverage = 5 / 7

verdict: FAIL

## Round 2 (2026-11-04T12:47:42+08:00)

- round：2
- reviewed_at：2026-11-04T12:47:42+08:00

reviewed_scope: e570c8f79524ba70

## Findings

本轮无新发现（无 t028_test_f005 及后续编号产生）。

## 结论

- 前轮 finding 复核：
  - t028_test_f001（important）：已消除。`docs/blueprint/testing.md:181` 网络保护行已改列现行存在的五个入口（`test_supervisor_browser_network_e2e.py`、`test_supervisor_network_ownership_e2e.py`、`test_supervisor_namespace_policy_e2e.py`、`test_supervisor_ipv6_policy_e2e.py`、`test_supervisor_policy_failure_e2e.py`，附网/回滚另引 `test_supervisor_reconciliation_e2e.py`）；`docs/blueprint/testing.md:196` search-defaults 行已改列 `test_api_search_defaults_routes.py` 与 `test_runtime_coordinator_integration.py`；t032 映射 AC-008 指令（同文件运行映射表）已同步改为单跑 quota chain 与 browser_network/network_ownership。reviewer 本轮对 testing.md 全部 `test_*.py` 引用再做存在性扫查：全部引用均有对应现行文件，不存在的两个旧文件名在文档与测试树中已无残留。
  - t028_test_f002（important）：已消除。`docs/blueprint/testing.md:153` 资源段已改写为三层准确表述：unit 算法层、resource 三个 E2E 的真实采样/决策但 monitor 投递腿为本地回调、配额投递链归 quota chain E2E 与生产投递路径；「已退役」断言与虚假提交号已删除（全文扫查无残留）。reviewer 本轮 collect-only 实测三个 resource E2E 文件共 5 条用例可收集，与新表述一致，未再把仍存在的覆盖静默丢弃。
  - t028_test_f003（minor）：已消除。`tests/integration/test_gateway_signaling.py:522-535` 在旧 Agent 关闭后增加 0.5s 静默窗口：窗口内收到 CLOSE/CLOSING/CLOSED 任一帧即断言失败，其后仍做 `not ws_viewer_2.closed` 与 STILL_ALIVE 往返。reviewer 本轮实跑该文件与两份 t028 unit 文件合计 29 passed，其中该文件 16 条全过。窗口断言不是条件跳过弱化：超时无帧为通过条件、收到 close 族帧为明确失败，与 AC-002 的延迟误关场景对应。
  - t028_test_f004（minor）：已消除。`tests/e2e/test_supervisor_quota_chain_e2e.py:231-236` 的保留证据 `cpu_policy` 已改为嵌入完整 `windows` 明细（连同 deliveries、capped/restored 帧数），不再只记数量；临时 proof 文件清理后保留证据仍可独立查 counter/采样窗。真实环境实跑仍归 t032，本条仅就证据结构复核。
  - 附带复核（code 路 f002/f003，非本路 finding）：`scripts/gate_evidence_manifest.py:56` 身份收集异常已显式记录为 `image_identity.error`；`scripts/run_gates.sh` evidence 模式 environment.log 已先落 raw、经脱敏脚本生成保留日志并删 raw，unit 中已补秘密形状断言；两份 t028 unit 文件本轮合计 13 条复跑通过（image identity 9 条 + run_gates evidence 4 条）。
- 改测方向复核：无「迁就实现」的改测。本轮修复均为文档纠错（指向真实入口、删除失真退役表述）与断言强化（静默窗口、完整 windows 证据），未就地把旧测试预期改成当前实现输出，未删测试、未删/反转断言。
- 危险模式扫描：对完整 diff 再扫恒真断言、删/反转 expect、注释断言、弱化断言、`.skip`/`.only`/`pytest.mark.skip`、`type: ignore`/`eslint-disable`、阈值放宽、条件跳过断言——未命中。唯一形似项仍为 `tests/unit/test_t028_image_identity.py` 中 `pytest.raises(pytest.skip.Exception)`，其语义是断言 fail-closed 以 skip 拒绝构造，属被测行为本身，合法（同 Round 1 判定）。
- 本轮新发现：0 条
- 未进表的提示：证据模式 unit 仍未覆盖 `CBROWSER_RUN_E2E=1` 时 e2e suite 的纳入与环境构建失败路径，可后续补 case（minor 扩展，不阻断；同 Round 1 提示，未恶化）。已知基线失败 unit hygiene 与 integration ac009 经任务说明为干净 base 同 ID/同签名，本轮未重复计为 finding，且与实施方门禁实测（unit 853 过/1 skip/1 存量 hygiene、integration 129 过/1 存量 ac009）一致。
- 总体判断：Round 1 两条 important 与两条 minor 均经 diff 与实跑核实真修，完整重审未发现新的 critical/important；AC-001 矩阵声明现与仓库现状一致，AC-002/005/006 测试真实可信，AC-003/004 入口与断言齐备（实跑归 t032），AC-007 映射已随 f001 修正可执行。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：re_verified——reviewer 对 `docs/blueprint/testing.md` 矩阵与 t032 映射的全部测试文件引用做存在性扫查（全部存在），对新旧 resource E2E 与六个新入口做 collect-only 实测（新入口 7 条 + resource 三文件 5 条，共 12 条可收集），并逐行核对三层资源表述与现行文件一致；Round 1 的 f001/f002 失真已消除，打勾成立。
- AC-002：re_verified——实跑 `tests/integration/test_gateway_signaling.py` 全文件 16 passed，逐行核对 close=1001、新旧 conn_id 不同、下行 REPLY_FROM_A2、旧 Agent 退出后 0.5s 静默窗口与 STILL_ALIVE 往返四组断言齐备。
- AC-003：trust_prior——本机无 Docker，真实链无法实跑（未把 collect-only/skip 记为实跑通过）；依赖静态核查与 collect：quota chain 入口可收集，`stream_monitor.py` 投递走生产 `GatewayControlClient.set_quota`、无内存回调/mock socket 残留，投递值/帧窗/cap/布局/motion-static/CPU policy 断言齐备，保留证据已嵌入完整 windows。实跑判定归 t032。
- AC-004：trust_prior——五个新入口均 collect 通过且断言逐行核查（下载字节/sha256、删除续跑、X11 0750 与无残留、注册预算 4→429 与 20→429 与重启恢复、search-defaults CSRF 403 与幂等终态）；其中删除续跑一条由 reviewer 本轮实跑通过（真实 API 子进程，basetemp 置于 /tmp，1 passed），其余四条实跑归 t032。
- AC-005：re_verified——实跑 unit 9 条包含在合计 29 passed 内；格式/本地存在/可解析三类 fail-closed、required 模式收集期失败与 `.scratch` 旁路守卫均有真实断言支撑。
- AC-006：re_verified——实跑 unit 4 条包含在合计 29 passed 内（PATH stub 驱动真实 `run_gates.sh`，redactor 与 manifest builder 为真实脚本执行）：证据模式跑完五 suite、失败时总退出非零、manifest 逐 suite 命令/退出码/JUnit 齐备、suite 与 environment 日志均已脱敏且 raw 不保留、默认模式仍首失败即停。
- AC-007：re_verified——逐行核查各新入口 finally 清理与独立资源命名，且 t032 运行映射逐项给出指令/镜像/预算/artifact 字段，本轮存在性扫查确认映射所引入口全部真实存在；真实环境清理实效随 t032 实跑判定。

coverage = 5 / 7

verdict: PASS

## Round 3 (2026-11-04T12:58:19+08:00)

- round：3
- reviewed_at：2026-11-04T12:58:19+08:00

reviewed_scope: 91b30ce90d1e8347

## Findings

本轮无新发现（无 t028_test_f005 及后续编号产生）。

## 结论

- 前轮 finding 复核：
  - t028_test_f001（important）：保持消除。本轮对 `docs/blueprint/testing.md` 全部 35 个 `test_*.py` 引用再做存在性扫查，缺失为 0；t032 映射所引入口仍全部真实存在。
  - t028_test_f002（important）：保持消除。资源三层表述未回退，本轮 collect-only 实测三个 resource E2E 文件共 5 条用例仍可收集，与文档表述一致。
  - t028_test_f003（minor）：保持消除。`tests/integration/test_gateway_signaling.py` 本轮实跑全过（与两份 t028 unit 文件合计 29 passed，其中该文件 16 条），旧 Agent 退出后 0.5s 静默窗口断言未变。
  - t028_test_f004（minor）：保持消除。`tests/e2e/test_supervisor_quota_chain_e2e.py:231-236` 保留证据 `cpu_policy` 仍嵌入完整 `windows` 明细（连同 deliveries、capped/restored 帧数），未退回只记数量。
  - 同源 code 路 t028_code_f004（minor，本轮重审起因）：已消除，且未破坏 AC-006 证据模式契约。`scripts/run_gates.sh:47-51` 脱敏失败分支已改为写显式占位行 + stderr 告警，其后 `rm -f` 无条件删除 raw，`|| cp` 回退在全文件无残留。reviewer 独立模拟脱敏失败（PATH 首位放置恒失败的 `python3` 替身、stub uv/npm 驱动真实 `run_gates.sh`）：`logs/environment.log` 恰为占位行「environment log redaction failed; raw log withheld from evidence」，`environment.raw.log` 不存在，stderr 出现对应告警，保留 logs 全目录无秘密形态值，五 suite 照常跑完、manifest `all_passed=true`、总退出码 0。正常路径仍由 unit 既有断言覆盖（environment.log 已脱敏且含 `<redacted>` 标记、raw 不存在），本轮实跑通过。
- 改测方向复核：无「迁就实现」的改测。本轮相对 Round 2 的内容变更只有 `scripts/run_gates.sh` 脱敏失败分支（生产脚本），测试文件未改；无删测试、无删/反转/弱化断言。
- 危险模式扫描：对完整 diff 再扫恒真断言、删/反转 expect、注释断言、弱化断言、`.skip`/`.only`/`pytest.mark.skip`、`type: ignore`/`eslint-disable`、阈值放宽、条件跳过断言——未命中。唯一形似项仍为 `tests/unit/test_t028_image_identity.py` 中 `pytest.raises(pytest.skip.Exception)`，语义为断言 fail-closed 以 skip 拒绝构造，属被测行为本身，合法（同前轮判定）。
- 本轮新发现：0 条
- 未进表的提示：code f004 的脱敏失败分支尚无常驻 unit 用例，本轮由 reviewer 以替身实测代验；可后续在 `tests/unit/test_t028_run_gates_evidence.py` 补一条 PATH 替身令 `python3` 失败的 case（minor 扩展，不阻断，与前轮「证据模式 unit 未覆盖 e2e 纳入与环境构建失败路径」提示同类）。已知基线经本轮全量实跑确认与实施方口径一致：unit 853 passed / 1 skipped / 1 failed（`test_repo_hygiene`，干净 base 同 ID）、integration 129 passed / 1 failed（`test_ac009`，干净 base 同签名），未重复计为 finding。本机无 Docker，Docker 用例仅 collect-only 与静态核查，未把 skip/collect 记为实跑通过。
- 总体判断：Round 1 全部 finding 与 code 路 f004 均经 diff、实跑与独立故障模拟核实真修；f004 修复未破坏 AC-006 证据模式契约（正常路径 unit 断言全过、失败路径占位与告警实证成立）；最终内容完整复审未发现新的 critical/important。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：re_verified——本轮对 testing.md 矩阵与 t032 映射的全部 35 个测试文件引用做存在性扫查（缺失 0），对六个新入口与三个 resource E2E 做 collect-only 实测（共 12 条可收集），矩阵声明与仓库现状一致，打勾成立。
- AC-002：re_verified——实跑 `tests/integration/test_gateway_signaling.py` 全文件 16 passed（包含在合计 29 passed 内），close=1001、新旧 conn_id 不同、下行 REPLY_FROM_A2、旧 Agent 退出后 0.5s 静默窗口与 STILL_ALIVE 往返断言未变。
- AC-003：trust_prior——本机无 Docker，真实链无法实跑（未把 collect-only/skip 记为实跑通过）；依赖静态核查与 collect：quota chain 入口可收集，`tests/fixtures/supervisor_resource_probe/stream_monitor.py` 投递走生产 `GatewayControlClient.set_quota`、无内存回调/mock socket 残留，保留证据已嵌入完整 windows 明细。实跑判定归 t032。
- AC-004：trust_prior——五个新入口均 collect 通过且断言经前轮逐行核查、本轮文件未变；其中删除续跑一条由 reviewer 本轮实跑通过（真实 API 子进程，basetemp 置于 /tmp，1 passed），其余四条实跑归 t032。
- AC-005：re_verified——unit 9 条本轮实跑通过（包含在合计 29 passed 内）；另以 required 模式 + 镜像变量分别设为 tag 值、短摘要、全零不可解析 ID 实跑收集，三类均明确报出「not an immutable sha256 image ID」或无法解析的拒绝原因，fail-closed 成立。
- AC-006：re_verified——unit 4 条本轮实跑通过（包含在合计 29 passed 内）：证据模式跑完五 suite、integration 失败时总退出非零、manifest 逐 suite 命令/退出码/JUnit 齐备、suite 与 environment 日志均已脱敏且 raw 不保留、默认模式仍首失败即停；另由 reviewer 独立模拟 environment 脱敏失败路径，证明显式占位 + stderr 告警 + raw 恒删除成立，f004 修复未破坏本契约。
- AC-007：re_verified——脱敏失败路径下 raw 恒删除、保留证据无未脱敏内容已经独立模拟实证；各新入口 finally 清理与独立资源命名、t032 运行映射（指令/镜像/预算/artifact 字段）经前轮逐行核查，本轮引用存在性扫查确认映射入口仍全部真实存在；真实环境清理实效随 t032 实跑判定。

coverage = 5 / 7

verdict: PASS
