# Task review t030（reviewer_focus: 代码）

- task：`t030_agent_executor_page_dialog_safety`
- spec：`docs/tasks/t030_agent_executor_page_dialog_safety/task.md`
- diff_anchor：`395c5d06494d8a5a17fb163b205c7baa6bd93958`
- target：相对 diff_anchor 的 worktree 全量改动（含 intent-to-add 新文件与未提交改动）
- round：1
- reviewed_at：2026-11-04T19:21:32+08:00

reviewed_scope: 1bb2ce47411153f6

## Findings

### t030_code_f001 - 跨调用 ref 的 runtime 校验是恒真式，状态文件未绑定 runtime/profile

- 严重度：important
- 锚点：AC-003（旧 runtime 的 ref 均被拒绝）、AC-004（跨调用 ref 仅在 runtime 等全部校验一致时可用）
- 位置：`src/backend/cbrowser/agent_executor/session.py:450`、`src/backend/cbrowser/agent_executor/refs.py:210`、`src/backend/cbrowser/agent_executor/state.py:56`
- 问题：`validate_ref` 的 runtime 检查比较的是两个调用方参数，但调用方在 `session.py:450-451` 两次传入同一个 `self.runtime_instance_id`，该比较永远不可能触发。更根本的是 `RefEntry` 序列化（`to_dict`）根本不含 runtime 字段，`save_state` 只写 `version`/`snapshots`/`ledger`，不写 profile 或 runtime。实测验证：构造一个 ref 条目后以任意 runtime 值调用校验直接通过，因为没有任何已存 runtime 可供比对。后果：默认状态路径靠文件名区分 profile/runtime，尚能防误用；但一旦用 `--state-file` 显式复用或拷贝了另一 runtime 的状态文件，旧 runtime 的 ref 与账本 cleanable 授权会被新 runtime 全盘接受（只要目标、frame、loader、签名恰好一致），AC-003/AC-004 宣称的 runtime 隔离在该路径上不存在。同一根因也影响账本恢复：`start` 时持久化账本按存活目标覆盖 baseline 时不校验文件来源。
- 建议：最小修复是把 `runtime_instance_id`（与 profile）写进 ref 条目与状态文件，在 `load_state`/`decode` 或 `start` 恢复时校验不一致即丢弃/拒绝，并把条目自带的 runtime 值作为 `validate_ref` 的被比较方传入，删除恒真式调用。

### t030_code_f002 - 已勾选的 AC-006 只覆盖自动消解子案，滞留会话的遗留 Dialog 无法由下一调用恢复

- 严重度：important
- 锚点：AC-006（CLI 退出后遗留的 Dialog 能由下一调用识别，并在页面命令无响应时恢复）
- 位置：`src/backend/cbrowser/agent_executor/session.py:112`、`src/backend/cbrowser/agent_executor/session.py:126`、`src/backend/cbrowser/agent_executor/session.py:635`
- 问题：Dialog 状态只存在于进程内 `DialogTracker`，`export_state` 只持久化快照与账本，不持久化 Dialog。`dialog_answer` 先 attach 再查跟踪器，但已打开的 Dialog 不会向新 attach 的会话重放 opening 事件，因此无认领会话自动消解之外的情形（例如 Playwright 监听会话滞留的 Dialog）下，下一调用既无法识别该 Dialog，也无法应答——页面命令被 modal 阻塞的状态得不到恢复。实现文档本身也承认该滞留情形“属 Chrome 层限制”，即承认未实现。而 spec 对该分支有明确的既定选型：新连接不能得知并应答时，应由容器内常驻 Agent 维护 Dialog 状态并经既有隧道暴露；实现方明确否决了常驻方案，却仍将 AC-006 打勾。自动消解子案（无认领会话时 Chrome 打开即 dismiss、下一调用畅通且观测到 false）是真实存在的，但它不等于 AC-006 全文。
- 建议：二选一并由批准方定夺：按 spec 既定选型补常驻 Dialog 会话（只启用所需能力、经既有隧道暴露），或经批准将 AC-006 文本收窄为仅自动消解子案并把常驻会话的归属明确写入 t031 范围；在收窄获批并落入 task 之前，本 finding 保持 blocking。

### t030_code_f003 - dialog_wait 不 attach，首步骤即 dialog_wait 的程序永远观测不到 Dialog

- 严重度：minor
- 锚点：AC-005（Dialog 可明确应答；触发命令 pending 时仍可应答）
- 位置：`src/backend/cbrowser/agent_executor/session.py:660`
- 问题：`dialog_wait` 只轮询进程内跟踪器，从不调用 `attach`；而同一文件的 `dialog_answer`（`session.py:635`）会先 attach。再现路径：动作程序的首步骤就是对某一 target 的 `dialog_wait`（此前无 adopt/snapshot/click attach 过该 target），则该 target 从未启用 Page 域，opening 事件永远到不了跟踪器，`dialog_wait` 恒以 `dialog_timeout` 告终，即使等待期间页面确实打开了 Dialog。现有测试与文档用法总是先 attach，故该缺陷被掩盖。
- 建议：`dialog_wait` 入口与 `dialog_answer` 对齐，先 attach 再轮询；attach 失败时返回明确的 `target_not_found`/`cdp_error` 而非超时误导。

### t030_code_f004 - 非法 dialog answer 值被静默折算为保守默认值，而非稳定错误

- 严重度：minor
- 锚点：AC-005（明确应答）、AC-001（稳定错误可区分）
- 位置：`src/backend/cbrowser/agent_executor/dialogs.py:50`
- 问题：`decide` 中 `answer` 不在 `("accept", "dismiss")` 时直接落入 `default_action`，不校验、不报错。实测验证：对 confirm 调用 `decide("accep")`（拼写错误）返回 `dismiss`，无任何错误信号。输出结果虽会写明实际动作，但调用方意图为 accept 的程序会在无告警的情况下得到相反结果；对 prompt 而言，非法 answer 同样被静默 dismiss。
- 建议：`decide` 收到非空且非法的 answer 时抛错，由 CLI 映射为 `invalid_program`；仅 `answer=None` 走保守默认语义。

### t030_code_f005 - 动作程序缺字段时报 internal_error，而非 invalid_program

- 严重度：minor
- 锚点：AC-001（中途错误可区分、稳定错误）
- 位置：`src/backend/cbrowser/agent_executor/cli.py:50`、`src/backend/cbrowser/agent_executor/cli.py:64`
- 问题：`_run_step` 直接用 `step["targetId"]`、`step["ref"]`、`step["text"]`、`step["url"]`、`step["expression"]` 取值（`cli.py:71-111`），缺字段时抛 `KeyError`（`timeoutMs`/`count` 非数字时抛 `ValueError`），而 `_step_error_code` 将这两类都映射为 `internal_error`。再现：`{"action": "click"}`（无 targetId/ref）返回 `internal_error`，调用方会误以为是执行器内部故障，实为程序本身非法。
- 建议：在 `_run_step` 入口对各动作的必填字段做显式校验，缺失/类型错误统一抛 `invalid_program`；或在 `_step_error_code` 中将 `KeyError`/`ValueError` 源自程序解析的情形映射为 `invalid_program`。

### t030_code_f006 - 失败的 Target.getTargets 响应会清空隧道已观测页面集，使最后一页 backstop 失效

- 严重度：minor
- 锚点：AC-008（最后一个内部 Tab 不导致意外停止）、AC-009（隧道保护）
- 位置：`src/backend/cbrowser/runtime_agent/tunnel_filter.py:161`
- 问题：`observe_incoming` 处理 `Target.getTargets` 响应时无条件用 `(result or {}).get("targetInfos", [])` 重建 `_known_pages`；当响应是错误（无 `result`）时，已观测页面集被清空为 `[]`。实测验证：先以一次成功响应建立单页集合（此时关闭该页被拒绝），再以一次错误响应冒充同 id 的 getTargets 回复，随后关闭同一页即被放行。触发条件较窄（需一次失败的 getTargets 响应在先），且执行器自身的账本清理仍受保护，但该 backstop 正是为防外部客户端关掉最后一页而设，错误响应不应削弱它。
- 建议：仅当响应含 `result.targetInfos` 且无 `error` 时才重建 `_known_pages`；错误响应只清除 pending 标记，不动已观测集合。

### t030_code_f007 - 规约宣称 Playwright 精确固定版本，但打包文件中无此依赖

- 严重度：minor
- 锚点：AC-010（文档与 help、公开 API 一致）；按审阅规则，版本号本身不作行为 AC 判 blocking
- 位置：`docs/specs/agent_executor.md`（CLI 一节）、`pyproject.toml`（dependencies）
- 问题：规约写明“Playwright 精确固定 `playwright==1.64.1`（与门禁锁一致）”，但 `pyproject.toml` 的 dependencies 中无任何 playwright 条目（实测 grep 仅命中 websockets 等其他依赖），仓内也无与之对应的锁文件条目。生产路径不走 Playwright，故不影响执行器行为，影响的是测试环境可复现性与文档真实性。
- 建议：二选一：把该版本钉入打包依赖（若测试链确实依赖它），或修正规约措辞为测试环境约定而非打包固定。

### t030_code_f008 - --token-file 的 0600 要求未在 CLI 落实

- 严重度：minor
- 锚点：AC-001（CLI 自身输出、错误、日志与账本不含凭证）、AC-010（授权规则）
- 位置：`src/backend/cbrowser/agent_executor/cli.py:203`
- 问题：`load_token` 直接读文件内容，不检查文件权限位；文档多处以 `--token-file`（0600）表述该输入，但一个全局可读的 token 文件会被静默接受。执行器自身不泄露 token（无 `--token` 旗标、错误经 redact），此项只是纵深缺口：松权限的凭证文件失去最后一道提醒。
- 建议：`load_token` 在读文件前检查模式，非 0600（或所有者不可读之外的放宽）时拒绝并给出明确错误，或在文档中把 0600 改述为使用者保管约定而非 CLI 强制项。

### t030_code_f009 - “关 Tab 授权由账本 enforcement”的表述越界：外部隧道客户端的关 Tab 不经过账本

- 严重度：minor
- 锚点：AC-002/AC-008（用户/unknown 页面保留）、AC-009（隧道保护范围）
- 位置：`src/backend/cbrowser/runtime_agent/tunnel_filter.py:95`（Target.closeTarget/Page.close 分支）、`src/backend/cbrowser/agent_executor/session.py:721`
- 问题：隧道对 `Target.closeTarget`/`Page.close` 除最后一页 backstop 外一律放行，从不查询执行器账本；账本只约束执行器自身 `cleanup` 发起的关闭。外部客户端（不走执行器）因此可经隧道关闭任意非最后一页的用户页，而文档表述会让读者以为关 Tab 授权已被账本兜底。按 spec 非范围，外部客户端排他归 t031，故本项不判 blocking；但文档边界必须收窄。
- 建议：把隧道过滤与规约中的相关表述修正为“执行器发起的清理由账本约束；外部客户端的关 Tab 在 t031 排他落地前仅受最后一页 backstop 约束”，不在 t030 范围内宣称用户页已防外部关闭。

### t030_code_f010 - mousedown 处理器触发的 Dialog 会使 click 丢掉 mouseReleased

- 严重度：minor
- 锚点：AC-005（触发命令 pending 时仍可应答；click 语义完整）
- 位置：`src/backend/cbrowser/agent_executor/session.py:502`
- 问题：`click` 的 press/release 循环在任一分发遇到 Dialog 时立即返回，不区分 Dialog 是在哪一阶段打开的。常见情形（click 处理器触发 Dialog）无此问题：release 已发出，只是其响应被挂起后丢弃。但若 Dialog 由 mousedown 处理器触发，press 分发挂起、click 提前返回，`mouseReleased` 从未发出；后续 `dialog_answer` 关闭 Dialog 后，目标元素永远收不到 mouseup/click，click 实际未完成，而返回结果只含 `{x, y, dialog}`，未记录 release 被跳过。
- 建议：记录 Dialog 触发阶段；若 Dialog 在 press 阶段打开，在 `dialog_answer` 成功后补发一次 `mouseReleased`（或在 click 结果中明确标注 release 未发出），使调用方可判断 click 是否完整。

## 结论

- 前轮 finding 复核（Round 1，首轮）：无前轮。
- 本轮新发现：10 条，其中 important 2 条（f001、f002），minor 8 条（f003–f010）。
- 未进表的提示：
  - 文件过大（结论段提示，不进 finding 表）：`src/backend/cbrowser/agent_executor/session.py` 733 行，已达实现源码 400 行 minor 阈值（未达 800 行 important 阈值）；本 task 新建该文件即 733 行，职责含会话生命周期、快照、校验、点击/Dialog 与清理，建议后续按步骤族拆分。`tests/integration/test_agent_executor_chain.py` 1159 行，未达测试源码 1200 行 important 阈值，接近上限，仅提示。`docs/specs/agent_executor.md` 等文档与测试文件未超阈值。
  - 圈复杂度（手算近似 McCabe，结论段提示）：逐函数扫过 diff 内新增/改动函数，最高约 9（`session.py` 的 `_handle_event` 与 `_validated_entry`），无函数达 15 行 minor 阈值、无需拆分 finding；纯转发与表驱动分支已排除。
  - 范围外观察（不进 finding 表）：`src/backend/cbrowser/agent_executor/transport.py` 的 `connect` 中 `try: kwargs["proxy"] = None except TypeError` 是死代码（字典赋值不可能抛 TypeError），无行为影响，可顺手清理；`session.py` 的 `close` 未取消 `_attach_tasks`，CLI 进程退出即终结，无可观测影响；隧道最后一页 backstop 对自动 attach（`Target.setAutoAttach`）建立的会话无映射，`Page.close` 经该类会话发起时 backstop 可能漏判，建议 t031 排他设计时一并确认。
  - 肯定项（经代码核对）：账本来源/管理权/清理权三分离真实落地（adopt 不授清理权、popup 需 openerId+时序窗口+账本三方证据、清理保留最新一页并报告 `last_tab_protected`）；ref 校验含 frame/loader/签名与 `isConnected` 存活关口，克隆替换节点可被识别；隧道对 `Browser.close`、下载行为覆盖、Emulation 覆盖族与 `Network.emulateNetworkConditions` 一律拒绝并返回带原 id/sessionId 的稳定错误，脚本登记与断开清理已接入 agent 隧道 teardown；CLI 无 `--token` 旗标、错误经 token redact、自身从不发送 `Browser.close`、关闭仅走 `Target.closeTarget` 且仅针对 cleanable 目标；快照 frame 归属以 pierced DOM 映射为准、无法映射的文档节点不进快照。
- AC 复验方式：
  - AC-001：re_verified——逐项核对 CLI 步骤分发、错误码映射、token 输入与 redact、成功不隐式清理/失败自动清理的代码路径；CLI 自身不发送 `Browser.close` 已 grep 确认。
  - AC-002：re_verified——核对账本 `baseline`/`record_created`/`record_observed`/`adopt`/`cleanup_plan` 的来源与清理权分离，adopt 不改来源、不授清理权、不导航。
  - AC-003：re_verified——核对 popup 三方归属证据、目标存活与 frame/loader/签名校验；但 f001 表明旧 runtime 子项在状态文件复用路径上未真正拒绝。
  - AC-004：re_verified——核对快照 DOM 映射、ref 命名空间隔离、逐项校验与 `isConnected` 关口；但 f001 表明 runtime 子项校验恒真。
  - AC-005：re_verified——核对保守默认语义、独立命令 future 与 click 的 dialog 感知等待；f003/f004/f010 为该 AC 下的 minor 缺口。
  - AC-006：re_verified——核对进程内 Dialog 跟踪、跨调用状态导出范围与 `dialog_answer` 的 attach 语义；复验结论是仅自动消解子案成立，f002 为 blocking 缺口。
  - AC-007：re_verified——核对 `permission` 步骤恒返回需真人 handOff 载荷、文件选择走独立步骤，规约已将 CDP 无原生事件列为限制。
  - AC-008：re_verified——核对清理仅关 cleanable 目标、最后一页保留与原因报告；f006 为隧道 backstop 的 minor 缺口。
  - AC-009：re_verified——核对隧道拒绝清单、稳定错误格式、脚本登记与断开清理、断开后下载重捕获的 agent 接线；f009 为文档边界 minor。
  - AC-010：re_verified——核对薄入口 Skill 落点（产品资产目录）、`cbrowser-agent` entrypoint、程序版本与稳定错误清单；f007 为版本钉死表述的 minor。
  - AC-011：trust_prior——云端真实 Chromium 与目标引擎的执行证据依赖实施侧门禁运行结果；本轮因本机无 pytest 环境且集成链需浏览器与显示服务，未重跑集成链，仅核对了集成链测试文件确实经正式认证隧道路由生产代码（API 自动化 WS → Supervisor → Agent UDS 隧道 → 真实浏览器）。
  - coverage = re_verified 10 / 总 AC 数 11（trust_prior 1 项，占比约 9%，未超 30%，无需加人工抽查行；但 f001/f002 本身已阻断）。
- 总体判断：实现主干扎实（账本、ref 校验、隧道拒绝、Dialog pending 处理均有真实代码支撑），但两条已勾选 AC 的关键子项未兑现——runtime 校验恒真、滞留 Dialog 无恢复路径——故不能 PASS。
- 系统性 follow-up：无新增 task。f002 的常驻 Dialog 会话归属建议由实施方在 note 处置表中定夺：并入已存在的 t031（真人优先控制权与安全交接，backlog）或新立 follow-up；不重复建项。

verdict: FAIL

## Round 2 (2026-11-04T19:39:00+08:00)

reviewed_scope: d13914853bdb5b3c

本轮说明：R2 prompt 内注入的契约快照仍将 AC-006 列为已勾选，但该快照渲染于主会话裁决之前；本轮以当前 task.md 为准——AC-006 已取消勾选（主会话裁决 2026-11-04），常驻 Agent 分支归 t031 设计输入。以下复核均以当前 task.md、note.md 与 diff 为准，不以注入快照的勾选态为准。

### 前轮 finding 复核

- t030_code_f001（important，runtime 校验恒真/状态文件无绑定）：已消除。`src/backend/cbrowser/agent_executor/refs.py:36,51,70` 为 RefEntry 增 runtime_instance_id 字段并随 to_dict 往返；`refs.py:239-240` 以条目自带 runtime 对照调用方活 runtime，不再是双参同值；`src/backend/cbrowser/agent_executor/state.py:67-79` 的 bound_state 在绑定不符时整体返回空；`src/backend/cbrowser/agent_executor/cli.py:335-342` 在覆盖 baseline 前先调 bound_state，跨 runtime 拷贝的状态文件不再被叠加。测试证据见 `tests/unit/test_agent_executor_refs.py:142-157`（跨 runtime 复用判 stale、无绑定条目永不通过）。
- t030_code_f002（important，AC-006 常驻分支缺失却打勾）：已消除（经批准的收窄路径，非实现覆盖）。task.md 的 AC-006 现为未勾选并附主会话裁决注；note.md Round 2 节有主会话裁决记录（f002 边界解读不成立、常驻分支归 t031）；`docs/specs/agent_executor.md:115-119` 明确写常驻分支不在 t030 实现、须与 t031 一并定夺。R1 建议的二选一中“经批准收窄并明确 t031 归属”已落入 task，本 finding 的 blocking 条件解除。注意：本轮不认同“AC-006 已实现”的说法，只认同“AC-006 已标记未完成且归属已明确”。
- t030_code_f003（minor，dialog_wait 不 attach）：已消除。`src/backend/cbrowser/agent_executor/session.py:670-676` 的 dialog_wait 入口先 attach 再轮询，与 dialog_answer 对齐；attach 失败走 target_not_found/cdp_error，不再以超时误导。
- t030_code_f004（minor，非法 answer 静默折算）：已消除。`src/backend/cbrowser/agent_executor/dialogs.py:68-69` 对非空非法 answer 抛 ValueError；session.py 的 dialog_answer 将其映射为 invalid_program；`tests/unit/test_agent_executor_dialogs.py:78` 有对应断言。
- t030_code_f005（minor，缺字段报 internal_error）：已消除。`src/backend/cbrowser/agent_executor/cli.py:69-82` 对必填字段做显式校验并统一报 invalid_program；cli.py 内已无 `step["..."]` 直接索引（grep 零命中），KeyError 路径已不存在；`tests/unit/test_agent_executor_cli.py:416-434` 有对应断言。
- t030_code_f006（minor，失败 getTargets 清空页面集）：已消除。`src/backend/cbrowser/runtime_agent/tunnel_filter.py:168-177` 仅当响应无 error 且 result 为 dict 时才重建已观测页面集，错误响应只清 pending 标记。
- t030_code_f007（minor，Playwright 钉死表述与打包不符）：已消除。`docs/specs/agent_executor.md:10-13` 已改述为生产路径不用 Playwright、门禁按 gate-requirements 固定版本；pyproject 仅新增 cbrowser-agent entrypoint，无 playwright 依赖宣称。
- t030_code_f008（minor，token-file 0600 未落实）：已消除（约定变更路径）。`src/backend/cbrowser/agent_executor/cli.py:246-261` 的 load_token 对非 0600 模式打 stderr 告警后继续，并附理由注释；`docs/blueprint/security.md:29-31` 已把 0600 定为调用方保管约定而非 CLI 强制项。
- t030_code_f009（minor，关 Tab 账本表述越界）：已消除。`docs/specs/agent_executor.md:146-147` 已收窄为执行器发起的清理由账本约束、外部客户端关 Tab 在 t031 排他落地前不受账本约束。
- t030_code_f010（minor，mousedown 触发 Dialog 丢 release 无标注）：已消除。`src/backend/cbrowser/agent_executor/session.py:514-521` 仅在 mousePressed 阶段打开 Dialog 时附 release_skipped: true；规约 Dialog 节已说明调用方应答后需重新动作。

### 本轮新发现

#### t030_code_f011 - f002 处置表行仍写“AC-006 维持勾选”，与裁决后现状矛盾

- 严重度：minor
- 锚点：文档与规格一致性（AC 状态表述）
- 位置：`docs/tasks/t030_agent_executor_page_dialog_safety/note.md` 处置表 t030_code_f002 行
- 问题：该行 rationale 仍写“AC-006 维持勾选”，但主会话裁决后 task.md 已改为未勾选，note.md Round 2 裁决段也已取代该判断。只读处置表会误以为 AC-006 仍勾选。
- 建议：finish 侧在该行追加裁决引用（不改写 R1 原意，标注“经 2026-11-04 主会话裁决取代：AC-006 已取消勾选、常驻分支归 t031 设计输入”），使处置表与 task.md 现状一致。

### 修复引入的回归扫描

- bound_state 误绑整体丢弃：fail-safe 方向——丢弃后旧页记 unknown，而 unknown 永不可清理，不会误删用户页。
- dialog_wait 先 attach：attach 失败以明确错误返回，不再恒超时。
- set_input_files 同会话先取 document（depth 0）：解决跨调用新会话 pushNodes 被拒的产品 bug，未改动 ref 校验语义。
- `src/backend/cbrowser/runtime_agent/agent.py` 隧道接线：非 dict 消息直通（CDP 本就要求 JSON 对象，无走私面）；断开清理为 best-effort 且异常被 contained，不破坏 teardown。
- R1 结论段提示项：transport.py 死代码 try/except 已删（proxy=None 直赋）；session.close 未取消 _attach_tasks 仍无可观测影响，未改。
- 本轮未发现新 blocking 缺陷。

### 结论

- 前轮 finding 复核：f001–f010 全部已消除（f001 真修；f002 经批准的收窄路径闭环；f003–f010 逐条真修）。
- 本轮新发现：1 条 minor（f011）。
- 未进表的提示：
  - 文件过大（结论段提示，不进 finding 表）：`tests/integration/test_agent_executor_chain.py` 现 1366 行，已超测试源码 1200 行 important 阈值（R1 时为 1159 行、仅提示）；本 task 仍净增该文件，建议后续按用例族拆分，不阻断本轮。`src/backend/cbrowser/agent_executor/session.py` 757 行，超 400 行 minor 阈值、未达 800 行 important 阈值，仅提示。
  - 圈复杂度：扫过本轮改动函数，无新增函数达 15 的 minor 阈值（validate_ref、bound_state、dialog_wait 均为短分支链），仅提示。
  - 范围外观察（不进 finding 表）：task.md 第 20 行设计行仍原文引用常驻 Agent 分支，该句为创建期设计文本，现须与 AC-006 裁决注一并理解；finish 侧可在设计行旁加一句指向裁决的注脚，非强制。
- AC 复验方式：
  - AC-001：re_verified——CLI 步骤校验、错误码映射、token redact、自身不发 Browser.close 的代码路径已核对。
  - AC-002：re_verified——账本来源/清理权分离未动，f001 修复补强了跨调用绑定。
  - AC-003：re_verified——popup 三方证据未动；f001 使旧 runtime 子项在状态复用路径上真实拒绝。
  - AC-004：re_verified——ref 逐项校验与条目自带 runtime 对照（refs.py:239）。
  - AC-005：re_verified——dialog_wait attach、decide 非法值、release_skipped 均已核对。
  - AC-006：未勾选，不计 re_verified——CLI 可应答分支与自动消解分支实现真实存在，但常驻分支未实现且已归 t031，AC 整体未完成。
  - AC-007：re_verified——permission 恒需真人、限制已文档化，本轮 diff 未触该路径（R1 结论延续）。
  - AC-008：re_verified——清理保留与 f006 backstop 修复均已核对。
  - AC-009：re_verified——隧道拒绝清单与 f006/f009 均已核对。
  - AC-010：re_verified——entrypoint、Skill 落点、f007 措辞均已核对。
  - AC-011：trust_prior——云端真实 Chromium 与目标引擎的执行证据依赖实施侧门禁运行结果；本轮未重跑集成链（代码审阅职责边界），仅核对链测试经正式隧道路由生产代码（R1 结论延续）。
  - coverage = 9 / 11（trust_prior 1 项，占比约 9%，未超 30%，无需加人工抽查行）。
- 总体判断：R1 全部 blocking 已消除，本轮仅 1 条 minor，故 PASS；f011 由 finish 侧在处置表追加裁决引用后闭环。
- 系统性 follow-up：无新增 task。常驻 Dialog 分支归 t031 设计输入（主会话裁决已定，t031 派发中明确写入）；测试链文件拆分建议记为后续清理，不另立项。

verdict: PASS

## Round 3 (2026-11-04T19:49:00+08:00) — 窄范围确认：AC-006 勾选态翻转

- 范围：仅确认主会话 A 方案翻转（AC-006 由未勾选改为打勾 + 行内 deferral 注）三方一致，以及 R2 之后无实现/测试改动；不重审实现，不重跑全量门禁。
- 核查通过项：
  - task.md 第 43 行：AC-006 现为 [x]，行内注完整写明“CLI 可应答分支已实现；容器内常驻 Agent 分支未在 t030 实现，归 t031 设计输入；本勾选为带 deferral 接受（沿 t024 先例），非已实现”。
  - note.md Round 2 裁决段落：原裁决（取消勾选）与补充裁决 A 方案并存——补充裁决写明 finish 门禁机械要求全部 AC 打勾（无 deferred 豁免态）、故改为打勾 + 行内 deferral 注、deferral 本身不变、仍归 t031 设计输入。
  - note.md 收尾报告结果摘要行：AC-006 表述为打勾 + 行内 deferral 注（勾选为带 deferral 接受，沿 t024 先例，非已实现），与 task.md 一致。
  - t024 先例属实：归档 t024 task.md 中 AC-001 与 AC-015 均为 [x] 打勾，补充裁决引用的先例成立。
  - R2 后改动面：仅 task.md 与 note.md 两处记录性改动（mtime 均为 R2 之后）；src、tests、specs、blueprint、pyproject、assets 在 R2 测试报告之后无新改动（mtime 核查），实现与测试未动。
- 历史记录说明：note.md 处置表 f002 行与原裁决段落中的“已取消勾选”措辞为 R1/R2 时期的历史记录，已被补充裁决取代（f002 行附有取代标注），不构成新的不一致，不另立案。
- 本轮新发现：1 条 minor。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t030_code_f012|minor|待处置|note.md 收尾报告“结果”行仍写“AC-006 未勾选”，与 task.md 现行 [x] 态及同报告结果摘要行“打勾 + 行内 deferral 注”矛盾；收尾报告是归档的最终状态记录，同一事实不得两说。处置建议：finish 侧把该行改为与摘要行一致的表述（打勾 + 行内 deferral 注，勾选为带 deferral 接受、非已实现）；note.md 属指纹排除文件，该行修正不应使 scope 再次失效（以 checker 复跑为准）|note.md 收尾报告“结果”行、结果摘要行|

### 结论

- 三方核心一致（task.md 勾选态 + 行内注、note.md 裁决段落补充裁决、收尾报告摘要行），R2 后实现与测试无改动。
- 但收尾报告结果行一处表述未同步翻转，构成表述矛盾；按本轮窄范围规则记 finding 并给 FAIL，待 f012 处置后需一轮窄范围确认（仅核该行修正）方可 finish。

verdict: FAIL

## Round 4 (2026-11-04T19:52:28+08:00) — 窄范围确认：f012 处置

reviewed_scope: be5e95a749676ba7

范围：仅核 R3 代码侧新立 minor t030_code_f012 的处置，不重审实现，不重跑全量门禁。指纹以被审 diff 的单一真相源实算（diff_anchor 为 t029 tip，note.md 属指纹排除文件，故 f012 的 note.md 修正不改变指纹），与测试侧 R3 实算值一致。

- 核查项 1（收尾报告结果行）：note.md 收尾报告“结果”行现为“部分满足——AC-006 打勾+行内 deferral 注（勾选为带 deferral 接受，沿 t024 先例，非已实现），deferred 归 t031 设计输入；其余 AC 满足”，与同报告结果摘要行“AC-006 打勾+行内 deferral 注：……勾选为带 deferral 接受，沿 t024 先例，非已实现”一致，f012 所指的表述矛盾已消除。
- 核查项 2（f012 处置行）：处置表 t030_code_f012 行存在，说明收尾报告“结果”行原“AC-006 未勾选”与 task.md 现行 [x] 态及结果摘要行矛盾、已改为与摘要行一致的表述，并注明 R1/R2/R3 原文未改写。
- 核查项 3（R2 后改动面）：以 R2 测试报告时间（19:42:46+08:00）为阈核查 mtime，src、tests、docs/specs、docs/blueprint、assets、pyproject.toml 在该时间之后无新改动文件；仅 task.md（AC-006 勾选态翻转）与 note.md（裁决记录句与 f012 两处修正）为 R2 之后的记录性改动，实现与测试未动。
- task.md 第 43 行 AC-006 现为 [x] 且行内注完整写明“CLI 可应答分支已实现；容器内常驻 Agent 分支未在 t030 实现，归 t031 设计输入；本勾选为带 deferral 接受（沿 t024 先例），非已实现”，勾选不被读作“已实现”。
- 本轮新发现：0 条。R3 代码侧的 f012 已处置，blocking 条件解除。

### 结论

三项核查全部通过，f012 已闭环；本轮窄范围确认通过。

verdict: PASS
