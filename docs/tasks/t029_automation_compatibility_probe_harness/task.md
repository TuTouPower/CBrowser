# Task spec

## 背景

自动化 CLI 优先复用正式 cbat\_ CDP 隧道。当前 SDK/UDS 基础不能证明额外 Playwright attach、snapshot/ref、输入方式对隐私指纹与浏览器状态无影响，而这正是 t030/t031 整条路线是否可用的判定依据，必须在 t030 实现前取得。已核实现状：

- 隧道完全透明（`runtime_agent/agent.py:433-442`）：外部 `Browser.close` 会使 Chrome 以 exit 0 退出，被判为 normal exit（`runner.py:770`、`recovery_rules.py:63`），Profile 停止且不自动恢复。
- Playwright 1.64.1（`scripts/gate-requirements.txt` 固定）的 `connect_over_cdp` 默认 `no_defaults=False`，会对既有默认 context 施加 accept_downloads、focus 与 media 仿真；Agent 只在外部客户端断开后重置下载捕获（`agent.py:474`），连接期间下载可能绕过 Artifact 捕获。
- 常驻 cdp_proxy 只持有 browser 级连接并监听下载事件（`cdp_proxy.py:75`），不跟踪页面 Dialog。
- `aria_snapshot(mode="ai")` 与 `get_by_ref` 只针对该 frame 最近一次 snapshot 解析，属单连接状态。

### 指纹增量验证是什么

“指纹增量”指：同一引擎、同一 seed/配置/视口下，以“生产 runtime 启动、无任何外部自动化连接”的状态为基线，逐级加入自动化动作后，页面内可观察信号相对基线新增的差异。它衡量的是“自动化本身多暴露了什么”，不是浏览器总体指纹好坏。分级：

|级别|在基线上增加的动作|
|---|---|
|L0|基线：生产 launch args 启动，无外部 CDP 客户端|
|L1|raw CDP browser 级连接，不启用任何域|
|L2|Playwright `connect_over_cdp(no_defaults=True)`|
|L3|Playwright `connect_over_cdp(no_defaults=False)`（默认 context 仿真）|
|L4|页面上启用 Runtime/Page 域（Playwright attach 行为）|
|L5|snapshot/locator（utility world 注入、aria snapshot）|
|L6|实际输入：CDP Input 派发与 XTEST 分别测|

每级观测字段包括：navigator 与 window/screen 指标、`document.hasFocus`/visibility、matchMedia 偏好、CDP 泄漏探针（Runtime 域启用造成的序列化/getter 副作用、绑定或全局变量、utility world 痕迹）、输入事件属性（isTrusted、screenX/Y、movementX/Y、pointerType、时间分布）。观测页与开源检测器在测试内自托管，BrowserLeaks/CreepJS/Pixelscan 等外站可达时作补充。

目标引擎可在云端取得：项目固定的 `cloakbrowser==0.6.4` 包为 linux-x64 下载官方 CloakBrowser 二进制（146.0.7680.177.5；生产 arm64 镜像为 146.0.7680.177.3）。用生产 launch args 与相同 seed/配置在 Xvfb 有头运行即可做增量与输入比较；普通 Chromium 只用于验证探针机制，不作为目标结论。引擎构建差异与容器化环境差异由 t032 在真实镜像上用同一探针复核。

## 契约区

### 范围

- 核对 ego-lite 公开 harness、现行 API/Supervisor/UDS 与 Playwright 公共 API，建立候选 API 与失效行为矩阵，覆盖 `no_defaults` 两种模式。
- 用真实 Playwright 与真实 Chromium/目标引擎，经真实认证服务与隧道组件验证连接、页面发现、popup/iframe/下载、多客户端断开与安全资源释放；记录 Playwright attach 发出的会改变共享浏览器状态的 CDP 命令。
- 在云端以目标引擎执行 L0–L6 指纹增量与 CDP/XTEST 输入比较，并预先登记判定阈值与采用规则；交付同一探针供 t032 在真实镜像复核。
- Dialog 原生行为基线：pending 命令、客户端退出遗留 Dialog 后新连接能否得知与应答、相关命令是否阻塞、beforeunload 激活条件。
- 给 t030 提供候选连接/输入边界、Dialog 机制选择依据与必须拦截的 CDP 命令清单。

### 非范围

- 不把普通 Chromium 结果说成 CloakBrowser/指纹通过；不在云端访问用户本机 Profile 或依赖 ego 原生绑定。
- 不直接宣布 XTEST 优于 CDP，不建设生产第二驱动；不引入全局探测变量或 isTrusted=false 输入兜底；不建设经验包 p031。
- 不实现执行器、页面账本、最后 Tab 或 adopt 生命周期（交 t030）。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001：候选矩阵通过真实 Playwright 进程与真实 Chromium/目标引擎验证 browser 级 `connect_over_cdp`（`no_defaults` 为 True/False）、默认 context/既有页面、popup/iframe/下载及断线行为，并经真实 API→Supervisor 控制面→Agent UDS→Chrome 组件运行；每项记录版本、方法、事件、响应和限制，不以 WS echo 或单次响应代替。
- [ ] AC-002：自动化子进程正常退出、异常或超时后，已有用户页面与浏览器仍存活，安全断开不发送 Browser.close、context.close 或停止 Profile；两种 `no_defaults` 模式下分别记录连接期间与断开后的下载是否进入 Artifact 捕获，并列出 attach 发出的改变共享浏览器状态的 CDP 命令。
- [ ] AC-003：目标兼容探针只经 Profile 限定 cbat\_ API→Supervisor→Agent UDS→loopback，覆盖授权失败、跨 Profile、下载策略覆盖/恢复、重连及外部 Browser.close 当前导致的 Profile 停止；无裸 CDP TCP 暴露。
- [ ] AC-004：在目标引擎（`cloakbrowser` 包下载的 CloakBrowser 二进制、生产 launch args、固定 seed/配置/视口、Xvfb 有头）上执行 L0–L6 增量对照：每级不少于 5 次重复采样，保存字段级样本；某字段值落在 L0 全部样本之外且在该级至少 4/5 样本复现才记为新增变化；每级给出“无变化/新增变化（列字段）/结论不足”及证据；外站不可达记 NOT_RUN，不以总分或 isTrusted=true 证明不可检测。
- [ ] AC-005：在目标引擎与 Xvfb 上比较 CDP 与 XTEST 输入，覆盖 DPR/缩放、装饰/内容区偏移、滚动、iframe、复杂交互与焦点争用，记录坐标误差与 AC-004 的输入事件字段；只有 CDP 存在可复现的新增变化或坐标误差超过 1 CSS px 时才判定 XTEST 有采用收益。
- [ ] AC-006：Dialog 基线在真实 Chromium 与目标引擎上覆盖 alert/confirm/prompt/beforeunload：触发命令 pending 时能否应答、客户端退出遗留 Dialog 后新连接能否得知并应答、Page 等域启用或其他命令是否阻塞、beforeunload 是否需要真实用户激活；结论作为 t030 机制选择输入，不声称执行器行为。
- [ ] AC-007：报告逐项区分云端已验（目标引擎 linux-x64）、目标待验（真实 arm64 镜像、容器化 X11/Stream、真实 Mac Chrome Viewer）与否决条件；给出各级是否可被 t030 采用、t030 必须拦截或避开的命令/能力清单，以及 t031/t032 的逐项输入；全部探针在云端验证参数、报告格式与安全清理。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；AC 中“目标探针/用例交付”只验入口、断言、报告和收集，不表示已完成目标实跑。真实环境行为执行只在 t032 判定。

## 上下文区

### 执行环境与参考来源

- 执行环境：云端 Muse。完成实现、触达生产逻辑的 unit/integration、真实 Chromium 与目标引擎（CloakBrowser linux-x64 二进制）测试，以及可收集的真实镜像用例和逐项运行说明。不要求访问宿主 Mac、OrbStack、用户局域网或真实 CloakBrowser/Stream 镜像；真实镜像复核集中到 t032。本 task 的 AC 只验云端交付，不把模拟结果、collect-only、skip 或历史 trust_prior 当作目标环境 PASS。代码交付完成不表示目标环境已验收；t032 通过前不得据此发布或宣称指纹安全。

- ego-lite 参考仓库：https://github.com/citrolabs/ego-lite ；固定研究基线：https://github.com/citrolabs/ego-lite/tree/12407167f84a58af24044f072868051952131491 。云端可直接读取公开源码，无需本机目录。其 AGENTS.md 明确只开源 harness/Skill，浏览器本体与 globalThis.ego 原生绑定闭源；只能借鉴公开实现与故障案例，不依赖原生绑定，不照搬合成事件兜底，不将上游效果当成本项目证据。

- 来源：p028（云端研究及探针；真实镜像结论交 t032）；2026-11-04，main@c6a9322 核实，同日按三方审阅修订。审阅补充：`no_defaults` 与下载覆盖、外部 Browser.close 停 Profile、跨连接 ref 与 Dialog 行为未知、普通 Chromium 不能代表目标指纹（改为云端直接用目标引擎二进制）、Dialog/最后 Tab/adopt 行为验收归 t030。

### 有意不测

- 真实 arm64 镜像、容器化 X11/Stream、宿主 Mac/OrbStack 与真实 Mac Chrome Viewer：由 t032 用本 task 探针复核；不得记为 PASS。

### 测试策略

- 真实 Chromium 与目标引擎运行正式服务组件；下载与缓存只放当前 worktree 允许目录。
- 目标探针先在普通 Chromium 验证输入校验、重复测量、字段差异、秘密脱敏与异常清理，再在目标引擎采样；外站受限记 NOT_RUN/INCONCLUSIVE。
- 自托管观测页与开源检测器版本固定并记录；L0 样本与各级样本使用新启动、同 seed 的独立浏览器进程。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- Playwright attach 在既有默认 context 上发出的 CDP 命令集及其对下载捕获的影响：UNVERIFIED-SPIKE，由 AC-001/AC-002 实测回填。
- Chromium/CloakBrowser 对遗留 Dialog 的新连接事件重放与命令阻塞行为：UNVERIFIED-SPIKE，由 AC-006 实测回填。
- 目标引擎 L1–L6 指纹增量与 CDP/XTEST 输入差异：UNVERIFIED-SPIKE，由 AC-004/AC-005 实测回填；真实镜像复核由 t032 完成。

### 风险与回退

- 风险：linux-x64 与 arm64 引擎构建差异使结论不完全外推；观察本身扰动基线；外站波动被误认为工具影响。
- 回退：仅清理本轮独立测试对象，不关闭用户浏览器；任一级判为新增变化时，t030 须避开该级能力或携证据修订方案，不能静默增加兜底驱动；t032 真实镜像结论与本 task 冲突时以 t032 为准并回修 t030。

### 依赖与约束

- 无未完成硬依赖。
- 云端环境前提：Playwright 浏览器下载、`cloakbrowser` 二进制下载、Xvfb 与 XTEST 扩展。任一前提不可用时停止相应 AC，向用户报告 BLOCKED 与证据，不以普通 Chromium 结果替代目标结论。
- 已知基线失败 `tests/integration/test_api_search_defaults_routes.py::test_retry_route_requires_csrf_and_maps_outcomes` 归 t026 修复；t026 合入前本 task 门禁按同 ID 存量对照，不重复修复，不得新增其他失败。
- 云端/本地边界遵循“执行环境与参考来源”；真实镜像执行义务只在 t032 判定。

### Finalization 时更新的 blueprint

- docs/blueprint/automation.md：候选边界、正式认证通路、各级增量结论与待真实镜像复核条件。
- docs/blueprint/testing.md：兼容/指纹/输入/Dialog 探针矩阵、阈值与证据分级。
