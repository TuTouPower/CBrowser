# Task spec

## 背景

t015 删 TURN 时误删与 TURN 无关的端到端断言。当前已有网络策略和资源算法测试，但不能拼接为隔离、清理保护、配额至真实画面的全链证据。本 task 补建可执行覆盖，实际目标环境运行统一交 t032。

## 契约区

### 范围

- 按原行为建立现行测试、实际组件和证据缺口映射，复用现有 namespace/IPv6/policy 测试。
- 基于 t026 新拓扑补 Gateway 附着、受管资源清理保护与中途失败回滚测试。
- 补 Supervisor→Gateway→Agent→Stream/Chrome 配额、不可越 FPS cap、布局、motion/static 和 CPU policy 的真实探针；恢复 Agent 替换连接精确断言。

### 非范围

- 不恢复 coturn/TURN 或旧架构文件；不重写已有效覆盖，不把多个组件单测合成 E2E PASS。
- 不承担生产自愈、配额新算法或本地压力执行。

### 验收标准

<!-- 规范（门禁必留，不得删除） -->

只写可观察、可独立验证的行为；每条使用稳定且不复用的 `AC-NNN`。需真实部署或人工环境验证时在编号前加 `[deploy]`。创建时均为未勾选（`- [ ]`）；实施验证通过后由实施 Agent 就地打勾（`- [x]`）；由 Review Agent 独立复核打勾真实性。技术选型不作为行为 AC。

<!-- /规范 -->

- [ ] AC-001：覆盖矩阵逐项列出 p016 原行为、现行入口、触达组件、云端结果与 t032 待执行项；已覆盖条目有明确断言引用，缺口有可收集执行入口。
- [ ] AC-002：交付可执行的真实 Docker 用例，断言合法 Gateway 动态附网、跨 Profile 同条件正负对照、运行容器仍附着拒绝清网、未知 endpoint 保留及部分附网失败只回滚本轮资源；无应用来源过滤制造隔离结果。
- [ ] AC-003：交付真实配额探针，观测链贯通 Supervisor、Gateway、Agent、Stream 和 Chrome，记录投递值、CPU counter/采样窗、限帧值与实际帧数；客户端抬高 FPS 不突破 cap，布局保持且 motion/static、CPU policy 分别有证据。
- [ ] AC-004：交付替换 Agent 场景，明确断言旧连接 close=1001、新旧 conn_id 不同、新连接上下行回复正确且后续 Viewer 持续可用；宽泛超时或异常不算通过。
- [ ] AC-005：云端验证生产组件接线、证据格式和缺项即失败规则；真实用例可收集，未提供镜像/Chrome 的 required 模式明确失败，普通收集不能冒充已运行。
- [ ] AC-006：每次探针资源与证据独立，正常/失败路径均只清理本轮资源并脱敏；运行指令、预算和 artifact 字段逐项映射到 t032。

### 可测试性声明

<!-- 规范（门禁必留，不得删除） -->

逐条说明不可自动测试的 AC 及替代验证；全部可测则写“全部 AC 可自动测试”。

<!-- /规范 -->

全部 AC 可自动测试；AC 中“目标探针/用例交付”只验入口、断言、报告和收集，不表示已完成目标实跑。真实环境行为执行只在 t032 判定。

## 上下文区

### 执行环境与参考来源

- 执行环境：云端 Muse。完成实现、触达生产逻辑的 unit/integration、可用的普通 Chromium 测试，以及可收集的真实环境用例和逐项运行说明。不要求访问宿主 Mac、OrbStack、用户局域网或真实 CloakBrowser/Stream 镜像；这些执行义务集中到 t032。本 task 的 AC 只验云端交付，不把模拟结果、collect-only、skip 或历史 trust_prior 当作目标环境 PASS。代码交付完成不表示目标环境已验收；t032 通过前不得据此发布或宣称指纹安全。

- ego-lite 参考仓库：https://github.com/citrolabs/ego-lite ；固定研究基线：https://github.com/citrolabs/ego-lite/tree/12407167f84a58af24044f072868051952131491 。云端可直接读取公开源码，无需本机目录。其 AGENTS.md 明确只开源 harness/Skill，浏览器本体与 globalThis.ego 原生绑定闭源；只能借鉴公开实现与故障案例，不依赖原生绑定，不照搬合成事件兜底，不将上游效果当成本项目证据。

- 来源：p016；2026-11-04，main@c6a9322 核实。现有 namespace、IPv6、policy failure、资源 monitor 和 Gateway control 测试仍在；缺少完整原 infrastructure 场景与配额真实画面证据。Agent 替换已有基本测试，但未完整恢复 p016 所列精确语义。t024 的 callback 投递断言不能代替实际媒体证据。

### 有意不测

- 宿主 Mac/OrbStack、目标 CloakBrowser、真实媒体/X11/指纹站点：当前 task 执行端为云端 Muse，统一由 t032 执行；不得记为 PASS。

### 测试策略

- 云端先用现有 fixture/生产组件验证新增断言确实观察对应行为，运行相关 unit/integration、E2E collect-only 和证据脱敏测试。
- 真实 Docker 正负隔离、CPU 采样、Chrome 帧率与替换连接由 t032 实跑；不降低旧预算、不用 mock 帧数作为媒体证明。

### 未知契约清单

<!-- 规范（门禁必留，不得删除） -->

未核实的外部契约标为 `UNVERIFIED-BLOCKING` 或 `UNVERIFIED-SPIKE`；核实后改写为结论和验证方式。无则写“无”。

<!-- /规范 -->

- 无（测试交付契约）；目标环境是否满足各行为由 t032 运行，本 task 不认领真实执行 PASS。

### 风险与回退

- 风险：测试只是验证替身或因环境错误产生假负例；强行复原旧文件可能回退拓扑。
- 回退：回退新增测试/探针 commit，不改生产配置；失败现场保留并列真实执行缺口。

### 依赖与约束

- 硬依赖 t026，需其执行结果已进入本 task 基线。
- 云端/本地边界遵循“执行环境与参考来源”；真实执行义务只在 t032 判定。

### Finalization 时更新的 blueprint

- docs/blueprint/testing.md：原行为映射、证据层级与新运行入口。
