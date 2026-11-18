# Task review t079（reviewer_focus: 通用）

- task：`t079_ui_status_errors_and_location_semantics`
- spec：`docs/tasks/t079_ui_status_errors_and_location_semantics/task.md`
- diff_anchor：`a8c916410d2e470de38d18c0c2e450a487ab1036`
- target：`git diff a8c916410d2e470de38d18c0c2e450a487ab1036`
- round：1
- reviewed_at：2026-11-18T02:12:11+08:00

reviewed_scope: 225c14b86a837b95

## Findings

### t079_gen_f001 - 格式合法但未分配/未知哨兵的国家代码仍被伪造国旗

- 严重度：important
- 锚点：AC-005「未知代码不伪造国旗，保留统一占位与可访问名称」
- 位置：`src/frontend/src/shared/presentation.ts:73`（`isRegionCode`）、`src/frontend/src/shared/presentation.ts:81`（`regionFlagEmoji`）、`src/frontend/src/shared/ui/StatusBadge.tsx:86`（`RegionBadge`）
- 问题：`isRegionCode` 只校验 `/^[A-Za-z]{2}$/` 格式，`regionFlagEmoji` 对任何双字母串都拼出区域指示符旗帜。因此后端 GeoIP 观测给出未分配代码或常见未知哨兵值（如 `XX`、`ZZ`、`AA`，`country_code` 列为 String(2) 且来自外部 GeoIP 数据，见 `src/backend/cbrowser/services/egress_probe.py:155`）时，`RegionBadge` 会渲染 🇽🇽 这类并不存在的国旗，而不是规格要求的 Globe 占位 + `regionUnknown` 可访问名；筛选候选标签（`ProxyListPage` 用同一 `regionFlagEmoji` 拼 label）同样受影响。新增测试 `src/frontend/src/shared/presentation.test.ts:85-91` 的「未知代码」夹具只有空串、`USA`、`U1`、`1S` 等格式非法值，没有覆盖格式合法但未分配的代码，假绿了这一分支。另外同一根因下 `regionEnglishName("ZZ")` 经 `Intl.DisplayNames` 得到 "Unknown Region" 作排序键、`"XX"` 得到 `"XX"` 本身，排序键亦非规范名称。
- 建议：把「有效地区」判定从纯格式校验改为真实分配校验，例如以 `Intl.DisplayNames(["en"], {type:"region"})` 的规范结果为准（结果等于代码本身或为 Unknown Region 时视为未知）或维护 CLDR 地区集合；`regionFlagEmoji` 对未分配代码返回 `null` 走占位分支，并补 `XX`/`ZZ` 夹具测试。

### t079_gen_f002 - 排序比较器内每次比较都新建 Intl.DisplayNames

- 严重度：minor
- 锚点：行为缺陷（性能）+ 国家候选排序时每比较一次即构造一次 ICU 对象
- 位置：`src/frontend/src/shared/presentation.ts:90`（`regionEnglishName`）、`src/frontend/src/shared/presentation.ts:142`（`sortCountryCandidates` 比较器在 152-153 行调用）
- 问题：`regionEnglishName` 每次调用都 `new Intl.DisplayNames(...)`，而 `sortCountryCandidates` 的比较器对每对元素各调用两次，构造次数随 O(n log n) 增长。当前国家候选规模小，无可观察故障，仅为无谓开销。
- 建议：把 `Intl.DisplayNames` 实例提升为模块级单例，或在排序前先为每个代码预算一次英文名再比较。

### t079_gen_f003 - 非拉丁城市排序测试未断言非拉丁名称本身的预期顺序

- 严重度：minor
- 锚点：AC-004「非拉丁名称使用明确本地化排序规则」测试覆盖偏弱
- 位置：`src/frontend/src/shared/presentation.test.ts:128`
- 问题：混合夹具用例只断言拉丁名 Kyoto < Osaka、集合大小不变与排序幂等，未断言 `东京`/`北京` 之间的预期顺序；若 collator 对汉字排序规则发生变化（如 ICU 升级改变拼音/笔画序），该用例仍会通过，无法守住 AC-004 对非拉丁名的明确排序承诺。实现本身（`compareNames` 单一 collator + 码点 tie-break）经复跑是确定性的，故仅记 minor。
- 建议：补一条断言非拉丁名相对顺序的用例，并注明所依据的 collator 规则。

## 结论

- 本轮新发现：3 条（important 1、minor 2）
- 未进表的提示：交付文件 `src/frontend/src/shared/presentation.ts` 与 `src/frontend/src/shared/presentation.test.ts` 在 git 中仍为未跟踪状态（`??`，未做 `git add -N`），reviewer 经文件系统直接读取核对，指纹行已按 prompt 给定值写入；门禁证据独立抽查与 progress 定性一致——unit 日志 4 失败/10 错误确为 t063×2 失败 + t063 built 系列 10 错误 + t068×2 失败，integration 4 错误确为 test_normal_exit_replay×2、test_supervisor_observation_authority、test_supervisor_manual_retry 四条，frontend 1 失败确为 ProxyListPage 列展示用例且本次单跑通过（见 AC 复验方式）。七视角已扫：安全（无注入/XSS/secret 引入，机器码仅进 title 诊断位）、契约·Breaking（`RegionCode` 更名 `RegionBadge` 为仓内组件、全部消费方已同步，i18n 删键后无残留引用，grep 核实）、健壮性（未知状态/错误码均有显式兜底，无吞错）、架构（单一 presentation 映射、无薄包装散落）除上表外无其他命中。
- 总体判断：AC-001/002/003/004/006 实现与测试真实成立；AC-005 对格式合法但未分配的未知代码仍伪造国旗（f001，important），故本轮 FAIL。
- 系统性 follow-up：无（f001 在本 task 内修复即可）

### AC 复验方式

- AC-001：TICK-VALID，re_verified。独立复跑 ProxyListPage/ProxyFormDialog 测试 41 条全过，失败状态断言本地化文案 `en.proxyErrorAuthFailed` 且机器码仅在 title；后端 grep 可达错误码全集（probe_failed、probe_bad_response、supervisor_unavailable、proxy_credentials_unavailable、echo_unreachable、echo_proxy_unsupported、invalid_echo_response、geoip_lookup_failed）与 presentation 映射逐一对齐，未知/缺失回退由 presentation.test 覆盖。
- AC-002：TICK-VALID，re_verified。独立复跑 presentation（10 条）、SessionHeader（20 条）、EnvironmentSwitcher（6 条）、SessionEntryPage 测试全过；grep 核实全部 observed_state 消费方（表格/卡片/详情/自动化/顶栏/切换器/入口）均经共享 `environmentStatusDescriptor`，缺失/枚举外值呈 statusUnknown 而非 stopped 或原始枚举。
- AC-003：TICK-VALID，re_verified。EnvironmentSwitcher 源码已移除每项右侧 StatusBadge、保留前置状态点与名称，并以 aria-label（`Alpha (Running)` 断言复跑通过）与 sr-only 文本承载状态；SessionHeader 测试复跑证实顶栏运行态中英分别为 运行中/Running、其余状态同词汇、传输徽标保留独立带主语文案。
- AC-004：TICK-VALID，re_verified。presentation.test 国家按规范英文名排序/按代码去重/与输入顺序无关、城市排序去重用例复跑通过；ProxyListPage 筛选测试复跑通过（国旗+名称标签选择、身份仍为代码、切换国家联动城市、全部项由工具栏固定首位）。
- AC-005：TICK-VOID，re_verified。表格/卡片/编辑弹窗三处 RegionBadge 与有效代码国旗+名称、格式非法代码占位均成立，但 f001 证实格式合法却未分配的代码（XX/ZZ/AA）仍被拼出伪造国旗，未满足「未知代码不伪造国旗」的完整承诺，打勾不成立。
- AC-006：TICK-VALID，re_verified。独立复跑 i18n.test（中英键集合严格相等且每键非空）通过；删键（sessRunning/sessStopped/envFilter\*/sessHeaderEnv\*）后 grep 无残留引用，en 词典中文残留仅 languageZh 本名一处；门禁证据 design_lint/design_check/frontend_build 均 exit 0，下拉去徽标后状态不重复呈现由 EnvironmentSwitcher 测试覆盖。

coverage = 6 / 6

verdict: FAIL

## Round 2 (2026-11-18T10:31:52+08:00)

- task：`t079_ui_status_errors_and_location_semantics`
- diff_anchor：`a8c916410d2e470de38d18c0c2e450a487ab1036`
- target：`git diff a8c916410d2e470de38d18c0c2e450a487ab1036`
- round：2

reviewed_scope: 06ec404687dd87f7

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核：
    - t079_gen_f001（important）：已消除。`src/frontend/src/shared/presentation.ts:96` 新增 `isKnownRegion`，以模块级 CLDR 英文名判定（`REGION_NAMES_EN.of()` 结果等于代码本身或为 "Unknown Region" 即未知）；`regionFlagEmoji`（`src/frontend/src/shared/presentation.ts:111`）对未知代码返回 `null`，`RegionBadge`（`src/frontend/src/shared/ui/StatusBadge.tsx:97`）据此走 Globe 占位 + `regionUnknown` 可访问名分支，筛选标签（`src/frontend/src/features/proxies/ProxyListPage.tsx:181`）经同一 `regionFlagEmoji` 拼 label、未知代码不带旗；`regionEnglishName`（`src/frontend/src/shared/presentation.ts:120`）对未知代码回退代码本身作排序键。补测真实覆盖哨兵：`src/frontend/src/shared/presentation.test.ts:96` 断言 XX/ZZ/AA 的 `isRegionCode=true`、`isKnownRegion=false`、`regionFlagEmoji=null`、排序键回退代码；`src/frontend/src/shared/ui/ui.test.tsx:235` 断言 RegionBadge 对 XX 呈占位且页面不出现 🇽🇽。reviewer 独立以 Node 24 复核 CLDR 行为：XX→"XX"、ZZ→"Unknown Region"、AA→"AA"，与判定逻辑一致；相关测试独立复跑全过。
    - t079_gen_f002（minor）：已消除。`Intl.DisplayNames(["en"], {type:"region"})` 已提升为模块级单例（`src/frontend/src/shared/presentation.ts:77`），本地化名称按 locale 缓存（`src/frontend/src/shared/presentation.ts:80`）；`sortCountryCandidates` 排序前为每个去重代码预算一次英文名存入 `sortKeys` 再比较（`src/frontend/src/shared/presentation.ts:168` 起），比较器内不再构造 ICU 对象。grep 全仓 `new Intl.DisplayNames` 仅剩这两处缓存构造点。
    - t079_gen_f003（minor）：已消除。`src/frontend/src/shared/presentation.test.ts:142` 新增用例断言 `sortCityCandidates(["北京","东京","上海"])` 精确等于 `["上海","东京","北京"]` 并断言 `compareNames("东京","北京") < 0`，注释注明依据为 `Intl.Collator("en")` 的 CLDR root 汉字 radical/stroke 序、ICU 升级时须连同 AC-004 规则一并复核。reviewer 独立以同一 collator 复跑得到 上海 < 东京 < 北京，与断言一致。
- 本轮新发现：0 条
- 未进表的提示：交付文件 `src/frontend/src/shared/presentation.ts`、`src/frontend/src/shared/presentation.test.ts` 在 git 中仍为未跟踪状态（`??`，未做 `git add -N`），与 Round 1 相同，reviewer 经文件系统直接读取核对，指纹行已按 prompt 给定值写入。CLDR 判定下 UK 等保留代码有名义名称、会得到旗帜，属 Round 1 建议的 CLDR 判定方法本身的边界，不在 f001 的未分配/哨兵范围（XX/ZZ/AA）内，不出 finding。reviewer 首次全量 vitest 复跑因与其它命令并行争用出现 worker 启动崩溃（573 过、0 条断言失败），单独以 `--maxWorkers=2` 重跑后 85 文件 697 条全过，定性为本机资源争用 flaky、非交付回归。门禁证据抽查：`.scratch/t079_gate_evidence3/suites.tsv` 与 progress 定性一致（design_lint/design_check/frontend_build/contract exit 0；unit/integration/frontend_test 的失败为修复前基线与负载 flaky），修复后证据由本轮独立全量复跑直接覆盖。
- 总体判断：Round 1 三条 finding 均以 diff 与独立复跑核实真实消除，修复未引入新问题；6 条 AC 全部成立，本轮 PASS。
- 系统性 follow-up：无

### AC 复验方式

- AC-001：TICK-VALID，re_verified。独立复跑 ProxyListPage 测试 26 条全过（失败状态呈本地化 `en.proxyErrorAuthFailed`、机器码仅在 title），presentation 错误码全集映射与兜底由 presentation.test 12 条覆盖并复跑通过，表格/卡片/编辑弹窗/详情四处消费方经 diff 核实共用 `proxyProbeErrorLabelKey`。
- AC-002：TICK-VALID，re_verified。独立复跑 presentation（12 条）、SessionHeader（20 条）、EnvironmentSwitcher（6 条）、SessionEntryPage（4 条）全过；diff 核实表格/卡片/详情/自动化/顶栏/切换器/入口均经共享 `environmentStatusDescriptor`，缺失/枚举外值呈 statusUnknown 而非 stopped 或原始枚举。
- AC-003：TICK-VALID，re_verified。EnvironmentSwitcher 源码已移除每项右侧 StatusBadge、保留前置状态点与名称，aria-label `Alpha (Running)` 与 sr-only 状态文本断言复跑通过；SessionHeader 复跑证实顶栏运行态中英分别为 运行中/Running、其余状态同词汇、传输徽标保留独立带主语文案。
- AC-004：TICK-VALID，re_verified。presentation.test 国家按规范英文名排序/按代码去重/与输入顺序无关、城市排序去重及新增非拉丁精确顺序（上海\<东京\<北京）用例独立复跑通过，reviewer 另以 Node collator 独立复现该顺序；ProxyListPage 筛选测试复跑通过（国旗+名称标签选择、身份仍为代码、切换国家联动城市）。
- AC-005：TICK-VALID，re_verified。f001 已消除：`isKnownRegion` 以 CLDR 规范名判定，XX/ZZ/AA 独立复跑断言无旗（presentation.test）且 RegionBadge 走 Globe 占位 + Unknown region 可访问名（ui.test 16 条复跑通过、断言不出现 🇽🇽），有效代码国旗+名称与筛选标签无旗分支经 ProxyListPage 复跑核实，打勾成立。
- AC-006：TICK-VALID，re_verified。独立复跑 i18n.test 5 条通过（中英键集合严格相等且每键非空）；删键（sessRunning/sessStopped/envFilter\*/sessHeaderEnv\*）后 grep 无残留引用；修复后独立全量复跑前端 vitest 85 文件 697 条全过、`test:types` exit 0，门禁证据 design_lint/design_check/frontend_build exit 0 抽查一致。

coverage = 6 / 6

verdict: PASS
