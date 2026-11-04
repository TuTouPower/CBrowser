# Task review t029（reviewer_focus: 测试）

- task：`t029_automation_compatibility_probe_harness`
- spec：`docs/tasks/t029_automation_compatibility_probe_harness/task.md`
- diff_anchor：`2c4d78ac8df3aaa001d489b575169a0b95422dbd`
- target：仓库根目录下 `git diff 2c4d78ac8df3aaa001d489b575169a0b95422dbd`
- round：1
- reviewed_at：2026-11-04T13:55:43+08:00

reviewed_scope: f85549915946777f

## Findings

### t029_test_f001 - Dialog「遗留/新连接」与 beforeunload 场景只采集不断言（两引擎同）

- 严重度：important
- 锚点：AC-006 —— 遗留 Dialog 后新连接能否得知并应答、相关命令是否阻塞、beforeunload 是否需要真实用户激活，这三问的答案没有任何断言锁定
- 位置：`tests/integration/test_automation_probe_chain.py:597-626`、`tests/integration/test_automation_probe_chain.py:710-732`
- 问题：`handle_new` 场景只断言 `rc == 0` 与 `new_session is not None`，beforeunload 两种激活方式也只断言 `rc == 0` 与 payload 非空，随后仅把 payload 存进 evidence 写报告。probe_client 明明产出了可断言的字段（`probe_client.py` handle_new 分支的 `opening_replayed` / `commands_blocked` / `handle_error` / `last_dialog`，beforeunload 分支的 `opening` / `handled` / `navigate_completed` / `final_url`），集成测试全部未用。失败场景：若新连接开始重放 opening、或遗留 Dialog 把新会话命令堵死、或脚本武装的 beforeunload 也触发拦截（与 spec 结论完全相反），两条 Dialog 测试仍全绿，AC-006 的核心结论靠 implementer 事后肉眼读报告成立，不受测试保护。reviewer 抽查了实施侧报告产物（gate scratch 的 chain-dialog.json / dialog-target.json），当前值确实为 `opening_replayed=false`、`commands_blocked=false`、`last_dialog.result=false`、input 激活有 opening 且导航完成——即行为目前正确，缺的是断言，不是结论本身。
- 建议：在两条 Dialog 测试中对 `handle_new` 断言 `opening_replayed is False`、`commands_blocked is False`、`last_dialog == {"type": "confirm", "result": False}`（或等价字段级断言）；对 beforeunload 断言 input 激活时 `opening` 非空且 `handled is True`、`navigate_completed is True`，script 激活时 `opening is None` 且 `navigate_completed is True`。

### t029_test_f002 - AC-006 的 alert 类型从未被任何测试执行

- 严重度：important
- 锚点：AC-006 —— 明列覆盖 alert/confirm/prompt/beforeunload
- 位置：`tests/integration/test_automation_probe_chain.py:580-598`、`tests/integration/test_automation_probe_chain.py:694-711`
- 问题：全仓搜索 `--dialog-type` 的调用点只有两处集合：pending 用 `prompt`，leave 与 handle_new 用 `confirm`；`alert` 只出现在 probe_client 的按钮映射（`tests/fixtures/automation_probe/probe_client.py:287`）与观测页按钮定义里，没有任何调用方传过 `--dialog-type alert`。即 alert 的「触发命令 pending 时能否应答」在普通 Chromium 全链与目标引擎直连两轮中都零执行，AC-006 三类 Dialog 中一类完全无测试，而 task.md 已将其打勾。
- 建议：两条 Dialog 测试的 pending 场景各增加一轮 `--dialog-type alert`（或把 pending 参数化为 alert/confirm/prompt 三轮），断言 opening 非空、`handled_while_pending is True`、`evaluate_completed is True`。

### t029_test_f003 - state_changing_methods 漏掉 addScript 与 setAutoAttach，报告清单与 spec 声称不符且无测试覆盖

- 严重度：important
- 锚点：AC-002 —— 须「列出 attach 发出的改变共享浏览器状态的 CDP 命令」
- 位置：`tests/fixtures/automation_probe/harness.py:365-381`、`tests/fixtures/automation_probe/harness.py:699-715`；缺测点：`tests/unit/test_automation_probe_harness.py:53-67`
- 问题：`classify_cdp_method` 对 `Page.addScriptToEvaluateOnNewDocument` 与 `Target.setAutoAttach` 落入兜底 `other`，而 `state_changing_methods()` 只收录 closes/download/emulation/domain_enable/navigation 五类，于是这两个 spec 明文点名的状态改变命令永远进不了报告的 `state_changing_methods`。reviewer 已独立复现：用 venv 直接调用，`classify_cdp_method('Page.addScriptToEvaluateOnNewDocument') == 'other'`、`classify_cdp_method('Target.setAutoAttach') == 'other'`，构造含三条命令的 bridge log 后 `state_changing_methods()` 只返回 `Page.navigate`；抽查实施侧 chain-target.json 的 `state_changing_methods` 实际产物同样不含这两项。但 spec `docs/specs/automation_compatibility.md:25` 声称这两项已被桥接记录且「完整清单以报告中的 state_changing_methods 为准」，与产物矛盾。unit 测试只断言了 MUST_MEDIATE_METHODS 含 addScript（静态清单正确），对 `classify_cdp_method` 的这两个方法与 `state_changing_methods()` 本身零测试，故缺口未被任何测试发现。
- 建议：给 addScript 增加注入类分类（如 `script_injection`）并纳入 `state_changing_methods` 收录集，setAutoAttach 同理评估归类；unit 补 `classify_cdp_method` 对这两项的断言与一个 `state_changing_methods()` 的 log 过滤用例。

### t029_test_f004 - 下载模式判别只断言 no_defaults=True 一侧，False 侧靠条件断言放行

- 严重度：important
- 锚点：AC-002 —— 「两种 no_defaults 模式下分别记录连接期间与断开后的下载是否进入 Artifact 捕获」，两模式的判别性结论（False 时客户端有 download 事件且 Agent 未捕获）未被断言
- 位置：`tests/integration/test_automation_probe_chain.py:309-311`、`tests/integration/test_automation_probe_chain.py:367-377`（循环体内仅 True 分支有 captured 断言）
- 问题：`_assert_matrix_output` 用条件断言：`download["event"] in {"download", "timeout"}` 后仅 `if download["event"] == "download"` 才断言文件名；目标引擎矩阵循环中只对 `no_defaults=True` 断言 Agent 捕获非空，对 False 一侧既不断言客户端事件必须为 `download`，也不断言 `agent_capture_during_connection == []`。失败场景：False 模式下 Playwright 下载事件超时且 Agent 也未捕获（双漏），或 False 模式下 Agent 意外捕获（覆盖结论反转），测试仍全绿。reviewer 抽查实施侧 chain-target.json：False 侧实际为 event=download、path_available=true、agent_capture=[]，True 侧为 timeout + 已捕获——当前行为与 spec 一致，缺的是 False 侧断言锁定。
- 建议：矩阵循环按模式分断言：False 时断言 `payload["download"]["event"] == "download"` 且 `captured == []`；True 时保留现有 Agent 捕获断言，并可断言客户端事件为 timeout（当前实现语义）。

### t029_test_f005 - 交付的 L0–L6/输入采样驱动未覆盖 AC-005 多个维度，t032 入口只验样本数不验判定

- 严重度：important
- 锚点：AC-005 —— 比较须覆盖 DPR/缩放、装饰/内容区偏移、滚动、iframe、复杂交互与焦点争用，并记录坐标误差；AC-007 要求全部探针在云端验证参数与报告格式供 t032 复核
- 位置：`tests/fixtures/automation_probe/run_levels.py:166-261`（L6 全段）、`tests/e2e/test_automation_compatibility_probe_e2e.py:83-93`
- 问题：交付的 run_levels.py 中 L6 只有 CDP/XTEST 两轮点击/文本/滚动采样：没有 DPR/缩放子场景（无任何缩放操作或 DPR 变化断言）、没有焦点争用子场景（无「另一客户端保持连接期间用 XTEST 点击」的编排）、XTEST 侧没有 iframe 子场景；且 CDP 侧不计算坐标误差——`input_details["cdp"]` 只存原始 click 事件，不存目标坐标/期望点（XTEST 侧有 `client_error` 与 mapping），报告读者无法从 levels.json 复算 spec 声称的「CDP 误差 0」。e2e 复核入口对 levels 报告只断言每级样本数 ≥5 与 `input_comparison` 键集为 {cdp, xtest}，不验 summary verdict、不验坐标误差与滚动量。结果是 spec 中缩放（INCONCLUSIVE）、焦点争用（2/2）、CDP 误差 0 等结论只能来自仓外一次性实验脚本，交付探针本身无法在 t032 复现这些维度，与「同一探针供 t032 复核」的交付定义有缺口。
- 建议：把缩放尝试、焦点争用、XTEST iframe 三个子场景补进 run_levels.py（缩放可明确产出 INCONCLUSIVE 字段），CDP 侧补记目标点与 `client_error`；e2e 复核增加对 summary verdict 与 CDP/XTEST 坐标误差字段存在性的断言（判定本身仍归 t032）。

### t029_test_f006 - 测试文件使用 # type: ignore 静默类型错误（危险模式）

- 严重度：important
- 锚点：危险模式扫描「静默错误：test 文件加 # type: ignore」——命中最低 important，不得降 minor
- 位置：`tests/unit/test_automation_probe_harness.py:102`、`tests/fixtures/automation_probe/harness.py:735`、`tests/fixtures/automation_probe/harness.py:743`
- 问题：unit 测试在断言行尾用 `# type: ignore[index]` 绕过类型检查，harness 的 HostBrowserRunner 两处覆写用 `# type: ignore[override]`。三处均无理由注释说明为何不能以正当类型写法消除。虽未弱化任何运行时断言，但按本轮审查规则属命中即 important 的危险模式，不能无说明放行。
- 建议：unit 处把 `sent` 改为带类型的 dict（如 `dict[str, Any]`）后删除 ignore；harness 两处若确因生产基类签名约束无法消除，改为与基类一致的签名或在行尾补明理由并收敛到一处说明，否则删除 ignore。

### t029_test_f007 - AC-002「超时后存活」无对应场景

- 严重度：minor
- 锚点：AC-002 —— 子进程「正常退出、异常或超时后」页面与浏览器仍存活
- 位置：`tests/integration/test_automation_probe_chain.py:364`（matrix 仅 `--disconnect exit`）、`tests/fixtures/automation_probe/probe_client.py:497`（disconnect 选项含 close/stop 但无调用方使用超时杀进程路径）
- 问题：正常退出由 matrix exit 覆盖，异常退出由 Dialog leave 的 `os._exit(3)` 侧面覆盖；但「客户端被超时杀死（如 _run_client timeout 杀进程）后浏览器存活」没有任何场景：hold 模式本可被超时终止验证，却只在 run_levels 中走 release 正常路径。
- 建议：补一个场景：启动 hold 客户端后由测试侧超时 kill，断言 chrome pid 存活且用户页面可 evaluate；或在 spec/note 中明确超时由 _exit(3) 异常退出等价覆盖的理由。

### t029_test_f008 - AC-003「无裸 CDP TCP 暴露」无断言，授权拒绝断言只排除 accepted 一种形态

- 严重度：minor
- 锚点：AC-003 —— 无裸 CDP TCP 暴露；授权失败/跨 Profile 拒绝
- 位置：`tests/integration/test_automation_probe_chain.py:272-291`、`tests/integration/test_automation_probe_chain.py:398-403`
- 问题：`_ws_rejection` 把任何非 `accepted` 的结果（握手异常、任意 close code、甚至链路故障）都算拒绝，断言仅为三项 `!= "accepted"`，不区分 4401/1011 等预期拒绝形态与无关故障；同时「无裸 CDP TCP 暴露」在全链测试中没有任何断言（如尝试绕过 API 端口直连浏览器 DevTools 端口应不可达/未监听于非 loopback）。
- 建议：拒绝断言收紧到预期形态集合（close:4401 / close:1011 / handshake 拒绝类），并补一条对浏览器 CDP 端口的非授权直连不可达断言（或在 spec 中注明该项由既有隧道测试覆盖的出处）。

## 结论

- 改测方向复核：无。本 task 为新增测试与探针，无对既有测试的就地改预期；diff 中既有测试文件零修改。
- 危险模式扫描：恒真断言、删/反转 expect、注释掉断言、弱化断言（`pages_after_popup_close >= 1` 为语义正当的下界，不计）、`.only` 均未命中；`pytest.skip` 均为引擎/Xvfb 前提缺失守卫、e2e 的 `skipif` 为 t032 门控（上下文区「有意不测」与测试策略已声明，合法，不出 finding）；XTestInput 的 fake_runner 是对子进程系统边界的注入且断言真实命令串，属合法边界 mock，不计 mock 误用；`# type: ignore` 命中 3 处，已列 f006。
- 本轮新发现：8 条（important 6、minor 2、critical 0）
- 未进表的提示：AC-004 的判定逻辑本身（compare/summarize 阈值）有真实 unit 覆盖且 reviewer 已独立重跑 unit 全绿，采样结论的可信度问题集中在 f005 的驱动覆盖面，不另出 finding；实施侧首轮 levels.json 曾把 client_exit_code 混入样本的旧产物仍留在仓外 scratch，仓内代码已剔除（run_levels.py hold_sample 注释与实现一致），不计 finding。
- 总体判断：Dialog 关键场景断言缺失（f001）、alert 零执行（f002）、状态改变命令清单漏项与 spec 声称矛盾（f003）、下载 False 侧不断言（f004）、AC-005 交付驱动覆盖缺口（f005）与 type:ignore 危险模式（f006）均为未解决 important，FAIL。
- 系统性 follow-up：无（上述均为本 task 内可修项，不另立 follow-up）。

## AC 复验方式

- AC-001：re_verified —— 逐行核对 `_assert_matrix_output` 与目标引擎/普通 Chromium 两条全链测试的断言，并抽查实施侧 reports-gate 的 chain-target.json / chain-chromium.json 产物（两模式 matrix、popup/frame/download/版本字段齐全且与 spec 一致）。
- AC-002：re_verified —— 核对 matrix 循环、断开后 rearm 捕获断言与 Browser.close 未发送断言，抽查 chain-target.json 两模式下载归属；同时复现了 f003 的分类漏项并发现 f004/f007 的断言缺口。
- AC-003：re_verified —— 核对未授权三拒绝、外部 Browser.close 停 Profile 测试（pid 死亡 + stopped 状态落盘断言齐全）与全链组件构成；TCP 暴露与拒绝形态的断言弱点见 f008。
- AC-004：trust_prior —— 判定规则（compare_level_samples / summarize_levels）有真实 unit 测试且 reviewer 已独立重跑 `tests/unit/test_automation_probe_harness.py` 6/6 通过；但每级 5 样本的实跑结论依赖实施侧采样产物（仓外 reports2/levels.json：L1–L6 均为 no_change、每级 5 样本，reviewer 已抽查该文件），集成/e2e 层无对 verdict 的断言，未独立复验实跑本身。
- AC-005：trust_prior —— CDP/XTEST 数值结论依赖实施侧 levels.json 抽查（XTEST client_error 5/5 为 [10, -10.88]、scroll 120/600 交替、CDP scroll 300/text 正确，reviewer 已抽查）；交付驱动的维度缺口见 f005，缩放子项按 spec 自述为 INCONCLUSIVE。
- AC-006：re_verified —— 核对两条 Dialog 测试断言与 probe_client 场景实现，并抽查 chain-dialog.json / dialog-target.json 产物（pending 应答、遗留消解、beforeunload 激活差异的实际值与 spec 一致）；断言缺口与 alert 缺失见 f001/f002。
- AC-007：re_verified —— 通读交付的 docs/specs/automation_compatibility.md 与 blueprint 两处更新，证据分级、否决条件、t030 拦截清单、t031/t032 输入均在文内逐项给出，MUST_MEDIATE_METHODS 与文档清单一致；其中 state_changing_methods 的完整性问题见 f003。

coverage = 5 / 7

verdict: FAIL

## Round 2 (2026-11-04T14:21:46+08:00)

- task：`t029_automation_compatibility_probe_harness`
- diff_anchor：`2c4d78ac8df3aaa001d489b575169a0b95422dbd`
- round：2

reviewed_scope: 57d3ed7ec37c791e

### 前轮 finding 复核

- t029_test_f001（Dialog 遗留/新连接与 beforeunload 只采集不断言）——**已消除**。两条 Dialog 测试均已字段级断言：普通 Chromium 全链 `tests/integration/test_automation_probe_chain.py:646` 起断言 `opening_replayed is False`、`commands_blocked is False`、`page_enable_error is None`、`last_dialog == {"type": "confirm", "result": False}`，目标引擎直连 `:790` 起同款断言；beforeunload 两轮在两条测试中均断言 input 激活时 `opening` 非空且 type 为 beforeunload、`handled is True`、`navigate_completed is True`、`final_url` 以 `/other` 结尾，script 激活时 `opening is None` 且导航完成。reviewer 抽查 `~/gate_scratch_t029/reports/chain-dialog.json`：`after_vanished_session` 实测值（opening_replayed=false、commands_blocked=false、last_dialog.result=false）与两类 beforeunload 值与断言一致。
- t029_test_f002（alert 从未执行）——**已消除**。两条 Dialog 测试各新增一轮 pending + `--dialog-type alert`（`tests/integration/test_automation_probe_chain.py:621`、`:768`），断言 `opening` 非空且 `opening["type"] == "alert"`、`handled_while_pending is True`、`evaluate_completed is True`；抽查 chain-dialog.json 含 `pending_alert` 且 handled/evaluate 均为 true。
- t029_test_f003（addScript/setAutoAttach 漏分类、报告清单与 spec 矛盾、无测试）——**已消除**。`tests/fixtures/automation_probe/harness.py:366-375` 新增 `script_injection` / `target_attach` 分类，`state_changing_methods()`（`:727-737`）收录两类；unit 新增 `test_classify_cdp_method_categories` 与 `test_state_changing_methods_include_injection_and_attach`（`tests/unit/test_automation_probe_harness.py:53-84`），reviewer 独立重跑 unit 8/8 通过；抽查 `~/gate_scratch_t029/reports/chain-target.json` 的 `state_changing_methods` 实际产物已含 `Page.addScriptToEvaluateOnNewDocument`（script_injection）与 `Target.setAutoAttach`（target_attach），与 spec `docs/specs/automation_compatibility.md:25` 声称一致。
- t029_test_f004（下载 False 侧不断言）——**已消除**。目标引擎矩阵循环 False 分支新增断言 `payload["download"]["event"] == "download"` 且 `captured == []`（`tests/integration/test_automation_probe_chain.py:382-383`），True 分支保留 Agent 捕获非空断言；抽查 chain-target.json：False 侧 event=download、agent_capture=[]，True 侧 event=timeout、agent_capture 非空，与断言锁定一致。
- t029_test_f005（交付驱动缺 AC-005 多维度、CDP 无坐标误差、e2e 只验样本数）——**已消除（主体），残余见本轮 f009**。`tests/fixtures/automation_probe/run_levels.py` 已补：CDP 侧记录 `target_client` 与 `client_error`（`:180-199`）、XTEST 侧 iframe 子场景并计算 `frame_client_error`（帧内坐标空间换算，`:262-297`）、缩放子场景（ctrl+plus 两轮后以 DPR 重算映射采样，记录 `dpr_after_zoom_keys` / `zoom_effective` / 双路 click 误差，`:340-375`）、焦点争用子场景（L3 hold 客户端保持连接期间 XTEST 点击并记录 hasFocus，`:377-405`）。e2e 复核入口 `tests/e2e/test_automation_compatibility_probe_e2e.py:90-100` 已断言每级 summary verdict 属合法集合、comparison 键集含 {cdp, xtest, zoom, focus_contention}、cdp/xtest 每条 `client_error is not None`。抽查 `~/gate_scratch_t029/reports3/levels.json`：L0–L5 与 L6 两路每级 5 样本、summary 全级有 verdict，input_comparison 四键齐全（cdp 首条 client_error=[0, -0.88]、xtest 首条 [10, -10.88] 且含 frame_client_error、zoom 2 条、focus_contention 2 条）。
- t029_test_f006（# type: ignore 危险模式 3 处）——**已消除**。全量 grep t029 交付文件（unit/integration/e2e/fixtures）已无任何 `type: ignore`；unit 处 `sent` 已改带类型 dict（`tests/unit/test_automation_probe_harness.py:130`，另见本轮 f010 的小瑕疵），harness 的 HostBrowserRunner 覆写（`tests/fixtures/automation_probe/harness.py:762-803`）已改为与基类一致的签名、无 ignore。危险模式以换形式弱化复核：未发现新的 ignore / eslint-disable / skip 掩盖（integration 的 pytest.skip 仍仅为引擎/Xvfb 前提守卫、e2e skipif 仍为 t032 门控，均合法）。
- t029_test_f007（AC-002 超时后存活无场景）——**已消除**。新增 `test_probe_chain_client_killed_mid_connection_survival`（`tests/integration/test_automation_probe_chain.py:838`）：经全链启动 hold 客户端、等 ready 后 `proc.kill()` 强杀，断言浏览器 pid 存活且用户页面仍可 evaluate 出标题——覆盖「客户端被杀死（超时/中止路径）后浏览器与页面存活」。
- t029_test_f008（无裸 CDP 断言缺失、授权拒绝断言过宽）——**修不彻底（原 minor，残余仍 minor，不阻断）**。已改进部分：拒绝断言收紧为 `outcome == "close:4401" or outcome.startswith("handshake:")`（`tests/integration/test_automation_probe_chain.py:414-420`），其他 close code 与 recv 阶段 error/timeout 形态不再放行；新增对已用端点（browser WS、bridge、API）hostname 属 loopback 的断言（`:422-428`）。残余：`_ws_rejection` 的 handshake 分支只拼异常类名（`:280`），任意握手期异常（如链路故障的 ConnectionRefused）仍会以 `handshake:*` 通过，未区分预期的 HTTP 403 拒绝形态；loopback 断言只核对测试自身构造/已用端点的 hostname，未对浏览器 DevTools 端口做未授权直连不可达的实际尝试。建议后续把 handshake 形态收紧到 InvalidStatus/403 类，并补一条对 CDP 端口绕过隧道的直连拒绝断言。

## Findings

### t029_test_f009 - e2e 复核对 zoom/focus_contention 只验键存在，缩放无 INCONCLUSIVE 判定字段

- 严重度：minor
- 锚点：AC-005 / AC-007 —— t032 复核入口对子场景的验证深度（f005 残余）
- 位置：`tests/e2e/test_automation_compatibility_probe_e2e.py:96`、`tests/fixtures/automation_probe/run_levels.py:363`
- 问题：e2e 对 `zoom` / `focus_contention` 只断言键出现在 input_comparison 中，不断言条目非空或其 client_error 存在（cdp/xtest 已逐条断言）；若某轮采样这两组为空列表，e2e 仍绿。同时 run_levels 的缩放条目只记 `zoom_effective` 布尔值，未产出判定字段——reports3 实测两条 zoom 均为 `zoom_effective=false`（缩放未生效），报告读者须自行对照 spec 才知该维度结论为 INCONCLUSIVE，报告本身无显式标记。失败场景限于证据可读性与 t032 复核灵敏度，不影响已测结论本身，故 minor。
- 建议：e2e 对 zoom/focus_contention 增加非空与 client_error 存在性断言（与 cdp/xtest 同款）；run_levels 缩放条目补 `verdict` 字段（zoom 未生效时显式写 INCONCLUSIVE）。

### t029_test_f010 - unit 测试新增的 Any 类型标注未导入 Any

- 严重度：minor
- 锚点：行为缺陷（测试代码静态正确性）—— f006 修复引入的小瑕疵
- 位置：`tests/unit/test_automation_probe_harness.py:130`（文件头 `:3-8` 无 typing 导入）
- 问题：`sent: dict[str, Any] = {}` 使用了未导入的 `Any`。因文件启用 `from __future__ import annotations` 且为局部变量标注，运行时不求值，reviewer 重跑 unit 8/8 仍通过；但对该文件跑 mypy/pyright/ruff 的未定义名检查会报错，属 f006「以正当类型写法消除 ignore」未完全做干净。
- 建议：补 `from typing import Any` 一行。

## 结论

- 前轮 finding 复核：f001、f002、f003、f004、f006、f007 已消除；f005 主体已消除（残余 minor 见 f009）；f008 修不彻底、残余仍为 minor（拒绝 handshake 形态与裸 CDP 直连尝试）。前轮 6 条 important 已全部消除，无换形式弱化（逐项以 diff/代码/断言与 reports 产物核实，未采信 note.md 处置表）。
- 改测方向复核：无。本轮改测均为新增场景与断言加强（Dialog/alert/下载 False 侧/杀客户端/e2e verdict 与误差断言），以及按 spec 声称修复分类实现并新增 unit 断言；未发现把旧预期就地改成新实现输出的迁就式改测。
- 本轮新发现：2 条（minor 2、important 0、critical 0）
- 未进表的提示：无。危险模式复扫：恒真断言、删/反转 expect、注释断言、弱化断言、`.only`、mock 被测逻辑均未命中；unit 独立重跑命令为 `PYTHONPATH=src/backend ~/gate_scratch_t029/venv/bin/python -m pytest tests/unit/test_automation_probe_harness.py -q`，结果 8 passed。
- 总体判断：前轮 blocking 全部消除，本轮仅 minor（f008 残余、f009、f010），PASS。
- 系统性 follow-up：无。

## AC 复验方式

- AC-001：re_verified —— 复核两条全链矩阵测试断言未回退，并抽查 reports/chain-target.json 与 chain-chromium.json（两模式 matrix、popup/frame/download/版本字段齐全）。
- AC-002：re_verified —— 复核 False/True 两侧下载断言（f004）、新增杀客户端存活测试（f007）、state_changing 清单产物含 addScript/setAutoAttach（f003），且独立重跑 unit 8/8 通过。
- AC-003：re_verified —— 复核拒绝断言收紧与 loopback 断言的新代码、外部 Browser.close 停 Profile 测试未回退；拒绝形态与裸 CDP 直连的残余弱点见 f008 复核（minor）。
- AC-004：trust_prior —— 判定规则 unit 已独立重跑通过、reports3/levels.json 已抽查（每级 5 样本、summary verdict 齐全）；每级实跑采样本身依赖实施侧产物，本轮按约束未重跑浏览器类集成/采样。
- AC-005：trust_prior —— 交付驱动代码已逐段复核（CDP 误差、XTEST iframe、缩放、焦点争用均已入 run_levels），数值结论依赖 reports3/levels.json 抽查（cdp [0, -0.88]、xtest [10, -10.88]、zoom 2 条 zoom_effective=false、focus 2 条）；实跑未独立重演。
- AC-006：re_verified —— 复核两引擎 Dialog 测试的全部新断言（f001/f002），并抽查 reports/chain-dialog.json 与 dialog-target.json 的 pending_alert、after_vanished_session、beforeunload 两激活值与断言一致。
- AC-007：re_verified —— 复核 e2e t032 入口新增的 verdict/误差断言与 spec 文档的证据分级、拦截清单；报告格式与探针参数在云端已验，真实环境判定仍归 t032。

coverage = 5 / 7

verdict: PASS

## Round 3 (2026-11-04T14:25:18+08:00)

- task：`t029_automation_compatibility_probe_harness`
- diff_anchor：`2c4d78ac8df3aaa001d489b575169a0b95422dbd`
- round：3

reviewed_scope: 76ccd941159cb86e

### 前轮 finding 复核

- t029_test_f001（Dialog 遗留/新连接与 beforeunload 只采集不断言）——**已消除，保持**。本轮重读 `tests/integration/test_automation_probe_chain.py` 两条 Dialog 测试全文：handle_new 的 `opening_replayed is False`、`commands_blocked is False`、`page_enable_error is None`、`last_dialog == {"type": "confirm", "result": False}` 与 beforeunload 两激活方式的字段级断言均原样在位，未回退、未弱化。
- t029_test_f002（alert 从未执行）——**已消除，保持**。两条 Dialog 测试的 pending + `--dialog-type alert` 轮次与 `opening["type"] == "alert"`、`handled_while_pending is True`、`evaluate_completed is True` 断言仍在位。
- t029_test_f003（addScript/setAutoAttach 漏分类）——**已消除，保持**。unit `test_classify_cdp_method_categories` 与 `test_state_changing_methods_include_injection_and_attach`（`tests/unit/test_automation_probe_harness.py:54-87`）仍在位，本轮独立重跑 unit 9/9 通过（含这两条）。
- t029_test_f004（下载 False 侧不断言）——**已消除，保持**。目标引擎矩阵循环 False 分支的 `payload["download"]["event"] == "download"` 且 `captured == []` 断言、True 分支 Agent 捕获非空断言均在位（False 分支断言在 `tests/integration/test_automation_probe_chain.py:382-383`）。
- t029_test_f005（交付驱动缺 AC-005 多维度）——**已消除，保持**（残余 f009 本轮已闭环，见下）。run_levels 的 CDP `client_error`、XTEST iframe、缩放、焦点争用子场景代码逐段在位。
- t029_test_f006（# type: ignore 危险模式）——**已消除，保持**。本轮全量 grep t029 交付文件（unit/integration/e2e/fixtures）无任何 `type: ignore`（仓内其他文件的存量 ignore 不在本 task diff 内，不计）；harness 覆写签名未回退。
- t029_test_f007（AC-002 超时后存活无场景）——**已消除，保持**。`test_probe_chain_client_killed_mid_connection_survival` 仍在位：hold 客户端 ready 后 `proc.kill()`、断言浏览器 pid 存活且页面可 evaluate。
- t029_test_f008（授权拒绝断言过宽、无裸 CDP 断言缺失）——**本轮收紧部分已闭环；loopback 残余仍为 minor，不阻断**。拒绝断言已改为精确集合：`tests/integration/test_automation_probe_chain.py:418` 断言三项 outcome（no_token / wrong_token / cross_profile）均 `in {"close:4401", "handshake:InvalidStatus"}`，注释（`:411-416`）明示不接受 accepted/timeout/通用 error；`_ws_rejection`（`:278-292`）的形态拼法未变，但调用方已精确钉死——链路故障类异常（如 `handshake:ConnectionRefusedError`）与 `error:*`、`close:<其他码>` 现在都会使断言失败，Round 2 指出的「任意握手期异常放行」已消除。残余与 Round 2 相同：loopback 断言（`:421-428`）仍只核对已用端点（browser WS、bridge、API）的 hostname，未新增对浏览器 DevTools 端口绕过隧道的未授权直连不可达尝试；该残余维持 minor，不另立新 finding。
- t029_test_f009（e2e 对 zoom/focus 只验键存在、缩放无判定字段）——**已消除**。e2e `tests/e2e/test_automation_compatibility_probe_e2e.py:102-111` 新增逐条断言：zoom 每条 `verdict in {"measured", "inconclusive_shortcut_ineffective"}` 且 `xtest_click`/`cdp_click` 的 `client_error is not None`；focus_contention 每条 `has_focus_during_L3` 为 bool 且 `xtest_click["client_error"] is not None`。生产侧 `tests/fixtures/automation_probe/run_levels.py:361-368` 缩放条目已产出 `verdict` 字段，取值与 e2e 枚举逐字一致（DPR 未变 → `inconclusive_shortcut_ineffective`，与 spec 的 INCONCLUSIVE 结论对齐）；`has_focus_during_L3` 键名（`:400-403`）与 e2e 断言一致。非空性由构造保证：zoom 为 `range(2)` 无条件 append（`:341-384`）、focus 在 hold ready 断言后 append（`:386-405`），驱动失败会先触发 e2e 的子进程返回码断言，故逐条循环不存在静默空转放行路径。注：`~/gate_scratch_t029/reports3/levels.json` 为修复前旧产物（zoom 条目无 verdict 字段），属产物未重跑而非代码缺口；新报告由 t032 复核入口重跑驱动时生成。
- t029_test_f010（unit 的 Any 未导入）——**已消除**。`tests/unit/test_automation_probe_harness.py:7` 已补 `from typing import Any`，`sent: dict[str, Any]`（`:142`）标注完整；本轮独立重跑 unit 9/9 通过。

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核：f001–f007 已消除且保持；f009、f010 已消除；f008 的拒绝断言收紧已闭环，仅 loopback 直连尝试残余维持 minor。前轮全部 critical / important 仍保持消除，无换形式弱化（逐项以当前 diff、代码与断言核实，未采信 note.md 处置表）。
- 改测方向复核：无。本轮小修均为按 Round 2 建议加强断言（e2e zoom/focus 逐条断言、拒绝精确集合）、生产侧补 verdict 字段与静态类型补导入；未发现把旧预期就地改成新实现输出的迁就式改测，verdict 枚举由 spec 的 INCONCLUSIVE 结论定义、生产与消费两侧逐字对齐。
- 本轮新发现：0 条
- 未进表的提示：f008 的 loopback 残余已在上文复核中记录（原 finding 的未闭环部分，不重复立项）；危险模式复扫：恒真断言、删/反转 expect、注释断言、弱化断言、`.only`、新增 skip、mock 被测逻辑均未命中（e2e 的 `skipif` 仍为 t032 门控，合法）。unit 独立重跑命令为 `TMPDIR=~/gate_scratch_t029/tmp PYTHONPATH=src/backend ~/gate_scratch_t029/venv/bin/python -m pytest tests/unit/test_automation_probe_harness.py -q`，结果 9 passed；按本轮约束未跑浏览器类集成测试。
- 总体判断：Round 2 新发现 f009/f010 与 f008 收紧均已闭环，Round 1/2 全部 finding 无回退，仅存 f008 loopback minor 残余，PASS。
- 系统性 follow-up：无。

## AC 复验方式

- AC-001：re_verified —— 重读两条全链矩阵测试断言（contexts/popup/frame/download/text/isTrusted）未回退，与 Round 2 抽查的 reports 产物结论一致。
- AC-002：re_verified —— 复核下载两模式双向断言、杀客户端存活测试、Browser.close 未发送断言均在位；判定相关的 unit 测试本轮独立重跑 9/9 通过。
- AC-003：re_verified —— 复核拒绝断言精确集合（`:418`）与 loopback hostname 断言的代码本身、外部 Browser.close 停 Profile 测试未回退；裸 CDP 直连尝试的残余见 f008 复核（minor）。
- AC-004：trust_prior —— 判定规则（compare/summarize）unit 已独立重跑通过；每级 5 样本的实跑结论依赖实施侧采样产物（reports3/levels.json，本轮按约束未重跑浏览器采样），且该产物为本轮小修前生成，L0–L6 summary verdict 不受小修影响。
- AC-005：trust_prior —— 交付驱动与 e2e 消费侧的字段契约（zoom verdict 枚举、has_focus 键、双路 client_error）已逐项代码对齐复核；CDP/XTEST 数值结论依赖实施侧 levels 产物抽查，实跑未独立重演，缩放维度新 verdict 字段的实测值待 t032 重跑报告确认。
- AC-006：re_verified —— 重读两引擎 Dialog 测试全文，pending/alert/遗留/beforeunload 全部断言在位未弱化，与 Round 2 抽查的 dialog 报告产物一致。
- AC-007：re_verified —— 复核 e2e t032 入口新增的 zoom/focus 逐条断言与生产侧字段逐字对齐，spec 文档的证据分级与拦截清单未回退；真实环境判定仍归 t032。

coverage = 5 / 7

verdict: PASS

## Round 4 (2026-11-04T15:34:21+08:00)

- task：`t029_automation_compatibility_probe_harness`
- diff_anchor：`2c4d78ac8df3aaa001d489b575169a0b95422dbd`
- round：4
- 本轮焦点：核实 Round 3 代码侧两条新 minor（f007 脱敏残余、f008 缩放 keysym 表述）的测试侧闭环；复核 Round 1/2 全部 finding 无回退；扫描本轮两处小修是否引入新测试问题。

### 前轮 finding 复核

- t029_test_f001（Dialog 遗留/新连接与 beforeunload 只采集不断言）——**已消除，保持**。两条 Dialog 测试的 `opening_replayed is False` 断言仍在位（`tests/integration/test_automation_probe_chain.py:646`、`:790`），beforeunload 两激活方式的字段级断言未回退、未弱化。
- t029_test_f002（alert 从未执行）——**已消除，保持**。两条 Dialog 测试的 pending + `--dialog-type alert` 轮次仍在位（`tests/integration/test_automation_probe_chain.py:621`、`:768`），断言 `opening["type"] == "alert"`、`handled_while_pending is True`、`evaluate_completed is True` 未变。
- t029_test_f003（addScript/setAutoAttach 漏分类）——**已消除，保持**。unit `test_classify_cdp_method_categories` 与 `test_state_changing_methods_include_injection_and_attach`（`tests/unit/test_automation_probe_harness.py:54-87`）仍在位，本轮独立重跑 unit 全部通过（含这两条）。
- t029_test_f004（下载 False 侧不断言）——**已消除，保持**。目标引擎矩阵循环 False 分支的 `payload["download"]["event"] == "download"` 且 `captured == []` 断言（`tests/integration/test_automation_probe_chain.py:382-383`）仍在位，True 分支 Agent 捕获断言未变。
- t029_test_f005（交付驱动缺 AC-005 多维度）——**已消除，保持**（残余 f009 已于 Round 3 闭环）。run_levels 的 CDP `client_error`、XTEST iframe、缩放、焦点争用子场景代码逐段在位；e2e 的 verdict/误差断言未回退。
- t029_test_f006（# type: ignore 危险模式）——**已消除，保持**。本轮全量 grep t029 交付文件（unit/integration/e2e/fixtures）无任何 `type: ignore`。
- t029_test_f007（AC-002 超时后存活无场景）——**已消除，保持**。`test_probe_chain_client_killed_mid_connection_survival`（`tests/integration/test_automation_probe_chain.py:838`）仍在位，hold 客户端 ready 后 `proc.kill()`、断言浏览器 pid 存活且页面可 evaluate。
- t029_test_f008（授权拒绝断言过宽、无裸 CDP 断言缺失）——**保持 Round 3 状态：拒绝精确集合已闭环，loopback 直连尝试残余仍为 minor，不阻断**。拒绝断言仍为精确集合 `{"close:4401", "handshake:InvalidStatus"}`（`tests/integration/test_automation_probe_chain.py:418`），注释明示不接受 accepted/timeout/通用 error；loopback 断言（`:421-428`）仍只核对已用端点 hostname，未新增对浏览器 DevTools 端口绕过隧道的未授权直连尝试。该残余与 Round 2/3 相同，不重复立项。
- t029_test_f009（e2e 对 zoom/focus 只验键存在、缩放无判定字段）——**已消除，保持**。e2e `tests/e2e/test_automation_compatibility_probe_e2e.py:102-111` 的 zoom verdict 枚举与双路 `client_error is not None`、focus 布尔与 `client_error` 逐条断言仍在位；run_levels 缩放条目 `verdict` 字段仍在位。
- t029_test_f010（unit 的 Any 未导入）——**已消除，保持**。`tests/unit/test_automation_probe_harness.py:7` 的 `from typing import Any` 仍在位，`sent: dict[str, Any]` 标注完整。

### 本轮重点核实（Round 3 代码侧新 minor 的测试侧闭环）

- 代码侧 f007（private_key 与复数键形脱敏残余）——**测试侧已闭环**。新增 unit 测试 `test_redact_report_value_catches_private_key_and_plural_forms`（`tests/unit/test_automation_probe_harness.py:126-155`）逐项断言 `private_key`、`cookies`、`api_keys`、`tokens`、`secrets`、`passwords`、`credentials` 均被脱敏为 `<redacted>`，同时断言 `key`（事件字段）保留原值、`monkey` 保留、`cookieEnabled is True`。该测试走真实 `build_report` / 脱敏路径，未 mock 被测逻辑；断言为精确等值，非存在性或弱化断言。本轮以 gate venv、TMPDIR 置于 gate scratch tmp 重跑 unit 单文件 `tests/unit/test_automation_probe_harness.py`，结果 10 passed（Round 3 的 9 条 + 本条新测试），脱敏新测试有效通过，非恒真。
- 代码侧 f008（缩放只发 ctrl+plus 两次、spec 声称两种 keysym）——**实现与 spec/e2e 断言已对齐，无静默放行（残余见本轮 f011）**。run_levels 缩放循环已改为 `("ctrl+plus", "ctrl+equal")`（`tests/fixtures/automation_probe/run_levels.py:350`），每轮 2 个 zoom 样本各发送两种 keysym 后再测 DPR；spec `docs/specs/automation_compatibility.md:61` 的「Ctrl+plus / Ctrl+equal 两种 keysym」表述与代码一致。keysym 经 `XTestInput.key` 原样透传为 xte 命令（`tests/fixtures/automation_probe/harness.py:539-540`），两种字符串为不同命令；`_send` 在 xte 返回非零时抛错（同文件 `_send` 实现），无效 keysym 不会静默记为 INCONCLUSIVE 后仍绿——驱动失败会先使子进程返回码断言失败。e2e 的 zoom 断言（verdict 枚举 `{measured, inconclusive_shortcut_ineffective}`、双路 `client_error is not None`）与生产侧 verdict 取值逐字一致，未因 keysym 改动而放宽。

## Findings

### t029_test_f011 - zoom 报告条目未记录实际尝试的 keysym，keysym 覆盖回归时 e2e 无法察觉

- 严重度：minor
- 锚点：AC-005 / AC-007 —— t032 复核入口对缩放子场景的验证深度（代码侧 f008 的测试侧残余）
- 位置：`tests/fixtures/automation_probe/run_levels.py:361-375`（zoom 条目字段集）、`tests/e2e/test_automation_compatibility_probe_e2e.py:102-108`（zoom 断言）
- 问题：zoom 条目只记 `dpr_after_zoom_keys`、`zoom_effective`、`verdict` 与双路 click 误差，未记本次实际发送的 keysym 列表。当前代码确实发送两种 keysym（见上文核实），结论本身无误；但若后续有人把元组改回 `("ctrl+plus", "ctrl+plus")`（即代码侧 f008 的原状），DPR 仍恒为 1、verdict 仍为 `inconclusive_shortcut_ineffective`、双路 client_error 仍非空，e2e 仍全绿，spec「两种 keysym 已试」的表述会再次失去报告证据而不被任何测试发现。失败场景限于证据可追溯性与 t032 复核灵敏度，不改变缩放 INCONCLUSIVE 结论与 XTEST 采用判定，故 minor。
- 建议：zoom 条目补 `keysym_attempted` 字段（取值为本次发送的 keysym 列表），e2e 断言其等于 `["ctrl+plus", "ctrl+equal"]`（或至少含两种不同 keysym）；或在 spec 中把 keysym 覆盖的证据出处改为代码行而非报告字段。

## 结论

- 前轮 finding 复核：f001–f007、f009、f010 已消除且保持；f008 拒绝精确集合保持闭环，仅 loopback 直连尝试残余维持 minor。前轮全部 critical / important 仍保持消除，无换形式弱化（逐项以当前 diff、代码与断言核实，未采信 note.md 处置表）。
- 改测方向复核：无。本轮小修为新增 unit 脱敏断言（精确等值）与生产侧缩放 keysym 元组改动（采样次数不变、verdict 逻辑与 e2e 枚举均未动）；未发现把旧预期就地改成新实现输出的迁就式改测，未发现删/反转 expect。
- 本轮新发现：1 条（minor 1、important 0、critical 0），即 f011。
- 未进表的提示：f008 的 loopback 残余与 f011 均已在上文记录（f008 为原 finding 的未闭环部分，不重复立项）；危险模式复扫：恒真断言、删/反转 expect、注释断言、弱化断言、`.only`、新增 skip、mock 被测逻辑均未命中（integration 的 pytest.skip 仍仅为引擎/Xvfb 前提守卫、e2e 的 skipif 仍为 t032 门控，均合法）；unit 独立重跑命令为 gate venv 下 `TMPDIR` 置于 gate scratch tmp、`PYTHONPATH=src/backend` 重跑 `tests/unit/test_automation_probe_harness.py -q`，结果 10 passed；按本轮约束未跑浏览器类集成测试。
- 总体判断：Round 3 代码侧两条新 minor 的测试侧影响均已闭环（f007 有精确 unit 断言且 10/10 通过，f008 代码/spec/e2e 已对齐且 xte 失败不静默放行），Round 1/2 全部 finding 无回退，本轮仅新增 minor（f011），PASS。
- 系统性 follow-up：无。

## AC 复验方式

- AC-001：re_verified —— 重读两条全链矩阵测试断言未回退，与 Round 2/3 抽查的报告产物结论一致。
- AC-002：re_verified —— 复核下载两模式双向断言、杀客户端存活测试、Browser.close 未发送断言均在位；脱敏相关的 unit 测试本轮独立重跑 10/10 通过。
- AC-003：re_verified —— 复核拒绝断言精确集合与 loopback hostname 断言的代码本身、外部 Browser.close 停 Profile 测试未回退；裸 CDP 直连尝试的残余见 f008 复核（minor）。
- AC-004：trust_prior —— 判定规则（compare/summarize）unit 已独立重跑通过；每级 5 样本的实跑结论依赖实施侧采样产物，本轮按约束未重跑浏览器采样。
- AC-005：trust_prior —— 交付驱动与 e2e 消费侧的字段契约（zoom verdict 枚举、双路 client_error、两种 keysym 发送）已逐项代码对齐复核；CDP/XTEST 数值结论依赖实施侧 levels 产物抽查，实跑未独立重演，keysym 覆盖的报告可追溯性残余见 f011（minor）。
- AC-006：re_verified —— 重读两引擎 Dialog 测试全文，pending/alert/遗留/beforeunload 全部断言在位未弱化，与 Round 2 抽查的 dialog 报告产物一致。
- AC-007：re_verified —— 复核 e2e t032 入口的 zoom/focus 逐条断言与生产侧字段对齐，spec 文档的证据分级与拦截清单未回退；真实环境判定仍归 t032。

coverage = 5 / 7

reviewed_scope: 6a0d27b116cbdfcb

verdict: PASS

## Round 5 (2026-11-04T16:30:43+08:00)

- task：`t029_automation_compatibility_probe_harness`
- diff_anchor：`2c4d78ac8df3aaa001d489b575169a0b95422dbd`
- round：5（review 上限 5 轮，本轮为最后一轮额度内复核）

### 本轮重点核实（Round 4 新 minor t029_test_f011 是否已消除）

- t029_test_f011（zoom 报告条目未记录实际尝试的 keysym，keysym 覆盖回归时 e2e 无法察觉）——**已消除**。三点逐项核实均成立：
  1. 生产侧已补字段：`tests/fixtures/automation_probe/run_levels.py:350` 缩放元组仍为 `("ctrl+plus", "ctrl+equal")`，`:351-352` 循环逐个经 `xtest.key` 发送，`:363` zoom 条目补 `"keysym_attempted": list(zoom_keysyms)`——字段取自与发送循环同一变量，而非另写一份硬编码列表。
  2. 消费侧已断言：`tests/e2e/test_automation_compatibility_probe_e2e.py:102-103` zoom 循环断言 `entry["keysym_attempted"] == ["ctrl+plus", "ctrl+equal"]`，为精确等值断言，非存在性或弱化断言；同循环保留 verdict 枚举与双路 `client_error is not None` 断言，未被放宽。
  3. 非恒真验证：若元组被改回 `("ctrl+plus", "ctrl+plus")`，发送循环与记录字段同步变为 `["ctrl+plus", "ctrl+plus"]`，与 e2e 期望 `["ctrl+plus", "ctrl+equal"]` 不等，断言必失败（reviewer 以等值比较独立验算：`["ctrl+plus", "ctrl+plus"] == ["ctrl+plus", "ctrl+equal"]` 为 False）。空转放行路径亦不存在：zoom 采样为 `range(2)` 无条件 append，且 e2e 先断言驱动子进程返回码为 0，驱动失败不会静默产出空列表蒙混。e2e 本身仅在 t032 门控环境变量下运行属既有门控，非本轮新增弱化。

### 前轮 finding 复核

- t029_test_f001（Dialog 遗留/新连接与 beforeunload 只采集不断言）——**已消除，保持**。两条 Dialog 测试的 `opening_replayed is False` 断言仍在位（`tests/integration/test_automation_probe_chain.py:646`、`:790`），beforeunload 两激活方式的字段级断言未回退。
- t029_test_f002（alert 从未执行）——**已消除，保持**。两条 Dialog 测试的 pending + `--dialog-type alert` 轮次仍在位（`tests/integration/test_automation_probe_chain.py:621`、`:768`），`opening["type"] == "alert"`、`handled_while_pending is True`、`evaluate_completed is True` 断言未变。
- t029_test_f003（addScript/setAutoAttach 漏分类）——**已消除，保持**。unit `test_classify_cdp_method_categories` 与 `test_state_changing_methods_include_injection_and_attach`（`tests/unit/test_automation_probe_harness.py:54-87`）仍在位，本轮独立重跑 unit 全部通过（含这两条）。
- t029_test_f004（下载 False 侧不断言）——**已消除，保持**。目标引擎矩阵循环 False 分支的 `payload["download"]["event"] == "download"` 且 `captured == []` 断言（`tests/integration/test_automation_probe_chain.py:382-383`）仍在位。
- t029_test_f005（交付驱动缺 AC-005 多维度）——**已消除，保持**（残余 f009、f011 均已闭环）。run_levels 的 CDP `client_error`、XTEST iframe、缩放、焦点争用子场景代码逐段在位；e2e 的 verdict/误差断言未回退，本轮又补 keysym 精确断言。
- t029_test_f006（# type: ignore 危险模式）——**已消除，保持**。本轮全量 grep t029 交付文件（unit/integration/e2e/fixtures）无任何 `type: ignore`。
- t029_test_f007（AC-002 超时后存活无场景）——**已消除，保持**。`test_probe_chain_client_killed_mid_connection_survival` 仍在位，hold 客户端 ready 后强杀、断言浏览器 pid 存活且页面可 evaluate。
- t029_test_f008（授权拒绝断言过宽、无裸 CDP 断言缺失）——**保持 Round 3/4 状态：拒绝精确集合已闭环，loopback 直连尝试残余仍为 minor，不阻断**。拒绝断言仍为精确集合 `{"close:4401", "handshake:InvalidStatus"}`（`tests/integration/test_automation_probe_chain.py:418`）；loopback 断言仍只核对已用端点 hostname，未新增对浏览器 DevTools 端口绕过隧道的未授权直连尝试。该残余与 Round 2/3/4 相同，不重复立项。
- t029_test_f009（e2e 对 zoom/focus 只验键存在、缩放无判定字段）——**已消除，保持**。e2e zoom verdict 枚举与双路 `client_error`、focus 布尔与 `client_error` 逐条断言仍在位；run_levels 缩放条目 `verdict` 字段仍在位，本轮又补 `keysym_attempted`。
- t029_test_f010（unit 的 Any 未导入）——**已消除，保持**。`tests/unit/test_automation_probe_harness.py:7` 的 `from typing import Any` 仍在位。

## Findings

本轮无新 finding。

## 结论

- 前轮 finding 复核：f001–f007、f009、f010 已消除且保持；f011 本轮已消除；f008 拒绝精确集合保持闭环，仅 loopback 直连尝试残余维持 minor。前轮全部 critical / important 仍保持消除，无换形式弱化（逐项以当前 diff、代码与断言核实，未采信 note.md 处置表）。
- 改测方向复核：无。本轮小修为生产侧 zoom 条目补 `keysym_attempted` 字段与 e2e 补精确等值断言，未动既有断言的预期，未发现把旧预期就地改成新实现输出的迁就式改测，未发现删/反转 expect。
- 本轮新发现：0 条
- 未进表的提示：f008 的 loopback 残余已在上文复核中记录（原 finding 的未闭环部分，不重复立项）；危险模式复扫：恒真断言、删/反转 expect、注释断言、弱化断言、`.only`、新增 skip、mock 被测逻辑均未命中（integration 的 pytest.skip 仍仅为引擎/Xvfb 前提守卫、e2e 的 skipif 仍为 t032 门控，均合法）；unit 独立重跑命令为 gate venv 下 TMPDIR 置于 gate scratch tmp、PYTHONPATH=src/backend 重跑 `tests/unit/test_automation_probe_harness.py -q`，结果 10 passed；按本轮约束未跑浏览器类集成测试。
- 总体判断：Round 4 唯一新 minor f011 已以「发送变量直出字段 + 精确等值断言」的方式闭环且经非恒真验算，Round 1–4 全部 finding 无回退，本轮无新 finding，PASS。
- 系统性 follow-up：无。

## AC 复验方式

- AC-001：re_verified —— 重读两条全链矩阵测试断言未回退，与 Round 2/3 抽查的报告产物结论一致。
- AC-002：re_verified —— 复核下载两模式双向断言、杀客户端存活测试、Browser.close 未发送断言均在位；判定相关的 unit 测试本轮独立重跑 10/10 通过。
- AC-003：re_verified —— 复核拒绝断言精确集合与 loopback hostname 断言的代码本身、外部 Browser.close 停 Profile 测试未回退；裸 CDP 直连尝试的残余见 f008 复核（minor）。
- AC-004：trust_prior —— 判定规则（compare/summarize）unit 已独立重跑通过；每级 5 样本的实跑结论依赖实施侧采样产物，本轮按约束未重跑浏览器采样。
- AC-005：trust_prior —— 交付驱动与 e2e 消费侧的字段契约（zoom verdict 枚举、双路 client_error、本轮新增的 keysym 精确断言）已逐项代码对齐复核并经非恒真验算；CDP/XTEST 数值结论依赖实施侧 levels 产物抽查，实跑未独立重演，缩放维度新字段的实测值待 t032 重跑报告确认。
- AC-006：re_verified —— 重读两引擎 Dialog 测试全文，pending/alert/遗留/beforeunload 全部断言在位未弱化，与 Round 2 抽查的 dialog 报告产物一致。
- AC-007：re_verified —— 复核 e2e t032 入口的 zoom/focus 逐条断言（含本轮 keysym 断言）与生产侧字段对齐，spec 文档的证据分级与拦截清单未回退；真实环境判定仍归 t032。

coverage = 5 / 7

reviewed_scope: 31ba2e506352e52e
verdict: PASS
