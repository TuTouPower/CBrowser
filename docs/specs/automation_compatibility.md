# 需求规范：自动化兼容性基线（t029 探针结论）

本文记录 t029 探针在云端取得的实测基线：目标引擎为 `cloakbrowser==0.6.4` 下载的 CloakBrowser linux-x64 二进制（146.0.7680.177.5），生产 launch args、固定 seed 290029、视口 1280x800、Xvfb 有头；普通 Chromium（Chrome for Testing 156）只用于验证探针机制与链路语义，不作为目标引擎结论。真实 arm64 镜像、容器化 X11/Stream 与真实 Mac Chrome Viewer 的复核由 t032 用同一探针执行，结论冲突时以 t032 为准。

探针组成（`tests/fixtures/automation_probe/`）：观测页与信号采集（`harness.py`）、外部客户端（`probe_client.py`，matrix/hold/raw_hold/dialog/input 五种模式）、L0–L6 采样驱动（`run_levels.py`）、全链集成测试（`tests/integration/test_automation_probe_chain.py`）、t032 复核入口（`tests/e2e/test_automation_compatibility_probe_e2e.py`，`CBROWSER_T029_PROBE_E2E=1` 门控）。报告格式 `automation-probe-report/v1`，含 toolchain 版本、预登记阈值与脱敏后的字段样本；报告不含任何 token 真值。

## 正式通路与候选矩阵（AC-001/AC-003）

- 唯一正式通路：外部客户端 →（`Authorization: Bearer cbat_...`）API automation WS → Supervisor 控制 WS → Agent UDS → 浏览器 loopback CDP。探针全程只经此通路或等价的桥接直连（桥接仅转发并记录命令，不改协议语义；通路等价性由全链测试单独证明）。
- 无 token、错误 token、跨 Profile token 三种未授权连接均被拒绝（非 accepted，连接不建立或以 4401/1011 关闭），无裸 CDP TCP 暴露。
- Playwright `connect_over_cdp` 两种模式均可完成：默认 context 与既有页面发现、popup 打开/关闭、iframe 定位与点击、aria snapshot（mode="ai"）与 `get_by_ref` 解析（ref 含 frame 前缀形如 `f2e1`，跨连接不可复用、只对该连接最近一次 snapshot 有效）、文本输入、滚动。
- 外部客户端以 raw CDP 发送 `Browser.close` 时，目标引擎进程退出、Runner 持久化 stopped 状态——这是当前隧道的既有行为，t030 必须在执行器侧拦截该命令（见拦截清单），不得依赖隧道自觉。

## 下载捕获（AC-002）

连接期间的下载归属由客户端模式决定，实测（目标引擎全链）：

|模式|客户端 download 事件|Agent Artifact 捕获|
|---|---|---|
|`no_defaults=True`|无事件（客户端未在 context 上布防下载行为，点击只触发浏览器默认行为）|捕获（Agent 的 browser 级行为生效，文件以 UUID 名落入 downloads 目录）|
|`no_defaults=False`|有事件，`path()` 可读临时文件|未捕获（Playwright 对默认 context 施加的下载行为覆盖了 browser 级行为）|

- 外部客户端断开后，Agent 的 rearm 恢复 browser 级下载捕获：断开后从存活的用户页面触发的下载仍进入 Agent 目录（全链实测）。
- 安全断开（进程退出/驱动停止）不发送 `Browser.close`、不关闭 context，用户页面与浏览器在自动化子进程正常退出、异常退出（Dialog leave 场景以 `os._exit(3)` 模拟）后均存活。
- Playwright attach 在默认 context 上发出的、会改变共享浏览器状态的命令类别（桥接记录实测）：各域 enable（Page/Log/Runtime/Network/Inspector）、`Page.addScriptToEvaluateOnNewDocument`、`Target.setAutoAttach`、`Page.navigate`、关闭 popup 时的 `Target.closeTarget`，以及 `no_defaults=False` 时的下载/focus/media 仿真设置。完整清单以报告中的 `state_changing_methods` 为准。

## Dialog 基线（AC-006）

普通 Chromium 全链与目标引擎直连两轮实测结论一致：

- `Page.javascriptDialogOpening`/`Closed` 经隧道转发到外部会话，事件含 `hasBrowserHandler=true`；在触发命令（一元 evaluate）pending 期间，同一会话可调用 `Page.handleJavaScriptDialog` 应答，pending 命令随后正常完成。alert/confirm/prompt 三类均然。
- prompt 的 `promptText` 回传在当前基线下不生效：以 accept + promptText 应答后，页面 `prompt()` 返回 `null`（直连与全链一致，属引擎/协议层行为）。t030 若需 prompt 文本输入，不能依赖此路径。
- 客户端进程退出遗留未应答 Dialog 时：Dialog 不会重放到新连接（新会话收不到 opening 事件）；新会话的 `Page.enable` 与其他命令不被阻塞；遗留 confirm 的页面结果为 `false`（已被消解），用户页面保持可用。即当前基线不满足 ego-lite 需求文档的「遗留 Dialog 向新会话重放 opening」一条，t030 的 Dialog 机制须按「遗留即消解、无重放」设计，不得假设重放。
- beforeunload 需要真实用户激活（两种引擎一致）：经真实输入点击页面控件启用后，导航触发 opening 事件、可应答、导航完成；仅以脚本赋值 `window.onbeforeunload`（无用户激活）时，导航不触发 opening 事件、直接完成——脚本武装的 beforeunload 在当前基线下不构成拦截点。

## 指纹增量 L0–L6（AC-004）

判定规则（预先登记）：每级 ≥5 个独立浏览器进程样本；某字段值落在 L0 全部样本之外且在该级 ≥4/5 样本复现，才记为新增变化。观测字段为观测页信号集（navigator/screen/matchMedia/WebGL/canvas 哈希/全局泄漏名单/`document.hasFocus` 等）。外站（BrowserLeaks/CreepJS/Pixelscan）云端不可达，记 NOT_RUN。

实测结果（目标引擎，每级 5 个独立进程样本，同 seed/视口）：

|级别|判定|说明|
|---|---|---|
|L1 raw CDP 连接|无变化|仅 browser 级连接、不启用任何域|
|L2 connect_over_cdp(no_defaults=True)|无变化|页面信号与 L0 一致|
|L3 connect_over_cdp(no_defaults=False)|无变化|默认 context 仿真未在观测字段上产生可复现差异（其下载行为差异见下载一节，属行为覆盖而非页面信号）|
|L4 启用 Runtime/Page 域|无变化|未见 Runtime 域启用的序列化/getter 副作用或全局泄漏（泄漏名单全空，各级一致）|
|L5 snapshot/locator|无变化|utility world 注入未在主世界留下可观察痕迹|
|L6 实际输入（CDP 与 XTEST 各 5 样本）|无变化|输入后信号集与 L0 一致；hasFocus 各级恒为 true|

结论：L1–L6 在本基线下均可被 t030 采用（以本节证据为限）；任一级在 t032 真实镜像复测出现可复现新增变化时，按证据分级一节的否决条件处理。首轮采样曾因把客户端退出码误并入信号样本而全级误报「新增变化」，已剔除并重跑——采样工具不得把运行元数据混入页面信号样本。

## CDP 与 XTEST 输入比较（AC-005）

同为目标引擎 + Xvfb、每种 5 样本（子场景样本数另注）：

|维度|CDP Input（经 Playwright）|XTEST（xte）|
|---|---|---|
|点击坐标|命中目标 client 坐标（5/5，误差 [0, −0.88] CSS px，为 bounding box 浮点与事件整数坐标的取整差，在 1 CSS px 阈值内）|系统偏差恒定 (+10, −10.88) CSS px（5/5 完全一致）：朴素映射（window.screenX/Y + outer/inner 差）在无窗口管理器的 Xvfb 下，Chrome 报告的窗口原点与内容区实际原点不一致；偏差确定性可校准，但未校准误差约 14.8px|
|滚动|wheel delta 精确（请求 300 → scrollTop 300，5/5）|滚轮格数与滚动量不成固定比例（5 格实测 120 或 600 交替），不可精确寻址滚动量|
|键盘/文本|精确|文本输入可用（5/5 得目标文本）；浏览器级缩放快捷键（Ctrl+plus / Ctrl+equal 两种 keysym）未生效、DPR 恒为 1，该维度对比 INCONCLUSIVE，归 t032 在有窗口管理器的真实容器复核|
|iframe|frame 内点击事件齐全（pointerdown/up/click、isTrusted）|可点击且 isTrusted（5/5）；frame 局部坐标系下误差 (+7, −12.81) CSS px，与主页面同源的映射系统偏差（事件 client 坐标为 frame 局部坐标，换算时须减去 frame 元素位置）|
|焦点争用|L3（defaults）客户端保持连接期间，XTEST 点击仍精确到达页面（2/2，误差同基线偏差）、document.hasFocus 恒 true，无争用失败|同左（XTEST 为被测一侧）|
|事件属性|isTrusted=true、pointerType=mouse、movementX/Y=0（与 XTEST 一致）|isTrusted=true；两者的事件字段集在本观测页上无差异|

采用判定（按预登记规则）：CDP 无可复现新增变化、坐标误差 ≤0.88 CSS px（未超过 1 CSS px），故 **XTEST 无采用收益**；t030 以 CDP Input 为唯一正式输入路径，XTEST 只作为 t032 复核与故障诊断工具保留，不建设生产第二驱动。

## t030 必须拦截或避开的命令/能力清单

外部连接经隧道可达、且会改变共享浏览器状态或终止 Profile 的命令，t030 执行器必须在放行前拦截或改写：

- 终止类：`Browser.close`（停 Profile）、`Target.closeTarget`、`Page.close`。
- 下载行为类：`Browser.setDownloadBehavior`、`Page.setDownloadBehavior`（覆盖 Agent 捕获；确需使用时必须在断开后可恢复并留痕）。
- 仿真覆盖类：`Emulation.setUserAgentOverride`、`Emulation.setDeviceMetricsOverride`、`Emulation.setGeolocationOverride`、`Emulation.setTouchEmulationEnabled`、`Emulation.setFocusEmulationEnabled`、`Emulation.setEmulatedMedia`、`Network.emulateNetworkConditions`（改变指纹/视口/网络画像，与 Profile 配置冲突）。
- 注入类：`Page.addScriptToEvaluateOnNewDocument`（对所有未来导航生效的持久注入，须按会话登记并在断开时清理）。
- 域启用类（Page/Runtime/Log/Network/Inspector enable）本身不改页面信号，但启用 Runtime 域是求值副作用的前提，t030 应按会话最小化启用并记录。

清单同时保存在探针代码 `MUST_MEDIATE_METHODS` 中，报告会逐项列出实测出现过的状态改变命令供对照。

## 证据分级与待验项（AC-007）

- 云端已验（目标引擎 linux-x64 + Xvfb）：候选矩阵与全链、下载归属与恢复、Dialog 基线、L0–L6 增量、CDP/XTEST 输入比较。
- 目标待验（t032）：真实 arm64 镜像（引擎 146.0.7680.177.3）同探针复核；容器化 X11/Stream 下的窗口装饰与坐标映射；真实 Mac 上 Chrome Viewer 的焦点与输入行为；真实镜像中外部 Browser.close 后的恢复编排。
- 否决条件：任一级在 t032 复测出现可复现新增变化时，t030 不得采用该级能力，须携证据修订方案；XTEST 只有在 CDP 出现可复现新增变化或坐标误差 >1 CSS px 时才有采用收益（见输入比较结论）。
- t031 输入：控制权交接不得假设 Dialog 重放或 prompt 文本回传；交接期间的下载归属以本 spec 的模式表为准。

## t032 执行口径（2026-11-05 用户决定）

- t032 改用实际交付引擎 `146.0.7680.177.3`，在 Linux arm64 容器内挂载仓库与引擎缓存，安装 pytest/xte 后在 Xvfb 有头环境复跑探针；不再要求云端基线 `146.0.7680.177.5`。
- 与 t029 云端 `.5` 结论只做跨版本参考；任何差异不得直接归因于自动化接入，报告须显式记录引擎版本。
- AC-012 外站人工判读与因果复核移除；可自动采集时记录 BrowserLeaks/CreepJS/Pixelscan 可达性，不可达/样本不足记 `INCONCLUSIVE`。
- AC-013 原生权限/设备选择器、真人 CAPTCHA/2FA、IME 人工交接移出本轮，报告记 `OUT_OF_SCOPE_BY_USER`；自动 CDP/XTEST 比较与程序化 control handoff 仍须执行。
- 容器执行是探针的运行方式，不改变被测生产链路；禁止在 macOS 宿主直接执行 Linux 引擎后声称已验。
