# Task review t028（reviewer_focus: 代码）

- task：`t028_runtime_isolation_quota_regression`
- spec：`docs/tasks/t028_runtime_isolation_quota_regression/task.md`
- diff_anchor：`2bbce465d16d958866691dd97bdbfd1cd7693616`
- target：`git diff 2bbce465d16d958866691dd97bdbfd1cd7693616`（仓库 CBrowser_t028，分支 t028_runtime_isolation_quota_regression）
- round：1
- reviewed_at：2026-11-04T12:44:13+08:00

reviewed_scope: 7c33f67e39250190

## Findings

### t028_code_f001 - 覆盖矩阵与 t032 运行映射引用了仓库中不存在的测试文件

- 严重度：important
- 锚点：AC-001（矩阵逐项列出现行入口、已覆盖条目引用具体断言、缺口均有可收集执行入口）与 AC-007（运行指令逐项映射到 t032）
- 位置：`docs/blueprint/testing.md:181`、`docs/blueprint/testing.md:196`、`docs/blueprint/testing.md:212`
- 问题：矩阵声称的「现行入口」中有两个文件在仓库与全部 git 历史中均不存在（`find` 与 `git log --all -- <path>` 均无结果）：(1) 第 181 行 p016「网络保护真实行为」行引用 `test_supervisor_network_protection_e2e.py`，实际网络类 E2E 是 `tests/e2e/test_supervisor_browser_network_e2e.py`、`tests/e2e/test_supervisor_network_ownership_e2e.py` 与 namespace/ipv6/policy_failure 三件；(2) 第 196 行 search-defaults 行引用 `test_search_defaults_runtime_chain.py`（integration），实际集成覆盖是 `tests/integration/test_api_search_defaults_routes.py` 等。更严重的是第 212 行 t032 运行映射把该不存在文件写进 AC-008 的单跑指令，t032 执行者照表运行会直接报 file not found。矩阵其余 22 个被引文件名已逐一核实存在，唯此两处悬空。
- 建议：把三处引用改成实际存在且覆盖对应行为的入口文件（网络保护行改引真实的 browser_network/network_ownership/namespace policy 入口，search-defaults 行改引 `test_api_search_defaults_routes.py`），或为确实缺失的行为补建入口；改后逐项复核矩阵全部引用可收集。

### t028_code_f002 - gate_evidence_manifest 对镜像身份收集的宽泛吞错可静默丢失 AC-005 证据

- 严重度：minor
- 锚点：AC-005（evidence 记录实际镜像 ID）／健壮性·可观测
- 位置：`scripts/gate_evidence_manifest.py:53`
- 问题：`except Exception: image_identity = {}` 本意只兜底环境构建失败时以裸解释器运行的回退路径，但它无条件生效：正常门禁（venv 内）运行时若 `e2e_env` 导入或收集真的出错，manifest 会静默写入空 `image_identity` 且 `all_passed` 不受影响，证据缺失无任何信号。
- 建议：仅在显式回退模式下吞错，或在 manifest 中记录 `image_identity_error` 字段标明收集失败，使证据缺失可观测。

### t028_code_f003 - 证据模式下 environment.log 未经脱敏直接保留

- 严重度：minor
- 锚点：AC-006 / AC-007（保留的证据日志须脱敏）
- 位置：`scripts/run_gates.sh:36`
- 问题：证据模式下各 suite 日志都经 `scripts/redact_evidence.py` 处理，唯独环境构建日志 `logs/environment.log` 由 uv 直接写入、从不脱敏，是证据目录里唯一未走脱敏通道的保留日志；若构建环境变量或索引 URL 含凭证形态文本，会原样落盘。
- 建议：环境构建输出先写临时 raw 文件，再与 suite 日志同样经 `redact_evidence.py` 落到 `logs/environment.log`（失败回退路径的 manifest 生成在其后，不受影响）。

## 结论

- 本轮新发现：3 条（important 1、minor 2）
- 未进表的提示：文件过大——无（本 task 触及文件最大 240 行，均未达阈值）；圈复杂度——无函数达 ≥15 阈值；范围外观察——无。本机无 Docker，Docker 相关 E2E 仅做 collect-only 与静态核查，未把 skip/collect 记为实跑通过。已知基线不重复报告：unit 的 `test_repo_hygiene` 失败（源于 t027 归档报告含绝对路径，干净 base 同 ID）、integration 的 `test_ac009_api_supervisor_start_and_stop_coordination`（干净 base 同签名环境性失败，本轮未重跑该文件）。
- 总体判断：矩阵/t032 映射存在悬空引用（f001，important），AC-001/AC-007 打勾不实，须修正后重审；其余实现（AC-002 精确断言、AC-005 fail-closed、AC-006 证据模式、stream_monitor 生产投递改线）经复验成立。
- 系统性 follow-up：无（f001 为本 task 文档修正，不另立项）。

### AC 复验方式

- AC-001：re_verified——逐行读矩阵并把全部被引测试文件名与仓库实际文件逐一比对（22 个存在、2 个悬空，见 f001）；t026 新拓扑条目引用其用例属实。
- AC-002：re_verified——读 `tests/integration/test_gateway_signaling.py` 新增断言（close data == 1001、新旧 conn_id 不同、下行 REPLY_FROM_A2 回复、旧 Agent 退出后 STILL_ALIVE 续传），实跑该用例通过、同文件 16 条全过。
- AC-003：trust_prior——依赖交付物本身：配额链入口可收集（collect-only 通过）、投递路径经静态核查确为生产 `GatewayControlClient.set_quota`（与 Supervisor runner 同一接线）、`stream_monitor.py` 已删 mock socket 旁路并改生产投递、proof 字段（deliveries/windows/帧窗）在代码中存在；但链路实跑（CPU counter、帧数、越权不突破）云端无 Docker 无任何运行证据，按 spec 执行环境约定归 t032 AC-008 判定。
- AC-004：re_verified——五个新入口均存在、可收集（本轮 collect-only 共 7 条含 x11 两条）且断言逐一读过；其中删除续跑用例在云端以真实 API 子进程实跑通过（本 reviewer 独立复跑 1 passed）；其余四腿的真实环境执行按约定归 t032，不冒充已验。
- AC-005：re_verified——unit 9 条全过（本轮实跑 t028 两 unit 文件共 13 条全过）；另以 tag 值实测 required 模式收集期逐变量明确拒绝并列出问题；`.scratch/images_env.txt` 旁路读取已删除且全仓无其他 `load_images_env` 消费方。
- AC-006：re_verified——unit 以 PATH stub 驱动真实 `run_gates.sh`：证据模式跑完全部 suite、失败总退出非零、manifest 含逐 suite 命令/退出码/JUnit/脱敏日志、默认 fail-fast 行为不变，4 条全过；manifest/redact 两脚本代码已读。
- AC-007：re_verified——t032 运行映射表逐项读过（指令、镜像/环境变量、预算、artifact 字段齐备），各 E2E 资源均带本轮唯一前缀且 finally 只清理自有资源、证据经 `save_evidence` 脱敏通道；唯映射中一处指令引用不存在文件，见 f001。

coverage = 6 / 7

verdict: FAIL

## Round 2 (2026-11-04T12:48:02+08:00)

- round：2
- target：相对 `2bbce465d16d958866691dd97bdbfd1cd7693616` 的完整 worktree diff（同 Round 1 口径）

reviewed_scope: e570c8f79524ba70

### 前轮 finding 复核

- t028_code_f001（important）：已消除。`docs/blueprint/testing.md` 网络保护行已改列现行五入口（browser_network / network_ownership / namespace / ipv6 / policy_failure），search-defaults 行已改列 `test_api_search_defaults_routes.py` 与 `test_runtime_coordinator_integration.py`，t032 映射 AC-008 指令同步改正。本轮对 testing.md 全部 `test_*.py` 引用再做存在性扫查：除一处先于本 task 的 spike 归档路径引用（`docs/archive/spikes/` 下文件实存、非本 diff 引入）外全部存在，悬空引用为零。
- t028_code_f002（minor）：已消除。`scripts/gate_evidence_manifest.py:53-56` 身份收集异常改为显式记录 `image_identity = {"error": "<类型>: <消息>"}`；本轮以无 pytest 的系统解释器实跑该脚本，manifest 实际写出 `image_identity.error = "ModuleNotFoundError: No module named 'pytest'"`，空 map 只再表示无镜像变量，证据缺失可观测。
- t028_code_f003（minor）：已消除（另有残余小缺口见本轮 f004）。`scripts/run_gates.sh:37-45` 构建输出先落 `environment.raw.log`、经 `redact_evidence.py` 脱敏生成 `logs/environment.log` 后删除 raw；unit 新增断言（environment.log 已脱敏且含脱敏标记、raw 不存在）随本轮实跑通过。
- 同源 test 路 t028_test_f002（important）：已消除。testing.md 资源段已改写为三层准确表述（unit 算法层 / resource 三 E2E 真实采样与决策、monitor 投递腿为本地回调 / 配额投递链归 quota chain E2E 与生产投递），虚假提交号已删除（全文扫查无该提交号与「退役」表述）；三文件实存且本轮 collect 在列。
- 同源 test 路 t028_test_f003（minor）：已消除。`tests/integration/test_gateway_signaling.py` AC-002 用例在旧 Agent 退出后新增 0.5s 静默窗口断言（窗口内收到 CLOSE/CLOSING/CLOSED 任一帧即失败），其后仍做存活往返；本轮实跑该文件 16 条全过。
- 同源 test 路 t028_test_f004（minor）：已消除。`tests/e2e/test_supervisor_quota_chain_e2e.py` 保留证据的 `cpu_policy` 已嵌入完整 `windows` 明细（counter 与决策）与 deliveries，不再只记窗数，证据不依赖临时 proof 文件存活。

### Findings

### t028_code_f004 - environment.log 脱敏失败时回退为未脱敏副本静默保留

- 严重度：minor
- 锚点：AC-006 / AC-007（保留的证据日志须脱敏）／健壮性·可观测
- 位置：`scripts/run_gates.sh:43-44`
- 问题：证据模式下 environment.log 的脱敏带 `|| cp environment.raw.log environment.log` 回退：当 `redact_evidence.py` 非零退出（系统 python3 缺失/损坏、脚本异常）时，未脱敏的构建原始输出被原样保留为正式证据日志且无任何告警，f003 的修复在该路径上不成立。正常路径（脱敏成功、raw 删除）已经 unit 断言覆盖并实跑通过，故仅记 minor。
- 建议：脱敏失败时改为写入显式占位内容（如一行 `redaction failed` 说明）或直接判门禁失败，不要把未脱敏原文落入保留证据。

## 结论

- 前轮 finding 复核：code 路 3 条与同源 test 路 4 条全部以 diff/代码/实跑核实已消除，无修不彻底项。
- 本轮新发现：1 条（minor 1：f004，f003 修复的回退路径残余）。
- 未进表的提示：文件过大——`tests/integration/test_gateway_signaling.py` 现 881 行，超测试源码 600 行 minor 阈值且本 task 净增约 50 行，按降级规则只在此提示、不进 finding 表；其余触及文件均未达阈值。圈复杂度——无函数达 ≥15。范围外观察——无。本机无 Docker，Docker 相关 E2E 仅 collect-only（本轮 6 文件 7 条全可收集）与静态核查，未把 skip/collect 记为实跑通过。已知基线不重复报告：unit `test_repo_hygiene`（t027 归档报告绝对路径，干净 base 同 ID）、integration `test_ac009`（干净 base 同签名环境性失败）。
- 总体判断：Round 1 全部 blocking/minor 修复真实成立，最终内容完整复审未见新的 critical/important；仅余 f004 一条 minor，不阻断。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：re_verified——逐行复读修正后矩阵与 t032 映射，并对 testing.md 全部测试文件引用做存在性扫查（悬空为零）；三层资源表述与仓库现状（三 resource E2E 实存可收集）一致。
- AC-002：re_verified——本轮实跑 `tests/integration/test_gateway_signaling.py` 全文件 16 passed；新增静默窗口断言逐行核对，close=1001、新旧 conn_id 不同、下行 REPLY_FROM_A2、旧 Agent 退出后 STILL_ALIVE 往返四项齐备。
- AC-003：trust_prior——与 Round 1 同口径：依赖交付物本身（入口本轮 collect-only 通过、投递路径静态核查为生产 `GatewayControlClient.set_quota`、保留证据已含完整 windows/deliveries 明细）；真实链实跑云端无 Docker、无运行证据，按 spec 执行环境约定归 t032。
- AC-004：re_verified——五个新入口本轮 collect-only 共 7 条全可收集且断言逐行复读；删除续跑用例本轮以 basetemp 置于 /tmp 独立实跑 1 passed（置于 home 目录时因本机 /home 挂载禁 chown 的已知环境约束失败，与实施笔记记录一致，非实现缺陷）；其余四腿真实环境执行归 t032。
- AC-005：re_verified——unit 9 条本轮实跑通过；另以 required 模式 + 镜像变量设为 tag/短摘要值实跑收集，收集期逐项报出「not an immutable sha256 image ID」明确失败，fail-closed 成立。
- AC-006：re_verified——unit 4 条本轮实跑通过（PATH stub 驱动真实 `run_gates.sh`，含 environment.log 脱敏新断言）；manifest/redact/run_gates 三脚本已通读，残余回退缺口见 f004。
- AC-007：re_verified——t032 运行映射逐项复读（指令已全部指向现行存在文件、镜像/环境变量、预算、artifact 字段齐备）；各 E2E 资源带本轮唯一前缀且 finally 只清理自有资源，证据经 `save_evidence`/脱敏通道保留。

coverage = 6 / 7

verdict: PASS

## Round 3 (2026-11-04T12:51:14+08:00)

- round：3
- target：相对 `2bbce465d16d958866691dd97bdbfd1cd7693616` 的完整 worktree diff（同 Round 1/2 口径，本轮为 f004 修复收尾重审）

reviewed_scope: 91b30ce90d1e8347

### 前轮 finding 复核

- t028_code_f004（minor，Round 2 新提出）：已消除。`scripts/run_gates.sh:45-49` 脱敏段已无 `|| cp` 回退（全 diff 扫查脚本内无该回退）：改为 `if ! python3 scripts/redact_evidence.py < environment.raw.log > environment.log`，失败分支写显式占位行 `environment log redaction failed; raw log withheld from evidence` 并向 stderr 输出 `gate evidence: warning: environment log redaction failed; raw log withheld` 告警，其后 `rm -f` 恒删除 raw 文件。本轮以 stub `python3` 使脱敏脚本对 environment.log 非零退出、实跑真实 `run_gates.sh` 证据模式独立验证失败路径：总流程不中断后续 suite、stderr 实际出现上述告警、保留的 `logs/environment.log` 内容恰为占位行一行、秘密形状文本未出现在其中、`logs/environment.raw.log` 不存在；正常路径（脱敏成功、raw 删除、含脱敏标记）仍由 unit 断言覆盖并随本轮 29 条实跑通过。修复与建议的占位方案一致，无残余。
- t028_code_f001（important）：仍消除。`docs/blueprint/testing.md` 全部 `test_*.py` 引用本轮再做存在性扫查，全部可定位到仓库现存文件（先于本 task 的 spike 归档引用亦实存），悬空引用为零；t032 映射指令同步指向现行文件。
- t028_code_f002（minor）：仍消除。`scripts/gate_evidence_manifest.py` 身份收集异常显式记录 `image_identity.error` 的实现未回退。
- t028_code_f003（minor）：仍消除（其回退残余即 f004，本轮已闭环，见上）。environment.log 正常路径经脱敏通道保留并删 raw，unit 断言本轮实跑通过。
- 同源 test 路 t028_test_f002 / f003 / f004（Round 2 已复核消除）：本轮相关实现与断言未回退——testing.md 三层资源表述未变、AC-002 静默窗口断言随 signaling 全文件本轮实跑通过、配额链保留证据的完整 `windows`/`deliveries` 明细未变。

### Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核：code 路 f001–f004 全部以 diff、代码与实跑核实已消除，无修不彻底项；f004 失败路径本轮以真实脚本实跑独立证伪了「静默保留未脱敏原文」的原失败场景。
- 本轮新发现：0 条。
- 未进表的提示：文件过大——`tests/integration/test_gateway_signaling.py` 现 881 行，超测试源码 600 行 minor 阈值且本 task 净增约 50 行，按降级规则只在此提示、不进 finding 表（与 Round 2 同一提示，非本轮新增问题，本轮未再向该文件增行）；其余触及文件均未达阈值（`scripts/run_gates.sh` 118 行、本轮 f004 修复仅改脱敏分支数行）。圈复杂度——无函数达 ≥15。范围外观察——无。本机无 Docker，Docker 相关 E2E 仅 collect-only（本轮 6 文件 7 条全可收集）与静态核查，未把 skip/collect 记为实跑通过。已知基线不重复报告：unit `test_repo_hygiene`（t027 归档报告绝对路径，干净 base 同 ID）、integration `test_ac009`（干净 base 同签名环境性失败）。
- 总体判断：Round 1 blocking 与历轮全部 minor 均已真实修复，最终内容完整复审未见回归或新的 critical/important/minor；本轮实跑 t028 相关 29 条测试（两 unit 文件加 signaling 全文件）全部通过，与实施侧自述一致。
- 系统性 follow-up：无。

### AC 复验方式

- AC-001：re_verified——逐行复读矩阵与 t032 映射，并对 testing.md 全部测试文件引用做存在性扫查（悬空为零）。
- AC-002：re_verified——本轮实跑 `tests/integration/test_gateway_signaling.py` 全文件通过（计入 29 条总数）；close=1001、新旧 conn_id 不同、下行回复、旧 Agent 退出后静默窗口与存活往返断言逐行复读齐备。
- AC-003：trust_prior——与 Round 1/2 同口径：依赖交付物本身（配额链入口本轮 collect-only 通过、投递路径静态核查为生产 `GatewayControlClient.set_quota`、保留证据含完整 windows/deliveries 明细）；真实链实跑云端无 Docker、无运行证据，按 spec 执行环境约定归 t032。
- AC-004：re_verified——五个新入口本轮 collect-only 共 7 条全可收集且断言与 Round 2 复读一致；其余四腿真实环境执行归 t032，不冒充已验。
- AC-005：re_verified——unit 9 条本轮实跑通过（计入 29 条总数）；required 模式 fail-closed 与 `.scratch` 旁路删除在最终 diff 中未回退。
- AC-006：re_verified——unit 4 条本轮实跑通过（计入 29 条总数，PATH stub 驱动真实 `run_gates.sh`，含默认 fail-fast 不变与失败总退出非零）；本轮另以脱敏失败 stub 实跑真实脚本，证据模式在脱敏失败时写占位行、发 stderr 告警且不保留 raw，未脱敏原文不进入证据目录。
- AC-007：re_verified——t032 运行映射逐项复读（指令全部指向现行存在文件、镜像/环境变量、预算、artifact 字段齐备）；各 E2E 资源独立与证据脱敏通道在最终 diff 中未回退，environment.log 脱敏失败路径本轮已闭环（见 f004 复核）。

coverage = 6 / 7

verdict: PASS
