---
tid: "t030"
slug: "agent_executor_page_dialog_safety"
title: "实现带页面保护、Dialog 恢复与短期引用的 Agent 执行器"
status: "done"
branch: "t030_agent_executor_page_dialog_safety"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "395c5d06494d8a5a17fb163b205c7baa6bd93958"
depends_on: "t029"
conflicts_with: ""
note: "来源 p030、p032、p033；云端 Muse，真实环境执行交 t032"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-04：从 p030、p032、p033 聚合立项，核实基线 main@c6a9322；只创建 backlog，不 start。
- 2026-11-04 实施设计（base=t029 分支 395c5d0；门禁 venv 位于仓外 ~/gate_scratch_t030，TMPDIR/UV_CACHE_DIR 同置仓外）：
  - CLI 路线：宿主 CLI `cbrowser-agent`（pyproject `[project.scripts]` entrypoint，Playwright 精确固定 `playwright==1.64.1`，与 gate 锁一致）经既有 cbat_ 认证隧道连接，`connect_over_cdp(no_defaults=True)`，不用 no_defaults=False（其下载/焦点/媒体仿真会覆盖 Agent 捕获，t029 已实测）。stdin 读 JSON 动作程序（p030 的 `<<'JS'` heredoc 素描落为结构化步骤：任意页内 JS 无法完成可信 CDP 输入、ref 逐项校验与 Dialog 处理，且 AC-001 要求稳定错误 taxonomy；`evaluate` 步骤仍提供页内求值/提取，调用方对其返回数据负责，文档中说明、不伪装成只读）。
  - 隧道过滤（agent.py `/cdp` 隧道，外部客户端唯一 choke 点；Agent 自身 `/control` 关闭路径不受影响，Supervisor 生命周期关闭仍可用）：Browser.close 一律拒绝；Browser/Page.setDownloadBehavior 与 Emulation 覆盖族、Network.emulateNetworkConditions 一律拒绝（自动化会话期间下载行为变更不得绕过 Artifact 捕获，AC-009）；Page.addScriptToEvaluateOnNewDocument 按会话登记、断开时经同一 chrome_ws 以 sessionId 尽力清除（平拒会破坏 Playwright utility 注入，t029 L5 已证实其存在；登记+清理达到“不断开不残留”的安全目标，见 spec）。拒绝一律返回带原 id 与原 sessionId 的稳定 CDP 错误，不转发。
  - 隧道过滤修订（2026-11-04 实测驱动）：首版曾对 Target.closeTarget/Page.close 做“仅放行本连接创建目标”的归属过滤，实测 Playwright `popup.close()`（点击从用户页打开的 popup）因此永久挂起——隧道无法区分“刚点击打开的 popup”与“用户页”。改为：关 Tab 不在隧道做归属过滤（Playwright 正常流程与执行器清理均需放行），关 Tab 授权由执行器账本 enforcement（仅 cleanable 目标）；隧道仅保留最后一页 backstop：当其观测到的页面集恰为 1 项时拒绝关闭（关最后一页可致浏览器退出），观测不到页面集时放行、账本仍为权威。t029 既有测试中与新策略冲突的断言（外部 Browser.close 停 Profile、no_defaults=False 期间客户端下载优先）按 testing.md 政策变更规则整体替换并注明 t030 为裁决来源，不静默改预期。
  - Dialog 机制选择（AC-006，依据 t029 AC-006 证据）：不建常驻 Dialog 跟踪 daemon。t029 实测：遗留 Dialog 不向新连接重放、新会话命令不被阻塞、遗留 confirm 已被消解为 false；因此机制 = 会话内动作前监听 + 会话启动探针（轻量命令验证页面可响应）+ 消解结果由常规页面状态观测。常驻 Agent 维护 Dialog 状态的备选被否决：无重放即无需要跨进程保存的状态，徒增指纹与状态漂移面；多客户端并发 Dialog 归属由 t031 排他保证。
  - ref 注册表：快照取 Page.getFrameTree（frameId/loaderId）+ Accessibility.getFullAXTree（backendDOMNodeId/角色/名称）；使用时逐项校验 runtime_instance_id、targetId 存活、frameId 存在且 loaderId 一致、DOM.resolveNode + describeNode 签名一致，任一失配返回失效错误并要求新快照；iframe/OOPIF 以 frameId 隔离，backendNodeId 不跨文档复用。输入只走 CDP Input 域（t029 采用结论），不用 synthetic-event 回退，不注入全局探测变量。
  - 账本：会话启动时已存 target 记 user/unknown；本会话 createTarget 创建的记 agent-owned 且可清理；adopt 保留原始来源、只授管理权不授清理权；popup 归属需 openerId + 动作时序 + 账本三方证据，证据不足记 unknown；清理永不关闭浏览器最后一个剩余页面 target，拒绝并报告 last_tab_protected。
  - 权限提示（AC-007）：CDP 无原生权限/设备提示事件，属不可检测情形，文档列为限制；CLI 提供显式 `permission` 步骤，一律返回需真人结果并附 t031 handOff 可消费的载荷（profile/target/kind/时间），永不静默授权；文件选择走 DOM.setFileInputFiles 独立步骤，与权限提示分开。
- 云端范围与本地最终 t032 分离；真实环境未执行不能按通过回填。
- 2026-11-04：按三方审阅修订：新增隧道层拒绝 Browser.close 与下载捕获保护；跨调用 ref 改自建注册表；targetId 经 CDP 获取；遗留 Dialog 机制按 t029 证据选择；凭据 AC 收窄到 CLI 自身输出；Skill 不放模板软链目录；固定 Playwright 版本与 entrypoint。
- 2026-11-04 快照调试（实测驱动，先于生产改动修测试、后修生产）：
  - 现象：CLI snapshot 只回 RootWebArea。原始 dump 证实：Chrome AX 树只在 frame 根节点带 frameId，其余节点 frameId 为空，旧实现按 AX frameId 过滤遂丢掉全部子节点；iframe 子树根本不在 AX 树内（iframe 节点 children 为空）。修复：frame 归属改以 pierced DOM 走查的文档槽位映射为准（URL 匹配优先、等数按序 zip、无法映射的文档节点不进快照）；子 frame 无 AX 对应元素以 DOM 条目进快照（role/name 为空、tag + id/class 识别）；主 frame 仍只用 AX 树。`getPartialAXTree` 取 iframe 子树已试：节点 id 语义不通（字符串/整数均被拒），此路不通，记为死胡同。
  - script 标记测试缺 `Page.enable`：实测 addScript 注册成功但无 Page.enable 时脚本不在新文档运行（直连浏览器亦然，与隧道无关）；测试 raw helper 补 Page.enable + Runtime.enable 后通过，属测试 bug 非产品缺陷；生产 attach 本就启用 Page/Runtime/DOM。
- 2026-11-04 跨调用状态（产品缺口，非测试问题）：测试按“快照一轮、下一轮用 ref”设计，但实现只有进程内注册表，AC-004 的跨调用校验与 runtime_instance_id 检查在进程内永远触发不了。补实现：ref 与账本持久化到状态文件（`--state-file`，默认 `~/.cache/cbrowser/agent-executor/<profile>_<runtime>.json`，0600、原子写入，不含凭证）；启动时持久化账本按存活目标覆盖 baseline、快照按存活目标恢复。配套语义变更：成功退出不再隐式清理（会话靠状态文件续存，上一调用创建的页留待后续调用），失败/取消仍自动清理，显式 `cleanup` 是正常结束入口；旧“每次退出都清理”使跨调用工作不可能，已废弃。CLI 单元 happy-path 断言随语义变更更新并注明理由（非静默改预期）。
- 2026-11-04 ref 测试真实性修正：原导航案与替换案因中途重拍快照导致注册表被替换，click 失败原因实为“不在快照内”而非 loaderId/签名变化，属假阳性通过。改为：导航案不重拍（用上一调用的持久化 ref 验 loaderId 失效）；替换案拆为快照轮 + 替换点击轮（验签名/存活失效）。
- 2026-11-04 节点存活关口：克隆替换节点仍可 resolve 且签名与原节点相同（克隆保留属性），仅凭 resolve + 签名无法识别；实测 `isConnected=false` 为决定性信号，`scrollIntoViewIfNeeded` 报 `Node is detached from document`。验证关口加 isConnected 检查，动作侧 detached 错误同样映射为 `ref_stale`。
- 2026-11-04 Dialog 分发死锁（产品 bug）：modal dialog 阻塞渲染线程，click 的 mouseReleased 响应不到达；顺序步骤里 click 永不返回，后续 dialog_wait/answer 跑不到。修复：分发改 dialog 感知等待（独立命令 future + 轮询跟踪器），dialog 一打开即提前返回并附带 dialog 信息，调用方以 dialog_answer 应答；click 自身永不自动应答。单元测试以 fake 挂起 release + 发 Opening 事件覆盖。
- 2026-11-04 Dialog 机制精细化（实测修正 t029 证据表述）：无认领会话时 Chrome 在打开时即自动 dismiss（Opening 后紧跟 Closed，结果 false），执行器页上不存在“存活到退出”的遗留 dialog；下一调用畅通且观测到消解结果 false。Playwright dialog 监听 lingering 时 dialog 滞留且新会话无法恢复（Page.enable 被 modal 堵死、handle 报无 dialog），属 Chrome 层限制，写入 spec 与测试注释，不谎称可恢复。legacy 测试因此改用 CLI 自建页（无 lingering 会话）并验证“下一调用畅通 + 消解为 false”这一 AC-006 可观测结果；pending 案仍在用户页 + no-op 监听下验证观察与应答（Playwright 无监听时自动 dismiss 会抢在 dialog_wait 前关闭 dialog，测试侧以 no-op 监听禁用自动 dismiss）。
- 2026-11-04 目标引擎覆盖：链测试原只用普通 Chromium，`_target_engine_cache` 定义未用。新增 `test_executor_target_engine_core_flow`（Playwright 直起 `~/.cloakbrowser/chromium-146.0.7680.177.5/chrome`，targets/adopt/snapshot/agent 页 popup 归属/input/extract/cleanup 全流）；初版在用户页点击导致 popup 期望错误——按规则用户页 opener 的 popup 本就该是 unknown，属测试期望错误，已改为 agent 页点击。
- 2026-11-04 门禁（见收尾报告；唯一失败为存量三项对照：integration 两项旋转/环境性 + unit hygiene t027 绝对路径，干净 base 同 ID；另两项初看失败实为手动跑法缺 PYTHONPATH，补齐后通过，非回归）。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-04T19:21:32+08:00 code / 2026-11-04T19:22:05+08:00 test)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t030_code_f001|important|已修|跨调用 ref 的 runtime 校验恒真（双参同值）、状态文件无绑定；RefEntry 增 runtime 字段并随 to_dict 往返，save_state 写（profile，runtime）绑定，加载绑定不符整体丢弃，validate_ref 改以条目自带 runtime 对照调用方活 runtime|src/backend/cbrowser/agent_executor/refs.py、state.py、session.py、cli.py；tests/unit/test_agent_executor_refs.py、test_agent_executor_state.py、test_agent_executor_cli.py（跨 runtime 复用状态文件：ref_stale + 清理零关闭）|
|t030_code_f002|important|已修|AC-006 只覆盖自动消解子案之说部分成立：task 设计行要求的选择与依据未记入 note/automation；已补选择与依据——新连接可应答的由 CLI 处理、CLI 退出后无认领的由 Chrome 自动消解、常驻 Agent 分支因改变全部客户端 dialog 语义而归 t031 设计域、live 外部持有 dialog 不属于“CLI 退出后遗留”故不在 AC-006 承诺内；AC-006 维持勾选，该边界判断已旗标主会话复核；【主会话裁决 2026-11-04 取代：该判断不成立，AC-006 已取消勾选，常驻 Agent 分支归 t031 设计输入，见 Round 2 裁决段落；本行 R1 原文保留，仅追加裁决引用】|docs/specs/agent_executor.md（Dialog 一节）、docs/blueprint/automation.md（t030 一节）；AC-006 边界判断见收尾报告|
|t030_code_f003|minor|已修|dialog_wait 不 attach 则恒超时；入口与 dialog_answer 对齐先 attach 再轮询|src/backend/cbrowser/agent_executor/session.py dialog_wait|
|t030_code_f004|minor|已修|非法 answer 静默折算为默认值；decide 对非空非法值抛 ValueError，session 映射为 invalid_program|src/backend/cbrowser/agent_executor/dialogs.py、session.py；tests/unit/test_agent_executor_dialogs.py、test_agent_executor_cli.py|
|t030_code_f005|minor|已修|缺字段报 internal_error；_run_step 必填字段显式校验，缺失/类型错误统一 invalid_program（text 允许空串以支持清空）|src/backend/cbrowser/agent_executor/cli.py；tests/unit/test_agent_executor_cli.py|
|t030_code_f006|minor|已修|失败的 getTargets 响应清空已观测页面集致 backstop 失效；仅成功且含 targetInfos 的响应才重建集合|src/backend/cbrowser/runtime_agent/tunnel_filter.py；tests/unit/test_tunnel_filter.py|
|t030_code_f007|minor|已修|规约称 Playwright 精确钉死但打包无此依赖；措辞修正为门禁环境按 gate-requirements.txt 固定，生产路径不依赖 Playwright|docs/specs/agent_executor.md（CLI 一节）；scripts/gate-requirements.txt:41 为钉死依据|
|t030_code_f008|minor|已修|token-file 0600 未在 CLI 落实；定为调用方保管约定：更宽权限只告警不拒绝（拒绝收不回已暴露文件、只会拒绝服务），理由写入文档与测试|src/backend/cbrowser/agent_executor/cli.py load_token；docs/blueprint/security.md；tests/unit/test_agent_executor_cli.py|
|t030_code_f009|minor|已修|“关 Tab 由账本约束”表述越界到外部客户端；收窄为执行器发起的清理由账本约束、外部客户端关 Tab 在 t031 前仅受最后一页 backstop 约束|docs/specs/agent_executor.md（隧道一节）；src/backend/cbrowser/runtime_agent/tunnel_filter.py 注释已与此一致|
|t030_code_f010|minor|已修|mousedown 触发 dialog 时 mouseReleased 从未发出却无标注；click 结果在 press 阶段 dialog 时附 release_skipped: true 并在规约中说明调用方应答后需重新动作|src/backend/cbrowser/agent_executor/session.py click；docs/specs/agent_executor.md；tests/unit/test_agent_executor_cli.py（fake hang_press 分支）|
|t030_test_f001|important|已修|超时/取消零测试；补 step_timeout（wait_for_target_count）、dialog_timeout（dialog_wait）、dialog_not_open、invalid_program（非法 answer）、程序超时 step_timeout 与任务取消 cancelled 及两种情形下的 fail-safe 清理|tests/unit/test_agent_executor_cli.py|
|t030_test_f002|important|已修|prompt + promptText 无真实浏览器验证；新增 prompt 集成测试：click 打开 prompt → accept + promptText → 页面记录 exact 文本|tests/integration/test_agent_executor_chain.py::test_executor_dialog_prompt_accepts_text|
|t030_test_f003|important|已修|set_input_files 零测试；补 unit fake 用例与真实浏览器用例；实测挖出产品 bug：跨调用新会话未请求 document 时 pushNodes 报“Document needs to be requested first”，已修 set_input_files 在同会话先取 document（depth 0）|tests/unit/test_agent_executor_cli.py；tests/integration/test_agent_executor_chain.py::test_executor_set_input_files；src/backend/cbrowser/agent_executor/session.py set_input_files；fixture 增加 file input|
|t030_test_f004|minor|已修|安装入口与 --help 无冒烟；补模块 --help 断言（含四旗标）与 pyproject 入口声明断言|tests/unit/test_agent_executor_cli.py::test_cli_help_smoke_and_entrypoint_declaration|
|t030_test_f005|minor|已修|固定 sleep 抖动；script 清理两处改带超时的轮询（导航中 evaluate 抛错以哨兵计为未就绪，不误判为 marker 缺失），关闭拒绝测试改 10 次存活轮询并注释即时抽查与长期存活分工|tests/integration/test_agent_executor_chain.py；tests/integration/test_automation_probe_chain.py|
|t030_test_f006|minor|已修|两个 probe 测试默认 skip（引擎缓存检测未命中）；engine_cache_dir 增包默认 ~/.cloakbrowser 候选（与链测试已接受的默认一致），skip 信息明示 CBROWSER_T029_ENGINE_CACHE；两测试现无 env var 亦真实运行并通过|tests/fixtures/automation_probe/harness.py engine_cache_dir；tests/integration/test_automation_probe_chain.py skip 信息|

未进表提示（code 侧结论段，非 finding）：transport.py 死代码 try/except 已删（proxy=None 直赋）；session.close 未取消 _attach_tasks 无可观测影响（CLI 进程退出即终结），不改；隧道 backstop 对 setAutoAttach 会话的漏判可能记为 t031 排他设计确认项。

### Round 2（待派发，执行者侧已就绪）

- R1 全部 16 条 finding 已按上表修复并实测通过（unit 932 passed + 1 存量 hygiene；chain 集成 8/8；两 probe 测试无 env var 亦真实运行并通过；diff --check 干净）。
- R2 审阅 prompt 已渲染至 `.scratch/review_prompts_r2/`（code/test 各一），但执行者会话两次派发 review 子代理均被运行时以“subagent bootstrap is no longer authorized”拒绝（非瞬时故障），R2 无法在本会话内完成；check_review_status 当前状态为 overall=FAIL（R1 结论）、review_scope=stale（R1 后有改动）、round=1。恢复入口：由主会话派发 code/test 两路 R2 复审（读 `.scratch/review_prompts_r2/` 的 prompt，覆盖写 review_code.md/review_test.md，round 写 2），双路 PASS 后执行者（或接管者）按流程写 handoff、跑 preflight、finish 单 commit、exact cleanup。执行 commit 尚未创建，工作区未提交改动完整、无残留进程。
- 主会话裁决（2026-11-04）：f002 边界解读不成立——task 设计行明确要求否则分支由容器内常驻 Agent 维护 Dialog 状态，“Chrome 自动消解”不在设计行列举的机制内；AC-006 因此取消勾选（主会话已同步改 task.md 勾选态，此为执行者请求的主会话裁决记录，非实现侧新增内容），常驻 Agent 分支改归 t031 设计输入（主会话将在 t031 派发中明确写入），不另立 pending；R2 须核查 task.md 勾选态与本裁决一致。
- 主会话补充裁决（2026-11-04，A 方案）：finish 门禁机械要求 task.md 验收标准节全部 AC 打勾（lifecycle.py _close_task 扫描勾选态，无 deferred 豁免态），未勾选的 AC-006 使 finish 永远过不了；故 AC-006 按 t024 先例改为打勾+行内 deferral 注（其 AC-001/AC-015 均为打勾+追踪说明、验证义务归 p027），勾选表示带明确 deferral 接受、非已实现；deferral 本身不变，仍归 t031 设计输入。
- R2 已完成（2026-11-04，主会话派发）：code/test 双路均为 PASS，reviewed_scope 一致，R1 16 条全部消除；code R2 新立 minor t030_code_f011 一条，处置见下表。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t030_code_f011|minor|已修|note.md 处置表 f002 行“AC-006 维持勾选”与裁决后现状矛盾；已在该行追加主会话裁决引用，标注该判断被裁决取代、AC-006 已取消勾选、常驻分支归 t031；R1 原行文字未改写|note.md 处置表 f002 行、Round 2 裁决段落|
|t030_code_f012|minor|已修|note.md 收尾报告“结果”行“AC-006 未勾选”与 task.md 现行 [x] 态及结果摘要行“打勾+行内 deferral 注”矛盾；已将该行改为与摘要行一致的表述（打勾+行内 deferral 注，勾选为带 deferral 接受、沿 t024 先例，非已实现）；R1/R2/R3 原文未改写|note.md 收尾报告结果行、结果摘要行|

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：部分满足——AC-006 打勾+行内 deferral 注（勾选为带 deferral 接受，沿 t024 先例，非已实现），deferred 归 t031 设计输入；其余 AC 满足
- 测试：contract 169 过；unit 932 过 + 1 skipped + 1 存量失败（test_repo_hygiene，t027 归档绝对路径，干净 base 同 ID）；集成链测试 8/8；前端 204 + test:types + build 过；E2E collect 99；git diff --check 干净；零新增失败
- 黑盒：testing.md blackbox_verify 为 E2E 必需模式（真实 Docker/镜像），本机无 Docker，按队列门禁口径跳过并按 pass 计；替代验收为真实 Chromium 全链集成实跑（8/8）与 probe 政策测试实跑；真实镜像黑盒义务归 t032
- review：full review 2 轮：R1 双路 FAIL（16 条）→ 全部已修；R2 双路 PASS（code 新 minor f011 已处置，test 零新 finding）；check_review_status overall=PASS、review_scope=ok、round=2
- AC 判定：见 `task.md` 行内打勾

### 结果摘要

- AC-001–005、007–011 满足（AC-011 测试侧实测链通过；代码侧未重跑集成链，计 trust_prior）；AC-006 打勾+行内 deferral 注：CLI 可应答分支与自动消解分支已实现，容器内常驻 Agent 分支未在 t030 实现，归 t031 设计输入（主会话裁决，见 Round 2 裁决段落；勾选为带 deferral 接受，沿 t024 先例，非已实现），不另立 pending
- 遗留：t032 真实镜像黑盒义务；t031 设计输入：常驻 Agent 分支、隧道 backstop 对 setAutoAttach 会话的漏判确认项（R1 code 侧未进表提示）

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
