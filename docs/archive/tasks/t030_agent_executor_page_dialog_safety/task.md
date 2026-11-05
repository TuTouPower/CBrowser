# Task spec

## 背景

把 CLI、页面账本、Dialog 防挂起、snapshot/ref 与隧道层保护合成一个可用执行器交付，避免先提供危险裸执行再补生命周期保护。复用 t029 的候选边界、指纹增量结论与 Dialog 基线；真实镜像复核由 t032 完成；控制权强制执行另由 t031 完成。已核实现状：

- 隧道透明转发（`runtime_agent/agent.py:433-442`）：任意脚本调用 `browser.close()` 会使 Profile 按 normal exit 停止且不恢复；Playwright 默认 context 仿真会在连接期间覆盖下载行为。
- 常驻 cdp_proxy 只监听下载事件（`cdp_proxy.py:75`）；客户端退出后不再有任何组件跟踪页面 Dialog。
- Playwright `get_by_ref` 只针对该 frame 最近一次 snapshot 解析，新连接不保留；Playwright Page 不暴露 targetId。
- `.claude/skills`、`.agents/skills` 下均为指向 `.repo_template` 的软链，产品 Skill 放入会被模板同步覆盖；`pyproject.toml` 无 CLI entrypoint，`cloakbrowser` 只声明 `playwright>=1.53`。

## 契约区

### 范围

- 读取 stdin JS 的宿主 CLI：单次会话内多步动作/等待/提取、结构化结果与稳定错误、取消/超时；经既有 cbat\_ 认证隧道连接；在项目打包中定义 entrypoint 并精确固定 Playwright 版本。
- 隧道层保护：runtime_agent CDP 代理拒绝外部客户端的 Browser.close 及 t029 列出的其他浏览器级破坏性命令；自动化会话期间外部下载行为变更不得绕过 Artifact 捕获。
- 页面账本：来源、任务管理权与清理权限分离；标识绑定 Profile/runtime_instance_id/targetId（targetId 经 CDP 会话获取，不依赖 Playwright 内部标识）；支持无刷新 adopt、popup 归属、保守清理与最后 Tab 保护。
- snapshot/locator：单次调用内复用 Playwright aria snapshot 与定位；跨调用短期 ref 由自建注册表绑定 runtime_instance_id、targetId、frameId、loaderId 与 backendNodeId，使用前逐项校验，失配即要求重新 snapshot。
- Dialog：动作前建立监听，提供 accept/dismiss/promptText，处理 pending 命令；跨 CLI 调用遗留 Dialog 的机制按 t029 AC-006 证据选择——新连接能得知并应答时由 CLI 处理，否则由容器内常驻 Agent 只启用所需能力维护 Dialog 状态并经既有隧道暴露；选择与依据写入 note.md 与 automation.md。
- 权限/设备提示显式需真人，预留 t031 handOff 接口。
- 薄入口 Skill + CLI 动态版本规范/help/错误说明随实现交付，Skill 放在产品源码或资产目录，不放模板软链目录，不安装到用户全局 skill 目录。

### 非范围

- 不实现 ego 闭源 TaskSpace/native snapshot，不新造完整 locator 引擎、经验包或无必要 daemon。
- 不承诺不可检测，不默认启用生产 XTEST；不提供任意 shell RPC；不把原始任意 CDP/evaluate 伪装成只读。
- 不完成真人抢占强制闸门与外部客户端排他；t031/t032 完成前不对外宣称人机安全共用，禁止绕开后续验收发布。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。review 判 FAIL 且需修改交付内容时，实施 Agent 撤回全部打勾，修复并重验后重新打勾；reviewer 用 `TICK-VALID` / `TICK-VOID` 逐条判定。

<!-- /规范 -->

- [x] AC-001：CLI 经正式 Profile 认证入口执行多步导航/定位/输入/等待/提取并输出可机器读取结果；中途错误、超时、取消可区分；CLI 自身输出、错误、日志与账本不含自动化凭证、Cookie 或认证头，默认不导出 Cookie/存储；调用方脚本主动返回的数据由调用方负责并在文档中说明。
- [x] AC-002：已有页面与用户同时新建的页面默认 user/unknown；仅可证明由本任务创建的页面可自动清理；adopt 保留来源且不刷新/导航，关闭权限需单独显式授权，不能由 managed=true 推导。
- [x] AC-003：popup 只在归属证据充分时纳入本任务；旧 runtime、已关闭 target、导航后 document 与被替换节点的句柄/ref 均被拒绝，不能按 URL/标题/索引或重用 ID 误绑定其他页面。
- [x] AC-004：紧凑 snapshot 与唯一 locator 解析到同一 frame/document/节点；跨调用 ref 仅在 runtime、target、frame、loader 与节点标识全部校验一致时可用，任一失配返回明确的失效错误并要求新快照，不静默重新解析；iframe/OOPIF 不串节点；不注入全局探测变量，不使用 synthetic-event 输入回退。
- [x] AC-005：alert/confirm/prompt/beforeunload 可明确应答及 promptText；无 handler 时采用保守语义（alert 只关闭，confirm/prompt/beforeunload 不默认 accept）；触发命令 pending 时仍可应答，不被同一队列锁死。
- [x] AC-006：CLI 退出后遗留的 Dialog 能由下一调用识别，并在页面命令无响应时恢复，机制与 t029 AC-006 证据一致；超时不自动重放点击/提交，不关闭 Profile；同一 Profile 由当前执行器会话应答，其他外部客户端的排他由 t031 保证。（主会话裁决 2026-11-04：CLI 可应答分支已实现；容器内常驻 Agent 分支未在 t030 实现，归 t031 设计输入，见 note.md Round 2 裁决；本勾选为带 deferral 接受（沿 t024 先例），非已实现。）
- [x] AC-007：权限/设备提示不被静默授权；可检测时返回需真人结果并可供 t031 handOff 消费；不可检测的情形在文档中列为限制并以明确错误或超时呈现；文件选择与权限提示分开处理。
- [x] AC-008：正常/异常/取消清理均保留用户/unknown 页面、浏览器和下载捕获；最后一个内部 Tab 不导致意外停止，不能安全保留时拒绝清理并报告原因。
- [x] AC-009：经隧道发送的 Browser.close 及 t029 清单中的浏览器级破坏性命令被拒绝并返回稳定错误，Profile 不因执行器或调用方脚本动作停止；自动化会话期间发生的下载仍进入 Artifact 捕获。
- [x] AC-010：薄入口 Skill 引导调用版本匹配的动态规范，help、公开 API 与稳定错误一致；文档包含生命周期、授权、失效与隧道拒绝规则；凭证不写入 Skill 或账本。
- [x] AC-011：云端真实 Chromium 与目标引擎场景覆盖以上页面、ref、Dialog、隧道保护与 CLI 行为，另有正式认证隧道集成测试；真实镜像用例可收集并逐条交给 t032；不以模拟权限弹窗作为原生验证。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；AC 中“目标探针/用例交付”只验入口、断言、报告和收集，不表示已完成目标实跑。真实环境行为执行只在 t032 判定。

## 上下文区

### 执行环境与参考来源

- 执行环境：云端 Muse。完成实现、触达生产逻辑的 unit/integration、真实 Chromium 与目标引擎（同 t029 的 CloakBrowser linux-x64 二进制）测试，以及可收集的真实镜像用例和逐项运行说明。不要求访问宿主 Mac、OrbStack、用户局域网或真实 CloakBrowser/Stream 镜像；这些执行义务集中到 t032。本 task 的 AC 只验云端交付，不把模拟结果、collect-only、skip 或历史 trust_prior 当作目标环境 PASS。代码交付完成不表示目标环境已验收；t032 通过前不得据此发布或宣称指纹安全。

- ego-lite 参考仓库：https://github.com/citrolabs/ego-lite ；固定研究基线：https://github.com/citrolabs/ego-lite/tree/12407167f84a58af24044f072868051952131491 。云端可直接读取公开源码，无需本机目录。其 AGENTS.md 明确只开源 harness/Skill，浏览器本体与 globalThis.ego 原生绑定闭源；只能借鉴公开实现与故障案例，不依赖原生绑定，不照搬合成事件兜底，不将上游效果当成本项目证据。

- 来源：p030、p032、p033；2026-11-04，main@c6a9322 核实，同日按三方审阅修订。p030 的首版需要 p032/p033 保护，因此合并而不拆成三个实现 task。ego 参考 page-ledger/page-model/page-ref-registry/run/browser-runtime 与 skill-body；指纹安全和闭源能力均未被证实。审阅补充：外部 Browser.close 停 Profile、连接期间下载覆盖、`get_by_ref` 单连接语义、targetId 无公开 API、遗留 Dialog 需常驻跟踪的可能、凭据 AC 不可由任意脚本保证、Skill 落点与 Playwright 版本固定。

### 有意不测

- 真实 arm64 镜像、宿主 Mac/OrbStack、真实媒体/X11/指纹站点：统一由 t032 执行；不得记为 PASS。

### 测试策略

- CLI 子进程与真实 Chromium/目标引擎测试，注入超时、进程退出、导航、替换 DOM、iframe/OOPIF、用户并发新页和 popup；触达生产账本/引用注册表与 runtime_agent 隧道代理，不能仅测测试模型。
- Dialog 使用真实用户激活动作和 pending 命令测试；跨进程重开验证状态恢复；权限检测不支持时显式错误。
- 隧道保护以真实 Playwright `browser.close()`、raw CDP Browser.close 与下载行为覆盖命令验证拒绝和 Artifact 捕获。
- 只持久化必要元数据，session/objectId 不未经验证跨进程复用；真实字体/指纹/目标 Dialog/最后 Tab 验证交 t032。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无（云端候选能力以 t029 回填的已核实结论为边界）；t029 某项为结论不足时，对应能力须先完成云端最小实验再实现，不能留裸假设或复制 ego 原生调用。真实镜像差异由 t032 验收。

### 风险与回退

- 风险：清理归属错误会丢用户页面；引用串 frame 会误操作；Dialog 监听竞争或超时后重放会重复业务动作；隧道命令过滤遗漏破坏性命令；常驻 Dialog 跟踪引入指纹变化。
- 回退：回退执行器 commit 并保留必要用户状态；连接退出仅断开本任务 transport，不调用 browser/context/Profile close；失败时清理范围不扩大。

### 依赖与约束

- 硬依赖 t029，需其执行结果已进入本 task 基线；任一 t029 级别判为新增变化时须避开该级能力或携证据修订方案。
- 已知基线失败 `tests/integration/test_api_search_defaults_routes.py::test_retry_route_requires_csrf_and_maps_outcomes` 归 t026 修复；t026 合入前本 task 门禁按同 ID 存量对照，不重复修复，不得新增其他失败。
- 云端/本地边界遵循“执行环境与参考来源”；真实执行义务只在 t032 判定。

### Finalization 时更新的 blueprint

- docs/blueprint/automation.md：CLI、账本、ref 注册表、Dialog 机制、隧道拒绝规则与 Skill 契约。
- docs/blueprint/security.md：凭证、清理权限、隧道过滤与任意代码信任边界。
- docs/blueprint/decisions.md：CDP 隧道由透明转发改为拒绝浏览器级破坏性命令的 ADR。
- docs/blueprint/testing.md：云端/真实镜像分层验证。
- docs/specs：新增自动化执行器 spec 并登记 specs_index。
