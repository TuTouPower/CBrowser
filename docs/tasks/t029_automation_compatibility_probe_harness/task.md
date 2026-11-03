# Task spec

## 背景

自动化 CLI 优先复用正式 cbat\_ CDP 隧道。当前 SDK/UDS 基础不证明额外 Playwright attach、snapshot/ref、输入和指纹增量无影响。先交付云端可核实的兼容性基线与可复现目标探针，避免云端等待本机硬件而整链阻塞。

## 契约区

### 范围

- 核对 ego-lite 公开 harness、现行 API/Supervisor/UDS 与 Playwright 公共 API，建立候选 API 和失效行为矩阵。
- 用云端可启动的普通 Chromium、真实认证服务/受控隧道验证候选连接、页面发现、popup/iframe/下载、多客户端断开与安全资源释放；目标引擎差异保持显式。
- 交付目标 CloakBrowser 正式隧道兼容探针、固定条件指纹增量对照与 CDP/XTEST 输入精度比较探针；只测试 XTEST 可行性，不建设生产第二驱动。
- 给 t030 提供云端候选连接/输入边界和最小兼容层接口，真实采用结论在 t032 冻结。

### 非范围

- 不把普通 Chromium 结果说成 CloakBrowser/指纹通过，不在云端访问用户本机 Profile 或依赖 ego 原生绑定。
- 不直接宣布 XTEST 优于 CDP、不引入全局探测变量或 isTrusted=false 输入兜底；不建设经验包 p031。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001：云端候选矩阵通过真实 Playwright/Chromium 进程验证 browser-level connectOverCDP、默认 context/既有页面、popup/iframe/下载及断线行为；每项记录版本、方法、事件、响应和限制，非单次 echo。
- [ ] AC-002：自动化子进程正常退出、异常或超时后，已有用户页面/浏览器仍存活且默认下载捕获可恢复；安全断开不发送 Browser.close、context.close 或停止 Profile，给出可运行证据。
- [ ] AC-003：目标兼容探针只经 Profile 限定 cbat\_ API→Supervisor→Agent UDS→loopback，覆盖授权失败、跨 Profile、下载策略覆盖/恢复及重连；无裸 CDP TCP 暴露。
- [ ] AC-004：指纹探针能在固定 seed/引擎/配置/视口下区分现行 runtime 基线、额外 raw CDP attach、Playwright attach、Runtime/Page 启用、snapshot/locator 与实际输入；保存字段级重复样本和外站失败分类，不只记录总分。
- [ ] AC-005：CDP/XTEST 比较探针覆盖 DPR/缩放、装饰/内容区、滚动、iframe、复杂交互与焦点争用；记录坐标误差和事件属性，不将 isTrusted=true 等同于不可检测。
- [ ] AC-006：Dialog 探针覆盖触发命令仍 pending、调用退出遗留 Dialog、下一调用恢复与 beforeunload 真实激活；最后一 Tab 与 adopt/用户并发新页具备生命周期探针。
- [ ] AC-007：所有目标探针可在云端收集/验证参数、报告格式与安全清理；报告明确云端已验、目标待验及潜在否决条件，并给 t030/t031 和 t032 提供逐项输入。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；AC 中“目标探针/用例交付”只验入口、断言、报告和收集，不表示已完成目标实跑。真实环境行为执行只在 t032 判定。

## 上下文区

### 执行环境与参考来源

- 执行环境：云端 Muse。完成实现、触达生产逻辑的 unit/integration、可用的普通 Chromium 测试，以及可收集的真实环境用例和逐项运行说明。不要求访问宿主 Mac、OrbStack、用户局域网或真实 CloakBrowser/Stream 镜像；这些执行义务集中到 t032。本 task 的 AC 只验云端交付，不把模拟结果、collect-only、skip 或历史 trust_prior 当作目标环境 PASS。代码交付完成不表示目标环境已验收；t032 通过前不得据此发布或宣称指纹安全。

- ego-lite 参考仓库：https://github.com/citrolabs/ego-lite ；固定研究基线：https://github.com/citrolabs/ego-lite/tree/12407167f84a58af24044f072868051952131491 。云端可直接读取公开源码，无需本机目录。其 AGENTS.md 明确只开源 harness/Skill，浏览器本体与 globalThis.ego 原生绑定闭源；只能借鉴公开实现与故障案例，不依赖原生绑定，不照搬合成事件兜底，不将上游效果当成本项目证据。

- 来源：p028（云端研究及探针；真实引擎结论交 t032）；2026-11-04，main@c6a9322 核实。现行 automation.md 与 runner/cdp_proxy 已提供认证通路及常驻 CDP。ego-lite 固定版本 AGENTS.md 已在线复核：公开 Node harness 依赖闭源 globalThis.ego，本项目不能直接运行其原生能力。p028 尚无目标引擎/外站/XTEST 实测结论。

### 有意不测

- 宿主 Mac/OrbStack、目标 CloakBrowser、真实媒体/X11/指纹站点：当前 task 执行端为云端 Muse，统一由 t032 执行；不得记为 PASS。

### 测试策略

- 普通 Chromium 测试运行真实浏览器及正式服务组件；测试前下载和缓存只放当前 worktree 允许目录，网络不足须如实报告，不能用 WS echo 替代协议兼容。
- 目标探针先验证输入校验、重复测量、字段差异、秘密脱敏与异常清理，再交 t032；外站受限必须记 NOT_RUN/INCONCLUSIVE。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无（本 task 只承诺普通 Chromium 候选验证与目标探针交付）；CloakBrowser/指纹/原生 XTEST 结论属于 t032 的独立验收，不作为本 task 已验证能力。

### 风险与回退

- 风险：候选连接在 CloakBrowser 上行为不同，指纹观察本身扰动基线；外站波动被误认为工具影响。
- 回退：仅清理本轮独立测试对象，不关闭用户浏览器；若 t032 否决候选，自动化发布保持阻断，携真实证据修订 t030，不能静默增加兜底驱动。

### 依赖与约束

- 无未完成硬依赖。
- 云端/本地边界遵循“执行环境与参考来源”；真实执行义务只在 t032 判定。

### Finalization 时更新的 blueprint

- docs/blueprint/automation.md：候选边界、正式认证通路与待本地采用条件。
- docs/blueprint/testing.md：兼容/指纹/输入探针矩阵与证据分级。
