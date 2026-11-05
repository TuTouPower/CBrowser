---
tid: "t029"
slug: "automation_compatibility_probe_harness"
title: "交付自动化兼容性基线与目标引擎验证探针"
status: "done"
branch: "t029_automation_compatibility_probe_harness"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "2c4d78ac8df3aaa001d489b575169a0b95422dbd"
depends_on: ""
conflicts_with: ""
note: "来源 p028；云端 Muse 以目标引擎二进制执行指纹增量与 Dialog 基线，真实镜像复核交 t032"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 2026-11-04：从 p028（云端研究及探针；真实引擎结论交 t032） 聚合立项，核实基线 main@c6a9322；只创建 backlog，不 start。
- 云端范围与本地最终 t032 分离；真实环境未执行不能按通过回填。
- 2026-11-04：按三方审阅与用户要求修订：指纹增量（L0–L6）与 CDP/XTEST 比较改为云端以 cloakbrowser linux-x64 目标引擎执行并预先登记阈值，云端前提不可用时向用户报告 BLOCKED；新增 no_defaults、下载覆盖、Browser.close 与 Dialog 基线；最后 Tab/adopt 移交 t030。
- 2026-11-04 执行（云端）：以 t028 分支（2c4d78a）为 base start；preflight PASS（3 项 UNVERIFIED-SPIKE 由本 task 实验回填）。
- 环境前提实测：Playwright 1.64.1 与 cloakbrowser 0.6.4 按 scripts/gate-requirements.txt 全 pin 安装于门禁 venv；目标引擎二进制 146.0.7680.177.5 下载并通过包内 SHA256/Ed25519 校验；Playwright 完整 Chromium（Chrome for Testing 156）另行下载（默认缓存只有 headless shell，探针在缺失时 skip 而非冒充）。本机缺 pulseaudio/openbox/xdotool/libXtst：BrowserRunner 以 HostBrowserRunner 子类仅替换 setup_pulse/setup_display/_configure_window 三个宿主方法，生产 launch 路径其余不变；XTEST 工具以 apt-get download 解压到仓外 scratch 使用（xte + LD_LIBRARY_PATH）。
- 探针结构：观测页/信号/CdpBridge 录制桥/阈值判定在 tests/fixtures/automation_probe/harness.py；外部客户端 probe_client.py（matrix/hold/raw_hold/dialog/input）；采样驱动 run_levels.py；全链集成 tests/integration/test_automation_probe_chain.py（API→Supervisor→Agent UDS→真实浏览器，组件全真、无 echo 替代）；t032 入口 tests/e2e/test_automation_compatibility_probe_e2e.py（CBROWSER_T029_PROBE_E2E=1 门控）。
- 关键排障记录（均为探针侧问题、非产品 finding）：①裸进程启动的有头普通 Chromium 在无窗口管理器 Xvfb 下不发布 DevTools，harness 改用 Playwright persistent context 启动 + DevToolsActivePort 发现。②集成测试曾用阻塞式 subprocess.run 跑外部客户端，冻住同一事件循环上的 Agent UDS 服务、10 秒 ping 超时掐断隧道；改 asyncio.to_thread 后全链通过——定性前以 raw 客户端对照（直连/桥接/全链三段）排除了产品嫌疑。③首轮采样把 client_exit_code 并入信号样本造成伪「新增变化」，已从样本剔除并注明；采样样本目录在样本后自清理（512M tmpfs 曾被 profile 目录撑爆致 StorageError 中断一轮采样）。④观测页 /other 路由 404 空响应使 beforeunload 导航落 chrome-error 人工页，已补真实页面。
- ego-lite 边界：固定 commit 12407167f84a58af24044f072868051952131491 只读研究其公开 harness 与 docs/native-javascript-dialog-requirement.md；浏览器本体与 globalThis.ego 闭源，未作运行依赖，未照搬合成事件兜底。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

### Round 1 (2026-11-04T13:56:25+08:00)

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t029_code_f001|important|已修|classify 把 addScriptToEvaluateOnNewDocument/setAutoAttach 归 other 被 state_changing 过滤，与 spec 清单矛盾；新增 script_injection/target_attach 两类并纳入过滤（与 t029_test_f003 同一问题）|tests/fixtures/automation_probe/harness.py classify_cdp_method / CdpBridge.state_changing_methods|
|t029_code_f002|important|已修|run_levels 输出未走 build_report（无 schema/脱敏），e2e 对 levels 不查 schema；已改 build_report 输出并在 e2e 断言 schema 与各级 verdict|tests/fixtures/automation_probe/run_levels.py；tests/e2e/test_automation_compatibility_probe_e2e.py|
|t029_code_f003|important|已修|「超时后存活」零实测；新增 hold 客户端被 SIGKILL 后浏览器与用户页面存活断言的集成测试（与 t029_test_f007 同一问题）|tests/integration/test_automation_probe_chain.py::test_probe_chain_client_killed_mid_connection_survival|
|t029_code_f004|minor|已修|redact 子串匹配误伤 cookieEnabled；改 token 化规则（敏感词仅在非首 token 或独占 key 时脱敏）并加回归测试|tests/fixtures/automation_probe/harness.py _is_secret_key；tests/unit/test_automation_probe_harness.py|
|t029_code_f005|minor|已修|死代码 READ_FRAME_EVENTS_SCRIPT（与 READ_EVENTS 重复）与 XTestInput.double_click 已删；READ_EVENTS_SCRIPT 已接线到 run_levels 使用|tests/fixtures/automation_probe/harness.py；run_levels.py|
|t029_test_f001|important|已修|Dialog handle_new/beforeunload 关键字段只采集不断言；已在两引擎测试中锁定 opening_replayed/commands_blocked/last_dialog/opening/handled/navigate_completed/final_url 的实测值|tests/integration/test_automation_probe_chain.py dialog 两测试|
|t029_test_f002|important|已修|alert 类型零覆盖；两引擎 dialog 测试均新增 alert pending 一轮并断言 opening 类型与应答完成|同上|
|t029_test_f003|important|已修|同 t029_code_f001，另补 classify 与 state_changing 的 unit 测试|tests/unit/test_automation_probe_harness.py|
|t029_test_f004|important|已修|no_defaults=False 侧不断言 Agent 未捕获；已锁定该轮 download 事件为 download 且 agent_capture 为空|tests/integration/test_automation_probe_chain.py target 测试|
|t029_test_f005|important|已修|交付 run_levels 缺 zoom/焦点争用/XTEST iframe 子场景且 CDP 不记坐标误差；已全部正式化进 run_levels（input_comparison 含 cdp/xtest/zoom/focus_contention，CDP 与 XTEST 均记录 target 与 client_error，XTEST 含 frame 误差），e2e 同步校验结构|tests/fixtures/automation_probe/run_levels.py|
|t029_test_f006|important|已修|3 处 # type: ignore 已消除（两处多余 override 标注删除；unit 处改 dict[str, Any]），全仓探针文件已无 type: ignore|tests/fixtures/automation_probe/harness.py；tests/unit/test_automation_probe_harness.py|
|t029_test_f007|minor|已修|同 t029_code_f003|同上|
|t029_test_f008|minor|已修|拒绝断言仅 != accepted；已锁定为预期拒绝形态集合（握手 403 或 accept 后 close 4401，实测两形态均可出现）并断言全部探针端点为回环地址；Round 2 复核后进一步收紧为精确集合 {close:4401, handshake:InvalidStatus}（残余意见中「DevTools 端口未授权直连尝试」在回环即信任边界的语义下无独立意义，以回环绑定断言为准）|tests/integration/test_automation_probe_chain.py target 测试|

### Round 2 (2026-11-04T14:22:32+08:00)

双路均 PASS；新发现 3 条 minor，均已修，待 Round 3 复核。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t029_code_f006|minor|已修|_is_secret_key 的 apikey 单 token 永不命中 api_key/apiKey 切分形；已加相邻 [api, key] 对命中规则并补单测（含 monkey 不误伤）|tests/fixtures/automation_probe/harness.py _is_secret_key；tests/unit/test_automation_probe_harness.py|
|t029_test_f009|minor|已修|e2e 对 zoom/focus 只验键存在、zoom 无判定字段；run_levels 的 zoom 条目已加 verdict（measured / inconclusive_shortcut_ineffective），e2e 已断言 zoom/focus 条目结构与误差字段|tests/fixtures/automation_probe/run_levels.py；tests/e2e/test_automation_compatibility_probe_e2e.py|
|t029_test_f010|minor|已修|unit 测试使用未导入的 Any；已补 typing 导入|tests/unit/test_automation_probe_harness.py|

### Round 3 (2026-11-04T15:29:00+08:00)

双路均 PASS；代码侧新发现 2 条 minor，均已修，待 Round 4 复核；测试侧无新 finding。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t029_code_f007|minor|已修|_is_secret_key 仍漏 private_key 与复数键形（cookies/api_keys/tokens/secrets/passwords/credentials）：相邻对规则已一般化为尾随 key 且前一 token ∈ {api, private}，集合 token 做单复数归一（去尾 s），并补 credential 进集合；单测断言上述 7 键形均脱敏且 key/monkey/cookieEnabled 保留；unit 单文件 10 passed|tests/fixtures/automation_probe/harness.py _is_secret_key/_SECRET_KEY_TOKENS；tests/unit/test_automation_probe_harness.py test_redact_report_value_catches_private_key_and_plural_forms|
|t029_code_f008|minor|已修|缩放采样两次发送的都是 ctrl+plus，spec 称两种 keysym 已试的表述超出交付代码证据；已把缩放循环元组改为 (ctrl+plus, ctrl+equal)，两种 keysym 各发送一次、采样次数不变，spec 第 61 行两种 keysym 表述现与代码一致，无需改 spec|tests/fixtures/automation_probe/run_levels.py 缩放循环|

### Round 4 (2026-11-04T15:34:00+08:00)

双路均 PASS；代码侧无新 finding，测试侧新发现 1 条 minor，已修，待 Round 5 复核（review 上限 5 轮，本轮为最后一轮额度内复核）。

|finding_id|severity|status|rationale|fix_ref|
|---|---|---|---|---|
|t029_test_f011|minor|已修|zoom 条目未记实际发送的 keysym 列表，若元组被改回 (ctrl+plus, ctrl+plus)，DPR 仍恒 1、verdict 仍 inconclusive、双路误差仍非空，e2e 仍全绿，spec「两种 keysym 已试」表述会再次失去报告证据而不被测试发现；已按 reviewer 建议选项一：zoom 条目补 keysym_attempted 字段（本次发送的 keysym 列表），e2e 断言其等于 ["ctrl+plus", "ctrl+equal"]；unit 单文件 10 passed、e2e collect 2 项、两文件语法校验通过|tests/fixtures/automation_probe/run_levels.py 缩放循环与 zoom 条目；tests/e2e/test_automation_compatibility_probe_e2e.py zoom 断言|
残余说明：t029_test_f008 的 loopback 直连尝试残余维持 minor，不另立项（见 review_test.md Round 4；拒绝精确集合已闭环，回环绑定断言即信任边界）。原处置表曾以“t029_test_f008 残余”单列一行，因 checker 要求 finding_id 严格形如 t029_test_fNNN 且不得重复，收尾时改为本段文字记录，不影响 f008 本体已修结论。

### Round 5 (2026-11-04T16:31:00+08:00)

双路均 PASS，无新 finding。代码侧复核 Round 4 测试侧 f011 的代码侧修复已消除，Round 1–4 全部 finding 保持消除；测试侧复核 f011 已以「发送变量直出字段 + 精确等值断言」闭环，Round 1–4 无回退，f008 拒绝精确集合保持闭环、loopback 残余维持 minor 不另立项。review 上限 5 轮已用满，本轮为终轮。

接管收尾证据修复（2026-11-04，原执行者停滞后由接管执行者执行，未改交付代码/测试）：review_code.md/review_test.md 各轮 target 行本机绝对路径改相对写法（4 处）及一处正文路径表述改写；处置表 Round 4 的残余行因 checker 格式与去重要求改为上段文字记录；本段与 Round 5 记录为收尾补记。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：全部满足（云端范围；真实镜像判定归 t032）
- 测试：逐 suite 以门禁 venv 单跑（未用证据模式，避免内层 run_gates 继承环境变量污染证据目录）。contract 169 passed（基线 169）；unit 859 passed + 1 skipped、1 failed（基线 853 → +6 为本 task harness 单测；唯一失败 test_repo_hygiene 与干净 base 同 ID、仅指向 t027 归档 review 报告的本机绝对路径，按链上分工不在本 task 处置）；integration 134 passed、1 failed（基线 129 → +5 为本 task 全链探针测试；唯一失败 test_ac009_api_supervisor_start_and_stop_coordination 已在 t028 tip 干净 worktree 对照复现、同 ID 存量）；前端 204 passed + test:types + build（与基线一致，本 task 未动前端）；E2E collect 99（基线 97 → +2 为 t032 复核入口，默认 skip）。
- 黑盒：testing.md 的 blackbox_verify 为 E2E 必需模式（真实 Docker/镜像），本机无 Docker，按队列门禁口径跳过按 pass；替代验收为全链集成实跑（真实 API/Supervisor/Agent/目标引擎）与 L0–L6 采样实跑，真实镜像黑盒义务归 t032（入口已交付）。
- review：5 轮双路闭环；Round 5（2026-11-04T16:30–16:31+08:00）代码/测试双路 PASS、无新 finding，全部 critical/important 保持消除，仅 f008 loopback 残余维持 minor 不另立项
- AC 判定：见 `task.md` 行内打勾（AC-001~AC-007 全勾；AC-005 的缩放子项为 INCONCLUSIVE 并已在 spec 记录失败模式与 t032 复核项）

### 结果摘要

- 交付探针全套：tests/fixtures/automation_probe/（harness/probe_client/run_levels）、全链集成 5 测试、harness unit 6 测试、t032 e2e 入口 2 测试；结论 spec docs/specs/automation_compatibility.md（含 t030 拦截清单、t031/t032 输入、证据分级），blueprint automation.md/testing.md 已同步。
- 核心实测结论：L1–L6 指纹增量在预登记阈值下均无新增变化；no_defaults 决定连接期下载归属（True→Agent 捕获、False→客户端覆盖），断开后 rearm 恢复；Dialog 无重放、不阻塞、promptText 不回传、beforeunload 需真实激活；外部 Browser.close 停 Profile（t030 须拦截）；CDP 输入坐标误差 0、XTEST 未校准偏差约 (+10, −10.88) CSS px 且滚轮量不稳定，按预登记规则判定 XTEST 无采用收益。
- 遗留：真实 arm64 镜像/容器 X11/缩放子项复核归 t032（不另立 pending，t032 task 已含）；外站检测器云端不可达记 NOT_RUN。

### 长期文档闭环

本 task 须出现在 specs_index 的关联 task 列；无长期 spec 变更时写 `- specs_index: not_applicable: 具体原因`。正式 spike 须有 report、现存 finding、采纳结论、后续 tid 或无需后续理由；finish 会检查这些引用。
