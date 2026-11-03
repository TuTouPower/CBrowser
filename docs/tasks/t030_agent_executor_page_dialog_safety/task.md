# Task spec

## 背景

把 CLI、页面账本、Dialog 防挂起和 snapshot/ref 合成一个可用执行器交付，避免先提供危险裸执行再补生命周期保护。复用 t029 候选兼容边界，真实目标引擎采用由 t032 最终验证；控制权强制执行另由 t031 完成。

## 契约区

### 范围

- 提供读取 stdin JS 的宿主 CLI，单次会话内多步动作/等待/提取、结构化结果/稳定错误及取消/超时；通过既有 cbat\_ 认证隧道连接。
- 页面来源、任务管理权与清理权限分离；稳定标识绑定 Profile/runtime/target，支持无刷新 adopt、popup 归属与保守清理。
- 提供紧凑 snapshot/locator 与跨调用短期 ref；绑定 frame/document/节点，失效必须重新 snapshot，优先复用 Playwright 现有观察/定位能力。
- 动作前建立 JS Dialog 监听，提供 accept/dismiss/promptText，处理 pending 命令及跨 CLI 调用遗留；权限/设备提示显式需真人，预留 t031 handOff 接口。
- 薄入口 Skill + CLI 动态版本规范/help/错误说明随实现交付；不安装到用户全局 skill 目录。

### 非范围

- 不实现 ego 闭源 TaskSpace/native snapshot，不新造完整 locator 引擎、经验包或无必要 daemon。
- 不承诺不可检测，不默认启用生产 XTEST；不提供任意 shell RPC；不把原始任意 CDP/evaluate 伪装成只读。
- 本 task 不完成真人抢占强制闸门；t031/t032 完成前不对外宣称人机安全共用，禁止绕开后续验收发布。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001：CLI 经正式 Profile 认证入口执行多步导航/定位/输入/等待/提取并输出可机器读取结果；中途错误、超时、取消可区分，结果不泄漏凭证、Cookie 或用户私密数据。
- [ ] AC-002：已有页面/用户同时新建页面默认 user/unknown；仅可证明由本任务创建的页面可自动清理。adopt 保留来源且不刷新/导航，关闭权限需单独显式授权，不能由 managed=true 推导。
- [ ] AC-003：popup 只在归属证据充分时纳入本任务；旧 runtime、已关闭 target、导航后 document 与被替换节点的句柄/ref 均拒绝，不能按 URL/标题/索引或重用 ID 误绑定其他页面。
- [ ] AC-004：紧凑 snapshot 与唯一 locator 解析到同一 frame/document/节点；跨 CLI 调用映射有效且 iframe/OOPIF 不串节点，失效要求新快照，不注入全局探测变量或 synthetic-event 输入回退。
- [ ] AC-005：alert/confirm/prompt/beforeunload 可明确应答及 promptText；无 handler 时采用保守取消语义（alert 只关闭，不对 confirm/prompt/beforeunload 默认 accept），应答可在触发命令 pending 时进行，不被同一队列锁死。
- [ ] AC-006：CLI 退出后遗留 Dialog 能由下一调用识别并在页面命令无响应时恢复；多客户端只由当前授权处理方应答，超时不自动重放点击/提交且不关闭 Profile。
- [ ] AC-007：权限/设备提示不被静默授权，给出需真人处理结果并可供 t031 handOff 消费；文件选择与权限提示分开，缺少可检测事件时明确限制。
- [ ] AC-008：正常/异常/取消清理均保留用户/unknown 页面、浏览器和下载捕获；最后一内部 Tab 不导致意外停止，或在不能安全保留时拒绝清理并报告原因。
- [ ] AC-009：薄入口 Skill 能引导调用版本匹配动态规范，help、公开 API 与稳定错误一致；文档包含生命周期、授权和失效规则，凭证不写入 Skill/账本。
- [ ] AC-010：云端真实 Chromium 场景覆盖以上页面、ref、Dialog 与 CLI 行为，另有正式认证隧道集成测试；目标引擎用例可收集并逐条交给 t032，不以模拟权限弹窗作为原生验证。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；AC 中“目标探针/用例交付”只验入口、断言、报告和收集，不表示已完成目标实跑。真实环境行为执行只在 t032 判定。

## 上下文区

### 执行环境与参考来源

- 执行环境：云端 Muse。完成实现、触达生产逻辑的 unit/integration、可用的普通 Chromium 测试，以及可收集的真实环境用例和逐项运行说明。不要求访问宿主 Mac、OrbStack、用户局域网或真实 CloakBrowser/Stream 镜像；这些执行义务集中到 t032。本 task 的 AC 只验云端交付，不把模拟结果、collect-only、skip 或历史 trust_prior 当作目标环境 PASS。代码交付完成不表示目标环境已验收；t032 通过前不得据此发布或宣称指纹安全。

- ego-lite 参考仓库：https://github.com/citrolabs/ego-lite ；固定研究基线：https://github.com/citrolabs/ego-lite/tree/12407167f84a58af24044f072868051952131491 。云端可直接读取公开源码，无需本机目录。其 AGENTS.md 明确只开源 harness/Skill，浏览器本体与 globalThis.ego 原生绑定闭源；只能借鉴公开实现与故障案例，不依赖原生绑定，不照搬合成事件兜底，不将上游效果当成本项目证据。

- 来源：p030、p032、p033；2026-11-04，main@c6a9322 核实。当前只有透明 CDP 通路，没有宿主 CLI/页面账本/ref 生命周期/完整 Dialog 路由。p030 的首版需要 p032/p033 保护，因此合并而不拆成三个实现 task。ego 参考 page-ledger/page-model/page-ref-registry/run/browser-runtime 与 skill-body；指纹安全和闭源能力均未被证实。

### 有意不测

- 宿主 Mac/OrbStack、目标 CloakBrowser、真实媒体/X11/指纹站点：当前 task 执行端为云端 Muse，统一由 t032 执行；不得记为 PASS。

### 测试策略

- CLI 子进程与真实普通 Chromium 测试，注入超时、进程退出、导航、替换 DOM、iframe/OOPIF、用户并发新页和 popup；触达生产账本/引用注册表，不能仅测测试模型。
- Dialog 使用真实用户激活动作和 pending 命令测试；跨进程重开验证状态恢复；权限检测不支持时显式错误。
- 只持久化必要元数据，session/objectId 不未经验证跨进程复用；真实字体/指纹/目标 Dialog/最后 Tab 验证交 t032。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无（云端候选能力以 t029 已核实 API 为边界）；不满足候选能力的行为须先完成云端最小实验再实现，不能留裸假设或复制 ego 原生调用。目标差异由 t032 验收。

### 风险与回退

- 风险：清理归属错误会丢用户页面；引用串 frame 会误操作；Dialog 监听竞争或超时后重放会重复业务动作。
- 回退：回退执行器 commit 并保留必要用户状态；连接退出仅断开本任务 transport，不调用 browser/context/Profile close；失败时清理范围不扩大。

### 依赖与约束

- 硬依赖 t029，需其执行结果已进入本 task 基线。
- 云端/本地边界遵循“执行环境与参考来源”；真实执行义务只在 t032 判定。

### Finalization 时更新的 blueprint

- docs/blueprint/automation.md：CLI、账本、ref、Dialog 与 Skill 契约。
- docs/blueprint/security.md：凭证、清理权限与任意代码信任边界。
- docs/blueprint/testing.md：云端/目标引擎分层验证。
