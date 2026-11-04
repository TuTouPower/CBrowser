# Task review t029（reviewer_focus: 代码）

- task：`t029_automation_compatibility_probe_harness`
- spec：`docs/tasks/t029_automation_compatibility_probe_harness/task.md`
- diff_anchor：`2c4d78ac8df3aaa001d489b575169a0b95422dbd`
- target：仓库根目录下 `git diff 2c4d78ac8df3aaa001d489b575169a0b95422dbd`
- round：1
- reviewed_at：2026-11-04T13:55:49+08:00

reviewed_scope: f85549915946777f

## Findings

### t029_code_f001 - state_changing_methods 按构造漏报 spec 自称已实测的状态改变命令，AC-002 的命令清单证据不完整

- 严重度：important
- 锚点：AC-002（须列出 attach 发出的改变共享浏览器状态的 CDP 命令）
- 位置：`tests/fixtures/automation_probe/harness.py:365`（`classify_cdp_method`）、`tests/fixtures/automation_probe/harness.py:699`（`CdpBridge.state_changing_methods`）
- 问题：`classify_cdp_method("Page.addScriptToEvaluateOnNewDocument")` 与 `classify_cdp_method("Target.setAutoAttach")` 均返回 `"other"`（reviewer 独立运行验证），而 `state_changing_methods()` 只收录类别 ∈ {closes_shared_state, download_policy, emulation_override, domain_enable, navigation}，两者必然被丢弃。但结论 spec `docs/specs/automation_compatibility.md:25` 明确把这两个方法列为「桥接记录实测」的 attach 状态改变命令，并声明「完整清单以报告中的 `state_changing_methods` 为准」——按交付代码生成的报告不可能包含 spec 声称已实测的这两项，AC-002 要求的命令清单证据自相矛盾、按构造不完整（凡分类落入 `other` 的状态改变命令都会被静默漏报）。注意 `MUST_MEDIATE_METHODS`（harness.py:396）含 addScript，故 t030 拦截清单本身不受影响，受损的是报告证据链。
- 建议：给 `Page.addScriptToEvaluateOnNewDocument` 增加独立类别（如 `script_injection`）并纳入 `state_changing_methods` 收录集，`Target.setAutoAttach` 归入 attach 配置类一并收录；或把收录规则改为「除 input_dispatch/page_evaluation/other 中的只读方法外全收录」并补 unit 断言覆盖这两个方法。

### t029_code_f002 - L0–L6 采样报告 levels.json 未走 build_report，不符合 spec 声明的 automation-probe-report/v1 报告格式

- 严重度：important
- 锚点：AC-007（全部探针在云端验证参数、报告格式与安全清理）
- 位置：`tests/fixtures/automation_probe/run_levels.py:250`
- 问题：采样驱动直接拼裸 dict `{"levels": ..., "summary": ..., "input_comparison": ...}` 写出 levels.json，未经 `build_report`：无 `schema`、无 toolchain 版本、无预登记阈值、无 `redact_report_value` 脱敏。而结论 spec `docs/specs/automation_compatibility.md:5` 声明探针报告格式为 `automation-probe-report/v1`、「含 toolchain 版本、预登记阈值与脱敏后的字段样本」——字段级样本恰恰只存在于 levels.json，该主采样产物与 spec 声明的报告格式不符。佐证：t032 入口 `tests/e2e/test_automation_compatibility_probe_e2e.py:66` 对 chain 报告断言 `schema == "automation-probe-report/v1"`，对 levels.json 却只断言 levels/summary/input_comparison 键存在，两条报告路径格式口径不一致，t032 按 v1 格式消费 levels.json 时会落空。
- 建议：run_levels 改走 `build_report(levels=..., summary=..., input_comparison=...)` 输出，并让 t032 levels 复核同样断言 schema；注意与 f004 一并处理脱敏误伤后再嵌入字段样本。

### t029_code_f003 - AC-002 的「超时后存活」子项无任何实测：全链测试只跑正常退出，客户端从未被超时杀死后断言存活

- 严重度：important
- 锚点：AC-002（自动化子进程正常退出、**异常或超时**后，已有用户页面与浏览器仍存活）
- 位置：`tests/integration/test_automation_probe_chain.py:360` 与 `:480`（两处 `--disconnect` 均为 `exit`）
- 问题：AC-002 枚举正常退出 / 异常 / 超时三种断开。交付证据中：正常退出由 matrix `--disconnect exit`（`os._exit(0)`）覆盖；异常退出由 Dialog leave 场景 `os._exit(3)` 覆盖且断言页面存活。但「超时」——已 attach 的自动化进程被外部超时杀死（如 SIGKILL）后浏览器/Profile 存活——没有任何用例执行：全仓 grep 无对已连接客户端的 kill/terminate 路径，`probe_client.py` 支持的 `close`/`stop` 断开模式也从未被集成测试使用。task.md 中 AC-002 已打勾，结论 spec 的对应表述亦悄悄只写「正常退出、异常退出」，超时子项属打勾未实测。
- 建议：补一个全链用例：hold/matrix 客户端 attach 后由测试侧超时杀死进程（SIGKILL），随后断言浏览器 pid 存活、用户页面可 evaluate、Agent 下载捕获仍可用；或若判定超时与异常退出在隧道视角等价，须在 spec 中写明等价依据并回改 AC 表述，不得静默略过。

### t029_code_f004 - redact_report_value 按键名子串匹配脱敏，会把信号字段 cookieEnabled 等误伤为 <redacted>（潜伏）

- 严重度：minor
- 锚点：行为缺陷（潜伏）——报告脱敏误伤字段级证据
- 位置：`tests/fixtures/automation_probe/harness.py:405`（`_SECRET_KEY_RE`）、`tests/fixtures/automation_probe/harness.py:250`（SIGNAL_SCRIPT 的 `cookieEnabled` 字段）
- 问题：`_SECRET_KEY_RE = (token|password|secret|authorization|cookie)` 对 dict 键做子串搜索，reviewer 独立验证 `build_report(samples=[{"cookieEnabled": True, "tokenCount": 3}])` 输出两值均被替换为 `<redacted>`。`cookieEnabled` 是 SIGNAL_SCRIPT 的正式观测字段；当前 levels 报告未走 build_report（见 f002）故尚未触发，但一旦按 f002 建议把字段样本嵌入 v1 报告，脱敏会静默 destroy 该字段的全部样本值，且报告读者无从察觉。
- 建议：键名匹配改为精确键或词边界（如 `^(.*_)?(token|password|secret|authorization|cookie)$` 类锚定），并补 unit 断言 `cookieEnabled` 原值保留、真凭证键仍被脱敏。

### t029_code_f005 - harness 存在未被任何调用方引用的死代码

- 严重度：minor
- 锚点：行为缺陷（可维护性）——死代码
- 位置：`tests/fixtures/automation_probe/harness.py:273`（`READ_EVENTS_SCRIPT` / `READ_FRAME_EVENTS_SCRIPT`）、`tests/fixtures/automation_probe/harness.py:500`（`XTestInput.double_click`）
- 问题：全仓 grep 显示两个 READ_*_SCRIPT 常量除定义外零引用（各客户端均内联自己的 evaluate 字符串），`XTestInput.double_click` 无任何调用方。作为交付给 t030/t032 复用的探针 API，死导出会让后续使用者误判正式读取路径。
- 建议：删除三处死代码，或让 probe_client/run_levels 统一改用 READ_EVENTS_SCRIPT 读取事件以消除重复内联。

## 结论

- 本轮新发现：5 条（important 3、minor 2、critical 0）
- 未进表的提示：
  - 文件行数（测试侧文件，按标准仅提示不进表）：`tests/fixtures/automation_probe/harness.py` 916 行、`tests/integration/test_automation_probe_chain.py` 807 行，均超过测试源码 600 行 minor 提示线、未达 1200 行 important 线；本 task 为新建/净增，建议后续按职责拆分（观测页/桥接/宿主 runner 可分文件）。
  - 复杂度提示：`tests/fixtures/automation_probe/probe_client.py` 的 `run_dialog` 手算圈复杂度约 12（四场景分支叠加），达结论提示线（≥10），未进表；后续加场景时建议按 scenario 拆函数。
  - 范围外观察：AC-005 的 XTEST iframe 子项未单独采样、缩放子项 INCONCLUSIVE，均已在 spec 中如实披露并指派 t032 复核，不出 finding；集成测试中 dialog handle_new 的具体结论字段（opening_replayed / commands_blocked）只入报告未做断言，属测试层强度问题，留待 test reviewer 判定。
  - 安全/契约/性能视角已扫：探针新增监听均为 loopback（ObservationServer、CdpBridge），无裸 CDP TCP 暴露，无硬编码凭证（测试 token 由 `secrets` 生成），XTEST 命令经 stdin 传入无 shell 拼接，未命中 finding。
- AC 复验方式：
  - AC-001：trust_prior——静态逐行核对 probe_client matrix 模式与全链测试断言（popup/iframe/snapshot ref/download/双模式）齐全；真实浏览器实跑依赖实施侧门禁记录与 spec 转录，本 reviewer 环境无目标引擎缓存/完整 Chromium/门禁 venv，未能独立重跑。
  - AC-002：trust_prior——静态核对断开存活断言与 rearm 下载断言存在；且 f001（命令清单机制漏报）、f003（超时子项未实测）指出其证据缺口。
  - AC-003：trust_prior——静态核对无 token/错误 token/跨 Profile 三种拒绝断言与外部 Browser.close 停 Profile 测试存在；实跑依赖实施侧记录。
  - AC-004：re_verified（判定规则部分）——reviewer 以系统 python 独立复跑 `compare_level_samples` / `summarize_levels`，验证「落在 L0 之外且 ≥4/5 复现才记新增变化、样本 <5 记 insufficient」与 AC 预登记阈值一致；每级 5 个独立进程的实跑采样本身为 trust_prior，依赖实施侧 levels 报告与 note 记录。
  - AC-005：trust_prior——静态核对 run_levels 的 CDP/XTEST 双腿采样代码与 spec 比较表、采用规则一致；实测数值依赖实施侧报告。
  - AC-006：trust_prior——静态核对 dialog 四场景（pending/leave/handle_new/beforeunload 双激活方式）在普通 Chromium 全链与目标引擎直连两套测试中的存在与关键断言；实跑结论依赖实施侧报告。
  - AC-007：re_verified——直接读取并交叉核对 `docs/specs/automation_compatibility.md`、`docs/blueprint/automation.md`、`docs/blueprint/testing.md`：证据分级（云端已验/目标待验/否决条件）、t030 拦截清单与 MUST_MEDIATE_METHODS 一致、t031/t032 输入与 t032 e2e 入口均在位；但报告格式一致性存在 f002 缺口。
  - coverage = 2/7
  - 建议合并前人工抽查 trust_prior 项（占比 5/7 > 30%）：重点抽查 AC-001/AC-002 的全链实跑报告（chain-target.json）与 AC-004 的 levels.json 原始样本。
- 总体判断：探针结构与主要结论链完整，但 AC-002 的命令清单证据存在按构造漏报（f001）、主采样报告格式与 spec 声明不符（f002）、AC-002 超时子项打勾未实测（f003），三条 important 未解决，判定 FAIL。
- 系统性 follow-up：无（三条 important 均为本 task 内可修，不需另立 task；f002/f004 修复时注意联动）

verdict: FAIL

## Round 2 (2026-11-04T14:22:31+08:00)

- task：`t029_automation_compatibility_probe_harness`
- diff_anchor：`2c4d78ac8df3aaa001d489b575169a0b95422dbd`
- target：仓库根目录下 `git diff 2c4d78ac8df3aaa001d489b575169a0b95422dbd`
- round：2
- reviewed_at：2026-11-04T14:22:31+08:00

reviewed_scope: 57d3ed7ec37c791e

### 前轮 finding 复核

- t029_code_f001（important）——**已消除**。以当前代码核实（不采信处置表）：`tests/fixtures/automation_probe/harness.py:362-374` 新增 `_INJECTION_METHODS`/`_ATTACH_METHODS`，`classify_cdp_method` 返回 `script_injection`/`target_attach`；`harness.py:727-740` 的 `state_changing_methods()` 收录集已含这两类。reviewer 以门禁 venv 独立运行复现：两方法分类正确、`CdpBridge.state_changing_methods()` 在含 `Browser.getVersion` 的日志中恰好返回这两项；unit 全套 8 passed。实跑产物 `~/gate_scratch_t029/reports/chain-target.json` 的 `state_changing_methods` 中两方法以新类别多次出现，与 spec 清单一致。
- t029_code_f002（important）——**已消除**。`tests/fixtures/automation_probe/run_levels.py:412-414` 已改走 `build_report(levels=..., summary=..., input_comparison=...)`；`tests/e2e/test_automation_compatibility_probe_e2e.py:92-95` 对 levels.json 断言 `schema == "automation-probe-report/v1"` 及各级样本数/verdict。只读核对实跑产物 `~/gate_scratch_t029/reports3/levels.json`：含 `schema=automation-probe-report/v1`、`toolchain`、`threshold`、`must_mediate_methods`，levels 为 L0–L5 与 L6_cdp_input/L6_xtest_input 共 8 键、各 5 样本，summary verdict 与 spec 一致。两条报告路径格式口径已统一。
- t029_code_f003（important）——**已消除**。新增 `tests/integration/test_automation_probe_chain.py:838` 的 `test_probe_chain_client_killed_mid_connection_survival`：经真实 `_Chain`（API→Supervisor→Agent UDS）以 hold（L4）客户端 attach、ready 文件确认连接建立后于 `:909` 执行 `proc.kill()`（SIGKILL，即超时/中止杀死路径），随后断言浏览器 pid 存活（`:912`）且用户页面仍可 evaluate 且标题正确（`:913-915`）。核心缺口（超时路径零实测）已补。保留说明：该用例浏览器为普通 Chromium、且未单独断言 kill 后 Agent 下载捕获——断开后捕获已由目标引擎 matrix 的正常退出路径覆盖，此点不构成 AC-002 缺口复现。
- t029_code_f004（minor）——**已消除**。`harness.py:426-440` 的 `_is_secret_key` 改为 camel/snake/kebab token 化判定（敏感词独占 key 或位于非首 token 时才脱敏）。reviewer 独立运行 `build_report` 复现：`cookieEnabled=True`、`tokenCount=3` 原值保留，`session_cookie`/`authToken`/`access_token` 均被脱敏；unit 回归测试 `test_redact_report_value_keeps_signal_fields` 在位且通过；实跑产物 reports3/levels.json 中全部 `cookieEnabled` 样本值为 True、无误伤 `<redacted>`。本轮修复新引入的另一键形边角见 f006（独立 minor，不影响 f004 结论）。
- t029_code_f005（minor）——**已消除**。全仓 grep：`READ_FRAME_EVENTS_SCRIPT` 与 `XTestInput.double_click` 已删除（零残留）；`READ_EVENTS_SCRIPT` 已被 `run_levels.py:223/263/328/359` 正式使用，不再是死导出。reviewer 另以 AST+引用扫描复查 harness 全部顶层定义：仅 `HostBrowserRunner.setup_pulse/setup_display/_configure_window` 无文本引用，系对 `BrowserRunner` 基类的多态 override，非死代码。

### Findings（本轮新发现）

### t029_code_f006 - _is_secret_key 的 apikey token 对 api_key / apiKey 键形永不命中，脱敏覆盖存在潜伏缺口

- 严重度：minor
- 锚点：行为缺陷（潜伏）——报告脱敏覆盖缺口；当前任何实跑报告均无此键形，未造成实际泄漏
- 位置：`tests/fixtures/automation_probe/harness.py:417`（`_SECRET_KEY_TOKENS` 含 `"apikey"`）、`tests/fixtures/automation_probe/harness.py:426-440`（`_is_secret_key` 的 token 化）
- 问题：reviewer 以门禁 venv 独立运行 `build_report(samples=[{"api_key": "z", "apikey": "w", "cookies": "v"}])`，输出 `api_key` 原值 `"z"` 未脱敏、`apikey` 被脱敏。原因：`api_key`/`apiKey` 经 `_KEY_SPLIT_RE`/`_CAMEL_RE` 切分后均为 tokens `[api, key]`，多 token 分支只查 `tokens[1:]` 即 `key`，与集合中的 `"apikey"` 永不相等——该 token 仅对字面键 `apikey` 可达，对最常见的下划线/驼峰键形是死条目，与集合声明的意图不一致。只读核对全部 gate 报告的键集，与敏感词相关的键只有 `cookieEnabled`/`dpr_after_zoom_keys`/`key`，故目前仅为潜伏问题，定 minor。
- 建议：token 化后同时比对拼接形（如 `"".join(tokens)` 与集合比对），或为 `api[-_]?key` 类键形加显式规则；补 unit 断言 `api_key`、`apiKey` 两键形均被脱敏。

## 结论

- 前轮 finding 复核：f001/f002/f003 三条 important 与 f004/f005 两条 minor 均以当前 diff、独立运行与实跑产物核实为**已消除**（证据见上逐条说明，未采信 note.md 处置表自述）。
- 本轮新发现：1 条（minor 1、important 0、critical 0）
- 未进表的提示：
  - 文件行数（测试侧文件，按标准仅提示不进表）：`tests/fixtures/automation_probe/harness.py` 946 行、`tests/integration/test_automation_probe_chain.py` 989 行，仍超测试源码 600 行 minor 提示线、未达 1200 行 important 线；本轮为修复继续净增，建议后续按职责拆分。
  - 复杂度提示：`tests/fixtures/automation_probe/probe_client.py` 的 `run_dialog` 圈复杂度约 12（Round 1 已提示，本轮未恶化），不进表。
  - 安全/契约/性能/健壮性视角已全量重扫：探针监听仍均为 loopback、无裸 CDP TCP 暴露、无硬编码凭证（token 由 `secrets` 生成）、实跑报告无本机绝对路径与 `cbat_` 真值残留（grep 计数 0）；`MUST_MEDIATE_METHODS` 与 spec/blueprint 拦截清单一致；除 f006 的潜伏键形边角外未命中新问题。
- AC 复验方式：
  - AC-001：trust_prior——静态核对 matrix 双模式代码与断言，并交叉核对实跑产物 chain-target.json 中双模式 matrix 结果（popup/iframe/download/断线字段齐全）；真实浏览器实跑本身依赖实施侧门禁记录，本轮未独立重跑全链。
  - AC-002：trust_prior——其机制部分经 reviewer 独立复验（分类/state_changing 的 unit 运行与产物清单核对、kill 用例代码逐行核实，见 f001/f003 复核）；浏览器存活的实跑结论依赖实施侧集成门禁记录。
  - AC-003：trust_prior——静态核对授权拒绝/跨 Profile/外部 Browser.close 用例与 `_Chain` 真实组件构成；实跑依赖实施侧记录。
  - AC-004：re_verified（判定规则与报告产物）——独立核对 reports3/levels.json 的结构与数值（8 键×5 样本、summary verdict、cookieEnabled 样本未被脱敏误伤），判定规则与预登记阈值一致（Round 1 已独立复跑 compare/summarize）；每级 5 个独立进程的采样实跑本身为 trust_prior，依赖实施侧 levels 报告。
  - AC-005：trust_prior——交叉核对 reports3/levels.json 的 input_comparison（cdp 误差 [0, −0.88]、xtest [10, −10.88]、zoom/focus_contention 各 2 条）与 spec 比较表及采用规则一致；实测过程依赖实施侧报告。
  - AC-006：trust_prior——静态核对 dialog 四场景在两套测试中的存在（handle_new 等断言强化属 test reviewer 处置范围）；实跑结论依赖实施侧报告。
  - AC-007：re_verified——直接读取并交叉核对 `docs/specs/automation_compatibility.md`、`docs/blueprint/automation.md`、`docs/blueprint/testing.md` 与 t032 e2e 入口：证据分级、拦截清单、t031/t032 输入均在位，且 Round 1 指出的报告格式不一致（f002）已消除。
  - coverage = 2/7
  - 建议合并前人工抽查 trust_prior 项（占比 5/7 > 30%）：重点抽查 AC-001/AC-002 的全链实跑报告（chain-target.json）与 AC-004 的 levels.json 原始样本。
- 总体判断：Round 1 的三条 important 已全部经独立核实消除，本轮仅新增一条潜伏 minor（f006，须由 implementer 写入 note.md 处置表），无未解决 critical / important，判定 PASS。
- 系统性 follow-up：无

verdict: PASS

## Round 3 (2026-11-04T14:26:05+08:00)

- task：`t029_automation_compatibility_probe_harness`
- diff_anchor：`2c4d78ac8df3aaa001d489b575169a0b95422dbd`
- target：仓库根目录下 `git diff 2c4d78ac8df3aaa001d489b575169a0b95422dbd`
- round：3
- reviewed_at：2026-11-04T14:26:05+08:00

reviewed_scope: 76ccd941159cb86e

### 前轮 finding 复核

- t029_code_f001（important）——**仍保持消除**。`tests/fixtures/automation_probe/harness.py:362-374` 的 `_INJECTION_METHODS`/`_ATTACH_METHODS` 与分类 `script_injection`/`target_attach` 在位；`harness.py:731-750` 的 `state_changing_methods()` 收录集仍含这两类；本轮以门禁 venv 独立重跑 unit 全套（9 passed），其中 `test_classify_cdp_method_categories` 与 `test_state_changing_methods_include_injection_and_attach` 通过。
- t029_code_f002（important）——**仍保持消除**。`tests/fixtures/automation_probe/run_levels.py:417-419` 仍走 `build_report(levels=..., summary=..., input_comparison=...)`；只读复核实跑产物 `~/gate_scratch_t029/reports3/levels.json` 仍为 `schema=automation-probe-report/v1`、含 toolchain/threshold、8 个 level 键；`tests/e2e/test_automation_compatibility_probe_e2e.py:92-95` 对 levels 报告的 schema/样本数/verdict 断言在位且本轮进一步收紧（见结论）。
- t029_code_f003（important）——**仍保持消除**。`tests/integration/test_automation_probe_chain.py:838` 的 `test_probe_chain_client_killed_mid_connection_survival` 在位，`:909` `proc.kill()` 后 `:912-915` 断言浏览器 pid 存活与用户页面可 evaluate，本轮代码未被改动削弱。
- t029_code_f004（minor）——**仍保持消除**。reviewer 独立运行 `build_report` 复现：`cookieEnabled=True`、`tokenCount=3` 原值保留，`session_cookie`/`authToken`/`access_token` 仍被脱敏；unit 回归测试通过。
- t029_code_f005（minor）——**仍保持消除**。全仓 grep `READ_FRAME_EVENTS_SCRIPT` 与 `XTestInput.double_click` 仍零残留；`READ_EVENTS_SCRIPT` 仍被 `run_levels.py` 多处正式使用。
- t029_code_f006（minor，Round 2 新发现）——**已消除**。以当前代码核实（不采信处置表）：`harness.py:426-450` 的 `_is_secret_key` 在 token 化后新增相邻对规则 `"apikey" in tokens or tokens[-2:] == ["api", "key"]`。reviewer 以门禁 venv 独立运行 `build_report` 复现：`api_key`、`apiKey`、`apikey`、`API_KEY`、`api-key`、`x_api_key`、`myApiKey` 全部输出 `<redacted>`，同时 `cookieEnabled`、`tokenCount`、`monkey` 原值保留（无新误伤）；新增 unit 测试 `test_redact_report_value_catches_api_key_spellings`（含 `monkey` 不误伤断言）在位且通过，unit 全套由 8 增至 9 passed。本轮残余的同族键形边角（复数形/private_key）为 f006 定义范围（api_key/apiKey/apikey）之外的独立问题，另立 f007，不影响 f006 消除结论。

### Findings（本轮新发现）

### t029_code_f007 - _is_secret_key 仍漏 private_key 与复数键形（cookies/api_keys/tokens），脱敏覆盖同族残余缺口

- 严重度：minor
- 锚点：行为缺陷（潜伏）——报告脱敏覆盖缺口；只读核对全部 gate 报告键集，无任何实跑报告含此类键，未造成实际泄漏，置信度中
- 位置：`tests/fixtures/automation_probe/harness.py:410-418`（`_SECRET_KEY_TOKENS` 仅含单数形）、`tests/fixtures/automation_probe/harness.py:440-450`（`_is_secret_key` 的 token 等值与 apikey 相邻对规则）
- 问题：reviewer 以门禁 venv 独立运行 `_is_secret_key` 复现：`private_key`、`cookies`、`api_keys`、`tokens`、`secrets`、`passwords`、`credentials` 均返回 False（不脱敏），而 `client_secret`、`bearer_token`、`x-api-key`、`refresh_token` 返回 True。原因与 f006 同族：敏感词集合只有单数 token，尾随 `key` 仅对 `api` 前缀设了相邻对规则，`private_key` 的 tokens `[private, key]` 两条规则均不命中；复数形与单数 token 永不相等。若后续探针报告嵌入此类键名的真实凭证值，将明文进入报告。与 f006 的区别：f006 指定的 `api_key`/`apiKey` 键形已按其建议修复，本条是修复后仍残留的相邻键形，不构成 f006 复发。
- 建议：把相邻对规则一般化为「尾随 `key` 且前一 token ∈ {api, private} 时脱敏」，并对集合 token 做单复数归一（如同时比对去尾 `s` 形）；补 unit 断言 `private_key`、`cookies`、`api_keys` 被脱敏且 `key`（事件字段，gate 报告中真实存在）、`monkey`、`cookieEnabled` 仍保留。

### t029_code_f008 - 缩放采样只发送 ctrl+plus 两次，spec 声称的 Ctrl+equal keysym 在交付代码中从未被试

- 严重度：minor
- 锚点：行为缺陷——文档与实现不一致（AC-005 缩放子项证据表述超出交付代码实际执行范围；该子项结论本身为 INCONCLUSIVE 并已指派 t032，不改变 XTEST 采用判定）
- 位置：`tests/fixtures/automation_probe/run_levels.py:350`（`for keys in ("ctrl+plus", "ctrl+plus")`）、`docs/specs/automation_compatibility.md:61`
- 问题：spec 写「浏览器级缩放快捷键（Ctrl+plus / Ctrl+equal 两种 keysym）未生效、DPR 恒为 1」，但交付的采样驱动在缩放循环中两次发送的都是 `ctrl+plus`，全仓 grep 与 gate 产物（reports3/levels.json、input-extra.json）均无 `ctrl+equal` 的发送记录——第二种 keysym 未生效的结论没有交付代码或产物证据支撑，且 t032 按交付驱动复跑也不会补上该 keysym。本轮新增的 zoom `verdict` 字段（`run_levels.py:364-368`：DPR≠1 记 `measured`、否则 `inconclusive_shortcut_ineffective`）逻辑本身正确，与 DPR 恒为 1 的实测及 spec 的 INCONCLUSIVE 表述一致，问题仅在 keysym 覆盖表述。
- 建议：把元组改为 `("ctrl+plus", "ctrl+equal")` 使两种 keysym 各发送一次（采样次数不变），或把 spec 第 61 行表述回改为仅 Ctrl+plus 已试、Ctrl+equal 未试；二选一即可，勿维持现状表述。

## 结论

- 前轮 finding 复核：f001/f002/f003 三条 important 与 f004/f005 两条 minor 仍保持消除；Round 2 的 f006（minor）已按其指定键形与修复建议消除（证据见上逐条说明，未采信 note.md 处置表自述）。
- 本轮新发现：2 条（minor 2、important 0、critical 0）
- 本轮小修扫描：harness `_is_secret_key` 相邻对修复无新误伤（`cookieEnabled`/`tokenCount`/`monkey` 独立复现保留）；run_levels zoom `verdict` 取值与实测 DPR 及 e2e 新断言的取值集 `{measured, inconclusive_shortcut_ineffective}` 一致（reports3 旧产物无 verdict 字段系修复前生成，e2e 系重跑驱动后断言，不构成不一致）；e2e/integration 断言收紧方向正确——e2e 新增对 cdp/xtest/zoom/focus 条目 `client_error is not None`、zoom verdict 集合、focus 布尔的断言，integration 的 dialog `opening_replayed is False`/`commands_blocked is False` 等具体结论断言在位，未见弱化或恒真断言；unit 的 `Any` 导入（`tests/unit/test_automation_probe_harness.py:7`）已被 `:142` 实际使用，非闲置导入。
- 未进表的提示：
  - 文件行数（测试侧文件，按标准仅提示不进表）：`tests/fixtures/automation_probe/harness.py` 950 行、`tests/integration/test_automation_probe_chain.py` 989 行，仍超测试源码 600 行提示线、未达 1200 行 important 线。
  - 复杂度提示：`tests/fixtures/automation_probe/probe_client.py` 的 `run_dialog` 圈复杂度约 12（前两轮已提示，本轮未恶化），不进表。
  - 测试结构观察（属 test reviewer 范畴，不进本表）：新增 unit 测试 `test_redact_report_value_catches_api_key_spellings` 尾部混入了与脱敏无关的 `classify_cdp_method`/`MUST_MEDIATE_METHODS` 断言，断言本身有效且通过，仅结构上建议拆分。
  - 安全/契约/性能/健壮性视角已扫本轮 diff：探针监听仍均为 loopback、无裸 CDP TCP 暴露、无硬编码凭证、XTEST 命令无 shell 拼接；除 f007 的潜伏键形边角外未命中新问题。
- AC 复验方式：
  - AC-001：trust_prior——静态核对 matrix 双模式代码与断言，并交叉核对实跑产物 chain-target.json 的双模式结果字段；真实浏览器实跑本身依赖实施侧门禁记录，本轮未独立重跑全链。
  - AC-002：trust_prior——其机制部分经 reviewer 独立复验（分类/state_changing/脱敏的 unit 独立重跑 9 passed、kill 用例代码逐行核实，见 f001/f003/f006 复核）；浏览器存活的实跑结论依赖实施侧集成门禁记录。
  - AC-003：trust_prior——静态核对授权拒绝/跨 Profile/外部 Browser.close 用例与 `_Chain` 真实组件构成；实跑依赖实施侧记录。
  - AC-004：re_verified（判定规则与报告产物）——独立重跑 unit 中 compare/summarize 阈值用例通过，并复核 reports3/levels.json 结构（v1 schema、8 键×5 样本、cookieEnabled 样本未被误伤）；每级 5 个独立进程的采样实跑本身为 trust_prior，依赖实施侧 levels 报告。
  - AC-005：trust_prior——交叉核对 reports3/levels.json 的 input_comparison（cdp 误差 [0, −0.88]、xtest [10, −10.88]、zoom DPR 恒 1）与 spec 比较表、采用规则及本轮新增 zoom verdict 逻辑一致；缩放 keysym 表述边角见 f008；实测过程依赖实施侧报告。
  - AC-006：trust_prior——静态核对 dialog 四场景在普通 Chromium 全链与目标引擎两套测试中的存在及本轮收紧后的具体结论断言；实跑结论依赖实施侧报告。
  - AC-007：re_verified——直接读取并交叉核对 `docs/specs/automation_compatibility.md`、`docs/blueprint/automation.md`、`docs/blueprint/testing.md` 与 t032 e2e 入口：证据分级、拦截清单、t031/t032 输入均在位，报告格式口径统一（f002 已消除）；spec 内部一处 keysym 表述超出代码证据，见 f008。
  - coverage = 2/7
  - 建议合并前人工抽查 trust_prior 项（占比 5/7 > 30%）：重点抽查 AC-001/AC-002 的全链实跑报告（chain-target.json）与 AC-004 的 levels.json 原始样本。
- 总体判断：Round 2 的 f006 已独立核实消除，Round 1/2 全部 finding 保持消除；本轮仅新增两条潜伏/表述类 minor（f007、f008，须由 implementer 写入 note.md 处置表），无未解决 critical / important，判定 PASS。
- 系统性 follow-up：无

verdict: PASS

## Round 4 (2026-11-04T15:34:14+08:00)

- task：`t029_automation_compatibility_probe_harness`
- diff_anchor：`2c4d78ac8df3aaa001d489b575169a0b95422dbd`
- target：仓库根目录下 `git diff 2c4d78ac8df3aaa001d489b575169a0b95422dbd`
- round：4
- reviewed_at：2026-11-04T15:34:14+08:00

reviewed_scope: 6a0d27b116cbdfcb

### 前轮 finding 复核

- t029_code_f001（important）——**仍保持消除**。`tests/fixtures/automation_probe/harness.py:362-374` 的 `_INJECTION_METHODS`/`_ATTACH_METHODS` 与分类 `script_injection`/`target_attach` 在位；`harness.py:731-750` 的 `state_changing_methods()` 收录集仍含这两类；本轮以门禁 venv 独立运行复现：两方法分类正确，含 `Browser.getVersion` 的日志中恰好只返回这两项。
- t029_code_f002（important）——**仍保持消除**。`tests/fixtures/automation_probe/run_levels.py:417-419` 仍走 `build_report(levels=..., summary=..., input_comparison=...)`；`tests/e2e/test_automation_compatibility_probe_e2e.py:90` 对 levels 报告断言 `schema == "automation-probe-report/v1"` 在位。
- t029_code_f003（important）——**仍保持消除**。`tests/integration/test_automation_probe_chain.py:838` 的 `test_probe_chain_client_killed_mid_connection_survival` 在位，`:909` `proc.kill()`（SIGKILL）后断言浏览器存活与用户页面可 evaluate 的代码未被改动削弱。
- t029_code_f004（minor）——**仍保持消除**。本轮独立运行 `build_report` 复现：`cookieEnabled=True`、`tokenCount=3` 原值保留，`session_cookie`/`authToken`/`access_token` 仍被脱敏；unit 回归测试通过（见下文 10 passed）。
- t029_code_f005（minor）——**仍保持消除**。全仓 grep `READ_FRAME_EVENTS_SCRIPT` 与 `XTestInput.double_click` 仍零残留；`READ_EVENTS_SCRIPT` 仍被 `run_levels.py:223/263/328/359` 正式使用。
- t029_code_f006（minor）——**仍保持消除**。本轮独立运行复现：`api_key`、`apiKey`、`apikey`、`x_api_key` 全部被脱敏；unit 测试 `test_redact_report_value_catches_api_key_spellings` 通过。
- t029_code_f007（minor，Round 3 新发现）——**已消除**。以当前代码独立核实（不采信 note.md 处置表自述）：`tests/fixtures/automation_probe/harness.py:410-418` 的 `_SECRET_KEY_TOKENS` 已含 `credential`；`harness.py:427-447` 的 `_is_secret_key` 已同时做到两点——尾随 `key` 规则一般化为前一 token ∈ {api, private}（`:444` 的 `norm[-2] in ("api", "private") and norm[-1] == "key"`），集合 token 做单复数归一（`:443` 的去尾 `s` 归一）。reviewer 以门禁 venv 独立运行 `build_report` 复现：`private_key`、`cookies`、`api_keys`、`tokens`、`secrets`、`passwords`、`credentials` 全部输出 `<redacted>`，同时 `key`（事件字段）、`monkey`、`cookieEnabled` 原值保留；新增 unit 测试 `tests/unit/test_automation_probe_harness.py:126-154`（`test_redact_report_value_catches_private_key_and_plural_forms`）逐项断言上述 7 个脱敏键与 3 个保留键，在位且通过。unit 单文件本轮重跑结果：10 passed（Round 3 的 9 个 + 本测试）。
- t029_code_f008（minor，Round 3 新发现）——**已消除**。`tests/fixtures/automation_probe/run_levels.py:350` 缩放循环已改为 `("ctrl+plus", "ctrl+equal")`，两种 keysym 各发送一次，采样次数不变（仍为 `range(2)` 的两个 zoom 样本）；`docs/specs/automation_compatibility.md:61` 的「Ctrl+plus / Ctrl+equal 两种 keysym」表述与交付代码现一致，第二种 keysym 不再是无代码证据的表述。zoom `verdict` 逻辑（DPR≠1 记 `measured`、否则 `inconclusive_shortcut_ineffective`）未被改动。

### Findings（本轮新发现）

无。本轮两处小修的扫描见结论段，未命中可进表的问题。

## 结论

- 前轮 finding 复核：f001/f002/f003 三条 important 与 f004/f005/f006 三条 minor 仍保持消除；Round 3 的 f007、f008 两条 minor 均以当前代码与独立运行核实为**已消除**（证据见上逐条说明，未采信 note.md 处置表自述）。
- 本轮新发现：0 条（critical 0、important 0、minor 0）
- 本轮小修扫描：
  - 脱敏归一：除规定键形外另抽查 `private_keys`、`apikeys` 均被脱敏，`cookiesEnabled`、`status`、`tokenCount` 均保留，未见去尾 `s` 归一引入的新误伤；单 token `keys` 归一后为 `key`，不在敏感集合内，仍保留，与事件字段定位一致。
  - 缩放 keysym：每样本现依次发送两种 keysym 而非同一 keysym 两次；`verdict` 为 DPR≠1 的二值判定，不记录步数，故即使两种 keysym 在 t032 环境均生效也不会改变 verdict 语义；等待、断言与样本数均未变，无回归。
  - 本轮 reviewer 未改代码、测试、task.md、note.md，未 commit、未 push；按任务约束仅重跑 unit 单文件，未跑浏览器类集成测试。
- 未进表的提示：
  - 文件行数（测试侧文件，按标准仅提示不进表）：`tests/fixtures/automation_probe/harness.py` 953 行、`tests/integration/test_automation_probe_chain.py` 989 行，仍超测试源码 600 行 minor 提示线、未达 1200 行 important 线。
  - 复杂度提示：`tests/fixtures/automation_probe/probe_client.py` 的 `run_dialog` 圈复杂度约 12（前几轮已提示，本轮未恶化），不进表。
  - 范围外观察（不进表，非本轮小修引入、非 f007 规定范围）：`_is_secret_key` 对首词敏感词 + 尾随 `key` 的键形（如 `secret_key`、`password_key`）仍返回 False——这是 Round 3 之前就存在的规则形态（首词规则只看非首 token、尾随规则仅限 api/private 前缀），本轮小修未引入、亦未扩大；如需硬化可另议，不影响本轮 f007 消除结论与 verdict。
  - 安全/契约/性能/健壮性视角已扫本轮 diff：探针监听仍均为 loopback、无裸 CDP TCP 暴露、无硬编码凭证、XTEST 命令无 shell 拼接；除上述范围外观察外未命中新问题。
- AC 复验方式：
  - AC-001：trust_prior——静态核对 matrix 双模式代码与断言；真实浏览器实跑依赖实施侧门禁记录，本轮按任务约束未重跑全链。
  - AC-002：trust_prior——其机制部分经 reviewer 独立复验（分类/state_changing 的独立运行、kill 用例代码逐行核实，见 f001/f003 复核）；浏览器存活的实跑结论依赖实施侧集成门禁记录。
  - AC-003：trust_prior——静态核对授权拒绝/跨 Profile/外部 Browser.close 用例与真实组件构成；实跑依赖实施侧记录。
  - AC-004：re_verified（判定规则部分）——本轮以门禁 venv 独立重跑 unit 单文件 10 passed，其中 compare/summarize 阈值用例通过；每级 5 个独立进程的采样实跑本身为 trust_prior，依赖实施侧 levels 报告。
  - AC-005：trust_prior——缩放 keysym 的代码与 spec 表述一致性经本轮独立核对（见 f008 复核）；CDP/XTEST 实测数值依赖实施侧报告。
  - AC-006：trust_prior——静态核对 dialog 四场景在两套测试中的存在及具体结论断言；实跑结论依赖实施侧报告。
  - AC-007：trust_prior（本轮抽查范围）——抽查 levels 报告的 v1 schema 断言与 zoom 表述一致性在位；完整的 spec/blueprint 交叉核对沿用 Round 3 结论，本轮未全量重读。
  - coverage = 1/7
  - 建议合并前人工抽查 trust_prior 项（占比 6/7 > 30%）：重点抽查 AC-001/AC-002 的全链实跑报告与 AC-004 的 levels.json 原始样本。
- 总体判断：Round 3 的两条 minor 已独立核实消除，Round 1/2 全部 finding 保持消除，本轮无新发现，无未解决 critical / important，判定 PASS。
- 系统性 follow-up：无

verdict: PASS

## Round 5 (2026-11-04T16:31:11+08:00)

- task：`t029_automation_compatibility_probe_harness`
- diff_anchor：`2c4d78ac8df3aaa001d489b575169a0b95422dbd`
- target：相对 diff_anchor 的 worktree 完整变化（代码侧复核）
- round：5
- reviewed_at：2026-11-04T16:31:11+08:00

reviewed_scope: 31ba2e506352e52e

### 本轮焦点复核：测试侧 t029_test_f011 的代码侧修复

- t029_test_f011（minor，Round 4 测试侧新发现：zoom 条目未记录实际尝试的 keysym）——**代码侧已消除**。以当前代码核实（不采信处置表）：
  - `tests/fixtures/automation_probe/run_levels.py:350` 定义具名元组 `zoom_keysyms = ("ctrl+plus", "ctrl+equal")`；`:351-352` 循环 `for keys in zoom_keysyms: await asyncio.to_thread(xtest.key, keys)`，两种 keysym 各发送一次，采样次数不变（外层仍为 `range(2)` 的两个 zoom 样本）。
  - 同一样本的 zoom 条目 `tests/fixtures/automation_probe/run_levels.py:363` 写 `"keysym_attempted": list(zoom_keysyms)`，与发送循环共用同一变量、同一定义点：元组不可变且发送与记录之间无对该变量的再赋值，故记录值不可能与发送值分叉；`list(...)` 转换保持原顺序，值为 `["ctrl+plus", "ctrl+equal"]`，与消费侧 `tests/e2e/test_automation_compatibility_probe_e2e.py:103` 的精确断言逐字一致。
  - 发送路径无静默放行：`XTestInput.key`（`tests/fixtures/automation_probe/harness.py:539-540`）原样透传为 `key <keysym>` 的 xte 命令，`_send`（同文件 `:518-529`）在 xte 返回非零时抛错；任一 keysym 失败时条目根本不会被 append，报告中已记录的条目不可能声称尝试过未实际发送的 keysym。
  - 脱敏不破坏该字段：reviewer 以门禁 venv 独立运行 `build_report` 复现，含 `keysym_attempted: ["ctrl+plus", "ctrl+equal"]` 的 zoom 条目经 `redact_report_value` 后原值保留（该键的 token 化结果不在敏感集合内，字符串本身亦无 Bearer/凭证/本地路径模式）；zoom 条目经 `run_levels.py:419` 的 `build_report` 输出，字段可到达最终报告。
  - 因此 f011 指出的回归盲区已闭合：若后续有人把元组改回 `("ctrl+plus", "ctrl+plus")`，`keysym_attempted` 与消费侧精确断言会同步失配而被发现，不再出现 DPR 恒为 1、verdict 仍为 `inconclusive_shortcut_ineffective` 却全绿的情形。

### 前轮 finding 复核

- t029_code_f001（important）——**仍保持消除**。`tests/fixtures/automation_probe/harness.py:362-374` 的 `_INJECTION_METHODS`/`_ATTACH_METHODS` 与 `script_injection`/`target_attach` 分类在位；`harness.py:734` 起的 `state_changing_methods()` 收录集仍含这两类；本轮独立运行复现：两方法分类正确。
- t029_code_f002（important）——**仍保持消除**。`tests/fixtures/automation_probe/run_levels.py:419` 仍走 `build_report(levels=..., summary=..., input_comparison=...)`；`tests/e2e/test_automation_compatibility_probe_e2e.py:90` 对 levels 报告断言 `schema == "automation-probe-report/v1"` 在位。
- t029_code_f003（important）——**仍保持消除**。`tests/integration/test_automation_probe_chain.py:838` 的 `test_probe_chain_client_killed_mid_connection_survival` 在位，`:909` 的 `proc.kill()`（SIGKILL）后断言浏览器存活与用户页面可 evaluate 的代码未被改动削弱。
- t029_code_f004（minor）——**仍保持消除**。本轮独立运行 `build_report` 复现：`cookieEnabled=True`、`tokenCount=3` 原值保留，`session_cookie`/`authToken`/`access_token` 仍被脱敏；unit 回归测试通过（见下文 10 passed）。
- t029_code_f005（minor）——**仍保持消除**。全仓 grep `READ_FRAME_EVENTS_SCRIPT` 与 `XTestInput.double_click` 仍零残留；`READ_EVENTS_SCRIPT` 仍被 `run_levels.py` 多处正式使用。
- t029_code_f006（minor）——**仍保持消除**。unit 测试 `test_redact_report_value_catches_api_key_spellings` 在位且通过。
- t029_code_f007（minor）——**仍保持消除**。`tests/fixtures/automation_probe/harness.py:410-418` 的敏感 token 集合与 `:427-447` 的单复数归一及 api/private 尾随 `key` 规则在位；unit 测试 `tests/unit/test_automation_probe_harness.py:126-154`（`test_redact_report_value_catches_private_key_and_plural_forms`）在位且通过。
- t029_code_f008（minor）——**仍保持消除**。缩放循环现为具名元组两种 keysym（见本轮焦点复核），与 `docs/specs/automation_compatibility.md:61` 的「Ctrl+plus / Ctrl+equal 两种 keysym」表述一致；zoom `verdict` 逻辑未被改动。

### Findings（本轮新发现）

无。本轮小修（具名元组 + `keysym_attempted` 字段）的扫描见结论段，未命中可进表的问题。

## 结论

- 前轮 finding 复核：f001/f002/f003 三条 important 与 f004/f005/f006/f007/f008 五条 minor 均以当前代码与独立运行核实为**仍保持消除**；Round 4 测试侧 f011 的代码侧修复经独立核实为**已消除**（证据见本轮焦点复核，未采信 note.md 处置表自述）。
- 本轮新发现：0 条（critical 0、important 0、minor 0）
- 本轮小修扫描：
  - 单一事实来源：发送与记录共用 `zoom_keysyms` 一个变量，元组不可变、无中间再赋值，记录值与发送值不可能分叉；顺序与消费侧精确断言逐字一致。
  - 无回归：zoom 样本数仍为 2，verdict 取值集、双路 `client_error` 结构、等待与断言均未变；脱敏复现证明新字段完整到达报告；xte 失败抛错而非静默记录。
  - 风格观察（不进表）：循环变量名为复数 `keys` 而实际每次取单个 keysym 字符串，仅命名欠精确，无行为影响。
  - 本轮 reviewer 未改代码、测试、task.md、note.md，未 commit、未 push；按任务约束仅重跑 unit 单文件，未跑浏览器类集成测试，未使用 live 浏览器。
- 未进表的提示：
  - 文件行数（测试侧文件，按标准仅提示不进表）：`tests/fixtures/automation_probe/harness.py` 953 行、`tests/integration/test_automation_probe_chain.py` 989 行，仍超测试源码 600 行 minor 提示线、未达 1200 行 important 线。
  - 复杂度提示：`tests/fixtures/automation_probe/probe_client.py` 的 `run_dialog` 圈复杂度约 12（前几轮已提示，本轮未恶化），不进表。
  - 安全/契约/性能/健壮性视角已扫本轮小修：探针监听仍均为 loopback、无裸 CDP TCP 暴露、无硬编码凭证、XTEST 命令无 shell 拼接；除上述风格观察外未命中新问题。
- AC 复验方式：
  - AC-001：trust_prior——静态核对 matrix 双模式代码与断言；真实浏览器实跑依赖实施侧门禁记录，本轮按任务约束未重跑全链。
  - AC-002：trust_prior——其机制部分经 reviewer 独立复验（分类/state_changing 的独立运行、kill 用例代码逐行核实，见 f001/f003 复核）；浏览器存活的实跑结论依赖实施侧集成门禁记录。
  - AC-003：trust_prior——静态核对授权拒绝/跨 Profile/外部 Browser.close 用例与真实组件构成；实跑依赖实施侧记录。
  - AC-004：re_verified（判定规则部分）——本轮以门禁 venv 独立重跑 unit 单文件 10 passed，其中 compare/summarize 阈值用例通过；每级 5 个独立进程的采样实跑本身为 trust_prior，依赖实施侧 levels 报告。
  - AC-005：trust_prior——缩放 keysym 的发送与记录一致性经本轮独立核对（见本轮焦点复核，含脱敏后字段保留复现）；CDP/XTEST 实测数值依赖实施侧报告。
  - AC-006：trust_prior——静态核对 dialog 四场景在两套测试中的存在及具体结论断言；实跑结论依赖实施侧报告。
  - AC-007：trust_prior（本轮抽查范围）——抽查 levels 报告的 v1 schema 断言与 zoom 字段契约在位；完整的 spec/blueprint 交叉核对沿用 Round 3 结论，本轮未全量重读。
  - coverage = 1/7
  - 建议合并前人工抽查 trust_prior 项（占比 6/7 > 30%）：重点抽查 AC-001/AC-002 的全链实跑报告与 AC-004 的 levels.json 原始样本。
- 总体判断：Round 4 测试侧 f011 的代码侧修复正确无害、单一事实来源使记录值与发送值不可能分叉，Round 1–4 全部 finding 保持消除，本轮无新发现，无未解决 critical / important，判定 PASS。
- 系统性 follow-up：无

verdict: PASS
